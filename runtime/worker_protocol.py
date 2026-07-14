from __future__ import annotations

import json
import sys
from typing import Any, Callable, Type


def response_for_service(
    service: Any,
    request: dict[str, Any],
    *,
    known_error: Type[Exception],
    internal_code: str,
    internal_message: str,
) -> dict[str, Any]:
    request_id = request.get("id")
    command = request.get("command")
    payload = request.get("payload")
    if not isinstance(command, str) or not isinstance(payload, dict):
        return {
            "id": request_id,
            "ok": False,
            "error": {
                "code": "invalid_request",
                "message": "Worker requests require a string command and object payload",
                "details": {},
            },
        }
    try:
        return {"id": request_id, "ok": True, "result": service.handle(command, payload)}
    except known_error as error:
        return {"id": request_id, "ok": False, "error": error.to_dict()}
    except Exception:
        return {
            "id": request_id,
            "ok": False,
            "error": {
                "code": internal_code,
                "message": internal_message,
                "details": {"command": command},
            },
        }


def serve_json_lines(
    service: Any,
    response_builder: Callable[[Any, dict[str, Any]], dict[str, Any]],
) -> int:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = response_builder(service, request)
        except Exception:
            request = {}
            response = {
                "id": None,
                "ok": False,
                "error": {
                    "code": "invalid_json",
                    "message": "Worker input must be one JSON object per line",
                    "details": {},
                },
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        if request.get("command") == "shutdown":
            break
    return 0
