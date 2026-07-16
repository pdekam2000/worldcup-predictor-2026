#!/usr/bin/env python3
"""Correct Score prematch odds ingestion — cache-first extraction + forward plan (no betting)."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.research.correct_score_odds.completeness import fixture_completeness
from worldcup_predictor.research.correct_score_odds.forward_collector import (
    build_forward_plan,
    plan_to_dict,
)
from worldcup_predictor.research.correct_score_odds.ingest import ingest_from_odds_snapshots
from worldcup_predictor.research.correct_score_odds.mapping import provider_capability_matrix
from worldcup_predictor.research.correct_score_odds.manual_import import preview_manual_rows
from worldcup_predictor.research.correct_score_odds.statuses import FINAL_PHASE_STATUSES

ART = ROOT / "artifacts" / "correct_score_odds"
REPORTS = ROOT / "reports" / "owner"


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_schema_compat(conn)

    matrix = provider_capability_matrix()
    (ART / "provider_capability_matrix.json").write_text(
        json.dumps(matrix, indent=2), encoding="utf-8"
    )

    existing = int(
        conn.execute("SELECT COUNT(1) FROM correct_score_odds_lines").fetchone()[0]
    )
    if existing >= 1000:
        print(f"CS lines already present ({existing}); skipping re-scan, exporting artifacts...", flush=True)
        extract = {
            "ingestion_run_id": "reuse_existing",
            "mode": "cache_snapshots",
            "snapshots_scanned": 0,
            "fixtures_scanned": int(
                conn.execute("SELECT COUNT(DISTINCT fixture_id) FROM correct_score_odds_lines").fetchone()[0]
            ),
            "lines_inserted": 0,
            "lines_deduped": 0,
            "lines_rejected": 0,
            "accepted_parsed": existing,
            "rejected_samples": [],
            "status": "ok_reused",
            "api_calls": 0,
            "prediction_jobs_created": 0,
            "freezes_modified": 0,
        }
    else:
        print("Ingesting CS odds from odds_snapshots (cache-first, 0 API calls)...", flush=True)
        extract = ingest_from_odds_snapshots(conn)
        print(
            f"inserted={extract['lines_inserted']} deduped={extract['lines_deduped']} "
            f"rejected={extract['lines_rejected']} fixtures={extract['fixtures_scanned']}",
            flush=True,
        )
    (ART / "raw_ingestion_manifest.json").write_text(json.dumps(extract, indent=2), encoding="utf-8")

    # parsed odds export (cap)
    parsed = [
        dict(r)
        for r in conn.execute(
            """
            SELECT fixture_id, bookmaker_name, market, selection, home_goals, away_goals,
                   decimal_odds, fetched_at_utc, kickoff_utc, prematch_status, settlement_scope,
                   provider, odds_kind, is_complete_market, ingestion_run_id, source_hash
            FROM correct_score_odds_lines
            WHERE prematch_status = 'prematch'
            ORDER BY fixture_id, bookmaker_name, selection
            LIMIT 200000
            """
        ).fetchall()
    ]
    write_csv(ART / "parsed_odds.csv", parsed)

    rejected = extract.get("rejected_samples") or []
    write_csv(ART / "rejected_rows.csv", rejected)

    # fixtures with CS
    fixtures = [
        int(r[0])
        for r in conn.execute(
            "SELECT DISTINCT fixture_id FROM correct_score_odds_lines WHERE prematch_status='prematch'"
        ).fetchall()
    ]
    completeness_rows = []
    bookmaker_rows = []
    freshness_rows = []
    for fid in fixtures[:2000]:
        completeness_rows.append(fixture_completeness(conn, fid))
        for r in conn.execute(
            """
            SELECT bookmaker_name, COUNT(*) AS n_scores,
                   MIN(decimal_odds) AS min_odd, MAX(decimal_odds) AS max_odd,
                   MAX(fetched_at_utc) AS last_fetched
            FROM correct_score_odds_lines
            WHERE fixture_id=? AND market='CORRECT_SCORE_90_MINUTES' AND prematch_status='prematch'
            GROUP BY bookmaker_name
            """,
            (fid,),
        ):
            bookmaker_rows.append({"fixture_id": fid, **dict(r)})
        for r in conn.execute(
            """
            SELECT fixture_id, MAX(fetched_at_utc) AS last_fetched,
                   AVG(odds_age_seconds) AS avg_age_seconds,
                   SUM(CASE WHEN is_fresh=1 THEN 1 ELSE 0 END) AS fresh_lines,
                   COUNT(*) AS n_lines
            FROM correct_score_odds_lines
            WHERE fixture_id=? AND prematch_status='prematch'
            """,
            (fid,),
        ):
            freshness_rows.append(dict(r))

    write_csv(ART / "fixture_market_completeness.csv", completeness_rows)
    write_csv(ART / "bookmaker_coverage.csv", bookmaker_rows)
    write_csv(ART / "odds_freshness.csv", freshness_rows)

    # Historical status: we have cached snapshot extraction, not provider historical archive
    hist_status = {
        "historical_provider_archive": False,
        "local_cached_snapshot_extraction": True,
        "fixtures_with_prematch_cs": len(fixtures),
        "lines_prematch": len(parsed),
        "checkpoint": extract.get("ingestion_run_id"),
        "resume_safe": True,
        "overwrites_snapshots": False,
        "note": (
            "Legitimate CS odds extracted from existing append-only odds_snapshots. "
            "OddAlerts/CSV historical CS unavailable. Provider historical CS archive not claimed."
        ),
    }
    (ART / "historical_collection_status.json").write_text(
        json.dumps(hist_status, indent=2), encoding="utf-8"
    )

    # Forward plan for upcoming fixtures
    now = datetime.now(timezone.utc)
    upcoming = []
    try:
        for r in conn.execute(
            """
            SELECT fixture_id, kickoff_utc, home_team, away_team, competition_key
            FROM fixtures
            WHERE kickoff_utc IS NOT NULL
              AND kickoff_utc > ?
            ORDER BY kickoff_utc ASC
            LIMIT 200
            """,
            (now.strftime("%Y-%m-%dT%H:%M:%SZ"),),
        ):
            upcoming.append(dict(r))
    except Exception:
        pass
    plan = build_forward_plan(conn, upcoming)
    plan_dump = plan_to_dict(conn)
    forward_doc = {
        **plan,
        "plan_summary": plan_dump,
        "upcoming_fixtures_planned": len(upcoming),
        "collection_schedule": ["first_available", "h24", "h6", "h1", "final_prematch"],
        "never_after_kickoff": True,
        "min_portfolios_target": 100,
        "preferred_portfolios_target": 500,
    }
    (ART / "forward_collection_plan.json").write_text(
        json.dumps(forward_doc, indent=2, default=str), encoding="utf-8"
    )

    # Manual import design sample (not persisted)
    manual_design = preview_manual_rows(
        fixture_id=0,
        home_team="HOME",
        away_team="AWAY",
        bookmaker_name="EXAMPLE_BOOK",
        capture_timestamp_utc=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        settlement_scope="90_MINUTES",
        rows=[{"selection": "1-0", "decimal_odds": 7.5}, {"selection": "2-1", "decimal_odds": 9.0}],
    )
    (ART / "manual_import_design.json").write_text(
        json.dumps(
            {
                "design": manual_design,
                "rules": [
                    "manual odds clearly labelled",
                    "no OCR-only silent acceptance",
                    "owner must confirm parsed values",
                    "fixture and home/away mapping shown before save",
                    "settlement scope confirmed 90_MINUTES",
                    "never presented as API-fetched",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    providers_yes = [p for p in matrix if p.get("correct_score_available") in {"yes", "yes_with_confirmation"}]
    n_fix = len(fixtures)
    n_lines = int(
        conn.execute(
            "SELECT COUNT(1) FROM correct_score_odds_lines WHERE prematch_status='prematch'"
        ).fetchone()[0]
    )

    if n_fix >= 50 and n_lines >= 1000:
        # ingestion complete from cache; ROI still needs portfolio re-run / more forward if sparse
        final_status = "CORRECT_SCORE_ODDS_INGESTION_COMPLETE"
        if n_fix < 100:
            final_status = "CORRECT_SCORE_ODDS_FORWARD_COLLECTION_ACTIVE"
    elif providers_yes and n_fix == 0:
        final_status = "CORRECT_SCORE_ODDS_FORWARD_COLLECTION_ACTIVE"
    elif not providers_yes:
        final_status = "CORRECT_SCORE_ODDS_PROVIDER_NOT_AVAILABLE"
    else:
        final_status = "CORRECT_SCORE_ODDS_FORWARD_COLLECTION_ACTIVE"

    summary = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "final_status": final_status,
        "fixtures_with_cs": n_fix,
        "prematch_lines": n_lines,
        "api_calls": 0,
        "providers_with_cs": [p["provider"] for p in providers_yes],
        "canonical_market": "CORRECT_SCORE_90_MINUTES",
        "deploy_betting": False,
        "auto_bet": False,
        "ecse_changed": False,
        "wde_changed": False,
        "freezes_modified": False,
        "valid_final_statuses": sorted(FINAL_PHASE_STATUSES),
    }
    (ART / "ingestion_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    _write_audit_and_reports(matrix, extract, hist_status, forward_doc, summary, completeness_rows)
    print(json.dumps({"final_status": final_status, "fixtures_with_cs": n_fix, "lines": n_lines}, indent=2))
    return 0


def _write_audit_and_reports(
    matrix: list[dict],
    extract: dict,
    hist: dict,
    forward: dict,
    summary: dict,
    completeness: list[dict],
) -> None:
    avg_scores = (
        sum(c.get("n_exact_scores_quoted_best") or 0 for c in completeness) / len(completeness)
        if completeness
        else 0
    )
    audit = f"""# CORRECT SCORE ODDS — PROVIDER CAPABILITY AUDIT

