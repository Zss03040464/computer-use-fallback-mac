from __future__ import annotations

from typing import Any

from .compat_services.errors import CompatServiceError
from .compat_services.service import CompatService, create_default_service
from .worker_protocol import response_for_service, serve_json_lines


def response_for(service: CompatService, request: dict[str, Any]) -> dict[str, Any]:
    return response_for_service(
        service,
        request,
        known_error=CompatServiceError,
        internal_code="compat_runtime_error",
        internal_message="Compatibility service failed",
    )


def main() -> int:
    return serve_json_lines(create_default_service(), response_for)


if __name__ == "__main__":
    raise SystemExit(main())
