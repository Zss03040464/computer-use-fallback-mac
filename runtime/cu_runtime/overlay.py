from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from .errors import ComputerUseError
from .session import SessionState


class ProcessAdapter:
    def spawn(self, command: list[str]) -> int:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return int(process.pid)

    @staticmethod
    def is_running(pid: int) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @staticmethod
    def command(pid: int) -> str:
        result = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()

    @staticmethod
    def terminate(pid: int) -> None:
        os.kill(int(pid), signal.SIGTERM)

    @staticmethod
    def kill(pid: int) -> None:
        os.kill(int(pid), signal.SIGKILL)


class OverlayManager:
    def __init__(
        self,
        session: SessionState,
        *,
        processes: Any | None = None,
        python_path: str | None = None,
        script_path: Path | None = None,
    ) -> None:
        self.session = session
        self.processes = processes or ProcessAdapter()
        self.python_path = python_path or sys.executable
        self.script_path = Path(script_path or Path(__file__).resolve().parents[1] / "virtual_cursor_overlay.py")

    def status(self) -> dict[str, Any]:
        pid = self._read_pid()
        if pid is None or not self.processes.is_running(pid):
            self._unlink_pid()
            return {"running": False, "pid": None, "sessionId": self.session.session_id}
        command = self.processes.command(pid)
        required = [str(self.script_path), str(self.session.cursor_path), str(self.session.overlay_pid_path)]
        required.extend(["--owner-pid", str(os.getpid())])
        if not all(value in command for value in required):
            self._unlink_pid()
            return {"running": False, "pid": None, "sessionId": self.session.session_id}
        return {"running": True, "pid": pid, "sessionId": self.session.session_id}

    def start(self) -> dict[str, Any]:
        current = self.status()
        if current["running"]:
            return current
        if not self.session.cursor_path.exists():
            self.session.set_cursor(0, 0, None)
        spawned_pid = self.processes.spawn(
            [
                self.python_path,
                str(self.script_path),
                "--session",
                self.session.session_id,
                "--state",
                str(self.session.cursor_path),
                "--pid",
                str(self.session.overlay_pid_path),
                "--owner-pid",
                str(os.getpid()),
            ]
        )
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            status = self.status()
            if status["running"]:
                return status
            time.sleep(0.02)
        self._terminate_spawned(spawned_pid)
        raise ComputerUseError(
            "runtime_unavailable",
            "Session virtual cursor overlay did not start",
            {"sessionId": self.session.session_id},
        )

    def _terminate_spawned(self, pid: int) -> None:
        if not self.processes.is_running(pid):
            return
        try:
            self.processes.terminate(pid)
        except Exception:
            pass
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline and self.processes.is_running(pid):
            time.sleep(0.02)
        if self.processes.is_running(pid):
            try:
                self.processes.kill(pid)
            except Exception:
                pass

    def stop(self) -> dict[str, Any]:
        status = self.status()
        if not status["running"]:
            return status
        pid = int(status["pid"])
        try:
            self.processes.terminate(pid)
        except Exception:
            pass
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline and self.processes.is_running(pid):
            time.sleep(0.02)
        if self.processes.is_running(pid):
            try:
                self.processes.kill(pid)
            except Exception:
                pass
        self._unlink_pid()
        return {"running": False, "pid": None, "sessionId": self.session.session_id}

    def _read_pid(self) -> int | None:
        try:
            return int(self.session.overlay_pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    def _unlink_pid(self) -> None:
        try:
            self.session.overlay_pid_path.unlink()
        except FileNotFoundError:
            pass
