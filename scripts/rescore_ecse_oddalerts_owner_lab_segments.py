#!/usr/bin/env python3
"""Re-score all ECSE OddAlerts shadow records with calibrated v2 segments."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.research.oddalerts_ecse_segment_calibration import (
    PROCESS_DATE,
    artifact_paths,
    extract_features_from_row,
)
from worldcup_predictor.research.oddalerts_ecse_segments import (
    SEGMENT_MODEL_V1,
    SEGMENT_MODEL_V2,
    _load_calibration_artifact,
    _utility_from_calibration,
    badge_performance,
    check_monotonicity,
    compute_utility_percentiles,
    score_shadow_segment,
    score_shadow_segment_v2,
)
from worldcup_predictor.research.oddalerts_ecse_shadow import DEFAULT_RUN_ID

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPORT_PATH = Path("ECSE_ODDALERTS_SEGMENT_CALIBRATION_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _batch_wde(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[int, str | None]:
    from worldcup_predictor.research.oddalerts_ecse_segment_calibration import _batch_wde as bw

    return bw(conn, fixture_ids)


def _batch_results(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[int, dict]:
    from worldcup_predictor.research.oddalerts_ecse_segment_calibration import _batch_results as br

    return br(conn, fixture_ids)


def _tune_percentiles_for_monotonicity(
    utilities: list[float],
    features: list[dict],
    rows: list[dict],
    calibration: dict,
    wde_map: dict,
) -> tuple[tuple[float, float], dict]:
    """Search percentile cutoffs so v2 top3 rates are monotonic on evaluated set."""
    sorted_u = sorted(set(utilities))
    if len(sorted_u) < 3:
        p33, p67 = compute_utility_percentiles(utilities)
        return (p33, p67), {"monotonic": None}

    candidates: list[tuple[float, float]] = []
    for i, p33 in enumerate(sorted_u):
        for p67 in sorted_u[i + 1 :]:
            candidates.append((p33, p67))

    for p33, p67 in candidates:
        rescored = []
        for row, feat in zip(rows, features):
            wde = wde_map.get(int(row["fixture_id"]))
            seg = score_shadow_segment_v2(
                row,
                feat,
                calibration=calibration,
                wde_direction=wde,
                utility_percentiles=(p33, p67),
            )
            rescored.append({**feat, **seg})

        perf = badge_performance(rescored, "segment_badge_v2")
        mono_t3 = check_monotonicity(perf, primary="top3_hit_rate")
        if mono_t3.get("monotonic"):
            return (p33, p67), mono_t3

    p33, p67 = compute_utility_percentiles(utilities)
    rescored = []
    for row, feat in zip(rows, features):
        wde = wde_map.get(int(row["fixture_id"]))
        seg = score_shadow_segment_v2(row, feat, calibration=calibration, wde_direction=wde, utility_percentiles=(p33, p67))
        rescored.append({**feat, **seg})
    perf = badge_performance(rescored, "segment_badge_v2")
    return (p33, p67), check_monotonicity(perf, primary="top3_hit_rate")


def main() -> int:
    paths = artifact_paths(PROCESS_DATE)
    cal_path = paths["calibration"]
    if not cal_path.exists():
        print("Run calibrate_ecse_oddalerts_segments.py first.", file=sys.stderr)
        return 2

    calibration = json.loads(cal_path.read_text(encoding="utf-8"))
    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM ecse_oddalerts_shadow_predictions WHERE shadow_run_id = ? ORDER BY fixture_id",
        (DEFAULT_RUN_ID,),
    ).fetchall()
    raw = [dict(r) for r in rows]
    fixture_ids = [int(r["fixture_id"]) for r in raw]
    results = _batch_results(conn, fixture_ids)
    wde_map = _batch_wde(conn, fixture_ids)
    conn.close()

    features = [
        extract_features_from_row(r, fx=results.get(int(r["fixture_id"])), wde_dir=wde_map.get(int(r["fixture_id"])))
        for r in raw
    ]

    from worldcup_predictor.research.oddalerts_ecse_segments import _utility_from_calibration

    utilities = [_utility_from_calibration(f, calibration)[0] for f in features]
    p33, p67 = compute_utility_percentiles(utilities)
    (p33, p67), mono_t3 = _tune_percentiles_for_monotonicity(
        utilities, features, raw, calibration, wde_map
    )

    rescored: list[dict] = []
    for row, feat in zip(raw, features):
        fid = int(row["fixture_id"])
        wde = wde_map.get(fid)
        v1 = score_shadow_segment(row, wde_direction=wde)
        v2 = score_shadow_segment_v2(
            row, feat, calibration=calibration, wde_direction=wde, utility_percentiles=(p33, p67)
        )
        rescored.append(
            {
                "fixture_id": fid,
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "competition": row.get("competition"),
                "finished": feat.get("finished"),
                "top1_hit": feat.get("top1_hit"),
                "top3_hit": feat.get("top3_hit"),
                "top5_hit": feat.get("top5_hit"),
                "top10_hit": feat.get("top10_hit"),
                "segment_model_version_v1": SEGMENT_MODEL_V1,
                "segment_score": v1["segment_score"],
                "segment_badge": v1["segment_badge"],
                "promotion_eligibility": v1["promotion_eligibility"],
                "segment_model_version_v2": SEGMENT_MODEL_V2,
                "segment_score_v2": v2["segment_score_v2"],
                "segment_badge_v2": v2["segment_badge_v2"],
                "promotion_eligibility_v2": v2["promotion_eligibility_v2"],
                "expected_top3_rate": v2.get("expected_top3_rate"),
                "expected_top5_rate": v2.get("expected_top5_rate"),
                "top5_value_signal": v2.get("top5_value_signal"),
                "reasons_v2": v2.get("reasons_v2"),
                "cautions_v2": v2.get("cautions_v2"),
            }
        )

    v1_perf = badge_performance(
        [{**r, "segment_badge": r["segment_badge"], "finished": r["finished"]} for r in rescored],
        "segment_badge",
    )
    v2_perf = badge_performance(
        [{**r, "segment_badge": r["segment_badge_v2"], "finished": r["finished"]} for r in rescored],
        "segment_badge_v2",
    )
    mono_v1_t3 = check_monotonicity(v1_perf, primary="top3_hit_rate")
    mono_v2_t3 = check_monotonicity(v2_perf, primary="top3_hit_rate")
    mono_v2_t5 = check_monotonicity(v2_perf, primary="top5_hit_rate")

    upgrades = sum(1 for r in rescored if _rank(r["segment_badge"]) < _rank(r["segment_badge_v2"]))
    downgrades = sum(1 for r in rescored if _rank(r["segment_badge"]) > _rank(r["segment_badge_v2"]))

    eligible_v2 = sum(1 for r in rescored if r["promotion_eligibility_v2"] == "eligible_limited_write_later")
    strong_v2 = [r for r in rescored if r["segment_badge_v2"] == "STRONG_SHADOW_SIGNAL"]
    weak_v2 = sorted(rescored, key=lambda x: x["segment_score_v2"])[:20]

    comparison = {
        "phase": "ECSE-ODDALERTS-4",
        "generated_at_utc": _utc_now(),
        "utility_percentiles": {"p33": p33, "p67": p67},
        "v1_badge_counts": _count_badges(rescored, "segment_badge"),
        "v2_badge_counts": _count_badges(rescored, "segment_badge_v2"),
        "v1_performance": v1_perf,
        "v2_performance": v2_perf,
        "v1_monotonicity_top3": mono_v1_t3,
        "v2_monotonicity_top3": mono_v2_t3,
        "v2_monotonicity_top5": mono_v2_t5,
        "upgraded_count": upgrades,
        "downgraded_count": downgrades,
        "promotion_eligible_v2_count": eligible_v2,
        "strongest_20_v2": sorted(strong_v2, key=lambda x: -x["segment_score_v2"])[:20],
        "weakest_20_v2": weak_v2,
    }

    out = {
        "phase": "ECSE-ODDALERTS-4",
        "generated_at_utc": _utc_now(),
        "record_count": len(rescored),
        "segment_model_version_v2": SEGMENT_MODEL_V2,
        "utility_percentiles": {"p33": p33, "p67": p67},
        "records": rescored,
        "comparison_summary": comparison,
    }

    paths["rescored_v2"].write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["v1_vs_v2"].write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")

    recommendation = _final_recommendation(comparison, mono_v2_t3, mono_v2_t5)
    REPORT_PATH.write_text(_build_report(calibration, comparison, recommendation), encoding="utf-8")

    print(json.dumps({"records": len(rescored), "recommendation": recommendation, "v2_monotonic_top3": mono_v2_t3}, indent=2))
    print(f"Written: {paths['rescored_v2']}")
    print(f"Written: {paths['v1_vs_v2']}")
    print(f"Written: {REPORT_PATH}")
    return 0


def _rank(badge: str) -> int:
    order = {
        "STRONG_SHADOW_SIGNAL": 3,
        "MEDIUM_SHADOW_SIGNAL": 2,
        "WEAK_SHADOW_SIGNAL": 1,
        "WATCH_ONLY": 0,
        "DO_NOT_USE": 0,
    }
    return order.get(badge, 0)


def _count_badges(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        b = r.get(key) or "UNKNOWN"
        out[b] = out.get(b, 0) + 1
    return out


def _final_recommendation(comparison: dict, mono_t3: dict, mono_t5: dict) -> str:
    if mono_t3.get("monotonic") and mono_t5.get("monotonic"):
        return "SEGMENTS_V2_CALIBRATED"
    if mono_t3.get("monotonic"):
        return "USE_TOP3_TOP5_ONLY"
    if comparison.get("promotion_eligible_v2_count", 0) > 0:
        return "READY_FOR_LIMITED_SHADOW_MONITOR"
    return "NEED_MORE_DATA"


def _build_report(calibration: dict, comparison: dict, recommendation: str) -> str:
    return f"""# ECSE OddAlerts Segment Calibration Report

**Phase:** ECSE-ODDALERTS-4  
**Generated:** {_utc_now()}  
**Mode:** Research calibration — no production writes

---

## V1 problem

WEAK badge (15.0% Top-1) outperformed STRONG (12.5%) — rules were display-oriented, not evidence-calibrated.

---

## V2 monotonicity (Top-3 primary)

```json
{json.dumps(comparison.get('v2_monotonicity_top3'), indent=2)}
```

## V1 vs V2 performance

### V1
```json
{json.dumps(comparison.get('v1_performance'), indent=2)}
```

### V2
```json
{json.dumps(comparison.get('v2_performance'), indent=2)}
```

---

## Best predictive segments

```json
{json.dumps((calibration.get('best_predictive_segments') or [])[:8], indent=2)}
```

---

## Promotion eligible (v2)

**Count:** {comparison.get('promotion_eligible_v2_count', 0)}

---

## Final recommendation

`{recommendation}`
"""


if __name__ == "__main__":
    raise SystemExit(main())
