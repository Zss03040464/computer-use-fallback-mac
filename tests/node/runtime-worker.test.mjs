import test from 'node:test';
import assert from 'node:assert/strict';

import { RuntimeWorker } from '../../src/runtime-worker.mjs';


test('persistent worker reuses one pid and session across calls', async (t) => {
  const worker = new RuntimeWorker({ sessionId: 'node-worker-test' });
  t.after(async () => worker.close());

  const first = await worker.call('runtime_info', {});
  const second = await worker.call('runtime_info', {});

  assert.equal(first.pid, second.pid);
  assert.equal(first.sessionId, 'node-worker-test');
  assert.equal(second.sessionId, 'node-worker-test');
  assert.equal(worker.pid, first.pid);
});

test('worker returns a structured error for unknown commands', async (t) => {
  const worker = new RuntimeWorker({ sessionId: 'node-worker-errors' });
  t.after(async () => worker.close());

  await assert.rejects(
    worker.call('not_a_command', {}),
    (error) => error.code === 'unknown_command' && error.details.command === 'not_a_command',
  );
});

test('close reaches process termination even when shutdown never responds', { timeout: 5000 }, async () => {
  const worker = new RuntimeWorker({ sessionId: 'node-worker-stuck-shutdown' });
  await worker.call('runtime_info', {});
  worker.call = async () => new Promise(() => {});
  const started = Date.now();
  await worker.close();
  assert.ok(Date.now() - started < 2500);
  assert.equal(worker.exited, true);
});

test('calls fail with a structured timeout instead of remaining pending forever', { timeout: 3000 }, async (t) => {
  const worker = new RuntimeWorker({
    moduleName: 'tests.fixtures.stuck_worker',
    moduleArgs: [],
    callTimeoutMs: 25,
  });
  t.after(async () => worker.close());

  await assert.rejects(
    worker.call('never_returns', {}),
    (error) => error.code === 'runtime_timeout'
      && error.details.command === 'never_returns'
      && error.details.timeoutMs === 25,
  );
});

test('protocol errors do not echo malformed worker output', async (t) => {
  const worker = new RuntimeWorker({
    moduleName: 'tests.fixtures.invalid_json_worker',
    moduleArgs: [],
  });
  t.after(async () => worker.close());

  await assert.rejects(
    worker.call('invalid_output', {}),
    (error) => error.code === 'runtime_protocol_error'
      && JSON.stringify(error.details) === '{}'
      && !error.message.includes('SENTINEL-protocol-private-value'),
  );
});
