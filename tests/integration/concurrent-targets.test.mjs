import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import { callHelper } from '../../src/bridge.mjs';
import { RuntimeWorker } from '../../src/runtime-worker.mjs';
import {
  assertFocusIsolation,
  assertPhysicalPointerIsolation,
  startInputActivityMonitor,
} from '../fixtures/input-activity.mjs';


const root = path.resolve(import.meta.dirname, '../..');
const python = path.join(root, '.venv', 'bin', 'python3');
const harness = path.join(root, 'tests', 'fixtures', 'background_input_harness.py');


function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}


async function waitForJson(file, predicate = () => true, timeoutMs = 7000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = JSON.parse(await readFile(file, 'utf8'));
      if (predicate(value)) return value;
    } catch (error) {
      lastError = error;
    }
    await sleep(30);
  }
  throw new Error(`Timed out waiting for ${file}: ${lastError?.message || 'predicate not met'}`);
}


async function waitForStableFrontmost(stableMs = 750, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  let previousKey;
  let stableSince = 0;
  let current;
  while (Date.now() < deadline) {
    current = await callHelper('frontmost_app');
    const key = JSON.stringify(current);
    if (key === previousKey) {
      if (Date.now() - stableSince >= stableMs) return current;
    } else {
      previousKey = key;
      stableSince = Date.now();
    }
    await sleep(75);
  }
  throw new Error(`Frontmost application did not stabilize: ${JSON.stringify(current)}`);
}


