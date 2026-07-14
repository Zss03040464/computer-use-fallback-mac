"""Minimal macOS compatibility services without input-delivery capabilities."""

from .service import CompatService, create_default_service

__all__ = ["CompatService", "create_default_service"]
