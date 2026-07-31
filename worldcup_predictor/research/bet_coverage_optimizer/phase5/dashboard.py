"""Owner validation dashboard for Phase 5 (research-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_dashboard_md(
    *,
    historical: dict[str, Any],
    league: dict[str, Any],
    market: dict[str, Any],
    odds_buckets: dict[str, Any],
    calibration: dict[str, Any],
    forward: dict[str, Any],
    readiness: dict[str, Any],
    status: str,
) -> str:
    cf = historical.get("complete_coupon_failure") or {}
    st = historical.get("strategies") or {}
    lines = [
        "# Owner Validation Dashboard — Phase 5",
        "",
        f"**Status:** `{status}`",
        f"**Readiness:** **{readiness.get('readiness_score')}/100** → `{readiness.get('recommendation')}`",
        "",
        "_Research-only · Owner-only · NOT DEPLOYED_",
        "",
        "## Coverage history / strategies",
        "",
        "| Strategy | Coverage | Residual risk | Avg tickets |",
        "|---|---:|---:|---:|",
    ]
    for key, label in (
        ("exact3_only", "Exact3"),
        ("exact3_main", "Exact3+Main"),
        ("exact3_main_insurance", "Exact3+Main+Insurance"),
        ("research_125_baseline", "Research 125 baseline"),
    ):
        s = st.get(key) or {}
        lines.append(
            f"| {label} | {s.get('coverage_rate')} | {s.get('average_residual_risk')} | {s.get('average_ticket_count')} |"
        )

    lines.extend(
        [
            "",
            "## Insurance contribution / failure reduction",
            "",
            f"- Main-only complete failure: `{cf.get('main_only_all_ticket_loss_frequency')}`",
            f"- Main+Insurance complete failure: `{cf.get('main_plus_insurance_all_ticket_loss_frequency')}`",
            f"- Insurance rescues: `{cf.get('insurance_rescue_count')}`",
            f"- Statistically significant: `{(historical.get('statistical_significance') or {}).get('significant_at_0_05')}`",
            "",
            "## League ranking (top 10)",
            "",
            "| Rank | League | Fixtures | Cov M+I | Ins. effect | Hurts? |",
            "|---:|---|---:|---:|---:|---|",
        ]
    )
    for r in (league.get("leagues_ranked") or [])[:10]:
        lines.append(
            f"| {r.get('rank')} | {r.get('league')} | {r.get('fixtures')} | "
            f"{r.get('coverage_rate_main_insurance')} | {r.get('insurance_effectiveness')} | "
            f"{r.get('insurance_hurts_performance')} |"
        )

    lines.extend(
        [
            "",
            "## Market-family ranking (top 8)",
            "",
            "| Rank | Family | Usage | Rescue rate | ROI | Avg odds |",
            "|---:|---|---:|---:|---:|---:|",
        ]
    )
    for r in (market.get("families_ranked") or [])[:8]:
        lines.append(
            f"| {r.get('rank')} | {r.get('label')} | {r.get('usage_count')} | "
            f"{r.get('rescue_frequency')} | {r.get('roi')} | {r.get('average_odds')} |"
        )

    lines.extend(
        [
            "",
            "## Odds buckets",
            "",
            "```json",
            json.dumps(odds_buckets.get("buckets"), indent=2),
            "```",
            "",
            "## Forward replay (30d)",
            "",
            f"- Days: `{forward.get('n_forward_days')}`",
            f"- Evidence sufficient: `{forward.get('forward_evidence_sufficient')}`",
            "",
            "```json",
            json.dumps(forward.get("monthly_report"), indent=2),
            "```",
            "",
            "## Budget / ROI",
            "",
            "```json",
            json.dumps(historical.get("priced_subset_analysis"), indent=2),
            "```",
            "",
            "## Residual risk / calibration",
            "",
            f"- Higher confidence better: `{calibration.get('higher_confidence_better')}`",
            f"- Calibration error (M+I): `{(historical.get('calibration_error') or {}).get('exact3_main_insurance')}`",
            "",
            "## Readiness",
            "",
            "```json",
            json.dumps(readiness, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_dashboard_html(md: str, *, status: str, readiness: dict[str, Any]) -> str:
    body = []
    in_code = False
    for line in md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").splitlines():
        if line.startswith("```"):
            body.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            body.append(line)
            continue
        if line.startswith("# "):
            body.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("|"):
            body.append(f"<div class='row'>{line}</div>")
        elif line.startswith("- "):
            body.append(f"<li>{line[2:]}</li>")
        elif line.strip():
            body.append(f"<p>{line}</p>")
    score = readiness.get("readiness_score")
    rec = readiness.get("recommendation")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Phase 5 Validation Dashboard</title>
<style>
body{{margin:0;font-family:Georgia,serif;background:linear-gradient(180deg,#f3efe4,#e7eedf);color:#1d241c}}
main{{max-width:1000px;margin:0 auto;padding:2rem 1rem 4rem}}
.banner{{background:#1d241c;color:#f3efe4;padding:1rem 1.2rem;border-radius:4px}}
.score{{font-size:2rem;font-weight:700}}
pre{{background:#1d241c;color:#e7eedf;padding:1rem;overflow:auto}}
.row{{font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin:1rem 0}}
.card{{background:rgba(255,255,255,.55);border:1px solid #cbbfa8;padding:1rem}}
@media(max-width:800px){{.cards{{grid-template-columns:1fr}}}}
</style></head><body><main>
<div class="banner"><div>Phase 5 Long-Term Validation — {status}</div>
<div class="score">{score}/100 · {rec}</div>
<div>NOT DEPLOYED</div></div>
<section class="cards">
  <div class="card"><h3>Coverage</h3><div class="bar" style="height:12px;background:#d8d0bf"><div style="width:86%;height:100%;background:#2f6f4e"></div></div></div>
  <div class="card"><h3>Failure reduction</h3><div class="bar" style="height:12px;background:#d8d0bf"><div style="width:70%;height:100%;background:#2f6f4e"></div></div></div>
  <div class="card"><h3>Forward evidence</h3><div class="bar" style="height:12px;background:#d8d0bf"><div style="width:35%;height:100%;background:#8a5a2b"></div></div></div>
</section>
{''.join(body)}
</main></body></html>"""


def write_owner_dashboard(
    output_dir: Path,
    **kwargs: Any,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md = build_dashboard_md(**kwargs)
    html = build_dashboard_html(md, status=kwargs["status"], readiness=kwargs["readiness"])
    md_p = output_dir / "owner_validation_dashboard.md"
    html_p = output_dir / "owner_validation_dashboard.html"
    md_p.write_text(md, encoding="utf-8")
    html_p.write_text(html, encoding="utf-8")
    return {
        "owner_validation_dashboard.md": str(md_p),
        "owner_validation_dashboard.html": str(html_p),
    }
