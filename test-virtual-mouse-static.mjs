import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

const root = path.dirname(new URL(import.meta.url).pathname);
const files = execFileSync('git', ['ls-files', 'runtime', 'src'], { cwd: root, encoding: 'utf8' })
  .trim()
  .split('\n')
  .filter((file) => /\.(?:py|mjs)$/.test(file));
const source = (await Promise.all(
  files.map((file) => readFile(path.join(root, file), 'utf8').catch(() => '')),
)).join('\n');

const bannedMouseApis = [
  'pyautogui.moveTo(',
  'pyautogui.click(',
  'pyautogui.scroll(',
  'pyautogui.hscroll(',
  'pyautogui.dragTo(',
  'pyautogui.mouseDown(',
  'pyautogui.mouseUp(',
  'CGEventPost(',
  'CGEventPostToPid(',
  'activateWithOptions_',
  '"AXRaise"',
];

const found = bannedMouseApis.filter((needle) => source.includes(needle));

if (found.length > 0) {
  console.error(`Physical pointer mouse APIs still present: ${found.join(', ')}`);
  process.exit(1);
}

console.log('Static virtual mouse guard: PASS');
