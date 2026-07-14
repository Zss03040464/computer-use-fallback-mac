import unittest

from runtime.cu_runtime.accessibility import AccessibilitySnapshot
from runtime.cu_runtime.actions import ActionRouter
from runtime.cu_runtime.capture import CaptureResult
from runtime.cu_runtime.errors import ComputerUseError
from runtime.cu_runtime.targets import TargetWindow


class FakeAdapter:
    def __init__(self, window):
        self.window = window
        self.performed = []
        self.fail_after = None

    def application(self, pid):
        return {"uid": "app", "children": [self.window]}

    def windows(self, application):
        return application["children"]

    def children(self, element):
        return element.get("children", [])

    def role(self, element):
        return element.get("role", "AXUnknown")

    def attribute(self, element, name):
        return element.get(str(name)) or element.get(name)

    def actions(self, element):
        return tuple(element.get("actions", ()))

    def bounds(self, element):
        return element.get("bounds")

    def identity(self, element):
        return element["uid"]

    def is_settable(self, element, name):
        return False

    def perform(self, element, action):
        if self.fail_after is not None and len(self.performed) >= self.fail_after:
            raise ComputerUseError("element_not_actionable", "failed", {"action": action})
        self.performed.append((element["uid"], action))


class FakeEventBackend:
    def __init__(self, verified=False):
        self.verified = verified
        self.can_deliver = verified
        self.calls = []

    def post_click(self, target, x, y, button, click_count):
        self.calls.append((target.pid, x, y, button, click_count))
        return self.verified


class ClickRoutingTest(unittest.TestCase):
    def setUp(self):
        self.target = TargetWindow(
            app="Harness",
            bundle_id="com.example.harness",
            display_name="Harness",
            path="/tmp/Harness.app",
            pid=77,
            window_id=88,
            title="Target",
            x=100,
            y=200,
            width=200,
            height=100,
        )
        self.button = {
            "uid": "button",
            "role": "AXButton",
            "bounds": (110, 210, 40, 30),
            "identifier": "target-button",
            "description": "Increment",
            "enabled": True,
            "actions": ["AXPress", "AXShowMenu"],
        }
        self.canvas = {
            "uid": "canvas",
            "role": "AXGroup",
            "bounds": (160, 210, 30, 30),
            "identifier": "canvas",
            "enabled": True,
            "actions": [],
        }
        self.window = {
            "uid": "window",
            "role": "AXWindow",
            "bounds": (100, 200, 200, 100),
            "children": [self.button, self.canvas],
        }
        self.adapter = FakeAdapter(self.window)
        self.snapshot = AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        self.capture = CaptureResult(b"png", 200, 100, 400, 200, 2.0, 2.0, "fake", self.target)

    def test_element_index_left_click_performs_axpress(self):
        router = ActionRouter(self.adapter, FakeEventBackend())
        result = router.click(self.target, self.snapshot, self.capture, element_index=1)
        self.assertEqual([("button", "AXPress")], self.adapter.performed)
        self.assertEqual("accessibility", result.backend)
        self.assertEqual("ax_action", result.verification)
        self.assertEqual((130, 225), result.global_point)

    def test_window_image_coordinate_click_hits_target_ax_tree(self):
        router = ActionRouter(self.adapter, FakeEventBackend())
        result = router.click(self.target, self.snapshot, self.capture, x=40, y=40)
        self.assertEqual([("button", "AXPress")], self.adapter.performed)
        self.assertEqual("target-button", result.element_identifier)
        self.assertEqual((120, 220), result.global_point)

    def test_right_click_uses_exposed_show_menu_action(self):
        router = ActionRouter(self.adapter, FakeEventBackend())
        router.click(self.target, self.snapshot, self.capture, element_index=1, button="right")
        self.assertEqual([("button", "AXShowMenu")], self.adapter.performed)

    def test_multi_click_partial_delivery_never_replays_completed_clicks(self):
        self.adapter.fail_after = 1
        router = ActionRouter(self.adapter, FakeEventBackend())
        with self.assertRaises(ComputerUseError) as partial:
            router.click(self.target, self.snapshot, self.capture, element_index=1, click_count=2)
        self.assertEqual("partial_delivery", partial.exception.code)
        self.assertEqual([("button", "AXPress")], self.adapter.performed)

    def test_secondary_action_must_be_exposed_by_current_element(self):
        router = ActionRouter(self.adapter, FakeEventBackend())
        with self.assertRaises(ComputerUseError) as unsupported:
            router.perform_secondary_action(self.target, self.snapshot, 1, "AXIncrement")
        self.assertEqual("element_not_actionable", unsupported.exception.code)

    def test_unacknowledged_pid_delivery_is_not_attempted(self):
        events = FakeEventBackend(verified=False)
        router = ActionRouter(self.adapter, events)
        with self.assertRaises(ComputerUseError) as unverified:
            router.click(self.target, self.snapshot, self.capture, x=130, y=40)
        self.assertEqual("unsupported_background_action", unverified.exception.code)
        self.assertEqual([], events.calls)

    def test_mutated_element_is_rejected_as_stale(self):
        router = ActionRouter(self.adapter, FakeEventBackend())
        self.button["identifier"] = "changed"
        with self.assertRaises(ComputerUseError) as stale:
            router.click(self.target, self.snapshot, self.capture, element_index=1)
        self.assertEqual("stale_state", stale.exception.code)
