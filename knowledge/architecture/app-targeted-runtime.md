# App-targeted runtime architecture

The Node MCP process owns one long-lived `RuntimeWorker`. The Python service resolves an explicit app/window, captures that window, builds the matching AX window subtree and stores the capture/snapshot under the MCP session.

Actions are serialized with a lock keyed by bundle/window. AX element fingerprints bind indexes to the target window and reject stale identity changes. AX window matching never falls back across multiple nonmatching windows.

The built-in event backend has no delivery capability and performs no raw post. Only an externally injected backend with an application acknowledgement contract may extend the router; unsupported controls fail before delivery.

Verified mouse-like results carry their resolved global action point. The service atomically writes that point with bundle/process/window, action, phase and timestamp into the owning session. `runtime/cu_runtime/cursor_feedback.py` is the shared model for the AppKit live overlay and app-state PNG compositor; a mismatched target never receives another session/window's cursor.

Every overlay receives an explicit persistent owner PID and rejects PID 0/1. Per-session overlays are managed by their worker. The legacy compatibility overlay is recognized only when its script, session, state path, PID path and owner arguments all match; status and cleanup never claim another session's overlay.

Source anchors: `src/runtime-worker.mjs`, `runtime/cu_runtime/service.py`, `targets.py`, `capture.py`, `accessibility.py`, `actions.py`, `session.py`, `cursor_feedback.py`.
