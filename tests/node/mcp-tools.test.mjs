import test from 'node:test';
import assert from 'node:assert/strict';

import { RuntimeCallError } from '../../src/runtime-worker.mjs';
import { tools } from '../../src/tool-definitions.mjs';
import { createToolHandler } from '../../src/tool-handlers.mjs';


const officialNames = [
  'list_apps',
  'get_app_state',
  'click',
  'drag',
  'scroll',
  'press_key',
  'type_text',
  'set_value',
  'select_text',
  'perform_secondary_action',
];


class FakeWorker {
  constructor(result = {}) {
    this.result = result;
    this.calls = [];
  }

  async call(command, payload) {
    this.calls.push({ command, payload });
    if (this.result instanceof Error) throw this.result;
    return this.result;
  }
}


test('tools expose official app-targeted surface and safe legacy targets', () => {
  const names = new Set(tools.map((tool) => tool.name));
  for (const name of officialNames) assert.equal(names.has(name), true, `missing ${name}`);

  const click = tools.find((tool) => tool.name === 'click');
  assert.equal(click.inputSchema.properties.app.type, 'string');
  assert.equal(click.inputSchema.properties.element_index.type, 'integer');
  assert.deepEqual(click.inputSchema.oneOf, [
    { required: ['element_index'] },
    { required: ['x', 'y'] },
  ]);

  const legacy = tools.find((tool) => tool.name === 'mouse_click');
  assert.equal(legacy.inputSchema.properties.app.type, 'string');
  assert.equal(legacy.inputSchema.properties.windowId.type, 'integer');
});


test('get_app_state returns target text and PNG image blocks', async () => {
  const worker = new FakeWorker({
    app: '/System/Applications/Calculator.app',
    target: { bundleId: 'com.apple.calculator', windowId: 42 },
    generation: 3,
    text: '0 AXWindow Calculator',
    cursorFeedback: { drawn: true, style: 'fallback-official-aqua-arrow-v2', imagePoint: [60, 50] },
    screenshot: { base64: Buffer.from('png').toString('base64'), backend: 'screen-capture-kit' },
  });
  const handler = createToolHandler({ runtime: worker, legacyCall: async () => null });

  const result = await handler('get_app_state', { app: 'com.apple.calculator' });

  assert.equal(result.content[0].text.includes('0 AXWindow Calculator'), true);
  assert.equal(result.content[1].type, 'image');
  assert.equal(result.content[1].mimeType, 'image/png');
  const summary = JSON.parse(result.content[0].text.split('\n\n').at(-1));
  assert.deepEqual(summary.cursorFeedback.imagePoint, [60, 50]);
  assert.deepEqual(worker.calls[0], {
    command: 'get_app_state',
    payload: { app: 'com.apple.calculator', windowId: undefined, launch: true, disableDiff: false },
  });
});


test('click maps official arguments to the runtime worker', async () => {
  const worker = new FakeWorker({ backend: 'accessibility', verification: 'ax_action' });
  const handler = createToolHandler({ runtime: worker, legacyCall: async () => null });

  const result = await handler('click', {
    app: 'Calculator',
    element_index: 7,
    mouse_button: 'left',
    click_count: 2,
  });

  assert.equal(result.isError, undefined);
  assert.deepEqual(worker.calls[0], {
    command: 'click',
    payload: {
      app: 'Calculator',
      windowId: undefined,
      element_index: 7,
      x: undefined,
      y: undefined,
      button: 'left',
      click_count: 2,
    },
  });
});

test('select_text preserves context and cursor semantics through MCP mapping', async () => {
  const worker = new FakeWorker({ backend: 'accessibility', verification: 'ax_action' });
  const handler = createToolHandler({ runtime: worker, legacyCall: async () => null });

  await handler('select_text', {
    app: 'TextEdit',
    windowId: 42,
    element_index: 8,
    text: 'world',
    prefix: 'second ',
    suffix: '!',
    selection_type: 'cursor_after',
  });

  assert.deepEqual(worker.calls[0], {
    command: 'select_text',
    payload: {
      app: 'TextEdit',
      windowId: 42,
      element_index: 8,
      text: 'world',
      prefix: 'second ',
      suffix: '!',
      selection_type: 'cursor_after',
    },
  });
});


test('structured runtime errors become MCP errors without leaking stack traces', async () => {
  const worker = new FakeWorker(new RuntimeCallError({
    code: 'stale_state',
    message: 'State changed',
    details: { recovery: 'Call get_app_state again' },
  }));
  const handler = createToolHandler({ runtime: worker, legacyCall: async () => null });

  const result = await handler('click', { app: 'Calculator', element_index: 7 });

  assert.equal(result.isError, true);
  assert.deepEqual(JSON.parse(result.content[0].text), {
    code: 'stale_state',
    message: 'State changed',
    details: { recovery: 'Call get_app_state again' },
  });
});

test('virtual cursor overlay is scoped through the runtime session', async () => {
  const worker = new FakeWorker({ running: true, pid: 123, sessionId: 'session-a' });
  const handler = createToolHandler({ runtime: worker, legacyCall: async () => ({ running: false }) });

  await handler('virtual_cursor_overlay', { action: 'start' });

  assert.deepEqual(worker.calls[0], {
    command: 'virtual_cursor_overlay',
    payload: { action: 'start' },
  });
});
