from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .cu_runtime.errors import ComputerUseError
from .cu_runtime.service import RuntimeService
from .cu_runtime.session import SessionState
from .worker_protocol import response_for_service, serve_json_lines


def response_for(service: RuntimeService, request: dict[str, Any]) -> dict[str, Any]:
    return response_for_service(
        service,
        request,
        known_error=ComputerUseError,
        internal_code="runtime_error",
        internal_message="Runtime service failed",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--runtime-root", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()

    session = SessionState.create(Path(args.runtime_root), args.session)
    service = RuntimeService(session)
    return serve_json_lines(service, response_for)


if __name__ == "__main__":
    raise SystemExit(main())
