from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .cu_runtime.errors import ComputerUseError
from .cu_runtime.service import RuntimeService
from .cu_runtime.session import SessionState


def response_for(service: RuntimeService, request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id")
    command = request.get("command")
    payload = request.get("payload") or {}
    if not isinstance(command, str) or not isinstance(payload, dict):
        return {
            "id": request_id,
            "ok": False,
            "error": {
                "code": "invalid_request",
                "message": "Worker requests require string command and object payload",
                "details": {},
            },
        }
    try:
        return {"id": request_id, "ok": True, "result": service.handle(command, payload)}
    except ComputerUseError as error:
        return {"id": request_id, "ok": False, "error": error.to_dict()}
    except Exception as error:
        return {
            "id": request_id,
            "ok": False,
            "error": {
                "code": "runtime_error",
                "message": str(error),
                "details": {"command": command},
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--runtime-root", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()

    session = SessionState.create(Path(args.runtime_root), args.session)
    service = RuntimeService(session)

    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = response_for(service, request)
        except Exception as error:
            response = {
                "id": None,
                "ok": False,
                "error": {
                    "code": "invalid_json",
                    "message": str(error),
                    "details": {},
                },
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        if request.get("command") == "shutdown":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
