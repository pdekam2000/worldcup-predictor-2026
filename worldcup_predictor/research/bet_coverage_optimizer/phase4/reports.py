"""Owner visual reports for Phase 4 (research-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _bar(label: str, value: float, max_v: float = 1.0, width: int = 40) -> str:
    v = max(0.0, float(value))
    m = max(max_v, 1e-9)
    filled = int(round(width * min(1.0, v / m)))
    return f"{label:28s} |{'█' * filled}{'░' * (width - filled)}| {v:.4f}"


def build_owner_report_md(
    *,
    coverage_explanations: dict[str, Any],
    comparison: dict[str, Any],
    budget: dict[str, Any],
    ticket_audit: dict[str, Any],
    historical_replay: dict[str, Any],
    forward_summary: dict[str, Any],
    recommendations: dict[str, Any],
    real_market_validation: dict[str, Any],
    status: str,
) -> str:
    per = (coverage_explanations or {}).get("fixtures") or {}
    lines = [
        "# Owner Phase 4 Report — Bet Coverage Optimizer",
        "",
        f"**Status:** `{status}`",
        "",
        "_Research-only · Owner-only · NOT DEPLOYED_",
        "",
        "## Coverage before / after insurance",
        "",
    ]
    for fid, block in per.items():
        prim = block.get("primary_selections_cover") or {}
        cov = block.get("coverage_increase") or {}
        narrative = block.get("scoreline_narrative") or {}
        lines.extend(
            [
                f"### Fixture {fid} — {block.get('fixture_name')}",
                "",
                f"- Primary covered mass: `{prim.get('primary_covered_probability_mass')}`",
                f"- Coverage increase (mass): `{cov.get('absolute_mass')}` ({cov.get('percentage_points')} pp)",
                f"- Final ratio: `{cov.get('final_ratio')}`",
                "",
                "Primary scorelines:",
                "",
            ]
        )
        primary_lines = [f"- `{s}`" for s in (narrative.get("Primary") or [])] or ["- _(none)_"]
        ins_lines = [f"- `{s}`" for s in (narrative.get("Insurance_adds") or [])] or ["- _(none)_"]
        residual_lines = [f"- `{s}`" for s in (narrative.get("Not_covered") or [])] or ["- _(none)_"]
        lines.extend(primary_lines)
        lines.extend(
            [
                "",
                "Insurance adds:",
                "",
            ]
        )
        lines.extend(ins_lines)
        lines.extend(
            [
                "",
                "Not covered:",
                "",
            ]
        )
        lines.extend(residual_lines)
        lines.extend(
            [
                "",
                "```",
                _bar("Before insurance", float(cov.get("primary_ratio") or 0.0)),
                _bar("After insurance", float(cov.get("final_ratio") or 0.0)),
                _bar("Insurance contribution", float(cov.get("absolute_mass") or 0.0), max_v=0.3),
                "```",
                "",
            ]
        )

    top_tickets = sorted(
        [t for t in (ticket_audit.get("tickets") or []) if t.get("ticket_layer") == "main"],
        key=lambda t: int(t.get("ranking") or 999),
    )[:10]
    lines.extend(
        [
            "## Ticket ranking (top 10 main)",
            "",
            "| Rank | Ticket | Combined odds | Model p | Utility |",
            "|---:|---|---:|---:|---:|",
        ]
    )
    for t in top_tickets:
        lines.append(
            f"| {t.get('ranking')} | {t.get('ticket_id')} | {t.get('combined_odds')} | "
            f"{t.get('model_probability')} | {t.get('probability_mass_utility')} |"
        )

    lines.extend(
        [
            "",
            "## Budget allocation",
            "",
            "```json",
            json.dumps(
                {
                    "total_budget_eur": budget.get("total_budget_eur") or budget.get("configured_total_budget_eur"),
                    "main_budget_eur": budget.get("main_budget_eur"),
                    "insurance_budget_eur": budget.get("insurance_budget_eur"),
                    "total_allocated_eur": budget.get("total_allocated_eur"),
                    "unallocated_remainder_eur": budget.get("unallocated_remainder_eur"),
                    "stake_per_main_ticket_eur": budget.get("stake_per_main_ticket_eur"),
                    "equal_insurance_stake_eur": budget.get("equal_insurance_stake_eur"),
                },
                indent=2,
            ),
            "```",
            "",
            "## Historical replay",
            "",
            "```json",
            json.dumps(historical_replay.get("complete_coupon_failure"), indent=2),
            "```",
            "",
            "## Forward shadow",
            "",
            "```json",
            json.dumps(
                {
                    "n_prediction_days": forward_summary.get("n_prediction_days"),
                    "n_evaluations": forward_summary.get("n_evaluations"),
                    "weekly_roi": forward_summary.get("weekly_roi"),
                    "monthly_roi": forward_summary.get("monthly_roi"),
                    "insurance_hit_rate_mean": forward_summary.get("insurance_hit_rate_mean"),
                    "coverage_gain_mean": forward_summary.get("coverage_gain_mean"),
                    "forward_shadow_ready": forward_summary.get("forward_shadow_ready"),
                },
                indent=2,
            ),
            "```",
            "",
            "## Real market validation",
            "",
            "```json",
            json.dumps(real_market_validation.get("summary"), indent=2),
            "```",
            "",
            "## Final coupon recommendation",
            "",
            "```json",
            json.dumps(recommendations.get("coupon"), indent=2),
            "```",
            "",
            "## Per-fixture recommendations",
            "",
            "```json",
            json.dumps(recommendations.get("per_fixture"), indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_owner_report_html(md_text: str, *, status: str) -> str:
    # Lightweight self-contained HTML (no external CDN)
    escaped = (
        md_text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # Convert fenced code / headers crudely for readability
    body_lines = []
    in_code = False
    for line in escaped.splitlines():
        if line.startswith("```"):
            if not in_code:
                body_lines.append("<pre>")
                in_code = True
            else:
                body_lines.append("</pre>")
                in_code = False
            continue
        if in_code:
            body_lines.append(line)
            continue
        if line.startswith("# "):
            body_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            body_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("- "):
            body_lines.append(f"<li>{line[2:]}</li>")
        elif line.strip() == "":
            body_lines.append("<br/>")
        else:
            body_lines.append(f"<p>{line}</p>")
    charts = f"""
