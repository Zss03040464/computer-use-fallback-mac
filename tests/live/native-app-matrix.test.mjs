import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { realpathSync } from 'node:fs';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import os from 'node:os';
import path from 'node:path';

import { inspectMacState } from '../fixtures/macos-state-probe.mjs';
import { RuntimeWorker } from '../../src/runtime-worker.mjs';
import {
  assertFocusIsolation,
  assertPhysicalPointerIsolation,
  startInputActivityMonitor,
} from '../fixtures/input-activity.mjs';
import {
  commandMatchesOwnership,
  parseProcessRows,
  selectOwnedProcessIds,
} from '../fixtures/process-ownership.mjs';


const root = path.resolve(import.meta.dirname, '../..');
const python = path.join(root, '.venv', 'bin', 'python3');
const harness = path.join(root, 'tests', 'fixtures', 'background_input_harness.py');


function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}


async function waitForJson(file, timeoutMs = 7000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      return JSON.parse(await readFile(file, 'utf8'));
    } catch (error) {
      lastError = error;
      await sleep(30);
    }
  }
  throw new Error(`Timed out waiting for ${file}: ${lastError?.message || 'not created'}`);
}


async function launchBlocker(directory, target) {
  const state = path.join(directory, 'blocker-state.json');
  const ready = path.join(directory, 'blocker-ready.json');
  const child = spawn(python, [
    harness,
    '--role', 'blocker',
    '--state', state,
    '--ready', ready,
    '--quartz-origin', `${target.bounds.x},${target.bounds.y}`,
  ], {
    cwd: root,
    env: { ...process.env, CU_BLOCKER_NORMAL: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  const handle = { child, state, ready: null, stderr: () => stderr };
  try {
    handle.ready = await waitForJson(ready);
    assert.equal(child.exitCode, null, stderr);
    await sleep(150);
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


function findElement(state, predicate, label) {
  const record = state.elements.find(predicate);
  assert.ok(record, `missing ${label}; state=${state.text}`);
  return record;
}


function edgeTabs(state) {
  return state.elements
    .filter((item) => item.role === 'AXRadioButton' && item.bounds)
    .sort((left, right) => left.bounds.x - right.bounds.x);
}


function rightmostTabCloseButton(state) {
  const tabs = edgeTabs(state);
  const tab = tabs.at(-1);
  assert.ok(tab, 'Edge state must expose at least one tab');
  const closeButtons = state.elements.filter((item) => (
    item.role === 'AXButton'
    && item.bounds
    && /^(Close tab|Close Tab|关闭标签页|关闭标签)$/.test(item.title || item.description || '')
    && item.bounds.x >= tab.bounds.x
    && item.bounds.x + item.bounds.width <= tab.bounds.x + tab.bounds.width
    && item.bounds.y >= tab.bounds.y
    && item.bounds.y + item.bounds.height <= tab.bounds.y + tab.bounds.height
  ));
  assert.equal(closeButtons.length, 1, 'Edge rightmost tab must expose one exact close button');
  return closeButtons[0];
}


async function waitForWindow(worker, predicate, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  let lastWindows = [];
  while (Date.now() < deadline) {
    const windows = await worker.call('list_windows', {});
    lastWindows = windows;
    const window = windows.find(predicate);
    if (window) return window;
    await sleep(80);
  }
  throw new Error(`Timed out waiting for native app window; last=${JSON.stringify(lastWindows)}`);
}


function processMatchesExecutable(pid, executable, requiredToken = null) {
  try {
    const command = execFileSync('ps', ['-p', String(pid), '-o', 'command='], { encoding: 'utf8' }).trim();
    return commandMatchesOwnership(command, executable, requiredToken);
  } catch {
    return false;
  }
}


function pidsForExecutable(executable, requiredToken = null) {
  const output = execFileSync('ps', ['-axo', 'pid=,command='], { encoding: 'utf8' });
  return new Set(selectOwnedProcessIds(parseProcessRows(output), executable, new Set(), requiredToken));
}


async function waitForOwnedPid(executable, preexisting, timeoutMs = 10_000, requiredToken = null) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const rows = parseProcessRows(execFileSync('ps', ['-axo', 'pid=,command='], { encoding: 'utf8' }));
    const created = selectOwnedProcessIds(rows, executable, preexisting, requiredToken);
    if (created.length === 1) return created[0];
    if (created.length > 1) throw new Error(`More than one new process appeared for ${executable}`);
    await sleep(50);
  }
  throw new Error(`Timed out waiting for an isolated process for ${executable}`);
}


async function launchOwnedApp(
  appName,
  openArguments,
  executable,
  preexisting,
  timeoutMs = 10_000,
  requiredToken = null,
) {
  execFileSync('open', ['-g', '-n', '-a', appName, ...openArguments]);
  try {
    return await waitForOwnedPid(executable, preexisting, timeoutMs, requiredToken);
  } catch (error) {
    await sleep(300);
    const rows = parseProcessRows(execFileSync('ps', ['-axo', 'pid=,command='], { encoding: 'utf8' }));
    const created = selectOwnedProcessIds(rows, executable, preexisting, requiredToken);
    await Promise.all(created.map((pid) => stopOwnedProcess(pid, executable, requiredToken)));
    throw error;
  }
}


async function stopOwnedProcess(pid, executable, requiredToken = null) {
  if (!pid || !processMatchesExecutable(pid, executable, requiredToken)) return;
  try { process.kill(pid, 'SIGTERM'); } catch { return; }
  const deadline = Date.now() + 1000;
  while (Date.now() < deadline && processMatchesExecutable(pid, executable, requiredToken)) await sleep(30);
  if (processMatchesExecutable(pid, executable, requiredToken)) {
    try { process.kill(pid, 'SIGKILL'); } catch {}
    const killDeadline = Date.now() + 1000;
    while (Date.now() < killDeadline && processMatchesExecutable(pid, executable, requiredToken)) await sleep(30);
  }
}


async function waitForAppState(worker, target, predicate, timeoutMs = 12_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  let lastState;
  while (Date.now() < deadline) {
    try {
      const state = await worker.call('get_app_state', { ...target, launch: false });
      lastState = state;
      if (predicate(state)) return state;
    } catch (error) {
      lastError = error;
    }
    await sleep(100);
  }
  throw new Error(`Timed out waiting for app state: ${lastError?.message || 'predicate not met'}; last=${lastState?.text || 'none'}`);
}


async function startBrowserFixture() {
  const html = `<!doctype html>
  <html lang="en"><head><meta charset="utf-8"><title>CU Browser Background Harness</title>
  <style>body{font:20px system-ui;margin:40px}button,input{font:inherit;margin:12px;padding:12px}.spacer{height:900px}</style></head>
  <body><button id="cu-browser-button" aria-label="Background Click">Background Click</button>
  <input id="cu-browser-input" aria-label="Background Input" value="initial">
  <p id="cu-browser-status" role="status">ready</p><div class="spacer">scroll target</div>
  <script>document.getElementById('cu-browser-button').addEventListener('click',()=>{document.getElementById('cu-browser-status').textContent='clicked'});</script>
  </body></html>`;
  const server = createServer((request, response) => {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    response.end(html);
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  return {
    url: `http://127.0.0.1:${address.port}/`,
    close: () => new Promise((resolve) => {
      server.close(resolve);
      server.closeAllConnections?.();
    }),
  };
}


test('production auto-launch error path keeps Chess in the background', { timeout: 30_000 }, async (t) => {
  const chessExecutable = '/System/Applications/Chess.app/Contents/MacOS/Chess';
  const preexisting = pidsForExecutable(chessExecutable);
  if (preexisting.size > 0) {
    t.skip('Chess is already running; the test will not claim or terminate a user process');
    return;
  }

  const worker = new RuntimeWorker({ sessionId: 'native-auto-launch' });
  let chessPid;
  let inputMonitor;
  t.after(async () => {
    let cleanupError;
    try {
      if (inputMonitor) await inputMonitor.stop();
    } catch (error) {
      cleanupError = error;
    }
    await worker.close();
    await stopOwnedProcess(chessPid, chessExecutable);
    if (cleanupError) throw cleanupError;
  });

  inputMonitor = await startInputActivityMonitor();
  const frontmostBefore = await inspectMacState('frontmost_app');
  const pointerBefore = await inspectMacState('physical_cursor_position');
  await inputMonitor.reset();
  const ownedPid = waitForOwnedPid(chessExecutable, preexisting, 10_000);
  let state;
  let launchError;
  try {
    state = await worker.call('get_app_state', { app: 'com.apple.Chess' });
    chessPid = await ownedPid;
  } catch (error) {
    chessPid = await ownedPid.catch(() => null);
    launchError = error;
  }

  assert.equal(state, undefined);
  assert.equal(launchError?.code, 'window_not_found');
  assert.ok(Number.isInteger(chessPid) && chessPid > 1, 'Chess must have launched as one exact owned process');
  const frontmostAfter = await inspectMacState('frontmost_app');
  const pointerAfter = await inspectMacState('physical_cursor_position');
  const activity = await inputMonitor.stop();
  assertFocusIsolation(frontmostBefore, frontmostAfter, activity, [chessPid]);
  assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity);
});


test('Calculator accepts a covered background click without pointer or focus movement', { timeout: 30_000 }, async (t) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'cu-native-calculator-'));
  const worker = new RuntimeWorker({ sessionId: 'native-calculator' });
  let blocker;
  const calculatorExecutable = '/System/Applications/Calculator.app/Contents/MacOS/Calculator';
  const preexisting = pidsForExecutable(calculatorExecutable);
  let calculatorPid;
  let inputMonitor;
  t.after(async () => {
    let cleanupError;
    try {
      if (inputMonitor) await inputMonitor.stop();
    } catch (error) {
      cleanupError = error;
    }
    await worker.close();
    await stopChild(blocker);
    await stopOwnedProcess(calculatorPid, calculatorExecutable);
    await rm(directory, { recursive: true, force: true });
    if (cleanupError) throw cleanupError;
  });

  inputMonitor = await startInputActivityMonitor();
  const frontmostBefore = await inspectMacState('frontmost_app');
  assert.ok(frontmostBefore.pid > 1, `frontmost app must expose a concrete pid: ${JSON.stringify(frontmostBefore)}`);
  const pointerBefore = await inspectMacState('physical_cursor_position');
  await inputMonitor.reset();
  calculatorPid = await launchOwnedApp('Calculator', [], calculatorExecutable, preexisting);
  const calculatorWindow = await waitForWindow(
    worker,
    (item) => item.pid === calculatorPid,
  );
  const app = `pid:${calculatorPid}`;
  let state = await worker.call('get_app_state', { app, windowId: calculatorWindow.windowId, launch: false });
  const clear = state.elements.find((item) => item.role === 'AXButton' && /^(AC|C|全部清除|清除)$/.test(item.title || item.description || ''));
  if (clear) {
    await worker.call('click', { app, windowId: state.target.windowId, element_index: clear.index });
    state = await worker.call('get_app_state', { app, windowId: state.target.windowId });
  }
  const seven = findElement(
    state,
    (item) => item.role === 'AXButton' && /^(7|Seven|七)$/.test(item.title || item.description || ''),
    'Calculator seven button',
  );
  blocker = await launchBlocker(directory, state.target);
  const blockerWindow = (await inspectMacState('list_windows')).find((window) => window.pid === blocker.ready.pid);
  assert.ok(blockerWindow, 'blocker window did not register with CoreGraphics');
  const sevenCenter = {
    x: state.target.bounds.x + seven.bounds.x + seven.bounds.width / 2,
    y: state.target.bounds.y + seven.bounds.y + seven.bounds.height / 2,
  };
  assert.ok(
    blockerWindow.bounds.x <= sevenCenter.x
      && sevenCenter.x < blockerWindow.bounds.x + blockerWindow.bounds.width
      && blockerWindow.bounds.y <= sevenCenter.y
      && sevenCenter.y < blockerWindow.bounds.y + blockerWindow.bounds.height,
    `blocker ${JSON.stringify(blockerWindow.bounds)} does not cover Calculator button at ${JSON.stringify(sevenCenter)}`,
  );

  const beforeText = state.text;
  await worker.call('click', {
    app,
    windowId: state.target.windowId,
    element_index: seven.index,
  });
  const after = await worker.call('get_app_state', {
    app,
    windowId: state.target.windowId,
  });

  assert.notEqual(after.text, beforeText);
  const displayValue = after.text.match(/AXStaticText[^\n]*Value: ([^\n]*)/)?.[1] || '';
  assert.equal(displayValue.match(/\d/g)?.at(-1), '7');
  assert.equal(after.cursorFeedback.drawn, true);
  assert.deepEqual(after.cursorFeedback.imagePoint, [
    Math.round((seven.bounds.x + seven.bounds.width / 2) * after.screenshot.scaleX),
    Math.round((seven.bounds.y + seven.bounds.height / 2) * after.screenshot.scaleY),
  ]);
  assert.equal((await waitForJson(blocker.state)).blockerClickCount, 0);
  const frontmostAfter = await inspectMacState('frontmost_app');
  const pointerAfter = await inspectMacState('physical_cursor_position');
  const activity = await inputMonitor.stop();
  assertFocusIsolation(frontmostBefore, frontmostAfter, activity, [calculatorPid, blocker.ready.pid]);
  assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity);
});


