from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from runtime.cu_runtime.session import SessionState


class SessionStateTest(unittest.TestCase):
    def test_two_sessions_never_share_paths_or_cursor_state(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = SessionState.create(root, "session-a")
            second = SessionState.create(root, "session-b")
            first.set_cursor(12, 34, None)
            second.set_cursor(90, 80, "left")
            self.assertNotEqual(first.directory, second.directory)
            self.assertEqual((12, 34, None), first.cursor_tuple())
            self.assertEqual((90, 80, "left"), second.cursor_tuple())
            self.assertNotEqual(first.cursor_path, second.cursor_path)

    def test_target_lock_times_out_for_second_session(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = SessionState.create(root, "session-a")
            second = SessionState.create(root, "session-b")
            with first.lock_target("com.example.app", 7):
                with self.assertRaisesRegex(Exception, "another session"):
                    with second.lock_target("com.example.app", 7, timeout=0.05):
                        pass

    def test_target_feedback_is_persisted_and_read_back(self):
        with TemporaryDirectory() as tmp:
            session = SessionState.create(Path(tmp), "feedback")
            session.set_cursor_display(
                60,
                50,
                None,
                130,
                225,
                target_bundle_id="com.example.harness",
                target_pid=77,
                target_window_id=88,
                action="AXPress",
                phase="released",
                updated_at_ms=1_000,
            )
            value = json.loads(session.cursor_path.read_text(encoding="utf-8"))
            self.assertEqual("com.example.harness", value["targetBundleId"])
            self.assertEqual(88, value["targetWindowId"])
            self.assertEqual(77, value["targetPid"])
            self.assertEqual("released", value["phase"])
            feedback = session.cursor_feedback()
            self.assertEqual((130, 225), (feedback.display_x, feedback.display_y))
