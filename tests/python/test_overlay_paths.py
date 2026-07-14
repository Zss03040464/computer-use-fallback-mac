from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from runtime.cu_runtime.overlay import OverlayManager
from runtime.cu_runtime.session import SessionState


class FakeProcesses:
    def __init__(self):
        self.next_pid = 1000
        self.commands = {}
        self.running = set()

    def spawn(self, command):
        pid = self.next_pid
        self.next_pid += 1
        self.commands[pid] = list(command)
        self.running.add(pid)
        pid_path = Path(command[command.index("--pid") + 1])
        pid_path.write_text(str(pid), encoding="utf-8")
        return pid

    def is_running(self, pid):
        return pid in self.running

    def command(self, pid):
        return " ".join(self.commands.get(pid, []))

    def terminate(self, pid):
        self.running.discard(pid)

    def kill(self, pid):
        self.running.discard(pid)


class NeverReadyProcesses(FakeProcesses):
    def spawn(self, command):
        pid = self.next_pid
        self.next_pid += 1
        self.commands[pid] = list(command)
        self.running.add(pid)
        return pid


class OverlayPathsTest(unittest.TestCase):
    def test_two_sessions_start_and_stop_only_their_own_overlay(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            processes = FakeProcesses()
            first = SessionState.create(root, "overlay-a")
            second = SessionState.create(root, "overlay-b")
            first.set_cursor(10, 20, None)
            second.set_cursor(30, 40, None)
            first_manager = OverlayManager(first, processes=processes, python_path="python", script_path=root / "overlay.py")
            second_manager = OverlayManager(second, processes=processes, python_path="python", script_path=root / "overlay.py")

            first_status = first_manager.start()
            second_status = second_manager.start()

            self.assertNotEqual(first.cursor_path, second.cursor_path)
            self.assertNotEqual(first.overlay_pid_path, second.overlay_pid_path)
            self.assertNotEqual(first_status["pid"], second_status["pid"])
            self.assertIn("--owner-pid", processes.commands[first_status["pid"]])

            first_manager.stop()
            self.assertFalse(first_manager.status()["running"])
            self.assertTrue(second_manager.status()["running"])
            self.assertTrue(second.overlay_pid_path.exists())

    def test_start_timeout_terminates_the_process_it_spawned(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            processes = NeverReadyProcesses()
            session = SessionState.create(root, "overlay-timeout")
            session.set_cursor(10, 20, None)
            manager = OverlayManager(
                session,
                processes=processes,
                python_path="python",
                script_path=root / "overlay.py",
            )

            with self.assertRaisesRegex(Exception, "did not start"):
                manager.start()

            self.assertEqual(set(), processes.running)
