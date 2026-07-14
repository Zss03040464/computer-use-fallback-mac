# 2026-07-13 setup focus interruption

## Symptom

While the user was typing in Codex, live verification could briefly activate another application and then restore Codex. The final foreground PID looked correct, but the temporary transition interrupted the active input method. Two red windows titled `CU Blocker Harness` were also visible during concurrent tests.

## Root cause

Production application launch already used `NSWorkspaceLaunchWithoutActivation | NSWorkspaceLaunchAsync` and did not reproduce the activation. The focus-taking path was test infrastructure:

- the former Edge fixture raised its window, wrote focused Accessibility attributes, posted Return to the Edge PID, then reactivated the previous application;
- focus monitoring started after application/blocker setup;
- the assertion compared final foreground state and could miss activate-and-restore transitions;
- ordinary AppKit harness setup could itself activate a test process.

The paired red windows were the two blocker occluders used by the concurrent target test. They existed to detect accidental visible-desktop clicking and were not virtual cursors.

## Fix

- Capture every workspace activation notification from before UI setup through cleanup.
- Reject protected PIDs and all unattributed transitions, including temporary transitions whose final PID is restored.
- Treat only a physical mouse-down or Command-Tab as an activation gesture; ordinary typing cannot excuse a transition.
- Remove the Edge raise/focus/key/restore fixture. Test only a reversible new-tab add/remove action in an Edge window that already exists; skip when Edge is not running.
- Build target/blocker fixtures as nonactivating panels, order them normally, then use Prohibited activation policy.
- Render blockers at 2% opacity by default; keep `CU_BLOCKER_VISIBLE=1` for explicit red diagnostics.

## Prevention

The fixture purity test bans `AXRaise`, focused-attribute writes, PID-targeted raw keys, application activation/restore and `orderFrontRegardless`. Production launch options are pinned by unit test, and a native Chess error-path test proves launch-time nonactivation even when no application window becomes available.