test('TextEdit accepts a covered background text value without pointer or focus movement', { timeout: 35_000 }, async (t) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'cu-native-textedit-'));
  const worker = new RuntimeWorker({ sessionId: 'native-textedit' });
  const filename = `cu-textedit-${Date.now()}.txt`;
  const documentPath = path.join(directory, filename);
  let blocker;
  const textEditExecutable = '/System/Applications/TextEdit.app/Contents/MacOS/TextEdit';
  const preexisting = pidsForExecutable(textEditExecutable);
  let textEditPid;
  let inputMonitor;
  t.after(async () => {
    let cleanupError;
    try {
      if (inputMonitor) await inputMonitor.stop();
    } catch (error) {
      cleanupError = error;
    }
    await worker.close();
    await stopChild(blocker);
    await stopOwnedProcess(textEditPid, textEditExecutable);
    await rm(directory, { recursive: true, force: true });
    if (cleanupError) throw cleanupError;
  });

  inputMonitor = await startInputActivityMonitor();
  const frontmostBefore = await inspectMacState('frontmost_app');
  const pointerBefore = await inspectMacState('physical_cursor_position');
  await inputMonitor.reset();
  await writeFile(documentPath, 'initial native text', 'utf8');
  textEditPid = await launchOwnedApp('TextEdit', [documentPath], textEditExecutable, preexisting);
  const window = await waitForWindow(
    worker,
    (item) => item.pid === textEditPid
      && item.title.includes(filename)
      && processMatchesExecutable(item.pid, textEditExecutable),
  );
  const app = `pid:${window.pid}`;
  const state = await worker.call('get_app_state', { app, windowId: window.windowId, launch: false });
  const editor = findElement(
    state,
    (item) => ['AXTextArea', 'AXTextField'].includes(item.role) && item.settable,
    'TextEdit editable text area',
  );
  blocker = await launchBlocker(directory, state.target);
  const editorCenter = {
    x: state.target.bounds.x + editor.bounds.x + Math.min(editor.bounds.width / 2, 100),
    y: state.target.bounds.y + editor.bounds.y + Math.min(editor.bounds.height / 2, 100),
  };
  const blockerWindow = (await inspectMacState('list_windows')).find((item) => item.pid === blocker.ready.pid);
  assert.ok(blockerWindow, 'TextEdit blocker window did not register');
  assert.ok(
    blockerWindow.bounds.x <= editorCenter.x
      && editorCenter.x < blockerWindow.bounds.x + blockerWindow.bounds.width
      && blockerWindow.bounds.y <= editorCenter.y
      && editorCenter.y < blockerWindow.bounds.y + blockerWindow.bounds.height,
    'TextEdit editable surface was not covered',
  );

  const value = 'TextEdit background verified';
  await worker.call('set_value', { app, windowId: window.windowId, element_index: editor.index, value });
  const after = await worker.call('get_app_state', { app, windowId: window.windowId, launch: false });

  assert.ok(after.text.includes(value));
  assert.equal((await waitForJson(blocker.state)).blockerClickCount, 0);
  const frontmostAfter = await inspectMacState('frontmost_app');
  const pointerAfter = await inspectMacState('physical_cursor_position');
  const activity = await inputMonitor.stop();
  assertFocusIsolation(frontmostBefore, frontmostAfter, activity, [textEditPid, blocker.ready.pid]);
  assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity);
});


