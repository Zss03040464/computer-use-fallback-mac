import base64
import io
import unittest

from PIL import Image

from runtime.compat_services.displays import DisplayInfo
from runtime.compat_services.errors import CompatServiceError
from runtime.compat_services.service import CompatService
from runtime.compat_worker import response_for


class FakeDisplayProvider:
    def __init__(self):
        self.display = DisplayInfo(
            display_id=7,
            x=10,
            y=5,
            logical_width=100,
            logical_height=50,
            pixel_width=200,
            pixel_height=100,
        )

    def active_displays(self):
        return [self.display]

    def main_display_id(self):
        return self.display.display_id


class FakeCaptureAdapter:
    def capture(self, display):
        self.last_display = display
        return Image.new("RGB", (display.pixel_width, display.pixel_height), "navy")


class FakeClipboardAdapter:
    def __init__(self):
        self.value = "initial"

    def read_text(self):
        return self.value

    def write_text(self, value):
        self.value = value


class FakePermissionAdapter:
    def inspect(self):
        return {"accessibility": True, "screenRecording": False}


class FakeOcrAdapter:
    def recognize(self, image):
        self.last_size = image.size
        return ["Please VERIFY you are human", "安全验证"]


class CompatServiceTest(unittest.TestCase):
    def setUp(self):
        self.displays = FakeDisplayProvider()
        self.capture = FakeCaptureAdapter()
        self.clipboard = FakeClipboardAdapter()
        self.permissions = FakePermissionAdapter()
        self.ocr = FakeOcrAdapter()
        self.service = CompatService(
            display_provider=self.displays,
            capture_adapter=self.capture,
            clipboard_adapter=self.clipboard,
            permission_adapter=self.permissions,
            ocr_adapter=self.ocr,
        )

    def test_dispatch_is_allowlisted_and_unknown_commands_are_structured(self):
        with self.assertRaises(CompatServiceError) as caught:
            self.service.handle("run_arbitrary_function", {"name": "system"})

        self.assertEqual("unknown_command", caught.exception.code)
        self.assertEqual({"command": "run_arbitrary_function"}, caught.exception.details)

    def test_permissions_have_stable_boolean_fields(self):
        self.assertEqual(
            {"accessibility": True, "screenRecording": False},
            self.service.handle("check_permissions", {}),
        )

    def test_screenshot_resizes_proportionally_and_returns_jpeg(self):
        result = self.service.handle("screenshot", {"displayId": 7, "targetWidth": 80})

        self.assertEqual(7, result["displayId"])
        self.assertEqual((80, 40), (result["width"], result["height"]))
        self.assertEqual((100, 50), (result["displayWidth"], result["displayHeight"]))
        self.assertEqual((200, 100), (result["pixelWidth"], result["pixelHeight"]))
        self.assertEqual("image/jpeg", result["mimeType"])
        image = Image.open(io.BytesIO(base64.b64decode(result["base64"])))
        self.assertEqual((80, 40), image.size)

    def test_screenshot_region_uses_logical_coordinates_and_bounded_crop(self):
        result = self.service.handle(
            "screenshot_region",
            {
                "displayId": 7,
                "x": 10,
                "y": 5,
                "width": 25,
                "height": 15,
                "targetHeight": 60,
            },
        )

        self.assertEqual((100, 60), (result["width"], result["height"]))
        self.assertEqual(
            {"x": 10, "y": 5, "width": 25, "height": 15},
            result["region"],
        )

    def test_out_of_bounds_region_fails_before_capture_result_is_returned(self):
        with self.assertRaises(CompatServiceError) as caught:
            self.service.handle(
                "screenshot_region",
                {"displayId": 7, "x": 99, "y": 49, "width": 2, "height": 2},
            )
        self.assertEqual("invalid_region", caught.exception.code)

    def test_clipboard_round_trip_preserves_plain_text(self):
        secret = "SENTINEL-clipboard-private-value"
        self.assertEqual({"written": True}, self.service.handle("write_clipboard", {"text": secret}))
        self.assertEqual(secret, self.service.handle("read_clipboard", {}))

    def test_coordinate_mapping_anchors_at_display_origin(self):
        physical = self.service.handle(
            "map_coordinates",
            {"displayId": 7, "x": 20, "y": 15, "to": "physical"},
        )
        self.assertEqual({"displayId": 7, "x": 30, "y": 25, "space": "physical"}, physical)

        logical = self.service.handle(
            "map_coordinates",
            {"displayId": 7, "x": 30, "y": 25, "to": "logical"},
        )
        self.assertEqual({"displayId": 7, "x": 20, "y": 15, "space": "logical"}, logical)

    def test_captcha_detection_returns_matches_without_full_ocr_text(self):
        result = self.service.handle("detect_captcha", {"displayId": 7})

        self.assertEqual(True, result["detected"])
        self.assertEqual(["verify", "验证"], result["matches"])
        self.assertNotIn("text", result)
        self.assertNotIn("Please VERIFY you are human", repr(result))

    def test_worker_response_does_not_echo_sensitive_payload_in_errors(self):
        secret = "SENTINEL-worker-private-value"
        response = response_for(
            self.service,
            {"id": 9, "command": "write_clipboard", "payload": {"text": secret}},
        )
        self.assertEqual({"id": 9, "ok": True, "result": {"written": True}}, response)
        self.assertNotIn(secret, repr(response))

        malformed = response_for(
            self.service,
            {"id": 10, "command": 42, "payload": {"text": secret}},
        )
        self.assertEqual("invalid_request", malformed["error"]["code"])
        self.assertNotIn(secret, repr(malformed))


if __name__ == "__main__":
    unittest.main()
