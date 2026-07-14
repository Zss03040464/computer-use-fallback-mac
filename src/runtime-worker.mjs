import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline';


const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');


export class RuntimeCallError extends Error {
  constructor({ code = 'runtime_error', message = 'Runtime call failed', details = {} } = {}) {
    super(message);
    this.name = 'RuntimeCallError';
    this.code = code;
    this.details = details;
  }
}


export class RuntimeWorker {
  constructor({
    sessionId = randomUUID(),
    pythonPath = path.join(projectRoot, '.venv', 'bin', 'python3'),
    runtimeRoot = path.join(projectRoot, 'runtime'),
    moduleName = 'runtime.worker',
    moduleArgs = null,
    callTimeoutMs = 30_000,
  } = {}) {
    this.sessionId = sessionId;
    this.nextId = 1;
    this.pending = new Map();
    this.closed = false;
    this.exited = false;
    this.callTimeoutMs = callTimeoutMs;
    this.child = spawn(
      pythonPath,
      [
        '-u',
        '-m',
        moduleName,
        ...(moduleArgs ?? ['--session', sessionId, '--runtime-root', runtimeRoot]),
      ],
      { cwd: projectRoot, stdio: ['pipe', 'pipe', 'pipe'] },
    );
    this.stderr = '';
    this.child.stderr.setEncoding('utf8');
    this.child.stderr.on('data', (chunk) => {
      this.stderr = `${this.stderr}${chunk}`.slice(-16_384);
    });
    this.lines = createInterface({ input: this.child.stdout });
    this.lines.on('line', (line) => this.#handleLine(line));
    this.child.on('error', (error) => this.#rejectAll(error));
    this.child.on('exit', (code, signal) => {
      this.exited = true;
      if (!this.closed) {
        this.#rejectAll(new RuntimeCallError({
          code: 'runtime_unavailable',
          message: `Runtime worker exited with code=${code} signal=${signal}`,
          details: { stderr: this.stderr },
        }));
      }
    });
  }

  get pid() {
    return this.child.pid;
  }

  call(command, payload = {}) {
    if (this.closed || !this.child.stdin.writable) {
      return Promise.reject(new RuntimeCallError({
        code: 'runtime_unavailable',
        message: 'Runtime worker is closed',
      }));
    }
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (!this.pending.has(id)) return;
        this.pending.delete(id);
        reject(new RuntimeCallError({
          code: 'runtime_timeout',
          message: 'Runtime call timed out',
          details: { command, timeoutMs: this.callTimeoutMs },
        }));
      }, this.callTimeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      this.child.stdin.write(`${JSON.stringify({ id, command, payload })}\n`, (error) => {
        if (error) {
          this.pending.delete(id);
          clearTimeout(timer);
          reject(error);
        }
      });
    });
  }

  async close() {
    if (this.closed) return;
    try {
      await Promise.race([
        this.call('shutdown', {}),
        new Promise((resolve) => setTimeout(resolve, 500)),
      ]);
    } catch {}
    this.closed = true;
    this.lines.close();
    this.child.stdin.end();
    let exited = await this.#waitForExit(500);
    if (!exited) {
      this.child.kill('SIGTERM');
      exited = await this.#waitForExit(500);
    }
    if (!exited) {
      this.child.kill('SIGKILL');
      await this.#waitForExit(1000);
    }
    this.#rejectAll(new RuntimeCallError({ code: 'runtime_unavailable', message: 'Runtime worker closed' }));
  }

  #waitForExit(timeoutMs) {
    if (this.exited) return Promise.resolve(true);
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.child.off('exit', onExit);
        resolve(false);
      }, timeoutMs);
      const onExit = () => {
        clearTimeout(timer);
        resolve(true);
      };
      this.child.once('exit', onExit);
    });
  }

  #handleLine(line) {
    let response;
    try {
      response = JSON.parse(line);
    } catch {
      this.#rejectAll(new RuntimeCallError({
        code: 'runtime_protocol_error',
        message: 'Runtime emitted invalid JSON',
        details: {},
      }));
      return;
    }
    const pending = this.pending.get(response.id);
    if (!pending) return;
    this.pending.delete(response.id);
    clearTimeout(pending.timer);
    if (response.ok) pending.resolve(response.result);
    else pending.reject(new RuntimeCallError(response.error));
  }

  #rejectAll(error) {
    for (const { reject, timer } of this.pending.values()) {
      clearTimeout(timer);
      reject(error);
    }
    this.pending.clear();
  }
}
