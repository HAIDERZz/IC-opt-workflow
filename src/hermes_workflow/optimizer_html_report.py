from __future__ import annotations

import html
import json
from typing import Any


def render_optimizer_insight_html(payload: dict[str, Any]) -> str:
    best = _dict(payload.get("best_observed"))
    tradeoff_interp = _dict(payload.get("tradeoff_interpretation_summary"))
    pareto = _dict(payload.get("pareto_tradeoff_summary"))
    history_ws = _dict(payload.get("history_warm_start"))
    history_reuse = _dict(payload.get("history_reuse_summary"))
    space = _dict(payload.get("space_compression_advisory"))
    advanced = _dict(payload.get("advanced_surrogate_visualization"))
    plots = _dict(payload.get("plots"))
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Optimizer Insight Report</title>",
            f"<style>{_css()}</style>",
            "</head>",
            "<body>",
            '<main class="page">',
            _header(payload),
            _section("Best observed", _best_point_html(best), "Best point"),
            _section(
                "Objective and feasibility",
                _status_counts_html(payload.get("status_counts")),
                "Run outcomes",
            ),
            _section(
                "Report-layer Pareto",
                _tradeoff_html(tradeoff_interp, pareto),
                "Trade-off analysis",
            ),
            _section(
                "Space Compression Advisory",
                _space_html(space),
                "Suggested next search window",
            ),
            _section(
                "History Warm-start",
                _history_html(history_ws, history_reuse),
                "Reused evidence",
            ),
            _section(
                "OpenBox Advanced Visualization",
                _advanced_html(advanced),
                "Linked OpenBox artifact",
            ),
            _section("Plot artifacts", _plots_html(plots), "Figures"),
            _section("Debug artifacts", _debug_artifacts_html(payload), "Raw evidence"),
            "</main>",
            "</body>",
            "</html>",
        ]
    )


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _header(payload: dict[str, Any]) -> str:
    status_counts = _dict(payload.get("status_counts"))
    feasible = status_counts.get("feasible", 0)
    pareto = _dict(payload.get("pareto_tradeoff_summary"))
    space = _dict(payload.get("space_compression_advisory"))
    ribbon_items = [
        ("status", payload.get("status", "unknown")),
        ("evaluations", payload.get("evaluation_count", 0)),
        ("feasible", feasible),
        ("pareto front", pareto.get("front_count", 0)),
        ("space advisory", space.get("status", "not_available")),
    ]
    items = "".join(
        f'<div class="ribbon-item"><span>{_esc(label)}</span><strong>{_esc(value)}</strong></div>'
        for label, value in ribbon_items
    )
    return (
        '<header class="report-header">'
        '<div class="eyebrow">IC optimizer report</div>'
        "<h1>Optimizer Insight Report</h1>"
        "<p>One static view of optimizer progress, trade-offs, reusable history, and suggested next search space.</p>"
        f'<div class="ribbon" aria-label="Run summary">{items}</div>'
        "</header>"
    )


def _section(title: str, body: str, label: str) -> str:
    return (
        '<section class="section">'
        '<div class="section-head">'
        f'<span class="section-label">{_esc(label)}</span>'
        f"<h2>{_esc(title)}</h2>"
        "</div>"
        f'<div class="section-body">{body}</div>'
        "</section>"
    )


