from __future__ import annotations

import html
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hermes_workflow.optimizer_artifacts import load_optimizer_artifacts


REPORT_RELATIVE = Path("reports/optimizer_insight_report.json")
MARKDOWN_RELATIVE = Path("reports/optimizer_insight_report.md")
VISUALS_DIR_RELATIVE = Path("reports/optimizer_visuals")
CONVERGENCE_RELATIVE = VISUALS_DIR_RELATIVE / "convergence.svg"
STATUS_DISTRIBUTION_RELATIVE = VISUALS_DIR_RELATIVE / "status_distribution.svg"
PARAMETER_OBJECTIVE_RELATIVE = VISUALS_DIR_RELATIVE / "parameter_objective_scatter.svg"


@dataclass(frozen=True)
class OptimizerInsightReport:
    status: str
    evaluation_count: int
    status_counts: dict[str, int]
    best_observed: dict[str, Any] | None
    plots: dict[str, str]
    observed_relationships: dict[str, dict[str, dict[str, Any]]]
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
        "convergence": CONVERGENCE_RELATIVE.as_posix(),
        "parameter_objective_scatter": PARAMETER_OBJECTIVE_RELATIVE.as_posix(),
        "status_distribution": STATUS_DISTRIBUTION_RELATIVE.as_posix(),
    }
    relationships = _observed_relationships(traces, warnings)
    advanced = _advanced_visualization_payload(report_payload)

    report = OptimizerInsightReport(
        status="fail" if issues else "pass",
        evaluation_count=evaluation_count,
        status_counts=status_counts,
        best_observed=best_observed,
        plots=plot_paths,
        observed_relationships=relationships,
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
    (project_root / CONVERGENCE_RELATIVE).write_text(
        _convergence_svg(traces),
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
        "## Plots",
        "",
    ]
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
