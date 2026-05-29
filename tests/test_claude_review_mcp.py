from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "tools" / "claude_review_mcp.py"


def load_server() -> ModuleType:
    spec = importlib.util.spec_from_file_location("claude_review_mcp", SERVER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tools_list_advertises_review_tools() -> None:
    server = load_server()

    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert tool_names == {"spec_review", "code_quality_review"}


def test_initialize_returns_server_capabilities() -> None:
    server = load_server()

    response = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "initialize"})

    assert response["result"]["serverInfo"]["name"] == "claude-review"
    assert response["result"]["capabilities"]["tools"] == {}


def test_unknown_method_returns_json_rpc_error() -> None:
    server = load_server()

    response = server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "unknown"})

    assert response["error"]["code"] == -32601
    assert "unknown method" in response["error"]["message"]
