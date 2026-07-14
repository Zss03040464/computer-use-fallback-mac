import unittest

from runtime.cu_runtime.capture import CaptureResult
from runtime.cu_runtime.service import RuntimeService
from runtime.cu_runtime.session import SessionState
from runtime.cu_runtime.targets import TargetWindow
from runtime.cu_runtime.errors import ComputerUseError


class FakeResolver:
    def __init__(self, target):
        self.target = target

    def resolve(self, app, window_id=None, launch=True):
        return self.target


class FakeCapture:
    def __init__(self, result):
        self.result = result

    def capture(self, target):
        return self.result


class FakeSnapshot:
    def serialize_text(self):
        return "0 AXWindow Target"


class FakeRouter:
    def __init__(self):
        self.clicks = []
        self.secondary = []
        self.calls = []
        self.click_error = None

    def click(self, target, snapshot, capture, **kwargs):
        self.clicks.append((target, snapshot, capture, kwargs))
        if self.click_error is not None:
            raise self.click_error
        return FakeResult("click")

    def perform_secondary_action(self, target, snapshot, element_index, action):
        self.secondary.append((target, snapshot, element_index, action))
        return FakeResult(action)

    def set_value(self, target, snapshot, element_index, value):
        self.calls.append(("set_value", element_index, value))
        return FakeResult("set_value")

    def type_text(self, target, snapshot, text, element_index=None):
        self.calls.append(("type_text", element_index, text))
        return FakeResult("type_text")

    def select_text(self, target, snapshot, element_index, text, **kwargs):
        self.calls.append(("select_text", element_index, text, kwargs))
        return FakeResult("select_text")

    def press_key(self, target, snapshot, key, modifiers=None, element_index=None):
        self.calls.append(("press_key", element_index, key, tuple(modifiers or [])))
        return FakeResult("press_key")

    def scroll(self, target, snapshot, capture, **kwargs):
        self.calls.append(("scroll", kwargs))
        return FakeResult("scroll")

    def drag(self, target, snapshot, capture, **kwargs):
        self.calls.append(("drag", kwargs))
        return FakeResult("drag")

    def mouse_button(self, target, snapshot, capture, element_index, x, y, button, pressed):
        self.calls.append(("mouse_button", element_index, x, y, button, pressed))
        return FakeResult(
            "mouse_down" if pressed else "mouse_up",
            delivery="pending" if pressed else "delivered",
        )


class FakeResult:
    def __init__(self, action, global_point=(13, 24), delivery="delivered"):
        self.action = action
        self.global_point = global_point
        self.delivery = delivery

    def to_dict(self):
        return {
            "action": self.action,
            "backend": "fake",
            "globalPoint": list(self.global_point) if self.global_point else None,
            "delivery": self.delivery,
        }


class FakeOverlay:
    def __init__(self, error=None):
        self.error = error
        self.starts = 0

    def start(self):
        self.starts += 1
        if self.error is not None:
            raise self.error
        return {"running": True, "pid": 999, "sessionId": "fake"}

    def stop(self):
        return {"running": False, "pid": None, "sessionId": "fake"}


