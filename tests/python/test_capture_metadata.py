import unittest

from runtime.cu_runtime.capture import CaptureFrame, WindowCapture
from runtime.cu_runtime.targets import TargetWindow


class FakeBackend:
    name = "fake-window"

    def __init__(self, frame=None, error=None):
        self.frame = frame
        self.error = error
        self.targets = []

    def capture(self, target):
        self.targets.append(target.window_id)
        if self.error:
            raise self.error
        return self.frame


class CaptureMetadataTest(unittest.TestCase):
    def setUp(self):
        self.target = TargetWindow(
            app="Calculator",
            bundle_id="com.apple.calculator",
            display_name="Calculator",
            path="/System/Applications/Calculator.app",
            pid=501,
            window_id=9001,
            title="Calculator",
            x=100,
            y=200,
            width=230,
            height=408,
        )

    def test_capture_reports_scale_and_maps_image_coordinates_to_target_window(self):
        backend = FakeBackend(CaptureFrame(b"png", 460, 816, "fake-window"))
        result = WindowCapture([backend]).capture(self.target)

        self.assertEqual((460, 816), (result.pixel_width, result.pixel_height))
        self.assertEqual((2.0, 2.0), (result.scale_x, result.scale_y))
        self.assertEqual((150, 250), result.image_to_global(100, 100))
        self.assertEqual((50, 50), result.image_to_logical(100, 100))
        self.assertEqual((100, 100), result.global_to_image(150, 250))
        self.assertEqual([9001], backend.targets)

    def test_capture_falls_back_to_next_app_window_backend(self):
        first = FakeBackend(error=RuntimeError("preferred failed"))
        second = FakeBackend(CaptureFrame(b"fallback", 230, 408, "core-graphics"))

        result = WindowCapture([first, second]).capture(self.target)

        self.assertEqual("core-graphics", result.backend)
        self.assertEqual(b"fallback", result.png)
