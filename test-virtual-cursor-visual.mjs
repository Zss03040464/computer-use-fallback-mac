import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { ensureBootstrapped } from './src/bridge.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pythonPath = path.join(__dirname, '.venv', 'bin', 'python3');
const testPath = path.join(__dirname, 'test-virtual-cursor-visual.py');

await ensureBootstrapped();

await new Promise((resolve, reject) => {
  execFile(pythonPath, [testPath], (error, stdout, stderr) => {
    if (stdout) process.stdout.write(stdout);
    if (stderr) process.stderr.write(stderr);
    if (error) {
      reject(error);
      return;
    }
    resolve();
  });
});
