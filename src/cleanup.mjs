import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';


const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');
const sessionsRoot = path.join(projectRoot, 'runtime', 'sessions');


function isRunning(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}


function commandFor(pid) {
  try {
    return execFileSync('ps', ['-p', String(pid), '-o', 'command='], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return '';
  }
}


export function cleanupSessionOverlay(sessionDirectory) {
  const directory = path.resolve(sessionDirectory);
  if (path.dirname(directory) !== path.resolve(sessionsRoot)) return false;
  const pidPath = path.join(directory, 'overlay.pid');
  let pid;
  try {
    pid = Number.parseInt(fs.readFileSync(pidPath, 'utf8').trim(), 10);
  } catch {
    return false;
  }
  const command = commandFor(pid);
  const expectedState = path.join(directory, 'cursor.json');
  if (
    Number.isInteger(pid)
    && isRunning(pid)
    && command.includes('virtual_cursor_overlay.py')
    && command.includes(expectedState)
    && command.includes(pidPath)
  ) {
    try {
      process.kill(pid, 'SIGTERM');
    } catch {}
  }
  try {
    fs.unlinkSync(pidPath);
  } catch {}
  return true;
}


export function cleanupVirtualCursorOverlay() {
  let entries = [];
  try {
    entries = fs.readdirSync(sessionsRoot, { withFileTypes: true });
  } catch {
    return 0;
  }
  let count = 0;
  for (const entry of entries) {
    if (entry.isDirectory() && cleanupSessionOverlay(path.join(sessionsRoot, entry.name))) count += 1;
  }
  return count;
}
