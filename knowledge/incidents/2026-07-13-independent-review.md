# 2026-07-13 independent review

Independent review found several correctness and safety defects before delivery:

- PID events were posted before returning an unverified error.
- AX window mismatch could select the first process window.
- `select_text` exposed semantics that were not implemented and used stale snapshot values.
- live tests could touch or terminate an unproven user process.
- cold bootstrap lacked a cross-process lock.
- the first lock revisions could release while an orphaned installer or stubborn process-group descendant was still running, and undrained output pipes could deadlock bootstrap.
- repeated actions could partially succeed and then replay.
- secure text redaction checked role instead of secure subrole.
- AX text ranges were initially treated as Python character indexes instead of UTF-16 code-unit offsets.
- the configured checkout exposed Python 3.9 grammar and older PyObjC constant compatibility gaps that the newer worktree environment did not reveal.

The fixes disable built-in raw posts, reject ambiguous window matches, implement and verify contextual/cursor selection against current AXValue, translate Python indexes and AX UTF-16 offsets at valid boundaries, isolate and prove live-process ownership, use an OS `flock` command controller that drains bounded output and retains the lock until the complete installer process group is gone, preserve Python 3.9 grammar and old-PyObjC AX constant compatibility, return `partial_delivery`, bound cleanup, and redact `AXSecureTextField` subroles.

## Cursor feedback follow-up

The official-style cursor feedback review found multi-display Y conversion, unbounded full-window compositor layers, missing target PID identity, malformed-state fallback at the origin, overlay startup/orphan cleanup gaps, and Edge process ownership based only on a new PID. These were fixed with primary-screen Quartz/AppKit conversion, compact cursor patches, bundle/PID/window matching, invalid-state suppression, owner-liveness and startup-timeout cleanup, plus an exact Edge profile token.

A later full-gate failure exposed that the legacy one-shot Python helper could not itself own the detached overlay. The first compatibility fix used `os.getppid()`, but review showed a parent-exit race could reparent it to launchd and that global `pgrep` cleanup could signal other sessions. The final implementation passes the persistent Node PID explicitly, rejects PID 0/1, and requires exact script/session/state/PID-file/owner arguments before status or signals. Unit and live regression gates cover both cases.

Regression anchors: `tests/python/test_no_global_targeting.py`, `test_accessibility_snapshot.py`, `test_text_key_actions.py`, `test_click_routing.py`, `test_scroll_drag_actions.py`, `tests/live/`, `tests/packaging/`.
