# Source Map

## Runtime architecture

| File | Responsibility |
| --- | --- |
| `start-mcp.mjs` | MCP stdio entrypoint |
| `src/mcp-server.mjs` | MCP lifecycle and tool request handlers |
| `src/tool-definitions.mjs` | Official-style and compatibility tool schemas |
| `src/tool-handlers.mjs` | MCP argument/result mapping |
| `src/bridge.mjs` | Python dependency bootstrap and worker ownership |
| `src/runtime-worker.mjs` | Persistent JSONL worker client and bounded shutdown |
| `runtime/worker.py` | Persistent Python command loop |
| `runtime/cu_runtime/service.py` | Session/target/snapshot/action orchestration |
| `runtime/cu_runtime/targets.py` | Application and CoreGraphics window discovery |
| `runtime/cu_runtime/capture.py` | ScreenCaptureKit-first target-window capture |
| `runtime/cu_runtime/accessibility.py` | AX window subtree, indexes, bounds and fingerprints |
| `runtime/cu_runtime/actions.py` | AX-first strict background action router |
| `runtime/cu_runtime/session.py` | Per-session cursor/snapshot paths and target locks |
| `runtime/cu_runtime/cursor_feedback.py` | Shared cursor record validation, V2 geometry/palette, pulse timing, 4x supersampled bounded PNG compositing |
| `runtime/cu_runtime/overlay.py` | Per-session virtual cursor overlay lifecycle |
| `runtime/virtual_cursor_overlay.py` | Click-through nonactivating AppKit panel process |
| `scripts/render-cursor-specimen.py` | Deterministic dark/mid/light production cursor specimen |

## Compatibility layer

`runtime/mac_helper.py` originates from the extracted cc-haha Computer Use helper. Display screenshots, permission checks, clipboard, OCR and coordinate diagnostics remain available. Its production mouse action commands no longer post desktop-global input; app-targeted actions use `runtime/cu_runtime/`.

The standalone runtime does not import cc-haha services, analytics, feature flags, authorization state or business logic.

## Verification map

| Area | Evidence |
| --- | --- |
| Global-targeting prohibition | `tests/python/test_no_global_targeting.py`, `test-virtual-mouse-static.mjs` |
| Session and lock isolation | `tests/python/test_session_state.py`, `tests/node/multi-worker-isolation.test.mjs` |
| Target resolution and capture | `tests/python/test_targets.py`, `tests/python/test_capture_metadata.py` |
| AX state and stale indexes | `tests/python/test_accessibility_snapshot.py` |
| Click/text/key/scroll/drag | `tests/python/test_click_routing.py`, `test_text_key_actions.py`, `test_scroll_drag_actions.py` |
| Cursor feedback and screenshot binding | `tests/python/test_cursor_feedback.py`, `test_action_service.py`, `test_target_service.py` |
| Cursor visual specimen | `tests/python/test_cursor_specimen.py`, `scripts/render-cursor-specimen.py` |
| Overlay activation isolation | `tests/live/overlay-focus-isolation.test.mjs`, `test-overlay-style.mjs` |
| Covered controlled target | `tests/integration/background-actions.test.mjs` |
| Concurrent targets | `tests/integration/concurrent-targets.test.mjs` |
| Native app matrix | `tests/live/native-app-matrix.test.mjs` |
| MCP transport | `tests/node/mcp-transport.test.mjs` |
| Installation assets | `test-installability.mjs` |

## Design records

- `knowledge/architecture/app-targeted-runtime.md`
- `knowledge/features/official-style-cursor-feedback.md`
- `knowledge/quality/background-control-verification.md`
- `knowledge/incidents/2026-07-13-overlay-activation-policy.md`
- `knowledge/incidents/2026-07-13-setup-focus-interruption.md`
