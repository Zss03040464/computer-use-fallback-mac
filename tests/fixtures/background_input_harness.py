from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyProhibited,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFloatingWindowLevel,
    NSMakeRect,
    NSScrollView,
    NSScreen,
    NSSecureTextField,
    NSSlider,
    NSTextField,
    NSPanel,
    NSView,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSTimer


WINDOW_WIDTH = 420
WINDOW_HEIGHT = 360


def set_identifier(view, value: str) -> None:
    if view.respondsToSelector_("setIdentifier:"):
        view.setIdentifier_(value)
    if view.respondsToSelector_("setAccessibilityIdentifier:"):
        view.setAccessibilityIdentifier_(value)


class EventSurface(NSView):
    controller = objc.ivar()

    def initWithFrame_controller_(self, frame, controller):
        self = objc.super(EventSurface, self).initWithFrame_(frame)
        if self is not None:
            self.controller = controller
            self.setWantsLayer_(True)
            self.layer().setBackgroundColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.25, 0.3, 1.0).CGColor())
        return self

    def mouseDown_(self, event):
        self.controller.raw_mouse_down += 1
        self.controller.writeState()

    def mouseUp_(self, event):
        self.controller.raw_mouse_up += 1
        self.controller.writeState()

    def mouseDragged_(self, event):
        self.controller.raw_drag += 1
        self.controller.writeState()

    def scrollWheel_(self, event):
        self.controller.raw_scroll += 1
        self.controller.writeState()


class FlippedView(NSView):
    def isFlipped(self):
        return True


