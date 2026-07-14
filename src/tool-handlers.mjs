import { RuntimeCallError } from './runtime-worker.mjs';


function textResult(value) {
  return { content: [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }] };
}

function errorResult(error) {
  const payload = {
    code: error.code || 'runtime_error',
    message: error.message || 'Computer Use action failed',
    details: error.details || {},
  };
  return { content: [{ type: 'text', text: JSON.stringify(payload) }], isError: true };
}

function targetPayload(args) {
  return { app: args.app, windowId: args.windowId };
}

function normalizeDirection(value = 'down') {
  return ({ u: 'up', d: 'down', l: 'left', r: 'right' })[value] || value;
}

export function createToolHandler({ runtime, legacyCall }) {
  return async function handleTool(name, args = {}) {
    try {
      switch (name) {
        case 'list_apps':
          return textResult(await runtime.call('list_apps', {}));
        case 'list_windows':
          return textResult(await runtime.call('list_windows', { app: args.app }));
        case 'get_app_state': {
          const state = await runtime.call('get_app_state', {
            app: args.app,
            windowId: args.windowId,
            launch: args.launch !== false,
            disableDiff: args.disableDiff === true,
          });
          return {
            content: [
              { type: 'text', text: `${state.text}\n\n${JSON.stringify({ target: state.target, generation: state.generation, cursorFeedback: state.cursorFeedback })}` },
              { type: 'image', data: state.screenshot.base64, mimeType: 'image/png' },
            ],
          };
        }
        case 'click':
          return textResult(await runtime.call('click', {
            ...targetPayload(args),
            element_index: args.element_index,
            x: args.x,
            y: args.y,
            button: args.mouse_button || 'left',
            click_count: args.click_count || 1,
          }));
        case 'perform_secondary_action':
          return textResult(await runtime.call('perform_secondary_action', { ...targetPayload(args), element_index: args.element_index, action: args.action }));
        case 'set_value':
          return textResult(await runtime.call('set_value', { ...targetPayload(args), element_index: args.element_index, value: args.value }));
        case 'type_text':
          return textResult(await runtime.call('type_text', { ...targetPayload(args), element_index: args.element_index, text: args.text }));
        case 'select_text':
          return textResult(await runtime.call('select_text', { ...targetPayload(args), element_index: args.element_index, text: args.text, prefix: args.prefix, suffix: args.suffix, selection_type: args.selection_type || 'text' }));
        case 'press_key':
          return textResult(await runtime.call('press_key', { ...targetPayload(args), element_index: args.element_index, key: args.key, modifiers: args.modifiers || [] }));
        case 'scroll':
          return textResult(await runtime.call('scroll', { ...targetPayload(args), element_index: args.element_index, x: args.x, y: args.y, direction: normalizeDirection(args.direction), pages: args.pages || 1, delta_x: args.delta_x || 0, delta_y: args.delta_y || 0 }));
        case 'drag':
          return textResult(await runtime.call('drag', { ...targetPayload(args), element_index: args.element_index, from_x: args.from_x, from_y: args.from_y, to_x: args.to_x, to_y: args.to_y, button: args.mouse_button || 'left' }));
        case 'cursor_position':
          return textResult(await runtime.call('cursor_position', {}));
        case 'mouse_move':
          return textResult(await runtime.call('set_cursor', { x: args.x, y: args.y, button: null }));
        case 'virtual_cursor_overlay':
          return textResult(await runtime.call('virtual_cursor_overlay', { action: args.action || 'status' }));
        case 'mouse_click':
          return textResult(await runtime.call('click', { ...targetPayload(args), element_index: args.element_index, x: args.x, y: args.y, button: args.button || 'left', click_count: args.count || 1 }));
        case 'mouse_scroll':
          return textResult(await runtime.call('scroll', { ...targetPayload(args), element_index: args.element_index, x: args.x, y: args.y, direction: normalizeDirection(args.direction), pages: args.pages || 1, delta_x: args.deltaX || 0, delta_y: args.deltaY || 0 }));
        case 'mouse_drag':
          return textResult(await runtime.call('drag', { ...targetPayload(args), element_index: args.element_index, from_x: args.fromX, from_y: args.fromY, to_x: args.toX, to_y: args.toY, button: args.button || 'left' }));
        case 'mouse_down':
        case 'mouse_up':
          return textResult(await runtime.call(name, { ...targetPayload(args), element_index: args.element_index, x: args.x, y: args.y, button: args.button }));
        case 'key': {
          const parts = String(args.keySequence).split('+');
          const key = parts.pop();
          return textResult(await runtime.call('press_key', { ...targetPayload(args), element_index: args.element_index, key, modifiers: parts }));
        }
        case 'detect_and_close_popups':
          return errorResult(new RuntimeCallError({ code: 'unsupported_background_action', message: 'Global popup clicking is disabled; inspect the target app state and click an explicit element.', details: {} }));
        case 'screenshot': {
          const result = await legacyCall('screenshot', args);
          return { content: [{ type: 'text', text: JSON.stringify({ width: result.width, height: result.height, displayId: result.displayId }) }, { type: 'image', data: result.base64, mimeType: 'image/jpeg' }] };
        }
        case 'screenshot_region': {
          const result = await legacyCall('zoom', { ...args, left: args.x, top: args.y });
          return { content: [{ type: 'text', text: JSON.stringify({ width: result.width, height: result.height }) }, { type: 'image', data: result.base64, mimeType: 'image/jpeg' }] };
        }
        case 'check_permissions':
        case 'read_clipboard':
        case 'map_coordinates':
        case 'detect_captcha':
          return textResult(await legacyCall(name, args));
        case 'write_clipboard':
          return textResult(await legacyCall('write_clipboard', { text: args.text }));
        default:
          return errorResult(new RuntimeCallError({ code: 'tool_not_found', message: `Tool not found: ${name}`, details: { name } }));
      }
    } catch (error) {
      return errorResult(error);
    }
  };
}
