from __future__ import annotations

from typing import Any

from .capture import CaptureService, CoreGraphicsDisplayCapture
from .clipboard import ClipboardService, PasteboardClipboard
from .displays import DisplayService, QuartzDisplayProvider
from .errors import CompatServiceError
from .ocr import CaptchaDetector, VisionOcrAdapter
from .permissions import MacPermissionAdapter


class CompatService:
    COMMANDS = {
        "check_permissions",
        "screenshot",
        "screenshot_region",
        "read_clipboard",
        "write_clipboard",
        "map_coordinates",
        "detect_captcha",
        "shutdown",
    }

    def __init__(
        self,
        *,
        display_provider,
        capture_adapter,
        clipboard_adapter,
        permission_adapter,
        ocr_adapter,
    ) -> None:
        self.displays = DisplayService(display_provider)
        self.capture = CaptureService(self.displays, capture_adapter)
        self.clipboard = ClipboardService(clipboard_adapter)
        self.permissions = permission_adapter
        self.captcha = CaptchaDetector(self.capture, ocr_adapter)

    def handle(self, command: str, payload: dict[str, Any]) -> Any:
        if command not in self.COMMANDS:
            raise CompatServiceError(
                "unknown_command",
                "Compatibility command is not supported",
                {"command": command},
            )
        if command == "check_permissions":
            result = self.permissions.inspect()
            return {
                "accessibility": bool(result.get("accessibility")),
                "screenRecording": bool(result.get("screenRecording")),
            }
        if command == "screenshot":
            return self.capture.screenshot(payload)
        if command == "screenshot_region":
            return self.capture.screenshot_region(payload)
        if command == "read_clipboard":
            return self.clipboard.read()
        if command == "write_clipboard":
            return self.clipboard.write(payload)
        if command == "map_coordinates":
            return self.displays.map_coordinates(payload)
        if command == "detect_captcha":
            return self.captcha.detect(payload)
        return {"shutdown": True}


def create_default_service() -> CompatService:
    return CompatService(
        display_provider=QuartzDisplayProvider(),
        capture_adapter=CoreGraphicsDisplayCapture(),
        clipboard_adapter=PasteboardClipboard(),
        permission_adapter=MacPermissionAdapter(),
        ocr_adapter=VisionOcrAdapter(),
    )
