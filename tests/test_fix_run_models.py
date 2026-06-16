"""Tests for fix_run_models — TDD RED phase."""
from __future__ import annotations

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Test 1: WorkflowSettings valid construction
# ---------------------------------------------------------------------------
def test_workflow_settings_valid():
    from hermes_workflow.fix_run_models import WorkflowSettings

    ws = WorkflowSettings(
        schema_version="1.0", mode="fix_run", starting_run_id="real_001"
    )
    assert ws.schema_version == "1.0"
    assert ws.mode == "fix_run"
    assert ws.starting_run_id == "real_001"


# ---------------------------------------------------------------------------
# Test 2: Missing starting_run_id defaults to "real_001"
# ---------------------------------------------------------------------------
def test_workflow_settings_default_starting_run_id():
    from hermes_workflow.fix_run_models import WorkflowSettings

    ws = WorkflowSettings(schema_version="1.0", mode="fix_run")
    assert ws.starting_run_id == "real_001"


# ---------------------------------------------------------------------------
# Test 3: starting_run_id="fix_001" fails (first version reuses real_NNN)
# ---------------------------------------------------------------------------
def test_workflow_settings_rejects_fix_001():
    from hermes_workflow.fix_run_models import WorkflowSettings

    with pytest.raises(ValidationError, match="starting_run_id"):
        WorkflowSettings(
            schema_version="1.0", mode="fix_run", starting_run_id="fix_001"
        )


# ---------------------------------------------------------------------------
# Test 4: FixedPoint valid construction
# ---------------------------------------------------------------------------
def test_fixed_point_valid():
    from hermes_workflow.fix_run_models import FixedPoint

    fp = FixedPoint(candidate_id="user_point_001", parameters={"w_m1": "8u"})
    assert fp.candidate_id == "user_point_001"
    assert fp.parameters == {"w_m1": "8u"}


# ---------------------------------------------------------------------------
# Test 5: FixedPoint rejects unsafe candidate_id
# ---------------------------------------------------------------------------
def test_fixed_point_rejects_unsafe_candidate_id():
    from hermes_workflow.fix_run_models import FixedPoint

    with pytest.raises(ValidationError, match="candidate_id"):
        FixedPoint(candidate_id="../bad", parameters={"w_m1": "8u"})


# ---------------------------------------------------------------------------
# Test 6: WaveformExport valid construction
# ---------------------------------------------------------------------------
def test_waveform_export_valid():
    from hermes_workflow.fix_run_models import WaveformExport

    we = WaveformExport(
        name="nf_pnoise",
        testbench="cg_nf",
        expression='getData("NF" ?result "pnoise")',
        output_format="csv",
        nil_policy="fail",
    )
    assert we.name == "nf_pnoise"
    assert we.output_format == "csv"
    assert we.nil_policy == "fail"


# ---------------------------------------------------------------------------
# Test 7: WaveformExport rejects output_format="psfascii"
# ---------------------------------------------------------------------------
def test_waveform_export_rejects_psfascii():
    from hermes_workflow.fix_run_models import WaveformExport

    with pytest.raises(ValidationError):
        WaveformExport(
            name="nf_pnoise",
            testbench="cg_nf",
            expression='getData("NF" ?result "pnoise")',
            output_format="psfascii",
            nil_policy="fail",
        )


# ---------------------------------------------------------------------------
# Test 8: WaveformExport rejects expression containing outfile(
# ---------------------------------------------------------------------------
def test_waveform_export_rejects_outfile():
    from hermes_workflow.fix_run_models import WaveformExport

    with pytest.raises(ValidationError, match="outfile"):
        WaveformExport(
            name="nf_pnoise",
            testbench="cg_nf",
            expression='outfile("data.csv")',
            output_format="csv",
            nil_policy="fail",
        )


# ---------------------------------------------------------------------------
# Test 9: WaveformExport rejects expression containing system(
# ---------------------------------------------------------------------------
def test_waveform_export_rejects_system():
    from hermes_workflow.fix_run_models import WaveformExport

    with pytest.raises(ValidationError, match="system"):
        WaveformExport(
            name="nf_pnoise",
            testbench="cg_nf",
            expression='system("rm -rf /")',
            output_format="csv",
            nil_policy="fail",
        )


# ---------------------------------------------------------------------------
# Test 10: WaveformExport rejects expression containing {{ template placeholders
# ---------------------------------------------------------------------------
def test_waveform_export_rejects_template_placeholders():
    from hermes_workflow.fix_run_models import WaveformExport

    with pytest.raises(ValidationError, match="template"):
        WaveformExport(
            name="nf_pnoise",
            testbench="cg_nf",
            expression='getData("{{signal}}")',
            output_format="csv",
            nil_policy="fail",
        )


# ---------------------------------------------------------------------------
# Test 11: FixedPointsConfig rejects empty points list
# ---------------------------------------------------------------------------
def test_fixed_points_config_rejects_empty_points():
    from hermes_workflow.fix_run_models import FixedPointsConfig

    with pytest.raises(ValidationError):
        FixedPointsConfig(schema_version="1.0", points=[])


# ---------------------------------------------------------------------------
# Test 12: WaveformExportsConfig rejects empty exports list
# ---------------------------------------------------------------------------
def test_waveform_exports_config_rejects_empty_exports():
    from hermes_workflow.fix_run_models import WaveformExportsConfig

    with pytest.raises(ValidationError):
        WaveformExportsConfig(schema_version="1.0", exports=[])


