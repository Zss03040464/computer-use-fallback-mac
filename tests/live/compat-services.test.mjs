import assert from 'node:assert/strict';
import test from 'node:test';

import { callCompat, closeRuntime } from '../../src/bridge.mjs';
import {
  assertFocusIsolation,
  assertPhysicalPointerIsolation,
  startInputActivityMonitor,
} from '../fixtures/input-activity.mjs';
import { inspectMacState } from '../fixtures/macos-state-probe.mjs';


test('read-only compatibility services preserve focus and the physical pointer', { timeout: 60_000 }, async (t) => {
  let inputMonitor;
  t.after(async () => {
    let cleanupError;
    try {
      if (inputMonitor) await inputMonitor.stop();
    } catch (error) {
      cleanupError = error;
    }
    await closeRuntime();
    if (cleanupError) throw cleanupError;
  });

  inputMonitor = await startInputActivityMonitor();
  const frontmostBefore = await inspectMacState('frontmost_app');
  const pointerBefore = await inspectMacState('physical_cursor_position');
  await inputMonitor.reset();

  const permissions = await callCompat('check_permissions', {});
  assert.equal(typeof permissions.accessibility, 'boolean');
  assert.equal(typeof permissions.screenRecording, 'boolean');

  const screenshot = await callCompat('screenshot', { targetWidth: 320 });
  assert.equal(screenshot.width, 320);
  assert.ok(screenshot.height > 0);
  assert.ok(screenshot.base64.length > 100);
  assert.equal(screenshot.mimeType, 'image/jpeg');

  const region = await callCompat('screenshot_region', {
    x: 0,
    y: 0,
    width: Math.min(200, screenshot.displayWidth),
    height: Math.min(100, screenshot.displayHeight),
    targetWidth: 160,
  });
  assert.equal(region.width, 160);
  assert.ok(region.height > 0);

  const mapped = await callCompat('map_coordinates', { x: 100, y: 100, to: 'physical' });
  assert.equal(mapped.space, 'physical');
  assert.equal(mapped.displayId, screenshot.displayId);

  const clipboard = await callCompat('read_clipboard', {});
  assert.equal(typeof clipboard, 'string');

  const captcha = await callCompat('detect_captcha', {});
  assert.equal(typeof captcha.detected, 'boolean');
  assert.equal(Array.isArray(captcha.matches), true);
  assert.equal(Object.hasOwn(captcha, 'text'), false);

  const frontmostAfter = await inspectMacState('frontmost_app');
  const pointerAfter = await inspectMacState('physical_cursor_position');
  const activity = await inputMonitor.stop();
  assertFocusIsolation(frontmostBefore, frontmostAfter, activity, []);
  assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity);
});
