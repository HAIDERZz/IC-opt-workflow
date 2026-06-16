from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.dry_run import run_dry_run
from hermes_workflow.execution_adapters.spectre_ocean import (
    AdapterPreconditionError,
    CommandResult,
    load_adapter_context,
    parse_ocean_scalars,
    render_ocean_replay_script,
    run_spectre_ocean_adapter,
)
from hermes_workflow.metric_requests import expression_sha256
from hermes_workflow.metric_results import check_metric_results
from hermes_workflow.package import (
    build_execution_package,
    create_project_from_template,
    sha256_file,
)
from hermes_workflow.netlists import prepare_netlist
from hermes_workflow.real_run import prepare_real_run
from hermes_workflow.reports import MetricResultCheckStatus, RealRunCheckStatus
from hermes_workflow.requirement_intake import prepare_from_requirement
from hermes_workflow.result_handoff import check_real_run
from tests.report_helpers import write_pass_reports
from tests.test_requirement_intake import _copy_multi_testbench_requirement_project


TEMPLATE_TEXT = """simulator lang=spectre
parameters FN={{FN}} WN={{WN}} FP={{FP}} WP={{WP}}
tran tran stop=10n
"""


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _create_ready_real_run_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-06-02T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-02T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    template_path = project_dir / "netlists" / "templates" / "template.scs"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(TEMPLATE_TEXT, encoding="utf-8")
    prepare_real_run(project_dir, created_at_utc="2026-06-02T00:20:00Z")
    return project_dir


def _create_ready_multi_testbench_project(tmp_path: Path) -> Path:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)
    assert prepare_from_requirement(project_dir).status == "pass"
    assert run_dry_run(project_dir).status.value == "pass"
    build_execution_package(project_dir, created_at_utc="2026-06-06T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-06T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-06T00:20:00Z")
    return project_dir


def _create_ready_corner_project(tmp_path: Path) -> Path:
    project_dir = _copy_multi_testbench_requirement_project(tmp_path)

    assert prepare_from_requirement(project_dir).status == "pass"
    assert run_dry_run(project_dir).status.value == "pass"

    # Overwrite the default nominal-only corner config with real corners
    corners_yaml = """\
schema_version: "1.0"
objective_policy: nominal
constraint_policy: nominal
corners:
  - id: ss
    description: slow-slow corner
  - id: ff
    description: fast-fast corner
"""
    corner_config_path = project_dir / "config" / "process_corners.yaml"
    corner_config_path.write_text(corners_yaml, encoding="utf-8")

    # Regenerate netlist templates with the new corner config
    netlist_report = prepare_netlist(project_dir)
    assert netlist_report.status.value == "pass", netlist_report.issues

    build_execution_package(project_dir, created_at_utc="2026-06-06T00:00:00Z")
    write_pass_reports(project_dir)
    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-06-06T00:10:00Z",
    )
    assert instruction["decision"] == "approve_first_real_run"
    prepare_real_run(project_dir, created_at_utc="2026-06-06T00:20:00Z")

    for testbench_id in ("cg_nf", "iip3"):
        source = (
            project_dir
            / "runs"
            / "dry_run"
            / "testbenches"
            / testbench_id
            / "input.scs"
        )
        target = (
            project_dir
            / "runs"
            / "real"
            / "real_001"
            / "testbenches"
            / testbench_id
            / "netlist"
            / "input.scs"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    corner_manifest = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "testbenches"
        / "cg_nf"
        / "corners"
        / "ss"
        / "real_run_manifest.json"
    )
    if not corner_manifest.exists():
        prepare_real_run(
            project_dir,
            testbench_id="cg_nf",
            corner_id="ss",
            created_at_utc="2026-06-06T00:20:00Z",
        )
    return project_dir


def _refresh_metric_request_hash(run_dir: Path) -> None:
    request_path = run_dir / "metric_extraction_request.json"
    manifest_path = run_dir / "real_run_manifest.json"
    manifest = _load_json(manifest_path)
    manifest["metric_extraction_request_sha256"] = sha256_file(request_path)
    _write_json(manifest_path, manifest)


def test_load_adapter_context_accepts_prepared_real_run(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)

    context = load_adapter_context(project_dir)

    assert context.run_id == "real_001"
    assert context.run_relative == "runs/real/real_001"
    assert context.run_dir == project_dir / "runs" / "real" / "real_001"
    assert context.input_scs == context.run_dir / "netlist" / "input.scs"
    assert context.psf_dir == context.run_dir / "psf"
    assert context.metrics_dir == context.run_dir / "metrics"
    assert context.request.backend == "spectre_ocean_batch"
    assert context.request.spectre["output_format"] == "psfxl"
    assert context.request.spectre["threads_per_run"] == 10
    assert "parallel_jobs" not in context.request.spectre
    assert context.request.metrics