def _best_point_html(best: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append('<div class="kv-grid">')
    parts.append(_kv("Run", best.get("run_id") or "n/a"))
    parts.append(_kv("Objective", _fmt(best.get("objective", "n/a"))))
    if best.get("status"):
        parts.append(_kv("Status", best.get("status")))
    params = _dict(best.get("parameters"))
    parts.append(
        f'<div class="kv"><span>Parameters</span><code>{_esc(json.dumps(params, sort_keys=True))}</code></div>'
    )
    parts.append("</div>")
    metrics = _dict(best.get("metrics"))
    if metrics:
        parts.append('<h3 class="sub-h">Best point metrics</h3>')
        parts.append('<div class="metric-chips">')
        for name, value in sorted(metrics.items()):
            parts.append(
                f'<span class="chip"><b>{_esc(name)}</b> {_esc(_fmt(value))}</span>'
            )
        parts.append("</div>")
    manifest_keys = [
        "metric_result_manifest",
        "result_manifest",
    ]
    manifests = [
        (key, best[key])
        for key in manifest_keys
        if best.get(key)
    ]
    if manifests:
        parts.append('<h3 class="sub-h">Result artifacts</h3>')
        parts.append("<ul>")
        for key, path in manifests:
            parts.append(f"<li>{_esc(key)}: <code>{_esc(path)}</code></li>")
        parts.append("</ul>")
    return "".join(parts)


def _status_counts_html(value: Any) -> str:
    counts = _dict(value)
    if not counts:
        return '<p class="muted">No status counts recorded.</p>'
    rows = "".join(
        f"<tr><td>{_esc(key)}</td><td>{_esc(count)}</td></tr>"
        for key, count in sorted(counts.items())
    )
    return f"<table><tbody>{rows}</tbody></table>"


def _tradeoff_html(
    tradeoff_interp: dict[str, Any], pareto: dict[str, Any]
) -> str:
    parts: list[str] = []
    parts.append(
        '<p class="note">Report-layer analysis only. Optimizer objective and '
        "best-candidate selection were not changed; optimizer mode unchanged.</p>"
    )
    front = _dict(tradeoff_interp.get("front_selectivity"))
    if front:
        parts.append('<div class="mini-metrics">')
        parts.append(_kv("Eligible", front.get("eligible_count", 0)))
        parts.append(_kv("Front", front.get("front_count", 0)))
        ratio = front.get("ratio", 0)
        parts.append(_kv("Ratio", f"{ratio:.2f}" if isinstance(ratio, (int, float)) else "n/a"))
        parts.append(_kv("Usefulness", front.get("usefulness", "unknown")))
        parts.append("</div>")
        msg = front.get("message")
        if msg:
            css_class = "warning" if front.get("usefulness") == "low" else "muted"
            parts.append(f'<p class="{css_class}">{_esc(msg)}</p>')
    blockers = tradeoff_interp.get("constraint_blockers")
    if isinstance(blockers, list) and blockers:
        parts.append('<h3 class="sub-h">Constraint blockers</h3>')
        body = "".join(
            f"<tr><td>{_esc(_dict(b).get('metric','n/a'))}</td>"
            f"<td>{_esc(_dict(b).get('failed_count', 0))}</td></tr>"
            for b in blockers[:10]
        )
        parts.append(
            "<table><thead><tr><th>Metric</th><th>Failed rows</th></tr>"
            f"</thead><tbody>{body}</tbody></table>"
        )
    feasible = tradeoff_interp.get("feasible_candidates")
    if isinstance(feasible, list) and feasible:
        parts.append('<h3 class="sub-h">Feasible candidates</h3>')
        body = "".join(_feasible_row_html(r) for r in feasible[:10])
        parts.append(
            "<table><thead><tr><th>Run</th><th>Objective</th><th>Parameters</th>"
            f"<th>Metrics</th></tr></thead><tbody>{body}</tbody></table>"
        )
    extremes = tradeoff_interp.get("metric_extremes")
    if isinstance(extremes, list) and extremes:
        parts.append('<h3 class="sub-h">Metric extremes</h3>')
        body = "".join(_extreme_row_html(r) for r in extremes[:12])
        parts.append(
            "<table><thead><tr><th>Metric</th><th>Direction</th><th>Run</th>"
            "<th>Status</th><th>Value</th><th>Failed constraints</th></tr>"
            f"</thead><tbody>{body}</tbody></table>"
        )
    if not tradeoff_interp:
        status = pareto.get("status", "not_available")
        reason = pareto.get("reason", "")
        if status == "available":
            front_rows = pareto.get("front_candidates")
            if isinstance(front_rows, list) and front_rows:
                parts.append('<div class="mini-metrics">')
                parts.append(_kv("Eligible", pareto.get("eligible_count", 0)))
                parts.append(_kv("Front", pareto.get("front_count", 0)))
                parts.append(_kv("Dominated", pareto.get("dominated_count", 0)))
                parts.append("</div>")
                body = "".join(_feasible_row_html(r) for r in front_rows[:12])
                parts.append(
                    "<table><thead><tr><th>Run</th><th>Objective</th><th>Parameters</th>"
                    f"<th>Metrics</th></tr></thead><tbody>{body}</tbody></table>"
                )
            else:
                parts.append(f'<p class="muted">Status: {_esc(status)}. {_esc(reason)}</p>')
        else:
            parts.append(f'<p class="muted">Status: {_esc(status)}. {_esc(reason)}</p>')
    return "".join(parts)


def _space_html(space: dict[str, Any]) -> str:
    status = space.get("status", "not_available")
    rows = space.get("suggestions")
    parts: list[str] = [
        '<p class="note">OpenBox Compressor dry-run, advisory only; '
        "these ranges were not applied to optimizer execution.</p>"
    ]
    if not isinstance(rows, list) or not rows:
        parts.append(
            f'<p class="muted">Status: {_esc(status)}. {_esc(space.get("reason", ""))}</p>'
        )
        return "".join(parts)
    parts.append('<div class="mini-metrics">')
    parts.append(_kv("Eligible", space.get("eligible_count", 0)))
    parts.append(_kv("Feasible", space.get("feasible_count", 0)))
    parts.append(_kv("Confidence", space.get("confidence", "unknown")))
    parts.append("</div>")
    feasible = space.get("feasible_count", 0)
    if isinstance(feasible, int) and feasible < 3:
        parts.append(
            '<p class="warning">Caution: few feasible rows were available, so '
            "support for these suggestions is limited.</p>"
        )
    body = "".join(
        "<tr>"
        f'<td>{_esc(_dict(row).get("variable", "n/a"))}</td>'
        f'<td>{_esc(_dict(_dict(row).get("original_display")).get("lower", "n/a"))}</td>'
        f'<td>{_esc(_dict(_dict(row).get("original_display")).get("upper", "n/a"))}</td>'
        f'<td>{_esc(_dict(_dict(row).get("suggested_display")).get("lower", "n/a"))}</td>'
        f'<td>{_esc(_dict(_dict(row).get("suggested_display")).get("upper", "n/a"))}</td>'
        f'<td>{_esc(_dict(row).get("compression_ratio", "n/a"))}</td>'
        "</tr>"
        for row in rows[:20]
    )
    parts.append(
        "<table><thead><tr><th>Variable</th><th>Original lower</th>"
        "<th>Original upper</th><th>Suggested lower</th>"
        f"<th>Suggested upper</th><th>Compression</th></tr></thead><tbody>{body}</tbody></table>"
    )
    return "".join(parts)


def _history_html(
    history_ws: dict[str, Any], history_reuse: dict[str, Any]
) -> str:
    parts: list[str] = []
    ws_status = history_ws.get("status", "not_available")
    parts.append(f'<p class="muted">History warm-start status: <strong>{_esc(ws_status)}</strong></p>')
    if ws_status != "not_available":
        parts.append('<div class="mini-metrics">')
        parts.append(_kv("Mode", history_ws.get("application_mode", "n/a")))
        accepted = history_ws.get("accepted_observation_count", "n/a")
        parts.append(
            f'<div class="kv" data-field="accepted_observation_count">'
            f"<span>Accepted</span><strong>{_esc(accepted)}</strong></div>"
        )
        parts.append(_kv("Applied", history_ws.get("applied_observation_count", "n/a")))
        parts.append(
            _kv("Applied to advisor", str(history_ws.get("applied_to_advisor", "n/a")).lower())
        )
        parts.append("</div>")
    if history_reuse.get("status") == "available":
        repeated = history_reuse.get("repeated_current_point_count", 0)
        status_counts = _dict(history_reuse.get("repeated_current_status_counts"))
        best_reused = history_reuse.get("best_candidate_reused_history")
        parts.append('<h3 class="sub-h">History reuse in this run</h3>')
        parts.append(
            f"<p>{repeated} current evaluation{'s' if repeated != 1 else ''} "
            "exactly matched accepted history parameter combinations.</p>"
        )
        if status_counts:
            parts.append("<ul>")
            for status, count in sorted(status_counts.items()):
                parts.append(f"<li>{_esc(status)}: {_esc(count)}</li>")
            parts.append("</ul>")
        parts.append(
            f"<p>Best candidate reused history: <strong>{_esc(str(best_reused).lower())}</strong></p>"
        )
        interp = history_reuse.get("interpretation")
        if interp:
            parts.append(f'<p class="note">{_esc(interp)}</p>')
    return "".join(parts)


def _advanced_html(advanced: dict[str, Any]) -> str:
    status = advanced.get("status", "not_available")
    parts: list[str] = [f'<p class="muted">Status: <strong>{_esc(status)}</strong></p>']
    for key in ("reason", "html_path", "json_path", "manifest_path"):
        value = advanced.get(key)
        if value:
            parts.append(f"<p>{_esc(key)}: <code>{_esc(value)}</code></p>")
    includes = advanced.get("includes")
    if isinstance(includes, list) and includes:
        parts.append("<ul>")
        for item in includes:
            parts.append(f"<li>{_esc(item)}</li>")
        parts.append("</ul>")
    return "".join(parts)


def _plots_html(plots: dict[str, Any]) -> str:
    if not plots:
        return '<p class="muted">No plot artifacts recorded.</p>'
    figures = []
    for name, path in sorted(plots.items()):
        src = _html_relative_report_path(str(path))
        figures.append(
            '<figure class="plot-figure">'
            f'<img src="{_esc(src)}" alt="{_esc(name)}">'
            f"<figcaption>{_esc(name)} <code>{_esc(path)}</code></figcaption>"
            "</figure>"
        )
    return '<div class="plot-gallery">' + "".join(figures) + "</div>"


def _debug_artifacts_html(payload: dict[str, Any]) -> str:
    parts: list[str] = [
        "<p>Raw JSON/JSONL remains the source of truth for exact counts and "
        "metric values. Inspect these artifacts before making detailed "
        "engineering recommendations.</p>",
        "<table><thead><tr><th>Artifact</th><th>Path</th></tr></thead><tbody>",
    ]
    entries: list[tuple[str, str]] = [
        ("JSON report", payload.get("report_path") or "reports/optimizer_insight_report.json"),
        ("Markdown report", payload.get("markdown_path") or "reports/optimizer_insight_report.md"),
        ("HTML report", payload.get("html_path") or "reports/optimizer_insight_report.html"),
        ("Optimizer run report", "reports/optimizer_run_report.json"),
        ("History warm-start audit", "reports/history_warm_start_audit.json"),
        (
            "Optimizer effectiveness audit",
            "reports/optimizer_effectiveness_audit.json",
        ),
    ]
    plots = payload.get("plots")
    if isinstance(plots, dict):
        for name, path in sorted(plots.items()):
            entries.append((f"Plot: {name}", str(path)))
    for label, path in entries:
        parts.append(f"<tr><td>{_esc(label)}</td><td><code>{_esc(path)}</code></td></tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _feasible_row_html(row: dict[str, Any]) -> str:
    metrics = _dict(row.get("metrics"))
    metric_text = ", ".join(
        f"{_esc(name)}={_esc(_fmt(value))}" for name, value in sorted(metrics.items())
    )
    return (
        "<tr>"
        f'<td>{_esc(row.get("run_id", "n/a"))}</td>'
        f'<td>{_esc(_fmt(row.get("objective", "n/a")))}</td>'
        f'<td><code>{_esc(json.dumps(_dict(row.get("parameters")), sort_keys=True))}</code></td>'
        f"<td>{metric_text}</td>"
        "</tr>"
    )


def _extreme_row_html(row: dict[str, Any]) -> str:
    failed = row.get("failed_constraints")
    failed_text = ", ".join(_esc(f) for f in failed) if isinstance(failed, list) else "n/a"
    return (
        "<tr>"
        f'<td>{_esc(row.get("metric", "n/a"))}</td>'
        f'<td>{_esc(row.get("direction", "n/a"))}</td>'
        f'<td>{_esc(row.get("run_id", "n/a"))}</td>'
        f'<td>{_esc(row.get("status", "n/a"))}</td>'
        f'<td>{_esc(_fmt(row.get("value", "n/a")))}</td>'
        f"<td>{failed_text}</td>"
        "</tr>"
    )


def _kv(label: str, value: Any) -> str:
    return (
        '<div class="kv">'
        f"<span>{_esc(label)}</span>"
        f"<strong>{_esc(value)}</strong>"
        "</div>"
    )


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        if abs(value) >= 1e6 or (abs(value) < 1e-3 and value != 0):
            return f"{value:.6g}"
        return f"{value:.4g}"
    return str(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _html_relative_report_path(path: str) -> str:
    return path.removeprefix("reports/")


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _css() -> str:
    return """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #17202a;
  --muted: #667085;
  --line: #d9dee7;
  --accent: #365f91;
  --soft-accent: #e9eef5;
  --pass: #2f9e44;
  --warn: #b7791f;
  --fail: #c2410c;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0;
}
.page {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 32px 0 48px;
}
.report-header {
  padding: 10px 0 24px;
  border-bottom: 1px solid var(--line);
}
.eyebrow,
.section-label {
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}
h1 {
  margin: 8px 0 10px;
  font-size: clamp(28px, 4vw, 44px);
  line-height: 1.05;
  letter-spacing: 0;
}
h2 {
  margin: 4px 0 0;
  font-size: 20px;
  line-height: 1.2;
  letter-spacing: 0;
}
.sub-h {
  margin: 18px 0 8px;
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
}
p {
  max-width: 820px;
  color: var(--muted);
  line-height: 1.58;
}
p strong { color: var(--text); }
.ribbon,
.kv-grid,
.mini-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}
.ribbon { margin-top: 22px; }
.ribbon-item,
.kv {
  min-width: 0;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 7px;
  padding: 12px;
}
.ribbon-item span,
.kv span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 4px;
}
.ribbon-item strong,
.kv strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 18px;
  line-height: 1.25;
}
.metric-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip {
  border: 1px solid var(--line);
  background: var(--soft-accent);
  border-radius: 5px;
  padding: 6px 10px;
  font-size: 13px;
  white-space: nowrap;
}
.chip b { color: var(--accent); }
.section {
  display: grid;
  grid-template-columns: minmax(180px, 260px) minmax(0, 1fr);
  gap: 28px;
  padding: 26px 0;
  border-bottom: 1px solid var(--line);
}
.section-body { min-width: 0; }
.note {
  border-left: 3px solid var(--accent);
  padding-left: 12px;
  color: var(--text);
}
.warning {
  border-left: 3px solid var(--warn);
  padding-left: 12px;
  color: var(--text);
  font-weight: 500;
}
.muted { color: var(--muted); }
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 7px;
  overflow: hidden;
}
th,
td {
  text-align: left;
  vertical-align: top;
  padding: 10px;
  border-bottom: 1px solid var(--line);
  overflow-wrap: anywhere;
}
th {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  background: var(--soft-accent);
}
code,
pre {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
pre {
  margin: 0;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 7px;
  padding: 12px;
  overflow-x: auto;
}
.plot-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 520px), 1fr));
  gap: 24px;
}
.plot-figure {
  margin: 0;
  min-width: 0;
}
.plot-figure img {
  display: block;
  width: 100%;
  min-height: 320px;
  object-fit: contain;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 7px;
}
.plot-figure figcaption {
  margin-top: 7px;
  color: var(--muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}
@media (max-width: 760px) {
  .page { width: min(100vw - 20px, 1180px); padding-top: 20px; }
  .section { display: block; padding: 22px 0; }
  .section-head { margin-bottom: 14px; }
  th, td { padding: 8px; }
  .plot-gallery { grid-template-columns: 1fr; }
  .plot-figure img { min-height: 0; }
}
"""
