from __future__ import annotations

import html
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from hermes_workflow.optimizer_artifacts import load_optimizer_artifacts
from hermes_workflow.validate import evaluate_objective


REPORT_RELATIVE = Path("reports/optimizer_insight_report.json")
MARKDOWN_RELATIVE = Path("reports/optimizer_insight_report.md")
VISUALS_DIR_RELATIVE = Path("reports/optimizer_visuals")
ALL_EVALUABLE_FOM_RELATIVE = VISUALS_DIR_RELATIVE / "all_evaluable_fom.svg"
BOTTLENECK_WEIGHTED_SCORE_RELATIVE = (
    VISUALS_DIR_RELATIVE / "bottleneck_weighted_score.svg"
)
CONVERGENCE_RELATIVE = VISUALS_DIR_RELATIVE / "convergence.svg"
FEASIBLE_CONVERGENCE_RELATIVE = VISUALS_DIR_RELATIVE / "feasible_convergence.svg"
STATUS_DISTRIBUTION_RELATIVE = VISUALS_DIR_RELATIVE / "status_distribution.svg"
PARAMETER_OBJECTIVE_RELATIVE = VISUALS_DIR_RELATIVE / "parameter_objective_scatter.svg"
CONSTRAINT_MARGINS_RELATIVE = VISUALS_DIR_RELATIVE / "constraint_margins.svg"


@dataclass(frozen=True)
class OptimizerInsightReport:
    status: str
    evaluation_count: int
    status_counts: dict[str, int]
    best_observed: dict[str, Any] | None
    plots: dict[str, str]
    all_evaluable_fom_summary: dict[str, Any]
    configured_objective_ranking: dict[str, Any]
    bottleneck_weighted_score_summary: dict[str, Any]
    ic_metric_summary: dict[str, Any]
    top_feasible_candidates: list[dict[str, Any]]
    constraint_margin_summary: dict[str, Any]
    observed_relationships: dict[str, dict[str, dict[str, Any]]]
    openbox_parameter_importance: dict[str, Any]
    advanced_surrogate_visualization: dict[str, str]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_path: Path | None = None
    markdown_path: Path | None = None


def generate_optimizer_insight_report(project_dir: str | Path) -> OptimizerInsightReport:
    project_root = Path(project_dir)
    issues: list[str] = []
    warnings: list[str] = []
    artifacts = load_optimizer_artifacts(project_root, issues)
    report_payload = artifacts.report
    traces = artifacts.traces

    if not traces:
        issues.append("no optimizer trace rows found")

    accepted = _load_json(project_root / "reports/optimizer_run_acceptance_report.json")
    if accepted and accepted.get("status") != "accepted":
        issues.append("optimizer acceptance report status is not accepted")

    evaluation_count = _int_value(report_payload.get("evaluation_count")) or len(traces)
    status_counts = dict(Counter(_string_value(row.get("status")) for row in traces))
    finite_rows = [row for row in traces if _finite_float(row.get("objective")) is not None]
    best_observed = _dict_value(report_payload.get("best_candidate"))
    if best_observed is None and finite_rows:
        best_observed = min(
            finite_rows,
            key=lambda row: _finite_float(row.get("objective")) or math.inf,
        )

    plot_paths = {
        "all_evaluable_fom": ALL_EVALUABLE_FOM_RELATIVE.as_posix(),
        "bottleneck_weighted_score": BOTTLENECK_WEIGHTED_SCORE_RELATIVE.as_posix(),
        "convergence": CONVERGENCE_RELATIVE.as_posix(),
        "feasible_convergence": FEASIBLE_CONVERGENCE_RELATIVE.as_posix(),
        "parameter_objective_scatter": PARAMETER_OBJECTIVE_RELATIVE.as_posix(),
        "constraint_margins": CONSTRAINT_MARGINS_RELATIVE.as_posix(),
        "status_distribution": STATUS_DISTRIBUTION_RELATIVE.as_posix(),
    }
    metric_contract = _load_metric_contract(project_root)
    all_evaluable_fom = _all_evaluable_fom_summary(
        traces,
        _string_value(metric_contract.get("objective_expression")),
        _string_value(metric_contract.get("objective_direction")),
    )
    configured_ranking = _configured_objective_ranking(traces, all_evaluable_fom)
    bottleneck_weighted = _bottleneck_weighted_score_summary(traces)
    top_feasible = _top_feasible_candidates(traces)
    constraint_margins = _constraint_margin_summary(traces, metric_contract)
    ic_summary = _ic_metric_summary(top_feasible, traces)
    relationships = _observed_relationships(traces, warnings)
    advanced = _advanced_visualization_payload(report_payload)
    openbox_importance = _openbox_parameter_importance(project_root, advanced, metric_contract)

    report = OptimizerInsightReport(
        status="fail" if issues else "pass",
        evaluation_count=evaluation_count,
        status_counts=status_counts,
        best_observed=best_observed,
        plots=plot_paths,
        all_evaluable_fom_summary=all_evaluable_fom,
        configured_objective_ranking=configured_ranking,
        bottleneck_weighted_score_summary=bottleneck_weighted,
        ic_metric_summary=ic_summary,
        top_feasible_candidates=top_feasible,
        constraint_margin_summary=constraint_margins,
        observed_relationships=relationships,
        openbox_parameter_importance=openbox_importance,
        advanced_surrogate_visualization=advanced,
        issues=issues,
        warnings=warnings,
        report_path=project_root / REPORT_RELATIVE,
        markdown_path=project_root / MARKDOWN_RELATIVE,
    )
    _write_outputs(project_root, report, traces)
    return report


