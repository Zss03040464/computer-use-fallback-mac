# Extracted from NanmiCoder/cc-haha runtime/mac_helper.py
# Purpose: macOS helper for screenshot, mouse, keyboard, clipboard, window, and permission operations.
# Local modifications should be minimal and documented in SOURCE_MAP.md.

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import signal
import shlex
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import mss
from AppKit import NSWorkspace, NSPasteboard, NSPasteboardTypeString, NSURL
from PIL import Image
from Quartz import (
    CGEventCreate,
    CGEventCreateMouseEvent,
    CGEventCreateScrollWheelEvent,
    CGEventGetLocation,
    CGEventPostToPid,
    CGEventSetIntegerValueField,
    CGEventSetLocation,
    CGDisplayBounds,
    CGDisplayIsMain,
    CGDisplayModeGetPixelHeight,
    CGDisplayModeGetPixelWidth,
    CGDisplayPixelsHigh,
    CGDisplayPixelsWide,
    CGGetActiveDisplayList,
    CGMainDisplayID,
    CGWindowListCopyWindowInfo,
    CGRectContainsPoint,
    CGRectIntersection,
    CGPointMake,
    CGPreflightScreenCaptureAccess,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseDragged,
    kCGEventLeftMouseUp,
    kCGEventOtherMouseDown,
    kCGEventOtherMouseDragged,
    kCGEventOtherMouseUp,
    kCGEventRightMouseDown,
    kCGEventRightMouseDragged,
    kCGEventRightMouseUp,
    kCGAnnotatedSessionEventTap,
    kCGHIDEventTap,
    kCGMouseButtonCenter,
    kCGMouseButtonLeft,
    kCGMouseButtonRight,
    kCGMouseEventClickState,
    kCGScrollEventUnitLine,
    kCGNullWindowID,
    kCGWindowBounds,
    kCGWindowIsOnscreen,
    kCGWindowLayer,
    kCGWindowListExcludeDesktopElements,
    kCGWindowListOptionOnScreenOnly,
    kCGWindowName,
    kCGWindowOwnerName,
    kCGWindowOwnerPID,
)

try:
    import Vision
    from Foundation import NSURL
    from Quartz import CGImageSourceCreateWithURL, CGImageSourceCreateImageAtIndex
    vision_available = True
except ImportError:
    vision_available = False

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("PYAUTOGUI_HIDE_SUPPORT_PROMPT", "1")

import pyautogui  # noqa: E402

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

try:
    import ApplicationServices as AX  # noqa: E402
    accessibility_services_available = True
except ImportError:
    AX = None
    accessibility_services_available = False

try:
    from cu_runtime.cursor_feedback import CURSOR_STYLE, composite_cursor_image
except ModuleNotFoundError:
    from runtime.cu_runtime.cursor_feedback import CURSOR_STYLE, composite_cursor_image

VIRTUAL_MOUSE_STATE_PATH = Path(__file__).with_name("virtual_mouse_state.json")
VIRTUAL_CURSOR_OVERLAY_SCRIPT = Path(__file__).with_name("virtual_cursor_overlay.py")
VIRTUAL_CURSOR_OVERLAY_PID_PATH = Path(__file__).with_name("virtual_cursor_overlay.pid")
VIRTUAL_CURSOR_OVERLAY_LOCK_PATH = Path(__file__).with_name("virtual_cursor_overlay.lock")
LEGACY_OVERLAY_OWNER_PID: int | None = None
VIRTUAL_MOUSE_EVENT_TAP = kCGAnnotatedSessionEventTap
VIRTUAL_CURSOR_STYLE = CURSOR_STYLE

KEY_MAP = {
    "a": "a",
    "b": "b",
    "c": "c",
    "d": "d",
    "e": "e",
    "f": "f",
    "g": "g",
    "h": "h",
    "i": "i",
    "j": "j",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "o": "o",
    "p": "p",
    "q": "q",
    "r": "r",
    "s": "s",
    "t": "t",
    "u": "u",
    "v": "v",
    "w": "w",
    "x": "x",
    "y": "y",
    "z": "z",
    "0": "0",
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "6": "6",
    "7": "7",
    "8": "8",
    "9": "9",
    "cmd": "command",
    "command": "command",
    "meta": "command",
    "super": "command",
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "option",
    "option": "option",
    "opt": "option",
    "fn": "fn",
    "escape": "esc",
    "esc": "esc",
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "space": "space",
    "backspace": "backspace",
    "delete": "delete",
    "forwarddelete": "delete",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "capslock": "capslock",
    "f1": "f1",
    "f2": "f2",
    "f3": "f3",
    "f4": "f4",
    "f5": "f5",
    "f6": "f6",
    "f7": "f7",
    "f8": "f8",
    "f9": "f9",
    "f10": "f10",
    "f11": "f11",
    "f12": "f12",
    "-": "minus",
    "=": "equals",
    "[": "[",
    "]": "]",
    "\\": "\\",
    ";": ";",
    "'": "'",
    ",": ",",
    ".": ".",
    "/": "/",
    "`": "`",
}

APPLE_KEY_CODES = {
    "enter": 36,
    "tab": 48,
    "space": 49,
    "backspace": 51,
    "esc": 53,
    "delete": 117,
    "home": 115,
    "end": 119,
    "pageup": 116,
    "pagedown": 121,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
}


def normalize_key(name: str) -> str:
    key = name.strip().lower()
    if key not in KEY_MAP:
        raise ValueError(f"Unsupported key: {name}")
    return KEY_MAP[key]


current_command = "unknown"
current_payload = {}

def log_operation(command: str, payload: dict[str, Any], result: Any = None, error: Any = None) -> None:
    log_path = Path(__file__).parent / "computer_use.log"
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "command": command,
        "payload": payload,
        "result": result,
        "error": error
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def json_output(payload: dict[str, Any]) -> None:
    if payload.get("ok"):
        log_operation(current_command, current_payload, result=payload.get("result"))
    else:
        log_operation(current_command, current_payload, error=payload.get("error"))
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def error_output(message: str, code: str = "runtime_error") -> None:
    json_output({"ok": False, "error": {"code": code, "message": message}})


def perform_ocr(image_path: str) -> list[dict[str, Any]]:
    if not vision_available:
        return []
    url = NSURL.fileURLWithPath_(image_path)
    image_source = CGImageSourceCreateWithURL(url, None)
    if not image_source:
        return []
    cg_image = CGImageSourceCreateImageAtIndex(image_source, 0, None)
    if not cg_image:
        return []

    results = []

    def handler(request, error):
        if error:
            return
        observations = request.results()
        if not observations:
            return
        for obs in observations:
            candidates = obs.topCandidates_(1)
            if not candidates:
                continue
            text = candidates[0].string()
            bbox = obs.boundingBox()
            results.append({
                "text": text,
                "confidence": float(obs.confidence()),
                "boundingBox": {
                    "x": float(bbox.origin.x),
                    "y": float(bbox.origin.y),
                    "width": float(bbox.size.width),
                    "height": float(bbox.size.height)
                }
            })

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(handler)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)

    handler_obj = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    success, error = handler_obj.performRequests_error_([request], None)
    if not success:
        return []

    return results


