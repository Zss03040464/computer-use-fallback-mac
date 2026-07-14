from __future__ import annotations

import io
from typing import Protocol

from PIL import Image

from .capture import CaptureService
from .errors import CompatServiceError


class OcrAdapter(Protocol):
    def recognize(self, image: Image.Image) -> list[str]:
        ...


class VisionOcrAdapter:
    def recognize(self, image: Image.Image) -> list[str]:
        import Quartz
        import Vision

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data = buffer.getvalue()
        provider = Quartz.CGDataProviderCreateWithCFData(data)
        cg_image = Quartz.CGImageCreateWithPNGDataProvider(provider, None, True, Quartz.kCGRenderingIntentDefault)
        if cg_image is None:
            raise CompatServiceError("ocr_failed", "Could not prepare captured image for Vision")

        request = Vision.VNRecognizeTextRequest.alloc().init()
        accurate_level = Vision.VNRequestTextRecognitionLevelAccurate
        request.setRecognitionLevel_(accurate_level)
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})
        success, error = handler.performRequests_error_([request], None)
        if not success or error is not None:
            raise CompatServiceError("ocr_failed", "Vision text recognition failed")

        lines = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if candidates:
                lines.append(str(candidates[0].string()))
        return lines


class CaptchaDetector:
    KEYWORDS = ("captcha", "verify", "verification", "验证", "验证码", "人机验证")

    def __init__(self, capture: CaptureService, adapter: OcrAdapter) -> None:
        self.capture = capture
        self.adapter = adapter

    def detect(self, payload: dict) -> dict:
        display, image = self.capture.capture_image(payload.get("displayId"))
        normalized = "\n".join(self.adapter.recognize(image)).casefold()
        matches = []
        for keyword in self.KEYWORDS:
            if keyword.casefold() in normalized and keyword not in matches:
                matches.append(keyword)
        return {
            "displayId": display.display_id,
            "detected": bool(matches),
            "matches": matches,
        }
