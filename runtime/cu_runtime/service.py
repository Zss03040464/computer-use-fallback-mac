from __future__ import annotations

import base64
from dataclasses import replace
import os
import time
from typing import Any

from .accessibility import AccessibilityAdapter, AccessibilitySnapshot
from .actions import ActionRouter
from .capture import WindowCapture
from .cursor_feedback import composite_cursor_png
from .errors import ComputerUseError
from .overlay import OverlayManager
from .session import SessionState
from .targets import TargetResolver


class RuntimeService:
    def __init__(
        self,
        session: SessionState,
        resolver: TargetResolver | Any | None = None,
        capture: WindowCapture | Any | None = None,
        snapshot_factory: Any | None = None,
        adapter: AccessibilityAdapter | Any | None = None,
        action_router: ActionRouter | Any | None = None,
        overlay_manager: OverlayManager | Any | None = None,
    ):
        self.session = session
        self._resolver = resolver
        self._capture = capture
        self._snapshot_factory = snapshot_factory
        self._adapter = adapter or AccessibilityAdapter()
        self._action_router = action_router
        self._overlay_manager = overlay_manager

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = TargetResolver()
        return self._resolver

    @property
    def capture(self):
        if self._capture is None:
            self._capture = WindowCapture()
        return self._capture

    def build_snapshot(self, target, generation: int):
        if self._snapshot_factory is not None:
            return self._snapshot_factory(target, generation)
        return AccessibilitySnapshot.build(
            self._adapter,
            target,
            generation,
        )

    @property
    def action_router(self):
        if self._action_router is None:
            self._action_router = ActionRouter(self._adapter)
        return self._action_router

    @property
    def overlay_manager(self):
        if self._overlay_manager is None:
            self._overlay_manager = OverlayManager(self.session)
        return self._overlay_manager

    def handle(self, command: str, payload: dict[str, Any]) -> Any:
        if command == "runtime_info":
            return {
                "pid": os.getpid(),
                "sessionId": self.session.session_id,
                "sessionDirectory": str(self.session.directory),
            }
        if command == "lock_probe":
            with self.session.lock_target(
                str(payload["bundleId"]),
                int(payload["windowId"]),
                timeout=float(payload.get("timeoutMs", 2000)) / 1000.0,
            ):
                time.sleep(max(0, int(payload.get("holdMs", 0))) / 1000.0)
            return {"locked": True}
        if command == "list_apps":
            return self.resolver.list_apps()
        if command == "list_windows":
            return self.resolver.list_windows(payload.get("app"))
        if command == "get_window_capture":
            target = self.resolver.resolve(
                str(payload["app"]),
                window_id=payload.get("windowId"),
                launch=bool(payload.get("launch", True)),
            )
            result = self.capture.capture(target)
            self.session.bound_target = target.to_dict()
            return {
                **result.metadata(),
                "base64": base64.b64encode(result.png).decode("ascii"),
            }
        if command == "get_app_state":
            target = self.resolver.resolve(
                str(payload["app"]),
                window_id=payload.get("windowId"),
                launch=bool(payload.get("launch", True)),
            )
            capture_result = self.capture.capture(target)
            rendered_png, cursor_feedback = composite_cursor_png(
                capture_result.png,
                self.session.cursor_feedback(),
                target,
                capture_result.scale_x,
                capture_result.scale_y,
            )
            capture_result = replace(capture_result, png=rendered_png)
            self.session.generation += 1
            snapshot = self.build_snapshot(target, self.session.generation)
            target_key = f"{target.bundle_id}:{target.window_id}"
            self.session.bound_target = target.to_dict()
            self.session.snapshots[target_key] = {
                "target": target,
                "capture": capture_result,
                "snapshot": snapshot,
            }
            return {
                "app": target.path,
                "target": target.to_dict(),
                "generation": self.session.generation,
                "text": snapshot.serialize_text(),
                "elements": snapshot.element_metadata() if hasattr(snapshot, "element_metadata") else [],
                "cursorFeedback": cursor_feedback,
                "screenshot": {
                    **capture_result.metadata(),
                    "base64": base64.b64encode(capture_result.png).decode("ascii"),
                },
            }
        if command == "click":
            state = self._target_state(payload)
            target = state["target"]
            with self.session.lock_target(target.bundle_id, target.window_id):
                result = self.action_router.click(
                    target,
                    state["snapshot"],
                    state["capture"],
                    element_index=payload.get("element_index"),
                    x=payload.get("x"),
                    y=payload.get("y"),
                    button=str(payload.get("button") or "left"),
                    click_count=int(payload.get("click_count") or 1),
                )
            return self._commit_cursor_feedback(state, result, phase="released", button=None)
        if command == "perform_secondary_action":
            state = self._target_state(payload)
            target = state["target"]
            with self.session.lock_target(target.bundle_id, target.window_id):
                result = self.action_router.perform_secondary_action(
                    target,
                    state["snapshot"],
                    int(payload["element_index"]),
                    str(payload["action"]),
                )
            return result.to_dict()
        if command == "set_value":
            state = self._target_state(payload)
            target = state["target"]
            with self.session.lock_target(target.bundle_id, target.window_id):
                result = self.action_router.set_value(
                    target,
                    state["snapshot"],
                    int(payload["element_index"]),
                    str(payload.get("value") or ""),
                )
            return result.to_dict()
        if command == "type_text":
            state = self._target_state(payload)
            target = state["target"]
            with self.session.lock_target(target.bundle_id, target.window_id):
                result = self.action_router.type_text(
                    target,
                    state["snapshot"],
                    str(payload.get("text") or ""),
                    element_index=payload.get("element_index"),
                )
            return result.to_dict()
        if command == "select_text":
            state = self._target_state(payload)
            target = state["target"]
            with self.session.lock_target(target.bundle_id, target.window_id):
                result = self.action_router.select_text(
                    target,
                    state["snapshot"],
                    int(payload["element_index"]),
                    str(payload.get("text") or ""),
                    prefix=payload.get("prefix"),
                    suffix=payload.get("suffix"),
                    selection_type=str(payload.get("selection_type") or "text"),
                )
            return result.to_dict()
        if command == "press_key":
            state = self._target_state(payload)
            target = state["target"]
            with self.session.lock_target(target.bundle_id, target.window_id):
                result = self.action_router.press_key(
                    target,
                    state["snapshot"],
                    str(payload["key"]),
                    modifiers=list(payload.get("modifiers") or []),
                    element_index=payload.get("element_index"),
                )
            return result.to_dict()
        if command == "scroll":
            state = self._target_state(payload)
            target = state["target"]
            with self.session.lock_target(target.bundle_id, target.window_id):
                result = self.action_router.scroll(
                    target,
                    state["snapshot"],
                    state["capture"],
                    element_index=payload.get("element_index"),
                    x=payload.get("x"),
                    y=payload.get("y"),
                    direction=str(payload.get("direction") or "down"),
                    pages=int(payload.get("pages") or 1),
                    delta_x=int(payload.get("delta_x") or 0),
                    delta_y=int(payload.get("delta_y") or 0),
                )
            return self._commit_cursor_feedback(state, result, phase="released", button=None)
        if command == "drag":
            state = self._target_state(payload)
            target = state["target"]
            with self.session.lock_target(target.bundle_id, target.window_id):
                result = self.action_router.drag(
                    target,
                    state["snapshot"],
                    state["capture"],
                    element_index=payload.get("element_index"),
                    from_x=float(payload["from_x"]),
                    from_y=float(payload["from_y"]),
                    to_x=float(payload["to_x"]),
                    to_y=float(payload["to_y"]),
                    button=str(payload.get("button") or "left"),
                )
            return self._commit_cursor_feedback(state, result, phase="released", button=None)
        if command in {"mouse_down", "mouse_up"}:
            state = self._target_state(payload)
            target = state["target"]
            pressed = command == "mouse_down"
            button = str(payload.get("button") or self.session.pressed_button or "left")
            target_key = f"{target.bundle_id}:{target.window_id}"
            element_index = int(payload["element_index"])
            if pressed and self.session.pressed_button is not None:
                raise ComputerUseError(
                    "invalid_request",
                    "A mouse button is already pending in this session",
                    {"button": self.session.pressed_button},
                )
            if not pressed and (
                self.session.pressed_button is None
                or self.session.pressed_target_key != target_key
                or self.session.pressed_element_index != element_index
                or self.session.pressed_button != button
            ):
                raise ComputerUseError(
                    "invalid_request",
                    "Mouse up does not match this session's pending mouse down",
                    {"targetKey": target_key, "elementIndex": element_index, "button": button},
                )
            with self.session.lock_target(target.bundle_id, target.window_id):
                result = self.action_router.mouse_button(
                    target,
                    state["snapshot"],
                    state["capture"],
                    element_index,
                    float(payload["x"]),
                    float(payload["y"]),
                    button,
                    pressed,
                )
            self.session.pressed_target_key = target_key if pressed else None
            self.session.pressed_element_index = element_index if pressed else None
            return self._commit_cursor_feedback(
                state,
                result,
                phase="pressed" if pressed else "released",
                button=button if pressed else None,
            )
        if command == "cursor_position":
            x, y, button = self.session.cursor_tuple()
            return {"x": x, "y": y, "button": button}
        if command == "set_cursor":
            x = int(payload["x"])
            y = int(payload["y"])
            if self.session.bound_target:
                bounds = self.session.bound_target["bounds"]
                target_key = (
                    f"{self.session.bound_target['bundleId']}:"
                    f"{int(self.session.bound_target['windowId'])}"
                )
                state = self.session.snapshots.get(target_key)
                if state is not None:
                    display_x, display_y = state["capture"].image_to_global(x, y)
                else:
                    display_x = int(bounds["x"]) + x
                    display_y = int(bounds["y"]) + y
                self.session.set_cursor_display(
                    x,
                    y,
                    payload.get("button"),
                    display_x,
                    display_y,
                    target_bundle_id=str(self.session.bound_target["bundleId"]),
                    target_pid=int(self.session.bound_target["pid"]),
                    target_window_id=int(self.session.bound_target["windowId"]),
                    action="mouse_move",
                    phase="steady",
                    updated_at_ms=int(time.time() * 1000),
                )
            else:
                self.session.set_cursor(x, y, payload.get("button"))
            result = {"x": self.session.cursor_x, "y": self.session.cursor_y, "button": self.session.pressed_button}
            result["cursorFeedback"] = self._start_overlay_feedback(persisted=self.session.bound_target is not None)
            return result
        if command == "virtual_cursor_overlay":
            action = str(payload.get("action") or "status")
            if action == "start":
                return self.overlay_manager.start()
            if action == "stop":
                return self.overlay_manager.stop()
            if action == "status":
                return self.overlay_manager.status()
            raise ComputerUseError("invalid_request", f"Unsupported overlay action: {action}", {"action": action})
        if command == "shutdown":
            if self._overlay_manager is not None:
                self._overlay_manager.stop()
            return {"stopping": True}
        raise ComputerUseError(
            "unknown_command",
            f"Unknown runtime command: {command}",
            {"command": command},
        )

    def _target_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("app") is not None:
            target = self.resolver.resolve(
                str(payload["app"]),
                window_id=payload.get("windowId"),
                launch=False,
            )
            key = f"{target.bundle_id}:{target.window_id}"
        elif self.session.bound_target is not None:
            bundle_id = str(self.session.bound_target["bundleId"])
            window_id = int(self.session.bound_target["windowId"])
            key = f"{bundle_id}:{window_id}"
        else:
            raise ComputerUseError(
                "target_required",
                "Action requires an explicit app/window or a preceding get_app_state call",
                {"recovery": ["list_apps", "get_app_state", "action"]},
            )
        state = self.session.snapshots.get(key)
        if state is None:
            raise ComputerUseError(
                "stale_state",
                "No current application state exists for the requested target",
                {"targetKey": key, "recovery": "Call get_app_state again"},
            )
        return state

    def _commit_cursor_feedback(
        self,
        state: dict[str, Any],
        result: Any,
        *,
        phase: str,
        button: str | None,
    ) -> dict[str, Any]:
        payload = result.to_dict()
        point = getattr(result, "global_point", None)
        if point is None:
            payload["cursorFeedback"] = {
                "persisted": False,
                "overlay": None,
                "warning": None,
                "reason": "point_unavailable",
            }
            return payload

        target = state["target"]
        try:
            image_x, image_y = state["capture"].global_to_image(*point)
            self.session.set_cursor_display(
                image_x,
                image_y,
                button,
                int(point[0]),
                int(point[1]),
                target_bundle_id=target.bundle_id,
                target_pid=target.pid,
                target_window_id=target.window_id,
                action=result.action,
                phase=phase,
                updated_at_ms=int(time.time() * 1000),
            )
        except Exception as error:
            payload["cursorFeedback"] = {
                "persisted": False,
                "overlay": None,
                "warning": self._feedback_warning(error, "cursor_feedback_unavailable"),
                "reason": "persistence_failed",
            }
            return payload

        payload["cursorFeedback"] = self._start_overlay_feedback(persisted=True)
        payload["cursorFeedback"]["delivery"] = str(getattr(result, "delivery", "delivered"))
        return payload

    def _start_overlay_feedback(self, *, persisted: bool) -> dict[str, Any]:
        feedback = {"persisted": persisted, "overlay": None, "warning": None, "reason": None}
        if not persisted:
            feedback["reason"] = "target_unbound"
            return feedback
        try:
            feedback["overlay"] = self.overlay_manager.start()
        except Exception as error:
            feedback["warning"] = self._feedback_warning(error, "cursor_overlay_unavailable")
        return feedback

    @staticmethod
    def _feedback_warning(error: Exception, fallback_code: str) -> dict[str, Any]:
        if isinstance(error, ComputerUseError):
            return error.to_dict()
        return {"code": fallback_code, "message": str(error), "details": {}}
