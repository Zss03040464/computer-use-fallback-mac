# Project Agent Instructions

Project root: the repository root.

## Current project truth

This project is the local stdio MCP server named `computer-use-fallback-mac`.

Codex launches it with:

```text
node ./start-mcp.mjs
```

## Mouse control rule

Mouse controls must use the application/window-targeted virtual mouse model.

Do not reintroduce `pyautogui.moveTo`, `pyautogui.click`, `pyautogui.scroll`, `pyautogui.hscroll`, `pyautogui.dragTo`, `pyautogui.mouseDown`, or `pyautogui.mouseUp` in mouse action paths.

Production mouse actions must use verified Accessibility semantics against an explicit PID/CoreGraphics window. Do not add desktop-global or unacknowledged PID event delivery, application activation, `AXRaise`, or a fallback that can hit the visible foreground window.

After verified mouse-like delivery, persist target-bound per-session cursor feedback. The click-through live overlay and `get_app_state` screenshot must consume the same cursor record. Feedback failure must not turn an already-delivered action into a failed tool call that callers may retry.

## Verification

Run real macOS UI diagnostics serially so disposable fixture windows cannot interfere with each other. Cursor state itself is isolated per MCP session under `runtime/sessions/`.

Required checks for mouse changes:

```bash
npm test
npm run test:live
npm run test:clean-install
npm audit --omit=dev
```

The physical pointer must remain unchanged during virtual mouse move, click, scroll, drag, mouse down, and mouse up.

## Repository publication rule

GitHub receives only the curated product snapshot. Local agent state, session logs, handoff/history records, runtime state, credentials, generated dependencies and personal absolute paths must never be tracked or uploaded.

Do not push a full local-history development branch to the publication remote. Run the repository-hygiene test and publish from a sanitized snapshot branch.
