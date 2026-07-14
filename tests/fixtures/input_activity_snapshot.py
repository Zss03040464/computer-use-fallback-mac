from __future__ import annotations

import json
import signal
import time

import Quartz
from AppKit import (
    NSWorkspace,
    NSWorkspaceApplicationKey,
    NSWorkspaceDidActivateApplicationNotification,
)


FOCUS_EVENT_TYPES = {
    Quartz.kCGEventLeftMouseDown,
    Quartz.kCGEventRightMouseDown,
    Quartz.kCGEventOtherMouseDown,
    Quartz.kCGEventKeyDown,
    Quartz.kCGEventFlagsChanged,
}
MONITORED_EVENT_TYPES = FOCUS_EVENT_TYPES | {Quartz.kCGEventMouseMoved}
PHYSICAL_ACTIVATION_EVENT_TYPES = {
    Quartz.kCGEventLeftMouseDown,
    Quartz.kCGEventRightMouseDown,
    Quartz.kCGEventOtherMouseDown,
}
COMMAND_TAB_KEYCODE = 48
ACTIVATION_ATTRIBUTION_SECONDS = 0.75


def main() -> int:
    stopping = False
    reset_requested = False
    last_hid_activation_at = None
    hid_activation_sequence = 0
    attributed_activation_sequence = 0
    summary = {
        "hidMouseMoves": 0,
        "nonHidMouseMoves": 0,
        "hidFocusEvents": 0,
        "hidActivationEvents": 0,
        "focusTransitions": [],
    }

    def stop(_signal_number, _frame) -> None:
        nonlocal stopping
        stopping = True

    def reset(_signal_number, _frame) -> None:
        nonlocal reset_requested
        reset_requested = True

    def observe(_proxy, event_type, event, _context):
        nonlocal last_hid_activation_at, hid_activation_sequence
        source_pid = int(
            Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID)
        )
        source_state = int(
            Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceStateID)
        )
        is_hid = (
            source_pid == 0
            and source_state == Quartz.kCGEventSourceStateHIDSystemState
        )
        if event_type == Quartz.kCGEventMouseMoved:
            key = "hidMouseMoves" if is_hid else "nonHidMouseMoves"
            summary[key] += 1
        elif event_type in FOCUS_EVENT_TYPES and is_hid:
            summary["hidFocusEvents"] += 1
            command_tab = (
                event_type == Quartz.kCGEventKeyDown
                and int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))
                == COMMAND_TAB_KEYCODE
                and bool(Quartz.CGEventGetFlags(event) & Quartz.kCGEventFlagMaskCommand)
            )
            if event_type in PHYSICAL_ACTIVATION_EVENT_TYPES or command_tab:
                summary["hidActivationEvents"] += 1
                hid_activation_sequence += 1
                last_hid_activation_at = time.monotonic()
        return event

    def activated(notification) -> None:
        nonlocal attributed_activation_sequence
        user_info = notification.userInfo() or {}
        application = user_info.get(NSWorkspaceApplicationKey)
        if application is None:
            return
        now = time.monotonic()
        hid_attributed = (
            last_hid_activation_at is not None
            and hid_activation_sequence > attributed_activation_sequence
            and now - last_hid_activation_at <= ACTIVATION_ATTRIBUTION_SECONDS
        )
        if hid_attributed:
            attributed_activation_sequence = hid_activation_sequence
        summary["focusTransitions"].append(
            {
                "pid": int(application.processIdentifier()),
                "bundleId": str(application.bundleIdentifier() or ""),
                "displayName": str(application.localizedName() or ""),
                "hidAttributed": bool(hid_attributed),
            }
        )

    mask = 0
    for event_type in MONITORED_EVENT_TYPES:
        mask |= Quartz.CGEventMaskBit(event_type)
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGHIDEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionListenOnly,
        mask,
        observe,
        None,
    )
    if tap is None:
        raise RuntimeError("Unable to create the read-only HID event monitor")

    source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes
    )
    Quartz.CGEventTapEnable(tap, True)
    workspace_center = NSWorkspace.sharedWorkspace().notificationCenter()
    activation_observer = workspace_center.addObserverForName_object_queue_usingBlock_(
        NSWorkspaceDidActivateApplicationNotification,
        None,
        None,
        activated,
    )
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGUSR1, reset)
    print(json.dumps({"ready": True}), flush=True)
    while not stopping:
        Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.1, False)
        if reset_requested:
            summary["hidMouseMoves"] = 0
            summary["nonHidMouseMoves"] = 0
            summary["hidFocusEvents"] = 0
            summary["hidActivationEvents"] = 0
            summary["focusTransitions"].clear()
            last_hid_activation_at = None
            hid_activation_sequence = 0
            attributed_activation_sequence = 0
            reset_requested = False
            print(json.dumps({"reset": True}), flush=True)
    workspace_center.removeObserver_(activation_observer)
    print(json.dumps({"summary": summary}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