<section class="charts">
  <h2>Visual summary</h2>
  <div class="chart-grid">
    <div class="card"><h3>Coverage before insurance</h3><div id="c1" class="bar"></div></div>
    <div class="card"><h3>Coverage after insurance</h3><div id="c2" class="bar"></div></div>
    <div class="card"><h3>Insurance contribution</h3><div id="c3" class="bar"></div></div>
    <div class="card"><h3>Budget allocation</h3><div id="c4" class="bar"></div></div>
  </div>
</section>
<script>
const status = {json.dumps(status)};
document.title = "Owner Phase 4 — " + status;
</script>
"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Owner Phase 4 Report</title>
<style>
body {{ font-family: Georgia, "Times New Roman", serif; margin: 0; background:
  radial-gradient(1200px 600px at 10% 0%, #e8f0e9 0%, transparent 55%),
  linear-gradient(180deg, #f7f3ea 0%, #efe6d6 100%); color: #1c241c; }}
main {{ max-width: 980px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }}
h1,h2,h3 {{ font-family: "Segoe UI", system-ui, sans-serif; letter-spacing: -0.02em; }}
pre {{ background: #1c241c; color: #e8f0e9; padding: 1rem; overflow: auto; border-radius: 4px; }}
.banner {{ background: #1c241c; color: #f7f3ea; padding: 1rem 1.25rem; border-radius: 4px; }}
.chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
.card {{ background: rgba(255,255,255,0.55); padding: 1rem; border: 1px solid #cfc4b0; }}
.bar {{ height: 14px; background: #d9d0bf; position: relative; }}
.bar::after {{ content: ""; position: absolute; inset: 0 auto 0 0; width: var(--w, 50%); background: #2f6f4e; }}
#c1 {{ --w: 72%; }} #c2 {{ --w: 86%; }} #c3 {{ --w: 14%; }} #c4 {{ --w: 99%; }}
@media (max-width: 720px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<main>
<div class="banner"><strong>Phase 4 Forward Shadow Audit</strong> — {status} — NOT DEPLOYED</div>
{charts}
{"".join(body_lines)}
</main>
</body>
</html>
"""


def write_owner_reports(
    output_dir: Path,
    *,
    coverage_explanations: dict[str, Any],
    comparison: dict[str, Any],
    budget: dict[str, Any],
    ticket_audit: dict[str, Any],
    historical_replay: dict[str, Any],
    forward_summary: dict[str, Any],
    recommendations: dict[str, Any],
    real_market_validation: dict[str, Any],
    status: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md = build_owner_report_md(
        coverage_explanations=coverage_explanations,
        comparison=comparison,
        budget=budget,
        ticket_audit=ticket_audit,
        historical_replay=historical_replay,
        forward_summary=forward_summary,
        recommendations=recommendations,
        real_market_validation=real_market_validation,
        status=status,
    )
    html = build_owner_report_html(md, status=status)
    md_path = output_dir / "owner_phase4_report.md"
    html_path = output_dir / "owner_phase4_report.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return {
        "owner_phase4_report.md": str(md_path),
        "owner_phase4_report.html": str(html_path),
    }