def perform_ocr_on_display(display_id: int | None = None) -> list[dict[str, Any]]:
    display = choose_display(display_id)
    res = capture_display(display_id)
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    temp_path = temp_file.name
    temp_file.close()
    try:
        with open(temp_path, "wb") as f:
            f.write(base64.b64decode(res["base64"]))

        ocr_raw = perform_ocr(temp_path)

        scale = display["scaleFactor"]
        img_width = res["width"]
        img_height = res["height"]

        converted = []
        for item in ocr_raw:
            bbox = item["boundingBox"]
            px = bbox["x"] * img_width
            py = (1.0 - bbox["y"] - bbox["height"]) * img_height
            pw = bbox["width"] * img_width
            ph = bbox["height"] * img_height

            lx = px / scale + display["originX"]
            ly = py / scale + display["originY"]
            lw = pw / scale
            lh = ph / scale

            converted.append({
                "text": item["text"],
                "confidence": item["confidence"],
                "bounds": {
                    "x": int(lx),
                    "y": int(ly),
                    "width": int(lw),
                    "height": int(lh),
                    "px": int(px),
                    "py": int(py),
                    "pw": int(pw),
                    "ph": int(ph)
                }
            })
        return converted
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass


def detect_and_close_popups(display_id: int | None = None) -> dict[str, Any]:
    ocr_results = perform_ocr_on_display(display_id)
    keywords = {"我知道了", "确定", "确认", "关闭", "同意", "取消", "cancel", "ok", "close", "dismiss", "agree"}
    closed_count = 0
    actions = []
    for item in ocr_results:
        text_clean = item["text"].strip().lower()
        matched = False
        if text_clean in keywords:
            matched = True
        elif text_clean in {"x", "×"} and item["bounds"]["width"] < 40 and item["bounds"]["height"] < 40:
            matched = True

        if matched:
            bx = item["bounds"]["x"] + item["bounds"]["width"] / 2
            by = item["bounds"]["y"] + item["bounds"]["height"] / 2
            click(int(bx), int(by), "left", 1, None)
            actions.append({"text": item["text"], "x": bx, "y": by})
            closed_count += 1
            time.sleep(0.5)

    return {"closed": closed_count > 0, "closedCount": closed_count, "actions": actions}


def detect_captcha(display_id: int | None = None) -> dict[str, Any]:
    ocr_results = perform_ocr_on_display(display_id)
    captcha_keywords = {"验证码", "安全验证", "滑动滑块", "人机身份验证", "hcaptcha", "recaptcha", "极验", "geetest", "拼图"}
    detected = False
    matched_texts = []
    for item in ocr_results:
        text_clean = item["text"].strip().lower()
        for kw in captcha_keywords:
            if kw in text_clean:
                detected = True
                matched_texts.append(item["text"])
                break
    return {"isCaptcha": detected, "matchedTexts": matched_texts}


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value not in {"0", "false", "False", ""}


def run_osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "osascript failed")
    return result.stdout.strip()


def applescript_modifier(name: str) -> str:
    if name == "command":
        return "command down"
    if name == "option":
        return "option down"
    if name == "shift":
        return "shift down"
    if name == "ctrl":
        return "control down"
    if name == "fn":
        return "fn down"
    raise ValueError(f"Unsupported AppleScript modifier: {name}")


def send_keystroke_via_osascript(character: str, modifiers: list[str] | None = None) -> None:
    escaped = character.replace("\\", "\\\\").replace('"', '\\"')
    if modifiers:
        modifier_expr = ", ".join(applescript_modifier(m) for m in modifiers)
        script = (
            'tell application "System Events" to keystroke '
            f'"{escaped}" using {{{modifier_expr}}}'
        )
    else:
        script = f'tell application "System Events" to keystroke "{escaped}"'
    run_osascript(script)


def send_keycode_via_osascript(key_code: int, modifiers: list[str] | None = None) -> None:
    if modifiers:
        modifier_expr = ", ".join(applescript_modifier(m) for m in modifiers)
        script = (
            'tell application "System Events" to key code '
            f"{int(key_code)} using {{{modifier_expr}}}"
        )
    else:
        script = f'tell application "System Events" to key code {int(key_code)}'
    run_osascript(script)


def get_displays() -> list[dict[str, Any]]:
    max_displays = 32
    err, active, count = CGGetActiveDisplayList(max_displays, None, None)
    displays: list[dict[str, Any]] = []
    main_id = CGMainDisplayID()
    display_ids = list(active[:count]) if err == 0 and count else [main_id]
    seen_display_ids: set[int] = set()
    for idx, display_id in enumerate(display_ids):
        display_id = int(display_id)
        if display_id in seen_display_ids:
            continue
        seen_display_ids.add(display_id)
        bounds = CGDisplayBounds(display_id)
        mode = None
        try:
            from Quartz import CGDisplayCopyDisplayMode
            mode = CGDisplayCopyDisplayMode(display_id)
        except Exception:
            mode = None
        physical_width = int(CGDisplayPixelsWide(display_id))
        physical_height = int(CGDisplayPixelsHigh(display_id))
        logical_width = int(bounds.size.width)
        logical_height = int(bounds.size.height)
        if logical_width <= 0 or logical_height <= 0:
            continue
        if mode is not None:
            mode_w = int(CGDisplayModeGetPixelWidth(mode))
            mode_h = int(CGDisplayModeGetPixelHeight(mode))
            physical_width = mode_w or physical_width
            physical_height = mode_h or physical_height
        scale_factor = physical_width / logical_width if logical_width else 1
        name = f"Display {idx + 1}"
        displays.append(
            {
                "id": int(display_id),
                "displayId": int(display_id),
                "width": logical_width,
                "height": logical_height,
                "scaleFactor": scale_factor,
                "originX": int(bounds.origin.x),
                "originY": int(bounds.origin.y),
                "isPrimary": bool(display_id == main_id or CGDisplayIsMain(display_id)),
                "name": name,
                "label": name,
            }
        )
    return displays


def choose_display(display_id: int | None) -> dict[str, Any]:
    displays = get_displays()
    if not displays:
        raise RuntimeError("No active displays found")
    if display_id is None:
        for display in displays:
            if display["isPrimary"]:
                return display
        return displays[0]
    for display in displays:
        if display["displayId"] == display_id or display["id"] == display_id:
            return display
    raise RuntimeError(f"Unknown display: {display_id}")


def display_for_logical_point(x: int, y: int, display_id: int | None = None) -> dict[str, Any]:
    if display_id is not None:
        return choose_display(display_id)
    for display in get_displays():
        if (
            display["originX"] <= x < display["originX"] + display["width"]
            and display["originY"] <= y < display["originY"] + display["height"]
        ):
            return display
    return choose_display(None)


def ensure_screen_recording_permission() -> None:
    pass