def _write_outputs(
    project_root: Path,
    report: OptimizerInsightReport,
    traces: list[dict[str, Any]],
) -> None:
    visuals_dir = project_root / VISUALS_DIR_RELATIVE
    visuals_dir.mkdir(parents=True, exist_ok=True)
    (project_root / ALL_EVALUABLE_FOM_RELATIVE).write_text(
        _all_evaluable_fom_svg(report.all_evaluable_fom_summary),
        encoding="utf-8",
    )
    (project_root / BOTTLENECK_WEIGHTED_SCORE_RELATIVE).write_text(
        _bottleneck_weighted_score_svg(report.bottleneck_weighted_score_summary),
        encoding="utf-8",
    )
    (project_root / CONVERGENCE_RELATIVE).write_text(
        _convergence_svg(traces),
        encoding="utf-8",
    )
    (project_root / FEASIBLE_CONVERGENCE_RELATIVE).write_text(
        _feasible_convergence_svg(traces),
        encoding="utf-8",
    )
    (project_root / STATUS_DISTRIBUTION_RELATIVE).write_text(
        _status_distribution_svg(report.status_counts),
        encoding="utf-8",
    )
    (project_root / PARAMETER_OBJECTIVE_RELATIVE).write_text(
        _parameter_objective_svg(traces),
        encoding="utf-8",
    )
    (project_root / CONSTRAINT_MARGINS_RELATIVE).write_text(
        _constraint_margins_svg(traces, report.constraint_margin_summary),
        encoding="utf-8",
    )

    if report.report_path is not None:
        report.report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(report)
        payload["schema_version"] = "1.0"
        payload["report_path"] = REPORT_RELATIVE.as_posix()
        payload["markdown_path"] = MARKDOWN_RELATIVE.as_posix()
        report.report_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if report.markdown_path is not None:
        report.markdown_path.write_text(
            _markdown_report(report),
            encoding="utf-8",
        )


def _load_metric_contract(project_root: Path) -> dict[str, Any]:
    path = project_root / "config" / "metrics.yaml"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, yaml.YAMLError):
        return {"metrics": {}, "constraints": [], "objective_expression": ""}
    if not isinstance(payload, dict):
        return {"metrics": {}, "constraints": [], "objective_expression": ""}
    metrics: dict[str, dict[str, Any]] = {}
    for metric in payload.get("metrics", []):
        if not isinstance(metric, dict) or not isinstance(metric.get("name"), str):
            continue
        metrics[metric["name"]] = {
            "unit": _string_value(metric.get("unit")),
        }
    constraints: list[dict[str, Any]] = []
    for constraint in payload.get("constraints", []):
        if not isinstance(constraint, dict):
            continue
        metric_name = _string_value(constraint.get("metric"))
        op = _string_value(constraint.get("op"))
        limit = _parse_quantity(constraint.get("value"))
        if metric_name and op and limit is not None:
            constraints.append(
                {
                    "metric": metric_name,
                    "op": op,
                    "limit": limit,
                    "unit": metrics.get(metric_name, {}).get("unit", ""),
                }
            )
    objective = payload.get("objective", {})
    objective_expression = (
        _string_value(objective.get("expression")) if isinstance(objective, dict) else ""
    )
    objective_direction = (
        _string_value(objective.get("direction")) if isinstance(objective, dict) else ""
    )
    if objective_direction not in {"minimize", "maximize"}:
        objective_direction = "minimize"
    return {
        "metrics": metrics,
        "constraints": constraints,
        "objective_expression": objective_expression,
        "objective_direction": objective_direction,
    }


