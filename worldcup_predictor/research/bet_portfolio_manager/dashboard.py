"""Owner portfolio dashboard (research-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_dashboard_md(
    *,
    daily: dict[str, Any],
    decision: dict[str, Any],
    ranking: dict[str, Any],
    allocation: dict[str, Any],
    risk: dict[str, Any],
    diversification: dict[str, Any],
    historical: dict[str, Any],
    forward: dict[str, Any],
    explanation: dict[str, Any],
    status: str,
) -> str:
    imp = historical.get("improvement") or {}
    lines = [
        "# Owner Portfolio Dashboard — Bet Portfolio Manager",
        "",
        f"**Status:** `{status}`",
        "",
        f"**Score:** **{daily.get('daily_portfolio_score')}** · Grade **{daily.get('grade')}** · Action **{decision.get('action')}**",
        "",
        "_Research-only · Owner-only · NOT DEPLOYED_",
        "",
        "## Explanation",
        "",
        *[f"- {x}" for x in (explanation.get("summary_lines") or [])],
        "",
        "## Capital allocation",
        "",
        "```json",
        json.dumps(allocation, indent=2),
        "```",
        "",
        "## Risk",
        "",
        "```json",
        json.dumps(risk, indent=2),
        "```",
        "",
        "## Fixture ranking (top)",
        "",
        "| Rank | Fixture | Priority | Residual | Eligible |",
        "|---:|---|---:|---:|---|",
    ]
    for r in (ranking.get("rankings") or [])[:15]:
        lines.append(
            f"| {r.get('portfolio_rank')} | {r.get('match_name') or r.get('fixture_id')} | "
            f"{r.get('investment_priority')} | {r.get('residual_risk')} | {r.get('eligible_for_capital')} |"
        )
    lines.extend(
        [
            "",
            "## Diversification / exposure",
            "",
            "```json",
            json.dumps(
                {
                    "diversification_score": diversification.get("diversification_score"),
                    "mean_pairwise_correlation": diversification.get("mean_pairwise_correlation"),
                    "league_concentration": diversification.get("league_concentration"),
                    "market_concentration": diversification.get("market_concentration"),
                },
                indent=2,
            ),
            "```",
            "",
            "## Historical performance (Always Bet vs Managed)",
            "",
            "```json",
            json.dumps(
                {
                    "always_bet": historical.get("always_bet"),
                    "portfolio_managed": historical.get("portfolio_managed"),
                    "improvement": imp,
                },
                indent=2,
            ),
            "```",
            "",
            "## Forward shadow",
            "",
            "```json",
            json.dumps(forward, indent=2),
            "```",
            "",
            f"- Skipped days (historical): `{imp.get('average_skipped_bad_days')}`",
            f"- ROI delta: `{imp.get('roi_delta')}`",
            f"- Drawdown improvement: `{imp.get('drawdown_delta')}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_dashboard_html(md: str, *, status: str, daily: dict[str, Any], decision: dict[str, Any]) -> str:
    body = []
    in_code = False
    escaped = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for line in escaped.splitlines():
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
    score = daily.get("daily_portfolio_score")
    grade = daily.get("grade")
    action = decision.get("action")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Portfolio Manager Dashboard</title>
<style>
body{{margin:0;font-family:Georgia,serif;background:linear-gradient(180deg,#eef3ea,#f6f1e6);color:#1c241c}}
main{{max-width:1000px;margin:0 auto;padding:2rem 1rem 4rem}}
.banner{{background:#1c241c;color:#f6f1e6;padding:1rem 1.25rem;border-radius:4px}}
.score{{font-size:2rem;font-weight:700}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:.75rem;margin:1rem 0}}
.card{{background:rgba(255,255,255,.55);border:1px solid #cbbfa8;padding:.9rem}}
pre{{background:#1c241c;color:#eef3ea;padding:1rem;overflow:auto}}
.row{{font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre}}
@media(max-width:900px){{.cards{{grid-template-columns:1fr 1fr}}}}
</style></head><body><main>
<div class="banner"><div>{status} — NOT DEPLOYED</div>
<div class="score">{score} · {grade} · {action}</div></div>
<section class="cards">
<div class="card"><h3>Score</h3><div>{score}</div></div>
<div class="card"><h3>Grade</h3><div>{grade}</div></div>
<div class="card"><h3>Action</h3><div>{action}</div></div>
<div class="card"><h3>Predictions</h3><div>Unchanged</div></div>
</section>
{''.join(body)}
</main></body></html>"""


def write_dashboard(output_dir: Path, **kwargs: Any) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md = build_dashboard_md(**kwargs)
    html = build_dashboard_html(
        md, status=kwargs["status"], daily=kwargs["daily"], decision=kwargs["decision"]
    )
    md_p = output_dir / "owner_portfolio_dashboard.md"
    html_p = output_dir / "owner_portfolio_dashboard.html"
    md_p.write_text(md, encoding="utf-8")
    html_p.write_text(html, encoding="utf-8")
    return {
        "owner_portfolio_dashboard.md": str(md_p),
        "owner_portfolio_dashboard.html": str(html_p),
    }