def draw_virtual_cursor_overlay(
    image: Image.Image,
    display: dict[str, Any],
    cursor_state: dict[str, Any] | None = None,
    region: dict[str, int] | None = None,
) -> dict[str, Any]:
    state = cursor_state or load_virtual_mouse_state()
    vx = int(state["x"])
    vy = int(state["y"])
    scale = float(display.get("scaleFactor") or 1.0)

    if region:
        left = int(region["left"])
        top = int(region["top"])
        width = int(region["width"])
        height = int(region["height"])
    else:
        left = int(display["originX"])
        top = int(display["originY"])
        width = int(display["width"])
        height = int(display["height"])

    if vx < left or vy < top or vx >= left + width or vy >= top + height:
        return {"drawn": False, "style": VIRTUAL_CURSOR_STYLE, "x": vx, "y": vy}

    image_scale_x = image.width / width if width else scale
    image_scale_y = image.height / height if height else scale
    px = (vx - left) * image_scale_x
    py = (vy - top) * image_scale_y
    cursor_scale = max(1.0, min(image_scale_x, image_scale_y))

    base, _ = composite_cursor_image(
        image,
        int(round(px)),
        int(round(py)),
        cursor_scale,
        0.0,
    )
    image.paste(base.convert(image.mode))

    return {
        "drawn": True,
        "style": VIRTUAL_CURSOR_STYLE,
        "x": vx,
        "y": vy,
        "pixelX": int(round(px)),
        "pixelY": int(round(py)),
        "scale": cursor_scale,
    }


def capture_display(
    display_id: int | None,
    resize: tuple[int, int] | None = None,
    zoom_factor: float | None = None,
    highlight_point: dict[str, float] | None = None,
    highlight_radius: int | None = None,
    show_virtual_cursor: bool = True,
) -> dict[str, Any]:
    ensure_screen_recording_permission()
    display = choose_display(display_id)
    monitor = {
        "left": display["originX"],
        "top": display["originY"],
        "width": display["width"],
        "height": display["height"],
    }
    with mss.mss() as sct:
        raw = sct.grab(monitor)
        image = Image.frombytes("RGB", raw.size, raw.rgb)

    cursor_overlay = {"drawn": False, "style": VIRTUAL_CURSOR_STYLE}
    if show_virtual_cursor:
        cursor_overlay = draw_virtual_cursor_overlay(image, display)

    if highlight_point:
        from PIL import ImageDraw
        scale = display["scaleFactor"]
        px = (highlight_point["x"] - display["originX"]) * scale
        py = (highlight_point["y"] - display["originY"]) * scale
        r = highlight_radius or 15
        draw = ImageDraw.Draw(image)
        draw.ellipse([px - r, py - r, px + r, py + r], outline="red", width=4)

    if zoom_factor and zoom_factor != 1.0:
        new_size = (int(image.width * zoom_factor), int(image.height * zoom_factor))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    elif resize:
        image = image.resize(resize, Image.Resampling.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=75, optimize=True)
    base64_data = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "base64": base64_data,
        "width": image.width,
        "height": image.height,
        "displayWidth": display["width"],
        "displayHeight": display["height"],
        "displayId": display["displayId"],
        "originX": display["originX"],
        "originY": display["originY"],
        "display": display,
        "cursorOverlay": cursor_overlay,
    }


def requested_resize(payload: dict[str, Any], source_width: int, source_height: int) -> tuple[int, int] | None:
    target_width = payload.get("targetWidth")
    target_height = payload.get("targetHeight")
    if not target_width and not target_height:
        return None

    if target_width and target_height:
        return (int(target_width), int(target_height))
    if target_width:
        width = int(target_width)
        height = max(1, round(width * source_height / source_width))
        return (width, height)

    height = int(target_height)
    width = max(1, round(height * source_width / source_height))
    return (width, height)


def capture_region(
    region: dict[str, int],
    resize: tuple[int, int] | None = None,
    zoom_factor: float | None = None,
    show_virtual_cursor: bool = True,
) -> dict[str, Any]:
    ensure_screen_recording_permission()
    with mss.mss() as sct:
        raw = sct.grab(region)
        image = Image.frombytes("RGB", raw.size, raw.rgb)

    cursor_overlay = {"drawn": False, "style": VIRTUAL_CURSOR_STYLE}
    if show_virtual_cursor:
        cursor_state = load_virtual_mouse_state()
        display = display_for_logical_point(int(cursor_state["x"]), int(cursor_state["y"]))
        cursor_overlay = draw_virtual_cursor_overlay(image, display, cursor_state, region)

    if zoom_factor and zoom_factor != 1.0:
        new_size = (int(image.width * zoom_factor), int(image.height * zoom_factor))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    elif resize:
        image = image.resize(resize, Image.Resampling.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=75, optimize=True)
    base64_data = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "base64": base64_data,
        "width": image.width,
        "height": image.height,
        "cursorOverlay": cursor_overlay,
    }


def list_windows() -> list[dict[str, Any]]:
    windows = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
        kCGNullWindowID,
    )
    out: list[dict[str, Any]] = []
    for window in windows or []:
        if int(window.get(kCGWindowLayer, 0)) != 0:
            continue
        if not bool(window.get(kCGWindowIsOnscreen, True)):
            continue
        bounds = window.get(kCGWindowBounds) or {}
        width = int(bounds.get("Width", 0))
        height = int(bounds.get("Height", 0))
        if width <= 1 or height <= 1:
            continue
        out.append(
            {
                "ownerName": window.get(kCGWindowOwnerName, "") or "",
                "title": window.get(kCGWindowName, "") or "",
                "pid": int(window.get(kCGWindowOwnerPID, 0)),
                "layer": int(window.get(kCGWindowLayer, 0)),
                "bounds": {
                    "x": int(bounds.get("X", 0)),
                    "y": int(bounds.get("Y", 0)),
                    "width": width,
                    "height": height,
                },
            }
        )
    return out


def bundle_id_to_app(bundle_id: str):
    return NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(bundle_id)


def installed_apps() -> list[dict[str, Any]]:
    search_roots = [
        Path("/Applications"),
        Path.home() / "Applications",
        Path("/System/Applications"),
        Path("/System/Applications/Utilities"),
    ]
    results: dict[str, dict[str, Any]] = {}
    workspace = NSWorkspace.sharedWorkspace()
    for root in search_roots:
        if not root.exists():
            continue
        for app in root.rglob("*.app"):
            try:
                bundle = workspace.bundleIdentifierForURL_(NSURL.fileURLWithPath_(str(app)))
            except Exception:
                bundle = None
            if not bundle:
                try:
                    url = workspace.URLForApplicationWithBundleIdentifier_(str(app))
                    bundle = workspace.bundleIdentifierForURL_(url) if url else None
                except Exception:
                    bundle = None
            info_plist = app / "Contents/Info.plist"
            display_name = app.stem
            if info_plist.exists():
                try:
                    import plistlib
                    with info_plist.open("rb") as f:
                        plist = plistlib.load(f)
                    bundle = bundle or plist.get("CFBundleIdentifier")
                    display_name = plist.get("CFBundleDisplayName") or plist.get("CFBundleName") or display_name
                except Exception:
                    pass
            if not bundle or bundle in results:
                continue
            results[bundle] = {
                "bundleId": str(bundle),
                "displayName": str(display_name),
                "path": str(app),
            }
    return sorted(results.values(), key=lambda item: item["displayName"].lower())


def running_apps() -> list[dict[str, Any]]:
    apps = []
    seen = set()
    for app in NSWorkspace.sharedWorkspace().runningApplications() or []:
        bundle_id = app.bundleIdentifier()
        if not bundle_id or bundle_id in seen:
            continue
        seen.add(bundle_id)
        name = app.localizedName() or bundle_id
        apps.append({"bundleId": str(bundle_id), "displayName": str(name)})
    return sorted(apps, key=lambda item: item["displayName"].lower())


