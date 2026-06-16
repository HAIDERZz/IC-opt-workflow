from __future__ import annotations

import pytest

from hermes_workflow.fix_run_models import WaveformExport
from hermes_workflow.metric_requests import (
    build_metric_extraction_request,
    expression_sha256,
)


# ---------------------------------------------------------------------------
# Helpers to build a minimal ContractBundle-like object for
# build_metric_extraction_request()
# ---------------------------------------------------------------------------


class _FakeSpectreSettings:
    def __init__(self):
        self.engine = "spectre_x"
        self.preset = type("P", (), {"value": "ax"})()
        self.output_format = "psfxl"
        self.threads_per_run = 10
        self.timeout_s = 600


class _FakeSpectre:
    def __init__(self):
        self.spectre = _FakeSpectreSettings()


class _FakeMetricOcean:
    def __init__(self):
        self.expression = 'value(VT("/net1") 1n)'
        self.expression_source = type("ES", (), {"value": "user_approved"})()
        self.source_reference = "test_ref"
        self.expected_value_type = type("EVT", (), {"value": "real_scalar"})()
        self.nil_policy = type("NP", (), {"value": "fail"})()
        self.non_finite_policy = type("NFP", (), {"value": "fail"})()
        self.result = "tran"


class _FakeMetric:
    def __init__(self, name="rise", unit="s"):
        self.name = name
        self.unit = unit
        self.required_signals = ["net1"]
        self.ocean = _FakeMetricOcean()


class _FakeMetrics:
    def __init__(self, metrics=None):
        self.metrics = metrics or [_FakeMetric()]


class _FakeBundle:
    def __init__(self, metrics=None):
        self.spectre = _FakeSpectre()
        self.metrics = _FakeMetrics(metrics)


def _make_waveform_export(
    name="nf_pnoise",
    testbench="cg_nf",
    expression='getData("NF" ?result "pnoise")',
    nil_policy="fail",
) -> WaveformExport:
    return WaveformExport(
        name=name,
        testbench=testbench,
        expression=expression,
        output_format="csv",
        nil_policy=nil_policy,
    )


# ---------------------------------------------------------------------------
# Test 1: fix-run request with one waveform export includes waveform_exports
# ---------------------------------------------------------------------------


def test_request_with_waveform_exports_includes_waveform_exports_in_payload():
    bundle = _FakeBundle()
    wf = _make_waveform_export()
    payload = build_metric_extraction_request(
        bundle,
        run_id="real_001",
        candidate_id="real_001",
        prepared_input_scs="runs/real/real_001/netlist/input.scs",
        prepared_input_sha256="abc123",
        run_prefix="runs/real/real_001",
        waveform_exports=[wf],
    )
    assert "waveform_exports" in payload
    assert len(payload["waveform_exports"]) == 1


# ---------------------------------------------------------------------------
# Test 2: waveform export entry fields
# ---------------------------------------------------------------------------


def test_waveform_export_entry_has_required_fields():
    bundle = _FakeBundle()
    wf = _make_waveform_export()
    payload = build_metric_extraction_request(
        bundle,
        run_id="real_001",
        candidate_id="real_001",
        prepared_input_scs="runs/real/real_001/netlist/input.scs",
        prepared_input_sha256="abc123",
        run_prefix="runs/real/real_001",
        waveform_exports=[wf],
    )
    entry = payload["waveform_exports"][0]
    assert entry["name"] == "nf_pnoise"
    assert entry["testbench"] == "cg_nf"
    assert entry["expression"] == 'getData("NF" ?result "pnoise")'
    assert entry["expression_sha256"] == expression_sha256(
        'getData("NF" ?result "pnoise")'
    )
    assert entry["output_format"] == "csv"
    assert entry["nil_policy"] == "fail"
    assert "csv_output_file" in entry


# ---------------------------------------------------------------------------
# Test 3: scalar metric request output is unchanged when no waveform_exports
# ---------------------------------------------------------------------------


def test_scalar_metrics_unchanged_without_waveform_exports():
    bundle = _FakeBundle()
    payload = build_metric_extraction_request(
        bundle,
        run_id="real_001",
        candidate_id="real_001",
        prepared_input_scs="runs/real/real_001/netlist/input.scs",
        prepared_input_sha256="abc123",
    )
    # No waveform_exports key should be present (or should be empty list)
    assert payload.get("waveform_exports") is None or payload["waveform_exports"] == []
    # Existing scalar metrics are still present
    assert len(payload["metrics"]) == 1
    assert payload["metrics"][0]["name"] == "rise"


# ---------------------------------------------------------------------------
# Test 4: empty scalar metrics are allowed when waveform_exports present
# ---------------------------------------------------------------------------


def test_empty_scalar_metrics_allowed_with_waveform_exports():
    bundle = _FakeBundle(metrics=[])
    wf = _make_waveform_export()
    payload = build_metric_extraction_request(
        bundle,
        run_id="real_001",
        candidate_id="real_001",
        prepared_input_scs="runs/real/real_001/netlist/input.scs",
        prepared_input_sha256="abc123",
        run_prefix="runs/real/real_001",
        metrics_subset=[],
        waveform_exports=[wf],
    )
    assert payload["metrics"] == []
    assert len(payload["waveform_exports"]) == 1


# ---------------------------------------------------------------------------
# Test 5: no scalar metrics AND no waveform exports fails
# ---------------------------------------------------------------------------


def test_no_scalar_metrics_and_no_waveform_exports_fails():
    bundle = _FakeBundle(metrics=[])
    with pytest.raises(ValueError, match="must provide at least one"):
        build_metric_extraction_request(
            bundle,
            run_id="real_001",
            candidate_id="real_001",
            prepared_input_scs="runs/real/real_001/netlist/input.scs",
            prepared_input_sha256="abc123",
            metrics_subset=[],
        )


# ---------------------------------------------------------------------------
# Test: csv_output_file path for single-testbench (no testbench/corner)
# ---------------------------------------------------------------------------


def test_csv_output_file_single_testbench():
    bundle = _FakeBundle()
    wf = _make_waveform_export()
    payload = build_metric_extraction_request(
        bundle,
        run_id="real_001",
        candidate_id="real_001",
        prepared_input_scs="runs/real/real_001/netlist/input.scs",
        prepared_input_sha256="abc123",
        run_prefix="runs/real/real_001",
        waveform_exports=[wf],
    )
    entry = payload["waveform_exports"][0]
    assert entry["csv_output_file"] == (
        "runs/real/real_001/metrics/waveforms/nf_pnoise.csv"
    )


# ---------------------------------------------------------------------------
# Test: csv_output_file path for multi-testbench
# ---------------------------------------------------------------------------


def test_csv_output_file_multi_testbench():
    bundle = _FakeBundle(metrics=[])
    wf = _make_waveform_export()
    payload = build_metric_extraction_request(
        bundle,
        run_id="real_001",
        candidate_id="real_001",
        prepared_input_scs="runs/real/real_001/netlist/input.scs",
        prepared_input_sha256="abc123",
        run_prefix="runs/real/real_001/testbenches/cg_nf/corners/tt",
        metrics_subset=[],
        waveform_exports=[wf],
    )
    entry = payload["waveform_exports"][0]
    assert entry["csv_output_file"] == (
        "runs/real/real_001/testbenches/cg_nf/corners/tt/metrics/waveforms/nf_pnoise.csv"
    )
