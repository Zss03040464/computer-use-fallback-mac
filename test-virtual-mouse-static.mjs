import { readFile } from 'node:fs/promises';

const helperPath = new URL('./runtime/mac_helper.py', import.meta.url);
const source = await readFile(helperPath, 'utf8');

const bannedMouseApis = [
  'pyautogui.moveTo(',
  'pyautogui.click(',
  'pyautogui.scroll(',
  'pyautogui.hscroll(',
  'pyautogui.dragTo(',
  'pyautogui.mouseDown(',
  'pyautogui.mouseUp(',
];

const found = bannedMouseApis.filter((needle) => source.includes(needle));

if (found.length > 0) {
  console.error(`Physical pointer mouse APIs still present: ${found.join(', ')}`);
  process.exit(1);
}

console.log('Static virtual mouse guard: PASS');
