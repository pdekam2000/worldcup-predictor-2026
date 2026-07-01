#!/usr/bin/env python3
"""Build static owner lab report for ECSE OddAlerts shadow predictions."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.owner.oddalerts_ecse_lab_service import EcseOddalertsOwnerLabService
from worldcup_predictor.research.oddalerts_ecse_shadow import DEFAULT_RUN_ID, PROCESS_DATE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPORT_DIR = Path("reports/owner")
PHASE = "ECSE-ODDALERTS-3"


def _date_tag(process_date: str) -> str:
    return process_date.replace("-", "")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def build_report_payload(data: dict) -> dict[str, object]:
    items = data.get("items") or []
    all_data = data
    # Re-fetch unfiltered for full lists
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "shadow_run_id": data.get("shadow_run_id"),
        "summary": data.get("summary"),
        "evaluation_stats": data.get("evaluation_stats"),
        "segment_stats": data.get("segment_stats"),
        "strong_signals": [
            {
                "fixture_id": i["fixture_id"],
                "match": f"{i.get('home_team')} vs {i.get('away_team')}",
                "top_1_score": i.get("top_1_score"),
                "segment_score": i.get("segment_score"),
                "promotion_action": i.get("promotion_action"),
            }
            for i in sorted(items, key=lambda x: -(x.get("segment_score") or 0))
            if i.get("segment_badge") == "STRONG_SHADOW_SIGNAL"
        ][:25],
        "strongest_inserted": [
            {
                "fixture_id": i["fixture_id"],
                "match": f"{i.get('home_team')} vs {i.get('away_team')}",
                "segment_score": i.get("segment_score"),
                "top_1_score": i.get("top_1_score"),
            }
            for i in sorted(
                [x for x in items if x.get("promotion_action") == "inserted"],
                key=lambda x: -(x.get("segment_score") or 0),
            )
        ][:15],
        "strongest_enriched": [
            {
                "fixture_id": i["fixture_id"],
                "match": f"{i.get('home_team')} vs {i.get('away_team')}",
                "segment_score": i.get("segment_score"),
                "top_1_score": i.get("top_1_score"),
            }
            for i in sorted(
                [x for x in items if x.get("promotion_action") == "enriched"],
                key=lambda x: -(x.get("segment_score") or 0),
            )
        ][:15],
        "weak_or_do_not_use": [
            {
                "fixture_id": i["fixture_id"],
                "match": f"{i.get('home_team')} vs {i.get('away_team')}",
                "segment_badge": i.get("segment_badge"),
                "segment_score": i.get("segment_score"),
                "cautions": i.get("segment_cautions"),
            }
            for i in items
            if i.get("segment_badge") in ("DO_NOT_USE", "WATCH_ONLY")
        ][:25],
        "recommendations": {
            "monitor_strong_inserted_bundesliga": "Inserted snapshots in bundesliga with STRONG badge",
            "avoid_world_cup_auto_promote": "World Cup segment underperforms — watch only until sample grows",
            "prefer_bookmaker_agreement": "Filter bookmaker_agreement_min=1 for tighter signals",
        },
    }


def build_markdown(payload: dict) -> str:
    summary = payload.get("summary") or {}
    eval_stats = payload.get("evaluation_stats") or {}
    return f"""# ECSE OddAlerts Owner Lab Report

**Phase:** {PHASE}  
**Generated:** {payload.get('generated_at_utc')}  
**Shadow run:** `{payload.get('shadow_run_id')}`

## Summary

| Metric | Value |
|--------|-------|
| Total shadow records | {summary.get('total_shadow_records')} |
| Finished | {summary.get('finished_count')} |
| Strong signals | {summary.get('strong_signal_count')} |
| Do not use | {summary.get('do_not_use_count')} |

## Evaluation

- Top-1: {eval_stats.get('top1_hit_rate')}
- Top-3: {eval_stats.get('top3_hit_rate')}
- Top-5: {eval_stats.get('top5_hit_rate')}

## Strong signals (top 10)

{json.dumps((payload.get('strong_signals') or [])[:10], indent=2)}

## Weak / do-not-use sample

{json.dumps((payload.get('weak_or_do_not_use') or [])[:10], indent=2)}

## Segment stats

{json.dumps(payload.get('segment_stats') or {}, indent=2)}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=PROCESS_DATE)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    args = parser.parse_args()

    tag = _date_tag(args.date)
    json_out = Path(f"artifacts/ecse_oddalerts_owner_lab_{tag}.json")
    md_out = REPORT_DIR / f"ecse_oddalerts_owner_lab_{tag}.md"

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120)
    conn.row_factory = sqlite3.Row
    service = EcseOddalertsOwnerLabService()
    data = service.list_shadow_predictions(conn, shadow_run_id=args.run_id, limit=500)
    conn.close()

    payload = build_report_payload(data)
    json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md_out.write_text(build_markdown(payload), encoding="utf-8")

    print(json.dumps({"records": summary_count(data), "json": str(json_out), "md": str(md_out)}, indent=2))
    return 0


def summary_count(data: dict) -> int:
    return int((data.get("summary") or {}).get("total_shadow_records") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
