from __future__ import annotations

import json
import sys


def frontmost_app() -> dict:
    from AppKit import NSWorkspace

    application = NSWorkspace.sharedWorkspace().frontmostApplication()
    if application is None:
        return {"pid": 0, "name": None, "bundleId": None}
    return {
        "pid": int(application.processIdentifier()),
        "name": str(application.localizedName() or ""),
        "bundleId": str(application.bundleIdentifier() or ""),
    }


def physical_cursor_position() -> dict:
    import Quartz

    location = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return {"x": float(location.x), "y": float(location.y)}


def list_windows() -> list[dict]:
    import Quartz

    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
    result = []
    for window in windows:
        bounds = window.get(Quartz.kCGWindowBounds) or {}
        result.append(
            {
                "windowId": int(window.get(Quartz.kCGWindowNumber, 0)),
                "pid": int(window.get(Quartz.kCGWindowOwnerPID, 0)),
                "owner": str(window.get(Quartz.kCGWindowOwnerName, "")),
                "title": str(window.get(Quartz.kCGWindowName, "")),
                "bounds": {
                    "x": float(bounds.get("X", 0)),
                    "y": float(bounds.get("Y", 0)),
                    "width": float(bounds.get("Width", 0)),
                    "height": float(bounds.get("Height", 0)),
                },
            }
        )
    return result


COMMANDS = {
    "frontmost_app": frontmost_app,
    "physical_cursor_position": physical_cursor_position,
    "list_windows": list_windows,
}


def main() -> int:
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command not in COMMANDS:
        print(json.dumps({"ok": False, "error": "unsupported probe"}))
        return 2
    print(json.dumps({"ok": True, "result": COMMANDS[command]()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
