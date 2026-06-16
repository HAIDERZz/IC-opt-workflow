from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from hermes_workflow.validate import ContractBundle


METRIC_BACKEND = "spectre_ocean_batch"
OCEAN_MODE = "nograph_replay"
OCEAN_READY_FORMATS = {"psfxl"}


def expression_sha256(expression: str) -> str:
    return hashlib.sha256(expression.encode("utf-8")).hexdigest()


def build_metric_extraction_request(
    bundle: ContractBundle,
    *,
    run_id: str,
    candidate_id: str,
    prepared_input_scs: str,
    prepared_input_sha256: str,
    run_prefix: str | None = None,
    metrics_subset: Sequence[Any] | None = None,
) -> dict:
    spectre = bundle.spectre.spectre
    if spectre.output_format not in OCEAN_READY_FORMATS:
        raise ValueError(
            "spectre.output_format must be OCEAN-ready for metric extraction: "
            f"{spectre.output_format}"
        )

    metrics = []
    selected_metrics = metrics_subset or bundle.metrics.metrics
    for metric in selected_metrics:
        if metric.ocean is None:
            raise ValueError(f"metric {metric.name} is missing ocean formula")
        ocean = metric.ocean
        entry = {
            "name": metric.name,
            "unit": metric.unit,
            "required_signals": metric.required_signals,
            "expression": ocean.expression,
            "expression_sha256": expression_sha256(ocean.expression),
            "expression_source": ocean.expression_source.value,
            "source_reference": ocean.source_reference,
            "expected_value_type": ocean.expected_value_type.value,
            "nil_policy": ocean.nil_policy.value,
            "non_finite_policy": ocean.non_finite_policy.value,
        }
        if ocean.result:
            entry["result"] = ocean.result
        metrics.append(entry)

    run_prefix = run_prefix or f"runs/real/{run_id}"
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "candidate_id": candidate_id,
        "backend": METRIC_BACKEND,
        "prepared_input_scs": prepared_input_scs,
        "prepared_input_sha256": prepared_input_sha256,
        "expected_psf_dir": f"{run_prefix}/psf",
        "spectre": {
            "engine": spectre.engine,
            "preset": spectre.preset.value,
            "output_format": spectre.output_format,
            "threads_per_run": spectre.threads_per_run,
            "timeout_s": spectre.timeout_s,
        },
        "ocean": {
            "mode": OCEAN_MODE,
            "script_file": f"{run_prefix}/metrics/metric_probe.ocn",
            "log_file": f"{run_prefix}/metrics/ocean.log",
            "scalar_output_file": f"{run_prefix}/metrics/ocean_scalars.tsv",
        },
        "metrics": metrics,
        "forbidden_actions": [
            "rewrite_metric_formula",
            "parse_psf_in_python",
            "modify_prepared_input_scs",
            "modify_immutable_config_files",
            "write_results_outside_run_dir",
        ],
    }
