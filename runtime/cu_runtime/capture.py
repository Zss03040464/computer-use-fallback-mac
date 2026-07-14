from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Protocol

from AppKit import NSBitmapImageFileTypePNG, NSBitmapImageRep
from Quartz import (
    CGImageGetHeight,
    CGImageGetWidth,
    CGWindowListCreateImage,
    CGRectNull,
    kCGWindowImageBoundsIgnoreFraming,
    kCGWindowImageNominalResolution,
    kCGWindowListOptionIncludingWindow,
)

from .errors import ComputerUseError
from .targets import TargetWindow


@dataclass(frozen=True)
class CaptureFrame:
    png: bytes
    pixel_width: int
    pixel_height: int
    backend: str


@dataclass(frozen=True)
class CaptureResult:
    png: bytes
    logical_width: int
    logical_height: int
    pixel_width: int
    pixel_height: int
    scale_x: float
    scale_y: float
    backend: str
    target: TargetWindow

    def image_to_logical(self, x: float, y: float) -> tuple[int, int]:
        return round(x / self.scale_x), round(y / self.scale_y)

    def image_to_global(self, x: float, y: float) -> tuple[int, int]:
        local_x, local_y = self.image_to_logical(x, y)
        return self.target.x + local_x, self.target.y + local_y

    def global_to_image(self, x: float, y: float) -> tuple[int, int]:
        return (
            round((x - self.target.x) * self.scale_x),
            round((y - self.target.y) * self.scale_y),
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "logicalWidth": self.logical_width,
            "logicalHeight": self.logical_height,
            "pixelWidth": self.pixel_width,
            "pixelHeight": self.pixel_height,
            "scaleX": self.scale_x,
            "scaleY": self.scale_y,
            "backend": self.backend,
            "target": self.target.to_dict(),
        }


class CaptureBackend(Protocol):
    name: str

    def capture(self, target: TargetWindow) -> CaptureFrame:
        ...


def cg_image_png(image: Any) -> bytes:
    representation = NSBitmapImageRep.alloc().initWithCGImage_(image)
    data = representation.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    if data is None:
        raise RuntimeError("Could not encode captured window as PNG")
    return bytes(data)


class CoreGraphicsCaptureBackend:
    name = "core-graphics"

    def capture(self, target: TargetWindow) -> CaptureFrame:
        image = CGWindowListCreateImage(
            CGRectNull,
            kCGWindowListOptionIncludingWindow,
            target.window_id,
            kCGWindowImageBoundsIgnoreFraming | kCGWindowImageNominalResolution,
        )
        if image is None:
            raise RuntimeError(f"CoreGraphics returned no image for window {target.window_id}")
        return CaptureFrame(
            png=cg_image_png(image),
            pixel_width=int(CGImageGetWidth(image)),
            pixel_height=int(CGImageGetHeight(image)),
            backend=self.name,
        )


class ScreenCaptureKitBackend:
    name = "screen-capture-kit"

    def __init__(self) -> None:
        import ScreenCaptureKit as SCK

        self.SCK = SCK

    def _wait(self, starter, timeout: float = 5.0):
        completed = threading.Event()
        values: dict[str, Any] = {}

        def callback(value, error):
            values["value"] = value
            values["error"] = error
            completed.set()

        starter(callback)
        if not completed.wait(timeout):
            raise RuntimeError("ScreenCaptureKit request timed out")
        if values.get("error") is not None:
            raise RuntimeError(str(values["error"]))
        return values.get("value")

    def capture(self, target: TargetWindow) -> CaptureFrame:
        content = self._wait(
            lambda callback: self.SCK.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
                True,
                True,
                callback,
            )
        )
        window = next(
            (candidate for candidate in content.windows() if int(candidate.windowID()) == target.window_id),
            None,
        )
        if window is None:
            raise RuntimeError(f"ScreenCaptureKit window {target.window_id} not found")
        configuration = self.SCK.SCStreamConfiguration.alloc().init()
        configuration.setWidth_(target.width)
        configuration.setHeight_(target.height)
        configuration.setShowsCursor_(False)
        content_filter = self.SCK.SCContentFilter.alloc().initWithDesktopIndependentWindow_(window)
        image = self._wait(
            lambda callback: self.SCK.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(
                content_filter,
                configuration,
                callback,
            )
        )
        if image is None:
            raise RuntimeError("ScreenCaptureKit returned no image")
        return CaptureFrame(
            png=cg_image_png(image),
            pixel_width=int(CGImageGetWidth(image)),
            pixel_height=int(CGImageGetHeight(image)),
            backend=self.name,
        )


class WindowCapture:
    def __init__(self, backends: list[CaptureBackend] | None = None) -> None:
        if backends is None:
            backends = []
            try:
                backends.append(ScreenCaptureKitBackend())
            except Exception:
                pass
            backends.append(CoreGraphicsCaptureBackend())
        self.backends = backends

    def capture(self, target: TargetWindow) -> CaptureResult:
        errors = []
        for backend in self.backends:
            try:
                frame = backend.capture(target)
                if frame.pixel_width <= 0 or frame.pixel_height <= 0:
                    raise RuntimeError("captured image has invalid dimensions")
                return CaptureResult(
                    png=frame.png,
                    logical_width=target.width,
                    logical_height=target.height,
                    pixel_width=frame.pixel_width,
                    pixel_height=frame.pixel_height,
                    scale_x=frame.pixel_width / target.width,
                    scale_y=frame.pixel_height / target.height,
                    backend=frame.backend,
                    target=target,
                )
            except Exception as error:
                errors.append({"backend": backend.name, "error": str(error)})
        raise ComputerUseError(
            "capture_failed",
            "All application-window capture backends failed",
            {"windowId": target.window_id, "attempts": errors},
        )