class HarnessController(NSObject):
    state_path = objc.ivar()
    ready_path = objc.ivar()
    role = objc.ivar()
    window = objc.ivar()
    text_field = objc.ivar()
    slider = objc.ivar()
    scroll_view = objc.ivar()
    click_count = objc.ivar()
    blocker_click_count = objc.ivar()
    confirm_count = objc.ivar()
    raw_mouse_down = objc.ivar()
    raw_mouse_up = objc.ivar()
    raw_drag = objc.ivar()
    raw_scroll = objc.ivar()

    def initWithRole_state_ready_origin_(self, role, state_path, ready_path, origin):
        self = objc.super(HarnessController, self).init()
        if self is None:
            return None
        self.role = role
        self.state_path = str(state_path)
        self.ready_path = str(ready_path)
        self.click_count = 0
        self.blocker_click_count = 0
        self.confirm_count = 0
        self.raw_mouse_down = 0
        self.raw_mouse_up = 0
        self.raw_drag = 0
        self.raw_scroll = 0

        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskNonactivatingPanel
        )
        self.window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(origin[0], origin[1], WINDOW_WIDTH, WINDOW_HEIGHT),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setHidesOnDeactivate_(False)
        title = "CU Target Harness" if role == "target" else "CU Blocker Harness"
        self.window.setTitle_(title)
        set_identifier(self.window, f"{role}-window")

        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT))
        self.window.setContentView_(content)
        if role == "target":
            self.buildTarget_(content)
        else:
            self.buildBlocker_(content)
            self.window.setHasShadow_(False)
            if os.environ.get("CU_BLOCKER_VISIBLE") != "1":
                self.window.setAlphaValue_(0.02)
            if os.environ.get("CU_BLOCKER_NORMAL") != "1":
                self.window.setLevel_(NSFloatingWindowLevel)

        self.window.orderFront_(None)
        self.writeState()
        Path(self.ready_path).write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "role": role,
                    "title": title,
                    "windowId": int(self.window.windowNumber()),
                    "origin": [origin[0], origin[1]],
                    "size": [WINDOW_WIDTH, WINDOW_HEIGHT],
                }
            ),
            encoding="utf-8",
        )
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.05,
            self,
            "poll:",
            None,
            True,
        )
        return self

    def buildTarget_(self, content):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(20, 285, 150, 36))
        button.setTitle_("Increment Target")
        button.setTarget_(self)
        button.setAction_("incrementTarget:")
        set_identifier(button, "target-button")
        content.addSubview_(button)

        self.text_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 235, 260, 32))
        self.text_field.setStringValue_("initial")
        self.text_field.setTarget_(self)
        self.text_field.setAction_("confirmText:")
        set_identifier(self.text_field, "target-text")
        content.addSubview_(self.text_field)

        self.slider = NSSlider.alloc().initWithFrame_(NSMakeRect(20, 190, 260, 28))
        self.slider.setMinValue_(0.0)
        self.slider.setMaxValue_(100.0)
        self.slider.setDoubleValue_(0.0)
        set_identifier(self.slider, "target-slider")
        content.addSubview_(self.slider)

        password = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(20, 162, 260, 24))
        password.setStringValue_("fixture-secret-must-not-leak")
        set_identifier(password, "target-password")
        content.addSubview_(password)

        self.scroll_view = NSScrollView.alloc().initWithFrame_(NSMakeRect(300, 80, 100, 240))
        self.scroll_view.setHasVerticalScroller_(True)
        document = FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, 80, 900))
        for index in range(20):
            label = NSTextField.labelWithString_(f"Row {index:02d}")
            label.setFrame_(NSMakeRect(5, 10 + index * 40, 70, 24))
            document.addSubview_(label)
        self.scroll_view.setDocumentView_(document)
        set_identifier(self.scroll_view, "target-scroll")
        content.addSubview_(self.scroll_view)

        surface = EventSurface.alloc().initWithFrame_controller_(NSMakeRect(20, 40, 260, 120), self)
        set_identifier(surface, "target-canvas")
        content.addSubview_(surface)

    def buildBlocker_(self, content):
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.55, 0.15, 0.15, 1.0).CGColor())
        button = NSButton.alloc().initWithFrame_(NSMakeRect(20, 285, 180, 36))
        button.setTitle_("Blocker Must Stay Zero")
        button.setTarget_(self)
        button.setAction_("incrementBlocker:")
        set_identifier(button, "blocker-button")
        content.addSubview_(button)

    def incrementTarget_(self, sender):
        self.click_count += 1
        self.writeState()

    def incrementBlocker_(self, sender):
        self.blocker_click_count += 1
        self.writeState()

    def confirmText_(self, sender):
        self.confirm_count += 1
        self.writeState()

    def poll_(self, timer):
        self.writeState()

    def writeState(self):
        payload = {
            "pid": os.getpid(),
            "role": str(self.role),
            "clickCount": int(self.click_count),
            "blockerClickCount": int(self.blocker_click_count),
            "confirmCount": int(self.confirm_count),
            "rawMouseDown": int(self.raw_mouse_down),
            "rawMouseUp": int(self.raw_mouse_up),
            "rawDrag": int(self.raw_drag),
            "rawScroll": int(self.raw_scroll),
            "textValue": str(self.text_field.stringValue()) if self.text_field is not None else "",
            "sliderValue": float(self.slider.doubleValue()) if self.slider is not None else 0.0,
            "scrollY": float(self.scroll_view.contentView().bounds().origin.y) if self.scroll_view is not None else 0.0,
        }
        path = Path(str(self.state_path))
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["target", "blocker"], required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--ready", required=True)
    parser.add_argument("--origin", default="520,420")
    parser.add_argument("--quartz-origin")
    args = parser.parse_args()
    origin = tuple(int(value) for value in args.origin.split(",", 1))
    if args.quartz_origin:
        quartz_origin = tuple(int(value) for value in args.quartz_origin.split(",", 1))
        screen_frame = NSScreen.screens()[0].frame()
        screen_max_y = round(screen_frame.origin.y + screen_frame.size.height)
        origin = (quartz_origin[0], screen_max_y - quartz_origin[1] - WINDOW_HEIGHT - 32)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    controller = HarnessController.alloc().initWithRole_state_ready_origin_(
        args.role,
        args.state,
        args.ready,
        origin,
    )
    app.setActivationPolicy_(NSApplicationActivationPolicyProhibited)

    def stop(signum, frame):
        app.terminate_(None)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    app.run()
    controller.writeState()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
