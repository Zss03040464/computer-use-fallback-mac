from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import fcntl
import json
from pathlib import Path
import re
import secrets
import time
from typing import Any, Iterator

from .cursor_feedback import CursorFeedback
from .errors import ComputerUseError


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


@dataclass
class SessionState:
    root: Path
    session_id: str
    cursor_x: int = 0
    cursor_y: int = 0
    pressed_button: str | None = None
    pressed_target_key: str | None = None
    pressed_element_index: int | None = None
    bound_target: dict[str, Any] | None = None
    generation: int = 0
    snapshots: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, root: Path, session_id: str | None = None) -> "SessionState":
        value = session_id or secrets.token_hex(16)
        if not SESSION_ID_PATTERN.fullmatch(value):
            raise ComputerUseError(
                "invalid_session",
                "Session identifier contains unsupported characters",
                {"sessionId": value},
            )
        state = cls(root=Path(root), session_id=value)
        state.directory.mkdir(parents=True, exist_ok=True)
        return state

    @property
    def directory(self) -> Path:
        return self.root / "sessions" / self.session_id

    @property
    def cursor_path(self) -> Path:
        return self.directory / "cursor.json"

    @property
    def overlay_pid_path(self) -> Path:
        return self.directory / "overlay.pid"

    @property
    def overlay_lock_path(self) -> Path:
        return self.directory / "overlay.lock"

    def set_cursor(self, x: int, y: int, button: str | None) -> None:
        self.cursor_x = int(x)
        self.cursor_y = int(y)
        self.pressed_button = button
        payload = {
            "x": self.cursor_x,
            "y": self.cursor_y,
            "button": self.pressed_button,
            "sessionId": self.session_id,
        }
        temporary = self.cursor_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.cursor_path)

    def set_cursor_display(
        self,
        x: int,
        y: int,
        button: str | None,
        display_x: int,
        display_y: int,
        *,
        target_bundle_id: str | None = None,
        target_pid: int | None = None,
        target_window_id: int | None = None,
        action: str | None = None,
        phase: str | None = None,
        updated_at_ms: int | None = None,
    ) -> None:
        self.cursor_x = int(x)
        self.cursor_y = int(y)
        self.pressed_button = button
        payload = {
            "x": self.cursor_x,
            "y": self.cursor_y,
            "displayX": int(display_x),
            "displayY": int(display_y),
            "button": self.pressed_button,
            "sessionId": self.session_id,
        }
        if (
            target_bundle_id is not None
            and target_pid is not None
            and target_window_id is not None
            and action is not None
            and phase is not None
            and updated_at_ms is not None
        ):
            payload.update(
                {
                    "targetBundleId": str(target_bundle_id),
                    "targetPid": int(target_pid),
                    "targetWindowId": int(target_window_id),
                    "action": str(action),
                    "phase": str(phase),
                    "updatedAtMs": int(updated_at_ms),
                }
            )
        temporary = self.cursor_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.cursor_path)

    def cursor_tuple(self) -> tuple[int, int, str | None]:
        return self.cursor_x, self.cursor_y, self.pressed_button

    def cursor_feedback(self) -> CursorFeedback | None:
        try:
            value = json.loads(self.cursor_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return CursorFeedback.from_mapping(value)

    @contextmanager
    def lock_target(
        self,
        bundle_id: str,
        window_id: int,
        timeout: float = 2.0,
    ) -> Iterator[None]:
        safe_bundle = re.sub(r"[^A-Za-z0-9_.-]", "_", bundle_id)
        lock_path = self.root / "locks" / f"{safe_bundle}-{int(window_id)}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as handle:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ComputerUseError(
                            "target_busy",
                            "Target is controlled by another session",
                            {"bundleId": bundle_id, "windowId": int(window_id)},
                        )
                    time.sleep(0.02)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
