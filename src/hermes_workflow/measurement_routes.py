"""Shared metric and waveform testbench-routing contract."""

from __future__ import annotations

from dataclasses import dataclass

from hermes_workflow.fix_run_models import WaveformExportsConfig
from hermes_workflow.schemas import MetricsConfig, TestbenchesConfig


@dataclass(frozen=True)
class MeasurementRouteIssue:
    file: str
    path: str
    message: str


def measurement_route_issues(
    *,
    metrics: MetricsConfig | None,
    waveform_exports: WaveformExportsConfig | None,
    testbenches: TestbenchesConfig | None,
) -> list[MeasurementRouteIssue]:
    """Return route errors for single- and multi-testbench projects."""
    declared = (
        {testbench.id for testbench in testbenches.testbenches}
        if testbenches is not None
        else None
    )
    issues: list[MeasurementRouteIssue] = []
    routed_testbenches: set[str] = set()

    for index, metric in enumerate(metrics.metrics if metrics is not None else []):
        if declared is None:
            if metric.testbench is not None:
                issues.append(
                    MeasurementRouteIssue(
                        file="metrics.yaml",
                        path=f"metrics[{index}].testbench",
                        message=(
                            f"metric {metric.name} must not declare testbench for a "
                            "single-testbench project"
                        ),
                    )
                )
        elif metric.testbench is None:
            issues.append(
                MeasurementRouteIssue(
                    file="metrics.yaml",
                    path=f"metrics[{index}].testbench",
                    message=(
                        f"metric {metric.name} must declare testbench when "
                        "Maestro Source.testbenches is used"
                    ),
                )
            )
        elif metric.testbench not in declared:
            issues.append(
                MeasurementRouteIssue(
                    file="metrics.yaml",
                    path=f"metrics[{index}].testbench",
                    message=(
                        f"metric {metric.name} references unknown testbench "
                        f"{metric.testbench}"
                    ),
                )
            )
        else:
            routed_testbenches.add(metric.testbench)

    for index, export in enumerate(
        waveform_exports.exports if waveform_exports is not None else []
    ):
        if declared is None:
            if export.testbench is not None:
                issues.append(
                    MeasurementRouteIssue(
                        file="waveform_exports.yaml",
                        path=f"exports[{index}].testbench",
                        message=(
                            f"waveform export {export.name} must not declare testbench "
                            "for a single-testbench project"
                        ),
                    )
                )
        elif export.testbench is None:
            issues.append(
                MeasurementRouteIssue(
                    file="waveform_exports.yaml",
                    path=f"exports[{index}].testbench",
                    message=(
                        f"waveform export {export.name} must declare testbench when "
                        "Maestro Source.testbenches is used"
                    ),
                )
            )
        elif export.testbench not in declared:
            issues.append(
                MeasurementRouteIssue(
                    file="waveform_exports.yaml",
                    path=f"exports[{index}].testbench",
                    message=(
                        f"waveform export {export.name} references unknown testbench "
                        f"{export.testbench}"
                    ),
                )
            )
        else:
            routed_testbenches.add(export.testbench)

    if testbenches is not None:
        for index, testbench in enumerate(testbenches.testbenches):
            if testbench.id not in routed_testbenches:
                issues.append(
                    MeasurementRouteIssue(
                        file="testbenches.yaml",
                        path=f"testbenches[{index}].id",
                        message=(
                            f"testbench {testbench.id} must have at least one routed "
                            "metric or waveform export"
                        ),
                    )
                )

    return issues
