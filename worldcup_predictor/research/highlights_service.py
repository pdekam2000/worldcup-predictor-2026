"""Phase 60C — Public-safe research highlights payload."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PHASE60C_DIR = ROOT / "artifacts" / "phase60c_goal_event_backfill"
HIGHLIGHTS_CACHE = PHASE60C_DIR / "research_highlights_cache.json"

FORBIDDEN_KEYS = frozenset(
    {
        "shadow",
        "elite_shadow",
        "wde",
        "root_cause",
        "admin",
        "internal_model",
        "lambda_bridge",
        "promotion",
    }
)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_highlights_payload() -> dict[str, Any]:
    after = _load_json(PHASE60C_DIR / "first_goal_distribution_after_backfill.json")
    odds = _load_json(PHASE60C_DIR / "odds_bucket_summary.json")
    quality = _load_json(PHASE60C_DIR / "data_quality_report.json")
    backfill = _load_json(PHASE60C_DIR / "backfill_result.json")

    if not after:
        after = _load_json(ROOT / "artifacts" / "phase60b_first_goal_timing_distribution" / "first_goal_timing_summary.json")

    main = (after or {}).get("main_answer") or {}
    overall = (after or {}).get("overall") or {}
    with_goal = main.get("among_fixtures_with_at_least_one_goal") or {}
    all_rel = main.get("among_all_reliable_completed_fixtures") or {}

    payload: dict[str, Any] = {
        "generated_at": (after or {}).get("generated_at") or datetime.now(timezone.utc).isoformat() + "Z",
        "disclaimer": "Research stats, not betting advice.",
        "first_goal_distribution": {
            "first_goal_1_30_pct": with_goal.get("first_goal_1_30_pct"),
            "first_goal_31_plus_pct": with_goal.get("first_goal_31_plus_pct"),
            "no_goal_pct": all_rel.get("no_goal_pct"),
            "sample_size_with_goal": with_goal.get("sample_size"),
            "sample_size_reliable": all_rel.get("sample_size"),
            "last_updated": (after or {}).get("generated_at"),
        },
        "bucket_distribution": {
            "counts": overall.get("bucket_counts") or {},
            "pct_of_reliable": overall.get("bucket_pct_of_reliable") or {},
        },
        "odds_bucket_stats": (odds or {}).get("favorite_bucket_stats") or {},
        "ou_bucket_stats": (odds or {}).get("ou_bucket_stats") or {},
        "data_quality": {
            "reliable_fixtures": overall.get("total_reliable_fixtures"),
            "excluded_fixtures": overall.get("data_missing_fixtures"),
            "api_calls_used": (backfill or {}).get("api_calls_used", 0),
            "fixtures_backfilled": (backfill or {}).get("fixtures_backfilled", 0),
            "coverage_warning": "Large share of finished fixtures may still lack goal-event timing until backfill expands.",
            "comparison": (quality or {}).get("comparison") or (backfill or {}).get("comparison"),
        },
    }
    return _strip_private(payload)


def _strip_private(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_private(v) for k, v in obj.items() if not any(f in str(k).lower() for f in FORBIDDEN_KEYS)}
    if isinstance(obj, list):
        return [_strip_private(v) for v in obj]
    return obj


def cache_highlights_payload(payload: dict[str, Any] | None = None) -> Path:
    PHASE60C_DIR.mkdir(parents=True, exist_ok=True)
    data = payload or build_highlights_payload()
    HIGHLIGHTS_CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return HIGHLIGHTS_CACHE


def load_highlights_payload() -> dict[str, Any]:
    cached = _load_json(HIGHLIGHTS_CACHE)
    if cached:
        return cached
    payload = build_highlights_payload()
    cache_highlights_payload(payload)
    return payload
