from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.package import create_project_from_template
from hermes_workflow.reports import DryRunReport, PassFail


def _create_project_with_template(tmp_path: Path, template_text: str) -> Path:
    project_dir = create_project_from_template(tmp_path / "bridge_test_inv")
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(template_text, encoding="utf-8")
    return project_dir


def _load_report(project_dir: Path) -> DryRunReport:
    payload = json.loads(
        (project_dir / "reports" / "dry_run_report.json").read_text(
            encoding="utf-8"
        )
    )
    return DryRunReport.model_validate(payload)


def test_run_dry_run_renders_lower_bound_candidate(tmp_path: Path) -> None:
    project_dir = _create_project_with_template(
        tmp_path,
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
""",
    )

    report = run_dry_run(project_dir)

    rendered_path = project_dir / "runs" / "dry_run" / "input.scs"
    rendered = rendered_path.read_text(encoding="utf-8")
    persisted = _load_report(project_dir)
    assert report == persisted
    assert report.status == PassFail.PASS
    assert report.rendered_candidate_scs == "runs/dry_run/input.scs"
    assert report.placeholder_check.unresolved_placeholders == []
    assert report.placeholder_check.unexpected_template_variables == []
    assert report.metrics_import_ok is True
    assert report.mock_metrics_ok is True
    assert report.objective_ok is True
    assert report.constraints_ok is True
    assert report.ledger_write_ok is True
    assert report.state_write_ok is True
    assert report.issues == []
    assert "{{" not in rendered
    assert "}}" not in rendered
    assert "FN=2" in rendered
    assert "WN=0.3 um" in rendered
    assert "FP=2" in rendered
    assert "WP=0.3 um" in rendered
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()
