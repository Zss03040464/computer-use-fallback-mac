# Background control verification

The primary acceptance test places a separate blocker over a controlled AppKit target. It checks target state, blocker state, frontmost application and physical cursor before and after every action family. A second test runs two workers and two targets concurrently.

Monitoring begins before target and blocker launch. A read-only HID event tap and workspace activation trace cover the entire interval: exact pointer equality remains mandatory without hardware movement, every mouse movement must be HID-originated, and any target, blocker or overlay activation fails even if focus is later restored. Ordinary typing never attributes focus movement; only a physical mouse-down or Command-Tab can attribute an unrelated application transition.

The blocker is a hit-test oracle, not product UI or the virtual cursor. Target and blocker fixtures are nonactivating `NSPanel` instances. Blockers default to 2% opacity; `CU_BLOCKER_VISIBLE=1` restores the red diagnostic appearance.

The native matrix creates isolated processes and profiles. Cleanup is allowed only after a PID is proven new relative to the pre-test process set and its executable matches the expected application. Edge is never launched by the gate; when already running, one background tab is added and removed reversibly. If Edge is absent, that optional check skips without mutation.

Cursor feedback uses the same covered AppKit harness and native state-action-state flow. After an indexed click, the next target-window PNG must report `cursorFeedback.drawn=true` at the scaled element center while blocker state, frontmost application and physical pointer remain unchanged. Two-worker integration asserts distinct target-bound image points.

Production launch is pinned to `NSWorkspaceLaunchWithoutActivation | NSWorkspaceLaunchAsync` (`0x00010200`). A native error-path check proves a newly launched process never enters the activation trace when no window is available.

Overlay lifecycle verification rejects invalid owners, proves one session cannot signal another and checks stable status, updates and cleanup. A separate exact-PID live check proves the click-through overlay never becomes frontmost.

The clean-copy smoke removes local dependencies, runs concurrent bootstrap clients through an OS `flock`, validates the atomic requirements stamp, then verifies a subsequent MCP process can connect through the SDK.

Test anchors: `tests/python/test_cursor_feedback.py`, `tests/python/test_cursor_specimen.py`, `tests/python/test_no_global_targeting.py`, `tests/python/test_targets.py`, `tests/fixtures/input-activity.mjs`, `tests/fixtures/input_activity_snapshot.py`, `tests/fixtures/background_input_harness.py`, `tests/integration/`, `tests/live/native-app-matrix.test.mjs`, `tests/live/overlay-focus-isolation.test.mjs`, `tests/packaging/clean-copy-smoke.mjs`.
