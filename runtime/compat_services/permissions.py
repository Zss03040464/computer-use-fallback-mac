from __future__ import annotations

from typing import Protocol


class PermissionAdapter(Protocol):
    def inspect(self) -> dict[str, bool]:
        ...


class MacPermissionAdapter:
    def inspect(self) -> dict[str, bool]:
        import ApplicationServices
        import Quartz

        return {
            "accessibility": bool(ApplicationServices.AXIsProcessTrusted()),
            "screenRecording": bool(Quartz.CGPreflightScreenCaptureAccess()),
        }
