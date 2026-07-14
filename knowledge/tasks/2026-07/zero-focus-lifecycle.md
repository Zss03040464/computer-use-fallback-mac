# Zero-focus lifecycle

Date: 2026-07-13
Status: complete

## Result

The focus-isolation contract now covers application launch, harness creation, blocker placement, background actions and cleanup. It rejects any temporary target/blocker/overlay activation rather than checking only the final foreground application.

The two red `CU Blocker Harness` windows were test-only occluders from the two-target concurrent test. They are now nonactivating and nearly transparent by default, while remaining available as visible red diagnostics through `CU_BLOCKER_VISIBLE=1`.

## Official comparison

Official Computer Use and the local production runtime each launched System Settings while continuous sampling observed only Codex as frontmost. The official request later lost its native pipe before returning state, and the local request returned `window_not_found`; neither launch activated System Settings. This isolated the reported interruption to test setup rather than the production nonactivation launch flags.

## Verification

- TDD RED: four focus assertion cases failed before transition history was enforced.
- TDD RED: the fixture purity test found all seven focus-taking/forced-ordering tokens before removal.
- `npm run test:all`: 89 Python, 20 Node, 2 integration and 6 live tests pass.
- Controlled actions still cover click, coordinate click, down/up, text, confirm, drag and scroll with zero blocker crosstalk.
- Native tests cover Chess launch error path, Calculator, TextEdit, Safari, reversible Edge tab action and exact-PID overlay nonactivation.
- Clean-copy install/MCP transport, `npm audit --omit=dev`, Node syntax and Python compile pass.
- Verifier-integrity review found no weakened assertions or skipped coverage; the sole structural finding is pre-existing `runtime/mac_helper.py` size debt untouched by this task.

IME composition contents are not read or modified by the test. The causal OS event that interrupts composition—application activation—is continuously observed and forbidden while ordinary key events cannot waive it.
