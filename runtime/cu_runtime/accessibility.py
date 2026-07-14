from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import time
from typing import Any, Iterable

import ApplicationServices as AX

from .errors import ComputerUseError
from .targets import TargetWindow


AX_DOM_IDENTIFIER_ATTRIBUTE = getattr(AX, "kAXDOMIdentifierAttribute", "AXDOMIdentifier")


@dataclass(frozen=True)
class SnapshotLimits:
    max_depth: int = 30
    max_nodes: int = 10_000
    max_text_bytes: int = 1_048_576
    max_value_bytes: int = 8_192


@dataclass(frozen=True)
class ElementRecord:
    index: int
    depth: int
    role: str
    title: str | None
    description: str | None
    identifier: str | None
    value: str | None
    enabled: bool
    settable: bool
    actions: tuple[str, ...]
    bounds: tuple[int, int, int, int] | None
    fingerprint: str
    raw: object = field(compare=False, repr=False)
    focused: bool = False
    subrole: str | None = None


class AccessibilityAdapter:
    transient_error = -25204

    def application(self, pid: int):
        return AX.AXUIElementCreateApplication(int(pid))

    def windows(self, application) -> list[Any]:
        return list(self.attribute(application, AX.kAXWindowsAttribute) or [])

    def children(self, element) -> list[Any]:
        return list(self.attribute(element, AX.kAXChildrenAttribute) or [])

    def role(self, element) -> str:
        return str(self.attribute(element, AX.kAXRoleAttribute) or "AXUnknown")

    def attribute(self, element, name: str):
        for attempt in range(3):
            try:
                error, value = AX.AXUIElementCopyAttributeValue(element, name, None)
            except Exception:
                return None
            if error == 0:
                return value
            if error != self.transient_error or attempt == 2:
                return None
            time.sleep(0.03 * (attempt + 1))
        return None

    def actions(self, element) -> tuple[str, ...]:
        for attempt in range(3):
            try:
                error, actions = AX.AXUIElementCopyActionNames(element, None)
            except Exception:
                return ()
            if error == 0:
                return tuple(str(action) for action in actions or [])
            if error != self.transient_error or attempt == 2:
                return ()
            time.sleep(0.03 * (attempt + 1))
        return ()

    def bounds(self, element) -> tuple[int, int, int, int] | None:
        position = self._ax_value(
            self.attribute(element, AX.kAXPositionAttribute),
            AX.kAXValueCGPointType,
        )
        size = self._ax_value(
            self.attribute(element, AX.kAXSizeAttribute),
            AX.kAXValueCGSizeType,
        )
        if position is None or size is None:
            return None
        return (
            round(position.x),
            round(position.y),
            round(size.width),
            round(size.height),
        )

    def identity(self, element) -> object:
        try:
            return (type(element).__name__, hash(element))
        except Exception:
            return (type(element).__name__, id(element))

    def is_settable(self, element, name: str) -> bool:
        try:
            error, value = AX.AXUIElementIsAttributeSettable(element, name, None)
            return error == 0 and bool(value)
        except Exception:
            return False

    def perform(self, element, action: str) -> None:
        error = AX.AXUIElementPerformAction(element, action)
        if error != 0:
            raise ComputerUseError(
                "element_not_actionable",
                f"Accessibility action failed: {action}",
                {"action": action, "axError": int(error)},
            )

    def set_attribute(self, element, name: str, value: Any) -> None:
        error = AX.AXUIElementSetAttributeValue(element, name, value)
        if error != 0:
            raise ComputerUseError(
                "element_not_actionable",
                f"Accessibility value update failed: {name}",
                {"attribute": name, "axError": int(error)},
            )

    @staticmethod
    def range_value(location: int, length: int):
        return AX.AXValueCreate(AX.kAXValueCFRangeType, (int(location), int(length)))

    @staticmethod
    def decode_range(value) -> tuple[int, int] | None:
        decoded = AccessibilityAdapter._ax_value(value, AX.kAXValueCFRangeType)
        if decoded is None:
            return None
        try:
            return int(decoded.location), int(decoded.length)
        except AttributeError:
            try:
                return int(decoded[0]), int(decoded[1])
            except (TypeError, ValueError, IndexError):
                return None

    @staticmethod
    def _ax_value(value, value_type):
        if value is None:
            return None
        try:
            ok, decoded = AX.AXValueGetValue(value, value_type, None)
            return decoded if ok else None
        except Exception:
            return None


