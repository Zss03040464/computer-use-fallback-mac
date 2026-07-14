import { spawn } from 'node:child_process';
import { access, readFile, rename, writeFile } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import path from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { RuntimeWorker } from './runtime-worker.mjs';
import { CompatWorker } from './compat-worker.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');
const venvRoot = path.join(projectRoot, '.venv');
const requirementsPath = path.join(projectRoot, 'runtime', 'requirements.txt');
const installStampPath = path.join(projectRoot, 'runtime', 'requirements.sha256');
const bootstrapLockPath = path.join(projectRoot, 'runtime', 'bootstrap.lock');

const pythonBinPath = path.join(venvRoot, 'bin', 'python3');
const pipBinPath = path.join(venvRoot, 'bin', 'pip');

let bootstrapPromise = null;
let runtimeWorker = null;
let compatWorker = null;

async function pathExists(target) {
  try {
    await access(target);
    return true;
  } catch {
    return false;
  }
}

const bootstrapLockProgram = [
  'import fcntl, json, os, select, signal, subprocess, sys, threading, time',
  '',
  'def write_message(message):',
  '    try:',
  '        print(json.dumps(message), flush=True)',
  '        return True',
  '    except BrokenPipeError:',
  '        return False',
  '',
  'def group_exists(group_id):',
  '    try:',
  '        os.killpg(group_id, 0)',
  '        return True',
  '    except ProcessLookupError:',
  '        return False',
  '    except PermissionError:',
  '        return True',
  '',
  'def wait_for_group_exit(group_id, timeout=None):',
  '    deadline = None if timeout is None else time.monotonic() + timeout',
  '    while group_exists(group_id):',
  '        if deadline is not None and time.monotonic() >= deadline:',
  '            return False',
  '        time.sleep(0.05)',
  '    return True',
  '',
  'def signal_group(group_id, requested_signal):',
  '    try:',
  '        os.killpg(group_id, requested_signal)',
  '    except ProcessLookupError:',
  '        pass',
  '',
  'def terminate_group(process):',
  '    group_id = process.pid',
  '    signal_group(group_id, signal.SIGTERM)',
  '    try:',
  '        process.wait(timeout=1)',
  '    except subprocess.TimeoutExpired:',
  '        pass',
  '    if not wait_for_group_exit(group_id, 1):',
  '        signal_group(group_id, signal.SIGKILL)',
  '    if process.poll() is None:',
  '        process.wait()',
  '    wait_for_group_exit(group_id)',
  '',
  'def drain_stream(stream, destination, limit=10 * 1024 * 1024):',
  '    retained = 0',
  '    for chunk in iter(lambda: stream.read(65536), ""):',
  '        if retained < limit:',
  '            kept = chunk[:limit - retained]',
  '            destination.append(kept)',
  '            retained += len(kept)',
  '    if retained >= limit:',
  '        destination.append("\\n[output truncated at 10 MiB]")',
  '',
  'def run_command(command):',
  '    process = subprocess.Popen(',
  '        [command["file"], *command.get("args", [])],',
  '        cwd=command.get("cwd"),',
  '        stdout=subprocess.PIPE,',
  '        stderr=subprocess.PIPE,',
  '        text=True,',
  '        start_new_session=True,',
  '    )',
  '    stdout_chunks, stderr_chunks = [], []',
  '    stdout_thread = threading.Thread(target=drain_stream, args=(process.stdout, stdout_chunks))',
  '    stderr_thread = threading.Thread(target=drain_stream, args=(process.stderr, stderr_chunks))',
  '    stdout_thread.start()',
  '    stderr_thread.start()',
  '    while process.poll() is None:',
  '        readable, _, _ = select.select([sys.stdin], [], [], 0.1)',
  '        if readable and os.read(sys.stdin.fileno(), 1) == b"":',
  '            terminate_group(process)',
  '            stdout_thread.join()',
  '            stderr_thread.join()',
  '            return None',
  '    if not wait_for_group_exit(process.pid, 1):',
  '        terminate_group(process)',
  '        return_code = process.returncode or 1',
  '        stderr_chunks.append("\\nCommand left background processes; the process group was terminated.")',
  '    else:',
  '        return_code = process.returncode',
  '    stdout_thread.join()',
  '    stderr_thread.join()',
  '    return {"ok": return_code == 0, "code": return_code, "stdout": "".join(stdout_chunks), "stderr": "".join(stderr_chunks)}',
  '',
  'with open(sys.argv[1], "a+", encoding="utf-8") as handle:',
  '    fcntl.flock(handle, fcntl.LOCK_EX)',
  '    print("LOCKED", flush=True)',
  '    for line in sys.stdin:',
  '        try:',
  '            command = json.loads(line)',
  '            result = run_command(command)',
  '            if result is None or not write_message(result):',
  '                break',
  '        except Exception as error:',
  '            if not write_message({"ok": False, "code": None, "stdout": "", "stderr": str(error)}):',
  '                break',
].join('\n');

