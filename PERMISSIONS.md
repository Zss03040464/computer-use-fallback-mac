# macOS Permissions

The application that launches this MCP server needs two macOS privacy grants.

## Accessibility

Required for reading the target application's AX window tree and performing exposed actions such as `AXPress`, value updates, text selection, scroll controls and slider changes.

System Settings → Privacy & Security → Accessibility → enable the terminal, IDE or agent host that launches `start-mcp.mjs`.

## Screen Recording

Required for ScreenCaptureKit/CoreGraphics target-window capture.

System Settings → Privacy & Security → Screen & System Audio Recording → enable the same host application.

Restart the host application after changing either permission. The project never changes these settings automatically.

## Diagnostics

```bash
npm start
```

Then call `check_permissions`, or run:

```bash
npm run test:unit
npm run test:integration
```

Blank/failed window capture usually indicates Screen Recording is missing. Empty AX state or `element_not_actionable` across ordinary native controls usually indicates Accessibility is missing. Do not bypass a permission failure with global mouse automation.
