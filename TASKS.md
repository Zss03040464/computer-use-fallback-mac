# Tasks

## Private GitHub repository publication

Status: sanitized source tree and publication controls complete on 2026-07-14; clean-root remote publication pending.

Task evidence: `knowledge/tasks/2026-07/github-repository-publication.md`

Current evidence:

- local agent state, handoff/history/dialogue records, session logs and Superpowers process notes are retained locally but absent from the tracked publication tree;
- repository hygiene tests reject local-only paths, personal home paths, sensitive filenames, common credential signatures, missing standard files, invalid package metadata and broken relative Markdown links;
- macOS CI, Dependabot, security, contribution, conduct, changelog, issue/PR templates and provenance notice are present;
- `npm test` passes with 89 Python tests, 22 Node tests and 2 controlled integration tests;
- clean-copy bootstrap/MCP transport, dependency audit, Node syntax, Python compilation, YAML parsing and Git whitespace checks pass;
- no product mouse, focus or delivery implementation changed, so the previously recorded live isolation matrix remains the applicable runtime evidence.

## App-targeted Computer Use 0.2.0

Status: implementation complete; final independent review and gates recorded on 2026-07-13.

Acceptance evidence:

- Unit contract: 62 Python tests and 12 Node tests, including UTF-16/emoji text-range boundaries and Python 3.9 grammar compatibility.
- Covered AppKit integration: click, coordinate click, down/up, set/select/type text, confirm, drag and scroll; blocker counter unchanged.
- Concurrent integration: two workers control two covered targets with isolated cursor/snapshot state.
- Native matrix: disposable Calculator, TextEdit, Safari and Microsoft Edge instances; physical pointer and frontmost application unchanged.
- Target capture: covering application excluded from captured PNG.
- Clean install: two concurrent cold bootstrap clients, atomic dependency stamp, parent-crash/orphan-process-group lock recovery, MCP SDK initialize/tools/list/call.
- Security: no production `CGEventPost`, `CGEventPostToPid`, pyautogui mouse action, `AXRaise` or app activation; secure AX subrole values redacted.

Fresh commands:

```bash
npm test
npm run test:live
npm run test:clean-install
npm audit --omit=dev
```

No push or external deployment is part of this task.

## Official-style cursor feedback

Status: complete; implementation, independent review, official comparison and delivery gates recorded on 2026-07-13.

Architecture: `knowledge/features/official-style-cursor-feedback.md`

Task evidence: `knowledge/tasks/2026-07/official-cursor-feedback.md`

Current evidence:

- 84 Python, 14 Node and 2 controlled integration tests pass.
- Four native application tests pass with cursor feedback assertions and unchanged physical pointer/frontmost application.
- Official and fallback Calculator state → indexed click → state screenshots both show feedback on the acted-on digit.
- `npm run test:all`, clean-copy installation, Python/Node syntax, dependency audit and production input-path scans pass.
- Codex Project System passed first in external mode for the dirty worktree and again in incremental mode after the configured checkout was cleanly materialized; both returned no failures or purity findings.
- Final independent review found no remaining P1/P2 after strict overlay owner/session hardening.

## Official cursor visual fidelity V2

Status: complete; implementation, official comparison, concurrent-input attribution and all delivery gates recorded on 2026-07-13.

Architecture: `knowledge/features/official-style-cursor-feedback.md`

Task evidence: `knowledge/tasks/2026-07/official-cursor-visual-fidelity-v2.md`

Acceptance focus:

- deeply follow the official translucent near-white arrow, soft bloom and antialiased geometry;
- retain a subtle pale-aqua inner edge and asymmetric lower-tail cut as the independent identity;
- remove the current accent dot and hard ring pulse;
- keep live and screenshot renderers synchronized without weakening physical-pointer, focus, target or session isolation.

Current evidence:

- official Calculator uniform-background sampling refined the visible core to 13×18 logical pixels;
- shared 4× supersampled Pillow rendering, AppKit rendering and legacy screenshot rendering use one geometry/palette contract;
- deterministic dark/mid/light 1×/2× specimen passes;
- Calculator state/index-click/state returns `style=fallback-official-aqua-arrow-v2`, `drawn=true` and the exact clicked center;
- a newly exposed first-start focus bug is fixed with nonactivating `NSPanel` plus prohibited activation policy and exact foreground PID assertions;
- live/integration isolation uses a read-only HID event tap, so concurrent user pointer/focus activity is attributed without accepting any non-HID mouse movement;
- the later zero-focus lifecycle task supersedes the disposable Edge-window fixture with an existing-window reversible-tab gate;
- `npm run test:all` passes with 87 Python tests, 18 Node tests, 2 controlled integration tests, 5 live tests and the legacy live overlay gate;
- clean-copy bootstrap/MCP transport, Node syntax, Python compile, dependency audit, static input safety, overlay style and installability guards pass;
- Codex Project System returns `passed: true` after an explicit verifier-integrity review, with no failures, purity findings or structural findings.
- the configured checkout was fast-forwarded locally through `4b3a2e6` and passed the full `npm run test:all` gate again; no push was performed.

## Zero-focus application lifecycle

Status: complete; root cause, TDD evidence and full lifecycle verification recorded on 2026-07-13.

Verification: `knowledge/quality/background-control-verification.md`

Task evidence: `knowledge/tasks/2026-07/zero-focus-lifecycle.md`

Current evidence:

- activation monitoring starts before target/blocker/app setup and rejects every temporary protected or unattributed focus transition;
- plain typing cannot attribute a transition; only physical mouse-down or Command-Tab may attribute an unrelated application switch;
- target and blocker fixtures use nonactivating panels, prohibited activation policy after construction and ordinary ordering;
- the two red `CU Blocker Harness` windows are test-only occluders and are 2% opaque by default;
- the former Edge fixture's raise/focus/targeted-Return/restore path is deleted; the live gate now performs one reversible new-tab action only when Edge is already running;
- the production launch option remains `0x00010200` and the Chess error-path live gate proves a newly launched process does not become frontmost;
- `npm run test:all` passes in the feature worktree with 89 Python, 20 Node, 2 controlled integration and 6 live tests, including the separate overlay activation test;
- the configured checkout rerun passes the same gates with five live successes and one expected Edge skip because the zero-focus gate refuses to launch Edge;
- clean-copy install/MCP transport, dependency audit, Node syntax, Python compile, static input safety, overlay style and installability gates pass.
- after explicit verifier-integrity review and legacy structural-baseline capture, Codex Project System returns `passed: true` with no failures or findings.