class ActionServiceTest(unittest.TestCase):
    def test_click_uses_cached_app_state_and_target_lock(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            target = TargetWindow(
                "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
                77, 88, "Target", 10, 20, 200, 100,
            )
            capture = CaptureResult(b"png", 200, 100, 200, 100, 1.0, 1.0, "fake", target)
            router = FakeRouter()
            overlay = FakeOverlay()
            service = RuntimeService(
                SessionState.create(Path(tmp), "action-service"),
                resolver=FakeResolver(target),
                capture=FakeCapture(capture),
                snapshot_factory=lambda target, generation: FakeSnapshot(),
                action_router=router,
                overlay_manager=overlay,
            )
            service.handle("get_app_state", {"app": "Harness"})

            result = service.handle("click", {"app": "Harness", "element_index": 1})

            self.assertEqual("click", result["action"])
            self.assertEqual([13, 24], result["globalPoint"])
            self.assertTrue(result["cursorFeedback"]["persisted"])
            self.assertEqual((3, 4, None), service.session.cursor_tuple())
            self.assertEqual(1, overlay.starts)
            self.assertEqual(1, router.clicks[0][3]["element_index"])

    def test_pending_mouse_down_feedback_is_not_labeled_delivered(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            target = TargetWindow(
                "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
                77, 88, "Target", 10, 20, 200, 100,
            )
            capture = CaptureResult(b"png", 200, 100, 200, 100, 1.0, 1.0, "fake", target)
            service = RuntimeService(
                SessionState.create(Path(tmp), "pending-down"),
                resolver=FakeResolver(target),
                capture=FakeCapture(capture),
                snapshot_factory=lambda target, generation: FakeSnapshot(),
                action_router=FakeRouter(),
                overlay_manager=FakeOverlay(),
            )
            service.handle("get_app_state", {"app": "Harness"})
            result = service.handle(
                "mouse_down",
                {"app": "Harness", "element_index": 3, "x": 3, "y": 4, "button": "left"},
            )
            self.assertEqual("pending", result["cursorFeedback"]["delivery"])
            self.assertEqual("pressed", service.session.cursor_feedback().phase)

    def test_failed_click_does_not_change_cursor_or_start_overlay(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            target = TargetWindow(
                "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
                77, 88, "Target", 10, 20, 200, 100,
            )
            capture = CaptureResult(b"png", 200, 100, 200, 100, 1.0, 1.0, "fake", target)
            router = FakeRouter()
            router.click_error = ComputerUseError("stale_state", "stale", {})
            overlay = FakeOverlay()
            service = RuntimeService(
                SessionState.create(Path(tmp), "failed-action"),
                resolver=FakeResolver(target),
                capture=FakeCapture(capture),
                snapshot_factory=lambda target, generation: FakeSnapshot(),
                action_router=router,
                overlay_manager=overlay,
            )
            service.handle("get_app_state", {"app": "Harness"})
            with self.assertRaises(ComputerUseError):
                service.handle("click", {"app": "Harness", "element_index": 1})
            self.assertFalse(service.session.cursor_path.exists())
            self.assertEqual(0, overlay.starts)

    def test_overlay_failure_is_a_warning_after_delivered_click(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            target = TargetWindow(
                "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
                77, 88, "Target", 10, 20, 200, 100,
            )
            capture = CaptureResult(b"png", 200, 100, 200, 100, 1.0, 1.0, "fake", target)
            overlay = FakeOverlay(ComputerUseError("runtime_unavailable", "overlay failed", {}))
            service = RuntimeService(
                SessionState.create(Path(tmp), "overlay-warning"),
                resolver=FakeResolver(target),
                capture=FakeCapture(capture),
                snapshot_factory=lambda target, generation: FakeSnapshot(),
                action_router=FakeRouter(),
                overlay_manager=overlay,
            )
            service.handle("get_app_state", {"app": "Harness"})
            result = service.handle("click", {"app": "Harness", "element_index": 1})
            self.assertEqual("click", result["action"])
            self.assertEqual("runtime_unavailable", result["cursorFeedback"]["warning"]["code"])

    def test_mouse_move_maps_scaled_image_point_to_global_overlay_point(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            target = TargetWindow(
                "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
                77, 88, "Target", 100, 200, 200, 100,
            )
            capture = CaptureResult(b"png", 200, 100, 400, 200, 2.0, 2.0, "fake", target)
            service = RuntimeService(
                SessionState.create(Path(tmp), "scaled-move"),
                resolver=FakeResolver(target),
                capture=FakeCapture(capture),
                snapshot_factory=lambda target, generation: FakeSnapshot(),
                action_router=FakeRouter(),
                overlay_manager=FakeOverlay(),
            )
            service.handle("get_app_state", {"app": "Harness"})

            service.handle("set_cursor", {"x": 20, "y": 30})

            value = json.loads(service.session.cursor_path.read_text(encoding="utf-8"))
            self.assertEqual((110, 215), (value["displayX"], value["displayY"]))
            self.assertEqual((20, 30, None), service.session.cursor_tuple())

    def test_secondary_action_uses_cached_snapshot(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            target = TargetWindow(
                "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
                77, 88, "Target", 10, 20, 200, 100,
            )
            capture = CaptureResult(b"png", 200, 100, 200, 100, 1.0, 1.0, "fake", target)
            router = FakeRouter()
            service = RuntimeService(
                SessionState.create(Path(tmp), "secondary-service"),
                resolver=FakeResolver(target),
                capture=FakeCapture(capture),
                snapshot_factory=lambda target, generation: FakeSnapshot(),
                action_router=router,
                overlay_manager=FakeOverlay(),
            )
            service.handle("get_app_state", {"app": "Harness"})

            result = service.handle(
                "perform_secondary_action",
                {"app": "Harness", "element_index": 2, "action": "AXShowMenu"},
            )

            self.assertEqual("AXShowMenu", result["action"])
            self.assertEqual((2, "AXShowMenu"), router.secondary[0][2:])

    def test_routes_text_key_scroll_drag_and_button_commands(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            target = TargetWindow(
                "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
                77, 88, "Target", 10, 20, 200, 100,
            )
            capture = CaptureResult(b"png", 200, 100, 200, 100, 1.0, 1.0, "fake", target)
            router = FakeRouter()
            service = RuntimeService(
                SessionState.create(Path(tmp), "all-actions"),
                resolver=FakeResolver(target),
                capture=FakeCapture(capture),
                snapshot_factory=lambda target, generation: FakeSnapshot(),
                action_router=router,
                overlay_manager=FakeOverlay(),
            )
            service.handle("get_app_state", {"app": "Harness"})

            service.handle("set_value", {"app": "Harness", "element_index": 1, "value": "x"})
            service.handle("type_text", {"app": "Harness", "element_index": 1, "text": "y"})
            service.handle("select_text", {"app": "Harness", "element_index": 1, "text": "z"})
            service.handle("press_key", {"app": "Harness", "element_index": 1, "key": "Return"})
            service.handle("scroll", {"app": "Harness", "element_index": 2, "direction": "down", "pages": 1})
            service.handle("drag", {"app": "Harness", "element_index": 3, "from_x": 1, "from_y": 2, "to_x": 3, "to_y": 4})
            service.handle("mouse_down", {"app": "Harness", "element_index": 3, "x": 3, "y": 4, "button": "left"})
            service.handle("mouse_up", {"app": "Harness", "element_index": 3, "x": 3, "y": 4, "button": "left"})

            self.assertEqual(
                ["set_value", "type_text", "select_text", "press_key", "scroll", "drag", "mouse_button", "mouse_button"],
                [call[0] for call in router.calls],
            )
            self.assertEqual((3, 4, None), service.session.cursor_tuple())

    def test_mouse_up_must_match_a_pending_down_in_the_same_session(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            target = TargetWindow(
                "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
                77, 88, "Target", 10, 20, 200, 100,
            )
            capture = CaptureResult(b"png", 200, 100, 200, 100, 1.0, 1.0, "fake", target)
            service = RuntimeService(
                SessionState.create(Path(tmp), "mouse-state"),
                resolver=FakeResolver(target),
                capture=FakeCapture(capture),
                snapshot_factory=lambda target, generation: FakeSnapshot(),
                action_router=FakeRouter(),
                overlay_manager=FakeOverlay(),
            )
            service.handle("get_app_state", {"app": "Harness"})
            with self.assertRaises(ComputerUseError) as unmatched:
                service.handle(
                    "mouse_up",
                    {"app": "Harness", "element_index": 3, "x": 3, "y": 4, "button": "left"},
                )
            self.assertEqual("invalid_request", unmatched.exception.code)
