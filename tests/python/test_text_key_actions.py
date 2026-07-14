import unittest

from runtime.cu_runtime.accessibility import ElementRecord
from runtime.cu_runtime.actions import ActionRouter, python_index_to_utf16, utf16_offset_to_python_index
from runtime.cu_runtime.errors import ComputerUseError
from runtime.cu_runtime.targets import TargetWindow


class FakeSnapshot:
    def __init__(self, record):
        self.record = record

    def element(self, index):
        if index != self.record.index:
            raise AssertionError(index)
        return self.record

    def revalidate(self, record, adapter):
        return None

    def focused_editable(self):
        return self.record


class FakeAdapter:
    def __init__(self, applies=True):
        self.set_values = []
        self.performed = []
        self.settable = {"AXValue", "AXSelectedText", "AXSelectedTextRange"}
        self.applies = applies
        self.attributes = {"AXValue": "hello world", "AXSelectedTextRange": (11, 0)}

    def set_attribute(self, element, attribute, value):
        self.set_values.append((element, str(attribute), value))
        if self.applies:
            self.attributes[str(attribute)] = value
            if str(attribute) == "AXSelectedText":
                location, length = self.attributes["AXSelectedTextRange"]
                before = self.attributes.get("AXValue", "")
                start = utf16_offset_to_python_index(before, location)
                end = utf16_offset_to_python_index(before, location + length)
                if start is None or end is None:
                    return
                self.attributes["AXValue"] = f"{before[:start]}{value}{before[end:]}"
                self.attributes["AXSelectedTextRange"] = (location + len(value.encode("utf-16-le")) // 2, 0)

    def attribute(self, element, attribute):
        return self.attributes.get(str(attribute))

    def perform(self, element, action):
        self.performed.append((element, action))

    def is_settable(self, element, attribute):
        return str(attribute) in self.settable

    def range_value(self, location, length):
        return (location, length)

    def decode_range(self, value):
        return value


class FakeEvents:
    def __init__(self, verified=False):
        self.verified = verified
        self.can_deliver = verified
        self.keys = []

    def post_key(self, target, key, modifiers):
        self.keys.append((target.pid, key, tuple(modifiers)))
        return self.verified


class TextKeyActionsTest(unittest.TestCase):
    def setUp(self):
        self.target = TargetWindow(
            "Harness", "com.example.harness", "Harness", "/tmp/Harness.app",
            77, 88, "Target", 10, 20, 200, 100,
        )
        self.raw = object()
        self.record = ElementRecord(
            1, 1, "AXTextField", "Input", None, "input", "hello world",
            True, True, ("AXConfirm",), (10, 10, 100, 30), "fingerprint", self.raw,
        )
        self.snapshot = FakeSnapshot(self.record)
        self.adapter = FakeAdapter()

    def test_set_value_targets_selected_ax_element(self):
        router = ActionRouter(self.adapter, FakeEvents())
        result = router.set_value(self.target, self.snapshot, 1, "replacement")
        self.assertEqual((self.raw, "AXValue", "replacement"), self.adapter.set_values[-1])
        self.assertEqual("accessibility", result.backend)

    def test_set_value_rejects_ax_success_without_observable_value_change(self):
        router = ActionRouter(FakeAdapter(applies=False), FakeEvents())
        with self.assertRaises(ComputerUseError) as unverified:
            router.set_value(self.target, self.snapshot, 1, "replacement")
        self.assertEqual("unverified_delivery", unverified.exception.code)

    def test_type_text_uses_selected_text_attribute_not_system_focus(self):
        router = ActionRouter(self.adapter, FakeEvents())
        router.type_text(self.target, self.snapshot, "inserted", element_index=1)
        self.assertEqual((self.raw, "AXSelectedText", "inserted"), self.adapter.set_values[-1])

    def test_type_text_rejects_ax_success_without_observable_text_change(self):
        adapter = FakeAdapter(applies=False)
        router = ActionRouter(adapter, FakeEvents())
        with self.assertRaises(ComputerUseError) as unverified:
            router.type_text(self.target, self.snapshot, "inserted", element_index=1)
        self.assertEqual("unverified_delivery", unverified.exception.code)

    def test_type_text_converts_ax_utf16_range_after_emoji(self):
        self.adapter.attributes["AXValue"] = "😀world"
        self.adapter.attributes["AXSelectedTextRange"] = (2, 0)
        router = ActionRouter(self.adapter, FakeEvents())
        router.type_text(self.target, self.snapshot, "X", element_index=1)
        self.assertEqual("😀Xworld", self.adapter.attributes["AXValue"])

    def test_type_text_rejects_range_inside_utf16_surrogate_pair_before_delivery(self):
        self.adapter.attributes["AXValue"] = "😀world"
        self.adapter.attributes["AXSelectedTextRange"] = (1, 0)
        router = ActionRouter(self.adapter, FakeEvents())
        with self.assertRaises(ComputerUseError) as stale:
            router.type_text(self.target, self.snapshot, "X", element_index=1)
        self.assertEqual("stale_state", stale.exception.code)
        self.assertEqual([], self.adapter.set_values)

    def test_select_text_sets_ax_range_for_unique_match(self):
        router = ActionRouter(self.adapter, FakeEvents())
        router.select_text(self.target, self.snapshot, 1, "world")
        self.assertEqual((self.raw, "AXSelectedTextRange", (6, 5)), self.adapter.set_values[-1])

    def test_select_text_uses_context_and_cursor_selection_type(self):
        self.adapter.attributes["AXValue"] = "first world, second world!"
        contextual = ElementRecord(
            1, 1, "AXTextField", "Input", None, "input", "first world, second world!",
            True, True, ("AXConfirm",), (10, 10, 100, 30), "fingerprint", self.raw,
        )
        snapshot = FakeSnapshot(contextual)
        router = ActionRouter(self.adapter, FakeEvents())
        result = router.select_text(
            self.target,
            snapshot,
            1,
            "world",
            prefix="second ",
            suffix="!",
            selection_type="cursor_after",
        )
        self.assertEqual((25, 0), self.adapter.set_values[-1][2])
        self.assertEqual("AXSelectedTextRange:cursor_after", result.action)

    def test_select_text_uses_current_ax_value_instead_of_stale_snapshot_value(self):
        self.adapter.attributes["AXValue"] = "prefix changed world suffix"
        router = ActionRouter(self.adapter, FakeEvents())
        result = router.select_text(
            self.target,
            self.snapshot,
            1,
            "world",
            prefix="changed ",
            suffix=" suffix",
        )
        self.assertEqual((15, 5), self.adapter.set_values[-1][2])
        self.assertEqual("AXSelectedTextRange:text", result.action)

    def test_select_text_writes_utf16_offsets_for_non_bmp_prefix(self):
        self.adapter.attributes["AXValue"] = "😀world"
        router = ActionRouter(self.adapter, FakeEvents())
        router.select_text(self.target, self.snapshot, 1, "world")
        self.assertEqual((2, 5), self.adapter.set_values[-1][2])

    def test_utf16_index_helpers_reject_surrogate_midpoint(self):
        self.assertEqual(2, python_index_to_utf16("😀world", 1))
        self.assertEqual(1, utf16_offset_to_python_index("😀world", 2))
        self.assertIsNone(utf16_offset_to_python_index("😀world", 1))

    def test_return_uses_axconfirm(self):
        router = ActionRouter(self.adapter, FakeEvents())
        router.press_key(self.target, self.snapshot, "Return", element_index=1)
        self.assertEqual([(self.raw, "AXConfirm")], self.adapter.performed)

    def test_unacknowledged_raw_key_delivery_is_not_attempted(self):
        events = FakeEvents(verified=False)
        router = ActionRouter(self.adapter, events)
        with self.assertRaises(ComputerUseError) as unverified:
            router.press_key(self.target, self.snapshot, "a", modifiers=["command"], element_index=1)
        self.assertEqual("unsupported_background_action", unverified.exception.code)
        self.assertEqual([], events.keys)