**Generated:** {summary["generated_at"]}  
**Phase status (ingestion):** `{summary["final_status"]}`

## Providers

| Provider | CS available | Prematch | Historical | Bookmaker-level | Preferred rank |
|---|---|---|---|---|---|
"""
    for p in sorted(matrix, key=lambda x: x.get("preferred_order_rank", 99)):
        audit += (
            f"| {p['provider']} | {p['correct_score_available']} | {p['prematch_available']} | "
            f"{p['historical_available']} | {p['bookmaker_level']} | {p.get('preferred_order_rank')} |\n"
        )
    audit += f"""

## Preferred ingestion order

1. **api_football** — Correct Score in bookmaker bets (confirmed)
2. **sportmonks** — Correct Score when premium odds include available
3. **manual_owner_import** — confirmed transcription only
4. OddAlerts / The Odds API / CSV — **not used for CS** (unsupported)

## Canonical market

- Market: `CORRECT_SCORE_90_MINUTES`
- Selection: `home_goals-away_goals` (e.g. `1-0`)
- Separate: `ANY_OTHER_HOME_WIN` / `ANY_OTHER_DRAW` / `ANY_OTHER_AWAY_WIN`
- Reject: 1st/2nd half, AET, penalties, combo result+score markets

## Cache-first extraction result