test('Safari accepts covered web actions without pointer or focus movement', { timeout: 45_000 }, async (t) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'cu-native-safari-'));
  const worker = new RuntimeWorker({ sessionId: 'native-safari' });
  const fixture = await startBrowserFixture();
  let blocker;
  const safariExecutable = realpathSync('/Applications/Safari.app/Contents/MacOS/Safari');
  const preexisting = pidsForExecutable(safariExecutable);
  let safariPid;
  let inputMonitor;
  t.after(async () => {
    let cleanupError;
    try {
      if (inputMonitor) await inputMonitor.stop();
    } catch (error) {
      cleanupError = error;
    }
    await worker.close();
    await stopChild(blocker);
    await stopOwnedProcess(safariPid, safariExecutable);
    await fixture.close();
    await rm(directory, { recursive: true, force: true });
    if (cleanupError) throw cleanupError;
  });

  inputMonitor = await startInputActivityMonitor();
  const frontmostBefore = await inspectMacState('frontmost_app');
  const pointerBefore = await inspectMacState('physical_cursor_position');
  await inputMonitor.reset();
  safariPid = await launchOwnedApp('Safari', ['-F', fixture.url], safariExecutable, preexisting, 15_000);
  const window = await waitForWindow(
    worker,
    (item) => item.pid === safariPid
      && item.title.includes('CU Browser Background Harness')
      && processMatchesExecutable(item.pid, safariExecutable),
    15_000,
  );
  const app = `pid:${window.pid}`;
  const state = await waitForAppState(
    worker,
    { app, windowId: window.windowId },
    (candidate) => candidate.elements.some((item) => (item.title || item.description) === 'Background Click'),
  );
  const button = findElement(
    state,
    (item) => item.role === 'AXButton' && (item.title || item.description) === 'Background Click',
    'Safari web button',
  );
  blocker = await launchBlocker(directory, state.target);
  const buttonCenter = {
    x: state.target.bounds.x + button.bounds.x + button.bounds.width / 2,
    y: state.target.bounds.y + button.bounds.y + button.bounds.height / 2,
  };
  const blockerWindow = (await inspectMacState('list_windows')).find((item) => item.pid === blocker.ready.pid);
  assert.ok(blockerWindow, 'Safari blocker window did not register');
  assert.ok(
    blockerWindow.bounds.x <= buttonCenter.x
      && buttonCenter.x < blockerWindow.bounds.x + blockerWindow.bounds.width
      && blockerWindow.bounds.y <= buttonCenter.y
      && buttonCenter.y < blockerWindow.bounds.y + blockerWindow.bounds.height,
    'Safari web button was not covered',
  );

  await worker.call('click', { app, windowId: window.windowId, element_index: button.index });
  const after = await waitForAppState(
    worker,
    { app, windowId: window.windowId },
    (candidate) => candidate.text.includes('clicked'),
  );

  assert.ok(after.text.includes('clicked'));
  assert.equal(after.cursorFeedback.drawn, true);
  assert.equal((await waitForJson(blocker.state)).blockerClickCount, 0);
  const frontmostAfter = await inspectMacState('frontmost_app');
  const pointerAfter = await inspectMacState('physical_cursor_position');
  const activity = await inputMonitor.stop();
  assertFocusIsolation(frontmostBefore, frontmostAfter, activity, [safariPid, blocker.ready.pid]);
  assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity);
});


