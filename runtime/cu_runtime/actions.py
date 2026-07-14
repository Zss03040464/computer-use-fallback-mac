from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import ApplicationServices as AX

from .accessibility import AccessibilitySnapshot, ElementRecord
from .capture import CaptureResult
from .errors import ComputerUseError
from .targets import TargetWindow


def python_index_to_utf16(text: str, index: int) -> int:
    if index < 0 or index > len(text):
        raise ValueError("Python string index is out of bounds")
    return len(text[:index].encode("utf-16-le")) // 2


def utf16_offset_to_python_index(text: str, offset: int) -> int | None:
    if offset < 0:
        return None
    units = 0
    for index, character in enumerate(text):
        if units == offset:
            return index
        units += len(character.encode("utf-16-le")) // 2
        if units > offset:
            return None
    return len(text) if units == offset else None


@dataclass(frozen=True)
class ActionResult:
    target: TargetWindow
    element_identifier: str | None
    element_fingerprint: str | None
    backend: str
    delivery: str
    verification: str
    action: str
    global_point: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "elementIdentifier": self.element_identifier,
            "elementFingerprint": self.element_fingerprint,
            "backend": self.backend,
            "delivery": self.delivery,
            "verification": self.verification,
            "action": self.action,
            "globalPoint": list(self.global_point) if self.global_point is not None else None,
        }


class AppDirectedEventBackend:
    """Disabled until an application-specific acknowledgement channel exists.

    Posting first and reporting an unverified error is unsafe because callers
    may retry an action that already happened. Injectable test/application
    adapters can implement these methods only when they return a real delivery
    acknowledgement.
    """

    can_deliver = False

    def post_click(
        self,
        target: TargetWindow,
        x: int,
        y: int,
        button: str,
        click_count: int,
    ) -> bool:
        return False

    def post_key(self, target: TargetWindow, key: str, modifiers: list[str]) -> bool:
        return False

    def post_scroll(
        self,
        target: TargetWindow,
        x: int,
        y: int,
        delta_x: int,
        delta_y: int,
    ) -> bool:
        return False

    def post_drag(
        self,
        target: TargetWindow,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        button: str,
    ) -> bool:
        return False

    def post_mouse_button(
        self,
        target: TargetWindow,
        x: int,
        y: int,
        button: str,
        pressed: bool,
    ) -> bool:
        return False


