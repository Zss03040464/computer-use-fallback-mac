import unittest

from runtime.cu_runtime.accessibility import AccessibilitySnapshot, SnapshotLimits
from runtime.cu_runtime.errors import ComputerUseError
from runtime.cu_runtime.targets import TargetWindow


class FakeAdapter:
    def __init__(self, root):
        self.root = root

    def application(self, pid):
        return {"uid": f"app-{pid}", "children": [self.root]}

    def windows(self, application):
        return application["children"]

    def children(self, element):
        return element.get("children", [])

    def role(self, element):
        return element.get("role", "AXUnknown")

    def attribute(self, element, name):
        return element.get(name)

    def actions(self, element):
        return tuple(element.get("actions", ()))

    def bounds(self, element):
        return element.get("bounds")

    def identity(self, element):
        return element["uid"]

    def is_settable(self, element, name):
        return bool(element.get("settable", False))


def element(uid, role, bounds, **attributes):
    return {"uid": uid, "role": role, "bounds": bounds, **attributes}


class AccessibilitySnapshotTest(unittest.TestCase):
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
            width=400,
            height=300,
        )
        self.button = element(
            "button",
            "AXButton",
            (110, 210, 40, 30),
            identifier="target-button",
            description="Increment",
            enabled=True,
            actions=["AXPress"],
        )
        self.second = element(
            "second",
            "AXButton",
            (160, 210, 40, 30),
            identifier="second-button",
            description="Second",
            enabled=True,
            actions=["AXPress", "AXShowMenu"],
        )
        self.container = element(
            "container",
            "AXGroup",
            (100, 200, 300, 200),
            children=[self.button, self.second],
        )
        self.window = element(
            "window",
            "AXWindow",
            (100, 200, 400, 300),
            identifier="window-88",
            title="Target",
            children=[self.container],
        )
        self.container["children"].append(self.window)
        self.adapter = FakeAdapter(self.window)

    def test_builds_deterministic_indexes_and_suppresses_cycles(self):
        first = AccessibilitySnapshot.build(self.adapter, self.target, generation=3)
        second = AccessibilitySnapshot.build(self.adapter, self.target, generation=4)

        self.assertEqual([0, 1, 2, 3], [record.index for record in first.elements])
        self.assertEqual(
            [record.fingerprint for record in first.elements],
            [record.fingerprint for record in second.elements],
        )
        self.assertEqual((10, 10, 40, 30), first.element(2).bounds)
        self.assertIn("2 AXButton Increment", first.serialize_text())

    def test_hit_test_prefers_smallest_deepest_actionable_element(self):
        snapshot = AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        record = snapshot.hit_test(20, 20, required_actions=("AXPress",))
        self.assertEqual("target-button", record.identifier)

    def test_revalidation_rejects_mutated_element(self):
        snapshot = AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        record = snapshot.element(2)
        self.button["identifier"] = "changed-button"
        with self.assertRaises(ComputerUseError) as stale:
            snapshot.revalidate(record, self.adapter)
        self.assertEqual("stale_state", stale.exception.code)

    def test_limits_depth_and_node_count(self):
        current = self.button
        for index in range(10):
            current = element(f"deep-{index}", "AXGroup", (100, 200, 10, 10), children=[current])
        self.window["children"] = [current]
        snapshot = AccessibilitySnapshot.build(
            self.adapter,
            self.target,
            generation=1,
            limits=SnapshotLimits(max_depth=2, max_nodes=3, max_text_bytes=4096, max_value_bytes=128),
        )
        self.assertLessEqual(len(snapshot.elements), 3)

    def test_missing_element_index_is_stale(self):
        snapshot = AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        with self.assertRaises(ComputerUseError) as stale:
            snapshot.element(999)
        self.assertEqual("stale_state", stale.exception.code)

    def test_focused_editable_returns_only_target_window_text_control(self):
        text_field = element(
            "text-field",
            "AXTextField",
            (120, 260, 200, 30),
            identifier="input",
            value="hello",
            focused=True,
            settable=True,
        )
        self.window["children"] = [text_field]
        snapshot = AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        self.assertEqual("input", snapshot.focused_editable().identifier)

    def test_element_metadata_exposes_window_local_bounds_for_precise_actions(self):
        snapshot = AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        metadata = snapshot.element_metadata()
        button = next(item for item in metadata if item["identifier"] == "target-button")
        self.assertEqual({"x": 10, "y": 10, "width": 40, "height": 30}, button["bounds"])
        self.assertEqual(["AXPress"], button["actions"])

    def test_standard_ax_attributes_win_over_lowercase_adapter_aliases(self):
        self.button["AXDescription"] = "Semantic Button Label"
        self.button["description"] = "<AXElement debug description>"
        snapshot = AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        button = next(record for record in snapshot.elements if record.identifier == "target-button")
        self.assertEqual("Semantic Button Label", button.description)

    def test_secure_text_field_values_are_never_serialized(self):
        password = element(
            "password",
            "AXTextField",
            (120, 260, 200, 30),
            identifier="password",
            AXSubrole="AXSecureTextField",
            value="do-not-leak",
            enabled=True,
            settable=True,
        )
        self.window["children"] = [password]
        snapshot = AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        record = next(item for item in snapshot.elements if item.identifier == "password")
        self.assertIsNone(record.value)
        self.assertNotIn("do-not-leak", snapshot.serialize_text())

    def test_multiple_nonmatching_ax_windows_are_rejected(self):
        other = element("other-window", "AXWindow", (700, 500, 300, 200), title="Other")
        self.adapter.root = self.window
        self.adapter.windows = lambda application: [self.window, other]
        self.window["bounds"] = (600, 400, 300, 200)
        with self.assertRaises(ComputerUseError) as mismatch:
            AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        self.assertEqual("window_not_found", mismatch.exception.code)

    def test_scroll_button_for_chooses_directional_button_inside_scrollbar(self):
        up = element("scroll-up", "AXButton", (480, 220, 12, 0), actions=["AXPress"], enabled=True)
        down = element("scroll-down", "AXButton", (480, 460, 12, 0), actions=["AXPress"], enabled=True)
        scrollbar = element(
            "scrollbar",
            "AXScrollBar",
            (478, 220, 20, 242),
            settable=True,
            children=[up, down],
        )
        scroll_area = element("scroll-area", "AXScrollArea", (300, 220, 200, 242), children=[scrollbar])
        self.window["children"] = [scroll_area]
        snapshot = AccessibilitySnapshot.build(self.adapter, self.target, generation=1)
        area_record = next(record for record in snapshot.elements if record.role == "AXScrollArea")
        self.assertEqual("scroll-up", snapshot.scroll_button_for(area_record, "up").raw["uid"])
        self.assertEqual("scroll-down", snapshot.scroll_button_for(area_record, "down").raw["uid"])
