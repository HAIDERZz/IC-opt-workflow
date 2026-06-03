from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_workflow import real_run
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.metric_requests import expression_sha256
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from hermes_workflow.real_run import prepare_real_run
from tests.report_helpers import write_pass_reports


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _create_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    return project_dir


def _write_template(project_dir: Path, text: str = TEMPLATE_TEXT) -> None:
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(text, encoding="utf-8")


def _approve_project(project_dir: Path) -> None:
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-31T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_prepare_real_run_rejects_missing_supervisor_instruction(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    _write_template(project_dir)

    with pytest.raises(FileNotFoundError, match="supervisor instruction is missing"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_reject_instruction(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at_utc": "2026-05-31T00:10:00Z",
                "decision": "reject_first_real_run",
                "reason": "not ready",
                "allowed_actions": [],
                "forbidden_actions": ["run_standalone_spectre_optimizer"],
                "approved_config_hashes": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_template(project_dir)

    with pytest.raises(ValueError, match="first real run is not approved"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_missing_execution_manifest(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    _write_template(project_dir)
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps({"decision": "approve_first_real_run"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="execution manifest is missing"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_config_drift_after_approval(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)
    variables_path = project_dir / "config" / "variables.yaml"
    variables_path.write_text(
        variables_path.read_text(encoding="utf-8").replace(
            'upper: "12"', 'upper: "14"', 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="immutable config drift detected: config/variables.yaml"
    ):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_instruction_missing_approved_hashes(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    build_execution_package(project_dir, created_at_utc="2026-05-31T00:00:00Z")
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at_utc": "2026-05-31T00:10:00Z",
                "decision": "approve_first_real_run",
                "reason": "approved without hashes",
                "allowed_actions": ["run_standalone_spectre_optimizer"],
                "forbidden_actions": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_template(project_dir)

    with pytest.raises(
        ValueError,
        match="supervisor instruction is missing approved_config_hashes",
    ):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_instruction_hash_mismatch(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    manifest = build_execution_package(
        project_dir,
        created_at_utc="2026-05-31T00:00:00Z",
    )
    approved_hashes = dict(manifest.payload["immutable_config_files"])
    approved_hashes["config/variables.yaml"] = "not-the-approved-hash"
    (project_dir / "supervisor_instruction.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at_utc": "2026-05-31T00:10:00Z",
                "decision": "approve_first_real_run",
                "reason": "approved with wrong hashes",
                "allowed_actions": ["run_standalone_spectre_optimizer"],
                "forbidden_actions": [],
                "approved_config_hashes": approved_hashes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_template(project_dir)

    with pytest.raises(
        ValueError,
        match="supervisor approved config hashes do not match execution manifest",
    ):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_writes_first_real_run_package(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    package = prepare_real_run(
        project_dir,
        created_at_utc="2026-05-31T00:20:00Z",
    )

    run_dir = project_dir / "runs" / "real" / "real_001"
    rendered = (run_dir / "input.scs").read_text(encoding="utf-8")
    candidate = _load_json(run_dir / "candidate.json")
    manifest = _load_json(run_dir / "real_run_manifest.json")

    assert package.run_id == "real_001"
    assert package.run_dir == run_dir
    assert package.rendered_input_scs == run_dir / "input.scs"
    assert package.candidate_path == run_dir / "candidate.json"
    assert package.manifest_path == run_dir / "real_run_manifest.json"
    assert "{{" not in rendered
    assert "}}" not in rendered
    assert "FN=2" in rendered
    assert "WN=0.3u" in rendered
    assert "FP=2" in rendered
    assert "WP=0.3u" in rendered
    assert candidate == {
        "schema_version": "1.0",
        "candidate_id": "real_001",
        "source": "lower_bound_first_real_run",
        "parameters": {
            "FN": "2",
            "WN": "0.3u",
            "FP": "2",
            "WP": "0.3u",
        },
    }
    assert manifest["schema_version"] == "1.0"
    assert manifest["run_id"] == "real_001"
    assert manifest["project_name"] == "bridge_test_inv"
    assert manifest["created_at_utc"] == "2026-05-31T00:20:00Z"
    assert manifest["status"] == "prepared"
    assert manifest["supervisor_decision"] == "approve_first_real_run"
    assert manifest["template_scs"] == "netlists/templates/template.scs"
    assert manifest["rendered_input_scs"] == "runs/real/real_001/input.scs"
    assert manifest["candidate_file"] == "runs/real/real_001/candidate.json"
    assert manifest["candidate_id"] == "real_001"
    assert manifest["candidate_source"] == "lower_bound_first_real_run"
    assert manifest["template_sha256"] == sha256_file(
        project_dir / "netlists" / "templates" / "template.scs"
    )
    assert manifest["rendered_input_sha256"] == sha256_file(run_dir / "input.scs")
    assert manifest["approved_config_hashes"]["config/project_config.yaml"]
    assert manifest["spectre"] == {
        "engine": "spectre_x",
        "preset": "ax",
        "output_format": "psfxl",
        "parallel_jobs": 10,
        "timeout_s": 3600,
    }
    assert "modify_maestro_setup" in manifest["forbidden_actions"]
    assert not (project_dir / "ledger" / "experiment_ledger.jsonl").exists()
    assert not (project_dir / "state" / "optimizer_state.json").exists()
    assert not (project_dir / "state" / "best_candidate.json").exists()


def test_prepare_real_run_copies_exported_netlist_sidecars(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)
    exported_dir = project_dir / "netlists" / "exported"
    (exported_dir / "input.scs").write_text(
        'include "ade_e.scs"\nparameters FN=2\n',
        encoding="utf-8",
    )
    (exported_dir / "ade_e.scs").write_text(
        "simulatorOptions options\n",
        encoding="utf-8",
    )
    (exported_dir / "amap").mkdir()
    (exported_dir / "amap" / "designData.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (exported_dir / ".modelFiles").write_text(
        "model file sidecar\n",
        encoding="utf-8",
    )

    prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    run_dir = project_dir / "runs" / "real" / "real_001"
    assert (run_dir / "ade_e.scs").read_text(encoding="utf-8") == (
        "simulatorOptions options\n"
    )
    assert (run_dir / "amap" / "designData.json").read_text(encoding="utf-8") == "{}\n"
    assert (run_dir / ".modelFiles").read_text(encoding="utf-8") == (
        "model file sidecar\n"
    )
    assert "FN=2" in (run_dir / "input.scs").read_text(encoding="utf-8")


def test_prepare_real_run_rejects_exported_netlist_sidecar_symlink(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)
    exported_dir = project_dir / "netlists" / "exported"
    (exported_dir / "input.scs").write_text("parameters FN=2\n", encoding="utf-8")
    target = tmp_path / "protected.scs"
    target.write_text("external sidecar\n", encoding="utf-8")
    (exported_dir / "ade_e.scs").symlink_to(target)

    with pytest.raises(
        FileExistsError,
        match="exported netlist bundle must not contain symlinks",
    ):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real" / "real_001").exists()


def test_prepare_real_run_writes_metric_extraction_request(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    package = prepare_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:20:00Z",
    )

    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    manifest = _load_json(run_dir / "real_run_manifest.json")

    assert package.metric_request_path == request_path
    assert package.metric_request_payload == request
    assert request["schema_version"] == "1.0"
    assert request["backend"] == "spectre_ocean_batch"
    assert request["run_id"] == "real_001"
    assert request["candidate_id"] == "real_001"
    assert request["prepared_input_scs"] == "runs/real/real_001/input.scs"
    assert request["prepared_input_sha256"] == manifest["rendered_input_sha256"]
    assert request["expected_psf_dir"] == "runs/real/real_001/psf"
    assert request["spectre"] == {
        "engine": "spectre_x",
        "preset": "ax",
        "output_format": "psfxl",
        "timeout_s": 3600,
    }
    assert request["ocean"] == {
        "mode": "nograph_replay",
        "script_file": "runs/real/real_001/metrics/metric_probe.ocn",
        "log_file": "runs/real/real_001/metrics/ocean.log",
        "scalar_output_file": "runs/real/real_001/metrics/ocean_scalars.tsv",
    }
    assert request["metrics"][0]["name"] == "rise"
    assert request["metrics"][0]["expression"]
    assert request["metrics"][0]["expression_sha256"] == expression_sha256(
        request["metrics"][0]["expression"]
    )
    request_metrics = {metric["name"]: metric for metric in request["metrics"]}
    assert set(request_metrics) == {"rise", "fall", "DC"}
    assert request_metrics["rise"]["expression"] == (
        'riseTime(VT("/VOUT") 0 nil 0.9 nil 10 90 nil "time")'
    )
    assert request_metrics["fall"]["expression"] == (
        'fallTime(VT("/VOUT") 0.9 nil 0 nil 10 90 nil "time")'
    )
    assert request_metrics["DC"]["expression"] == 'VDC("/VDD") * IDC("/M0/S")'
    assert request_metrics["DC"]["unit"] == "W"
    assert request_metrics["DC"]["required_signals"] == ["/VDD", "/M0/S"]
    assert "rewrite_metric_formula" in request["forbidden_actions"]
    assert (
        manifest["metric_extraction_request"]
        == "runs/real/real_001/metric_extraction_request.json"
    )
    assert manifest["metric_extraction_request_sha256"] == sha256_file(request_path)


def test_prepare_real_run_rejects_metric_without_ocean_formula(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    metrics_text = metrics_path.read_text(encoding="utf-8")
    assert "source_reference: template:spectre_maestro_project:rise" in metrics_text
    metrics_path.write_text(
        metrics_text.replace(
            "    ocean:\n"
            "      expression: riseTime(VT(\"/VOUT\") 0 nil 0.9 nil 10 90 nil \"time\")\n"
            "      result: tran\n"
            "      expression_source: user_approved\n"
            "      source_reference: template:spectre_maestro_project:rise\n"
            "      expected_value_type: real_scalar\n"
            "      nil_policy: fail\n"
            "      non_finite_policy: fail\n",
            "",
            1,
        ),
        encoding="utf-8",
    )
    _approve_project(project_dir)
    _write_template(project_dir)

    with pytest.raises(ValueError, match="metric rise is missing ocean formula"):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real" / "real_001").exists()


def test_prepare_real_run_requires_ocean_ready_spectre_format(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    spectre_path = project_dir / "config" / "spectre.yaml"
    spectre_path.write_text(
        spectre_path.read_text(encoding="utf-8").replace(
            "output_format: psfxl",
            "output_format: psfascii",
        ),
        encoding="utf-8",
    )
    _approve_project(project_dir)
    _write_template(project_dir)

    with pytest.raises(
        ValueError,
        match="spectre.output_format must be OCEAN-ready for metric extraction: psfascii",
    ):
        prepare_real_run(project_dir)

    assert not (project_dir / "runs" / "real" / "real_001").exists()


def test_prepare_real_run_accepts_valid_custom_run_id(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    package = prepare_real_run(
        project_dir,
        run_id="real_007",
        created_at_utc="2026-05-31T00:20:00Z",
    )

    manifest = _load_json(
        project_dir / "runs" / "real" / "real_007" / "real_run_manifest.json"
    )
    assert package.run_id == "real_007"
    assert manifest["run_id"] == "real_007"
    assert manifest["candidate_id"] == "real_007"
    assert manifest["rendered_input_scs"] == "runs/real/real_007/input.scs"


def test_prepare_real_run_rejects_placeholder_candidate_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    def placeholder_candidate(_bundle, run_id: str) -> dict:
        return {
            "schema_version": "1.0",
            "candidate_id": run_id,
            "source": "lower_bound_first_real_run",
            "parameters": {
                "FN": "{{WN}}",
                "WN": "0.3u",
                "FP": "2",
                "WP": "0.3u",
            },
        }

    monkeypatch.setattr(real_run, "_lower_bound_candidate", placeholder_candidate)

    with pytest.raises(
        ValueError,
        match="candidate parameter values must not contain placeholders: FN",
    ):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real" / "real_001").exists()


def test_prepare_real_run_rejects_invalid_run_id(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    with pytest.raises(ValueError, match=r"run_id must match real_\[0-9\]\{3\}: run_1"):
        prepare_real_run(project_dir, run_id="run_1")

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_missing_template(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)

    with pytest.raises(
        FileNotFoundError,
        match="template.scs is missing: netlists/templates/template.scs",
    ):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real").exists()


def test_prepare_real_run_rejects_unexpected_template_variable(
    tmp_path: Path,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(
        project_dir,
        """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}} EXTRA={{EXTRA}}
tran tran stop=10n
""",
    )

    with pytest.raises(ValueError, match="unexpected template variables: EXTRA"):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real" / "real_001").exists()


def test_prepare_real_run_refuses_existing_package(tmp_path: Path) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)
    prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    with pytest.raises(FileExistsError, match="real run package already exists"):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:21:00Z")


def test_prepare_real_run_cleans_partial_run_directory_on_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    original_write_text = Path.write_text

    def failing_write_text(self: Path, data: str, *args, **kwargs):
        if self.name == "candidate.json":
            raise OSError("simulated candidate write failure")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(OSError, match="simulated candidate write failure"):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real" / "real_001").exists()

    monkeypatch.undo()
    package = prepare_real_run(project_dir, created_at_utc="2026-05-31T00:21:00Z")
    assert package.manifest_path.exists()


def test_prepare_real_run_cleans_partial_run_directory_on_manifest_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = _create_project(tmp_path)
    _approve_project(project_dir)
    _write_template(project_dir)

    original_write_text = Path.write_text

    def failing_write_text(self: Path, data: str, *args, **kwargs):
        if self.name == "real_run_manifest.json":
            raise OSError("simulated manifest write failure")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(OSError, match="simulated manifest write failure"):
        prepare_real_run(project_dir, created_at_utc="2026-05-31T00:20:00Z")

    assert not (project_dir / "runs" / "real" / "real_001").exists()