async function launchHarness(role, directory, origin) {
  await mkdir(directory, { recursive: true });
  const state = path.join(directory, 'state.json');
  const ready = path.join(directory, 'ready.json');
  const child = spawn(python, [
    harness,
    '--role', role,
    '--state', state,
    '--ready', ready,
    '--origin', origin,
  ], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  const handle = { child, state, ready: null, stderr: () => stderr };
  try {
    handle.ready = await waitForJson(ready);
    assert.equal(child.exitCode, null, stderr);
    return handle;
  } catch (error) {
    await stopChild(handle);
    throw error;
  }
}


async function stopChild(handle) {
  if (!handle || handle.child.exitCode !== null) return;
  handle.child.kill('SIGTERM');
  await Promise.race([
    new Promise((resolve) => handle.child.once('exit', resolve)),
    sleep(1000),
  ]);
  if (handle.child.exitCode === null) {
    handle.child.kill('SIGKILL');
    await new Promise((resolve) => handle.child.once('exit', resolve));
  }
}


function element(state, identifier) {
  const record = state.elements.find((item) => item.identifier === identifier);
  assert.ok(record, `missing AX element ${identifier}`);
  return record;
}


test('two sessions control covered target processes concurrently without crossover', { timeout: 40_000 }, async (t) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'cu-concurrent-'));
  const workers = [
    new RuntimeWorker({ sessionId: 'concurrent-target-a' }),
    new RuntimeWorker({ sessionId: 'concurrent-target-b' }),
  ];
  const children = [];
  let inputMonitor;
  t.after(async () => {
    let cleanupError;
    try {
      if (inputMonitor) await inputMonitor.stop();
    } catch (error) {
      cleanupError = error;
    }
    await Promise.all(workers.map((worker) => worker.close()));
    await Promise.all(children.map(stopChild));
    await rm(directory, { recursive: true, force: true });
    if (cleanupError) throw cleanupError;
  });

  inputMonitor = await startInputActivityMonitor();
  const frontmostBefore = await waitForStableFrontmost();
  const pointerBefore = await callHelper('physical_cursor_position');
  await inputMonitor.reset();
  const targetA = await launchHarness('target', path.join(directory, 'target-a'), '140,330');
  children.push(targetA);
  const targetB = await launchHarness('target', path.join(directory, 'target-b'), '700,330');
  children.push(targetB);
  await sleep(250);

  const appA = `pid:${targetA.ready.pid}`;
  const appB = `pid:${targetB.ready.pid}`;
  const [stateA, stateB] = await Promise.all([
    workers[0].call('get_app_state', { app: appA, windowId: targetA.ready.windowId }),
    workers[1].call('get_app_state', { app: appB, windowId: targetB.ready.windowId }),
  ]);

  const blockerA = await launchHarness('blocker', path.join(directory, 'blocker-a'), '140,330');
  children.push(blockerA);
  const blockerB = await launchHarness('blocker', path.join(directory, 'blocker-b'), '700,330');
  children.push(blockerB);
  await sleep(150);

  const buttonA = element(stateA, 'target-button');
  const buttonB = element(stateB, 'target-button');
  const textA = element(stateA, 'target-text');
  const textB = element(stateB, 'target-text');
  const sliderA = element(stateA, 'target-slider');
  const sliderB = element(stateB, 'target-slider');
  const scrollA = element(stateA, 'target-scroll');
  const scrollB = element(stateB, 'target-scroll');

  await Promise.all([
    workers[0].call('click', { app: appA, windowId: targetA.ready.windowId, element_index: buttonA.index }),
    workers[1].call('click', { app: appB, windowId: targetB.ready.windowId, element_index: buttonB.index }),
  ]);
  await Promise.all([
    waitForJson(targetA.state, (value) => value.clickCount === 1),
    waitForJson(targetB.state, (value) => value.clickCount === 1),
  ]);

  await Promise.all([
    workers[0].call('set_value', { app: appA, windowId: targetA.ready.windowId, element_index: textA.index, value: 'session A' }),
    workers[1].call('set_value', { app: appB, windowId: targetB.ready.windowId, element_index: textB.index, value: 'session B' }),
    workers[0].call('drag', {
      app: appA,
      windowId: targetA.ready.windowId,
      element_index: sliderA.index,
      from_x: sliderA.bounds.x,
      from_y: sliderA.bounds.y + sliderA.bounds.height / 2,
      to_x: sliderA.bounds.x + sliderA.bounds.width * 0.25,
      to_y: sliderA.bounds.y + sliderA.bounds.height / 2,
    }),
    workers[1].call('drag', {
      app: appB,
      windowId: targetB.ready.windowId,
      element_index: sliderB.index,
      from_x: sliderB.bounds.x,
      from_y: sliderB.bounds.y + sliderB.bounds.height / 2,
      to_x: sliderB.bounds.x + sliderB.bounds.width * 0.8,
      to_y: sliderB.bounds.y + sliderB.bounds.height / 2,
    }),
    workers[0].call('scroll', { app: appA, windowId: targetA.ready.windowId, element_index: scrollA.index, direction: 'down', pages: 1 }),
    workers[1].call('scroll', { app: appB, windowId: targetB.ready.windowId, element_index: scrollB.index, direction: 'down', pages: 1 }),
  ]);
  await Promise.all([
    workers[0].call('set_cursor', { x: 31, y: 41 }),
    workers[1].call('set_cursor', { x: 151, y: 161 }),
  ]);

  const [cursorStateA, cursorStateB] = await Promise.all([
    workers[0].call('get_app_state', { app: appA, windowId: targetA.ready.windowId }),
    workers[1].call('get_app_state', { app: appB, windowId: targetB.ready.windowId }),
  ]);
  assert.equal(cursorStateA.cursorFeedback.drawn, true);
  assert.equal(cursorStateB.cursorFeedback.drawn, true);
  assert.deepEqual(cursorStateA.cursorFeedback.imagePoint, [31, 41]);
  assert.deepEqual(cursorStateB.cursorFeedback.imagePoint, [151, 161]);
  assert.notDeepEqual(cursorStateA.cursorFeedback.imagePoint, cursorStateB.cursorFeedback.imagePoint);

  const [finalA, finalB, blockerStateA, blockerStateB, cursorA, cursorB] = await Promise.all([
    waitForJson(targetA.state, (value) => value.textValue === 'session A' && value.sliderValue >= 20 && value.sliderValue <= 30 && value.scrollY > 0),
    waitForJson(targetB.state, (value) => value.textValue === 'session B' && value.sliderValue >= 75 && value.sliderValue <= 85 && value.scrollY > 0),
    waitForJson(blockerA.state),
    waitForJson(blockerB.state),
    workers[0].call('cursor_position', {}),
    workers[1].call('cursor_position', {}),
  ]);

  assert.equal(finalA.textValue, 'session A');
  assert.equal(finalB.textValue, 'session B');
  assert.equal(blockerStateA.blockerClickCount, 0);
  assert.equal(blockerStateB.blockerClickCount, 0);
  assert.deepEqual(cursorA, { x: 31, y: 41, button: null });
  assert.deepEqual(cursorB, { x: 151, y: 161, button: null });
  const frontmostAfter = await callHelper('frontmost_app');
  const pointerAfter = await callHelper('physical_cursor_position');
  const activity = await inputMonitor.stop();
  assertFocusIsolation(
    frontmostBefore,
    frontmostAfter,
    activity,
    [targetA.ready.pid, targetB.ready.pid, blockerA.ready.pid, blockerB.ready.pid],
  );
  assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity);
});
