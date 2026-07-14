const targetProperties = {
  app: {
    type: 'string',
    description: 'Application display name, bundle identifier, or absolute .app path.',
  },
  windowId: {
    type: 'integer',
    description: 'Optional CoreGraphics window identifier.',
  },
};

const coordinateProperties = {
  x: { type: 'number', description: 'X coordinate in the target window screenshot.' },
  y: { type: 'number', description: 'Y coordinate in the target window screenshot.' },
};

export const tools = [
  {
    name: 'list_apps',
    description: 'List installed and running macOS applications addressable by Computer Use.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'get_app_state',
    description: 'Capture one application window without foreground compositing and return its Accessibility state.',
    inputSchema: {
      type: 'object',
      properties: {
        ...targetProperties,
        disableDiff: { type: 'boolean', description: 'Return a full state tree instead of a future diff.' },
        launch: { type: 'boolean', description: 'Launch without activation when the app is not running. Default true.' },
      },
      required: ['app'],
    },
  },
  {
    name: 'click',
    description: 'Click an indexed element or window-local coordinate without activating the target app or moving the physical pointer.',
    inputSchema: {
      type: 'object',
      properties: {
        ...targetProperties,
        element_index: { type: 'integer' },
        ...coordinateProperties,
        mouse_button: { type: 'string', enum: ['left', 'right', 'middle'] },
        click_count: { type: 'integer', minimum: 1 },
      },
      required: ['app'],
      oneOf: [{ required: ['element_index'] }, { required: ['x', 'y'] }],
    },
  },
  {
    name: 'drag',
    description: 'Drag a target control using AX value semantics or app-directed events.',
    inputSchema: {
      type: 'object',
      properties: {
        ...targetProperties,
        element_index: { type: 'integer' },
        from_x: { type: 'number' }, from_y: { type: 'number' },
        to_x: { type: 'number' }, to_y: { type: 'number' },
        mouse_button: { type: 'string', enum: ['left', 'right', 'middle'] },
      },
      required: ['app', 'from_x', 'from_y', 'to_x', 'to_y'],
    },
  },
  {
    name: 'scroll',
    description: 'Scroll an indexed target element or window-local point without foreground activation.',
    inputSchema: {
      type: 'object',
      properties: {
        ...targetProperties,
        element_index: { type: 'integer' },
        ...coordinateProperties,
        direction: { type: 'string', enum: ['up', 'down', 'left', 'right', 'u', 'd', 'l', 'r'] },
        pages: { type: 'integer', minimum: 1 },
        delta_x: { type: 'integer' },
        delta_y: { type: 'integer' },
      },
      required: ['app'],
      oneOf: [{ required: ['element_index'] }, { required: ['x', 'y'] }],
    },
  },
  {
    name: 'press_key',
    description: 'Perform a target-scoped key or semantic confirm action.',
    inputSchema: {
      type: 'object',
      properties: {
        ...targetProperties,
        element_index: { type: 'integer' },
        key: { type: 'string' },
        modifiers: { type: 'array', items: { type: 'string' } },
      },
      required: ['app', 'key'],
    },
  },
  {
    name: 'type_text',
    description: 'Insert text through an editable element inside the explicit target application.',
    inputSchema: {
      type: 'object',
      properties: { ...targetProperties, element_index: { type: 'integer' }, text: { type: 'string' } },
      required: ['app', 'text'],
    },
  },
  {
    name: 'set_value',
    description: 'Set an Accessibility element value in the explicit target application.',
    inputSchema: {
      type: 'object',
      properties: { ...targetProperties, element_index: { type: 'integer' }, value: { type: 'string' } },
      required: ['app', 'element_index', 'value'],
    },
  },
  {
    name: 'select_text',
    description: 'Select an exact text occurrence inside a target editable element.',
    inputSchema: {
      type: 'object',
      properties: {
        ...targetProperties,
        element_index: { type: 'integer' },
        text: { type: 'string' },
        prefix: { type: 'string' },
        suffix: { type: 'string' },
        selection_type: { type: 'string', enum: ['text', 'cursor_before', 'cursor_after'] },
      },
      required: ['app', 'element_index', 'text'],
    },
  },
  {
    name: 'perform_secondary_action',
    description: 'Perform an action explicitly exposed by the current Accessibility element.',
    inputSchema: {
      type: 'object',
      properties: { ...targetProperties, element_index: { type: 'integer' }, action: { type: 'string' } },
      required: ['app', 'element_index', 'action'],
    },
  },
  { name: 'check_permissions', description: 'Check macOS Accessibility and Screen Recording permissions.', inputSchema: { type: 'object', properties: {} } },
  {
    name: 'screenshot',
    description: 'Compatibility display screenshot. Prefer get_app_state for app-targeted work.',
    inputSchema: { type: 'object', properties: { displayId: { type: 'integer' }, targetWidth: { type: 'integer' }, targetHeight: { type: 'integer' }, showVirtualCursor: { type: 'boolean' } } },
  },
  {
    name: 'screenshot_region',
    description: 'Compatibility display-region screenshot. Prefer get_app_state.',
    inputSchema: { type: 'object', properties: { ...coordinateProperties, width: { type: 'integer' }, height: { type: 'integer' }, targetWidth: { type: 'integer' }, targetHeight: { type: 'integer' }, showVirtualCursor: { type: 'boolean' } }, required: ['x', 'y', 'width', 'height'] },
  },
  { name: 'cursor_position', description: 'Get this MCP session virtual cursor.', inputSchema: { type: 'object', properties: {} } },
  { name: 'virtual_cursor_overlay', description: 'Start, stop, or inspect this session virtual cursor overlay.', inputSchema: { type: 'object', properties: { action: { type: 'string', enum: ['start', 'stop', 'status'] } } } },
  { name: 'mouse_move', description: 'Move only this session virtual cursor.', inputSchema: { type: 'object', properties: coordinateProperties, required: ['x', 'y'] } },
  {
    name: 'mouse_click',
    description: 'Compatibility app-targeted click. A preceding get_app_state call is required.',
    inputSchema: { type: 'object', properties: { ...targetProperties, element_index: { type: 'integer' }, ...coordinateProperties, button: { type: 'string', enum: ['left', 'right', 'middle'] }, count: { type: 'integer' } }, oneOf: [{ required: ['element_index'] }, { required: ['x', 'y'] }] },
  },
  { name: 'mouse_scroll', description: 'Compatibility app-targeted scroll.', inputSchema: { type: 'object', properties: { ...targetProperties, element_index: { type: 'integer' }, ...coordinateProperties, direction: { type: 'string' }, pages: { type: 'integer' }, deltaX: { type: 'integer' }, deltaY: { type: 'integer' } } } },
  { name: 'mouse_drag', description: 'Compatibility app-targeted drag.', inputSchema: { type: 'object', properties: { ...targetProperties, element_index: { type: 'integer' }, fromX: { type: 'number' }, fromY: { type: 'number' }, toX: { type: 'number' }, toY: { type: 'number' }, button: { type: 'string' } }, required: ['fromX', 'fromY', 'toX', 'toY'] } },
  { name: 'mouse_down', description: 'Compatibility target-scoped mouse down.', inputSchema: { type: 'object', properties: { ...targetProperties, element_index: { type: 'integer' }, ...coordinateProperties, button: { type: 'string' } }, required: ['element_index', 'x', 'y'] } },
  { name: 'mouse_up', description: 'Compatibility target-scoped mouse up.', inputSchema: { type: 'object', properties: { ...targetProperties, element_index: { type: 'integer' }, ...coordinateProperties, button: { type: 'string' } }, required: ['element_index', 'x', 'y'] } },
  { name: 'key', description: 'Compatibility target-scoped key sequence.', inputSchema: { type: 'object', properties: { ...targetProperties, element_index: { type: 'integer' }, keySequence: { type: 'string' } }, required: ['keySequence'] } },
  { name: 'read_clipboard', description: 'Read the text clipboard.', inputSchema: { type: 'object', properties: {} } },
  { name: 'write_clipboard', description: 'Write the text clipboard.', inputSchema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] } },
  { name: 'list_windows', description: 'List addressable CoreGraphics windows and stable window IDs, optionally filtered to one app.', inputSchema: { type: 'object', properties: { app: targetProperties.app } } },
  { name: 'map_coordinates', description: 'Map logical and physical display coordinates.', inputSchema: { type: 'object', properties: { ...coordinateProperties, to: { type: 'string', enum: ['logical', 'physical'] }, displayId: { type: 'integer' } }, required: ['x', 'y', 'to'] } },
  { name: 'detect_captcha', description: 'Read-only CAPTCHA keyword scan.', inputSchema: { type: 'object', properties: { displayId: { type: 'integer' } } } },
  { name: 'detect_and_close_popups', description: 'Disabled unsafe compatibility action.', inputSchema: { type: 'object', properties: {} } },
];

Object.freeze(tools);
