from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.history_warm_start import (
    HISTORY_WARM_START_AUDIT_MD_RELATIVE,
    HISTORY_WARM_START_AUDIT_RELATIVE,
    audit_history_warm_start,
)
from hermes_workflow.optimizer_artifacts import EVALUATIONS_RELATIVE
from hermes_workflow.validate import assert_valid_project
from tests.project_factory import create_generic_project, write_yaml

NO_ACCEPTED_ISSUE = (
    "history warm-start has no accepted observations; "
    "OpenBox will start without transfer history"
)


def _write_evaluations(project_dir: Path, rows: list[str]) -> None:
    """Write raw JSONL lines (allows injecting malformed rows)."""
    path = project_dir / EVALUATIONS_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in rows), encoding="utf-8")


def _current_project_with_warm_start(
    tmp_path: Path,
    sources: list[dict[str, object]],
    *,
    enabled: bool = True,
) -> tuple[Path, object]:
    project_dir = create_generic_project(tmp_path, name="current_project")
    write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {
                "enabled": enabled,
                "sources": sources,
                "warm_start_strategy": "topk",
            },
        },
    )
    bundle = assert_valid_project(project_dir)
    return project_dir, bundle


def test_missing_warm_start_config_returns_disabled(tmp_path: Path) -> None:
    project_dir = create_generic_project(tmp_path, name="current_project")
    bundle = assert_valid_project(project_dir)

    audit = audit_history_warm_start(project_dir, bundle)

    assert audit.enabled is False
    assert audit.status == "disabled"
    assert audit.sources == []
    assert audit.accepted_observation_count == 0
    assert audit.rejected_observation_count == 0
    assert audit.openbox_transfer_learning.enabled is False
    assert audit.openbox_transfer_learning.warm_start_strategy is None
    assert audit.issues == []

    json_path = project_dir / HISTORY_WARM_START_AUDIT_RELATIVE
    md_path = project_dir / HISTORY_WARM_START_AUDIT_MD_RELATIVE
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "disabled"
    assert payload["enabled"] is False
    assert payload["openbox_transfer_learning"]["enabled"] is False


def test_disabled_warm_start_returns_disabled(tmp_path: Path) -> None:
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": "/tmp/ignored_source", "label": "ignored"}],
        enabled=False,
    )

    audit = audit_history_warm_start(project_dir, bundle)

    assert audit.enabled is False
    assert audit.status == "disabled"
    assert audit.sources == []
    assert audit.openbox_transfer_learning.enabled is False
    assert (project_dir / HISTORY_WARM_START_AUDIT_RELATIVE).exists()
    assert (project_dir / HISTORY_WARM_START_AUDIT_MD_RELATIVE).exists()


def test_relative_source_path_resolves_relative_to_current_project(
    tmp_path: Path,
) -> None:
    project_dir = create_generic_project(tmp_path, name="current_project")
    source_dir = create_generic_project(project_dir, name="prev_round")
    _write_evaluations(source_dir, ['{"parameters": {"FN": 2}, "metrics": {"gain": 1.0}}'])
    write_yaml(
        project_dir / "config" / "history_warm_start.yaml",
        {
            "schema_version": "1.0",
            "history_warm_start": {
                "enabled": True,
                "sources": [{"path": "prev_round", "label": "round1"}],
                "warm_start_strategy": "topk",
            },
        },
    )
    bundle = assert_valid_project(project_dir)

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.path == str((project_dir / "prev_round").resolve())
    assert source.candidate_trace_count == 1
    assert source.rejection_reasons == {"compatibility_not_evaluated": 1}


def test_missing_source_path_creates_source_path_missing(tmp_path: Path) -> None:
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": str(tmp_path / "does_not_exist"), "label": "missing"}],
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.status == "rejected"
    assert any("source_path_missing" in issue for issue in source.issues)
    assert source.candidate_trace_count == 0
    assert source.rejected_observation_count == 0


