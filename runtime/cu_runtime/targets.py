from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import plistlib
import time
from typing import Any, Callable, Iterable

from AppKit import NSWorkspace, NSURL
from Quartz import (
    CGWindowListCopyWindowInfo,
    kCGNullWindowID,
    kCGWindowBounds,
    kCGWindowIsOnscreen,
    kCGWindowLayer,
    kCGWindowListExcludeDesktopElements,
    kCGWindowListOptionOnScreenOnly,
    kCGWindowName,
    kCGWindowNumber,
    kCGWindowOwnerName,
    kCGWindowOwnerPID,
)

from .errors import ComputerUseError


@dataclass(frozen=True)
class AppRecord:
    bundle_id: str
    display_name: str
    path: str
    pid: int | None
    running: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundleId": self.bundle_id,
            "displayName": self.display_name,
            "path": self.path,
            "pid": self.pid,
            "running": self.running,
        }


@dataclass(frozen=True)
class TargetWindow:
    app: str
    bundle_id: str
    display_name: str
    path: str
    pid: int
    window_id: int
    title: str
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {
            "app": payload["app"],
            "bundleId": payload["bundle_id"],
            "displayName": payload["display_name"],
            "path": payload["path"],
            "pid": payload["pid"],
            "windowId": payload["window_id"],
            "title": payload["title"],
            "bounds": {
                "x": payload["x"],
                "y": payload["y"],
                "width": payload["width"],
                "height": payload["height"],
            },
        }


class MacWorkspace:
    def __init__(self) -> None:
        self.workspace = NSWorkspace.sharedWorkspace()

    def list_apps(self) -> list[AppRecord]:
        records: dict[str, AppRecord] = {}
        for app in self.workspace.runningApplications() or []:
            bundle_id = app.bundleIdentifier()
            bundle_url = app.bundleURL()
            if not bundle_id or not bundle_url:
                continue
            records[str(bundle_id)] = AppRecord(
                bundle_id=str(bundle_id),
                display_name=str(app.localizedName() or bundle_id),
                path=str(bundle_url.path()),
                pid=int(app.processIdentifier()),
                running=not bool(app.isTerminated()),
            )

        search_roots = [
            Path("/Applications"),
            Path("/System/Applications"),
            Path("/System/Applications/Utilities"),
            Path.home() / "Applications",
        ]
        for root in search_roots:
            if not root.exists():
                continue
            for app_path in root.glob("*.app"):
                info_path = app_path / "Contents" / "Info.plist"
                if not info_path.exists():
                    continue
                try:
                    with info_path.open("rb") as handle:
                        info = plistlib.load(handle)
                except Exception:
                    continue
                bundle_id = info.get("CFBundleIdentifier")
                if not bundle_id or bundle_id in records:
                    continue
                display_name = (
                    info.get("CFBundleDisplayName")
                    or info.get("CFBundleName")
                    or app_path.stem
                )
                records[str(bundle_id)] = AppRecord(
                    bundle_id=str(bundle_id),
                    display_name=str(display_name),
                    path=str(app_path),
                    pid=None,
                    running=False,
                )
        return sorted(records.values(), key=lambda record: record.display_name.casefold())

    def launch_without_activation(self, app: AppRecord) -> None:
        url = NSURL.fileURLWithPath_(app.path)
        options = 0x00000200 | 0x00010000  # without activation | async
        ok, error = self.workspace.launchApplicationAtURL_options_configuration_error_(
            url,
            options,
            {},
            None,
        )
        if not ok:
            raise ComputerUseError(
                "app_not_running",
                f"Could not launch {app.display_name} without activation",
                {"bundleId": app.bundle_id, "error": str(error) if error else None},
            )


def quartz_windows() -> list[dict[str, Any]]:
    options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
    windows = CGWindowListCopyWindowInfo(
        options,
        kCGNullWindowID,
    ) or []
    result: list[dict[str, Any]] = []
    for window in windows:
        bounds = window.get(kCGWindowBounds) or {}
        result.append(
            {
                "windowId": int(window.get(kCGWindowNumber, 0)),
                "pid": int(window.get(kCGWindowOwnerPID, 0)),
                "ownerName": str(window.get(kCGWindowOwnerName, "") or ""),
                "title": str(window.get(kCGWindowName, "") or ""),
                "layer": int(window.get(kCGWindowLayer, 0)),
                "onScreen": bool(window.get(kCGWindowIsOnscreen, True)),
                "bounds": {
                    "x": int(bounds.get("X", 0)),
                    "y": int(bounds.get("Y", 0)),
                    "width": int(bounds.get("Width", 0)),
                    "height": int(bounds.get("Height", 0)),
                },
            }
        )
    return result


