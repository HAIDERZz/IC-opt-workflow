from __future__ import annotations

import html
import json
from typing import Any


def render_optimizer_insight_html(payload: dict[str, Any]) -> str:
    best = _dict(payload.get("best_observed"))
    pareto = _dict(payload.get("pareto_tradeoff_summary"))
    space = _dict(payload.get("space_compression_advisory"))
    advanced = _dict(payload.get("advanced_surrogate_visualization"))
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
            _section("Best observed", _best_observed_html(best), "Best point"),
            _section(
                "Objective and feasibility",
                _status_counts_html(payload.get("status_counts")),
                "Run outcomes",
            ),
            _section("Report-layer Pareto", _pareto_html(pareto), "Trade-off front"),
            _section(
                "Space Compression Advisory",
                _space_html(space),
                "Suggested next search window",
            ),
            _section(
                "History Warm-start",
                _json_block(_history_warm_start_payload(payload)),
                "Reused evidence",
            ),
            _section(
                "OpenBox Advanced Visualization",
                _json_block(advanced or {"status": "not_available"}),
                "Linked OpenBox artifact",
            ),
            _section("Plot artifacts", _plots_html(_dict(payload.get("plots"))), "Figures"),
            _section("Artifact index", _artifact_html(payload), "Files"),
            "</main>",
            "</body>",
            "</html>",
        ]
    )


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


def _best_observed_html(best: dict[str, Any]) -> str:
    return (
        '<div class="kv-grid">'
        f'{_kv("Run", best.get("run_id") or "n/a")}'
        f'{_kv("Objective", best.get("objective", "n/a"))}'
        f'{_kv("Parameters", json.dumps(best.get("parameters", {}), sort_keys=True), code=True)}'
        "</div>"
    )


def _status_counts_html(value: Any) -> str:
    counts = _dict(value)
    if not counts:
        return '<p class="muted">No status counts recorded.</p>'
    rows = "".join(
        f"<tr><td>{_esc(key)}</td><td>{_esc(count)}</td></tr>"
        for key, count in sorted(counts.items())
    )
    return f"<table><tbody>{rows}</tbody></table>"


def _pareto_html(pareto: dict[str, Any]) -> str:
    status = pareto.get("status", "not_available")
    rows = pareto.get("front_candidates")
    summary = (
        '<p class="note">Computed from existing raw metrics; optimizer mode unchanged. '
        "Best-candidate selection still follows the configured objective.</p>"
    )
    if not isinstance(rows, list) or not rows:
        return (
            summary
            + f'<p class="muted">Status: {_esc(status)}. {_esc(pareto.get("reason", ""))}</p>'
        )
    counts = (
        '<div class="mini-metrics">'
        f'{_kv("Eligible", pareto.get("eligible_count", 0))}'
        f'{_kv("Front", pareto.get("front_count", 0))}'
        f'{_kv("Dominated", pareto.get("dominated_count", 0))}'
        "</div>"
    )
    body = "".join(
        "<tr>"
        f'<td>{_esc(_dict(row).get("run_id", "n/a"))}</td>'
        f'<td><code>{_esc(json.dumps(_dict(row).get("metrics", {}), sort_keys=True))}</code></td>'
        f'<td><code>{_esc(json.dumps(_dict(row).get("parameters", {}), sort_keys=True))}</code></td>'
        "</tr>"
        for row in rows[:12]
    )
    return (
        summary
        + counts
        + "<table><thead><tr><th>Run</th><th>Metrics</th><th>Parameters</th></tr></thead>"
        + f"<tbody>{body}</tbody></table>"
    )


def _space_html(space: dict[str, Any]) -> str:
    status = space.get("status", "not_available")
    rows = space.get("suggestions")
    summary = (
        '<p class="note">OpenBox Compressor dry-run, advisory only; '
        "these ranges were not applied to optimizer execution.</p>"
    )
    if not isinstance(rows, list) or not rows:
        return (
            summary
            + f'<p class="muted">Status: {_esc(status)}. {_esc(space.get("reason", ""))}</p>'
        )
    counts = (
        '<div class="mini-metrics">'
        f'{_kv("Eligible", space.get("eligible_count", 0))}'
        f'{_kv("Feasible", space.get("feasible_count", 0))}'
        f'{_kv("Confidence", space.get("confidence", "unknown"))}'
        "</div>"
    )
    body = "".join(
        "<tr>"
        f'<td>{_esc(_dict(row).get("variable", "n/a"))}</td>'
        f'<td>{_esc(_dict(_dict(row).get("suggested_display")).get("lower", "n/a"))}</td>'
        f'<td>{_esc(_dict(_dict(row).get("suggested_display")).get("upper", "n/a"))}</td>'
        f'<td>{_esc(_dict(row).get("compression_ratio", "n/a"))}</td>'
        "</tr>"
        for row in rows[:20]
    )
    return (
        summary
        + counts
        + "<table><thead><tr><th>Variable</th><th>Suggested lower</th>"
        + f"<th>Suggested upper</th><th>Compression</th></tr></thead><tbody>{body}</tbody></table>"
    )


def _history_warm_start_payload(payload: dict[str, Any]) -> dict[str, Any]:
    direct = payload.get("history_warm_start")
    if isinstance(direct, dict):
        return direct
    openbox_payload = payload.get("openbox")
    if isinstance(openbox_payload, dict) and isinstance(
        openbox_payload.get("history_warm_start"), dict
    ):
        return openbox_payload["history_warm_start"]
    return {"status": "not_available"}


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
    return '<div class="plot-grid">' + "".join(figures) + "</div>"


def _artifact_html(payload: dict[str, Any]) -> str:
    artifacts = {
        "JSON": payload.get("report_path") or "reports/optimizer_insight_report.json",
        "Markdown": payload.get("markdown_path") or "reports/optimizer_insight_report.md",
        "HTML": payload.get("html_path") or "reports/optimizer_insight_report.html",
    }
    plots = payload.get("plots")
    if isinstance(plots, dict):
        artifacts.update({f"Plot: {name}": path for name, path in sorted(plots.items())})
    return _json_block(artifacts)


def _json_block(value: Any) -> str:
    return f"<pre>{_esc(json.dumps(value, indent=2, sort_keys=True))}</pre>"


def _kv(label: str, value: Any, *, code: bool = False) -> str:
    tag = "code" if code else "strong"
    return (
        '<div class="kv">'
        f"<span>{_esc(label)}</span>"
        f"<{tag}>{_esc(value)}</{tag}>"
        "</div>"
    )


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
  font-size: clamp(30px, 5vw, 52px);
  line-height: 1.02;
  letter-spacing: 0;
}
h2 {
  margin: 4px 0 0;
  font-size: 20px;
  line-height: 1.2;
  letter-spacing: 0;
}
p {
  max-width: 820px;
  color: var(--muted);
  line-height: 1.58;
}
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
.plot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}
.plot-figure {
  margin: 0;
  min-width: 0;
}
.plot-figure img {
  display: block;
  width: 100%;
  height: auto;
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
}
"""
