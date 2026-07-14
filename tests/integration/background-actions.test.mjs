import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
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
const imageDifference = path.join(root, 'tests', 'fixtures', 'image_difference.py');


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


function launchHarness(role, directory) {
  const state = path.join(directory, `${role}-state.json`);
  const ready = path.join(directory, `${role}-ready.json`);
  const child = spawn(python, [
    harness,
    '--role', role,
    '--state', state,
    '--ready', ready,
    '--origin', '520,420',
  ], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  return { child, state, ready, stderr: () => stderr };
}


async function stopChild(handle) {
  if (handle.child.exitCode !== null) return;
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


test('covered target receives semantic actions without pointer focus or blocker crosstalk', { timeout: 30_000 }, async (t) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'cu-background-'));
  const worker = new RuntimeWorker({ sessionId: 'background-actions' });
  let targetHarness;
  let blockerHarness;
  let inputMonitor;
  t.after(async () => {
    let cleanupError;
    try {
      if (inputMonitor) await inputMonitor.stop();
    } catch (error) {
      cleanupError = error;
    }
    await worker.close();
    if (blockerHarness) await stopChild(blockerHarness);
    if (targetHarness) await stopChild(targetHarness);
    await rm(directory, { recursive: true, force: true });
    if (cleanupError) throw cleanupError;
  });

  inputMonitor = await startInputActivityMonitor();
  const frontmostBefore = await callHelper('frontmost_app');
  const pointerBefore = await callHelper('physical_cursor_position');
  await inputMonitor.reset();
  targetHarness = launchHarness('target', directory);
  const targetReady = await waitForJson(targetHarness.ready);
  assert.equal(targetHarness.child.exitCode, null, targetHarness.stderr());
  // AppKit animates the first order-front operation; capture only after the
  // window has reached its final bounds so before/after occlusion is comparable.
  await sleep(250);
  const app = `pid:${targetReady.pid}`;
  const uncovered = await worker.call('get_app_state', { app, windowId: targetReady.windowId });
  const uncoveredPath = path.join(directory, 'uncovered.png');
  await writeFile(uncoveredPath, Buffer.from(uncovered.screenshot.base64, 'base64'));

  blockerHarness = launchHarness('blocker', directory);
  const blockerReady = await waitForJson(blockerHarness.ready);
  assert.equal(blockerHarness.child.exitCode, null, blockerHarness.stderr());
  await sleep(150);

  const covered = await worker.call('get_app_state', { app, windowId: targetReady.windowId });
  assert.equal(covered.text.includes('fixture-secret-must-not-leak'), false);
  const coveredPath = path.join(directory, 'covered.png');
  await writeFile(coveredPath, Buffer.from(covered.screenshot.base64, 'base64'));
  const visual = JSON.parse(execFileSync(python, [imageDifference, uncoveredPath, coveredPath], { encoding: 'utf8' }));
  assert.ok(visual.difference < 0.03, `covering window leaked into app capture: ${visual.difference}`);

  const button = element(covered, 'target-button');
  const text = element(covered, 'target-text');
  const slider = element(covered, 'target-slider');
  const scroll = element(covered, 'target-scroll');

  await worker.call('click', { app, windowId: targetReady.windowId, element_index: button.index });
  await waitForJson(targetHarness.state, (value) => value.clickCount === 1);
  const afterIndexedClick = await worker.call('get_app_state', { app, windowId: targetReady.windowId });
  const expectedCursorPoint = [
    Math.round((button.bounds.x + button.bounds.width / 2) * afterIndexedClick.screenshot.scaleX),
    Math.round((button.bounds.y + button.bounds.height / 2) * afterIndexedClick.screenshot.scaleY),
  ];
  assert.equal(afterIndexedClick.cursorFeedback.drawn, true);
  assert.deepEqual(afterIndexedClick.cursorFeedback.imagePoint, expectedCursorPoint);
  const afterIndexedClickPath = path.join(directory, 'after-indexed-click.png');
  await writeFile(afterIndexedClickPath, Buffer.from(afterIndexedClick.screenshot.base64, 'base64'));
  const cursorVisual = JSON.parse(execFileSync(
    python,
    [imageDifference, coveredPath, afterIndexedClickPath],
    { encoding: 'utf8' },
  ));
  assert.ok(cursorVisual.difference > 0, 'post-click app state did not render cursor feedback');

  const centerX = button.bounds.x + button.bounds.width / 2;
  const centerY = button.bounds.y + button.bounds.height / 2;
  await worker.call('click', { app, windowId: targetReady.windowId, x: centerX, y: centerY });
  await waitForJson(targetHarness.state, (value) => value.clickCount === 2);

  await worker.call('mouse_down', {
    app,
    windowId: targetReady.windowId,
    element_index: button.index,
    x: centerX,
    y: centerY,
    button: 'left',
  });
  await worker.call('mouse_up', {
    app,
    windowId: targetReady.windowId,
    element_index: button.index,
    x: centerX,
    y: centerY,
    button: 'left',
  });
  await waitForJson(targetHarness.state, (value) => value.clickCount === 3);

  await worker.call('set_value', { app, windowId: targetReady.windowId, element_index: text.index, value: 'background text' });
  await waitForJson(targetHarness.state, (value) => value.textValue === 'background text');
  const refreshed = await worker.call('get_app_state', { app, windowId: targetReady.windowId });
  const refreshedText = element(refreshed, 'target-text');
  await worker.call('select_text', {
    app,
    windowId: targetReady.windowId,
    element_index: refreshedText.index,
    text: 'background',
    selection_type: 'text',
  });
  await worker.call('type_text', {
    app,
    windowId: targetReady.windowId,
    element_index: refreshedText.index,
    text: 'verified',
  });
  await waitForJson(targetHarness.state, (value) => value.textValue === 'verified text');
  await worker.call('press_key', { app, windowId: targetReady.windowId, element_index: refreshedText.index, key: 'Return' });
  await waitForJson(targetHarness.state, (value) => value.confirmCount === 1);

  const sliderY = slider.bounds.y + slider.bounds.height / 2;
  await worker.call('drag', {
    app,
    windowId: targetReady.windowId,
    element_index: slider.index,
    from_x: slider.bounds.x,
    from_y: sliderY,
    to_x: slider.bounds.x + slider.bounds.width * 0.75,
    to_y: sliderY,
  });
  await waitForJson(targetHarness.state, (value) => value.sliderValue >= 70 && value.sliderValue <= 80);

  await worker.call('scroll', {
    app,
    windowId: targetReady.windowId,
    element_index: scroll.index,
    direction: 'down',
    pages: 1,
  });
  await waitForJson(targetHarness.state, (value) => value.scrollY > 0);

  const blockerState = await waitForJson(blockerHarness.state);
  const frontmostAfter = await callHelper('frontmost_app');
  const pointerAfter = await callHelper('physical_cursor_position');
  const activity = await inputMonitor.stop();
  assert.equal(blockerState.blockerClickCount, 0);
  assertFocusIsolation(
    frontmostBefore,
    frontmostAfter,
    activity,
    [targetReady.pid, blockerReady.pid],
  );
  assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity);
});
