import { callHelper } from './src/bridge.mjs';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function samePoint(a, b) {
  return a.x === b.x && a.y === b.y;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function stablePhysicalSample() {
  const first = await callHelper('physical_cursor_position');
  await sleep(80);
  const second = await callHelper('physical_cursor_position');
  return { stable: samePoint(first, second), point: second, first, second };
}

async function verifyPhysicalStableDuring(label, action) {
  const failures = [];
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const sample = await stablePhysicalSample();
    if (!sample.stable) {
      failures.push(`attempt ${attempt}: ambient movement before action (${sample.first.x}, ${sample.first.y}) -> (${sample.second.x}, ${sample.second.y})`);
      continue;
    }

    const before = sample.point;
    const result = await action();
    await sleep(80);
    const after = await callHelper('physical_cursor_position');
    console.log(`${label} physical attempt ${attempt}: before=(${before.x}, ${before.y}) after=(${after.x}, ${after.y})`);
    if (samePoint(before, after)) {
      return result;
    }
    failures.push(`attempt ${attempt}: after action (${before.x}, ${before.y}) -> (${after.x}, ${after.y})`);
  }
  throw new Error(`Physical cursor moved or was not stable during ${label}:\n${failures.join('\n')}`);
}

async function main() {
  console.log('--- STARTING LOCAL CONTROL TEST ---');

  // 1. Permissions check
  console.log('\n[1/6] Checking macOS Permissions...');
  const perms = await callHelper('check_permissions');
  console.log('Permissions Result:', perms);

  // 2. Screenshot
  console.log('\n[2/6] Capturing Screenshot...');
  try {
    const screenshot = await callHelper('screenshot', { targetWidth: 800, targetHeight: 500 });
    const imgPath = path.join(__dirname, 'test_screen.jpg');
    await writeFile(imgPath, Buffer.from(screenshot.base64, 'base64'));
    console.log(`Screenshot captured and saved to: ${imgPath}`);
  } catch (err) {
    console.error('Screenshot failed (this might be expected if screen recording permission is missing):', err.message);
  }

  // 3. Cursor Position
  console.log('\n[3/6] Getting Current Virtual and Physical Cursor Position...');
  const originalPos = await callHelper('cursor_position');
  const originalPhysicalPos = await callHelper('physical_cursor_position');
  console.log('Original Virtual Cursor Position:', originalPos);
  console.log('Original Physical Cursor Position:', originalPhysicalPos);

  // 4. Virtual Mouse Move (move 30 pixels delta without moving physical pointer)
  console.log('\n[4/6] Moving Virtual Mouse...');
  try {
    const targetX = 974;
    const targetY = 684;
    const newPos = await verifyPhysicalStableDuring('move_mouse', async () => {
      await callHelper('move_mouse', { x: targetX, y: targetY });
      return callHelper('cursor_position');
    });
    console.log(`New Virtual Cursor Position:`, newPos);
    if (newPos.x === targetX && newPos.y === targetY) {
      console.log('Virtual mouse move verification: SUCCESS');
    } else {
      throw new Error(`Virtual cursor mismatch: expected (${targetX}, ${targetY}) got (${newPos.x}, ${newPos.y})`);
    }
    console.log('Physical pointer stability verification: SUCCESS');
  } catch (err) {
    console.error('Virtual mouse move failed:', err.message);
    throw err;
  }

  // 5. Write Clipboard
  console.log('\n[5/6] Writing to Clipboard...');
  const testText = `Test text at ${new Date().toISOString()}`;
  await callHelper('write_clipboard', { text: testText });
  console.log(`Wrote text: "${testText}"`);

  // 6. Read Clipboard
  console.log('\n[6/6] Reading from Clipboard...');
  const readText = await callHelper('read_clipboard');
  console.log(`Read text:  "${readText}"`);
  if (readText === testText) {
    console.log('Clipboard verification: SUCCESS');
  } else {
    console.log('Clipboard verification: FAILURE (content mismatch)');
  }

  console.log('\n--- TESTS COMPLETED ---');
}

main().catch(err => {
  console.error('Test execution failed:', err);
  process.exit(1);
});