def test_source_missing_evaluations_creates_missing_optimizer_evaluations(
    tmp_path: Path,
) -> None:
    source_dir = create_generic_project(tmp_path, name="source_project")
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": str(source_dir), "label": "round1"}],
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.status == "rejected"
    assert any(
        "missing_optimizer_evaluations" in issue for issue in source.issues
    )
    assert source.candidate_trace_count == 0


def test_invalid_source_project_creates_source_not_valid_project(
    tmp_path: Path,
) -> None:
    not_a_project = tmp_path / "not_a_project"
    not_a_project.mkdir()
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": str(not_a_project), "label": "bad"}],
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.status == "rejected"
    assert any(
        "source_not_valid_project" in issue for issue in source.issues
    )
    assert source.candidate_trace_count == 0


def test_malformed_jsonl_row_is_counted_and_does_not_abort_source(
    tmp_path: Path,
) -> None:
    source_dir = create_generic_project(tmp_path, name="source_project")
    _write_evaluations(
        source_dir,
        [
            '{"parameters": {"a": 1}}',
            "{not valid json",
            '{"parameters": {"b": 2}}',
        ],
    )
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": str(source_dir), "label": "round1"}],
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.rejection_reasons["invalid_optimizer_evaluations"] == 1
    # Source was not aborted: the later valid row was still read as a candidate.
    assert source.rejection_reasons["compatibility_not_evaluated"] == 2
    assert source.candidate_trace_count == 2
    assert source.rejected_observation_count == 3
    assert source.status == "rejected"


def test_valid_jsonl_rows_counted_as_candidate_traces(tmp_path: Path) -> None:
    source_dir = create_generic_project(tmp_path, name="source_project")
    _write_evaluations(
        source_dir,
        [
            '{"parameters": {"FN": 2}, "metrics": {"gain": 1.0}}',
            '{"parameters": {"FN": 3}, "metrics": {"gain": 2.0}}',
        ],
    )
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": str(source_dir), "label": "round1"}],
    )

    audit = audit_history_warm_start(project_dir, bundle)

    source = audit.sources[0]
    assert source.candidate_trace_count == 2
    assert source.accepted_observation_count == 0
    assert source.rejected_observation_count == 2
    assert source.rejection_reasons == {"compatibility_not_evaluated": 2}
    assert source.status == "rejected"

    assert audit.status == "completed"
    assert audit.accepted_observation_count == 0
    assert audit.rejected_observation_count == 2
    assert NO_ACCEPTED_ISSUE in audit.issues
    assert audit.openbox_transfer_learning.enabled is True
    assert audit.openbox_transfer_learning.source_count == 1
    assert audit.openbox_transfer_learning.accepted_observation_count == 0
    assert audit.openbox_transfer_learning.warm_start_strategy == "topk"
    assert audit.openbox_transfer_learning.applied_to_advisor is False


def test_reports_contain_expected_status_counts_issues(tmp_path: Path) -> None:
    source_dir = create_generic_project(tmp_path, name="source_project")
    _write_evaluations(source_dir, ['{"parameters": {}}', '{"parameters": {}}'])
    project_dir, bundle = _current_project_with_warm_start(
        tmp_path,
        sources=[{"path": str(source_dir), "label": "round1"}],
    )

    audit_history_warm_start(project_dir, bundle)

    payload = json.loads(
        (project_dir / HISTORY_WARM_START_AUDIT_RELATIVE).read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "1.0"
    assert payload["enabled"] is True
    assert payload["status"] == "completed"
    assert payload["accepted_observation_count"] == 0
    assert payload["rejected_observation_count"] == 2
    assert payload["sources"][0]["candidate_trace_count"] == 2
    assert payload["sources"][0]["rejection_reasons"] == {
        "compatibility_not_evaluated": 2
    }
    assert NO_ACCEPTED_ISSUE in payload["issues"]

    markdown = (
        project_dir / HISTORY_WARM_START_AUDIT_MD_RELATIVE
    ).read_text(encoding="utf-8")
    assert "Status: completed" in markdown
    assert "Accepted observations: 0" in markdown
    assert "Rejected observations: 2" in markdown
    assert NO_ACCEPTED_ISSUE in markdown