# ---------------------------------------------------------------------------
# Test 13: FixRunReport validates optimizer_state_created is False
# ---------------------------------------------------------------------------
def test_fix_run_report_rejects_optimizer_state_created_true():
    from hermes_workflow.fix_run_models import FixRunReport

    with pytest.raises(ValidationError, match="optimizer_state_created"):
        FixRunReport(
            schema_version="1.0",
            workflow_mode="fix_run",
            status="completed",
            points=[],
            optimizer_state_created=True,
            optimizer_decision_report_created=False,
        )


# ---------------------------------------------------------------------------
# Test 14: FixRunReport validates optimizer_decision_report_created is False
# ---------------------------------------------------------------------------
def test_fix_run_report_rejects_optimizer_decision_report_created_true():
    from hermes_workflow.fix_run_models import FixRunReport

    with pytest.raises(ValidationError, match="optimizer_decision_report_created"):
        FixRunReport(
            schema_version="1.0",
            workflow_mode="fix_run",
            status="completed",
            points=[],
            optimizer_state_created=False,
            optimizer_decision_report_created=True,
        )


# ---------------------------------------------------------------------------
# Test 15: WaveformExportManifest serializes and deserializes correctly
# ---------------------------------------------------------------------------
def test_waveform_export_manifest_round_trip():
    from hermes_workflow.fix_run_models import (
        WaveformExportManifest,
        WaveformExportResult,
    )

    result = WaveformExportResult(
        name="nf",
        expression='getData("NF")',
        expression_sha256="abc123",
        output_format="csv",
        csv_path="output/nf.csv",
        status="pass",
        issues=[],
    )
    manifest = WaveformExportManifest(
        schema_version="1.0",
        workflow_mode="fix_run",
        run_id="real_001",
        candidate_id="user_point_001",
        testbench_id="cg_nf",
        corner_id="tt",
        model_section="typical",
        corner_variables={"temp": "25"},
        parameters={"w_m1": "8u"},
        exports=[result],
        psf_dir="runs/real_001/psf",
        ocean_log="runs/real_001/ocean.log",
    )
    data = manifest.model_dump()
    restored = WaveformExportManifest.model_validate(data)
    assert restored.schema_version == "1.0"
    assert restored.exports[0].name == "nf"
    assert restored.candidate_id == "user_point_001"


# ---------------------------------------------------------------------------
# Test 16: WaveformExportResult with status "pass" and "fail" both work
# ---------------------------------------------------------------------------
def test_waveform_export_result_pass_and_fail():
    from hermes_workflow.fix_run_models import WaveformExportResult

    passed = WaveformExportResult(
        name="nf",
        expression='getData("NF")',
        expression_sha256="abc123",
        output_format="csv",
        csv_path="output/nf.csv",
        status="pass",
    )
    assert passed.status == "pass"
    assert passed.issues == []

    failed = WaveformExportResult(
        name="nf",
        expression='getData("NF")',
        expression_sha256="abc123",
        output_format="csv",
        csv_path="output/nf.csv",
        status="fail",
        issues=["nil value encountered"],
    )
    assert failed.status == "fail"
    assert failed.issues == ["nil value encountered"]


# ---------------------------------------------------------------------------
# Test 17: ChildRunIssue can be created with testbench_id, corner_id, and message
# ---------------------------------------------------------------------------
def test_child_run_issue_valid():
    from hermes_workflow.fix_run_models import ChildRunIssue

    issue = ChildRunIssue(
        testbench_id="cg_nf",
        corner_id="tt",
        message="dc convergence failed",
    )
    assert issue.testbench_id == "cg_nf"
    assert issue.corner_id == "tt"
    assert issue.message == "dc convergence failed"


# ---------------------------------------------------------------------------
# Test 18: ChildRunIssue can be created with only message (optional fields)
# ---------------------------------------------------------------------------
def test_child_run_issue_only_message():
    from hermes_workflow.fix_run_models import ChildRunIssue

    issue = ChildRunIssue(message="generic failure")
    assert issue.testbench_id is None
    assert issue.corner_id is None
    assert issue.message == "generic failure"


# ---------------------------------------------------------------------------
# Test 19: FixRunPointReport can include child_issues
# ---------------------------------------------------------------------------
def test_fix_run_point_report_with_child_issues():
    from hermes_workflow.fix_run_models import ChildRunIssue, FixRunPointReport

    report = FixRunPointReport(
        candidate_id="user_point_001",
        run_id="real_001",
        testbench_corner_count=4,
        scalar_metric_manifest_paths=["metrics.json"],
        waveform_export_manifest_paths=["waveforms.json"],
        csv_artifact_paths=["data.csv"],
        issues=["point-level issue"],
        child_issues=[
            ChildRunIssue(testbench_id="cg_nf", corner_id="tt", message="dc convergence failed"),
            ChildRunIssue(testbench_id="cg_gain", message="gain too low"),
        ],
    )
    assert len(report.child_issues) == 2
    assert report.child_issues[0].testbench_id == "cg_nf"
    assert report.child_issues[0].corner_id == "tt"
    assert report.child_issues[1].corner_id is None


# ---------------------------------------------------------------------------
# Test 20: FixRunPointReport child_issues defaults to empty list
# ---------------------------------------------------------------------------
def test_fix_run_point_report_child_issues_default():
    from hermes_workflow.fix_run_models import FixRunPointReport

    report = FixRunPointReport(
        candidate_id="user_point_001",
        run_id="real_001",
        testbench_corner_count=4,
        scalar_metric_manifest_paths=["metrics.json"],
        waveform_export_manifest_paths=["waveforms.json"],
        csv_artifact_paths=["data.csv"],
        issues=["point-level issue"],
    )
    assert report.child_issues == []
