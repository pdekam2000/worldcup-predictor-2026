"""Phase 64 — value / betting intelligence foundation (research only)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.odds_bucket_research import FAVORITE_BUCKETS, OddsBucketResearch

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "value_intelligence"


def _pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 2) if d else None


def run_value_intelligence(*, write_artifacts: bool = True) -> dict[str, Any]:
    """Aggregate odds-bucket statistics for future betting-safe research."""
    research = OddsBucketResearch()
    raw = research.run()
    rows = raw["match_rows"]
    favorite_stats = raw["favorite_bucket_stats"]
    ou_stats = raw["ou_bucket_stats"]

    bucket_rows: list[dict[str, Any]] = []
    for label in [b[2] for b in FAVORITE_BUCKETS]:
        stats = favorite_stats.get(label) or {}
        if not stats.get("match_count"):
            continue
        bucket_rows.append(
            {
                "bucket": label,
                "match_count": stats["match_count"],
                "favorite_win_pct": stats.get("favorite_win_pct"),
                "draw_pct": stats.get("draw_pct"),
                "underdog_win_pct": stats.get("underdog_win_pct"),
                "over_25_pct": stats.get("over_25_pct"),
                "btts_yes_pct": stats.get("btts_yes_pct"),
                "first_goal_1_30_pct": stats.get("first_goal_1_30_pct"),
                "favorite_blind_roi_pct": stats.get("favorite_blind_roi_pct"),
                "avg_goals": stats.get("avg_goals"),
            }
        )

    ou_rows: list[dict[str, Any]] = []
    for label, stats in (ou_stats or {}).items():
        if not stats.get("match_count"):
            continue
        ou_rows.append(
            {
                "ou_bucket": label,
                "match_count": stats["match_count"],
                "over_25_hit_rate_pct": stats.get("over_25_hit_rate_pct"),
                "avg_implied_over_prob": stats.get("avg_implied_over_prob"),
                "actual_over_prob": stats.get("actual_over_prob"),
                "edge_estimate": stats.get("edge_estimate"),
            }
        )

    total = len(rows)
    draws = sum(1 for r in rows if r.is_draw)
    fav_wins = sum(1 for r in rows if r.favorite_won)
    underdog = sum(1 for r in rows if r.underdog_won)
    over25 = sum(1 for r in rows if r.over_25)
    btts = sum(1 for r in rows if r.btts_yes)
    in_1_30 = sum(1 for r in rows if r.first_goal_1_30)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "disclaimer": "Research only — not betting advice.",
        "sample_size": total,
        "overall": {
            "favorite_win_pct": _pct(fav_wins, total),
            "draw_pct": _pct(draws, total),
            "underdog_win_pct": _pct(underdog, total),
            "over_25_hit_pct": _pct(over25, total),
            "btts_hit_pct": _pct(btts, total),
            "first_goal_1_30_pct": _pct(in_1_30, total),
        },
        "favorite_buckets": bucket_rows,
        "ou_buckets": ou_rows,
        "warnings": list(raw.get("warnings") or [])[:50],
        "data_quality_warnings": [
            "Odds coverage is sparse for some competitions",
            "Blind ROI by bucket is illustrative only",
            "No live betting recommendations are produced",
        ],
    }

    if write_artifacts:
        write_value_artifacts(summary)

    return summary


def write_value_artifacts(summary: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = ARTIFACT_DIR / "value_bucket_summary.json"
    csv_path = ARTIFACT_DIR / "value_bucket_summary.csv"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    rows = summary.get("favorite_buckets") or []
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text("bucket,match_count\n", encoding="utf-8")


def load_value_summary() -> dict[str, Any] | None:
    path = ARTIFACT_DIR / "value_bucket_summary.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
