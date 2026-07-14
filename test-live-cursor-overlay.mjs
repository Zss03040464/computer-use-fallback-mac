import { RuntimeWorker } from './src/runtime-worker.mjs';
import { inspectMacState } from './tests/fixtures/macos-state-probe.mjs';

async function main() {
  console.log('--- STARTING LIVE CURSOR OVERLAY TEST ---');
  const worker = new RuntimeWorker({ sessionId: `legacy-live-${process.pid}` });
  try {
    await worker.call('virtual_cursor_overlay', { action: 'stop' });
    const before = await worker.call('cursor_position');
    const frontmostBefore = await inspectMacState('frontmost_app');
    await worker.call('set_cursor', { x: before.x + 40, y: before.y + 40, button: null });

    const started = await worker.call('virtual_cursor_overlay', { action: 'start' });
    if (!started.running || !started.pid) {
      throw new Error(`Overlay did not start: ${JSON.stringify(started)}`);
    }
    const status = await worker.call('virtual_cursor_overlay', { action: 'status' });
    if (!status.running || status.pid !== started.pid) {
      throw new Error(`Overlay status is not running with same pid: ${JSON.stringify(status)}`);
    }
    const frontmostAfterStart = await inspectMacState('frontmost_app');
    if (JSON.stringify(frontmostAfterStart) !== JSON.stringify(frontmostBefore)) {
      throw new Error(`Overlay changed frontmost application: before=${JSON.stringify(frontmostBefore)} after=${JSON.stringify(frontmostAfterStart)}`);
    }

    await worker.call('set_cursor', { x: before.x + 90, y: before.y + 90, button: null });
    const afterMove = await worker.call('cursor_position');
    if (afterMove.x !== before.x + 90 || afterMove.y !== before.y + 90) {
      throw new Error(`Virtual cursor did not update while overlay was running: ${JSON.stringify(afterMove)}`);
    }

    const stopped = await worker.call('virtual_cursor_overlay', { action: 'stop' });
    if (stopped.running) {
      throw new Error(`Overlay did not stop: ${JSON.stringify(stopped)}`);
    }
    console.log('--- LIVE CURSOR OVERLAY TEST COMPLETED ---');
  } finally {
    try { await worker.call('virtual_cursor_overlay', { action: 'stop' }); } catch {}
    await worker.close();
  }
}

main().catch((err) => {
  console.error('Live cursor overlay test failed:', err);
  process.exit(1);
});
