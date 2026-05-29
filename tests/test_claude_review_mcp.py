from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


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


def test_spec_review_invokes_claude_with_read_only_review_prompt(tmp_path: Path) -> None:
    server = load_server()
    completed = subprocess.CompletedProcess(
        args=["claude"],
        returncode=0,
        stdout="\u2705 Spec compliant\n",
        stderr="",
    )

    with patch.object(server.subprocess, "run", return_value=completed) as run:
        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "spec_review",
                    "arguments": {
                        "repo_path": str(tmp_path),
                        "task_text": "Task 5 requirements",
                        "implementer_report": "Implemented manifest builder",
                        "git_range": "abc123..def456",
                    },
                },
            }
        )

    command = run.call_args.args[0]
    prompt = command[-1]
    assert command[:2] == ["claude", "-p"]
    assert "--permission-mode" in command
    assert "Edit" not in command
    assert "Task 5 requirements" in prompt
    assert "Implemented manifest builder" in prompt
    assert "abc123..def456" in prompt
    assert "Do not trust the implementer report" in prompt
    assert response["result"]["content"] == [{"type": "text", "text": "\u2705 Spec compliant\n"}]


def test_spec_review_rejects_missing_repo_before_claude_call(tmp_path: Path) -> None:
    server = load_server()
    missing = tmp_path / "missing"

    with patch.object(server.subprocess, "run") as run:
        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "spec_review",
                    "arguments": {
                        "repo_path": str(missing),
                        "task_text": "Task",
                        "implementer_report": "Report",
                    },
                },
            }
        )

    run.assert_not_called()
    assert response["error"]["code"] == -32000
    assert "repo_path does not exist" in response["error"]["message"]


def test_code_quality_review_prompt_includes_git_range_and_sections(tmp_path: Path) -> None:
    server = load_server()
    completed = subprocess.CompletedProcess(
        args=["claude"],
        returncode=0,
        stdout="### Strengths\nsolid\n\n### Assessment\nReady to proceed? Yes\n",
        stderr="",
    )

    with patch.object(server.subprocess, "run", return_value=completed) as run:
        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "code_quality_review",
                    "arguments": {
                        "repo_path": str(tmp_path),
                        "requirements": "Task 5 manifest requirements",
                        "base_sha": "abc123",
                        "head_sha": "def456",
                        "description": "Added manifest builder",
                        "extra_context": "Focus on package.py boundaries",
                    },
                },
            }
        )

    prompt = run.call_args.args[0][-1]
    assert "git diff --stat abc123..def456" in prompt
    assert "git diff abc123..def456" in prompt
    assert "Task 5 manifest requirements" in prompt
    assert "Added manifest builder" in prompt
    assert "Focus on package.py boundaries" in prompt
    assert "#### Critical (Must Fix)" in prompt
    assert response["result"]["content"][0]["text"].startswith("### Strengths")


def test_claude_failure_returns_mcp_error(tmp_path: Path) -> None:
    server = load_server()
    completed = subprocess.CompletedProcess(
        args=["claude"],
        returncode=1,
        stdout="",
        stderr="authentication failed",
    )

    with patch.object(server.subprocess, "run", return_value=completed):
        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "code_quality_review",
                    "arguments": {
                        "repo_path": str(tmp_path),
                        "requirements": "requirements",
                        "base_sha": "abc123",
                        "head_sha": "def456",
                        "description": "description",
                    },
                },
            }
        )

    assert response["error"]["code"] == -32000
    assert "authentication failed" in response["error"]["message"]
