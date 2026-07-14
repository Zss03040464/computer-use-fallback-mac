# Official cursor visual fidelity V2

Status: complete
Date: 2026-07-13

## Requirement

Use official Computer Use as the live visual reference, replace the current saturated cyan-dot cursor with a deeply similar but independently distinguishable cursor, and preserve all background-control and physical-pointer-isolation guarantees.

## Approved design

`knowledge/features/official-style-cursor-feedback.md`

## Evidence collected

- Official Calculator initial, immediate click, settled click and moved-cursor states were captured locally.
- The official visible core is approximately 15 by 20 pixels at 1x, with translucent near-white fill, a pale edge and a soft bloom.
- The official style has no accent dot and no hard pulse ring.
- Local official captures are analysis evidence only and are not copied into the repository.

## Required invariants

- preserve exact bundle/PID/window cursor binding;
- preserve click-through overlay and per-session ownership;
- preserve unchanged physical pointer and frontmost application;
- preserve strict failure for input without a verified background-safe route;
- share one visual contract across live and screenshot rendering.

## Implemented result

- `fallback-official-aqua-arrow-v2` uses an independently drawn 13×18 cool-white translucent arrow.
- The weak aqua tail edge and asymmetric lower cut provide a subtle difference from the official sample.
- The old saturated outline, accent dot and hard ring are removed.
- The target-window compositor uses a compact 4× supersampled patch; AppKit and legacy screenshots consume the same geometry/palette contract.
- The session overlay is a nonactivating `NSPanel` under prohibited activation policy.
- `frontmost_app` now exposes exact PID so same-bundle focus changes cannot hide.

## Final evidence

- official Calculator initial/click/settled/moved/uniform-background captures analyzed locally without committing official assets;
- deterministic 1×/2× dark, mid and light specimen generated from production code;
- `npm run test:all`: 87 Python, 18 Node, 2 controlled integration and 5 native/overlay live tests pass, followed by the legacy live overlay gate;
- Calculator, TextEdit, Safari and the then-current disposable Edge fixture accepted covered background actions; the later zero-focus task supersedes that Edge fixture with an existing-window reversible-tab gate;
- read-only HID event attribution proves concurrent user movement is hardware-originated and rejects every non-HID mouse-move event;
- clean-copy bootstrap/MCP transport, dependency audit, Node syntax, Python compile, static input safety, overlay style and installability gates pass;
- Codex Project System passes after explicit review of all changed verifier files, with no purity or structural findings;
- manual app-targeted Calculator capture returns `drawn=true`, exact element center and the V2 style identifier while the physical pointer remains unchanged.