def app_display_name(bundle_id: str) -> str | None:
    for app in NSWorkspace.sharedWorkspace().runningApplications() or []:
        if app.bundleIdentifier() == bundle_id:
            return str(app.localizedName() or bundle_id)
    for app in installed_apps():
        if app["bundleId"] == bundle_id:
            return str(app["displayName"])
    return None


def frontmost_app() -> dict[str, Any] | None:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if not app:
        return None
    bundle_id = app.bundleIdentifier()
    if not bundle_id:
        return None
    return {
        "bundleId": str(bundle_id),
        "displayName": str(app.localizedName() or bundle_id),
        "pid": int(app.processIdentifier()),
    }


def app_under_point(x: int, y: int) -> dict[str, str] | None:
    point = CGPointMake(x, y)
    running_by_name = {
        str(app.localizedName() or app.bundleIdentifier()): str(app.bundleIdentifier())
        for app in NSWorkspace.sharedWorkspace().runningApplications() or []
        if app.bundleIdentifier()
    }
    for window in list_windows():
        bounds = window["bounds"]
        rect = ((bounds["x"], bounds["y"]), (bounds["width"], bounds["height"]))
        if CGRectContainsPoint(rect, point):
            owner = window["ownerName"]
            bundle = running_by_name.get(owner)
            if bundle:
                return {"bundleId": bundle, "displayName": str(owner)}
    return None


def find_window_displays(bundle_ids: list[str]) -> list[dict[str, Any]]:
    if not bundle_ids:
        return []
    displays = get_displays()
    names_by_bundle = {
        bundle_id: app_display_name(bundle_id) or bundle_id for bundle_id in bundle_ids
    }
    windows = list_windows()
    result = []
    for bundle_id in bundle_ids:
        target_name = names_by_bundle.get(bundle_id)
        display_ids: set[int] = set()
        for window in windows:
            owner = window["ownerName"]
            if not owner:
                continue
            if target_name and owner != target_name:
                continue
            if not target_name and owner != bundle_id:
                continue
            wx = window["bounds"]["x"]
            wy = window["bounds"]["y"]
            ww = window["bounds"]["width"]
            wh = window["bounds"]["height"]
            window_rect = ((wx, wy), (ww, wh))
            for display in displays:
                display_rect = ((display["originX"], display["originY"]), (display["width"], display["height"]))
                intersection = CGRectIntersection(window_rect, display_rect)
                if intersection.size.width > 0 and intersection.size.height > 0:
                    display_ids.add(int(display["displayId"]))
        result.append({"bundleId": bundle_id, "displayIds": sorted(display_ids)})
    return result


def open_app(bundle_id: str) -> None:
    url = bundle_id_to_app(bundle_id)
    if not url:
        raise RuntimeError(f"App not found for bundle identifier: {bundle_id}")
    ok, err = NSWorkspace.sharedWorkspace().launchApplicationAtURL_options_configuration_error_(url, 0, {}, None)
    if not ok:
        raise RuntimeError(str(err) if err else f"Failed to open app {bundle_id}")


def read_clipboard() -> str:
    pb = NSPasteboard.generalPasteboard()
    value = pb.stringForType_(NSPasteboardTypeString)
    return "" if value is None else str(value)


def write_clipboard(text: str) -> None:
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def paste_clipboard() -> None:
    send_keystroke_via_osascript("v", ["command"])


def ax_attribute(element, attribute: str):
    if not accessibility_services_available or element is None:
        return None
    try:
        err, value = AX.AXUIElementCopyAttributeValue(element, attribute, None)
        if err == 0:
            return value
    except Exception:
        return None
    return None


def ax_actions(element) -> list[str]:
    if not accessibility_services_available or element is None:
        return []
    try:
        err, actions = AX.AXUIElementCopyActionNames(element, None)
        if err == 0:
            return [str(action) for action in actions]
    except Exception:
        return []
    return []


def ax_element_at_position(x: int, y: int):
    if not accessibility_services_available:
        return None
    try:
        system = AX.AXUIElementCreateSystemWide()
        err, element = AX.AXUIElementCopyElementAtPosition(system, int(x), int(y), None)
        return element if err == 0 else None
    except Exception:
        return None


def ax_find_descendant(element, role: str, depth: int = 0, max_depth: int = 5):
    if element is None or depth > max_depth:
        return None
    if ax_attribute(element, AX.kAXRoleAttribute) == role:
        return element
    for child in ax_attribute(element, AX.kAXChildrenAttribute) or []:
        found = ax_find_descendant(child, role, depth + 1, max_depth)
        if found is not None:
            return found
    return None


def ax_focused_element():
    if not accessibility_services_available:
        return None
    try:
        system = AX.AXUIElementCreateSystemWide()
        err, element = AX.AXUIElementCopyAttributeValue(system, AX.kAXFocusedUIElementAttribute, None)
        return element if err == 0 else None
    except Exception:
        return None


def ax_find_text_element_nearby(element):
    if not accessibility_services_available or element is None:
        return None
    # 1. Check current element and its parent chain
    curr = element
    while curr is not None:
        role = ax_attribute(curr, AX.kAXRoleAttribute)
        if role in {AX.kAXTextFieldRole, AX.kAXTextAreaRole}:
            return curr
        curr = ax_attribute(curr, AX.kAXParentAttribute)
    # 2. Check descendant elements
    found = ax_find_descendant(element, AX.kAXTextFieldRole)
    if found is not None:
        return found
    found = ax_find_descendant(element, AX.kAXTextAreaRole)
    if found is not None:
        return found
    return None


def ax_text_target_from_virtual_cursor():
    if not accessibility_services_available:
        return None
    vx, vy = get_virtual_mouse_position()
    element = ax_element_at_position(vx, vy)
    return ax_find_text_element_nearby(element)


def ax_set_text(text: str) -> bool:
    if not accessibility_services_available:
        return False
    # Priority: Prefer virtual cursor target (isolated input) over system wide focus
    candidates = [
        ax_text_target_from_virtual_cursor(),
        ax_focused_element(),
    ]
    for element in candidates:
        if element is None:
            continue
        role = ax_attribute(element, AX.kAXRoleAttribute)
        if role not in {AX.kAXTextFieldRole, AX.kAXTextAreaRole}:
            continue
        try:
            err = AX.AXUIElementSetAttributeValue(element, AX.kAXValueAttribute, text)
            if err == 0:
                return True
        except Exception:
            continue
    return False


def ax_confirm_text_target() -> bool:
    if not accessibility_services_available:
        return False
    # Priority: Prefer virtual cursor target over system wide focus
    candidates = [
        ax_text_target_from_virtual_cursor(),
        ax_focused_element(),
    ]
    for element in candidates:
        if element is None:
            continue
        if AX.kAXConfirmAction in ax_actions(element):
            try:
                if AX.AXUIElementPerformAction(element, AX.kAXConfirmAction) == 0:
                    return True
            except Exception:
                continue
    return False


