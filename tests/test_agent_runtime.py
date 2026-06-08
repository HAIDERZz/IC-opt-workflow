from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.agent_runtime import (
    default_runtime_home,
    inspect_runtime_adapter,
    install_runtime_adapter,
)
from hermes_workflow.cli import app

runner = CliRunner()


def test_install_platform_neutral_skill(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target_home = tmp_path / "agent"

    result = install_runtime_adapter(
        "skill",
        target_home=target_home,
        repo_root=repo_root,
    )

    assert result.runtime == "skill"
    assert result.target_home == target_home
    skill = target_home / "skills" / "ic-opt" / "SKILL.md"
    assert skill.is_file()
    assert "platform-neutral" in skill.read_text(encoding="utf-8").lower()
    assert result.installed == [target_home / "skills" / "ic-opt"]
    assert result.skipped == []


def test_install_runtime_adapter_skips_existing_without_force(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target_home = tmp_path / "agent"
    existing = target_home / "skills" / "ic-opt"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("keep me\n", encoding="utf-8")

    result = install_runtime_adapter(
        "skill",
        target_home=target_home,
        repo_root=repo_root,
    )

    assert (existing / "SKILL.md").read_text(encoding="utf-8") == "keep me\n"
    assert result.installed == []
    assert result.skipped == [existing]


def test_install_runtime_adapter_force_replaces_existing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target_home = tmp_path / "agent"
    existing = target_home / "skills" / "ic-opt"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("replace me\n", encoding="utf-8")

    install_runtime_adapter(
        "skill",
        target_home=target_home,
        repo_root=repo_root,
        force=True,
    )

    assert "replace me" not in (existing / "SKILL.md").read_text(encoding="utf-8")


def test_inspect_runtime_adapter_does_not_write_missing_files(tmp_path: Path) -> None:
    target_home = tmp_path / "agent"

    result = inspect_runtime_adapter("skill", target_home=target_home)

    assert result.runtime == "skill"
    assert result.present == []
    assert target_home / "skills" / "ic-opt" in result.missing
    assert not target_home.exists()


def test_default_runtime_home() -> None:
    assert default_runtime_home("skill") == Path.home() / ".ic-opt"


def test_install_runtime_adapter_cli(tmp_path: Path) -> None:
    target_home = tmp_path / "agent"

    result = runner.invoke(
        app,
        [
            "install-runtime-adapter",
            "skill",
            "--target-home",
            str(target_home),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "runtime: skill" in result.output
    assert "installed:" in result.output
    assert (target_home / "skills" / "ic-opt" / "SKILL.md").is_file()


def test_runtime_adapter_status_cli_is_read_only(tmp_path: Path) -> None:
    target_home = tmp_path / "agent"

    result = runner.invoke(
        app,
        [
            "runtime-adapter-status",
            "skill",
            "--target-home",
            str(target_home),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "runtime: skill" in result.output
    assert "missing:" in result.output
    assert not target_home.exists()
