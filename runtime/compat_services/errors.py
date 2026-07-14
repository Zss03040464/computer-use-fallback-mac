from __future__ import annotations

from typing import Any


class CompatServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.details = {} if details is None else details

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
