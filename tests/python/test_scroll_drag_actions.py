import unittest

from runtime.cu_runtime.accessibility import ElementRecord
from runtime.cu_runtime.actions import ActionRouter
from runtime.cu_runtime.capture import CaptureResult
from runtime.cu_runtime.errors import ComputerUseError
from runtime.cu_runtime.targets import TargetWindow


class FakeSnapshot:
    def __init__(self, records):
        self.records = {record.index: record for record in records}

    def element(self, index):
        return self.records[index]

    def revalidate(self, record, adapter):
        return None

    def hit_test(self, x, y, required_actions=()):
        candidates = []
        for record in self.records.values():
            if record.bounds is None:
                continue
            left, top, width, height = record.bounds
            if left <= x < left + width and top <= y < top + height:
                if not required_actions or any(action in record.actions for action in required_actions):
                    candidates.append(record)
        if not candidates:
            raise ComputerUseError("element_not_actionable", "none", {})
        return min(candidates, key=lambda record: record.bounds[2] * record.bounds[3])

    def scrollbar_for(self, record):
        return next((item for item in self.records.values() if item.role == "AXScrollBar"), None)

    def scroll_button_for(self, record, direction):
        identifier = "scroll-up" if direction == "up" else "scroll-down"
        return next((item for item in self.records.values() if item.identifier == identifier), None)


class FakeAdapter:
    def __init__(self, applies=True):
        self.performed = []
        self.values = []
        self.fail_actions = set()
        self.fail_after = {}
        self.action_counts = {}
        self.applies = applies

    def perform(self, raw, action):
        self.action_counts[action] = self.action_counts.get(action, 0) + 1
        if action in self.fail_actions:
            raise ComputerUseError("element_not_actionable", "failed", {"action": action})
        if self.action_counts[action] > self.fail_after.get(action, float("inf")):
            raise ComputerUseError("element_not_actionable", "failed", {"action": action})
        self.performed.append((raw, action))

    def set_attribute(self, raw, attribute, value):
        self.values.append((raw, str(attribute), value))
        if self.applies:
            raw[str(attribute)] = value

    def attribute(self, raw, attribute):
        return raw.get(str(attribute))

    def is_settable(self, raw, attribute):
        return True


class FakeEvents:
    def __init__(self, verified=False):
        self.verified = verified
        self.can_deliver = verified
        self.scrolls = []
        self.drags = []
        self.buttons = []

    def post_scroll(self, target, x, y, delta_x, delta_y):
        self.scrolls.append((target.pid, x, y, delta_x, delta_y))
        return self.verified

    def post_drag(self, target, from_x, from_y, to_x, to_y, button):
        self.drags.append((target.pid, from_x, from_y, to_x, to_y, button))
        return self.verified

    def post_mouse_button(self, target, x, y, button, pressed):
        self.buttons.append((target.pid, x, y, button, pressed))
        return self.verified