test('Microsoft Edge existing window accepts a reversible covered new-tab action without pointer or focus movement', { timeout: 40_000 }, async (t) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'cu-native-edge-'));
  const worker = new RuntimeWorker({ sessionId: 'native-edge' });
  const edgeExecutable = '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge';
  let blocker;
  let edgePid;
  let edgeWindow;
  let inputMonitor;
  const preexistingEdgeWindows = (await inspectMacState('list_windows'))
    .filter((item) => processMatchesExecutable(item.pid, edgeExecutable));
  if (preexistingEdgeWindows.length === 0) {
    t.skip('Microsoft Edge is not running; the focus-isolation test will not launch it');
    await worker.close();
    await rm(directory, { recursive: true, force: true });
    return;
  }
  edgeWindow = preexistingEdgeWindows[0];
  edgePid = edgeWindow.pid;
  t.after(async () => {
    let cleanupError;
    try {
      if (inputMonitor) await inputMonitor.stop();
    } catch (error) {
      cleanupError = error;
    }
    await stopChild(blocker);
    await worker.close();
    await rm(directory, { recursive: true, force: true });
    if (cleanupError) throw cleanupError;
  });

  inputMonitor = await startInputActivityMonitor();
  const frontmostBefore = await inspectMacState('frontmost_app');
  const pointerBefore = await inspectMacState('physical_cursor_position');
  await inputMonitor.reset();
  const app = `pid:${edgeWindow.pid}`;
  const state = await waitForAppState(
    worker,
    { app, windowId: edgeWindow.windowId },
    (candidate) => candidate.elements.some((item) => item.role === 'AXButton' && /^(New tab|New Tab|新建标签页|新标签页)$/.test(item.title || item.description || '')),
  );
  const newTab = findElement(
    state,
    (item) => item.role === 'AXButton' && /^(New tab|New Tab|新建标签页|新标签页)$/.test(item.title || item.description || ''),
    'Edge new-tab button',
  );
  const originalTabs = edgeTabs(state);
  const originalTabTitles = originalTabs.map((item) => item.title || item.description || '');
  assert.ok(originalTabs.length >= 1, 'Edge existing window must expose at least one tab');
  blocker = await launchBlocker(directory, state.target);
  const buttonCenter = {
    x: state.target.bounds.x + newTab.bounds.x + newTab.bounds.width / 2,
    y: state.target.bounds.y + newTab.bounds.y + newTab.bounds.height / 2,
  };
  const blockerWindow = (await inspectMacState('list_windows')).find((item) => item.pid === blocker.ready.pid);
  assert.ok(blockerWindow, 'Edge blocker window did not register');
  assert.ok(
    blockerWindow.bounds.x <= buttonCenter.x
      && buttonCenter.x < blockerWindow.bounds.x + blockerWindow.bounds.width
      && blockerWindow.bounds.y <= buttonCenter.y
      && buttonCenter.y < blockerWindow.bounds.y + blockerWindow.bounds.height,
    'Edge new-tab button was not covered',
  );

  let after;
  let restored;
  try {
    await worker.call('click', { app, windowId: edgeWindow.windowId, element_index: newTab.index });
    after = await waitForAppState(
      worker,
      { app, windowId: edgeWindow.windowId },
      (candidate) => edgeTabs(candidate).length === originalTabs.length + 1,
    );
  } finally {
    const cleanupState = after || await worker.call('get_app_state', {
      app,
      windowId: edgeWindow.windowId,
      launch: false,
    });
    if (edgeTabs(cleanupState).length === originalTabs.length + 1) {
      const closeTab = rightmostTabCloseButton(cleanupState);
      await worker.call('click', {
        app,
        windowId: edgeWindow.windowId,
        element_index: closeTab.index,
      });
      restored = await waitForAppState(
        worker,
        { app, windowId: edgeWindow.windowId },
        (candidate) => edgeTabs(candidate).length === originalTabs.length,
      );
    }
  }

  assert.equal(edgeTabs(after).length, originalTabs.length + 1);
  assert.ok(restored, 'Edge test must remove the exact tab it added');
  assert.deepEqual(
    edgeTabs(restored).map((item) => item.title || item.description || ''),
    originalTabTitles,
  );
  assert.equal(after.cursorFeedback.drawn, true);
  assert.equal((await waitForJson(blocker.state)).blockerClickCount, 0);
  const frontmostAfter = await inspectMacState('frontmost_app');
  const pointerAfter = await inspectMacState('physical_cursor_position');
  const activity = await inputMonitor.stop();
  assertFocusIsolation(frontmostBefore, frontmostAfter, activity, [edgePid, blocker.ready.pid]);
  assertPhysicalPointerIsolation(pointerBefore, pointerAfter, activity);
});
