# 2026-07-13 overlay activation policy

## Symptom

A no-blocker Calculator visual probe preserved the physical pointer but changed the frontmost application from Codex to the session overlay's `org.python.python` process. Existing covered-window live tests did not expose it because the blocker and overlay shared the Python bundle identifier and the diagnostic returned only bundle/name.

## Reproduction evidence

An instrumented timeline stayed on the Codex PID through Calculator launch, worker creation, window discovery and initial state. Immediately after the first verified click started the session overlay, the frontmost process changed to the overlay PID and stayed there until overlay stop.

## Root cause

The overlay process used `NSApplicationActivationPolicyAccessory`, which remains activatable. A borderless AppKit window could therefore make the persistent overlay process frontmost. Converting the window to a nonactivating panel alone was insufficient; the process activation policy also had to prohibit activation.

A later full controlled-integration run exposed a second edge: `orderFrontRegardless()` can still displace an active Accessory fixture even when the overlay process is prohibited. The safe combination is therefore both process-level prohibition and ordinary nonactivating-panel ordering.

## Fix

- render through `NSPanel` with `NSWindowStyleMaskNonactivatingPanel`;
- use `NSApplicationActivationPolicyProhibited`;
- show the panel with `orderFront_(None)`, never `orderFrontRegardless()`;
- include `pid` in `frontmost_app` diagnostics;
- compare full frontmost identity, including PID, in live tests;
- add `tests/live/overlay-focus-isolation.test.mjs` without a same-bundle blocker masking the result.

## Verification

The new regression failed before the policy change with Codex PID replaced by the overlay Python PID. The controlled covered-window integration later failed with the inverse transition—its Python blocker PID was replaced by Codex—until `orderFrontRegardless()` was removed. Exact-PID focus isolation now passes with both a regular foreground app and an Accessory foreground fixture. A live screen capture confirms the overlay remains visible while exact frontmost PID is unchanged. Covered Calculator and legacy overlay tests also pass.
