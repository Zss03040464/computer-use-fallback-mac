# Official-style cursor feedback

Status: complete
Date: 2026-07-13

## Requirement

Use Codex official Computer Use as the behavioral reference and make successful mouse-like actions update one per-session cursor that appears both as a click-through live overlay and in the next `get_app_state` window screenshot.

## Verified gap

Official Calculator click feedback appears at the acted-on indexed button in the next state screenshot. The current fallback has a standalone overlay implementation, but `RuntimeService.click` does not persist/start it and `get_app_state` does not composite cursor feedback into the independent target-window capture.

## Approved design

`knowledge/features/official-style-cursor-feedback.md`

## Safety contract

- preserve physical-pointer and focus isolation;
- update feedback only after verified action delivery, except an explicitly `pending` session-owned mouse-down;
- never fail an already-delivered action because overlay startup failed;
- composite only when the cursor target matches the captured window;
- keep session cursor and overlay state isolated.

## Acceptance evidence

- unit red-green coverage for points, phases, compositing, warnings, failures and strict overlay ownership;
- covered-window and two-session integration evidence;
- official/fallback Calculator state-click-state comparison;
- full project quality gates and independent review.

## Current evidence

- 84 Python tests, 14 Node tests and 2 covered integration tests pass under `npm test`.
- Calculator, TextEdit, Safari and isolated Microsoft Edge live tests pass.
- Official and fallback Calculator state/index-click/state screenshots both show post-action cursor feedback at the acted-on digit.
- Edge ownership regression now requires `open -n`, a temporary profile and one verified new executable PID.
- Independent review hardening added exact bundle/PID/window cursor binding, compact compositor allocations, multi-display Quartz/AppKit mapping, malformed-state suppression, overlay owner-liveness cleanup, startup-timeout process cleanup and exact Edge profile-token ownership.
- Legacy overlay ownership is passed explicitly from the persistent Node bridge, rejects PID 0/1, and requires exact script/session/state/PID-file/owner arguments before status or signal operations. Cross-session cleanup is regression-tested.
- `npm run test:all`, `npm run test:clean-install`, Node/Python syntax, `npm audit --omit=dev` and banned production input-path scans pass.
- Codex Project System gate returned `passed: true` with no failures, purity findings, verifier changes or structural findings in the final clean configured checkout.
- Multiple independent review rounds ended with no remaining Critical or Important findings.
