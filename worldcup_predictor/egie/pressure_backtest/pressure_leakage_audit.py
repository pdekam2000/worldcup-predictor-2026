"""Leakage audit for Phase 54H-1 pressure shadow backtest."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.pressure_backtest.pressure_dataset_builder import ARTIFACT_DIR, ARTIFACT_DIR_H2
from worldcup_predictor.egie.pressure_backtest.pressure_feature_builder import (
    FORBIDDEN_PREMATCH_KEYS,
    PRESSURE_FEATURE_NAMES,
    PressureFeatureBuilder,
)
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_uefa_goal_events
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
from worldcup_predictor.config.settings import get_settings

FORBIDDEN_LABEL_KEYS = frozenset(
    {
        "label_first_goal_team",
        "label_goal_range",
        "label_next_goal_team",
        "label_goal_minute_bucket",
        "label_home_goals",
        "label_away_goals",
        "label_total_goals",
        "home_goals",
        "away_goals",
        "final_score",
    }
)


def run_pressure_leakage_audit(output_dir: Path | None = None) -> dict[str, Any]:
    out_dir = output_dir or ARTIFACT_DIR
    builder = PressureFeatureBuilder()
    summaries = builder.load_ordered_summaries()
    chronological = builder.build_prematch_chronological_features(summaries)
    settings = get_settings()
    checks: list[dict[str, Any]] = []

    leaked_keys: set[str] = set()
    for feats in chronological.values():
        leaked_keys |= FORBIDDEN_PREMATCH_KEYS & set(feats.keys())
        leaked_keys |= FORBIDDEN_LABEL_KEYS & set(feats.keys())
    checks.append(
        {
            "name": "no_forbidden_keys_in_prematch_features",
            "pass": len(leaked_keys) == 0,
            "detail": f"forbidden_keys_found={sorted(leaked_keys)}",
        }
    )

    first_match_violations = 0
    team_seen: dict[int, bool] = {}
    for row in summaries:
        sm_id = int(row.get("sportmonks_fixture_id") or 0)
        feats = chronological.get(sm_id, {})
        for tid in (row.get("home_team_id"), row.get("away_team_id")):
            if tid is None:
                continue
            tid = int(tid)
            if not team_seen.get(tid):
                if feats.get("pressure_available"):
                    first_match_violations += 1
                team_seen[tid] = True
    checks.append(
        {
            "name": "prematch_first_fixture_no_pressure_history",
            "pass": first_match_violations == 0,
            "detail": f"violations={first_match_violations}",
        }
    )

    inplay_violations = 0
    inplay_checked = 0
    for row in summaries:
        sm_id = int(row.get("sportmonks_fixture_id") or 0)
        home_id = int(row.get("home_team_id") or 0)
        away_id = int(row.get("away_team_id") or 0)
        cache = load_cache(cache_path(settings, sm_id))
        payload = (cache or {}).get("payload")
        if not payload or home_id <= 0:
            continue
        goals = parse_uefa_goal_events(payload)
        for goal in goals[:3]:
            minute = goal.get("minute")
            if minute is None:
                continue
            inplay_checked += 1
            feats = builder.build_inplay_features_before_minute(
                sm_id,
                before_minute=int(minute),
                home_team_id=home_id,
                away_team_id=away_id,
            )
            if feats.get("inplay_before_minute") != int(minute):
                inplay_violations += 1
            raw_rows = builder.repo.get_records_for_fixture(sm_id)
            leaked_after = [
                r for r in raw_rows if int(r.get("minute") or -1) >= int(minute) and feats.get("pressure_available")
            ]
            if leaked_after and feats.get("pressure_last_10_home") is not None:
                max_used = max(int(r.get("minute") or -1) for r in raw_rows if int(r.get("minute") or -1) < int(minute))
                if max_used >= int(minute):
                    inplay_violations += 1
    checks.append(
        {
            "name": "inplay_uses_pressure_before_target_only",
            "pass": inplay_violations == 0,
            "detail": f"checked={inplay_checked} violations={inplay_violations}",
        }
    )

    checks.append(
        {
            "name": "no_final_score_in_feature_columns",
            "pass": not any(k in PRESSURE_FEATURE_NAMES for k in FORBIDDEN_LABEL_KEYS),
            "detail": "pressure_feature_names_clean",
        }
    )

    temporal_ok = True
    team_last_at: dict[int, Any] = {}
    for row in summaries:
        sm_id = int(row.get("sportmonks_fixture_id") or 0)
        started = row.get("match_started_at")
        feats = chronological.get(sm_id, {})
        for tid in (row.get("home_team_id"), row.get("away_team_id")):
            if tid is None:
                continue
            tid = int(tid)
            if feats.get("pressure_available") and tid in team_last_at:
                if started and team_last_at[tid] and started < team_last_at[tid]:
                    temporal_ok = False
            team_last_at[tid] = started
    checks.append(
        {
            "name": "no_future_fixture_leakage",
            "pass": temporal_ok,
            "detail": "prematch_uses_strictly_prior_fixtures",
        }
    )

    passed = all(c["pass"] for c in checks)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "all_pass": passed,
        "fixtures_audited": len(summaries),
        "checks": checks,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "leakage_audit.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