def test_load_adapter_context_accepts_multi_testbench_child_run(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_testbench_project(tmp_path)

    context = load_adapter_context(
        project_dir,
        testbench_id="cg_nf",
        corner_id="nominal",
    )

    child_relative = "runs/real/real_001/testbenches/cg_nf/corners/nominal"
    assert context.run_id == "real_001"
    assert context.run_relative == child_relative
    assert context.run_dir == (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "testbenches"
        / "cg_nf"
        / "corners"
        / "nominal"
    )
    assert context.input_scs == context.run_dir / "netlist" / "input.scs"
    assert context.psf_dir == context.run_dir / "psf"
    assert context.metrics_dir == context.run_dir / "metrics"
    assert [metric.name for metric in context.request.metrics] == ["MAX_GAIN"]
    assert context.request.expected_psf_dir == f"{child_relative}/psf"


def test_load_adapter_context_rejects_formula_hash_drift(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    request = _load_json(request_path)
    request["metrics"][0]["expression_sha256"] = expression_sha256("different_formula")
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    with pytest.raises(AdapterPreconditionError, match="expression hash mismatch"):
        load_adapter_context(project_dir)


def test_load_adapter_context_rejects_non_psfxl_request(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    request = _load_json(request_path)
    request["spectre"]["output_format"] = "psfascii"
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    with pytest.raises(AdapterPreconditionError, match="output_format must be psfxl"):
        load_adapter_context(project_dir)


def test_load_adapter_context_rejects_unsafe_expected_psf_dir(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    request = _load_json(request_path)
    request["expected_psf_dir"] = "../escaped/psf"
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    with pytest.raises(AdapterPreconditionError, match="expected_psf_dir is unsafe"):
        load_adapter_context(project_dir)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request, _manifest: request.update(
                {"prepared_input_scs": "runs/real/real_001/netlist/alternate_input.scs"}
            ),
            "prepared_input_scs must be runs/real/real_001/netlist/input.scs",
        ),
        (
            lambda request, _manifest: request.update(
                {"expected_psf_dir": "runs/real/real_001/alternate_psf"}
            ),
            "expected_psf_dir must be runs/real/real_001/psf",
        ),
        (
            lambda request, _manifest: request["ocean"].update(
                {"script_file": "runs/real/real_001/metrics/alternate.ocn"}
            ),
            "ocean script_file must be runs/real/real_001/metrics/metric_probe.ocn",
        ),
        (
            lambda request, _manifest: request["ocean"].update(
                {"log_file": "runs/real/real_001/metrics/alternate.log"}
            ),
            "ocean log_file must be runs/real/real_001/metrics/ocean.log",
        ),
        (
            lambda request, _manifest: request["ocean"].update(
                {"scalar_output_file": "runs/real/real_001/metrics/alternate.tsv"}
            ),
            (
                "ocean scalar_output_file must be "
                "runs/real/real_001/metrics/ocean_scalars.tsv"
            ),
        ),
    ],
)
def test_load_adapter_context_rejects_under_run_wrong_contract_paths(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    manifest_path = run_dir / "real_run_manifest.json"
    request = _load_json(request_path)
    manifest = _load_json(manifest_path)
    mutate(request, manifest)
    _write_json(request_path, request)
    _write_json(manifest_path, manifest)
    _refresh_metric_request_hash(run_dir)

    with pytest.raises(AdapterPreconditionError, match=message):
        load_adapter_context(project_dir)


def test_load_adapter_context_rejects_symlinked_input_before_hashing(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    input_scs = project_dir / "runs" / "real" / "real_001" / "netlist" / "input.scs"
    outside_input = tmp_path / "outside_input.scs"
    outside_input.write_text(input_scs.read_text(encoding="utf-8"), encoding="utf-8")
    input_scs.unlink()
    input_scs.symlink_to(outside_input)

    with pytest.raises(AdapterPreconditionError, match="prepared_input_scs is a symlink"):
        load_adapter_context(project_dir)


def test_load_adapter_context_reports_request_hash_drift_before_metric_semantics(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    request = _load_json(request_path)
    request["spectre"].pop("engine")
    request["expected_psf_dir"] = "../escaped/psf"
    request["metrics"][0]["expression_sha256"] = expression_sha256("different_formula")
    request["metrics"][0]["nil_policy"] = "allow"
    _write_json(request_path, request)

    with pytest.raises(
        AdapterPreconditionError,
        match="metric request file hash mismatch",
    ):
        load_adapter_context(project_dir)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request: request["spectre"].pop("engine"),
            "spectre.engine is required",
        ),
        (
            lambda request: request["spectre"].update({"timeout_s": 0}),
            "spectre.timeout_s must be a positive integer",
        ),
    ],
)
def test_load_adapter_context_rejects_invalid_spectre_request_shape(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    request_path = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metric_extraction_request.json"
    )
    request = _load_json(request_path)
    mutate(request)
    _write_json(request_path, request)
    _refresh_metric_request_hash(project_dir / "runs" / "real" / "real_001")

    with pytest.raises(AdapterPreconditionError, match=message):
        load_adapter_context(project_dir)


def test_render_ocean_replay_script_preserves_formula_text(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    context = load_adapter_context(project_dir)

    script = render_ocean_replay_script(context)

    for metric in context.request.metrics:
        assert metric.expression in script
        assert metric.expression_sha256 in script
    assert "openResults" in script
    assert "selectResult" in script
    assert "ocean_scalars.tsv" in script
    assert "rewrite" not in script.lower()


def test_render_ocean_replay_script_omits_select_result_without_result_hint(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    request["metrics"] = [request["metrics"][0]]
    request["metrics"][0].pop("result")
    expression = 'value(getData("NF" ?result "pnoise") 3e+09)'
    request["metrics"][0]["expression"] = expression
    request["metrics"][0]["expression_sha256"] = expression_sha256(expression)
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    context = load_adapter_context(project_dir)
    script = render_ocean_replay_script(context)

    assert expression in script
    assert "selectResult" not in script


def test_parse_ocean_scalars_accepts_finite_pass_rows(tmp_path: Path) -> None:
    scalars_path = tmp_path / "ocean_scalars.tsv"
    scalars_path.write_text(
        "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
        "rise\t1.25e-10\ts\tpass\tabc123\t\n"
        "fall\t1.50e-10\ts\tpass\tdef456\t\n",
        encoding="utf-8",
    )

    rows = parse_ocean_scalars(scalars_path)

    assert rows["rise"].value == 1.25e-10
    assert rows["rise"].value_text == "1.25e-10"
    assert rows["fall"].status == "pass"


def test_parse_ocean_scalars_rejects_non_finite_pass_row(tmp_path: Path) -> None:
    scalars_path = tmp_path / "ocean_scalars.tsv"
    scalars_path.write_text(
        "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
        "rise\tNaN\ts\tpass\tabc123\t\n",
        encoding="utf-8",
    )

    with pytest.raises(AdapterPreconditionError, match="not finite"):
        parse_ocean_scalars(scalars_path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "rise\t1.25e-10\ts\tpass\tabc123\t\tunexpected\n",
            "row is malformed",
        ),
        (
            "rise\t1.25e-10\ts\tpass\tabc123\n",
            "row is malformed",
        ),
        (
            "\t1.25e-10\ts\tpass\tabc123\t\n",
            "metric is required",
        ),
        (
            "rise\t1.25e-10\t\tpass\tabc123\t\n",
            "unit is required",
        ),
        (
            "rise\t1.25e-10\ts\tpass\t\t\n",
            "expression_sha256 is required",
        ),
        (
            "rise\t1.25e-10\ts\tok\tabc123\t\n",
            "status is invalid",
        ),
        (
            "rise\t1.25e-10\ts\tpass\tabc123\t\n"
            "rise\t1.50e-10\ts\tpass\tdef456\t\n",
            "duplicate scalar metric",
        ),
        (
            "rise\t1.25e-10\ts\tfail\tabc123\texpression_error\n",
            "fail value must be empty",
        ),
        (
            "rise\t\ts\tpass\tabc123\t\n",
            "value is required for pass",
        ),
    ],
)
def test_parse_ocean_scalars_rejects_malformed_rows(
    tmp_path: Path,
    body: str,
    message: str,
) -> None:
    scalars_path = tmp_path / "ocean_scalars.tsv"
    scalars_path.write_text(
        "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n" + body,
        encoding="utf-8",
    )

    with pytest.raises(AdapterPreconditionError, match=message):
        parse_ocean_scalars(scalars_path)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request: request["metrics"][0].update({"name": "rise\tbad"}),
            "metric name",
        ),
        (
            lambda request: request["metrics"][0].update({"unit": "s\nbad"}),
            "unit",
        ),
    ],
)
def test_render_ocean_replay_script_rejects_control_characters_from_request(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    mutate(request)
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    context = load_adapter_context(project_dir)

    with pytest.raises(AdapterPreconditionError, match=message):
        render_ocean_replay_script(context)


def test_render_ocean_replay_script_rejects_control_characters_in_path(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    context = load_adapter_context(project_dir)
    context.request.ocean.scalar_output_file += "\n"

    with pytest.raises(AdapterPreconditionError, match="scalar_output_file"):
        render_ocean_replay_script(context)


def test_render_ocean_replay_script_rejects_control_characters_in_hash(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    context = load_adapter_context(project_dir)
    context.request.metrics[0].expression_sha256 += "\n"

    with pytest.raises(AdapterPreconditionError, match="expression_sha256"):
        render_ocean_replay_script(context)


def test_render_ocean_replay_script_rejects_unsafe_result_selector(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    request["metrics"][0]["result"] = "tran) printf(\"oops\")"
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    context = load_adapter_context(project_dir)

    with pytest.raises(AdapterPreconditionError, match="result selector"):
        render_ocean_replay_script(context)


def test_render_ocean_replay_script_preserves_formula_with_control_text(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    expression = 'strcat("line1\n" "line2")'
    request["metrics"][0]["expression"] = expression
    request["metrics"][0]["expression_sha256"] = expression_sha256(expression)
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    context = load_adapter_context(project_dir)
    script = render_ocean_replay_script(context)

    assert expression in script


def test_render_ocean_replay_script_keeps_drpl_formula_unchanged(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    expression = (
        "db(harmonic(drplPacVolGnExpDen("
        '"(v(\\"/RF_P\\" ?result \\"pac\\")-v(\\"/RF_N\\" ?result \\"pac\\"))" '
        "\\'(0) nil) \\'-1))"
    )
    request["metrics"][0]["expression"] = expression
    request["metrics"][0]["expression_sha256"] = expression_sha256(expression)
    request["metrics"][0]["result"] = "pac"
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    context = load_adapter_context(project_dir)
    script = render_ocean_replay_script(context)

    assert expression in script
    assert "drplPacVolGnExpDen" in script
    assert 'VT("/RF_P"' not in script
    assert 'VT("/RF_N"' not in script


def _metrics_dir_from_ocean_argv(project_dir: Path, argv: list[str]) -> Path:
    replay_path = Path(argv[argv.index("-replay") + 1])
    return project_dir / replay_path.parent


class FakeSuccessRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        self.commands.append(argv)
        stdout_path.write_text("fake stdout\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        assert timeout_s > 0
        if argv[0] == "spectre":
            psf_dir = cwd.parent / "psf"
            psf_dir.mkdir(parents=True, exist_ok=True)
            (psf_dir / "spectre.out").write_text("fake spectre out\n", encoding="utf-8")
        elif argv[0] == "ocean":
            assert cwd.name == "bridge_test_inv"
            metrics_dir = _metrics_dir_from_ocean_argv(cwd, argv)
            request = _load_json(metrics_dir.parent / "metric_extraction_request.json")
            lines = ["metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"]
            for index, metric in enumerate(request["metrics"], start=1):
                lines.append(
                    f"{metric['name']}\t{index}.25\t{metric['unit']}\tpass\t"
                    f"{metric['expression_sha256']}\t\n"
                )
            (metrics_dir / "ocean.log").write_text("fake ocean log\n", encoding="utf-8")
            (metrics_dir / "ocean_scalars.tsv").write_text(
                "".join(lines),
                encoding="utf-8",
            )
        return CommandResult(
            return_code=0,
            started_at_utc="2026-06-02T00:30:00Z",
            completed_at_utc="2026-06-02T00:31:00Z",
        )


class FakeSpectreFailureRunner(FakeSuccessRunner):
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        self.commands.append(argv)
        stdout_path.write_text("fake stdout\n", encoding="utf-8")
        stderr_path.write_text("fake spectre failure\n", encoding="utf-8")
        if argv[0] == "spectre":
            return CommandResult(
                return_code=2,
                started_at_utc="2026-06-02T00:30:00Z",
                completed_at_utc="2026-06-02T00:31:00Z",
            )
        raise AssertionError("ocean should not run after spectre failure")


class FakeOceanFailureRunner(FakeSuccessRunner):
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        if argv[0] == "ocean":
            self.commands.append(argv)
            stdout_path.write_text("fake ocean stdout\n", encoding="utf-8")
            stderr_path.write_text("fake ocean failure\n", encoding="utf-8")
            metrics_dir = _metrics_dir_from_ocean_argv(cwd, argv)
            (metrics_dir / "ocean.log").write_text(
                "fake ocean failure log\n",
                encoding="utf-8",
            )
            (metrics_dir / "ocean_scalars.tsv").write_text(
                "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n",
                encoding="utf-8",
            )
            return CommandResult(
                return_code=3,
                started_at_utc="2026-06-02T00:31:00Z",
                completed_at_utc="2026-06-02T00:32:00Z",
            )
        return super().run(
            argv,
            cwd=cwd,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_s=timeout_s,
        )


class FakeTransientOceanFailureRunner(FakeSuccessRunner):
    def __init__(self) -> None:
        super().__init__()
        self.ocean_attempts = 0

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        if argv[0] == "ocean":
            self.ocean_attempts += 1
            if self.ocean_attempts == 1:
                self.commands.append(argv)
                stdout_path.write_text("fake ocean stdout\n", encoding="utf-8")
                stderr_path.write_text("fake ocean license failure\n", encoding="utf-8")
                metrics_dir = _metrics_dir_from_ocean_argv(cwd, argv)
                (metrics_dir / "ocean.log").write_text(
                    "license checkout failed\n",
                    encoding="utf-8",
                )
                return CommandResult(
                    return_code=35,
                    started_at_utc="2026-06-02T00:31:00Z",
                    completed_at_utc="2026-06-02T00:32:00Z",
                )
        return super().run(
            argv,
            cwd=cwd,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_s=timeout_s,
        )


class FakeOceanFailureWithoutArtifactsRunner(FakeSuccessRunner):
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        if argv[0] == "ocean":
            self.commands.append(argv)
            stdout_path.write_text("fake ocean stdout\n", encoding="utf-8")
            stderr_path.write_text("fake ocean failure\n", encoding="utf-8")
            return CommandResult(
                return_code=3,
                started_at_utc="2026-06-02T00:31:00Z",
                completed_at_utc="2026-06-02T00:32:00Z",
            )
        return super().run(
            argv,
            cwd=cwd,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_s=timeout_s,
        )


class FakeOceanMalformedScalarRunner(FakeSuccessRunner):
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        if argv[0] == "ocean":
            self.commands.append(argv)
            stdout_path.write_text("fake ocean stdout\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            metrics_dir = _metrics_dir_from_ocean_argv(cwd, argv)
            (metrics_dir / "ocean.log").write_text("fake ocean log\n", encoding="utf-8")
            (metrics_dir / "ocean_scalars.tsv").write_text(
                "metric\tvalue\tunit\tstatus\texpression_sha256\tmessage\n"
                "rise\tNaN\ts\tpass\tabc123\t\n",
                encoding="utf-8",
            )
            return CommandResult(
                return_code=0,
                started_at_utc="2026-06-02T00:31:00Z",
                completed_at_utc="2026-06-02T00:32:00Z",
            )
        return super().run(
            argv,
            cwd=cwd,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_s=timeout_s,
        )


def test_run_spectre_ocean_adapter_fake_success_writes_valid_contracts(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSuccessRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "succeeded"
    assert [command[0] for command in runner.commands] == ["spectre", "ocean"]
    real_report = check_real_run(project_dir)
    metric_report = check_metric_results(project_dir)
    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.PASS


def test_run_spectre_ocean_adapter_uses_project_root_for_ocean_paths(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSuccessRunner()

    run_spectre_ocean_adapter(project_dir, runner=runner)

    assert "+escchars" in runner.commands[0]
    assert "+preset=ax" in runner.commands[0]
    assert "+mt=10" in runner.commands[0]
    assert runner.commands[0][runner.commands[0].index("-format") + 1] == "psfxl"
    assert runner.commands[0][runner.commands[0].index("+log") + 1] == (
        "../psf/spectre.out"
    )
    assert runner.commands[0][runner.commands[0].index("-raw") + 1] == "../psf"
    assert runner.commands[1][runner.commands[1].index("-replay") + 1] == (
        "runs/real/real_001/metrics/metric_probe.ocn"
    )
    assert runner.commands[1][runner.commands[1].index("-log") + 1] == (
        "runs/real/real_001/metrics/ocean.log"
    )
    assert (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metrics"
        / "ocean_scalars.tsv"
    ).exists()
    script = (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metrics"
        / "metric_probe.ocn"
    ).read_text(encoding="utf-8")
    assert '"runs/real/real_001/psf"' in script
    assert '"runs/real/real_001/metrics/ocean_scalars.tsv"' in script


def test_run_spectre_ocean_adapter_accepts_multi_testbench_child_run(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_multi_testbench_project(tmp_path)
    runner = FakeSuccessRunner()

    result = run_spectre_ocean_adapter(
        project_dir,
        testbench_id="iip3",
        corner_id="nominal",
        runner=runner,
    )

    child_relative = "runs/real/real_001/testbenches/iip3/corners/nominal"
    assert result.status == "succeeded"
    assert result.result_manifest_path == (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "testbenches"
        / "iip3"
        / "corners"
        / "nominal"
        / "result_manifest.json"
    )
    assert result.metric_result_manifest_path == (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "testbenches"
        / "iip3"
        / "corners"
        / "nominal"
        / "metrics"
        / "metric_result_manifest.json"
    )
    assert runner.commands[1][runner.commands[1].index("-replay") + 1] == (
        f"{child_relative}/metrics/metric_probe.ocn"
    )
    metric_manifest = _load_json(result.metric_result_manifest_path)
    assert [metric["name"] for metric in metric_manifest["metrics"]] == ["IIP3"]


def test_load_adapter_context_accepts_corner_aware_child_run(tmp_path: Path) -> None:
    project_dir = _create_ready_corner_project(tmp_path)

    context = load_adapter_context(
        project_dir, testbench_id="cg_nf", corner_id="ss"
    )

    corner_relative = "runs/real/real_001/testbenches/cg_nf/corners/ss"
    assert context.run_id == "real_001"
    assert context.run_relative == corner_relative
    assert context.run_dir == (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "testbenches"
        / "cg_nf"
        / "corners"
        / "ss"
    )
    assert context.input_scs == context.run_dir / "netlist" / "input.scs"
    assert context.psf_dir == context.run_dir / "psf"
    assert context.metrics_dir == context.run_dir / "metrics"
    assert context.testbench_id == "cg_nf"
    assert context.corner_id == "ss"
    assert context.request.expected_psf_dir == f"{corner_relative}/psf"


def test_run_spectre_ocean_adapter_accepts_corner_aware_child_run(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_corner_project(tmp_path)
    runner = FakeSuccessRunner()

    result = run_spectre_ocean_adapter(
        project_dir,
        testbench_id="cg_nf",
        corner_id="ss",
        runner=runner,
    )

    corner_relative = "runs/real/real_001/testbenches/cg_nf/corners/ss"
    assert result.status == "succeeded"
    assert result.result_manifest_path == (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "testbenches"
        / "cg_nf"
        / "corners"
        / "ss"
        / "result_manifest.json"
    )
    assert result.metric_result_manifest_path == (
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "testbenches"
        / "cg_nf"
        / "corners"
        / "ss"
        / "metrics"
        / "metric_result_manifest.json"
    )
    manifest = _load_json(result.result_manifest_path)
    assert manifest.get("testbench_id") == "cg_nf"
    assert manifest.get("corner_id") == "ss"
    assert runner.commands[1][runner.commands[1].index("-replay") + 1] == (
        f"{corner_relative}/metrics/metric_probe.ocn"
    )


def test_run_spectre_ocean_adapter_records_actual_spectre_settings(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSuccessRunner()

    run_spectre_ocean_adapter(project_dir, runner=runner)

    manifest = _load_json(
        project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    )
    assert manifest["simulator"]["preset"] == "ax"
    assert manifest["simulator"]["output_format"] == "psfxl"
    assert manifest["simulator"]["threads_per_run"] == 10
    assert manifest["simulator"]["timeout_s"] == 3600


def test_load_adapter_context_rejects_spectre_setting_drift(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    request["spectre"]["timeout_s"] = 99
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    with pytest.raises(AdapterPreconditionError, match="spectre.timeout_s"):
        load_adapter_context(project_dir)


def test_adapter_accepts_missing_parallel_jobs_in_spectre_contract(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)

    context = load_adapter_context(project_dir, run_id="real_001")

    assert "parallel_jobs" not in context.prepared.spectre
    assert "parallel_jobs" not in context.request.spectre


def test_adapter_still_rejects_threads_per_run_mismatch(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    request_path = run_dir / "metric_extraction_request.json"
    request = _load_json(request_path)
    request["spectre"]["threads_per_run"] = 99
    _write_json(request_path, request)
    _refresh_metric_request_hash(run_dir)

    with pytest.raises(AdapterPreconditionError, match="spectre.threads_per_run"):
        load_adapter_context(project_dir, run_id="real_001")


def test_tool_entrypoint_reports_success_without_real_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    import tools.run_spectre_ocean_adapter as entrypoint

    def fake_run(project: Path, **kwargs):
        assert project == project_dir
        assert kwargs == {
            "run_id": "real_001",
            "testbench_id": None,
            "corner_id": None,
            "allow_overwrite": False,
        }
        return type(
            "Result",
            (),
            {
                "status": "succeeded",
                "run_id": "real_001",
                "result_manifest_path": project_dir
                / "runs"
                / "real"
                / "real_001"
                / "result_manifest.json",
                "metric_result_manifest_path": project_dir
                / "runs"
                / "real"
                / "real_001"
                / "metrics"
                / "metric_result_manifest.json",
                "issues": [],
            },
        )()

    monkeypatch.setattr(entrypoint, "run_spectre_ocean_adapter", fake_run)

    exit_code = entrypoint.main([str(project_dir), "--run-id", "real_001"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "succeeded" in captured.out
    assert "result_manifest=" in captured.out
    assert "metric_result_manifest=" in captured.out


def test_spectre_failure_writes_failed_result_manifest_and_skips_ocean(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSpectreFailureRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "failed"
    assert [command[0] for command in runner.commands] == ["spectre"]
    assert result.metric_result_manifest_path is None
    manifest = _load_json(result.result_manifest_path)
    assert manifest["status"] == "failed"
    assert manifest["result_data"] is None
    assert manifest["metric_result_manifest"] is None
    declared_artifacts = [manifest["log_file"], *manifest["artifact_files"]]
    assert "runs/real/real_001/psf/spectre.out" not in declared_artifacts
    assert "runs/real/real_001/psf" not in declared_artifacts
    for artifact in declared_artifacts:
        assert (project_dir / artifact).exists()
    real_report = check_real_run(project_dir)
    assert real_report.status == RealRunCheckStatus.PASS
    assert real_report.result_status == "failed"


def test_ocean_failure_writes_metric_failure_manifest(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeOceanFailureRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "failed"
    assert [command[0] for command in runner.commands] == [
        "spectre",
        "ocean",
        "ocean",
        "ocean",
    ]
    real_manifest = _load_json(result.result_manifest_path)
    assert real_manifest["status"] == "succeeded"
    assert real_manifest["result_data"] is not None
    assert result.metric_result_manifest_path is not None
    metric_manifest = _load_json(result.metric_result_manifest_path)
    assert metric_manifest["status"] == "failed"
    assert metric_manifest["ocean"]["return_code"] == 3
    assert metric_manifest["ocean"]["attempts"] == 3
    assert metric_manifest["ocean"]["return_codes"] == [3, 3, 3]
    requested = _load_json(
        project_dir / "runs" / "real" / "real_001" / "metric_extraction_request.json"
    )
    assert len(metric_manifest["metrics"]) == len(requested["metrics"])
    for metric in metric_manifest["metrics"]:
        assert metric["status"] == "failed"
        assert metric["value"] is None
        assert metric["value_text"] is None
        assert "ocean command failed" in metric["issues"]
    real_report = check_real_run(project_dir)
    metric_report = check_metric_results(project_dir)
    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.FAIL
    assert any("ocean return_code" in issue for issue in metric_report.issues)


def test_ocean_command_failure_retries_without_rerunning_spectre(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeTransientOceanFailureRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "succeeded"
    assert [command[0] for command in runner.commands] == [
        "spectre",
        "ocean",
        "ocean",
    ]
    assert runner.ocean_attempts == 2
    metric_manifest = _load_json(result.metric_result_manifest_path)
    assert metric_manifest["status"] == "succeeded"
    assert metric_manifest["ocean"]["return_code"] == 0
    assert metric_manifest["ocean"]["attempts"] == 2
    assert metric_manifest["ocean"]["return_codes"] == [35, 0]


def test_ocean_failure_without_log_or_scalars_declares_only_existing_artifacts(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeOceanFailureWithoutArtifactsRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "failed"
    assert [command[0] for command in runner.commands] == [
        "spectre",
        "ocean",
        "ocean",
        "ocean",
    ]
    manifest = _load_json(result.result_manifest_path)
    assert "runs/real/real_001/metrics/ocean.log" not in manifest["artifact_files"]
    assert (
        "runs/real/real_001/metrics/ocean_scalars.tsv" not in manifest["artifact_files"]
    )
    assert (
        "runs/real/real_001/metrics/metric_result_manifest.json"
        in manifest["artifact_files"]
    )
    for artifact in [manifest["log_file"], *manifest["artifact_files"]]:
        assert (project_dir / artifact).exists()
    real_report = check_real_run(project_dir)
    metric_report = check_metric_results(project_dir)
    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.FAIL
    assert any("ocean return_code" in issue for issue in metric_report.issues)
    metric_manifest = _load_json(
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metrics"
        / "metric_result_manifest.json"
    )
    assert metric_manifest["ocean"]["attempts"] == 3
    assert metric_manifest["ocean"]["return_codes"] == [3, 3, 3]


def test_ocean_zero_exit_with_malformed_scalars_writes_failure_manifests(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeOceanMalformedScalarRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "failed"
    assert result.metric_result_manifest_path is not None
    real_report = check_real_run(project_dir)
    metric_report = check_metric_results(project_dir)
    assert real_report.status == RealRunCheckStatus.PASS
    assert metric_report.status == MetricResultCheckStatus.FAIL
    metric_manifest = _load_json(result.metric_result_manifest_path)
    assert metric_manifest["ocean"]["return_code"] == 0
    assert any("not finite" in issue for issue in metric_manifest["issues"])


def test_adapter_rejects_overwrite_of_existing_success(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_spectre_ocean_adapter(project_dir, runner=FakeSuccessRunner())

    with pytest.raises(AdapterPreconditionError, match="result already exists"):
        run_spectre_ocean_adapter(project_dir, runner=FakeSuccessRunner())


def test_adapter_allows_overwrite_without_deleting_unrelated_files(tmp_path: Path) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    unrelated = run_dir / "keep.me"
    unrelated.write_text("do not delete\n", encoding="utf-8")
    run_spectre_ocean_adapter(project_dir, runner=FakeSuccessRunner())

    result = run_spectre_ocean_adapter(
        project_dir,
        runner=FakeSuccessRunner(),
        allow_overwrite=True,
    )

    assert result.status == "succeeded"
    assert unrelated.read_text(encoding="utf-8") == "do not delete\n"


@pytest.mark.parametrize(
    "relative_output",
    [
        "runs/real/real_001/metrics/metric_probe.ocn",
        "runs/real/real_001/spectre.stdout",
        "runs/real/real_001/spectre.stderr",
        "runs/real/real_001/result_manifest.json",
        "runs/real/real_001/metrics/ocean.stdout",
        "runs/real/real_001/metrics/ocean.stderr",
        "runs/real/real_001/metrics/metric_result_manifest.json",
        "runs/real/real_001/metrics/ocean.log",
        "runs/real/real_001/metrics/ocean_scalars.tsv",
        "runs/real/real_001/psf/spectre.out",
    ],
)
def test_run_spectre_ocean_adapter_rejects_symlinked_output_files(
    tmp_path: Path,
    relative_output: str,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    output_path = project_dir / relative_output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    outside_output = tmp_path / f"outside_{output_path.name}"
    outside_output.write_text("outside\n", encoding="utf-8")
    output_path.symlink_to(outside_output)

    with pytest.raises(AdapterPreconditionError, match="output file is a symlink"):
        run_spectre_ocean_adapter(project_dir, runner=FailingIfCalledRunner())


def test_run_spectre_ocean_adapter_rejects_symlinked_result_with_overwrite_allowed(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    result_path = project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    outside_output = tmp_path / "outside_result_manifest.json"
    outside_output.write_text("{}\n", encoding="utf-8")
    result_path.symlink_to(outside_output)

    with pytest.raises(AdapterPreconditionError, match="output file is a symlink"):
        run_spectre_ocean_adapter(
            project_dir,
            runner=FailingIfCalledRunner(),
            allow_overwrite=True,
        )


def test_run_spectre_ocean_adapter_ocean_log_argv_is_under_metrics(
    tmp_path: Path,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSuccessRunner()

    run_spectre_ocean_adapter(project_dir, runner=runner)

    ocean_command = runner.commands[1]
    assert ocean_command[ocean_command.index("-log") + 1] == (
        "runs/real/real_001/metrics/ocean.log"
    )


class FailingIfCalledRunner:
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        timeout_s: int,
    ) -> CommandResult:
        raise AssertionError(f"runner should not be called: {argv}")


@pytest.mark.parametrize(
    ("directory_name", "message"),
    [
        ("metrics", "metrics directory is a symlink"),
        ("psf", "psf directory is a symlink"),
    ],
)
def test_run_spectre_ocean_adapter_rejects_symlinked_output_directories(
    tmp_path: Path,
    directory_name: str,
    message: str,
) -> None:
    project_dir = _create_ready_real_run_project(tmp_path)
    run_dir = project_dir / "runs" / "real" / "real_001"
    target = tmp_path / f"outside_{directory_name}"
    target.mkdir()
    link = run_dir / directory_name
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(AdapterPreconditionError, match=message):
        run_spectre_ocean_adapter(project_dir, runner=FailingIfCalledRunner())


# ── B-10: command_trace tests (RED first) ──────────────────────────────


def test_local_success_result_manifest_has_command_trace_spectre_argv(
    tmp_path: Path,
) -> None:
    """B-10: local success result_manifest.json must contain command_trace.spectre.argv."""
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSuccessRunner()

    run_spectre_ocean_adapter(project_dir, runner=runner)

    manifest = _load_json(
        project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    )
    assert "command_trace" in manifest, "result_manifest must contain command_trace"
    ct = manifest["command_trace"]
    assert ct["schema_version"] == "1.0"
    assert ct["execution_mode"] == "local"
    assert "spectre" in ct, "command_trace must contain spectre sub-object"
    spectre_trace = ct["spectre"]
    assert isinstance(spectre_trace["argv"], list)
    assert spectre_trace["argv"][0] == "spectre"
    assert any("+preset=" in a for a in spectre_trace["argv"])
    assert any("+mt=" in a for a in spectre_trace["argv"])
    assert spectre_trace["cwd"] is not None
    assert spectre_trace["timeout_s"] > 0
    # Must not contain parallel_jobs anywhere in the trace
    trace_str = json.dumps(ct)
    assert "parallel_jobs" not in trace_str


def test_local_success_metric_manifest_has_command_trace_ocean_argv(
    tmp_path: Path,
) -> None:
    """B-10: local success metric_result_manifest.json must contain command_trace.ocean.argv."""
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSuccessRunner()

    run_spectre_ocean_adapter(project_dir, runner=runner)

    metric_manifest = _load_json(
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metrics"
        / "metric_result_manifest.json"
    )
    assert "command_trace" in metric_manifest, (
        "metric_result_manifest must contain command_trace"
    )
    ct = metric_manifest["command_trace"]
    assert ct["schema_version"] == "1.0"
    assert ct["execution_mode"] == "local"
    assert "ocean" in ct, "command_trace must contain ocean sub-object"
    ocean_trace = ct["ocean"]
    assert isinstance(ocean_trace["argv"], list)
    assert ocean_trace["argv"][0] == "ocean"
    assert "-nograph" in ocean_trace["argv"]
    assert "-replay" in ocean_trace["argv"]
    assert ocean_trace["mode"] == "nograph_replay"
    assert ocean_trace["timeout_s"] > 0
    assert isinstance(ocean_trace["return_code"], int)
    assert isinstance(ocean_trace["return_codes"], list)
    # Must not contain parallel_jobs
    trace_str = json.dumps(ct)
    assert "parallel_jobs" not in trace_str


def test_local_spectre_failure_result_manifest_still_has_command_trace(
    tmp_path: Path,
) -> None:
    """B-10: Spectre failure result manifest must still record command_trace."""
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSpectreFailureRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "failed"
    manifest = _load_json(result.result_manifest_path)
    assert "command_trace" in manifest, (
        "failure result_manifest must still contain command_trace"
    )
    ct = manifest["command_trace"]
    assert ct["execution_mode"] == "local"
    assert "spectre" in ct
    spectre_trace = ct["spectre"]
    assert isinstance(spectre_trace["argv"], list)
    assert spectre_trace["argv"][0] == "spectre"


def test_local_ocean_failure_metric_manifest_has_command_trace_with_return_codes(
    tmp_path: Path,
) -> None:
    """B-10: OCEAN failure metric manifest must have command_trace with return_codes."""
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeOceanFailureRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "failed"
    assert result.metric_result_manifest_path is not None
    metric_manifest = _load_json(result.metric_result_manifest_path)
    assert "command_trace" in metric_manifest, (
        "ocean failure metric_result_manifest must contain command_trace"
    )
    ct = metric_manifest["command_trace"]
    assert ct["execution_mode"] == "local"
    assert "ocean" in ct
    ocean_trace = ct["ocean"]
    assert isinstance(ocean_trace["argv"], list)
    assert ocean_trace["argv"][0] == "ocean"
    assert isinstance(ocean_trace["return_code"], int)
    assert isinstance(ocean_trace["return_codes"], list)
    assert len(ocean_trace["return_codes"]) > 0
    # Must not contain parallel_jobs
    trace_str = json.dumps(ct)
    assert "parallel_jobs" not in trace_str


def test_local_command_trace_does_not_contain_parallel_jobs(
    tmp_path: Path,
) -> None:
    """B-10: command_trace must never contain parallel_jobs in any field."""
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeSuccessRunner()

    run_spectre_ocean_adapter(project_dir, runner=runner)

    result_manifest = _load_json(
        project_dir / "runs" / "real" / "real_001" / "result_manifest.json"
    )
    metric_manifest = _load_json(
        project_dir
        / "runs"
        / "real"
        / "real_001"
        / "metrics"
        / "metric_result_manifest.json"
    )
    for manifest, label in [
        (result_manifest, "result_manifest"),
        (metric_manifest, "metric_result_manifest"),
    ]:
        ct_str = json.dumps(manifest.get("command_trace", {}))
        assert "parallel_jobs" not in ct_str, (
            f"command_trace in {label} must not contain parallel_jobs"
        )


def test_local_transient_ocean_failure_command_trace_has_retry_return_codes(
    tmp_path: Path,
) -> None:
    """B-10: transient OCEAN failure command_trace.ocean.return_codes matches manifest."""
    project_dir = _create_ready_real_run_project(tmp_path)
    runner = FakeTransientOceanFailureRunner()

    result = run_spectre_ocean_adapter(project_dir, runner=runner)

    assert result.status == "succeeded"
    assert result.metric_result_manifest_path is not None
    metric_manifest = _load_json(result.metric_result_manifest_path)
    assert "command_trace" in metric_manifest
    ocean_trace = metric_manifest["command_trace"]["ocean"]
    assert ocean_trace["return_codes"] == [35, 0]
    assert ocean_trace["return_code"] == 0