class ActionRouter:
    def __init__(self, adapter, event_backend: AppDirectedEventBackend | Any | None = None) -> None:
        self.adapter = adapter
        self.event_backend = event_backend or AppDirectedEventBackend()

    def click(
        self,
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        capture: CaptureResult,
        *,
        element_index: int | None = None,
        x: float | None = None,
        y: float | None = None,
        button: str = "left",
        click_count: int = 1,
    ) -> ActionResult:
        record, global_point = self._resolve_element_and_point(
            target,
            snapshot,
            capture,
            element_index=element_index,
            x=x,
            y=y,
        )
        snapshot.revalidate(record, self.adapter)
        normalized = button.casefold()
        semantic_action = "AXPress" if normalized == "left" else "AXShowMenu" if normalized == "right" else None
        if semantic_action and semantic_action in record.actions:
            completed = 0
            requested = max(1, int(click_count))
            for _ in range(requested):
                try:
                    self.adapter.perform(record.raw, semantic_action)
                    completed += 1
                except ComputerUseError as error:
                    if completed:
                        raise ComputerUseError(
                            "partial_delivery",
                            "Click sequence stopped after a partial Accessibility delivery",
                            {"completedClicks": completed, "requestedClicks": requested, "action": semantic_action},
                        ) from error
                    raise
            return ActionResult(
                target,
                record.identifier,
                record.fingerprint,
                "accessibility",
                "delivered",
                "ax_action",
                semantic_action,
                global_point,
            )

        self._require_event_backend(target, record, "click")
        verified = self.event_backend.post_click(
            target,
            global_point[0],
            global_point[1],
            normalized,
            max(1, int(click_count)),
        )
        if not verified:
            raise ComputerUseError(
                "unverified_delivery",
                "The target application did not expose a verifiable background click action",
                {
                    "bundleId": target.bundle_id,
                    "pid": target.pid,
                    "windowId": target.window_id,
                    "elementIdentifier": record.identifier,
                    "backend": "pid_event",
                },
            )
        return ActionResult(
            target,
            record.identifier,
            record.fingerprint,
            "pid_event",
            "delivered",
            "app_acknowledged",
            "click",
            global_point,
        )

    def perform_secondary_action(
        self,
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        element_index: int,
        action: str,
    ) -> ActionResult:
        record = snapshot.element(element_index)
        snapshot.revalidate(record, self.adapter)
        if action not in record.actions:
            raise ComputerUseError(
                "element_not_actionable",
                "Requested secondary action is not exposed by the element",
                {
                    "elementIndex": element_index,
                    "action": action,
                    "availableActions": list(record.actions),
                },
            )
        self.adapter.perform(record.raw, action)
        return ActionResult(
            target,
            record.identifier,
            record.fingerprint,
            "accessibility",
            "delivered",
            "ax_action",
            action,
        )

    def set_value(
        self,
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        element_index: int,
        value: str,
    ) -> ActionResult:
        record = snapshot.element(element_index)
        snapshot.revalidate(record, self.adapter)
        if not record.settable and not self.adapter.is_settable(record.raw, AX.kAXValueAttribute):
            raise ComputerUseError("element_not_actionable", "Element value is not settable", {"elementIndex": element_index})
        self.adapter.set_attribute(record.raw, AX.kAXValueAttribute, value)
        if not self._wait_attribute_value(record.raw, AX.kAXValueAttribute, value):
            raise ComputerUseError(
                "unverified_delivery",
                "Accessibility accepted the value update but the target did not expose the requested value",
                {"elementIndex": element_index, "attribute": "AXValue"},
            )
        return self._ax_result(target, record, "AXValue")

    def type_text(
        self,
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        text: str,
        *,
        element_index: int | None = None,
    ) -> ActionResult:
        record = snapshot.element(element_index) if element_index is not None else snapshot.focused_editable()
        snapshot.revalidate(record, self.adapter)
        if not self.adapter.is_settable(record.raw, AX.kAXSelectedTextAttribute):
            raise ComputerUseError(
                "unsupported_background_action",
                "Target does not expose background-safe selected text insertion",
                {"elementIndex": record.index},
            )
        before_value = self.adapter.attribute(record.raw, AX.kAXValueAttribute)
        before = "" if before_value is None else str(before_value)
        selected_range = self.adapter.decode_range(
            self.adapter.attribute(record.raw, AX.kAXSelectedTextRangeAttribute)
        )
        if selected_range is None:
            raise ComputerUseError(
                "unsupported_background_action",
                "Target does not expose a readable selected text range for verified insertion",
                {"elementIndex": record.index},
            )
        location, length = selected_range
        start_index = utf16_offset_to_python_index(before, location)
        end_index = utf16_offset_to_python_index(before, location + length)
        if start_index is None or end_index is None or length < 0:
            raise ComputerUseError(
                "stale_state",
                "Target selected text range is outside the current UTF-16 value boundaries",
                {"elementIndex": record.index, "selection": list(selected_range)},
            )
        expected = f"{before[:start_index]}{text}{before[end_index:]}"
        self.adapter.set_attribute(record.raw, AX.kAXSelectedTextAttribute, text)
        if not self._wait_attribute_value(record.raw, AX.kAXValueAttribute, expected):
            raise ComputerUseError(
                "unverified_delivery",
                "Accessibility accepted text insertion but the exact target value was not observed",
                {"elementIndex": record.index, "attribute": "AXSelectedText"},
            )
        return self._ax_result(target, record, "AXSelectedText")

    def select_text(
        self,
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        element_index: int,
        text: str,
        *,
        prefix: str | None = None,
        suffix: str | None = None,
        selection_type: str = "text",
    ) -> ActionResult:
        record = snapshot.element(element_index)
        snapshot.revalidate(record, self.adapter)
        current_value = self.adapter.attribute(record.raw, AX.kAXValueAttribute)
        if current_value is None:
            raise ComputerUseError(
                "unsupported_background_action",
                "Target does not expose a current text value for verified selection",
                {"elementIndex": element_index},
            )
        value = str(current_value)
        locations = []
        offset = 0
        while True:
            location = value.find(text, offset)
            if location < 0:
                break
            before_matches = prefix is None or value[max(0, location - len(prefix)) : location] == prefix
            after = location + len(text)
            after_matches = suffix is None or value[after : after + len(suffix)] == suffix
            if before_matches and after_matches:
                locations.append(location)
            offset = location + max(1, len(text))
        if not locations:
            raise ComputerUseError("element_not_actionable", "Selection text was not found", {"text": text})
        if len(locations) > 1:
            raise ComputerUseError("element_not_actionable", "Selection text is ambiguous", {"text": text})
        location = locations[0]
        utf16_location = python_index_to_utf16(value, location)
        utf16_after = python_index_to_utf16(value, location + len(text))
        normalized_type = selection_type.casefold()
        if normalized_type == "text":
            selection = (utf16_location, utf16_after - utf16_location)
        elif normalized_type == "cursor_before":
            selection = (utf16_location, 0)
        elif normalized_type == "cursor_after":
            selection = (utf16_after, 0)
        else:
            raise ComputerUseError(
                "invalid_request",
                f"Unsupported selection type: {selection_type}",
                {"selectionType": selection_type},
            )
        if not self.adapter.is_settable(record.raw, AX.kAXSelectedTextRangeAttribute):
            raise ComputerUseError("unsupported_background_action", "Text selection range is not settable", {"elementIndex": element_index})
        range_value = self.adapter.range_value(*selection)
        self.adapter.set_attribute(
            record.raw,
            AX.kAXSelectedTextRangeAttribute,
            range_value,
        )
        if not self._wait_selection_state(record.raw, selection, location, text, prefix, suffix):
            raise ComputerUseError(
                "unverified_delivery",
                "Accessibility accepted the selection update but did not expose the requested range",
                {"elementIndex": element_index, "selection": list(selection)},
            )
        return self._ax_result(target, record, f"AXSelectedTextRange:{normalized_type}")

    def press_key(
        self,
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        key: str,
        *,
        modifiers: list[str] | None = None,
        element_index: int | None = None,
    ) -> ActionResult:
        record = snapshot.element(element_index) if element_index is not None else snapshot.focused_editable()
        snapshot.revalidate(record, self.adapter)
        if key.casefold() in {"return", "enter"} and "AXConfirm" in record.actions:
            self.adapter.perform(record.raw, "AXConfirm")
            return self._ax_result(target, record, "AXConfirm")
        self._require_event_backend(target, record, "key")
        verified = self.event_backend.post_key(target, key, list(modifiers or []))
        if not verified:
            self._raise_unverified(target, record, "pid_key_event")
        return ActionResult(target, record.identifier, record.fingerprint, "pid_event", "delivered", "app_acknowledged", "key")

    def scroll(
        self,
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        capture: CaptureResult,
        *,
        element_index: int | None = None,
        x: float | None = None,
        y: float | None = None,
        direction: str = "down",
        pages: int = 1,
        delta_x: int = 0,
        delta_y: int = 0,
    ) -> ActionResult:
        record = snapshot.element(element_index) if element_index is not None else snapshot.hit_test(*capture.image_to_logical(x, y))
        snapshot.revalidate(record, self.adapter)
        feedback_point = self._feedback_point(target, record, capture, x, y)
        action_map = {
            "down": "AXScrollDownByPage",
            "up": "AXScrollUpByPage",
            "left": "AXScrollLeftByPage",
            "right": "AXScrollRightByPage",
        }
        action = action_map.get(direction.casefold())
        if action and action in record.actions:
            completed = 0
            for _ in range(max(1, int(pages))):
                try:
                    self.adapter.perform(record.raw, action)
                    completed += 1
                except ComputerUseError as error:
                    if completed:
                        raise ComputerUseError(
                            "partial_delivery",
                            "Scrolling stopped after a partial Accessibility delivery",
                            {"completedPages": completed, "requestedPages": int(pages), "action": action},
                        ) from error
                    break
            if completed:
                return self._ax_result(target, record, action, feedback_point)
        scroll_button = snapshot.scroll_button_for(record, direction)
        if scroll_button is not None:
            snapshot.revalidate(scroll_button, self.adapter)
            completed = 0
            requested = max(1, int(pages))
            for _ in range(requested):
                try:
                    self.adapter.perform(scroll_button.raw, "AXPress")
                    completed += 1
                except ComputerUseError as error:
                    if completed:
                        raise ComputerUseError(
                            "partial_delivery",
                            "Scrollbar fallback stopped after a partial Accessibility delivery",
                            {"completedPages": completed, "requestedPages": requested, "action": "AXPress"},
                        ) from error
                    raise
            return self._ax_result(target, scroll_button, "AXPress", feedback_point)
        point = feedback_point
        if point is None:
            raise ComputerUseError("invalid_request", "Action requires coordinates", {"elementIndex": record.index})
        self._require_event_backend(target, record, "scroll")
        verified = self.event_backend.post_scroll(target, point[0], point[1], int(delta_x), int(delta_y))
        if not verified:
            self._raise_unverified(target, record, "pid_scroll_event")
        return ActionResult(target, record.identifier, record.fingerprint, "pid_event", "delivered", "app_acknowledged", "scroll", point)

    def drag(
        self,
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        capture: CaptureResult,
        *,
        element_index: int | None = None,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        button: str = "left",
    ) -> ActionResult:
        record = snapshot.element(element_index) if element_index is not None else snapshot.hit_test(*capture.image_to_logical(from_x, from_y))
        snapshot.revalidate(record, self.adapter)
        if record.role in {"AXSlider", "AXScrollBar", "AXSplitter"} and record.bounds is not None:
            minimum = float(self.adapter.attribute(record.raw, AX.kAXMinValueAttribute) or 0.0)
            maximum = float(self.adapter.attribute(record.raw, AX.kAXMaxValueAttribute) or 1.0)
            left, top, width, height = record.bounds
            local_to_x, local_to_y = capture.image_to_logical(to_x, to_y)
            orientation = str(self.adapter.attribute(record.raw, AX.kAXOrientationAttribute) or "AXHorizontalOrientation")
            ratio = ((local_to_y - top) / max(1, height)) if "Vertical" in orientation else ((local_to_x - left) / max(1, width))
            value = minimum + max(0.0, min(1.0, ratio)) * (maximum - minimum)
            self.adapter.set_attribute(record.raw, AX.kAXValueAttribute, value)
            if not self._wait_numeric_value(record.raw, AX.kAXValueAttribute, value):
                raise ComputerUseError(
                    "unverified_delivery",
                    "Accessibility accepted the drag value but the target did not expose the requested result",
                    {"elementIndex": record.index, "requestedValue": value},
                )
            return self._ax_result(target, record, "AXValue", capture.image_to_global(to_x, to_y))
        from_global = capture.image_to_global(from_x, from_y)
        to_global = capture.image_to_global(to_x, to_y)
        self._require_event_backend(target, record, "drag")
        verified = self.event_backend.post_drag(target, *from_global, *to_global, button)
        if not verified:
            self._raise_unverified(target, record, "pid_drag_event")
        return ActionResult(target, record.identifier, record.fingerprint, "pid_event", "delivered", "app_acknowledged", "drag", to_global)

    def mouse_button(
        self,
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        capture: CaptureResult,
        element_index: int,
        x: float,
        y: float,
        button: str,
        pressed: bool,
    ) -> ActionResult:
        record = snapshot.element(element_index)
        snapshot.revalidate(record, self.adapter)
        global_x, global_y = capture.image_to_global(x, y)
        normalized = button.casefold()
        semantic_action = "AXPress" if normalized == "left" else "AXShowMenu" if normalized == "right" else None
        if semantic_action and semantic_action in record.actions:
            if not pressed:
                self.adapter.perform(record.raw, semantic_action)
            return ActionResult(
                target,
                record.identifier,
                record.fingerprint,
                "accessibility",
                "pending" if pressed else "delivered",
                "release_required" if pressed else "ax_action",
                "mouse_down" if pressed else semantic_action,
                (global_x, global_y),
            )
        self._require_event_backend(target, record, "mouse_button")
        verified = self.event_backend.post_mouse_button(target, global_x, global_y, normalized, pressed)
        if not verified:
            self._raise_unverified(target, record, "pid_mouse_button_event")
        return ActionResult(
            target,
            record.identifier,
            record.fingerprint,
            "pid_event",
            "delivered",
            "app_acknowledged",
            "mouse_down" if pressed else "mouse_up",
            (global_x, global_y),
        )

    @staticmethod
    def _ax_result(
        target: TargetWindow,
        record: ElementRecord,
        action: str,
        global_point: tuple[int, int] | None = None,
    ) -> ActionResult:
        return ActionResult(
            target,
            record.identifier,
            record.fingerprint,
            "accessibility",
            "delivered",
            "ax_action",
            action,
            global_point,
        )

    @staticmethod
    def _feedback_point(target, record, capture, x, y):
        if x is not None and y is not None:
            return capture.image_to_global(x, y)
        if record.bounds is None:
            return None
        left, top, width, height = record.bounds
        return target.x + left + width // 2, target.y + top + height // 2

    @staticmethod
    def _raise_unverified(target: TargetWindow, record: ElementRecord, backend: str) -> None:
        raise ComputerUseError(
            "unverified_delivery",
            "The target application did not expose a verifiable background action",
            {
                "bundleId": target.bundle_id,
                "pid": target.pid,
                "windowId": target.window_id,
                "elementIdentifier": record.identifier,
                "backend": backend,
            },
        )

    def _require_event_backend(self, target: TargetWindow, record: ElementRecord, action: str) -> None:
        if getattr(self.event_backend, "can_deliver", False):
            return
        raise ComputerUseError(
            "unsupported_background_action",
            "The target does not expose a background-safe semantic action and no acknowledged app event backend is configured",
            {
                "bundleId": target.bundle_id,
                "pid": target.pid,
                "windowId": target.window_id,
                "elementIdentifier": record.identifier,
                "action": action,
            },
        )

    def _wait_attribute_value(self, raw, attribute: str, expected: Any, timeout: float = 0.3) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            actual = self.adapter.attribute(raw, attribute)
            if str(actual) == str(expected):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.03)

    def _wait_selection_state(
        self,
        raw,
        expected: tuple[int, int],
        text_location: int,
        text: str,
        prefix: str | None,
        suffix: str | None,
        timeout: float = 0.3,
    ) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            range_value = self.adapter.attribute(raw, AX.kAXSelectedTextRangeAttribute)
            current_value = self.adapter.attribute(raw, AX.kAXValueAttribute)
            current = "" if current_value is None else str(current_value)
            after = text_location + len(text)
            text_matches = current[text_location:after] == text
            prefix_matches = prefix is None or current[max(0, text_location - len(prefix)) : text_location] == prefix
            suffix_matches = suffix is None or current[after : after + len(suffix)] == suffix
            if self.adapter.decode_range(range_value) == expected and text_matches and prefix_matches and suffix_matches:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.03)

    def _wait_numeric_value(self, raw, attribute: str, expected: float, timeout: float = 0.3) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            try:
                actual = float(self.adapter.attribute(raw, attribute))
            except (TypeError, ValueError):
                actual = None
            if actual is not None and abs(actual - float(expected)) <= 1e-6:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.03)

    @staticmethod
    def _resolve_element_and_point(
        target: TargetWindow,
        snapshot: AccessibilitySnapshot,
        capture: CaptureResult,
        *,
        element_index: int | None,
        x: float | None,
        y: float | None,
    ) -> tuple[ElementRecord, tuple[int, int]]:
        if element_index is not None:
            record = snapshot.element(element_index)
            if record.bounds is None:
                if x is None or y is None:
                    raise ComputerUseError(
                        "invalid_request",
                        "Element has no bounds; image coordinates are required for event fallback",
                        {"elementIndex": element_index},
                    )
                return record, capture.image_to_global(x, y)
            left, top, width, height = record.bounds
            return record, (target.x + left + width // 2, target.y + top + height // 2)
        if x is None or y is None:
            raise ComputerUseError(
                "invalid_request",
                "Click requires element_index or both x and y",
                {},
            )
        local_x, local_y = capture.image_to_logical(x, y)
        record = snapshot.hit_test(local_x, local_y)
        return record, capture.image_to_global(x, y)
