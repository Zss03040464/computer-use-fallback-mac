# Virtual cursor feedback

Successful mouse-like actions produce one target-bound cursor record per MCP session. The record contains input/image coordinates, the global display point, bundle/process/window identity, action, button phase and timestamp.

The click-through AppKit overlay and `get_app_state` PNG compositor share geometry, palette and pulse timing from `runtime/cu_runtime/cursor_feedback.py`. Initial state has no cursor. A verified click/release creates a pulse that decays to the steady cursor; target mismatch, malformed state and out-of-bounds coordinates draw nothing.

The `aqua-glass-arrow-v2` style has a 13 by 18 logical-pixel translucent cool-white body, near-white edge, soft non-ring bloom and weak aqua clipped-tail edge. PNG output is rendered at 4x inside a bounded patch and downsampled with Lanczos. The AppKit path consumes the same repository-owned geometry and palette.

Feedback is post-delivery and best effort. The first half of a session-owned down/up gesture is explicitly labeled `cursorFeedback.delivery=pending`; matching mouse-up completes it. Cursor-state or overlay errors are warnings and cannot turn completed input into a failed action that callers may replay. Unsupported input still fails before delivery.

The overlay watches an explicit persistent owner PID, rejects invalid owners and exits when that owner disappears. Its window is a nonactivating `NSPanel`, and the process uses `NSApplicationActivationPolicyProhibited`; foreground identity is verified by exact PID.

Verification anchors include `tests/python/test_cursor_feedback.py`, `tests/python/test_cursor_specimen.py`, `tests/python/test_action_service.py`, `tests/python/test_target_service.py`, `tests/live/overlay-focus-isolation.test.mjs`, covered integration, two-session integration and the native application matrix.

