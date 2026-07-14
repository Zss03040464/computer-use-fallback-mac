from pathlib import Path
from unittest.mock import patch
import unittest

from runtime import mac_helper


class LegacyOverlayOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.previous_owner = mac_helper.LEGACY_OVERLAY_OWNER_PID
        mac_helper.LEGACY_OVERLAY_OWNER_PID = 4321

    def tearDown(self):
        mac_helper.LEGACY_OVERLAY_OWNER_PID = self.previous_owner

    def command(self, *, session="legacy-global", owner=4321, state=None, pid_path=None):
        state = state or mac_helper.VIRTUAL_MOUSE_STATE_PATH
        pid_path = pid_path or mac_helper.VIRTUAL_CURSOR_OVERLAY_PID_PATH
        return (
            f"python {mac_helper.VIRTUAL_CURSOR_OVERLAY_SCRIPT} "
            f"--session {session} --state {state} --pid {pid_path} --owner-pid {owner}"
        )

    def test_only_exact_legacy_overlay_command_is_owned(self):
        self.assertTrue(mac_helper.legacy_overlay_command_matches(self.command()))
        self.assertFalse(mac_helper.legacy_overlay_command_matches(self.command(session="other-session")))
        self.assertFalse(mac_helper.legacy_overlay_command_matches(self.command(owner=9999)))
        self.assertFalse(
            mac_helper.legacy_overlay_command_matches(
                self.command(state=Path("/tmp/other-cursor.json"))
            )
        )
        self.assertFalse(
            mac_helper.legacy_overlay_command_matches(
                self.command(pid_path=Path("/tmp/other-overlay.pid"))
            )
        )

    def test_invalid_owner_pid_never_matches(self):
        mac_helper.LEGACY_OVERLAY_OWNER_PID = 1
        self.assertFalse(mac_helper.legacy_overlay_command_matches(self.command(owner=1)))

    def test_cleanup_never_signals_another_session_overlay(self):
        other_session = self.command(session="other-session")
        with (
            patch.object(mac_helper, "pid_is_running", return_value=True),
            patch.object(mac_helper, "process_command", return_value=other_session),
            patch.object(mac_helper.os, "kill") as kill,
        ):
            mac_helper.kill_overlay_pids([9876])
        kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
