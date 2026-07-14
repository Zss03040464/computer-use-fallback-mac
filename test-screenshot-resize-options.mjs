import { callHelper } from './src/bridge.mjs';

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function main() {
  console.log('--- STARTING SCREENSHOT RESIZE OPTION TEST ---');

  const fullByWidth = await callHelper('screenshot', {
    targetWidth: 640,
    showVirtualCursor: false,
  });
  assert(fullByWidth.width === 640, `Expected width 640, got ${fullByWidth.width}`);
  assert(fullByWidth.height > 0 && fullByWidth.height < fullByWidth.displayHeight, `Unexpected proportional height: ${fullByWidth.height}`);
  console.log(`screenshot targetWidth only: ${fullByWidth.width}x${fullByWidth.height}`);

  const regionByHeight = await callHelper('zoom', {
    x: 0,
    y: 0,
    width: 400,
    height: 200,
    targetHeight: 100,
    showVirtualCursor: false,
  });
  assert(regionByHeight.height === 100, `Expected height 100, got ${regionByHeight.height}`);
  assert(regionByHeight.width === 200, `Expected proportional width 200, got ${regionByHeight.width}`);
  console.log(`screenshot_region targetHeight only: ${regionByHeight.width}x${regionByHeight.height}`);

  console.log('--- SCREENSHOT RESIZE OPTION TEST COMPLETED ---');
}

main().catch((err) => {
  console.error('Screenshot resize option test failed:', err);
  process.exit(1);
});
