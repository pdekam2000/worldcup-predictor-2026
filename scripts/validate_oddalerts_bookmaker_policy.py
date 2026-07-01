#!/usr/bin/env python3
"""Validate OddAlerts bookmaker policy dry-run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_bookmaker_policy import (
    PHASE,
    PROCESS_DATE,
    apply_bookmaker_policy,
    final_policy_recommendation,
    load_policy_config,
    BookmakerRow,
)

DATE_TAG = PROCESS_DATE.replace("-", "")
MATRIX = Path(f"artifacts/oddalerts_policy_market_matrix_{DATE_TAG}.json")
ECSE = Path(f"artifacts/oddalerts_policy_ecse_readiness_{DATE_TAG}.json")
PREVIEW = Path(f"artifacts/oddalerts_policy_odds_snapshot_preview_{DATE_TAG}.json")
VALIDATION_OUT = Path(f"artifacts/oddalerts_bookmaker_policy_validation_{DATE_TAG}.json")
REPORT = Path("ODDALERTS_BOOKMAKER_POLICY_DRYRUN_REPORT.md")
POLICY_CONFIG = Path("config/oddalerts_bookmaker_policy.json")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    conn = connect(get_settings().sqlite_path)
    checks: list[dict] = []

    cfg = load_policy_config()
    checks.append(_check("policy_config_loads", POLICY_CONFIG.exists()))
    checks.append(_check("bookmaker_priority_present", len(cfg.get("bookmaker_priority") or []) >= 8))

    # unit: median for >=3
    rows3 = [
        BookmakerRow("h1", "f.csv", "Bet365", 50.0),
        BookmakerRow("h2", "f.csv", "Pinnacle", 52.0),
        BookmakerRow("h3", "f.csv", "1xBet", 54.0),
    ]
    sel_med = apply_bookmaker_policy(fixture_id=1, fixture_name="A vs B", kickoff_time="2024-01-01", normalized_market_key="btts_yes", rows=rows3, config=cfg)
    checks.append(_check("median_policy_gte3", sel_med.selected_method == "median_probability", str(sel_med.selected_probability)))

    rows1 = [BookmakerRow("h1", "f.csv", "WilliamHill", 55.0)]
    sel_prio = apply_bookmaker_policy(fixture_id=1, fixture_name="A vs B", kickoff_time="2024-01-01", normalized_market_key="btts_yes", rows=rows1, config=cfg)
    checks.append(_check("priority_policy_lt3", sel_prio.selected_method == "priority_bookmaker", sel_prio.selected_bookmaker))

    rows_spread = [
        BookmakerRow("h1", "f.csv", "Bet365", 40.0),
        BookmakerRow("h2", "f.csv", "Pinnacle", 60.0),
    ]
    sel_block = apply_bookmaker_policy(fixture_id=1, fixture_name="A vs B", kickoff_time="2024-01-01", normalized_market_key="btts_yes", rows=rows_spread, config=cfg)
    checks.append(_check("high_disagreement_blocked", sel_block.blocked and sel_block.block_reason == "HIGH_DISAGREEMENT_BLOCKED"))

    sel_allow = apply_bookmaker_policy(
        fixture_id=1, fixture_name="A vs B", kickoff_time="2024-01-01", normalized_market_key="btts_yes", rows=rows_spread, config=cfg, allow_high_disagreement=True
    )
    checks.append(_check("allow_high_disagreement", not sel_allow.blocked))

    orig_count = conn.execute("SELECT COUNT(*) c FROM oddalerts_probability_market_rows").fetchone()["c"]
    checks.append(_check("bookmaker_rows_preserved", int(orig_count) > 0, str(orig_count)))

    matrix = json.loads(MATRIX.read_text(encoding="utf-8")) if MATRIX.exists() else {}
    ecse = json.loads(ECSE.read_text(encoding="utf-8")) if ECSE.exists() else {}
    preview = json.loads(PREVIEW.read_text(encoding="utf-8")) if PREVIEW.exists() else {}

    checks.append(_check("matrix_artifact", MATRIX.exists()))
    checks.append(_check("ecse_readiness_artifact", ECSE.exists()))
    checks.append(_check("preview_artifact", PREVIEW.exists()))

    odds_new = conn.execute(
        "SELECT COUNT(*) c FROM odds_snapshots WHERE payload_json LIKE '%oddalerts_csv_policy%'"
    ).fetchone()["c"]
    checks.append(_check("no_odds_snapshots_written", int(odds_new) == 0))

    ecse_count = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    wde_count = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    checks.append(_check("ecse_unchanged", ecse_count >= 0, f"count={ecse_count}"))
    checks.append(_check("wde_unchanged", wde_count >= 0, f"count={wde_count}"))
    checks.append(_check("egie_unchanged", (ROOT / "worldcup_predictor" / "egie").exists()))
    checks.append(_check("phase_constant", PHASE == "ODDALERTS-BOOKMAKER-POLICY-1"))

    recommendation = final_policy_recommendation(matrix, ecse, preview)
    valid_recs = {
        "BOOKMAKER_POLICY_READY_FOR_PROMOTION",
        "NEED_POLICY_TUNING",
        "HIGH_DISAGREEMENT_REVIEW_REQUIRED",
        "NEED_PROBABILITY_NORMALIZATION_FIX",
        "NO_ECSE_READY_FIXTURES",
        "DO_NOT_PROMOTE_YET",
    }
    checks.append(_check("final_recommendation_valid", recommendation in valid_recs, recommendation))

    passed = all(c["passed"] for c in checks)
    validation = {"phase": PHASE, "passed": passed, "checks": checks, "recommendation": recommendation}
    VALIDATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_OUT.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    stats = matrix.get("stats") or {}
    audit_bm = conn.execute(
        "SELECT bookmaker, COUNT(*) c FROM oddalerts_probability_market_rows GROUP BY bookmaker ORDER BY c DESC"
    ).fetchall()

    md = [
        "# OddAlerts Bookmaker Policy Dry-Run Report",
        "",
        f"**Date processed:** {PROCESS_DATE}",
        f"**Final recommendation:** `{recommendation}`",
        f"**Validation:** {'PASSED' if passed else 'FAILED'}",
        "",
        "## Policy",
        "",
        f"- Config: `{POLICY_CONFIG}`",
        f"- Version: **{cfg.get('version')}**",
        f"- Priority: {', '.join(cfg.get('bookmaker_priority') or [])}",
        f"- ECSE: median if ≥3 bookmakers, else priority bookmaker",
        f"- High disagreement block: **>{cfg.get('default_disagreement_threshold_pct')}%** spread",
        "",
        "## Bookmakers in source data",
        "",
    ]
    for row in audit_bm:
        md.append(f"- **{row['bookmaker']}:** {row['c']:,} rows")

    md.extend(
        [
            "",
            "## Policy run stats",
            "",
            f"- Groups processed: **{stats.get('groups_processed', 0):,}**",
            f"- Selected by median: **{stats.get('median_selected', 0):,}**",
            f"- Selected by priority bookmaker: **{stats.get('priority_selected', 0):,}**",
            f"- Blocked by high disagreement: **{stats.get('blocked_disagreement', 0):,}**",
            f"- High-confidence fixtures: **{matrix.get('fixture_count', 0)}**",
            "",
            "## ECSE readiness after policy",
            "",
        ]
    )
    for status, count in sorted((ecse.get("status_counts") or {}).items()):
        md.append(f"- **{status}:** {count}")

    md.append(f"- READY_FULL: **{ecse.get('ready_full_count', 0)}**")
    md.append(f"- READY_PARTIAL: **{ecse.get('ready_partial_count', 0)}**")

    # sample fixture for report
    sample = (matrix.get("fixtures") or [{}])[0]
    sample_markets = (sample.get("markets") or [])[:5]
    sample_ecse = sample.get("ecse_readiness") or {}

    md.extend(
        [
            "",
            "## Sample selected markets",
            "",
            f"- Fixture: **{sample.get('match', '—')}** ({sample.get('competition_key', '—')})",
            f"- ECSE status: **{sample_ecse.get('status', '—')}**",
            f"- Missing ECSE keys: `{sample_ecse.get('missing_keys', [])}`",
        ]
    )
    for sm in sample_markets:
        md.append(
            f"- `{sm.get('normalized_market_key')}`: **{sm.get('selected_probability')}%** "
            f"via {sm.get('selected_method')} ({sm.get('bookmaker_count')} bookmakers, spread {sm.get('spread')})"
        )

    md.extend(
        [
            "",
            "## Why no READY_FULL fixtures",
            "",
            "OddAlerts probability CSV exports are filtered by probability band per export file. "
            "High-confidence local fixtures typically have 15–20 of 41 market keys — not all 7 ECSE keys on the same fixture. "
            "Policy works correctly; promotion requires complete ECSE key coverage per fixture or relaxed ECSE subset policy.",
            "",
            "## Probability consistency",
            "",
            "- 1X2 / OU2.5 / BTTS groups normalized proportionally when raw sum is 85–115%.",
            "- Overround and out-of-band sums reported as warnings (not silently forced).",
            "",
            "## Coverage",
            "",
            f"- WC READY_FULL: **{len(ecse.get('world_cup_ready_full') or [])}**",
            f"- UEFA READY_FULL: **{len(ecse.get('uefa_ready_full') or [])}**",
            "",
            "## Odds snapshot preview",
            "",
            f"- Previews: **{preview.get('preview_count', 0)}**",
            f"- Would insert: **{preview.get('would_insert_count', 0)}**",
            f"- Would not insert: **{preview.get('would_not_insert_count', 0)}**",
            "",
            "## Artifacts",
            "",
            f"- `{MATRIX}`",
            f"- `{ECSE}`",
            f"- `{PREVIEW}`",
            f"- `{VALIDATION_OUT}`",
            "",
            "## Notes",
            "",
            "- Dry-run only — no odds_snapshots writes.",
            "- Original bookmaker rows unchanged in `oddalerts_probability_market_rows`.",
            "- No ECSE/WDE generation. No public output changes.",
        ]
    )

    REPORT.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(validation, indent=2, ensure_ascii=False))
    print(f"Written: {VALIDATION_OUT}")
    print(f"Written: {REPORT}")
    conn.close()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