function acquireBootstrapLock(timeoutMs = 300_000) {
  const child = spawn('python3', ['-u', '-c', bootstrapLockProgram, bootstrapLockPath], {
    cwd: projectRoot,
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  return new Promise((resolve, reject) => {
    let settled = false;
    const lines = createInterface({ input: child.stdout });
    const iterator = lines[Symbol.asyncIterator]();
    const controller = { child, iterator, lines, stderr: '' };
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill('SIGKILL');
      reject(new Error('Timed out waiting for the OS bootstrap lock'));
    }, timeoutMs);
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk) => { controller.stderr += chunk; });
    iterator.next().then(({ value, done }) => {
      if (!settled && !done && value === 'LOCKED') {
        settled = true;
        clearTimeout(timer);
        resolve(controller);
      } else if (!settled) {
        settled = true;
        clearTimeout(timer);
        reject(new Error(`Bootstrap lock helper returned an invalid greeting: ${value ?? '<eof>'}`));
      }
    }, reject);
    child.once('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(error);
    });
    child.once('exit', (code, signal) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(new Error(`Bootstrap lock helper exited code=${code} signal=${signal}: ${controller.stderr}`));
    });
  });
}

async function runBootstrapCommand(controller, file, args) {
  const { child, iterator } = controller;
  if (child.exitCode !== null || child.stdin.destroyed) {
    throw new Error(`Bootstrap controller is unavailable: ${controller.stderr}`);
  }
  child.stdin.write(`${JSON.stringify({ file, args, cwd: projectRoot })}\n`);
  const { value, done } = await iterator.next();
  if (done) throw new Error(`Bootstrap controller exited before returning a command result: ${controller.stderr}`);
  let result;
  try {
    result = JSON.parse(value);
  } catch (error) {
    throw new Error(`Bootstrap controller returned invalid JSON: ${error.message}`);
  }
  if (!result.ok) {
    throw new Error(`Command failed: ${file} ${args.join(' ')}\nExit Code: ${result.code}\nStderr: ${result.stderr}\nStdout: ${result.stdout}`);
  }
  return { stdout: result.stdout, stderr: result.stderr };
}

async function releaseBootstrapLock(controller) {
  const child = controller?.child;
  if (!child || child.exitCode !== null) return;
  child.stdin.end();
  const exited = await new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.off('exit', onExit);
      resolve(false);
    }, 1000);
    const onExit = () => {
      clearTimeout(timer);
      resolve(true);
    };
    child.once('exit', onExit);
  });
  if (!exited && child.exitCode === null) {
    child.kill('SIGKILL');
    await new Promise((resolve) => child.once('exit', resolve));
  }
}

async function writeInstallStamp(digest) {
  const temporary = `${installStampPath}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${digest}\n`, 'utf8');
  await rename(temporary, installStampPath);
}

export async function ensureBootstrapped() {
  if (bootstrapPromise) return bootstrapPromise;

  bootstrapPromise = (async () => {
    const lockProcess = await acquireBootstrapLock();
    try {
      if (!(await pathExists(pythonBinPath))) {
        console.error('[Computer Use Bridge] Creating virtual environment at .venv...');
        await runBootstrapCommand(lockProcess, 'python3', ['-m', 'venv', venvRoot]);
      }

      if (!(await pathExists(pipBinPath))) {
        console.error('[Computer Use Bridge] Bootstrapping pip...');
        await runBootstrapCommand(lockProcess, pythonBinPath, ['-m', 'ensurepip', '--upgrade']);
      }

      const requirements = await readFile(requirementsPath, 'utf8');
      const digest = createHash('sha256').update(requirements).digest('hex');
      let installedDigest = '';
      try {
        installedDigest = (await readFile(installStampPath, 'utf8')).trim();
      } catch {}

      if (installedDigest !== digest) {
        console.error('[Computer Use Bridge] Installing/Updating Python dependencies from requirements.txt...');
        await runBootstrapCommand(lockProcess, pythonBinPath, [
          '-m', 'pip', 'install', '--require-hashes', '-r', requirementsPath,
        ]);
        await writeInstallStamp(digest);
        console.error('[Computer Use Bridge] Python dependencies installed successfully.');
      }
    } finally {
      await releaseBootstrapLock(lockProcess);
    }
  })();

  try {
    await bootstrapPromise;
  } catch (error) {
    bootstrapPromise = null;
    throw error;
  }
}

export async function callCompat(command, payload = {}) {
  await ensureBootstrapped();
  if (!compatWorker) compatWorker = new CompatWorker();
  return compatWorker.call(command, payload);
}

export async function callRuntime(command, payload = {}) {
  await ensureBootstrapped();
  if (!runtimeWorker) runtimeWorker = new RuntimeWorker();
  return runtimeWorker.call(command, payload);
}

export async function closeRuntime() {
  const workers = [runtimeWorker, compatWorker].filter(Boolean);
  runtimeWorker = null;
  compatWorker = null;
  await Promise.all(workers.map((worker) => worker.close()));
}

export function runtimeSessionId() {
  return runtimeWorker?.sessionId ?? null;
}
