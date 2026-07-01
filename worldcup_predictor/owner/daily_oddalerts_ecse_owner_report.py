"""Daily OddAlerts ECSE owner report builder."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.owner.daily_oddalerts_ecse_pipeline import (
    DailyPipelineResult,
    owner_report_json_path,
    owner_report_md_path,
)
from worldcup_predictor.research.oddalerts_ecse_monitor import ensure_monitor_table


def _load_monitor_signals(conn, date_from: str, date_to: str) -> list[dict[str, Any]]:
    ensure_monitor_table(conn)
    rows = conn.execute(
        """
        SELECT home_team, away_team, competition, kickoff_utc, top_1_score,
               top_3_scores_json, top_5_scores_json, segment_badge_v2,
               expected_top3_rate, expected_top5_rate, top5_value_signal,
               promotion_eligibility_v2, reasons_json, cautions_json,
               source_trace_json, final_score, top1_hit, top3_hit, top5_hit
        FROM ecse_oddalerts_shadow_monitor
        WHERE substr(kickoff_utc, 1, 10) >= ? AND substr(kickoff_utc, 1, 10) <= ?
        ORDER BY kickoff_utc ASC
        """,
        (date_from, date_to),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        out.append(
            {
                "match": f"{r['home_team']} vs {r['away_team']}",
                "competition": r["competition"],
                "kickoff_utc": r["kickoff_utc"],
                "top1": r["top_1_score"],
                "top3": json.loads(r.get("top_3_scores_json") or "[]"),
                "top5": json.loads(r.get("top_5_scores_json") or "[]"),
                "badge_v2": r["segment_badge_v2"],
                "expected_top3_rate": r.get("expected_top3_rate"),
                "expected_top5_rate": r.get("expected_top5_rate"),
                "top5_value_signal": bool(r.get("top5_value_signal")),
                "eligibility": r.get("promotion_eligibility_v2"),
                "reasons": json.loads(r.get("reasons_json") or "[]"),
                "cautions": json.loads(r.get("cautions_json") or "[]"),
                "source_trace": json.loads(r.get("source_trace_json") or "{}"),
                "finished": r.get("final_score") is not None,
                "final_score": r.get("final_score"),
                "hits": {
                    "top1": r.get("top1_hit"),
                    "top3": r.get("top3_hit"),
                    "top5": r.get("top5_hit"),
                },
            }
        )
    return out


def build_daily_oddalerts_ecse_owner_report(result: DailyPipelineResult) -> dict[str, Any]:
    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row

    signals = _load_monitor_signals(conn, result.date_from, result.date_to)
    upcoming = [s for s in signals if not s["finished"]]
    finished = [s for s in signals if s["finished"]]
    eligible_upcoming = [
        s
        for s in upcoming
        if s.get("eligibility") in ("eligible_limited_write_later", "eligible_shadow_watch")
    ]
    conn.close()

    state = result.to_state_dict()
    json_path = owner_report_json_path(result.process_date)
    md_path = owner_report_md_path(result.process_date)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        **state,
        "upcoming_monitored": upcoming,
        "finished_evaluated": finished,
        "best_eligible_signals": eligible_upcoming[:20],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    skipped = result.skipped_reasons or {}
    promo = result.promotion or {}
    gmail = result.gmail or {}
    mon = result.monitor or {}

    signal_lines = []
    for s in eligible_upcoming[:10]:
        signal_lines.append(
            f"| {s['match']} | {s['competition']} | {s['kickoff_utc'][:16]} | "
            f"{s['top1']} | {', '.join(str(x) for x in (s['top3'] or [])[:3])} | "
            f"{s['badge_v2']} | {s.get('expected_top3_rate')} | {s.get('top5_value_signal')} |"
        )

    md = f"""# Daily OddAlerts ECSE Owner Report

**Date:** {result.process_date}  
**Window:** {result.date_from} → {result.date_to}  
**Run ID:** `{result.run_id}`  
**Recommendation:** `{result.final_recommendation}`

---

## 1. OddAlerts CSV status

| Metric | Value |
|--------|-------|
| Emails scanned | {gmail.get('emails_found', 0)} |
| CSV links found | {gmail.get('links_found', 0)} |
| New files downloaded | {gmail.get('files_downloaded', 0)} |
| Duplicates skipped | {gmail.get('duplicates_skipped', 0)} |
| Rows imported | {state.get('rows_imported', 0)} |
| READY_FULL before → after | {result.ready_full_before} → {result.ready_full_after} |

---

## 2. Odds snapshot status

| Metric | Value |
|--------|-------|
| Inserted | {promo.get('inserted_count', 0)} |
| Enriched | {promo.get('enriched_count', 0)} |
| Skipped | {promo.get('skipped_count', 0)} |
| Safe candidates | {promo.get('safe_candidate_count', 0)} |
| Promotion status | {promo.get('status', 'not_run')} |
| Backup | {(promo.get('backup') or {}).get('backup_path', '—')} |

---

## 3. Limited Shadow Monitor

| Metric | Value |
|--------|-------|
| Candidates discovered | {mon.get('discovered_count', 0)} |
| Records written | {mon.get('written_count', 0)} |
| Skipped non-eligible v2 | {mon.get('skipped_ineligible_count', 0)} |
| Upcoming monitored | {len(upcoming)} |
| Finished evaluated | {len(finished)} |

---

## 4. Best owner-only signals (eligible upcoming)

| Match | Competition | Kickoff | Top1 | Top3 | Badge | Exp Top3 | Top5 signal |
|-------|-------------|---------|------|------|-------|----------|-------------|
{chr(10).join(signal_lines) if signal_lines else '| — | — | — | — | — | — | — | — |'}

---

## 5. Waiting / missing data

| Reason | Count |
|--------|-------|
| no_oddalerts_snapshot | {skipped.get('no_oddalerts_snapshot', 0)} |
| historical_shadow_batch | {skipped.get('historical_shadow_batch', 0)} |
| outside_kickoff_window | {skipped.get('outside_kickoff_window', 0)} |
| high_disagreement_block | {skipped.get('high_disagreement_block', 0)} |
| fresh_provider_conflict | {skipped.get('fresh_provider_conflict', 0)} |
| monitor non-eligible v2 | {mon.get('skipped_ineligible_count', 0)} |

---

## Production guard

| Table | Before | After |
|-------|--------|-------|
| ecse_prediction_snapshots | {result.production_guard.get('before', {}).get('ecse_prediction_snapshots')} | {result.production_guard.get('after', {}).get('ecse_prediction_snapshots')} |
| odds_snapshots | {result.production_guard.get('before', {}).get('odds_snapshots')} | {result.production_guard.get('after', {}).get('odds_snapshots')} |
| worldcup_stored_predictions | {result.production_guard.get('before', {}).get('worldcup_stored_predictions')} | {result.production_guard.get('after', {}).get('worldcup_stored_predictions')} |

**Owner Lab:** `/owner/ecse-oddalerts-shadow` (Historical Shadow + Live Shadow Monitor tabs)
"""
    md_path.write_text(md, encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "payload": payload}
