"""Daily / weekly / monthly owner reports for two-fixture shadow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.two_fixture_forward_shadow.constants import (
    PRIMARY_SELECTION_GATE,
    STRATEGY_VERSION,
)
from worldcup_predictor.research.two_fixture_forward_shadow.observability import build_status

ROOT = Path(__file__).resolve().parents[3]


def _ensure_dirs() -> dict[str, Path]:
    base = ROOT / "reports" / "owner" / "portfolio"
    paths = {
        "daily": base / "daily",
        "weekly": base / "weekly",
        "monthly": base / "monthly",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def write_daily_report(
    conn,
    report_date: str,
    *,
    freezes: list[dict[str, Any]],
    pair: dict[str, Any] | None,
    evaluations: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    paths = _ensure_dirs()
    evals = {e["portfolio_id"]: e for e in (evaluations or [])}
    # pick primary benchmark freeze for display
    primary = None
    for f in freezes:
        if (
            f.get("stake_strategy") == "EQUAL_GROSS_RETURN"
            and f.get("bookmaker_mode") == "SINGLE_BOOKMAKER_EXECUTABLE"
        ):
            primary = f
            break
    if not primary and freezes:
        primary = freezes[0]

    tickets = json.loads(primary["primary_tickets_json"]) if primary else []
    hedges = json.loads(primary["hedge_tickets_json"]) if primary else []
    ev = evals.get(primary["portfolio_id"]) if primary else None

    en = f"""# TWO-FIXTURE SHADOW — {report_date}

**Strategy version:** `{STRATEGY_VERSION}`  
**Selection gate:** `{PRIMARY_SELECTION_GATE}` (train-locked)  
**Stakes:** HYPOTHETICAL — no real bets  

## Selected pair

"""
    if pair:
        en += f"""- Fixture A: `{pair.get('fixture_a')}` ({pair.get('league_a')})
- Fixture B: `{pair.get('fixture_b')}` ({pair.get('league_b')})
- Joint Top5 est: {pair.get('joint_top5_est')}
- Odds completeness: {pair.get('odds_completeness')}
- Selection: {pair.get('selection_strategy')} @ {pair.get('selection_timestamp_utc')}
"""
    else:
        en += "_No eligible pair today._\n"

    en += "\n## Primary 25 (EQUAL_GROSS_RETURN / SINGLE_BOOKMAKER)\n\n"
    if tickets:
        en += "| Ticket | Scores | Combo odds | Stake | Gross if win | Net if win |\n|---|---|---:|---:|---:|---:|\n"
        for t in tickets:
            en += (
                f"| {t.get('ticket_id')} | {t.get('score_a')}×{t.get('score_b')} | "
                f"{t.get('combo_odds')} | {t.get('stake')} | {t.get('gross_return_if_win')} | "
                f"{t.get('net_portfolio_if_win')} |\n"
            )
    else:
        en += "_No freeze._\n"

    en += "\n## Hedges (max 5)\n\n"
    for h in hedges:
        en += (
            f"- `{h.get('selection')}` ({h.get('kind')}) odds={h.get('decimal_odds')} "
            f"stake={h.get('stake')} class={h.get('hedge_classification')} "
            f"scenario={h.get('failure_scenario')}\n"
        )
    if not hedges:
        en += "_None._\n"

    if primary:
        en += f"""
## Portfolio summary

- Portfolio ID: `{primary.get('portfolio_id')}`
- Snapshot window: {primary.get('snapshot_window')}
- Bookmaker mode: {primary.get('bookmaker_mode')}
- Total stake (hypothetical): €{primary.get('total_stake')}
- Expected joint coverage: {primary.get('expected_joint_coverage')}
- Hedge-enhanced coverage: {primary.get('hedge_enhanced_coverage')}
- Worst-case loss: €{primary.get('worst_case_loss')}
- Full-loss prob est: {primary.get('full_loss_prob_est')}
- Min covered return: {primary.get('min_covered_return')}
- Cohort: {primary.get('cohort')}
- Freeze hash: `{primary.get('freeze_hash')}`
"""

    en += "\n## After completion\n\n"
    if ev:
        en += f"""- Actual: {ev.get('actual_score_a')} / {ev.get('actual_score_b')}
