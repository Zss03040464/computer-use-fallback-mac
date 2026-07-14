#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyProhibited,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSScreenSaverWindowLevel,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSObject, NSTimer

from cu_runtime.cursor_feedback import (
    CURSOR_AQUA_RGBA,
    CURSOR_EDGE_RGBA,
    CURSOR_FILL_RGBA,
    CURSOR_GLOW_RGBA,
    CURSOR_SHAPE,
    CURSOR_STYLE,
    CursorFeedback,
    cursor_visual,
)

WINDOW_WIDTH = 40
WINDOW_HEIGHT = 40
HOTSPOT_X = 10
HOTSPOT_Y = 10


def read_state(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["x"] = int(data.get("displayX", data["x"]))
        data["y"] = int(data.get("displayY", data["y"]))
        return data
    except Exception:
        return None


def screen_geometry_for_frames(
    x: int,
    y: int,
    frames: list[tuple[float, float, float, float]],
) -> dict[str, float]:
    if not frames:
        return {"appkit_x": 0.0, "appkit_y": 0.0, "width": 0.0, "height": 0.0, "top_y": 0.0}
    primary_x, primary_y, primary_width, primary_height = frames[0]
    del primary_x, primary_width
    primary_top = primary_y + primary_height
    fallback = None
    for origin_x, origin_y, width, height in frames:
        top_y = primary_top - (origin_y + height)
        geometry = {
            "appkit_x": origin_x,
            "appkit_y": origin_y,
            "width": width,
            "height": height,
            "top_y": top_y,
        }
        if fallback is None:
            fallback = geometry
        if origin_x <= x < origin_x + width and top_y <= y < top_y + height:
            return geometry
    return fallback


def screen_geometry_for_point(x: int, y: int) -> dict[str, float]:
    screens = list(NSScreen.screens() or [])
    frames = []
    for screen in screens:
        frame = screen.frame()
        frames.append((float(frame.origin.x), float(frame.origin.y), float(frame.size.width), float(frame.size.height)))
    return screen_geometry_for_frames(x, y, frames)


def frame_origin_for_point(
    x: int,
    y: int,
    frames: list[tuple[float, float, float, float]],
) -> tuple[float, float]:
    if not frames:
        return float(x - HOTSPOT_X), float(y - HOTSPOT_Y)
    primary_top = frames[0][1] + frames[0][3]
    return (
        float(x - HOTSPOT_X),
        float(primary_top - y - WINDOW_HEIGHT + HOTSPOT_Y),
    )


def process_is_running(pid: int) -> bool:
    if int(pid) <= 1:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True


class CursorView(NSView):
    pulse_strength = objc.ivar(type=objc._C_DBL)

    def isOpaque(self):
        return False

    def drawRect_(self, rect):
        def point(dx, dy):
            return (HOTSPOT_X + dx, WINDOW_HEIGHT - (HOTSPOT_Y + dy))

        def color(rgba, alpha_multiplier=1.0):
            red, green, blue, alpha = rgba
            return NSColor.colorWithCalibratedRed_green_blue_alpha_(
                red / 255.0,
                green / 255.0,
                blue / 255.0,
                min(1.0, (alpha / 255.0) * alpha_multiplier),
            )

        path = NSBezierPath.bezierPath()
        first = True
        for dx, dy in CURSOR_SHAPE:
            if first:
                path.moveToPoint_(point(dx, dy))
                first = False
            else:
                path.lineToPoint_(point(dx, dy))
        path.closePath()
        path.setLineJoinStyle_(1)
        path.setLineCapStyle_(1)

        pulse = max(0.0, min(1.0, float(self.pulse_strength or 0.0)))
        outer_glow = path.copy()
        outer_glow.setLineJoinStyle_(1)
        outer_glow.setLineCapStyle_(1)
        outer_glow.setLineWidth_(7.0 + 2.0 * pulse)
        color(CURSOR_GLOW_RGBA, 0.22 + 0.18 * pulse).setStroke()
        outer_glow.stroke()

        inner_glow = path.copy()
        inner_glow.setLineJoinStyle_(1)
        inner_glow.setLineCapStyle_(1)
        inner_glow.setLineWidth_(4.0 + 1.2 * pulse)
        color(CURSOR_GLOW_RGBA, 0.46 + 0.24 * pulse).setStroke()
        inner_glow.stroke()

        color(CURSOR_FILL_RGBA).setFill()
        path.fill()
        path.setLineWidth_(1.15)
        color(CURSOR_EDGE_RGBA).setStroke()
        path.stroke()

        tail_edge = NSBezierPath.bezierPath()
        for index, (dx, dy) in enumerate(CURSOR_SHAPE[2:5]):
            if index == 0:
                tail_edge.moveToPoint_(point(dx, dy))
            else:
                tail_edge.lineToPoint_(point(dx, dy))
        tail_edge.setLineJoinStyle_(1)
        tail_edge.setLineCapStyle_(1)
        tail_edge.setLineWidth_(0.75)
        color(CURSOR_AQUA_RGBA).setStroke()
        tail_edge.stroke()


class OverlayController(NSObject):
    state_path = objc.ivar()
    pid_path = objc.ivar()
    window = objc.ivar()
    view = objc.ivar()
    owner_pid = objc.ivar()

    def initWithStatePath_pidPath_ownerPid_(self, state_path, pid_path, owner_pid):
        self = objc.super(OverlayController, self).init()
        if self is None:
            return None

        self.state_path = str(state_path)
        self.pid_path = str(pid_path)
        self.owner_pid = int(owner_pid)

        frame = NSMakeRect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(NSColor.clearColor())
        self.window.setHasShadow_(False)
        self.window.setIgnoresMouseEvents_(True)
        self.window.setLevel_(NSScreenSaverWindowLevel)
        self.window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )

        self.view = CursorView.alloc().initWithFrame_(NSMakeRect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT))
        self.view.pulse_strength = 0.0
        self.window.setContentView_(self.view)
        Path(self.pid_path).write_text(f"{os.getpid()}\n", encoding="utf-8")
        self.tick_(None)
        return self

    def tick_(self, timer):
        if not process_is_running(int(self.owner_pid)):
            NSApplication.sharedApplication().terminate_(None)
            return
        state = read_state(Path(str(self.state_path)))
        if state is None:
            self.window.orderOut_(None)
            return
        x = int(state.get("x") or 0)
        y = int(state.get("y") or 0)
        feedback = CursorFeedback.from_mapping(state)
        self.view.pulse_strength = cursor_visual(feedback).pulse if feedback is not None else 0.0

        screens = list(NSScreen.screens() or [])
        frames = []
        for screen in screens:
            frame = screen.frame()
            frames.append((float(frame.origin.x), float(frame.origin.y), float(frame.size.width), float(frame.size.height)))
        frame_x, frame_y = frame_origin_for_point(x, y, frames)
        self.window.setFrameOrigin_((frame_x, frame_y))
        self.window.orderFront_(None)
        self.view.setNeedsDisplay_(True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--pid", required=True)
    parser.add_argument("--owner-pid", required=True, type=int)
    args = parser.parse_args()
    if args.owner_pid <= 1:
        parser.error("--owner-pid must identify a persistent non-system process")

    pid_path = Path(args.pid)

    def handle_signal(signum, frame):
        try:
            pid_path.unlink()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyProhibited)

    controller = OverlayController.alloc().initWithStatePath_pidPath_ownerPid_(
        args.state,
        str(pid_path),
        args.owner_pid,
    )
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0 / 30.0,
        controller,
        "tick:",
        None,
        True,
    )
    try:
        app.run()
    finally:
        try:
            pid_path.unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
