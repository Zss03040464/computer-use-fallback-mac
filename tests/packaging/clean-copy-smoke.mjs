import { spawn } from 'node:child_process';
import { access, chmod, cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import os from 'node:os';
import path from 'node:path';


const root = path.resolve(import.meta.dirname, '../..');


function run(command, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, stdio: 'inherit' });
    child.once('error', reject);
    child.once('exit', (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} ${args.join(' ')} failed with code=${code} signal=${signal}`));
    });
  });
}


async function waitForPath(target, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await access(target);
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
  throw new Error(`Timed out waiting for ${target}`);
}


function processIsAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === 'ESRCH') return false;
    throw error;
  }
}


const temporary = await mkdtemp(path.join(os.tmpdir(), 'computer-use-clean-copy-'));
const copyRoot = path.join(temporary, 'computer-use-fallback-mac');

try {
  await cp(root, copyRoot, {
    recursive: true,
    filter(source) {
      const relative = path.relative(root, source);
      if (!relative) return true;
      const parts = relative.split(path.sep);
      if (parts.some((part) => ['.git', '.venv', 'node_modules', '.worktrees', '__pycache__'].includes(part))) return false;
      if (relative.startsWith(`runtime${path.sep}sessions${path.sep}`)) return false;
      if (relative.startsWith(`runtime${path.sep}locks${path.sep}`)) return false;
      if (/runtime\/.*\.(?:log|pid|lock|sha256)$/.test(relative)) return false;
      return true;
    },
  });
  await run('npm', ['ci', '--ignore-scripts'], copyRoot);
  await run(process.execPath, ['test-installability.mjs'], copyRoot);

  const wrapperRoot = path.join(temporary, 'crash-wrapper');
  const wrapperPath = path.join(wrapperRoot, 'python3');
  const crashSentinel = path.join(temporary, 'installer.pid');
  const stubbornChildSentinel = path.join(temporary, 'installer-child.pid');
  await run('mkdir', ['-p', wrapperRoot], temporary);
  await writeFile(wrapperPath, [
    '#!/bin/sh',
    'if [ "$1" = "-u" ] && [ "$2" = "-c" ]; then',
    '  exec /usr/bin/python3 "$@"',
    'fi',
    'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then',
    '  echo $$ > "$CRASH_SENTINEL"',
    '  sh -c \'echo $$ > "$CRASH_CHILD_SENTINEL"; trap "" TERM INT; while :; do sleep 1; done\' &',
    '  trap "exit 143" TERM INT',
    '  wait',
    'fi',
    'exec /usr/bin/python3 "$@"',
    '',
  ].join('\n'));
  await chmod(wrapperPath, 0o755);

  const crashingClient = spawn(process.execPath, ['tests/packaging/bootstrap-client.mjs'], {
    cwd: copyRoot,
    env: {
      ...process.env,
      CRASH_CHILD_SENTINEL: stubbornChildSentinel,
      CRASH_SENTINEL: crashSentinel,
      PATH: `${wrapperRoot}:${process.env.PATH}`,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  await waitForPath(crashSentinel);
  await waitForPath(stubbornChildSentinel);
  const orphanCandidatePid = Number((await readFile(crashSentinel, 'utf8')).trim());
  const stubbornChildPid = Number((await readFile(stubbornChildSentinel, 'utf8')).trim());
  crashingClient.kill('SIGKILL');
  await once(crashingClient, 'exit');

  try {
    await run(process.execPath, ['tests/packaging/bootstrap-client.mjs'], copyRoot);
    if (processIsAlive(orphanCandidatePid)) {
      throw new Error('Bootstrap lock was released while a parent-orphaned installer was still running');
    }
    if (processIsAlive(stubbornChildPid)) {
      throw new Error('Bootstrap lock was released while an installer descendant was still running');
    }
  } finally {
    if (processIsAlive(orphanCandidatePid)) {
      try { process.kill(-orphanCandidatePid, 'SIGKILL'); } catch {}
    }
    if (processIsAlive(stubbornChildPid)) {
      try { process.kill(stubbornChildPid, 'SIGKILL'); } catch {}
    }
  }

  await Promise.all([
    run(process.execPath, ['tests/packaging/bootstrap-client.mjs'], copyRoot),
    run(process.execPath, ['tests/packaging/bootstrap-client.mjs'], copyRoot),
  ]);
  const requirements = await readFile(path.join(copyRoot, 'runtime', 'requirements.txt'));
  const expectedStamp = createHash('sha256').update(requirements).digest('hex');
  const actualStamp = (await readFile(path.join(copyRoot, 'runtime', 'requirements.sha256'), 'utf8')).trim();
  if (actualStamp !== expectedStamp) throw new Error('Concurrent bootstrap produced an invalid dependency stamp');
  await access(path.join(copyRoot, 'runtime', 'bootstrap.lock'));
  await run(process.execPath, ['--test', 'tests/node/mcp-transport.test.mjs'], copyRoot);
  process.stdout.write('Clean-copy install smoke: PASS\n');
} finally {
  await rm(temporary, { recursive: true, force: true });
}