- Status: **{ev.get('result_status')}**
- Winning ticket: {ev.get('winning_ticket_id')}
- Gross: {ev.get('gross_return')}
- Net: {ev.get('net_return')}
- ROI: {ev.get('roi')}
- Full loss: {ev.get('full_loss')}
"""
    else:
        en += "_RESULT_PENDING_\n"

    en += f"\nFreezes today: {len(freezes)} (parallel strategies × bookmaker modes)\n"
    en_path = paths["daily"] / f"{report_date}_TWO_FIXTURE_SHADOW.md"
    en_path.write_text(en, encoding="utf-8")

    fa = f"""# سایه پکیج دو بازی — {report_date}

نسخه استراتژی: `{STRATEGY_VERSION}`  
شرط‌ها فرضی هستند — بدون شرط واقعی.

جفت انتخاب‌شده: {pair.get('fixture_a') if pair else '—'} / {pair.get('fixture_b') if pair else '—'}  
وضعیت نتیجه: {(ev or {}).get('result_status', 'RESULT_PENDING')}  
ROI: {(ev or {}).get('roi')}

جزئیات کامل در گزارش انگلیسی همان روز.
"""
    fa_path = paths["daily"] / f"{report_date}_TWO_FIXTURE_SHADOW_FA.md"
    fa_path.write_text(fa, encoding="utf-8")
    return {"en": str(en_path), "fa": str(fa_path)}


def write_weekly_monthly(conn) -> dict[str, str]:
    paths = _ensure_dirs()
    status = build_status(conn)
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    month_key = now.strftime("%Y-%m")

    rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT f.*, e.result_status, e.roi, e.net_return, e.primary_hit, e.full_loss, e.recovery_class
            FROM tfps_portfolio_freezes f
            LEFT JOIN tfps_portfolio_evaluations e ON e.portfolio_id=f.portfolio_id
            ORDER BY f.frozen_at_utc DESC
            LIMIT 5000
            """
        ).fetchall()
    ]

    def aggregate(title: str, key: str, path: Path) -> str:
        completed = [r for r in rows if r.get("result_status") not in (None, "RESULT_PENDING", "RESULT_UNAVAILABLE", "PORTFOLIO_INVALID")]
        primary_wins = sum(1 for r in completed if r.get("result_status") == "PRIMARY_WIN")
        full_losses = sum(1 for r in completed if int(r.get("full_loss") or 0) == 1)
        stake = sum(float(r.get("total_stake") or 0) for r in completed)
        net = sum(float(r.get("net_return") or 0) for r in completed if r.get("net_return") is not None)
        roi = (net / stake) if stake else None
        body = f"""# {title}

**Generated:** {now.strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Strategy version:** `{STRATEGY_VERSION}`

## Cumulative sample (portfolio unit)

| Metric | Value |
|---|---|
| Frozen portfolios | {status['frozen_portfolios']} |
| Completed evaluated | {status['completed_portfolios']} |
| Pending | {status['pending_portfolios']} |
| To 100 milestone | {status['portfolios_to_100']} |
| To 500 milestone | {status['portfolios_to_500']} |
| To 1000 milestone | {status['portfolios_to_1000']} |
| Active cohort | {status['cohort_active']} |

## Completed slice (all strategies in DB)

| Metric | Value |
|---|---|
| Completed rows | {len(completed)} |
| Primary wins | {primary_wins} |
| Full losses | {full_losses} |
| Hypothetical stake | {stake} |
| Net | {net} |
| ROI | {roi} |
| Equal Gross avg ROI | {status.get('equal_gross_return_avg_roi')} |
| Minimax avg ROI | {status.get('minimax_avg_roi')} |
| Same-bookmaker freezes | {status['same_bookmaker_freezes']} |
| Cross-bookmaker theoretical | {status['cross_bookmaker_theoretical_freezes']} |

## Rules

- No automatic betting
- ROI streams for SINGLE vs CROSS never merged
- Cohort A locked for first 100 completed portfolios
- Unit of sample = executable two-fixture portfolio (not odds line count)

Health: `{status['health']}`  
Timer enabled: `{status['timer_enabled']}`
"""
        path.write_text(body, encoding="utf-8")
        return str(path)

    week_path = paths["weekly"] / f"{week_key}_TWO_FIXTURE_PORTFOLIO.md"
    month_path = paths["monthly"] / f"{month_key}_TWO_FIXTURE_PORTFOLIO.md"
    return {
        "weekly": aggregate(f"TWO-FIXTURE PORTFOLIO WEEKLY {week_key}", week_key, week_path),
        "monthly": aggregate(f"TWO-FIXTURE PORTFOLIO MONTHLY {month_key}", month_key, month_path),
    }
