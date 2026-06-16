from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app
from hermes_workflow.agent_runtime import (
    default_runtime_home,
    inspect_runtime_adapter,
    install_runtime_adapter,
)


runner = CliRunner()


def test_install_claude_runtime_adapter(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target_home = tmp_path / "claude"

    result = install_runtime_adapter(
        "claude",
        target_home=target_home,
        repo_root=repo_root,
    )

    assert result.runtime == "claude"
    assert result.target_home == target_home
    skill = target_home / "skills" / "ic-opt" / "SKILL.md"
    assert skill.is_file()
    assert "runtime-native" in skill.read_text(encoding="utf-8").lower()
    assert result.installed == [target_home / "skills" / "ic-opt"]
    assert result.skipped == []


def test_install_opencode_runtime_adapter(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target_home = tmp_path / "opencode"

    result = install_runtime_adapter(
        "opencode",
        target_home=target_home,
        repo_root=repo_root,
    )

    assert result.runtime == "opencode"
    command = target_home / "command" / "ic-opt.md"
    agent = target_home / "agents" / "ic-opt-execution.md"
    assert command.is_file()
    assert agent.is_file()
    assert "ic-opt-execution" in command.read_text(encoding="utf-8")
    assert "mode: subagent" in agent.read_text(encoding="utf-8")
    assert result.installed == [command, agent]
    assert result.skipped == []


def test_install_runtime_adapter_skips_existing_without_force(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target_home = tmp_path / "opencode"
    existing = target_home / "command" / "ic-opt.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("keep me\n", encoding="utf-8")

    result = install_runtime_adapter(
        "opencode",
        target_home=target_home,
        repo_root=repo_root,
    )

    assert existing.read_text(encoding="utf-8") == "keep me\n"
    assert existing in result.skipped
    assert target_home / "agents" / "ic-opt-execution.md" in result.installed


def test_install_runtime_adapter_force_replaces_existing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target_home = tmp_path / "opencode"
    existing = target_home / "command" / "ic-opt.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("replace me\n", encoding="utf-8")

    install_runtime_adapter(
        "opencode",
        target_home=target_home,
        repo_root=repo_root,
        force=True,
    )

    assert "replace me" not in existing.read_text(encoding="utf-8")


def test_inspect_runtime_adapter_does_not_write_missing_files(tmp_path: Path) -> None:
    target_home = tmp_path / "opencode"

    result = inspect_runtime_adapter("opencode", target_home=target_home)

    assert result.runtime == "opencode"
    assert result.present == []
    assert target_home / "command" / "ic-opt.md" in result.missing
    assert not target_home.exists()


def test_default_runtime_home() -> None:
    assert default_runtime_home("claude").name == ".claude"
    assert default_runtime_home("opencode").parts[-2:] == (".config", "opencode")


def test_install_runtime_adapter_cli(tmp_path: Path) -> None:
    target_home = tmp_path / "opencode"

    result = runner.invoke(
        app,
        [
            "install-runtime-adapter",
            "opencode",
            "--target-home",
            str(target_home),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "runtime: opencode" in result.output
    assert "installed:" in result.output
    assert (target_home / "command" / "ic-opt.md").is_file()
    assert (target_home / "agents" / "ic-opt-execution.md").is_file()


def test_runtime_adapter_status_cli_is_read_only(tmp_path: Path) -> None:
    target_home = tmp_path / "opencode"

    result = runner.invoke(
        app,
        [
            "runtime-adapter-status",
            "opencode",
            "--target-home",
            str(target_home),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "runtime: opencode" in result.output
    assert "missing:" in result.output
    assert not target_home.exists()
