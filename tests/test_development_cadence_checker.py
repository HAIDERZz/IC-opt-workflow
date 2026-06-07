import importlib.util
import json
from pathlib import Path


CHECKER = Path(__file__).resolve().parents[1] / "tools" / "check_development_cadence.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_development_cadence", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_project(
    root: Path,
    *,
    review_status: str = "verified-only",
    current_status: str = "process hardening complete; verified-only",
    review_evidence: dict[str, str | None] | None = None,
    progress_status: str = "process hardening complete; verified-only",
) -> None:
    spec_path = root / "docs/superpowers/specs/process-hardening.md"
    active_plan_path = root / "docs/superpowers/plans/current.md"
    plan_path = root / "docs/superpowers/plans/top-level.md"
    progress_path = root / "docs/NEXT.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    active_plan_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        "# Process Hardening\n\n"
        "Acceptance criteria are explicit.\n"
    )
    active_plan_path.write_text("# Current Plan\n")
    plan_path.write_text("# Top Level Plan\n")
    progress_path.write_text(
        "\n".join(
            [
                "- Current scope: Plan C process hardening lightweight cadence guard",
                f"- Current status: {progress_status}",
                "- Next required action: decide whether to redo C-11 or draft next approved scope",
            ]
        )
    )
    state = {
        "schema_version": "1.0",
        "current_scope": "Plan C process hardening lightweight cadence guard",
        "current_status": current_status,
        "review_status": review_status,
        "subagent_dispatch": "not_available",
        "active_spec": "docs/superpowers/specs/process-hardening.md",
        "active_plan": "docs/superpowers/plans/current.md",
        "top_level_plan": "docs/superpowers/plans/top-level.md",
        "progress_files": ["docs/NEXT.md"],
        "next_allowed_action": "decide whether to redo C-11 or draft next approved scope",
        "forbidden_actions": [
            "run Virtuoso",
            "run Spectre",
            "run OCEAN",
            "run SSH",
            "run Claude CLI",
            "run virtuoso-bridge-lite",
            "use network",
            "run subprocess-backed C-7 adapter",
            "parse PSF",
            "rewrite OCEAN formulas",
            "commit raw input.scs",
            "commit protected include sidecars",
            "commit PSF/raw data",
            "commit full Cadence logs",
        ],
        "required_pre_commit_checks": ["python3 tools/check_development_cadence.py"],
        "review_evidence": review_evidence
        if review_evidence is not None
        else {"spec_review": None, "code_quality_review": None},
    }
    (root / "docs/CURRENT_TASK_STATE.json").write_text(json.dumps(state, indent=2))


def test_checker_accepts_verified_only_state(tmp_path: Path) -> None:
    _write_project(tmp_path)

    checker = _load_checker()

    assert checker.check_project(tmp_path) == []


def test_checker_rejects_reviewed_without_evidence(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        review_status="reviewed",
        current_status="process hardening complete and reviewed",
        review_evidence={"spec_review": None, "code_quality_review": None},
        progress_status="process hardening complete and reviewed",
    )

    checker = _load_checker()

    errors = checker.check_project(tmp_path)
    assert any("review evidence" in error for error in errors)


def test_checker_rejects_reviewed_current_status_for_verified_only(
    tmp_path: Path,
) -> None:
    _write_project(
        tmp_path,
        current_status="process hardening complete and reviewed",
        progress_status="process hardening complete and reviewed",
    )

    checker = _load_checker()

    errors = checker.check_project(tmp_path)
    assert any("verified-only" in error and "reviewed" in error for error in errors)


def test_checker_rejects_missing_active_plan(tmp_path: Path) -> None:
    _write_project(tmp_path)
    state_path = tmp_path / "docs/CURRENT_TASK_STATE.json"
    state = json.loads(state_path.read_text())
    del state["active_plan"]
    state_path.write_text(json.dumps(state, indent=2))

    checker = _load_checker()

    errors = checker.check_project(tmp_path)
    assert any("active_plan" in error for error in errors)
