import { execFile } from 'node:child_process';
import path from 'node:path';


const root = path.resolve(import.meta.dirname, '../..');
const python = path.join(root, '.venv', 'bin', 'python3');
const probe = path.join(import.meta.dirname, 'macos_state_probe.py');


export function inspectMacState(command) {
  return new Promise((resolve, reject) => {
    execFile(python, [probe, command], { cwd: root }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr || stdout || `macOS state probe failed: ${command}`));
        return;
      }
      try {
        const response = JSON.parse(stdout);
        if (!response.ok) throw new Error(response.error || `macOS state probe failed: ${command}`);
        resolve(response.result);
      } catch (parseError) {
        reject(parseError);
      }
    });
  });
}
