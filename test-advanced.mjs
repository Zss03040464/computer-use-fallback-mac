import { callHelper } from './src/bridge.mjs';

async function main() {
  console.log('--- STARTING ADVANCED CONTROL TEST ---');

  // 1. Coordinates mapping
  console.log('\n[1] Testing Coordinate Mapping...');
  const mapRes = await callHelper('map_coordinates', { x: 100, y: 100, to: 'physical' });
  console.log('Map to physical:', mapRes);
  const mapBack = await callHelper('map_coordinates', { x: mapRes.x, y: mapRes.y, to: 'logical' });
  console.log('Map back to logical:', mapBack);

  // 2. OCR Test
  console.log('\n[2] Testing Vision OCR...');
  const ocrRes = await callHelper('ocr', {});
  console.log(`OCR detected ${ocrRes.length} text blocks.`);
  if (ocrRes.length > 0) {
    console.log('First 3 text blocks:', ocrRes.slice(0, 3));
  }

  // 3. Captcha check
  console.log('\n[3] Testing Captcha Detection...');
  const captchaRes = await callHelper('detect_captcha', {});
  console.log('Captcha scan result:', captchaRes);

  // 4. Click verify test
  console.log('\n[4] Testing Click with pre-post screenshots...');
  const physicalBeforeClick = await callHelper('physical_cursor_position');
  await callHelper('move_mouse', {
    x: physicalBeforeClick.x + 12,
    y: physicalBeforeClick.y + 12
  });
  const pos = await callHelper('cursor_position');
  console.log('Current virtual cursor:', pos);
  console.log('Physical cursor before click:', physicalBeforeClick);

  const clickRes = await callHelper('click', {
    x: pos.x,
    y: pos.y,
    button: 'left',
    count: 1,
    verify: true,
    verifyRegionSize: 80
  });
  console.log('Click verification metadata:', {
    clicked: clickRes.clicked,
    hasBefore: !!clickRes.before,
    hasAfter: !!clickRes.after,
    diff: clickRes.diff
  });
  const physicalAfterClick = await callHelper('physical_cursor_position');
  console.log('Physical cursor after click:', physicalAfterClick);
  if (physicalAfterClick.x !== physicalBeforeClick.x || physicalAfterClick.y !== physicalBeforeClick.y) {
    throw new Error(`Physical cursor moved during virtual click: before (${physicalBeforeClick.x}, ${physicalBeforeClick.y}) after (${physicalAfterClick.x}, ${physicalAfterClick.y})`);
  }

  // 5. Popup Close Test
  console.log('\n[5] Testing Popup Closer...');
  const popupRes = await callHelper('detect_and_close_popups', {});
  console.log('Popup closer result:', popupRes);

  console.log('\n--- ADVANCED TESTS COMPLETED ---');
}

main().catch(err => {
  console.error('Advanced test failed:', err);
  process.exit(1);
});
