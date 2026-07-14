import test from 'node:test';
import assert from 'node:assert/strict';

import { RuntimeWorker } from '../../src/runtime-worker.mjs';


test('two workers isolate cursor state and allow different targets concurrently', async (t) => {
  const first = new RuntimeWorker({ sessionId: 'multi-a' });
  const second = new RuntimeWorker({ sessionId: 'multi-b' });
  t.after(async () => Promise.all([first.close(), second.close()]));

  await first.call('set_cursor', { x: 11, y: 22, button: null });
  await second.call('set_cursor', { x: 33, y: 44, button: 'left' });
  assert.deepEqual(await first.call('cursor_position', {}), { x: 11, y: 22, button: null });
  assert.deepEqual(await second.call('cursor_position', {}), { x: 33, y: 44, button: 'left' });

  const started = Date.now();
  await Promise.all([
    first.call('lock_probe', { bundleId: 'com.example.a', windowId: 1, holdMs: 200 }),
    second.call('lock_probe', { bundleId: 'com.example.b', windowId: 2, holdMs: 200 }),
  ]);
  assert.ok(Date.now() - started < 350, 'different targets should not serialize');
});


test('cross-process lock returns target_busy instead of redirecting', async (t) => {
  const first = new RuntimeWorker({ sessionId: 'lock-a' });
  const second = new RuntimeWorker({ sessionId: 'lock-b' });
  t.after(async () => Promise.all([first.close(), second.close()]));

  await Promise.all([
    first.call('runtime_info', {}),
    second.call('runtime_info', {}),
  ]);

  const holding = first.call('lock_probe', {
    bundleId: 'com.example.shared', windowId: 9, holdMs: 300, timeoutMs: 1000,
  });
  await new Promise((resolve) => setTimeout(resolve, 80));
  await assert.rejects(
    second.call('lock_probe', {
      bundleId: 'com.example.shared', windowId: 9, holdMs: 0, timeoutMs: 50,
    }),
    (error) => error.code === 'target_busy',
  );
  await holding;
});