- Snapshots scanned: {extract.get("snapshots_scanned")}
- Fixtures scanned: {extract.get("fixtures_scanned")}
- Lines inserted: {extract.get("lines_inserted")}
- Deduped: {extract.get("lines_deduped")}
- Rejected: {extract.get("lines_rejected")}
- API calls: **0** (this run)

## Historical

{hist.get("note")}

Fixtures with prematch CS locally: **{hist.get("fixtures_with_prematch_cs")}**

## Forward collection

Planned rows: {forward.get("planned_rows")}  
Upcoming fixtures: {forward.get("upcoming_fixtures_planned")}  
Stops at kickoff: **yes**  
Target portfolios: {forward.get("min_portfolios_target")}–{forward.get("preferred_portfolios_target")}

## Completeness (sample)

Average exact scores quoted (best odds map): **{avg_scores:.1f}**

## Constraints

- No fabricated odds
- No synthetic-as-real
- No freeze/ECSE/WDE changes
- No automatic betting
"""
    (REPORTS / "CORRECT_SCORE_ODDS_PROVIDER_CAPABILITY_AUDIT.md").write_text(audit, encoding="utf-8")

    en = f"""# CORRECT SCORE ODDS INGESTION REPORT

**Final status:** `{summary["final_status"]}`  
**Generated:** {summary["generated_at"]}

## Summary

Legitimate prematch Correct Score odds were extracted from existing `odds_snapshots` payloads (API-Football / SportMonks shaped bookmaker bets) into additive table `correct_score_odds_lines`.

| Metric | Value |
|---|---|
| Fixtures with CS | {summary["fixtures_with_cs"]} |
| Prematch lines | {summary["prematch_lines"]} |
| API calls this run | {summary["api_calls"]} |
| Providers | {", ".join(summary["providers_with_cs"])} |

## Storage

- Additive tables only (`correct_score_odds_lines`, ingestion runs, manual imports, forward plan)
- Existing `odds_snapshots` rows are **never overwritten**
- Odds kind: `api_extracted` vs `manual_owner_confirmed` clearly separated

## Daily pipeline

Optional cache-first enrichment after eligibility; does not block prediction, create jobs, modify freezes, or evaluate results.

## Manual fallback

Designed with owner confirmation gate — see `artifacts/correct_score_odds/manual_import_design.json`.

## Forward shadow

Plan windows: first available / 24h / 6h / 1h / final prematch. Never after kickoff.

## Artifacts

See `artifacts/correct_score_odds/`.

## Next

Re-run two-fixture portfolio research using **only real** CS odds for ROI.

STOP constraints respected: no production betting, no formula changes.
"""
    (REPORTS / "CORRECT_SCORE_ODDS_INGESTION_REPORT.md").write_text(en, encoding="utf-8")

    fa = f"""# گزارش دریافت ضرایب اسکور دقیق (Correct Score)

**وضعیت نهایی:** `{summary["final_status"]}`  
**زمان:** {summary["generated_at"]}

## خلاصه

ضرایب پیش‌ازبازی اسکور دقیق از `odds_snapshots` موجود استخراج و در جدول افزودنی `correct_score_odds_lines` ذخیره شد.

- تعداد بازی دارای CS: **{summary["fixtures_with_cs"]}**
- تعداد خطوط پیش‌ازبازی: **{summary["prematch_lines"]}**
- فراخوانی API در این اجرا: **{summary["api_calls"]}**
- ارائه‌دهندگان: {", ".join(summary["providers_with_cs"])}

بازار کانونی: `CORRECT_SCORE_90_MINUTES`  
بدون شرط‌بندی خودکار، بدون تغییر ECSE/WDE/فریز.

جزئیات: `artifacts/correct_score_odds/`
"""
    (REPORTS / "CORRECT_SCORE_ODDS_INGESTION_REPORT_FA.md").write_text(fa, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
