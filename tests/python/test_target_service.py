import base64
from io import BytesIO
import unittest

from PIL import Image

from runtime.cu_runtime.capture import CaptureResult
from runtime.cu_runtime.service import RuntimeService
from runtime.cu_runtime.session import SessionState
from runtime.cu_runtime.targets import TargetWindow


class FakeResolver:
    def __init__(self, target):
        self.target = target

    def list_apps(self):
        return [{"bundleId": self.target.bundle_id, "displayName": self.target.display_name}]

    def list_windows(self, app=None):
        return [{"windowId": self.target.window_id, "pid": self.target.pid, "title": self.target.title}]

    def resolve(self, app, window_id=None, launch=True):
        return self.target


class FakeCapture:
    def __init__(self, result):
        self.result = result

    def capture(self, target):
        return self.result


class FakeSnapshot:
    def __init__(self, generation):
        self.generation = generation

    def serialize_text(self):
        return "0 AXWindow Target\n\t1 AXButton Increment"


class FakeSnapshotFactory:
    def __init__(self):
        self.generations = []

    def __call__(self, target, generation):
        self.generations.append(generation)
        return FakeSnapshot(generation)


class TargetServiceTest(unittest.TestCase):
    @staticmethod
    def _png(width=230, height=408):
        image = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_lists_apps_and_returns_window_capture_metadata(self):
        target = TargetWindow(
            app="Calculator",
            bundle_id="com.apple.calculator",
            display_name="Calculator",
            path="/System/Applications/Calculator.app",
            pid=501,
            window_id=9001,
            title="Calculator",
            x=10,
            y=20,
            width=230,
            height=408,
        )
        capture = CaptureResult(b"png", 230, 408, 230, 408, 1.0, 1.0, "fake", target)
        session = SessionState.create(self._temporary_root(), "service-targets")
        service = RuntimeService(session, resolver=FakeResolver(target), capture=FakeCapture(capture))

        self.assertEqual("com.apple.calculator", service.handle("list_apps", {})[0]["bundleId"])
        self.assertEqual(9001, service.handle("list_windows", {"app": "Calculator"})[0]["windowId"])
        result = service.handle("get_window_capture", {"app": "Calculator"})
        self.assertEqual(base64.b64encode(b"png").decode("ascii"), result["base64"])
        self.assertEqual(9001, result["target"]["windowId"])

    def test_get_app_state_binds_target_snapshot_and_generation(self):
        target = TargetWindow(
            app="Calculator",
            bundle_id="com.apple.calculator",
            display_name="Calculator",
            path="/System/Applications/Calculator.app",
            pid=501,
            window_id=9001,
            title="Calculator",
            x=10,
            y=20,
            width=230,
            height=408,
        )
        capture = CaptureResult(b"png", 230, 408, 230, 408, 1.0, 1.0, "fake", target)
        factory = FakeSnapshotFactory()
        session = SessionState.create(self._temporary_root(), "service-state")
        service = RuntimeService(
            session,
            resolver=FakeResolver(target),
            capture=FakeCapture(capture),
            snapshot_factory=factory,
        )

        result = service.handle("get_app_state", {"app": "Calculator"})

        self.assertEqual(1, result["generation"])
        self.assertEqual("0 AXWindow Target\n\t1 AXButton Increment", result["text"])
        self.assertEqual(9001, session.bound_target["windowId"])
        self.assertIn("com.apple.calculator:9001", session.snapshots)
        self.assertEqual([1], factory.generations)

    def test_get_app_state_composites_matching_session_feedback(self):
        target = TargetWindow(
            "Calculator", "com.apple.calculator", "Calculator",
            "/System/Applications/Calculator.app", 501, 9001, "Calculator",
            10, 20, 230, 408,
        )
        original = self._png()
        capture = CaptureResult(original, 230, 408, 230, 408, 1.0, 1.0, "fake", target)
        session = SessionState.create(self._temporary_root(), "matching-cursor")
        session.set_cursor_display(
            20, 20, None, 30, 40,
            target_bundle_id=target.bundle_id,
            target_pid=target.pid,
            target_window_id=target.window_id,
            action="AXPress",
            phase="released",
            updated_at_ms=1_000,
        )
        service = RuntimeService(
            session,
            resolver=FakeResolver(target),
            capture=FakeCapture(capture),
            snapshot_factory=FakeSnapshotFactory(),
        )

        state = service.handle("get_app_state", {"app": "Calculator"})

        self.assertTrue(state["cursorFeedback"]["drawn"])
        self.assertEqual([20, 20], state["cursorFeedback"]["imagePoint"])
        self.assertNotEqual(original, base64.b64decode(state["screenshot"]["base64"]))

    def test_get_app_state_does_not_composite_other_window_feedback(self):
        target = TargetWindow(
            "Calculator", "com.apple.calculator", "Calculator",
            "/System/Applications/Calculator.app", 501, 9001, "Calculator",
            10, 20, 230, 408,
        )
        original = self._png()
        capture = CaptureResult(original, 230, 408, 230, 408, 1.0, 1.0, "fake", target)
        session = SessionState.create(self._temporary_root(), "mismatched-cursor")
        session.set_cursor_display(
            20, 20, None, 30, 40,
            target_bundle_id=target.bundle_id,
            target_pid=target.pid,
            target_window_id=999,
            action="AXPress",
            phase="released",
            updated_at_ms=1_000,
        )
        service = RuntimeService(
            session,
            resolver=FakeResolver(target),
            capture=FakeCapture(capture),
            snapshot_factory=FakeSnapshotFactory(),
        )

        state = service.handle("get_app_state", {"app": "Calculator"})

        self.assertFalse(state["cursorFeedback"]["drawn"])
        self.assertEqual("target_mismatch", state["cursorFeedback"]["reason"])
        self.assertEqual(original, base64.b64decode(state["screenshot"]["base64"]))

    def _temporary_root(self):
        self.addCleanup(self._cleanup_root)
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name)

    def _cleanup_root(self):
        self._tmp.cleanup()
