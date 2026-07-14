import { callHelper } from './src/bridge.mjs';

async function main() {
  console.log('--- STARTING LIVE CURSOR OVERLAY TEST ---');

  await callHelper('virtual_cursor_overlay', { action: 'stop' });
  const before = await callHelper('cursor_position');
  const frontmostBefore = await callHelper('frontmost_app');
  await callHelper('move_mouse', { x: before.x + 40, y: before.y + 40 });

  const started = await callHelper('virtual_cursor_overlay', { action: 'start' });
  if (!started.running || !started.pid) {
    throw new Error(`Overlay did not start: ${JSON.stringify(started)}`);
  }
  if ((started.pids || []).length !== 1) {
    throw new Error(`Overlay should have exactly one process: ${JSON.stringify(started)}`);
  }

  const status = await callHelper('virtual_cursor_overlay', { action: 'status' });
  if (!status.running || status.pid !== started.pid) {
    throw new Error(`Overlay status is not running with same pid: ${JSON.stringify(status)}`);
  }
  if ((status.pids || []).length !== 1) {
    throw new Error(`Overlay status should report exactly one process: ${JSON.stringify(status)}`);
  }
  const frontmostAfterStart = await callHelper('frontmost_app');
  if (JSON.stringify(frontmostAfterStart) !== JSON.stringify(frontmostBefore)) {
    throw new Error(`Overlay changed frontmost application: before=${JSON.stringify(frontmostBefore)} after=${JSON.stringify(frontmostAfterStart)}`);
  }

  await callHelper('move_mouse', { x: before.x + 90, y: before.y + 90 });
  const afterMove = await callHelper('cursor_position');
  if (afterMove.x !== before.x + 90 || afterMove.y !== before.y + 90) {
    throw new Error(`Virtual cursor did not update while overlay was running: ${JSON.stringify(afterMove)}`);
  }

  const stopped = await callHelper('virtual_cursor_overlay', { action: 'stop' });
  if (stopped.running) {
    throw new Error(`Overlay did not stop: ${JSON.stringify(stopped)}`);
  }

  console.log('--- LIVE CURSOR OVERLAY TEST COMPLETED ---');
}

main().catch((err) => {
  console.error('Live cursor overlay test failed:', err);
  process.exit(1);
});
