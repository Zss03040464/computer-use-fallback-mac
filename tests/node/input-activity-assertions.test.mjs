import test from 'node:test';
import assert from 'node:assert/strict';

import {
  assertFocusIsolation,
  assertPhysicalPointerIsolation,
  startInputActivityMonitor,
} from '../fixtures/input-activity.mjs';


function activity({
  hidMove = 0,
  nonHidMove = 0,
  hidFocus = 0,
  hidActivation = 0,
  transitions = [],
} = {}) {
  return {
    hidMouseMoves: hidMove,
    nonHidMouseMoves: nonHidMove,
    hidFocusEvents: hidFocus,
    hidActivationEvents: hidActivation,
    focusTransitions: transitions,
  };
}


test('pointer isolation stays exact when no HID movement occurred', () => {
  assert.doesNotThrow(() => assertPhysicalPointerIsolation(
    { x: 10, y: 20 },
    { x: 10, y: 20 },
    activity(),
  ));
  assert.throws(() => assertPhysicalPointerIsolation(
    { x: 10, y: 20 },
    { x: 11, y: 20 },
    activity(),
  ), /without HID movement/);
});


test('pointer isolation attributes concurrent hardware motion but rejects synthetic motion', () => {
  assert.doesNotThrow(() => assertPhysicalPointerIsolation(
    { x: 10, y: 20 },
    { x: 30, y: 40 },
    activity({ hidMove: 7 }),
  ));
  assert.throws(() => assertPhysicalPointerIsolation(
    { x: 10, y: 20 },
    { x: 30, y: 40 },
    activity({ hidMove: 7, nonHidMove: 1 }),
  ), /non-HID mouse movement/);
});


test('focus isolation rejects a protected temporary steal even when final focus is restored', () => {
  const before = { pid: 100, displayName: 'Codex' };
  const interruptedTyping = activity({
    hidFocus: 8,
    transitions: [
      { pid: 300, bundleId: 'com.microsoft.edgemac', hidAttributed: false },
      { pid: 100, bundleId: 'com.openai.codex', hidAttributed: false },
    ],
  });
  assert.throws(
    () => assertFocusIsolation(before, before, interruptedTyping, [300]),
    /protected application became frontmost/,
  );
});


test('focus isolation rejects unattributed unrelated transitions', () => {
  const before = { pid: 100, displayName: 'Codex' };
  const after = { pid: 200, displayName: 'Obsidian' };
  assert.throws(() => assertFocusIsolation(
    before,
    after,
    activity({
      hidFocus: 8,
      transitions: [{ pid: 200, bundleId: 'md.obsidian', hidAttributed: false }],
    }),
    [300],
  ), /unattributed focus transition/);
});


test('focus isolation allows a physically attributed unrelated app switch', () => {
  const before = { pid: 100, displayName: 'Codex' };
  const after = { pid: 200, displayName: 'Obsidian' };
  assert.doesNotThrow(() => assertFocusIsolation(
    before,
    after,
    activity({
      hidFocus: 1,
      hidActivation: 1,
      transitions: [{ pid: 200, bundleId: 'md.obsidian', hidAttributed: true }],
    }),
    [300],
  ));
  assert.throws(() => assertFocusIsolation(
    before,
    { pid: 300, displayName: 'Target' },
    activity({
      hidFocus: 1,
      hidActivation: 1,
      transitions: [{ pid: 300, bundleId: 'com.apple.calculator', hidAttributed: true }],
    }),
    [300],
  ), /protected application became frontmost/);
});


test('input activity monitor starts and returns an attributed event summary', async () => {
  const monitor = await startInputActivityMonitor();
  await monitor.reset();
  const summary = await monitor.stop();
  assert.equal(Number.isInteger(summary.hidMouseMoves), true);
  assert.equal(Number.isInteger(summary.nonHidMouseMoves), true);
  assert.equal(Number.isInteger(summary.hidFocusEvents), true);
  assert.equal(Number.isInteger(summary.hidActivationEvents), true);
  assert.equal(Array.isArray(summary.focusTransitions), true);
});