class TargetResolver:
    def __init__(
        self,
        workspace: MacWorkspace | Any | None = None,
        window_source: Callable[[], Iterable[dict[str, Any]]] | None = None,
        process_checker: Callable[[int], bool] | None = None,
    ) -> None:
        self.workspace = workspace or MacWorkspace()
        self.window_source = window_source or quartz_windows
        self.process_checker = process_checker or self._process_running

    def list_apps(self) -> list[dict[str, Any]]:
        return [app.to_dict() for app in self.workspace.list_apps()]

    def list_windows(self, app: str | None = None) -> list[dict[str, Any]]:
        target_pid = None
        if app:
            if app.startswith("pid:"):
                try:
                    target_pid = int(app.removeprefix("pid:"))
                except ValueError:
                    raise ComputerUseError("app_not_found", f"Invalid process target: {app}", {"app": app}) from None
            else:
                record = self._match_app(app)
                if record is None:
                    raise ComputerUseError("app_not_found", f"Application not found: {app}", {"app": app})
                if not record.running or record.pid is None:
                    return []
                target_pid = int(record.pid)
        windows = []
        for item in self.window_source():
            bounds = item.get("bounds") or {}
            pid = int(item.get("pid") or 0)
            if target_pid is not None and pid != target_pid:
                continue
            if int(item.get("layer") or 0) != 0 or not bool(item.get("onScreen", True)):
                continue
            width = int(bounds.get("width") or 0)
            height = int(bounds.get("height") or 0)
            if width <= 1 or height <= 1:
                continue
            windows.append(
                {
                    "windowId": int(item.get("windowId") or 0),
                    "pid": pid,
                    "ownerName": str(item.get("ownerName") or ""),
                    "title": str(item.get("title") or ""),
                    "bounds": {
                        "x": int(bounds.get("x") or 0),
                        "y": int(bounds.get("y") or 0),
                        "width": width,
                        "height": height,
                    },
                }
            )
        return windows

    def _match_app(self, identifier: str) -> AppRecord | None:
        normalized = identifier.casefold()
        normalized_path = str(Path(identifier).expanduser()) if identifier.startswith(("/", "~")) else identifier
        for app in self.workspace.list_apps():
            if app.bundle_id.casefold() == normalized:
                return app
            if app.display_name.casefold() == normalized:
                return app
            if app.path == normalized_path:
                return app
        return None

    def resolve(
        self,
        app: str,
        window_id: int | None = None,
        launch: bool = True,
        timeout: float = 5.0,
    ) -> TargetWindow:
        record = None
        if app.startswith("pid:"):
            try:
                explicit_pid = int(app.removeprefix("pid:"))
            except ValueError:
                raise ComputerUseError("app_not_found", f"Invalid process target: {app}", {"app": app}) from None
            pid_windows = self._windows_for_pid(explicit_pid)
            if pid_windows or self.process_checker(explicit_pid):
                owner = str(pid_windows[0].get("ownerName") or app) if pid_windows else f"Process {explicit_pid}"
                record = AppRecord(app, owner, "", explicit_pid, True)
        if record is None:
            record = self._match_app(app)
        if record is None:
            raise ComputerUseError("app_not_found", f"Application not found: {app}", {"app": app})
        if not record.running:
            if not launch:
                raise ComputerUseError(
                    "app_not_running",
                    f"Application is not running: {record.display_name}",
                    {"bundleId": record.bundle_id},
                )
            self.workspace.launch_without_activation(record)

        deadline = time.monotonic() + timeout
        while True:
            current = self._match_app(record.bundle_id) or record
            all_candidates = self._windows_for_pid(int(current.pid or record.pid or 0))
            candidates = all_candidates
            if window_id is not None:
                candidates = [item for item in candidates if item["windowId"] == int(window_id)]
            if candidates and current.pid:
                selected = max(
                    candidates,
                    key=lambda item: item["bounds"]["width"] * item["bounds"]["height"],
                )
                bounds = selected["bounds"]
                return TargetWindow(
                    app=app,
                    bundle_id=current.bundle_id,
                    display_name=current.display_name,
                    path=current.path,
                    pid=int(current.pid),
                    window_id=int(selected["windowId"]),
                    title=str(selected.get("title") or ""),
                    x=int(bounds["x"]),
                    y=int(bounds["y"]),
                    width=int(bounds["width"]),
                    height=int(bounds["height"]),
                )
            if time.monotonic() >= deadline or (window_id is not None and all_candidates):
                break
            time.sleep(0.05)
        raise ComputerUseError(
            "window_not_found",
            f"No matching window for {record.display_name}",
            {"bundleId": record.bundle_id, "windowId": window_id},
        )

    def revalidate(self, target: TargetWindow) -> TargetWindow:
        for window in self._windows_for_pid(target.pid):
            if int(window["windowId"]) == target.window_id:
                return target
        raise ComputerUseError(
            "target_changed",
            "The bound application window no longer exists",
            {"bundleId": target.bundle_id, "pid": target.pid, "windowId": target.window_id},
        )

    def _windows_for_pid(self, pid: int) -> list[dict[str, Any]]:
        result = []
        for item in self.window_source():
            bounds = item.get("bounds") or {}
            if int(item.get("pid") or 0) != pid:
                continue
            if int(item.get("layer") or 0) != 0 or not bool(item.get("onScreen", True)):
                continue
            if int(bounds.get("width") or 0) <= 1 or int(bounds.get("height") or 0) <= 1:
                continue
            result.append(item)
        return result

    @staticmethod
    def _process_running(pid: int) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
