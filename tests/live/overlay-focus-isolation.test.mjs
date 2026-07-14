import test from 'node:test';
import assert from 'node:assert/strict';

import { inspectMacState } from '../fixtures/macos-state-probe.mjs';
import { RuntimeWorker } from '../../src/runtime-worker.mjs';
import {
  assertFocusIsolation,
  assertPhysicalPointerIsolation,
  startInputActivityMonitor,
} from '../fixtures/input-activity.mjs';


test('session overlay never becomes the frontmost application', { timeout: 15_000 }, async (t) => {
  const worker = new RuntimeWorker({ sessionId: 'overlay-focus-isolation' });
  let inputMonitor;
  t.after(async () => {
    let cleanupError;
    try {
      if (inputMonitor) await inputMonitor.stop();
    } catch (error) {
      cleanupError = error;
    }
    try { await worker.call('virtual_cursor_overlay', { action: 'stop' }); } catch {}
    await worker.close();
    if (cleanupError) throw cleanupError;
  });

  inputMonitor = await startInputActivityMonitor();
  const frontmostBefore = await inspectMacState('frontmost_app');
  assert.ok(frontmostBefore.pid > 1, `frontmost app must expose a concrete pid: ${JSON.stringify(frontmostBefore)}`);
  const pointerBefore = await inspectMacState('physical_cursor_position');
  await inputMonitor.reset();
  const cursor = await worker.call('cursor_position', {});

  const moved = await worker.call('set_cursor', {
    x: cursor.x + 25,
    y: cursor.y + 25,
  });
  assert.equal(moved.cursorFeedback.reason, 'target_unbound');
  const started = await worker.call('virtual_cursor_overlay', { action: 'start' });
  assert.equal(started.running, true);
  await new Promise((resolve) => setTimeout(resolve, 150));

  const frontmostAfter = await inspectMacState('frontmost_app');
  const pointerAfter = await inspectMacState('physical_cursor_position');
  const activity = await inputMonitor.stop();
  assertFocusIsolation(frontmostBefore, frontmostAfter, activity, [started.pid]);
  assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity);
});
