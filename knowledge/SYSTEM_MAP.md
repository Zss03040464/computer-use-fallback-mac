# computer-use-fallback-mac system map

## Purpose

Provide a standalone macOS Computer Use MCP component that captures and controls an explicit application window without moving the physical pointer, activating the target application, or allowing an obscuring foreground window to receive the action.

## Domains

- MCP surface: `src/mcp-server.mjs` and `src/tool-handlers.mjs` expose target discovery, state capture and actions.
- Runtime process: `src/runtime-worker.mjs` owns one persistent `runtime/worker.py` per MCP process.
- Target state: `targets.py`, `capture.py` and `accessibility.py` bind capture and deterministic AX indexes to an explicit PID/CoreGraphics window.
- Safe actions: `actions.py` uses verifiable AX semantics; unsupported background input fails before global delivery.
- Session isolation: `session.py` owns snapshots, target locks and cursor state; different windows may proceed concurrently.
- Cursor feedback: `cursor_feedback.py`, `overlay.py` and `virtual_cursor_overlay.py` render one bundle/PID/window-bound cursor in both the click-through live overlay and the next matching app-state PNG.
- Quality: Python/Node unit tests, covered-window integration, concurrent workers, native Calculator/TextEdit/Safari/Edge tests, clean-copy packaging and project-system gates.

## Runtime flow

1. `list_apps` / `list_windows` discovers an addressable target.
2. `get_app_state` resolves the target, captures only that window, builds its AX subtree and caches the generation-bound snapshot.
3. An action revalidates the target and element, acquires the target lock and uses a background-safe semantic route.
4. Successful mouse-like delivery records its resolved global point; a down/up first half is explicitly marked pending.
5. The owning live overlay and next matching app-state PNG render the same session feedback without changing physical pointer or frontmost application.
6. Missing AX semantics, stale state, target mismatch and unverified delivery return structured errors instead of a desktop-global fallback.

## Verified boundaries

- Non-AX/proprietary canvases are not universally controllable and fail explicitly when no verifiable background route exists.
- Production action paths exclude `CGEventPost`, `CGEventPostToPid`, pyautogui mouse operations, `AXRaise` and application activation.
- Overlay ownership requires an explicit persistent PID and exact session/state/PID-file identity before status or signal operations.
