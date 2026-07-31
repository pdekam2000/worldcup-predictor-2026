"""30-day forward shadow evaluation (research-only, no production interaction)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.phase4.forward_shadow import (
    connect,
    evaluate_prediction_day,
    store_prediction_day,
    summarize_forward_shadow,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.historical_validation import (
    run_historical_validation,
)


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_forward_shadow_30d(
    *,
    db_path: Path,
    frozen_fixtures: list[dict[str, Any]],
    historical_comparison: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """
    Group frozen completed fixtures by kickoff date, store + evaluate each day.
    Extends Phase-4 forward_shadow.db schema without production writes.
    """
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fx in frozen_fixtures:
        day = str(fx.get("kickoff") or "")[:10]
        if len(day) < 10:
            day = "unknown"
        by_day[day].append(fx)

    days_sorted = sorted(d for d in by_day if d != "unknown")[-30:]
    daily_reports = []
    for day in days_sorted:
        rows = by_day[day]
        hv = run_historical_validation(rows)
        cf = hv["complete_coupon_failure"]
        priced = hv["priced_subset_analysis"]
        day_id = store_prediction_day(
            db_path,
            prediction_date=day,
            main_tickets=[{"ticket_id": f"MAIN-{fx['fixture_id']}", "fixture_id": fx["fixture_id"]} for fx in rows],
            insurance_tickets=[
                {
                    "ticket_id": f"INS-{fx['fixture_id']}",
                    "fixture_id": fx["fixture_id"],
                    "market": fx.get("insurance_market_label"),
                }
                for fx in rows
                if fx.get("insurance_market_label")
            ],
            coverage_report={
                "n": len(rows),
                "coverage_main": hv["strategies"]["exact3_main"]["coverage_rate"],
                "coverage_ins": hv["strategies"]["exact3_main_insurance"]["coverage_rate"],
            },
            budget={"research_unit_stake": 1.0, "n_fixtures": len(rows)},
            day_id=f"fwd_{day}",
        )
        evaluate_prediction_day(
            db_path,
            day_id=day_id,
            main_only_result={"all_ticket_loss_frequency": cf.get("main_only_all_ticket_loss_frequency")},
            main_plus_insurance_result={
                "all_ticket_loss_frequency": cf.get("main_plus_insurance_all_ticket_loss_frequency")
            },
            insurance_hit_rate=round(
                cf.get("insurance_rescue_count", 0) / max(1, len(rows)), 8
            ),
            coverage_gain=round(
                hv["strategies"]["exact3_main_insurance"]["coverage_rate"]
                - hv["strategies"]["exact3_main"]["coverage_rate"],
                8,
            ),
            daily_roi=priced.get("roi"),
            notes="Frozen completed fixtures — research forward shadow.",
        )
        daily_reports.append(
            {
                "date": day,
                "n_fixtures": len(rows),
                "roi": priced.get("roi"),
                "coupon_survival_main": hv["strategies"]["exact3_main"]["ticket_survival_rate"],
                "coupon_survival_main_insurance": hv["strategies"]["exact3_main_insurance"][
                    "ticket_survival_rate"
                ],
                "coverage_gain": round(
                    hv["strategies"]["exact3_main_insurance"]["coverage_rate"]
                    - hv["strategies"]["exact3_main"]["coverage_rate"],
                    8,
                ),
            }
        )

    summary = summarize_forward_shadow(db_path)
    weekly = []
    for i in range(0, len(daily_reports), 7):
        chunk = daily_reports[i : i + 7]
        rois = [d["roi"] for d in chunk if d.get("roi") is not None]
        weekly.append(
            {
                "week_index": i // 7 + 1,
                "n_days": len(chunk),
                "roi_sum": round(sum(rois), 8) if rois else None,
                "avg_coverage_gain": round(
                    sum(d["coverage_gain"] for d in chunk) / len(chunk), 8
                )
                if chunk
                else None,
            }
        )
    monthly = {
        "n_days": len(daily_reports),
        "roi_sum": round(sum(d["roi"] for d in daily_reports if d.get("roi") is not None), 8)
        if any(d.get("roi") is not None for d in daily_reports)
        else None,
        "avg_coverage_gain": round(
            sum(d["coverage_gain"] for d in daily_reports) / len(daily_reports), 8
        )
        if daily_reports
        else None,
        "insurance_improves_survival_days": sum(
            1
            for d in daily_reports
            if d["coupon_survival_main_insurance"] >= d["coupon_survival_main"]
        ),
    }

    # Persist extended daily metrics table
    conn = connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_metrics (
              prediction_date TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL
            )
            """
        )
        for d in daily_reports:
            conn.execute(
                "INSERT OR REPLACE INTO daily_metrics(prediction_date, payload_json) VALUES (?, ?)",
                (d["date"], json.dumps(d)),
            )
        conn.commit()
    finally:
        conn.close()

    payload = {
        "research_only": True,
        "owner_only": True,
        "no_production_interaction": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_forward_days": len(daily_reports),
        "daily_report": daily_reports,
        "weekly_report": weekly,
        "monthly_report": monthly,
        "forward_shadow_summary": summary,
        "historical_comparison": {
            "historical_main_fail": (historical_comparison.get("complete_coupon_failure") or {}).get(
                "main_only_all_ticket_loss_frequency"
            ),
            "historical_main_ins_fail": (historical_comparison.get("complete_coupon_failure") or {}).get(
                "main_plus_insurance_all_ticket_loss_frequency"
            ),
            "forward_improves_vs_main_days": monthly.get("insurance_improves_survival_days"),
        },
        "forward_evidence_sufficient": len(daily_reports) >= 14
        and monthly.get("insurance_improves_survival_days", 0) > len(daily_reports) * 0.5,
        "note": (
            f"Evaluated {len(daily_reports)} frozen prediction days (cap 30). "
            "Not a live production shadow."
        ),
    }
    out = output_dir / "forward_shadow_30d.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifact"] = str(out)
    return payload