class ScrollDragActionsTest(unittest.TestCase):
    def setUp(self):
        self.target = TargetWindow(
            "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
            77, 88, "Target", 100, 200, 200, 100,
        )
        self.capture = CaptureResult(b"png", 200, 100, 200, 100, 1.0, 1.0, "fake", self.target)
        self.scroll_raw = {}
        self.scrollbar_raw = {"AXValue": 0.0, "AXMinValue": 0.0, "AXMaxValue": 1.0}
        self.slider_raw = {"AXMinValue": 0.0, "AXMaxValue": 100.0}
        self.canvas_raw = {}
        self.scroll_record = ElementRecord(
            1, 1, "AXScrollArea", None, "Scroll", "scroll", None, True, False,
            ("AXScrollDownByPage", "AXScrollUpByPage"), (0, 0, 200, 100), "scroll-fp", self.scroll_raw,
        )
        self.slider_record = ElementRecord(
            2, 2, "AXSlider", None, "Slider", "slider", "0", True, True,
            (), (0, 20, 100, 20), "slider-fp", self.slider_raw,
        )
        self.scrollbar_record = ElementRecord(
            4, 2, "AXScrollBar", None, "Scrollbar", "scrollbar", "0", True, True,
            (), (180, 0, 20, 100), "scrollbar-fp", self.scrollbar_raw,
        )
        self.scroll_up_record = ElementRecord(
            5, 3, "AXButton", None, "Scroll up", "scroll-up", None, True, False,
            ("AXPress",), (185, 0, 10, 0), "scroll-up-fp", {},
        )
        self.scroll_down_record = ElementRecord(
            6, 3, "AXButton", None, "Scroll down", "scroll-down", None, True, False,
            ("AXPress",), (185, 100, 10, 0), "scroll-down-fp", {},
        )
        self.canvas_record = ElementRecord(
            3, 2, "AXGroup", None, "Canvas", "canvas", None, True, False,
            (), (120, 20, 70, 70), "canvas-fp", self.canvas_raw,
        )
        self.button_record = ElementRecord(
            7, 2, "AXButton", None, "Button", "target-button", None, True, False,
            ("AXPress",), (10, 20, 80, 30), "button-fp", {},
        )
        self.snapshot = FakeSnapshot([
            self.scroll_record,
            self.slider_record,
            self.canvas_record,
            self.scrollbar_record,
            self.scroll_up_record,
            self.scroll_down_record,
            self.button_record,
        ])
        self.adapter = FakeAdapter()

    def test_scroll_uses_exposed_ax_page_action(self):
        router = ActionRouter(self.adapter, FakeEvents())
        result = router.scroll(self.target, self.snapshot, self.capture, element_index=1, direction="down", pages=2)
        self.assertEqual([(self.scroll_raw, "AXScrollDownByPage")] * 2, self.adapter.performed)
        self.assertEqual((200, 250), result.global_point)

    def test_scroll_area_falls_back_to_scrollbar_direction_button(self):
        self.adapter.fail_actions.add("AXScrollDownByPage")
        router = ActionRouter(self.adapter, FakeEvents())
        router.scroll(self.target, self.snapshot, self.capture, element_index=1, direction="down", pages=2)
        self.assertEqual([(self.scroll_down_record.raw, "AXPress")] * 2, self.adapter.performed)

    def test_partial_page_scroll_never_replays_completed_pages_with_fallback(self):
        self.adapter.fail_after["AXScrollDownByPage"] = 1
        router = ActionRouter(self.adapter, FakeEvents())
        with self.assertRaises(ComputerUseError) as partial:
            router.scroll(self.target, self.snapshot, self.capture, element_index=1, direction="down", pages=2)
        self.assertEqual("partial_delivery", partial.exception.code)
        self.assertEqual([(self.scroll_raw, "AXScrollDownByPage")], self.adapter.performed)

    def test_partial_scrollbar_fallback_never_replays_completed_pages(self):
        self.adapter.fail_actions.add("AXScrollDownByPage")
        self.adapter.fail_after["AXPress"] = 1
        router = ActionRouter(self.adapter, FakeEvents())
        with self.assertRaises(ComputerUseError) as partial:
            router.scroll(self.target, self.snapshot, self.capture, element_index=1, direction="down", pages=2)
        self.assertEqual("partial_delivery", partial.exception.code)
        self.assertEqual([(self.scroll_down_record.raw, "AXPress")], self.adapter.performed)

    def test_slider_drag_sets_clamped_ax_value(self):
        router = ActionRouter(self.adapter, FakeEvents())
        result = router.drag(
            self.target,
            self.snapshot,
            self.capture,
            element_index=2,
            from_x=0,
            from_y=30,
            to_x=75,
            to_y=30,
        )
        self.assertEqual((self.slider_raw, "AXValue", 75.0), self.adapter.values[-1])
        self.assertEqual((175, 230), result.global_point)

    def test_slider_drag_rejects_unobservable_value_update(self):
        router = ActionRouter(FakeAdapter(applies=False), FakeEvents())
        with self.assertRaises(ComputerUseError) as unverified:
            router.drag(
                self.target,
                self.snapshot,
                self.capture,
                element_index=2,
                from_x=0,
                from_y=30,
                to_x=75,
                to_y=30,
            )
        self.assertEqual("unverified_delivery", unverified.exception.code)

    def test_unacknowledged_canvas_drag_is_not_attempted(self):
        events = FakeEvents(verified=False)
        router = ActionRouter(self.adapter, events)
        with self.assertRaises(ComputerUseError) as unverified:
            router.drag(
                self.target,
                self.snapshot,
                self.capture,
                element_index=3,
                from_x=130,
                from_y=30,
                to_x=180,
                to_y=60,
            )
        self.assertEqual("unsupported_background_action", unverified.exception.code)
        self.assertEqual([], events.drags)

    def test_verified_mouse_down_and_up_stay_on_target_pid(self):
        events = FakeEvents(verified=True)
        router = ActionRouter(self.adapter, events)
        down = router.mouse_button(self.target, self.snapshot, self.capture, 3, 140, 40, "left", True)
        up = router.mouse_button(self.target, self.snapshot, self.capture, 3, 140, 40, "left", False)
        self.assertEqual(
            [(77, 240, 240, "left", True), (77, 240, 240, "left", False)],
            events.buttons,
        )
        self.assertEqual((240, 240), down.global_point)
        self.assertEqual((240, 240), up.global_point)

    def test_button_mouse_down_defers_ax_press_until_mouse_up(self):
        events = FakeEvents(verified=False)
        router = ActionRouter(self.adapter, events)
        down = router.mouse_button(self.target, self.snapshot, self.capture, 7, 50, 35, "left", True)
        self.assertEqual("pending", down.delivery)
        self.assertEqual([], self.adapter.performed)
        up = router.mouse_button(self.target, self.snapshot, self.capture, 7, 50, 35, "left", False)
        self.assertEqual("delivered", up.delivery)
        self.assertEqual([(self.button_record.raw, "AXPress")], self.adapter.performed)
        self.assertEqual([], events.buttons)
