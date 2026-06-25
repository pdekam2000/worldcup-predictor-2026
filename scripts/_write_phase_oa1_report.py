#!/usr/bin/env python3
"""Write PHASE_OA1_ODDALERTS_PROVIDER_AUDIT_REPORT.md"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_OA1_ODDALERTS_PROVIDER_AUDIT_REPORT.md"


def _pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{100 * float(v):.1f}%"


def write_report(
    *,
    connectivity: dict[str, Any],
    coverage: dict[str, Any],
    books: dict[str, Any],
    fg: dict[str, Any],
    markets: dict[str, Any],
    cs: dict[str, Any],
    depth: dict[str, Any],
    decision: dict[str, Any],
) -> Path:
    ranking = decision.get("provider_ranking") or []
    fg_strats = fg.get("strategies") or {}
    leagues = coverage.get("leagues") or {}

    lines = [
        "# PHASE OA-1 — OddAlerts Provider Trial Audit",
        "",
        "**Mode:** Audit only  ",
        "**Production deploy:** NO  ",
        "**EGIE / prediction engine:** UNCHANGED  ",
        "",
        "---",
        "",
        "## Executive Answer",
        "",
        f"**Is OddAlerts useful?** **{'Yes — conditionally' if decision.get('is_oddalerts_useful') else 'Limited today'}** "
        f"for probability model + multi-book odds history. Not a Sportmonks FG replacement on measured evidence.",
        "",
        f"**Worth monthly pay?** {decision.get('worth_monthly_pay')}",
        "",
        f"**Recommended architecture:** {decision.get('recommended_architecture')}",
        "",
        "### Nine decision questions",
        "",
        "1. **Useful?** Yes for odds history + probability on single-fixture includes; bulk fixtures list blocked.",
        "2. **Better than Sportmonks for betting intelligence?** **No for FG Team** — Sportmonks sharp MW 78.7% (K2); OA FG accuracy **not measured** (0 finished fixtures in pool).",
        "3. **Improves FG Team?** **Not proven** — no FTS market in history sample; no finished FG evaluable rows.",
        "4. **Improves BTTS?** **Not proven** — probability available but outcome accuracy not measurable on upcoming-only pool.",
        "5. **Improves O/U?** **Not proven** — same limitation.",
        "6. **Improves Match Winner?** **Promising signals** — consensus/closing/sharp derivable from odds history; accuracy not measured.",
        "7. **Monthly pay justified?** Conditional on unlocking bulk historical fixture access.",
        "8. **Provider ranking:** see below.",
        "9. **Architecture:** API-Football spine + Sportmonks UEFA odds + OddAlerts optional shadow.",
        "",
        "---",
        "",
        "## STEP 1 — Connectivity",
        "",
        f"Artifact: `artifacts/oddalerts_connectivity_test.json`",
        "",
        f"- **Configured:** {connectivity.get('configured')}",
        f"- **Pass / Fail:** {connectivity.get('pass_count')} / {connectivity.get('fail_count')}",
        f"- Raw samples: `artifacts/oddalerts_raw/`",
        "",
        "| Endpoint | OK | Notes |",
        "|----------|-----|-------|",
    ]

    for name, ep in (connectivity.get("endpoints") or {}).items():
        lines.append(f"| {name} | {ep.get('ok')} | {ep.get('error') or ep.get('row_count', '')} |")

    lines.extend(["", "## STEP 2 — League Coverage", ""])
    for league, row in leagues.items():
        lines.append(
            f"- **{league}** (id {row.get('competition_id')}): fixtures_seen={row.get('fixtures_seen')}, "
            f"odds={row.get('odds')}, probability={row.get('probability')}, "
            f"opening/closing/peak={row.get('opening_odds')}"
        )

    lines.extend(["", "## STEP 3 — Sharp Book Audit", ""])
    lines.append(f"- History rows (sample fixture): **{books.get('history_row_count')}**")
    lines.append(f"- FTS market present: **{books.get('first_team_to_score_market_present')}**")
    lines.append(f"- Markets: {', '.join(books.get('history_markets') or [])[:200]}")
    for row in books.get("focus_bookmakers") or []:
        lines.append(
            f"- **{row.get('bookmaker')}** listed={row.get('listed_in_api')} "
            f"history_rows={row.get('history_rows_sample_fixture')}"
        )

    lines.extend(["", "## STEP 4 — First Goal Signal Test", ""])
    lines.append(f"- Fixtures scanned: **{fg.get('fixtures_scanned')}**")
    lines.append(f"- Evaluable finished: **{fg.get('evaluable_finished_fixtures')}**")
    lines.append(f"- Limitation: {fg.get('limitation')}")
    for name, st in fg_strats.items():
        lines.append(
            f"- **{name}**: accuracy {_pct(st.get('fg_accuracy'))}, "
            f"coverage={st.get('coverage')}, pending_rate={_pct(st.get('pending_rate'))}"
        )
    k2 = fg.get("k2_sportmonks_reference") or {}
    lines.append(
        f"\nK2 reference (Sportmonks UEFA): sharp MW {_pct(k2.get('sharp_mw_fg_accuracy'))} "
        f"(n={k2.get('evaluable_fixtures')})"
    )

    lines.extend(["", "## STEP 5 — BTTS / O-U Audit", ""])
    btts = markets.get("btts") or {}
    ou = markets.get("over_under_25") or {}
    lines.append(f"- BTTS probability rows: {btts.get('rows_with_probability')} | measurable accuracy: {btts.get('accuracy_measurable')}")
    lines.append(f"- O/U 2.5 probability rows: {ou.get('rows_with_probability')} | measurable accuracy: {ou.get('accuracy_measurable')}")
    lines.append(f"- EGIE LGBM baselines (ML-1): BTTS {btts.get('egie_lgbm_test_baseline')}, O/U {ou.get('egie_lgbm_test_baseline')}")

    lines.extend(["", "## STEP 6 — Correct Score Audit", ""])
    lines.append(f"- Correct score market in history: **{cs.get('correct_score_market_in_odds_history')}**")
    lines.append(f"- Useful for exact score engine: **{cs.get('useful_for_exact_score_engine')}**")
    lines.append(f"- Useful for goal timing: **{cs.get('useful_for_goal_timing_engine')}**")
    lines.append(f"- xG proxy fields: {cs.get('expected_goals_proxy_from_probability')}")

    lines.extend(["", "## STEP 7 — Historical Depth", ""])
    lines.append(f"- Competitions paginated: {depth.get('competitions_paginated')}")
    lines.append(f"- Odds history window: {depth.get('odds_history_window_documented')}")
    lines.append(f"- Fixtures list endpoint: {depth.get('fixtures_list_endpoint')}")
    lines.append(f"- Value/past endpoint: {depth.get('value_past_endpoint')}")

    lines.extend(["", "## STEP 8 — Provider Ranking", ""])
    for row in ranking:
        lines.append(f"- **{row.get('provider')}** (score {row.get('score')}): {row.get('role')} — {row.get('fg_team_evidence')}")

    lines.extend(["", "## Strengths / Gaps", ""])
    for s in decision.get("strengths") or []:
        lines.append(f"- Strength: {s}")
    for g in decision.get("gaps") or []:
        lines.append(f"- Gap: {g}")

    lines.extend(
        [
            "",
            "---",
            "",
            "**STOP — Audit only. No deploy. No production changes.**",
        ]
    )

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT
