from pathlib import Path

from typer.testing import CliRunner

from hermes_workflow.cli import app


ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_source_and_packaged_agent_skill_are_in_sync() -> None:
    source_skill = ROOT / "skills" / "ic-opt" / "SKILL.md"
    packaged_skill = (
        ROOT / "src" / "hermes_workflow" / "agent_skills" / "ic-opt" / "SKILL.md"
    )

    assert source_skill.read_text(encoding="utf-8") == packaged_skill.read_text(
        encoding="utf-8"
    )


def test_pyproject_packages_agent_skill() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"agent_skills/ic-opt/SKILL.md"' in pyproject


def test_agent_skill_path_cli_points_to_existing_skill() -> None:
    result = runner.invoke(app, ["agent-skill-path"])

    assert result.exit_code == 0, result.output
    path = Path(result.output.strip())
    assert path.is_file()
    assert "IC Auto Opt Agent Operator" in path.read_text(encoding="utf-8")