class AccessibilitySnapshot:
    def __init__(
        self,
        target: TargetWindow,
        generation: int,
        elements: list[ElementRecord],
        limits: SnapshotLimits,
    ) -> None:
        self.target = target
        self.generation = int(generation)
        self.elements = elements
        self.limits = limits
        self._by_index = {record.index: record for record in elements}

    @classmethod
    def build(
        cls,
        adapter,
        target: TargetWindow,
        generation: int,
        limits: SnapshotLimits | None = None,
    ) -> "AccessibilitySnapshot":
        active_limits = limits or SnapshotLimits()
        application = adapter.application(target.pid)
        windows = adapter.windows(application)
        root = cls._matching_window(adapter, windows, target)
        if root is None:
            raise ComputerUseError(
                "window_not_found",
                "Accessibility window does not match the target window",
                {"pid": target.pid, "windowId": target.window_id},
            )

        elements: list[ElementRecord] = []
        seen: set[object] = set()

        def visit(element, depth: int) -> None:
            if depth > active_limits.max_depth or len(elements) >= active_limits.max_nodes:
                return
            identity = adapter.identity(element)
            if identity in seen:
                return
            seen.add(identity)
            elements.append(
                cls._record_for(
                    adapter,
                    target,
                    element,
                    index=len(elements),
                    depth=depth,
                    max_value_bytes=active_limits.max_value_bytes,
                )
            )
            for child in adapter.children(element):
                visit(child, depth + 1)

        visit(root, 0)
        return cls(target, generation, elements, active_limits)

    @staticmethod
    def _matching_window(adapter, windows: Iterable[Any], target: TargetWindow):
        candidates = list(windows)
        for window in candidates:
            bounds = adapter.bounds(window)
            if bounds is None:
                continue
            expected = (target.x, target.y, target.width, target.height)
            if all(abs(actual - wanted) <= 8 for actual, wanted in zip(bounds, expected)):
                return window
        return candidates[0] if len(candidates) == 1 else None

    @classmethod
    def _record_for(
        cls,
        adapter,
        target: TargetWindow,
        element,
        *,
        index: int,
        depth: int,
        max_value_bytes: int,
    ) -> ElementRecord:
        global_bounds = adapter.bounds(element)
        local_bounds = None
        if global_bounds is not None:
            local_bounds = (
                int(global_bounds[0] - target.x),
                int(global_bounds[1] - target.y),
                int(global_bounds[2]),
                int(global_bounds[3]),
            )
        role = adapter.role(element)
        subrole = cls._text(
            adapter.attribute(element, AX.kAXSubroleAttribute) or adapter.attribute(element, "subrole"),
            max_value_bytes,
        )
        title = cls._text(adapter.attribute(element, AX.kAXTitleAttribute) or adapter.attribute(element, "title"), max_value_bytes)
        description = cls._text(
            adapter.attribute(element, AX.kAXDescriptionAttribute) or adapter.attribute(element, "description"),
            max_value_bytes,
        )
        identifier = cls._text(
            adapter.attribute(element, AX.kAXIdentifierAttribute)
            or adapter.attribute(element, AX_DOM_IDENTIFIER_ATTRIBUTE)
            or adapter.attribute(element, "identifier"),
            max_value_bytes,
        )
        value = None
        if subrole != AX.kAXSecureTextFieldSubrole:
            value = cls._text(adapter.attribute(element, AX.kAXValueAttribute) or adapter.attribute(element, "value"), max_value_bytes)
        enabled_value = adapter.attribute(element, AX.kAXEnabledAttribute)
        if enabled_value is None:
            enabled_value = adapter.attribute(element, "enabled")
        enabled = True if enabled_value is None else bool(enabled_value)
        focused_value = adapter.attribute(element, AX.kAXFocusedAttribute)
        if focused_value is None:
            focused_value = adapter.attribute(element, "focused")
        focused = bool(focused_value)
        actions = tuple(sorted(adapter.actions(element)))
        settable = bool(adapter.is_settable(element, AX.kAXValueAttribute))
        fingerprint_payload = {
            "pid": target.pid,
            "windowId": target.window_id,
            "role": role,
            "subrole": subrole,
            "title": title,
            "description": description,
            "identifier": identifier,
            "bounds": local_bounds,
            "actions": actions,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return ElementRecord(
            index=index,
            depth=depth,
            role=role,
            title=title,
            description=description,
            identifier=identifier,
            value=value,
            enabled=enabled,
            settable=settable,
            actions=actions,
            bounds=local_bounds,
            fingerprint=fingerprint,
            raw=element,
            focused=focused,
            subrole=subrole,
        )

    @staticmethod
    def _text(value: Any, max_bytes: int) -> str | None:
        if value is None:
            return None
        text = str(value)
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        return encoded[:max_bytes].decode("utf-8", errors="ignore")

    def element(self, index: int) -> ElementRecord:
        try:
            return self._by_index[int(index)]
        except (KeyError, TypeError, ValueError):
            raise ComputerUseError(
                "stale_state",
                "Element index does not exist in the current application state",
                {"elementIndex": index, "generation": self.generation},
            ) from None

    def hit_test(
        self,
        local_x: float,
        local_y: float,
        required_actions: tuple[str, ...] = (),
    ) -> ElementRecord:
        candidates = []
        for record in self.elements:
            if not record.enabled or record.bounds is None:
                continue
            x, y, width, height = record.bounds
            if not (x <= local_x < x + width and y <= local_y < y + height):
                continue
            if required_actions and not any(action in record.actions for action in required_actions):
                continue
            candidates.append((width * height, -record.depth, record.index, record))
        if not candidates:
            raise ComputerUseError(
                "element_not_actionable",
                "No actionable element exists at the target coordinate",
                {"x": local_x, "y": local_y, "windowId": self.target.window_id},
            )
        return min(candidates)[3]

    def focused_editable(self) -> ElementRecord:
        editable_roles = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}
        focused = [record for record in self.elements if record.focused and record.role in editable_roles]
        if len(focused) == 1:
            return focused[0]
        if not focused:
            editable = [record for record in self.elements if record.role in editable_roles and record.enabled]
            if len(editable) == 1:
                return editable[0]
        raise ComputerUseError(
            "element_not_actionable",
            "No unique editable element is focused inside the target window",
            {"windowId": self.target.window_id},
        )

    def scrollbar_for(self, container: ElementRecord) -> ElementRecord | None:
        if container.bounds is None:
            return None
        left, top, width, height = container.bounds
        right = left + width
        bottom = top + height
        candidates = []
        for record in self.elements:
            if record.role != "AXScrollBar" or record.bounds is None or not record.settable:
                continue
            bar_left, bar_top, bar_width, bar_height = record.bounds
            bar_right = bar_left + bar_width
            bar_bottom = bar_top + bar_height
            overlaps = bar_left < right + 4 and bar_right > left - 4 and bar_top < bottom + 4 and bar_bottom > top - 4
            if overlaps:
                candidates.append((bar_width * bar_height, record))
        return min(candidates, default=(0, None), key=lambda item: item[0])[1]

    def scroll_button_for(self, container: ElementRecord, direction: str) -> ElementRecord | None:
        scrollbar = container if container.role == "AXScrollBar" else self.scrollbar_for(container)
        if scrollbar is None:
            return None
        try:
            start = next(index for index, record in enumerate(self.elements) if record.index == scrollbar.index)
        except StopIteration:
            return None
        descendants = []
        for record in self.elements[start + 1 :]:
            if record.depth <= scrollbar.depth:
                break
            if record.role == "AXButton" and record.enabled and "AXPress" in record.actions and record.bounds is not None:
                descendants.append(record)
        if not descendants:
            return None
        horizontal = direction.casefold() in {"left", "right"}
        def position(record: ElementRecord) -> float:
            left, top, width, height = record.bounds or (0, 0, 0, 0)
            return (left + width / 2) if horizontal else (top + height / 2)
        reverse = direction.casefold() in {"down", "right"}
        return sorted(descendants, key=position, reverse=reverse)[0]

    def revalidate(self, record: ElementRecord, adapter) -> None:
        current = self._record_for(
            adapter,
            self.target,
            record.raw,
            index=record.index,
            depth=record.depth,
            max_value_bytes=self.limits.max_value_bytes,
        )
        if current.fingerprint != record.fingerprint:
            raise ComputerUseError(
                "stale_state",
                "Element no longer matches the captured application state",
                {
                    "elementIndex": record.index,
                    "generation": self.generation,
                    "expected": record.fingerprint,
                    "actual": current.fingerprint,
                },
            )

    def serialize_text(self) -> str:
        lines = []
        used = 0
        for record in self.elements:
            label = record.description or record.title or record.identifier or ""
            metadata = []
            if record.value not in (None, ""):
                metadata.append(f"Value: {record.value}")
            if record.actions:
                metadata.append(f"Actions: {', '.join(record.actions)}")
            suffix = f", {', '.join(metadata)}" if metadata else ""
            indentation = "\t" * record.depth
            line = f"{indentation}{record.index} {record.role} {label}{suffix}".rstrip()
            encoded_size = len((line + "\n").encode("utf-8"))
            if used + encoded_size > self.limits.max_text_bytes:
                break
            lines.append(line)
            used += encoded_size
        return "\n".join(lines)

    def element_metadata(self) -> list[dict[str, Any]]:
        result = []
        for record in self.elements:
            bounds = None
            if record.bounds is not None:
                bounds = {
                    "x": record.bounds[0],
                    "y": record.bounds[1],
                    "width": record.bounds[2],
                    "height": record.bounds[3],
                }
            result.append(
                {
                    "index": record.index,
                    "role": record.role,
                    "subrole": record.subrole,
                    "title": record.title,
                    "description": record.description,
                    "identifier": record.identifier,
                    "enabled": record.enabled,
                    "settable": record.settable,
                    "focused": record.focused,
                    "actions": list(record.actions),
                    "bounds": bounds,
                    "fingerprint": record.fingerprint,
                }
            )
        return result
