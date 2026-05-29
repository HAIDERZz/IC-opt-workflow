from __future__ import annotations

import json
import sys
from typing import Any


JSON = dict[str, Any]


SPEC_REVIEW_SCHEMA: JSON = {
    "type": "object",
    "required": ["repo_path", "task_text", "implementer_report"],
    "properties": {
        "repo_path": {"type": "string"},
        "task_text": {"type": "string"},
        "implementer_report": {"type": "string"},
        "git_range": {"type": "string"},
        "extra_context": {"type": "string"},
    },
}


CODE_QUALITY_SCHEMA: JSON = {
    "type": "object",
    "required": ["repo_path", "requirements", "base_sha", "head_sha", "description"],
    "properties": {
        "repo_path": {"type": "string"},
        "requirements": {"type": "string"},
        "base_sha": {"type": "string"},
        "head_sha": {"type": "string"},
        "description": {"type": "string"},
        "extra_context": {"type": "string"},
    },
}


TOOLS: list[JSON] = [
    {
        "name": "spec_review",
        "description": "Ask Claude CLI to perform a read-only spec compliance review.",
        "inputSchema": SPEC_REVIEW_SCHEMA,
    },
    {
        "name": "code_quality_review",
        "description": "Ask Claude CLI to perform a read-only code-quality review for a git range.",
        "inputSchema": CODE_QUALITY_SCHEMA,
    },
]


def result_response(request_id: object, result: JSON) -> JSON:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: object, code: int, message: str) -> JSON:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_request(request: JSON) -> JSON | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return result_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "claude-review", "version": "0.1.0"},
            },
        )
    if method == "tools/list":
        return result_response(request_id, {"tools": TOOLS})
    return error_response(request_id, -32601, f"unknown method: {method}")


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle_request(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