def ax_press_at_position(x: int, y: int) -> bool:
    element = ax_element_at_position(x, y)
    while element is not None:
        if AX.kAXPressAction in ax_actions(element):
            try:
                if AX.AXUIElementPerformAction(element, AX.kAXPressAction) == 0:
                    return True
            except Exception:
                pass
        element = ax_attribute(element, AX.kAXParentAttribute)
    return False


def detect_screen_recording_permission() -> bool | None:
    try:
        if CGPreflightScreenCaptureAccess():
            return True
    except Exception:
        pass

    try:
        windows = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID,
        )
    except Exception:
        return None

    eligible_windows = 0
    for window in windows or []:
        if int(window.get(kCGWindowLayer, 0)) != 0:
            continue
        if not bool(window.get(kCGWindowIsOnscreen, True)):
            continue

        bounds = window.get(kCGWindowBounds) or {}
        width = int(bounds.get("Width", 0))
        height = int(bounds.get("Height", 0))
        if width <= 1 or height <= 1:
            continue

        eligible_windows += 1
        if (window.get(kCGWindowName, "") or "").strip():
            return True

    if eligible_windows > 0:
        return False
    return None


def detect_accessibility_permission() -> bool:
    framework_path = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    try:
        application_services = ctypes.CDLL(framework_path)
        application_services.AXIsProcessTrusted.restype = ctypes.c_bool
        application_services.AXIsProcessTrusted.argtypes = []
        return bool(application_services.AXIsProcessTrusted())
    except Exception:
        return False


def check_permissions() -> dict[str, bool | None]:
    accessibility = detect_accessibility_permission()
    screen_recording = detect_screen_recording_permission()
    return {
        "accessibility": accessibility,
        "screenRecording": screen_recording,
    }


def physical_cursor_position() -> tuple[int, int]:
    event = CGEventCreate(None)
    location = CGEventGetLocation(event)
    return int(location.x), int(location.y)


def load_virtual_mouse_state() -> dict[str, Any]:
    try:
        data = json.loads(VIRTUAL_MOUSE_STATE_PATH.read_text(encoding="utf-8"))
        return {
            "x": int(data["x"]),
            "y": int(data["y"]),
            "button": data.get("button"),
        }
    except Exception:
        x, y = physical_cursor_position()
        state = {"x": x, "y": y, "button": None}
        save_virtual_mouse_state(state)
        return state


