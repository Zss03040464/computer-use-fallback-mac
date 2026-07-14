from __future__ import annotations

import base64
import io
from typing import Any, Protocol

from AppKit import NSBitmapImageFileTypePNG, NSBitmapImageRep
from PIL import Image

from .displays import DisplayInfo, DisplayService
from .errors import CompatServiceError


class CaptureAdapter(Protocol):
    def capture(self, display: DisplayInfo) -> Image.Image:
        ...


class CoreGraphicsDisplayCapture:
    def capture(self, display: DisplayInfo) -> Image.Image:
        import Quartz

        cg_image = Quartz.CGDisplayCreateImage(display.display_id)
        if cg_image is None:
            raise CompatServiceError(
                "capture_failed",
                "CoreGraphics returned no display image",
                {"displayId": display.display_id},
            )
        representation = NSBitmapImageRep.alloc().initWithCGImage_(cg_image)
        data = representation.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
        if data is None:
            raise CompatServiceError("capture_failed", "Display image encoding failed")
        with Image.open(io.BytesIO(bytes(data))) as image:
            return image.convert("RGB")


def _positive_integer(payload: dict, name: str, required: bool = False) -> int | None:
    value = payload.get(name)
    if value is None and not required:
        return None
    if isinstance(value, bool):
        value = None
    try:
        converted = int(value)
    except (TypeError, ValueError):
        converted = 0
    if converted <= 0:
        raise CompatServiceError(
            "invalid_dimensions",
            f"{name} must be a positive integer",
            {"field": name},
        )
    return converted


def _resize(image: Image.Image, target_width: int | None, target_height: int | None) -> Image.Image:
    if target_width is None and target_height is None:
        return image
    width, height = image.size
    if target_width is None:
        target_width = max(1, round(width * target_height / height))
    if target_height is None:
        target_height = max(1, round(height * target_width / width))
    return image.resize((target_width, target_height), Image.Resampling.LANCZOS)


class CaptureService:
    def __init__(self, displays: DisplayService, adapter: CaptureAdapter) -> None:
        self.displays = displays
        self.adapter = adapter

    def screenshot(self, payload: dict) -> dict[str, Any]:
        display = self.displays.resolve(payload.get("displayId"))
        image = self.adapter.capture(display)
        return self._encode(image, display, payload)

    def screenshot_region(self, payload: dict) -> dict[str, Any]:
        display = self.displays.resolve(payload.get("displayId"))
        try:
            x = float(payload["x"])
            y = float(payload["y"])
        except (KeyError, TypeError, ValueError):
            raise CompatServiceError("invalid_region", "Region coordinates must be numbers")
        width = _positive_integer(payload, "width", required=True)
        height = _positive_integer(payload, "height", required=True)
        if x < 0 or y < 0 or x + width > display.logical_width or y + height > display.logical_height:
            raise CompatServiceError(
                "invalid_region",
                "Region must be inside the selected display",
                {"displayId": display.display_id},
            )
        image = self.adapter.capture(display)
        left = round(x * display.scale_x)
        top = round(y * display.scale_y)
        right = round((x + width) * display.scale_x)
        bottom = round((y + height) * display.scale_y)
        result = self._encode(image.crop((left, top, right, bottom)), display, payload)
        result["region"] = {"x": x if x % 1 else int(x), "y": y if y % 1 else int(y), "width": width, "height": height}
        return result

    def capture_image(self, display_id: int | None = None) -> tuple[DisplayInfo, Image.Image]:
        display = self.displays.resolve(display_id)
        return display, self.adapter.capture(display)

    def _encode(self, image: Image.Image, display: DisplayInfo, payload: dict) -> dict[str, Any]:
        target_width = _positive_integer(payload, "targetWidth")
        target_height = _positive_integer(payload, "targetHeight")
        rendered = _resize(image, target_width, target_height).convert("RGB")
        output = io.BytesIO()
        rendered.save(output, format="JPEG", quality=88, optimize=True)
        return {
            "base64": base64.b64encode(output.getvalue()).decode("ascii"),
            "mimeType": "image/jpeg",
            "width": rendered.width,
            "height": rendered.height,
            "displayId": display.display_id,
            "displayWidth": display.logical_width,
            "displayHeight": display.logical_height,
            "pixelWidth": display.pixel_width,
            "pixelHeight": display.pixel_height,
            "scaleX": display.scale_x,
            "scaleY": display.scale_y,
        }