def _top_feasible_candidates(
    traces: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    feasible = [
        row
        for row in traces
        if row.get("status") == "feasible"
        and _finite_float(row.get("objective")) is not None
    ]
    top_rows = sorted(feasible, key=lambda row: _finite_float(row.get("objective")) or math.inf)[
        :limit
    ]
    candidates: list[dict[str, Any]] = []
    for row in top_rows:
        metrics = _dict_value(row.get("metrics"), default={})
        candidates.append(
            {
                "run_id": _string_value(row.get("run_id")),
                "evaluation_index": _int_value(row.get("evaluation_index")),
                "objective": _finite_float(row.get("objective")),
                "objective_display": _format_scientific(_finite_float(row.get("objective"))),
                "parameters": _dict_value(row.get("parameters"), default={}),
                "metrics": metrics,
                "metrics_display": {
                    name: _format_metric_value(name, value)
                    for name, value in sorted(metrics.items())
                    if _finite_float(value) is not None
                },
            }
        )
    return candidates


def _ic_metric_summary(
    top_feasible: list[dict[str, Any]],
    traces: list[dict[str, Any]],
) -> dict[str, Any]:
    best = top_feasible[0] if top_feasible else None
    metric_names = sorted(
        {key for row in traces for key in _dict_value(row.get("metrics"), default={}).keys()}
    )
    metric_summary: dict[str, dict[str, Any]] = {}
    feasible_rows = [row for row in traces if row.get("status") == "feasible"]
    for metric in metric_names:
        values = [
            value
            for row in feasible_rows
            if (value := _finite_float(_dict_value(row.get("metrics"), default={}).get(metric)))
            is not None
        ]
        if not values:
            continue
        metric_summary[metric] = {
            "min": min(values),
            "max": max(values),
            "min_display": _format_metric_value(metric, min(values)),
            "max_display": _format_metric_value(metric, max(values)),
        }
    return {
        "objective": {
            "best_feasible_run_id": best.get("run_id") if best else None,
            "best_feasible_objective": best.get("objective") if best else None,
            "best_feasible_objective_display": (
                best.get("objective_display") if best else None
            ),
            "feasible_count": len(feasible_rows),
        },
        "metrics": metric_summary,
    }


def _constraint_margin_summary(
    traces: list[dict[str, Any]],
    metric_contract: dict[str, Any],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for constraint in metric_contract.get("constraints", []):
        metric = constraint["metric"]
        margins: list[tuple[int, str, float]] = []
        for row in traces:
            value = _finite_float(_dict_value(row.get("metrics"), default={}).get(metric))
            if value is None:
                continue
            margin = _constraint_margin(value, constraint["limit"], constraint["op"])
            if margin is None:
                continue
            margins.append(
                (
                    _int_value(row.get("evaluation_index")),
                    _string_value(row.get("run_id")),
                    margin,
                )
            )
        if not margins:
            continue
        best_index, best_run, best_margin = max(margins, key=lambda item: item[2])
        worst_index, worst_run, worst_margin = min(margins, key=lambda item: item[2])
        summary[metric] = {
            "op": constraint["op"],
            "limit": constraint["limit"],
            "limit_display": _format_metric_value(metric, constraint["limit"]),
            "sample_count": len(margins),
            "passing_count": sum(1 for _idx, _run, margin in margins if margin >= 0),
            "violating_count": sum(1 for _idx, _run, margin in margins if margin < 0),
            "best_margin": best_margin,
            "best_margin_display": _format_metric_delta(metric, best_margin),
            "best_margin_run_id": best_run,
            "best_margin_evaluation_index": best_index,
            "worst_margin": worst_margin,
            "worst_margin_display": _format_metric_delta(metric, worst_margin),
            "worst_margin_run_id": worst_run,
            "worst_margin_evaluation_index": worst_index,
            "series": [
                {
                    "evaluation_index": index,
                    "run_id": run_id,
                    "margin": margin,
                    "margin_display": _format_metric_delta(metric, margin),
                    "normalized_margin": margin / max(abs(constraint["limit"]), 1e-30),
                }
                for index, run_id, margin in margins
            ],
        }
    return summary


def _constraint_margin(value: float, limit: float, op: str) -> float | None:
    if op in {"lt", "le", "lte", "<", "<="}:
        return limit - value
    if op in {"gt", "ge", "gte", ">", ">="}:
        return value - limit
    return None


def _observed_relationships(
    traces: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    parameter_names = sorted(
        {
            key
            for row in traces
            for key in _dict_value(row.get("parameters"), default={}).keys()
        }
    )
    metric_names = sorted(
        {key for row in traces for key in _dict_value(row.get("metrics"), default={}).keys()}
    )
    targets = ["objective", *metric_names]
    relationships: dict[str, dict[str, dict[str, Any]]] = {}
    for parameter in parameter_names:
        parameter_relationships: dict[str, dict[str, Any]] = {}
        for target in targets:
            pairs: list[tuple[float, float]] = []
            for row in traces:
                parameters = _dict_value(row.get("parameters"), default={})
                x_value = _parse_number(parameters.get(parameter))
                if target == "objective":
                    y_value = _finite_float(row.get("objective"))
                else:
                    metrics = _dict_value(row.get("metrics"), default={})
                    y_value = _finite_float(metrics.get(target))
                if x_value is None or y_value is None:
                    continue
                pairs.append((x_value, y_value))
            parameter_relationships[target] = _relationship_summary(pairs)
        relationships[parameter] = parameter_relationships
    if not relationships:
        warnings.append("no numeric parameter relationships could be computed")
    return relationships


def _relationship_summary(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    if len(pairs) < 3:
        return {
            "sample_count": len(pairs),
            "correlation": None,
            "relationship": "insufficient_data",
        }
    correlation = _pearson([pair[0] for pair in pairs], [pair[1] for pair in pairs])
    if correlation is None:
        relationship = "weak"
    elif correlation > 0.25:
        relationship = "positive"
    elif correlation < -0.25:
        relationship = "negative"
    else:
        relationship = "weak"
    return {
        "sample_count": len(pairs),
        "correlation": None if correlation is None else round(correlation, 6),
        "relationship": relationship,
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    x_deltas = [value - x_mean for value in xs]
    y_deltas = [value - y_mean for value in ys]
    x_norm = math.sqrt(sum(value * value for value in x_deltas))
    y_norm = math.sqrt(sum(value * value for value in y_deltas))
    if x_norm == 0 or y_norm == 0:
        return None
    return sum(x * y for x, y in zip(x_deltas, y_deltas, strict=True)) / (
        x_norm * y_norm
    )


def _convergence_svg(traces: list[dict[str, Any]]) -> str:
    rows = [
        (index + 1, objective)
        for index, row in enumerate(traces)
        if (objective := _finite_float(row.get("objective"))) is not None
    ]
    if not rows:
        return _empty_svg("Convergence", "No finite objective values")
    best_rows: list[tuple[int, float]] = []
    best = math.inf
    for index, objective in rows:
        best = min(best, objective)
        best_rows.append((index, best))
    return _line_svg(
        title="Objective Convergence",
        series=[
            ("objective", rows, "#5a6ff0"),
            ("best so far", best_rows, "#138a4d"),
        ],
        x_label="evaluation",
        y_label="objective",
    )


def _all_evaluable_fom_summary(
    traces: list[dict[str, Any]],
    objective_expression: str,
    objective_direction: str = "minimize",
) -> dict[str, Any]:
    source = "configured_objective" if objective_expression else "stored_objective"
    direction = (
        objective_direction if objective_direction in {"minimize", "maximize"} else "minimize"
    )
    series: list[dict[str, Any]] = []
    for row_index, row in enumerate(traces):
        fom = (
            _evaluate_configured_objective(row, objective_expression)
            if objective_expression
            else _finite_float(row.get("objective"))
        )
        if fom is None:
            continue
        objective = _internal_objective_from_fom(fom, direction)
        evaluation_index = _int_value(row.get("evaluation_index")) or row_index + 1
        series.append(
            {
                "evaluation_index": evaluation_index,
                "run_id": _string_value(row.get("run_id")),
                "fom": fom,
                "fom_display": _format_scientific(fom),
                "objective": objective,
                "objective_display": _format_scientific(objective),
            }
        )
    best = min(series, key=lambda item: item["objective"]) if series else {}
    return {
        "source": source,
        "direction": direction,
        "objective_expression": objective_expression or None,
        "sample_count": len(series),
        "best_run_id": best.get("run_id"),
        "best_evaluation_index": best.get("evaluation_index"),
        "best_fom": best.get("fom"),
        "best_fom_display": best.get("fom_display"),
        "best_objective": best.get("objective"),
        "best_objective_display": best.get("objective_display"),
        "series": series,
    }


def _internal_objective_from_fom(fom: float, direction: str) -> float:
    return -fom if direction == "maximize" else fom


def _evaluate_configured_objective(
    row: dict[str, Any],
    objective_expression: str,
) -> float | None:
    metrics: dict[str, float] = {}
    for name, value in _dict_value(row.get("metrics"), default={}).items():
        numeric = _parse_number(value)
        if numeric is not None:
            metrics[str(name)] = numeric
    if not metrics:
        return None
    try:
        objective = evaluate_objective(objective_expression, metrics)
    except (KeyError, ValueError, ZeroDivisionError, OverflowError):
        return None
    return objective if math.isfinite(objective) else None


def _configured_objective_ranking(
    traces: list[dict[str, Any]],
    all_evaluable_fom: dict[str, Any],
    *,
    limit: int = 10,
) -> dict[str, Any]:
    rows_by_run_id = {
        _string_value(row.get("run_id")): row
        for row in traces
        if _string_value(row.get("run_id"))
    }
    rows_by_index = {
        _int_value(row.get("evaluation_index")): row
        for row in traces
        if _int_value(row.get("evaluation_index"))
    }
    ranked_points = sorted(
        [
            point
            for point in all_evaluable_fom.get("series", [])
            if isinstance(point, dict) and _finite_float(point.get("objective")) is not None
        ],
        key=lambda point: float(point["objective"]),
    )
    top_candidates: list[dict[str, Any]] = []
    for point in ranked_points[:limit]:
        run_id = _string_value(point.get("run_id"))
        evaluation_index = _int_value(point.get("evaluation_index"))
        row = rows_by_run_id.get(run_id) or rows_by_index.get(evaluation_index) or {}
        metrics = _dict_value(row.get("metrics"), default={})
        top_candidates.append(
            {
                "run_id": run_id,
                "evaluation_index": evaluation_index,
                "status": _string_value(row.get("status")),
                "fom": _finite_float(point.get("fom")),
                "fom_display": _format_scientific(_finite_float(point.get("fom"))),
                "objective": _finite_float(point.get("objective")),
                "objective_display": _format_scientific(_finite_float(point.get("objective"))),
                "parameters": _dict_value(row.get("parameters"), default={}),
                "metrics": metrics,
                "metrics_display": {
                    name: _format_metric_value(name, value)
                    for name, value in sorted(metrics.items())
                    if _parse_number(value) is not None
                },
            }
        )
    best = top_candidates[0] if top_candidates else None
    return {
        "source": all_evaluable_fom.get("source"),
        "direction": all_evaluable_fom.get("direction"),
        "objective_expression": all_evaluable_fom.get("objective_expression"),
        "sample_count": all_evaluable_fom.get("sample_count", 0),
        "best_candidate": best,
        "top_candidates": top_candidates,
    }


def _bottleneck_weighted_score_summary(traces: list[dict[str, Any]]) -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    for row_index, row in enumerate(traces):
        scores = _normalized_mixer_metric_scores(
            _dict_value(row.get("metrics"), default={})
        )
        if scores is None:
            continue
        weighted_score = (
            0.15 * scores["BW"]
            + 0.10 * scores["MAX_GAIN"]
            + 0.25 * scores["NF_3G"]
            + 0.30 * scores["IIP3"]
            + 0.20 * scores["P1DB"]
        )
        bottleneck_score = min(scores.values())
        combined_score = 0.7 * bottleneck_score + 0.3 * weighted_score
        evaluation_index = _int_value(row.get("evaluation_index")) or row_index + 1
        series.append(
            {
                "evaluation_index": evaluation_index,
                "run_id": _string_value(row.get("run_id")),
                "status": _string_value(row.get("status")),
                "weighted_score": weighted_score,
                "bottleneck_score": bottleneck_score,
                "combined_score": combined_score,
                "combined_objective": -combined_score,
                "component_scores": scores,
            }
        )
    best = max(series, key=lambda point: point["combined_score"]) if series else {}
    return {
        "source": "normalized_margin_components",
        "sample_count": len(series),
        "best_run_id": best.get("run_id"),
        "best_evaluation_index": best.get("evaluation_index"),
        "best_combined_score": best.get("combined_score"),
        "best_combined_objective": best.get("combined_objective"),
        "series": series,
        "formula": "score = 0.7*bottleneck + 0.3*weighted",
        "weights": {
            "BW": 0.15,
            "MAX_GAIN": 0.10,
            "NF_3G": 0.25,
            "IIP3": 0.30,
            "P1DB": 0.20,
        },
    }


def _normalized_mixer_metric_scores(metrics: dict[str, Any]) -> dict[str, float] | None:
    bw = _parse_number(metrics.get("BW"))
    max_gain = _parse_number(metrics.get("MAX_GAIN"))
    nf_3g = _parse_number(metrics.get("NF_3G"))
    iip3 = _parse_number(metrics.get("IIP3"))
    p1db = _parse_number(metrics.get("P1DB"))
    if None in {bw, max_gain, nf_3g, iip3, p1db} or bw is None or bw <= 0:
        return None
    return {
        "BW": _clamp01(10 * (math.log(bw / 19e9) / math.log(10)) / 0.5),
        "MAX_GAIN": _clamp01((max_gain - 4) / 0.5),
        "NF_3G": _clamp01((12 - nf_3g) / 0.1),
        "IIP3": _clamp01(iip3 / 0.5),
        "P1DB": _clamp01((p1db + 2) / 0.5),
    }


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _all_evaluable_fom_svg(summary: dict[str, Any]) -> str:
    rows = [
        (
            _int_value(point.get("evaluation_index")),
            float(point["fom"]),
        )
        for point in summary.get("series", [])
        if isinstance(point, dict) and _finite_float(point.get("fom")) is not None
    ]
    if not rows:
        return _empty_svg("All Evaluable FoM", "No finite FoM values")
    direction = _string_value(summary.get("direction")) or "minimize"
    return _line_svg(
        title="All Evaluable FoM",
        series=[("FoM", rows, "#5a6ff0")],
        x_label="evaluation",
        y_label=f"FoM ({direction})",
    )


def _bottleneck_weighted_score_svg(summary: dict[str, Any]) -> str:
    points = [
        point
        for point in summary.get("series", [])
        if isinstance(point, dict)
        and _finite_float(point.get("weighted_score")) is not None
        and _finite_float(point.get("bottleneck_score")) is not None
    ]
    if not points:
        return _empty_svg(
            "Normalized Margin Bottleneck Plot",
            "No complete BW/MAX_GAIN/NF_3G/IIP3/P1DB score points",
        )
    width = 820
    height = 520
    margin = 76
    plot_width = width - margin * 2
    plot_height = height - margin * 2
    parts = [
        _svg_header(width, height),
        _svg_text(24, 34, "Normalized Margin Bottleneck Plot", 18),
        _svg_rect(margin, margin, plot_width, plot_height, "#ffffff", "#d0d4dc"),
    ]
    for tick in [0.0, 0.25, 0.5, 0.75, 1.0]:
        x1, y1 = _scale_point(tick, 0.0, 0.0, 1.0, 0.0, 1.0, margin, margin, plot_width, plot_height)
        x2, y2 = _scale_point(tick, 1.0, 0.0, 1.0, 0.0, 1.0, margin, margin, plot_width, plot_height)
        parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#e3e6ec" stroke-width="1"/>')
        x3, y3 = _scale_point(0.0, tick, 0.0, 1.0, 0.0, 1.0, margin, margin, plot_width, plot_height)
        x4, y4 = _scale_point(1.0, tick, 0.0, 1.0, 0.0, 1.0, margin, margin, plot_width, plot_height)
        parts.append(f'<line x1="{x3:.2f}" y1="{y3:.2f}" x2="{x4:.2f}" y2="{y4:.2f}" stroke="#e3e6ec" stroke-width="1"/>')
    for score, color in [(0.2, "#5a6ff0"), (0.4, "#e08b2d"), (0.6, "#2f9e44"), (0.8, "#d64545")]:
        line = _score_line_segment(score)
        if line is None:
            continue
        (x_start, y_start), (x_end, y_end) = line
        sx1, sy1 = _scale_point(x_start, y_start, 0.0, 1.0, 0.0, 1.0, margin, margin, plot_width, plot_height)
        sx2, sy2 = _scale_point(x_end, y_end, 0.0, 1.0, 0.0, 1.0, margin, margin, plot_width, plot_height)
        parts.append(f'<line x1="{sx1:.2f}" y1="{sy1:.2f}" x2="{sx2:.2f}" y2="{sy2:.2f}" stroke="{color}" stroke-width="1.5" opacity="0.75"/>')
        parts.append(_svg_text(sx2 + 6, sy2 + 4, f"score={score:.1f}", 11))
    best_run_id = _string_value(summary.get("best_run_id"))
    color_by_status = {
        "feasible": "#2f9e44",
        "constraint_failed": "#e08b2d",
        "metric_check_failed": "#d64545",
        "real_check_failed": "#6b7280",
    }
    for point in points:
        weighted_score = float(point["weighted_score"])
        bottleneck_score = float(point["bottleneck_score"])
        sx, sy = _scale_point(weighted_score, bottleneck_score, 0.0, 1.0, 0.0, 1.0, margin, margin, plot_width, plot_height)
        run_id = _string_value(point.get("run_id"))
        color = color_by_status.get(_string_value(point.get("status")), "#5a6ff0")
        radius = 6 if run_id == best_run_id else 3.5
        stroke = "#111827" if run_id == best_run_id else "none"
        parts.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="{radius}" fill="{color}" stroke="{stroke}" stroke-width="1.5"><title>{html.escape(run_id)} score={float(point["combined_score"]):.4g}</title></circle>')
        if run_id == best_run_id:
            parts.append(_svg_text(sx + 8, sy - 8, f"best {run_id}", 12))
    parts.append(_svg_text(width / 2, height - 24, "Weighted-sum score", 12, anchor="middle"))
    parts.append(_svg_text(18, height / 2, "Bottleneck score min(z_i)", 12))
    legend_items = [
        ("feasible", "#2f9e44"),
        ("constraint_failed", "#e08b2d"),
        ("metric_check_failed", "#d64545"),
        ("real_check_failed", "#6b7280"),
    ]
    for index, (label, color) in enumerate(legend_items):
        y = 56 + index * 18
        parts.append(_svg_rect(width - 210, y - 10, 12, 12, color, "none"))
        parts.append(_svg_text(width - 192, y, label, 11))
    parts.append("</svg>")
    return "\n".join(parts)


def _score_line_segment(score: float) -> tuple[tuple[float, float], tuple[float, float]] | None:
    x_min = max(0.0, (score - 0.7) / 0.3)
    x_max = min(1.0, score / 0.3)
    if x_min > x_max:
        return None
    return (
        (x_min, (score - 0.3 * x_min) / 0.7),
        (x_max, (score - 0.3 * x_max) / 0.7),
    )


def _feasible_convergence_svg(traces: list[dict[str, Any]]) -> str:
    rows = [
        (index + 1, objective)
        for index, row in enumerate(traces)
        if row.get("status") == "feasible"
        and (objective := _finite_float(row.get("objective"))) is not None
    ]
    if not rows:
        return _empty_svg("Feasible Objective Convergence", "No feasible objective values")
    best_rows: list[tuple[int, float]] = []
    best = math.inf
    for index, objective in rows:
        best = min(best, objective)
        best_rows.append((index, best))
    return _line_svg(
        title="Feasible Objective Convergence",
        series=[
            ("feasible objective", rows, "#5a6ff0"),
            ("best feasible so far", best_rows, "#138a4d"),
        ],
        x_label="evaluation",
        y_label="objective (feasible only)",
    )


def _status_distribution_svg(status_counts: dict[str, int]) -> str:
    if not status_counts:
        return _empty_svg("Status Distribution", "No status rows")
    width = 760
    height = 360
    margin = 60
    plot_width = width - margin * 2
    plot_height = height - margin * 2
    items = sorted(status_counts.items())
    max_count = max(status_counts.values()) or 1
    bar_gap = 18
    bar_width = max(20, (plot_width - bar_gap * (len(items) - 1)) / len(items))
    parts = [_svg_header(width, height), _svg_text(24, 32, "Status Distribution", 18)]
    parts.append(_svg_rect(margin, margin, plot_width, plot_height, "#ffffff", "#d0d4dc"))
    for idx, (status, count) in enumerate(items):
        x = margin + idx * (bar_width + bar_gap)
        bar_height = (count / max_count) * (plot_height - 30)
        y = margin + plot_height - bar_height
        parts.append(_svg_rect(x, y, bar_width, bar_height, "#6f8bdc", "none"))
        parts.append(_svg_text(x + bar_width / 2, y - 8, str(count), 12, anchor="middle"))
        parts.append(
            _svg_text(
                x + bar_width / 2,
                margin + plot_height + 20,
                status,
                11,
                anchor="middle",
            )
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _parameter_objective_svg(traces: list[dict[str, Any]]) -> str:
    parameter_names = sorted(
        {
            key
            for row in traces
            for key in _dict_value(row.get("parameters"), default={}).keys()
        }
    )
    if not parameter_names:
        return _empty_svg("Parameter vs Objective", "No numeric parameters")
    panels = []
    for parameter in parameter_names[:6]:
        points: list[tuple[float, float]] = []
        for row in traces:
            parameters = _dict_value(row.get("parameters"), default={})
            x_value = _parse_number(parameters.get(parameter))
            y_value = _finite_float(row.get("objective"))
            if x_value is None or y_value is None:
                continue
            points.append((x_value, y_value))
        if points:
            panels.append((parameter, points))
    if not panels:
        return _empty_svg("Parameter vs Objective", "No numeric parameter/objective pairs")

    width = 820
    panel_height = 220
    height = 60 + panel_height * len(panels)
    parts = [_svg_header(width, height), _svg_text(24, 32, "Parameter vs Objective", 18)]
    for idx, (parameter, points) in enumerate(panels):
        y_offset = 52 + idx * panel_height
        parts.extend(
            _scatter_panel(
                title=parameter,
                points=points,
                x=70,
                y=y_offset,
                width=690,
                height=150,
            )
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _constraint_margins_svg(
    traces: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    if not summary:
        return _empty_svg("Constraint Margins", "No configured constraint margins")
    series: list[tuple[str, list[tuple[int, float]], str]] = []
    colors = ["#138a4d", "#c77700", "#5a6ff0", "#b33f62", "#4e888c"]
    for index, (metric, metric_summary) in enumerate(sorted(summary.items())):
        points = [
            (
                _int_value(point.get("evaluation_index")),
                float(point.get("normalized_margin", 0.0)),
            )
            for point in metric_summary.get("series", [])
            if isinstance(point, dict)
        ]
        if points:
            series.append((metric, points, colors[index % len(colors)]))
    if not series:
        return _empty_svg("Constraint Margins", "No margin series")
    return _line_svg(
        title="Constraint Margins",
        series=series,
        x_label="evaluation",
        y_label="normalized margin (positive = pass)",
    )


def _line_svg(
    *,
    title: str,
    series: list[tuple[str, list[tuple[int, float]], str]],
    x_label: str,
    y_label: str,
) -> str:
    width = 820
    height = 420
    margin = 64
    plot_width = width - margin * 2
    plot_height = height - margin * 2
    all_points = [point for _name, points, _color in series for point in points]
    x_values = [point[0] for point in all_points]
    y_values = [point[1] for point in all_points]
    parts = [_svg_header(width, height), _svg_text(24, 32, title, 18)]
    parts.append(_svg_rect(margin, margin, plot_width, plot_height, "#ffffff", "#d0d4dc"))
    for name, points, color in series:
        path = _polyline_path(
            points,
            min(x_values),
            max(x_values),
            min(y_values),
            max(y_values),
            margin,
            margin,
            plot_width,
            plot_height,
        )
        parts.append(f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2"/>')
        legend_y = 56 + 18 * series.index((name, points, color))
        parts.append(_svg_rect(width - 190, legend_y - 10, 12, 12, color, "none"))
        parts.append(_svg_text(width - 170, legend_y, name, 12))
    parts.append(_svg_text(width / 2, height - 18, x_label, 12, anchor="middle"))
    parts.append(_svg_text(18, height / 2, y_label, 12))
    parts.append("</svg>")
    return "\n".join(parts)


def _scatter_panel(
    *,
    title: str,
    points: list[tuple[float, float]],
    x: float,
    y: float,
    width: float,
    height: float,
) -> list[str]:
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    parts = [_svg_text(x, y - 12, title, 13)]
    parts.append(_svg_rect(x, y, width, height, "#ffffff", "#d0d4dc"))
    for point_x, point_y in points:
        sx, sy = _scale_point(
            point_x,
            point_y,
            min(x_values),
            max(x_values),
            min(y_values),
            max(y_values),
            x,
            y,
            width,
            height,
        )
        parts.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="3" fill="#5a6ff0"/>')
    return parts


def _polyline_path(
    points: list[tuple[int, float]],
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    x: float,
    y: float,
    width: float,
    height: float,
) -> str:
    scaled = [
        _scale_point(point_x, point_y, min_x, max_x, min_y, max_y, x, y, width, height)
        for point_x, point_y in points
    ]
    return " ".join(f"{point_x:.2f},{point_y:.2f}" for point_x, point_y in scaled)


def _scale_point(
    point_x: float,
    point_y: float,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    x: float,
    y: float,
    width: float,
    height: float,
) -> tuple[float, float]:
    x_span = max(max_x - min_x, 1e-30)
    y_span = max(max_y - min_y, 1e-30)
    sx = x + ((point_x - min_x) / x_span) * width
    sy = y + height - ((point_y - min_y) / y_span) * height
    return sx, sy


def _markdown_report(report: OptimizerInsightReport) -> str:
    best = report.best_observed or {}
    lines = [
        "# Optimizer Insight Report",
        "",
        f"- Status: `{report.status}`",
        f"- Evaluation count: `{report.evaluation_count}`",
        f"- Status counts: `{json.dumps(report.status_counts, sort_keys=True)}`",
        "",
        "## Best observed",
        "",
        f"- Run: `{_string_value(best.get('run_id')) or 'n/a'}`",
        f"- Objective: `{best.get('objective', 'n/a')}`",
        f"- Parameters: `{json.dumps(best.get('parameters', {}), sort_keys=True)}`",
        "",
        "## IC-native Summary",
        "",
        f"- Best feasible run: `{report.ic_metric_summary['objective']['best_feasible_run_id'] or 'n/a'}`",
        f"- Feasible count: `{report.ic_metric_summary['objective']['feasible_count']}`",
        f"- Best feasible objective: `{report.ic_metric_summary['objective']['best_feasible_objective_display'] or 'n/a'}`",
        "",
        "## All evaluable FoM",
        "",
        f"- Source: `{report.all_evaluable_fom_summary['source']}`",
        f"- Direction: `{report.all_evaluable_fom_summary.get('direction', 'minimize')}`",
        f"- Sample count: `{report.all_evaluable_fom_summary['sample_count']}`",
        f"- Best run: `{report.all_evaluable_fom_summary['best_run_id'] or 'n/a'}`",
        f"- Best FoM: `{report.all_evaluable_fom_summary.get('best_fom_display') or 'n/a'}`",
        f"- Internal objective: `{report.all_evaluable_fom_summary['best_objective_display'] or 'n/a'}`",
        f"- Plot: `{report.plots['all_evaluable_fom']}`",
        "",
        "## Configured Objective Ranking",
        "",
        f"- Source: `{report.configured_objective_ranking['source']}`",
        f"- Direction: `{report.configured_objective_ranking.get('direction', 'minimize')}`",
        f"- Sample count: `{report.configured_objective_ranking['sample_count']}`",
    ]
    configured_best = report.configured_objective_ranking.get("best_candidate") or {}
    lines.extend(
        [
            f"- Best run: `{configured_best.get('run_id') or 'n/a'}`",
            f"- Best FoM: `{configured_best.get('fom_display') or 'n/a'}`",
            f"- Internal objective: `{configured_best.get('objective_display') or 'n/a'}`",
            "",
        ]
    )
    configured_top = report.configured_objective_ranking.get("top_candidates", [])
    if configured_top:
        for candidate in configured_top[:5]:
            lines.append(
                "- "
                f"{candidate['run_id']}: fom={candidate['fom_display']}, "
                f"objective={candidate['objective_display']}, "
                f"status={candidate['status']}, "
                f"parameters={json.dumps(candidate['parameters'], sort_keys=True)}, "
                f"metrics={json.dumps(candidate['metrics_display'], sort_keys=True)}"
            )
    else:
        lines.append("- No configured objective candidates.")
    bottleneck = report.bottleneck_weighted_score_summary
    lines.extend(
        [
            "",
            "## Normalized Margin Bottleneck Plot",
            "",
            f"- Sample count: `{bottleneck['sample_count']}`",
            f"- Best run: `{bottleneck['best_run_id'] or 'n/a'}`",
            f"- Best score: `{_format_scientific(_finite_float(bottleneck.get('best_combined_score')))}`",
            f"- Plot: `{report.plots['bottleneck_weighted_score']}`",
        ]
    )
    lines.extend(
        [
            "",
            "## Top feasible candidates",
            "",
        ]
    )
    if report.top_feasible_candidates:
        for candidate in report.top_feasible_candidates[:5]:
            lines.append(
                "- "
                f"{candidate['run_id']}: objective={candidate['objective_display']}, "
                f"parameters={json.dumps(candidate['parameters'], sort_keys=True)}, "
                f"metrics={json.dumps(candidate['metrics_display'], sort_keys=True)}"
            )
    else:
        lines.append("- No feasible candidates.")
    lines.extend(
        [
            "",
            "## Constraint margins",
            "",
        ]
    )
    if report.constraint_margin_summary:
        for metric, summary in sorted(report.constraint_margin_summary.items()):
            lines.append(
                "- "
                f"{metric}: limit={summary['limit_display']}, "
                f"best_margin={summary['best_margin_display']} "
                f"({summary['best_margin_run_id']}), "
                f"worst_margin={summary['worst_margin_display']} "
                f"({summary['worst_margin_run_id']}), "
                f"pass={summary['passing_count']}/{summary['sample_count']}"
            )
    else:
        lines.append("- No configured constraints were found.")
    lines.extend(
        [
            "",
            "## OpenBox parameter importance",
            "",
        ]
    )
    if report.openbox_parameter_importance.get("status") == "available":
        lines.append(f"- Method: `{report.openbox_parameter_importance['method']}`")
        objective = report.openbox_parameter_importance.get("objective", {})
        for objective_name, rows in sorted(objective.items()):
            top = ", ".join(
                f"{row['parameter']} {row['share_display']}" for row in rows[:4]
            )
            lines.append(f"- {objective_name}: {top}")
        constraints = report.openbox_parameter_importance.get("constraints", {})
        for constraint_name, rows in sorted(constraints.items()):
            top = ", ".join(
                f"{row['parameter']} {row['share_display']}" for row in rows[:4]
            )
            lines.append(f"- {constraint_name}: {top}")
    else:
        lines.append(f"- Status: `{report.openbox_parameter_importance.get('status')}`")
    lines.extend(
        [
            "",
        "## Plots",
        "",
        ]
    )
    for name, path in sorted(report.plots.items()):
        lines.append(f"- {name}: `{path}`")
    lines.extend(["", "## Observed Relationships", ""])
    for parameter, targets in sorted(report.observed_relationships.items()):
        lines.append(f"### {parameter}")
        for target, summary in sorted(targets.items()):
            lines.append(
                "- "
                f"{target}: {summary['relationship']} "
                f"(corr={summary['correlation']}, n={summary['sample_count']})"
            )
        lines.append("")
    lines.extend(
        [
            "## Advanced surrogate visualization",
            "",
            f"- Status: `{report.advanced_surrogate_visualization['status']}`",
        ]
    )
    if reason := report.advanced_surrogate_visualization.get("reason"):
        lines.append(f"- Reason: {reason}")
    if html_path := report.advanced_surrogate_visualization.get("html_path"):
        lines.append(f"- HTML: `{html_path}`")
    if json_path := report.advanced_surrogate_visualization.get("json_path"):
        lines.append(f"- JSON data: `{json_path}`")
    if manifest_path := report.advanced_surrogate_visualization.get("manifest_path"):
        lines.append(f"- Manifest: `{manifest_path}`")
    if includes := report.advanced_surrogate_visualization.get("includes"):
        lines.append(f"- Includes: `{json.dumps(includes)}`")
    if warnings := report.advanced_surrogate_visualization.get("warnings"):
        lines.append(f"- Warnings: `{json.dumps(warnings)}`")
    lines.extend(
        [
            "",
            "Note: relationships are observed correlations from evaluated samples, not causal guarantees.",
            "",
        ]
    )
    return "\n".join(lines)


def _advanced_visualization_payload(report_payload: dict[str, Any]) -> dict[str, Any]:
    openbox_payload = _dict_value(report_payload.get("openbox"), default={})
    advanced = _dict_value(openbox_payload.get("advanced_visualization"), default={})
    if not advanced:
        return {
            "status": "not_generated",
            "reason": (
                "OpenBox advanced visualization was not recorded in the optimizer "
                "run report."
            ),
        }
    status = _string_value(advanced.get("status")) or "unknown"
    payload: dict[str, Any] = {
        "status": status,
    }
    for key in (
        "reason",
        "failure_kind",
        "mode",
        "html_path",
        "json_path",
        "output_dir",
        "manifest_path",
        "logging_dir",
    ):
        value = advanced.get(key)
        if isinstance(value, str) and value:
            payload[key] = value
    includes = advanced.get("includes")
    if isinstance(includes, list):
        payload["includes"] = [str(item) for item in includes]
    requested_includes = advanced.get("requested_includes")
    if isinstance(requested_includes, list):
        payload["requested_includes"] = [str(item) for item in requested_includes]
    warnings = advanced.get("warnings")
    if isinstance(warnings, list):
        payload["warnings"] = [str(item) for item in warnings]
    for key in ("open_html", "show_importance", "verify_surrogate"):
        value = advanced.get(key)
        if isinstance(value, bool):
            payload[key] = value
    return payload


def _openbox_parameter_importance(
    project_root: Path,
    advanced: dict[str, Any],
    metric_contract: dict[str, Any],
) -> dict[str, Any]:
    json_path = _string_value(advanced.get("json_path"))
    if not json_path:
        return {"status": "not_available", "reason": "no OpenBox visualization data path"}
    payload = _load_openbox_visualization_data(project_root / json_path)
    if not payload:
        return {"status": "not_available", "reason": "OpenBox visualization data not readable"}
    data = _dict_value(payload.get("data"), default={})
    importance = _dict_value(data.get("importance_data"), default={})
    parameter_names = [str(name) for name in importance.get("x", [])]
    method = _string_value(importance.get("method")) or "unknown"
    objective_data = _dict_value(importance.get("data"), default={})
    constraint_data = _dict_value(importance.get("con_data"), default={})
    constraints = metric_contract.get("constraints", [])
    result = {
        "status": "available",
        "method": method,
        "objective": {},
        "constraints": {},
    }
    for objective_name, values in objective_data.items():
        if isinstance(values, list):
            result["objective"][objective_name] = _importance_rows(parameter_names, values)
    for constraint_name, values in constraint_data.items():
        label = constraint_name
        if constraint_name.startswith("cons "):
            try:
                constraint_index = int(constraint_name.split()[1]) - 1
            except (IndexError, ValueError):
                constraint_index = -1
            if 0 <= constraint_index < len(constraints):
                label = str(constraints[constraint_index].get("metric", constraint_name))
        if isinstance(values, list):
            result["constraints"][label] = _importance_rows(parameter_names, values)
    return result


def _load_openbox_visualization_data(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return {}
    if text.startswith("var info=") and text.endswith(";"):
        text = text[len("var info=") : -1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _importance_rows(
    parameter_names: list[str],
    values: list[Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    numeric_values = [
        _finite_float(value) or 0.0
        for value in values[: len(parameter_names)]
    ]
    total = sum(abs(value) for value in numeric_values)
    for parameter, value in zip(parameter_names, numeric_values, strict=False):
        rows.append(
            {
                "parameter": parameter,
                "importance": value,
                "share": None if total == 0 else abs(value) / total,
                "share_display": "n/a" if total == 0 else f"{abs(value) / total * 100:.1f}%",
            }
        )
    return sorted(rows, key=lambda row: abs(row["importance"]), reverse=True)


def _empty_svg(title: str, message: str) -> str:
    width = 640
    height = 240
    return "\n".join(
        [
            _svg_header(width, height),
            _svg_text(24, 32, title, 18),
            _svg_text(24, 120, message, 14),
            "</svg>",
        ]
    )


def _svg_header(width: int | float, height: int | float) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )


def _svg_text(
    x: int | float,
    y: int | float,
    text: str,
    size: int,
    *,
    anchor: str = "start",
) -> str:
    escaped = html.escape(text)
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" text-anchor="{anchor}" fill="#1f2430">{escaped}</text>'
    )


def _svg_rect(
    x: int | float,
    y: int | float,
    width: int | float,
    height: int | float,
    fill: str,
    stroke: str,
) -> str:
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" '
        f'fill="{fill}" stroke="{stroke}"/>'
    )


def _parse_quantity(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        result = float(value)
        return result if math.isfinite(result) else None
    if not isinstance(value, str):
        return None
    first_token = value.strip().split(maxsplit=1)[0] if value.strip() else ""
    return _parse_number(first_token)


def _format_metric_value(metric: str, value: Any) -> str:
    numeric = _finite_float(value)
    if numeric is None:
        return "n/a"
    unit = _display_unit(metric, numeric)
    scaled = numeric / unit["scale"]
    return f"{_format_compact(scaled)} {unit['suffix']}".strip()


def _format_metric_delta(metric: str, value: Any) -> str:
    numeric = _finite_float(value)
    if numeric is None:
        return "n/a"
    unit = _display_unit(metric, numeric)
    scaled = numeric / unit["scale"]
    return f"{_format_compact(scaled)} {unit['suffix']}".strip()


def _format_scientific(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6g}"


def _display_unit(metric: str, value: float) -> dict[str, Any]:
    name = metric.lower()
    magnitude = abs(value)
    if name in {"rise", "fall", "delay", "time"}:
        if magnitude < 1e-9:
            return {"scale": 1e-12, "suffix": "ps"}
        if magnitude < 1e-6:
            return {"scale": 1e-9, "suffix": "ns"}
        return {"scale": 1e-6, "suffix": "us"}
    if name in {"dc", "power", "pwr"}:
        if magnitude < 1e-3:
            return {"scale": 1e-6, "suffix": "uW"}
        return {"scale": 1e-3, "suffix": "mW"}
    return {"scale": 1.0, "suffix": ""}


def _format_compact(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{value:.3g}"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dict_value(value: Any, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {} if default is None else default


def _int_value(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _parse_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(float(value)) else None
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    unit_multipliers = {
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "meg": 1e6,
        "g": 1e9,
    }
    lowered = cleaned.lower()
    for unit, multiplier in sorted(unit_multipliers.items(), key=lambda item: -len(item[0])):
        if lowered.endswith(unit):
            number = lowered[: -len(unit)]
            try:
                return float(number) * multiplier
            except ValueError:
                return None
    try:
        return float(cleaned)
    except ValueError:
        return None