def save_virtual_mouse_state(state: dict[str, Any]) -> None:
    safe_state = {
        "x": int(state["x"]),
        "y": int(state["y"]),
        "button": state.get("button"),
        "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    VIRTUAL_MOUSE_STATE_PATH.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def legacy_overlay_command_matches(command: str) -> bool:
    owner_pid = LEGACY_OVERLAY_OWNER_PID
    if owner_pid is None or int(owner_pid) <= 1:
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if str(VIRTUAL_CURSOR_OVERLAY_SCRIPT) not in tokens:
        return False

    required = {
        "--session": "legacy-global",
        "--state": str(VIRTUAL_MOUSE_STATE_PATH),
        "--pid": str(VIRTUAL_CURSOR_OVERLAY_PID_PATH),
        "--owner-pid": str(int(owner_pid)),
    }
    for flag, expected in required.items():
        try:
            index = tokens.index(flag)
        except ValueError:
            return False
        if index + 1 >= len(tokens) or tokens[index + 1] != expected:
            return False
    return True


def process_command(pid: int) -> str:
    result = subprocess.run(
        ["ps", "-p", str(int(pid)), "-o", "command="],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip()


def legacy_overlay_pid_is_owned(pid: int) -> bool:
    return pid_is_running(pid) and legacy_overlay_command_matches(process_command(pid))


def overlay_process_pids() -> list[int]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            text=True,
            capture_output=True,
            check=False,
        )
        pids = []
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue
            pid = int(parts[0])
            if pid != os.getpid() and legacy_overlay_command_matches(parts[1]):
                pids.append(pid)
        return sorted(set(pids))
    except Exception:
        return []


def write_overlay_pid(pid: int | None) -> None:
    try:
        if pid is None:
            VIRTUAL_CURSOR_OVERLAY_PID_PATH.unlink()
        else:
            VIRTUAL_CURSOR_OVERLAY_PID_PATH.write_text(f"{pid}\n", encoding="utf-8")
    except Exception:
        pass


def virtual_cursor_overlay_status() -> dict[str, Any]:
    pids = overlay_process_pids()
    if len(pids) == 1:
        write_overlay_pid(pids[0])
        return {"running": True, "pid": pids[0], "pids": pids}
    if len(pids) > 1:
        return {"running": True, "pid": pids[-1], "pids": pids, "duplicates": True}

    try:
        pid = int(VIRTUAL_CURSOR_OVERLAY_PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return {"running": False, "pid": None, "pids": []}

    if not legacy_overlay_pid_is_owned(pid):
        write_overlay_pid(None)
        return {"running": False, "pid": None, "pids": []}

    return {"running": True, "pid": pid, "pids": [pid]}


def kill_overlay_pids(pids: list[int]) -> None:
    owned_pids = [pid for pid in sorted(set(pids)) if legacy_overlay_pid_is_owned(pid)]
    for pid in owned_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    deadline = time.time() + 0.8
    while time.time() < deadline:
        remaining = [pid for pid in owned_pids if legacy_overlay_pid_is_owned(pid)]
        if not remaining:
            break
        time.sleep(0.05)
    for pid in [pid for pid in owned_pids if legacy_overlay_pid_is_owned(pid)]:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    deadline = time.time() + 1.0
    while time.time() < deadline:
        remaining = [pid for pid in owned_pids if legacy_overlay_pid_is_owned(pid)]
        if not remaining:
            break
        time.sleep(0.05)


def start_virtual_cursor_overlay(required: bool = True) -> dict[str, Any]:
    if LEGACY_OVERLAY_OWNER_PID is None or int(LEGACY_OVERLAY_OWNER_PID) <= 1:
        raise RuntimeError("Legacy cursor overlay requires an explicit persistent owner PID")
    status = virtual_cursor_overlay_status()
    if status["running"] and not status.get("duplicates"):
        return status
    if status.get("duplicates"):
        kill_overlay_pids(list(status.get("pids") or []))
        write_overlay_pid(None)

    if not VIRTUAL_CURSOR_OVERLAY_SCRIPT.exists():
        if required:
            raise RuntimeError(f"Overlay script not found: {VIRTUAL_CURSOR_OVERLAY_SCRIPT}")
        return {"running": False, "pid": None, "error": "overlay_script_missing"}

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                str(VIRTUAL_CURSOR_OVERLAY_SCRIPT),
                "--session",
                "legacy-global",
                "--state",
                str(VIRTUAL_MOUSE_STATE_PATH),
                "--pid",
                str(VIRTUAL_CURSOR_OVERLAY_PID_PATH),
                "--owner-pid",
                str(int(LEGACY_OVERLAY_OWNER_PID)),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

        deadline = time.time() + 2.0
        while time.time() < deadline:
            status = virtual_cursor_overlay_status()
            if status["running"]:
                return status
            time.sleep(0.05)

        status = virtual_cursor_overlay_status()
        if required and not status["running"]:
            try:
                process.terminate()
                process.wait(timeout=0.5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            raise RuntimeError("Virtual cursor overlay did not start")
        return status
    except Exception as exc:
        if required:
            raise
        return {"running": False, "pid": None, "error": str(exc)}


def stop_virtual_cursor_overlay() -> dict[str, Any]:
    status = virtual_cursor_overlay_status()
    if not status["running"]:
        write_overlay_pid(None)
        return {"running": False, "pid": None, "pids": []}

    kill_overlay_pids(list(status.get("pids") or [int(status["pid"])]))
    write_overlay_pid(None)
    return virtual_cursor_overlay_status()


def handle_virtual_cursor_overlay(action: str | None) -> dict[str, Any]:
    normalized = (action or "status").lower()
    if normalized == "status":
        return virtual_cursor_overlay_status()
    if normalized == "start":
        return start_virtual_cursor_overlay(required=True)
    if normalized == "stop":
        return stop_virtual_cursor_overlay()
    raise ValueError(f"Unsupported virtual cursor overlay action: {action}")


def get_virtual_mouse_position() -> tuple[int, int]:
    state = load_virtual_mouse_state()
    return int(state["x"]), int(state["y"])


def set_virtual_mouse_position(x: int, y: int, button: str | None = None) -> dict[str, Any]:
    state = load_virtual_mouse_state()
    state["x"] = int(x)
    state["y"] = int(y)
    if button is not None or "button" not in state:
        state["button"] = button
    save_virtual_mouse_state(state)
    start_virtual_cursor_overlay(required=False)
    return state


def mouse_button_spec(button: str | None) -> dict[str, Any]:
    normalized = (button or "left").lower()
    if normalized == "left":
        return {
            "name": "left",
            "button": kCGMouseButtonLeft,
            "down": kCGEventLeftMouseDown,
            "up": kCGEventLeftMouseUp,
            "dragged": kCGEventLeftMouseDragged,
        }
    if normalized == "right":
        return {
            "name": "right",
            "button": kCGMouseButtonRight,
            "down": kCGEventRightMouseDown,
            "up": kCGEventRightMouseUp,
            "dragged": kCGEventRightMouseDragged,
        }
    if normalized == "middle":
        return {
            "name": "middle",
            "button": kCGMouseButtonCenter,
            "down": kCGEventOtherMouseDown,
            "up": kCGEventOtherMouseUp,
            "dragged": kCGEventOtherMouseDragged,
        }
    raise ValueError(f"Unsupported mouse button: {button}")


def post_mouse_event(event_type: int, x: int, y: int, button: int, click_state: int = 1) -> None:
    event = CGEventCreateMouseEvent(None, event_type, CGPointMake(int(x), int(y)), button)
    CGEventSetIntegerValueField(event, kCGMouseEventClickState, int(click_state))
    post_virtual_input_event(event, int(x), int(y))


def frontmost_process_id() -> int | None:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    pid = app.processIdentifier()
    return int(pid) if pid else None


def process_id_for_point(x: int, y: int) -> int | None:
    windows = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
        kCGNullWindowID,
    ) or []
    for window in windows:
        if not window.get(kCGWindowIsOnscreen):
            continue
        if int(window.get(kCGWindowLayer, 0)) != 0:
            continue
        bounds = window.get(kCGWindowBounds) or {}
        left = int(bounds.get("X", 0))
        top = int(bounds.get("Y", 0))
        width = int(bounds.get("Width", 0))
        height = int(bounds.get("Height", 0))
        if left <= x < left + width and top <= y < top + height:
            pid = window.get(kCGWindowOwnerPID)
            return int(pid) if pid else None
    return None


def post_virtual_input_event(event, x: int | None = None, y: int | None = None) -> None:
    raise RuntimeError(
        "target_required: legacy desktop-global input is disabled; "
        "bind an application with get_app_state and use the app-targeted action tools"
    )


def post_click(x: int, y: int, button: str, count: int) -> None:
    spec = mouse_button_spec(button)
    click_count = max(1, int(count))
    for index in range(click_count):
        click_state = index + 1
        post_mouse_event(spec["down"], x, y, spec["button"], click_state)
        post_mouse_event(spec["up"], x, y, spec["button"], click_state)
        if index + 1 < click_count:
            time.sleep(0.08)
    set_virtual_mouse_position(x, y, None)


def post_scroll(x: int, y: int, delta_x: int, delta_y: int) -> None:
    event = CGEventCreateScrollWheelEvent(
        None,
        kCGScrollEventUnitLine,
        2,
        int(delta_y),
        int(delta_x),
    )
    CGEventSetLocation(event, CGPointMake(int(x), int(y)))
    post_virtual_input_event(event, int(x), int(y))
    set_virtual_mouse_position(x, y, None)


def interpolated_points(start_x: int, start_y: int, end_x: int, end_y: int, steps: int = 12) -> list[tuple[int, int]]:
    total_steps = max(1, int(steps))
    points = []
    for index in range(1, total_steps + 1):
        ratio = index / total_steps
        points.append((
            int(round(start_x + (end_x - start_x) * ratio)),
            int(round(start_y + (end_y - start_y) * ratio)),
        ))
    return points


def post_drag(from_point: dict[str, Any] | None, to_point: dict[str, Any], button: str = "left") -> None:
    spec = mouse_button_spec(button)
    if from_point:
        start_x = int(from_point["x"])
        start_y = int(from_point["y"])
    else:
        start_x, start_y = get_virtual_mouse_position()
    end_x = int(to_point["x"])
    end_y = int(to_point["y"])
    post_mouse_event(spec["down"], start_x, start_y, spec["button"], 1)
    for x, y in interpolated_points(start_x, start_y, end_x, end_y):
        post_mouse_event(spec["dragged"], x, y, spec["button"], 1)
        time.sleep(0.01)
    post_mouse_event(spec["up"], end_x, end_y, spec["button"], 1)
    set_virtual_mouse_position(end_x, end_y, None)


def post_mouse_down(x: int | None = None, y: int | None = None, button: str = "left") -> None:
    spec = mouse_button_spec(button)
    if x is None or y is None:
        vx, vy = get_virtual_mouse_position()
    else:
        vx, vy = int(x), int(y)
    post_mouse_event(spec["down"], vx, vy, spec["button"], 1)
    set_virtual_mouse_position(vx, vy, spec["name"])


def post_mouse_up(x: int | None = None, y: int | None = None, button: str | None = None) -> None:
    state = load_virtual_mouse_state()
    release_button = button or state.get("button") or "left"
    spec = mouse_button_spec(release_button)
    if x is None or y is None:
        vx, vy = int(state["x"]), int(state["y"])
    else:
        vx, vy = int(x), int(y)
    post_mouse_event(spec["up"], vx, vy, spec["button"], 1)
    set_virtual_mouse_position(vx, vy, None)


def click(x: int, y: int, button: str, count: int, modifiers: list[str] | None) -> None:
    if modifiers:
        normalized = [normalize_key(m) for m in modifiers]
        for key in normalized:
            pyautogui.keyDown(key)
        try:
            post_click(x, y, button, count)
        finally:
            for key in reversed(normalized):
                pyautogui.keyUp(key)
    else:
        post_click(x, y, button, count)


def scroll(x: int, y: int, delta_x: int, delta_y: int) -> None:
    post_scroll(x, y, delta_x, delta_y)


def key_action(sequence: str, repeat: int = 1) -> None:
    parts = [normalize_key(part) for part in sequence.split("+") if part.strip()]
    modifiers = [part for part in parts if part in {"command", "option", "shift", "ctrl", "fn"}]
    non_modifiers = [part for part in parts if part not in {"command", "option", "shift", "ctrl", "fn"}]

    # Try AX-based action for enter key first
    if parts == ["enter"] and ax_confirm_text_target():
        return

    # For any actual system-wide key presses, perform focus alignment guard
    assert_focus_aligned("key press")

    for _ in range(max(1, repeat)):
        if parts == ["command", "v"]:
            paste_clipboard()
        elif len(non_modifiers) == 1 and len(parts) == len(modifiers) + 1:
            key = non_modifiers[0]
            if key in APPLE_KEY_CODES:
                send_keycode_via_osascript(APPLE_KEY_CODES[key], modifiers)
            elif len(key) == 1:
                send_keystroke_via_osascript(key, modifiers)
            else:
                pyautogui.hotkey(*parts, interval=0.02)
        elif len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts, interval=0.02)
        time.sleep(0.01)


def hold_keys(keys: list[str], duration_ms: int) -> None:
    normalized = [normalize_key(k) for k in keys]
    # Hold keys is a system-wide action, guard it
    assert_focus_aligned("hold keys")
    for key in normalized:
        pyautogui.keyDown(key)
    try:
        time.sleep(max(duration_ms, 0) / 1000)
    finally:
        for key in reversed(normalized):
            pyautogui.keyUp(key)


def ax_window_of_element(element):
    if not accessibility_services_available or element is None:
        return None
    curr = element
    try:
        for _ in range(50):
            if curr is None:
                break
            role = ax_attribute(curr, AX.kAXRoleAttribute)
            if role == AX.kAXWindowRole:
                return curr
            curr = ax_attribute(curr, AX.kAXParentAttribute)
    except Exception:
        pass
    return None


def ax_focused_window():
    if not accessibility_services_available:
        return None
    try:
        system = AX.AXUIElementCreateSystemWide()
        err, element = AX.AXUIElementCopyAttributeValue(system, AX.kAXFocusedWindowAttribute, None)
        return element if err == 0 else None
    except Exception:
        return None


def ax_window_bounds_key(window_el):
    if window_el is None:
        return None
    pos = ax_attribute(window_el, AX.kAXPositionAttribute)
    size = ax_attribute(window_el, AX.kAXSizeAttribute)
    if not pos or not size:
        return None
    try:
        return (int(pos.x), int(pos.y), int(size.width), int(size.height))
    except Exception:
        try:
            px = getattr(pos, "x", None)
            py = getattr(pos, "y", None)
            if px is None: px = pos[0]
            if py is None: py = pos[1]
            sw = getattr(size, "width", None)
            sh = getattr(size, "height", None)
            if sw is None: sw = size[0]
            if sh is None: sh = size[1]
            return (int(px), int(py), int(sw), int(sh))
        except Exception:
            pass
    return None


def quartz_window_under_virtual_cursor():
    vx, vy = get_virtual_mouse_position()
    point = CGPointMake(vx, vy)
    for window in list_windows():
        bounds = window["bounds"]
        rect = ((bounds["x"], bounds["y"]), (bounds["width"], bounds["height"]))
        if CGRectContainsPoint(rect, point):
            return window
    return None


def ax_window_from_quartz(q_win):
    if q_win is None:
        return None
    pid = q_win.get("pid")
    bounds = q_win.get("bounds")
    if not pid or not bounds:
        return None
    try:
        app_el = AX.AXUIElementCreateApplication(pid)
        err, windows_list = AX.AXUIElementCopyAttributeValue(app_el, AX.kAXWindowsAttribute, None)
        if err == 0 and windows_list:
            for win_el in windows_list:
                b_key = ax_window_bounds_key(win_el)
                if b_key:
                    if (abs(b_key[0] - bounds["x"]) <= 5 and
                        abs(b_key[1] - bounds["y"]) <= 5 and
                        abs(b_key[2] - bounds["width"]) <= 5 and
                        abs(b_key[3] - bounds["height"]) <= 5):
                        return win_el
    except Exception:
        pass
    return None


def assert_focus_aligned(action_label: str) -> None:
    if not accessibility_services_available:
        return
    vx, vy = get_virtual_mouse_position()
    app_under = app_under_point(vx, vy)
    front = frontmost_app()

    under_id = app_under.get("bundleId") if app_under else None
    front_id = front.get("bundleId") if front else None

    # 1. Package-level check
    mismatch = (under_id != front_id)

    # 2. Window-level check (ensuring same window bounds to prevent crosstalk across displays for the same app)
    q_win_under = quartz_window_under_virtual_cursor()
    bounds_under = None
    if q_win_under:
        b = q_win_under["bounds"]
        bounds_under = (b["x"], b["y"], b["width"], b["height"])

    win_focused = ax_focused_window()
    bounds_focused = ax_window_bounds_key(win_focused)

    if bounds_under and bounds_focused and bounds_under != bounds_focused:
        mismatch = True

    if mismatch:
        raise RuntimeError(
            f"CrosstalkPrevented: Target mismatch for global {action_label}. "
            f"Virtual cursor is over '{app_under.get('displayName') if app_under else 'Desktop/None'}' ({under_id}) with window bounds {bounds_under}, "
            f"but frontmost app is '{front.get('displayName') if front else 'None'}' ({front_id}) with focused window bounds {bounds_focused}. "
            f"Execution blocked because focus-stealing recovery is disabled."
        )


def type_text(text: str) -> None:
    if ax_set_text(text):
        return

    # AX text setting failed, falling back to system-wide keyboard events. Guard it.
    assert_focus_aligned("type_text")

    if text.isascii() and len(text) <= 1024:
        pyautogui.write(text, interval=0.008)
        return

    previous_clipboard = read_clipboard()
    write_clipboard(text)
    try:
        paste_clipboard()
        time.sleep(0.25)
    finally:
        write_clipboard(previous_clipboard)


def main() -> int:
    global current_command, current_payload, LEGACY_OVERLAY_OWNER_PID
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--payload", default="{}")
    parser.add_argument("--owner-pid", required=True, type=int)
    args = parser.parse_args()
    if args.owner_pid <= 1:
        parser.error("--owner-pid must identify the persistent bridge process")
    payload = json.loads(args.payload)

    current_command = args.command
    current_payload = payload
    LEGACY_OVERLAY_OWNER_PID = int(args.owner_pid)

    try:
        command = args.command
        if command == "map_coordinates":
            x = float(payload["x"])
            y = float(payload["y"])
            to_type = payload.get("to", "physical")
            display_id = payload.get("displayId")
            display = choose_display(display_id)
            scale = display["scaleFactor"]
            if to_type == "physical":
                mx = (x - display["originX"]) * scale + display["originX"]
                my = (y - display["originY"]) * scale + display["originY"]
            else:
                mx = (x - display["originX"]) / scale + display["originX"]
                my = (y - display["originY"]) / scale + display["originY"]
            json_output({"ok": True, "result": {"x": int(mx), "y": int(my), "scale": scale, "to": to_type}})
            return 0
        if command == "check_permissions":
            perms = check_permissions()
            json_output({"ok": True, "result": perms})
            return 0
        if command == "virtual_cursor_overlay":
            result = handle_virtual_cursor_overlay(payload.get("action"))
            json_output({"ok": True, "result": result})
            return 0
        if command == "list_displays":
            json_output({"ok": True, "result": get_displays()})
            return 0
        if command == "get_display_size":
            json_output({"ok": True, "result": choose_display(payload.get("displayId"))})
            return 0
        if command == "screenshot":
            display = choose_display(payload.get("displayId"))
            resize = requested_resize(payload, display["width"], display["height"])
            result = capture_display(
                display["displayId"],
                resize=resize,
                zoom_factor=payload.get("zoomFactor"),
                highlight_point=payload.get("highlightPoint"),
                highlight_radius=payload.get("highlightRadius"),
                show_virtual_cursor=payload.get("showVirtualCursor", True),
            )
            json_output({"ok": True, "result": result})
            return 0
        if command == "resolve_prepare_capture":
            display = choose_display(payload.get("preferredDisplayId"))
            resize = requested_resize(payload, display["width"], display["height"])
            result = capture_display(
                display["displayId"],
                resize,
                show_virtual_cursor=payload.get("showVirtualCursor", True),
            )
            result["hidden"] = []
            result["resolvedDisplayId"] = result["displayId"]
            json_output({"ok": True, "result": result})
            return 0
        if command == "zoom":
            region = {
                "left": int(payload["x"]),
                "top": int(payload["y"]),
                "width": int(payload["width"]),
                "height": int(payload["height"]),
            }
            resize = requested_resize(payload, region["width"], region["height"])
            result = capture_region(
                region,
                resize=resize,
                zoom_factor=payload.get("zoomFactor"),
                show_virtual_cursor=payload.get("showVirtualCursor", True),
            )
            json_output({"ok": True, "result": result})
            return 0
        if command == "prepare_for_action":
            json_output({"ok": True, "result": []})
            return 0
        if command == "preview_hide_set":
            json_output({"ok": True, "result": []})
            return 0
        if command == "find_window_displays":
            json_output({"ok": True, "result": find_window_displays(list(payload.get("bundleIds") or []))})
            return 0
        if command == "list_windows":
            json_output({"ok": True, "result": list_windows()})
            return 0
        if command == "key":
            key_action(str(payload["keySequence"]), int(payload.get("repeat") or 1))
            json_output({"ok": True, "result": True})
            return 0
        if command == "hold_key":
            hold_keys(list(payload.get("keyNames") or []), int(payload.get("durationMs") or 0))
            json_output({"ok": True, "result": True})
            return 0
        if command == "type":
            type_text(str(payload.get("text") or ""))
            json_output({"ok": True, "result": True})
            return 0
        if command == "click":
            verify = payload.get("verify", False)
            before_b64 = None
            after_b64 = None
            diff_percent = 0.0

            if verify:
                region_size = int(payload.get("verifyRegionSize", 100))
                region = {
                    "left": int(payload["x"] - region_size // 2),
                    "top": int(payload["y"] - region_size // 2),
                    "width": region_size,
                    "height": region_size
                }
                try:
                    before_res = capture_region(region)
                    before_b64 = before_res["base64"]
                except Exception:
                    pass

            click(int(payload["x"]), int(payload["y"]), str(payload.get("button") or "left"), int(payload.get("count") or 1), payload.get("modifiers"))

            if verify and before_b64:
                time.sleep(0.15)
                try:
                    after_res = capture_region(region)
                    after_b64 = after_res["base64"]

                    img_before = Image.open(BytesIO(base64.b64decode(before_b64)))
                    img_after = Image.open(BytesIO(base64.b64decode(after_b64)))

                    if img_before.size == img_after.size:
                        from PIL import ImageChops, ImageStat
                        diff = ImageChops.difference(img_before, img_after)
                        stat = ImageStat.Stat(diff)
                        if stat.mean:
                            diff_percent = sum(stat.mean) / (len(stat.mean) * 255.0)
                except Exception:
                    pass

            if verify:
                json_output({
                    "ok": True,
                    "result": {
                        "clicked": True,
                        "before": before_b64,
                        "after": after_b64,
                        "diff": float(diff_percent)
                    }
                })
            else:
                json_output({"ok": True, "result": True})
            return 0
        if command == "drag":
            from_point = payload.get("from")
            post_drag(from_point, payload["to"], str(payload.get("button") or "left"))
            json_output({"ok": True, "result": True})
            return 0
        if command == "move_mouse":
            set_virtual_mouse_position(int(payload["x"]), int(payload["y"]), None)
            json_output({"ok": True, "result": True})
            return 0
        if command == "scroll":
            scroll(int(payload["x"]), int(payload["y"]), int(payload.get("deltaX") or 0), int(payload.get("deltaY") or 0))
            json_output({"ok": True, "result": True})
            return 0
        if command == "mouse_down":
            post_mouse_down(payload.get("x"), payload.get("y"), str(payload.get("button") or "left"))
            json_output({"ok": True, "result": True})
            return 0
        if command == "mouse_up":
            post_mouse_up(payload.get("x"), payload.get("y"), payload.get("button"))
            json_output({"ok": True, "result": True})
            return 0
        if command == "cursor_position":
            x, y = get_virtual_mouse_position()
            json_output({"ok": True, "result": {"x": int(x), "y": int(y)}})
            return 0
        if command == "physical_cursor_position":
            x, y = physical_cursor_position()
            json_output({"ok": True, "result": {"x": int(x), "y": int(y)}})
            return 0
        if command == "frontmost_app":
            json_output({"ok": True, "result": frontmost_app()})
            return 0
        if command == "app_under_point":
            json_output({"ok": True, "result": app_under_point(int(payload["x"]), int(payload["y"]))})
            return 0
        if command == "list_installed_apps":
            json_output({"ok": True, "result": installed_apps()})
            return 0
        if command == "list_running_apps":
            json_output({"ok": True, "result": running_apps()})
            return 0
        if command == "open_app":
            open_app(str(payload["bundleId"]))
            json_output({"ok": True, "result": True})
            return 0
        if command == "read_clipboard":
            json_output({"ok": True, "result": read_clipboard()})
            return 0
        if command == "write_clipboard":
            write_clipboard(str(payload.get("text") or ""))
            json_output({"ok": True, "result": True})
            return 0
        if command == "paste_clipboard":
            paste_clipboard()
            json_output({"ok": True, "result": True})
            return 0
        if command == "detect_and_close_popups":
            res = detect_and_close_popups(payload.get("displayId"))
            json_output({"ok": True, "result": res})
            return 0
        if command == "detect_captcha":
            res = detect_captcha(payload.get("displayId"))
            json_output({"ok": True, "result": res})
            return 0
        if command == "ocr":
            res = perform_ocr_on_display(payload.get("displayId"))
            json_output({"ok": True, "result": res})
            return 0
        error_output(f"Unknown command: {command}", code="bad_command")
        return 2
    except Exception as exc:
        error_output(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
