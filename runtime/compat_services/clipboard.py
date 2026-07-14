from __future__ import annotations

from typing import Protocol

from .errors import CompatServiceError


class ClipboardAdapter(Protocol):
    def read_text(self) -> str:
        ...

    def write_text(self, value: str) -> None:
        ...


class PasteboardClipboard:
    def read_text(self) -> str:
        from AppKit import NSPasteboard, NSPasteboardTypeString

        value = NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString)
        return "" if value is None else str(value)

    def write_text(self, value: str) -> None:
        from AppKit import NSPasteboard, NSPasteboardTypeString

        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        if not pasteboard.setString_forType_(value, NSPasteboardTypeString):
            raise CompatServiceError("clipboard_write_failed", "macOS rejected the clipboard write")


class ClipboardService:
    def __init__(self, adapter: ClipboardAdapter) -> None:
        self.adapter = adapter

    def read(self) -> str:
        return self.adapter.read_text()

    def write(self, payload: dict) -> dict:
        value = payload.get("text")
        if not isinstance(value, str):
            raise CompatServiceError("invalid_clipboard_text", "Clipboard text must be a string")
        self.adapter.write_text(value)
        return {"written": True}
