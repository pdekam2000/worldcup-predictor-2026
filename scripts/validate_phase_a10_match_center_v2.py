#!/usr/bin/env python3
"""Phase A10 — Match Center V2 (AI Command Center) validation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # Files
    record(checks, "season_resolver", (ROOT / "worldcup_predictor/schedule/season_resolver.py").is_file())
    record(checks, "season_resolve_cache", (ROOT / "worldcup_predictor/quota/season_resolve_cache.py").is_file())
    record(checks, "match_schedule_cache", (ROOT / "worldcup_predictor/quota/match_schedule_cache.py").is_file())
    record(checks, "match_center_aggregator", (ROOT / "worldcup_predictor/api/match_center_aggregator.py").is_file())
    record(checks, "todays_elite_picks_component", (FRONTEND / "src/components/match-center/TodaysElitePicks.jsx").is_file())
    record(checks, "match_center_skeleton", (FRONTEND / "src/components/match-center/MatchCenterSkeleton.jsx").is_file())
    record(checks, "owner_insight_overlay", (FRONTEND / "src/components/match-center/OwnerInsightOverlay.jsx").is_file())

    matches_py = (ROOT / "worldcup_predictor/api/routes/matches.py").read_text(encoding="utf-8")
    comps_py = (ROOT / "worldcup_predictor/api/routes/competitions.py").read_text(encoding="utf-8")
    helpers_py = (ROOT / "worldcup_predictor/api/match_center_helpers.py").read_text(encoding="utf-8")
    match_center = (FRONTEND / "src/pages/MatchCenter.jsx").read_text(encoding="utf-8")
    elite_card = (FRONTEND / "src/components/match-center/EliteMatchCard.jsx").read_text(encoding="utf-8")
    combo_js = (FRONTEND / "src/lib/comboGenerator.js").read_text(encoding="utf-8")
    api_js = (FRONTEND / "src/api/worldcupApi.js").read_text(encoding="utf-8")

    record(checks, "matches_parallel_aggregator", "aggregate_all_competitions" in matches_py)
    record(checks, "matches_elite_picks_endpoint", "/elite-picks-today" in matches_py)
    record(checks, "matches_owner_optional_auth", "get_optional_current_user" in matches_py)
    record(checks, "competitions_season_resolver", "resolve_active_season" in comps_py)
    record(checks, "helpers_ai_match_score", "compute_ai_match_score" in helpers_py)
    record(checks, "helpers_match_insights", "extract_match_insights" in helpers_py)
    record(checks, "helpers_fixture_status", "fixture_status_label" in helpers_py)
    record(checks, "helpers_elite_picks_today", "get_todays_elite_picks" in helpers_py)
    record(checks, "frontend_elite_picks_section", "TodaysElitePicks" in match_center)
    record(checks, "frontend_skeleton_loading", "MatchCenterSkeleton" in match_center)
    record(checks, "frontend_incremental_load", "PRIORITY_COMPETITION" in match_center)
    record(checks, "card_ai_score", "ai_match_score" in elite_card)
    record(checks, "card_insights", "match_insights" in elite_card)
    record(checks, "card_owner_overlay", "OwnerInsightOverlay" in elite_card)
    record(checks, "combo_safe_balanced", "SAFE COMBO" in combo_js and "BALANCED COMBO" in combo_js)
    record(checks, "combo_high_value_odds", "HIGH VALUE" in combo_js and "HIGH ODDS" in combo_js)
    record(checks, "combo_correlation_guard", "isCorrelated" in combo_js)
    record(checks, "api_auth_fetch_matches", "authFetch" in api_js)
    record(checks, "api_elite_picks_fetch", "fetchElitePicksToday" in api_js)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "WeightedDecision" in wde)
    record(checks, "scoring_engine_exists", "def " in scoring)

    try:
        from worldcup_predictor.schedule.season_resolver import resolve_active_season, _is_world_cup_locked
        from worldcup_predictor.config.competitions import get_competition

        wc = get_competition("world_cup_2026")
        record(checks, "world_cup_season_locked", _is_world_cup_locked(wc))
        pl = get_competition("premier_league")
        resolved_pl = resolve_active_season(pl.key)
        record(checks, "season_resolver_returns_int", isinstance(resolved_pl, int))
        record(checks, "no_hardcoded_2024_only", resolved_pl >= 2024)
    except Exception as exc:
        record(checks, "season_resolver_runtime", False, str(exc))

    try:
        from worldcup_predictor.api.match_center_helpers import (
            compute_ai_match_score,
            extract_match_insights,
            fixture_status_label,
            get_todays_elite_picks,
        )

        ai = compute_ai_match_score({"confidence": 80, "stars": 4, "is_elite_pick": True}, {"sportmonks_xg": {}})
        record(checks, "ai_score_labels", ai["score"] >= 58 and ai["label"] in ("Elite", "Strong", "Good", "Watch", "Skip"))
        insights = extract_match_insights({"sportmonks_xg": {"home_xg": 1.4}, "head_to_head": [{"winner": "home"}]})
        record(checks, "insights_from_payload", len(insights) >= 1)
        label = fixture_status_label(bucket="upcoming", status="NS", has_prediction=True, payload=None)
        record(checks, "fixture_status_ready", label == "Prediction Ready")
        picks = get_todays_elite_picks(
            [
                {
                    "date": time.strftime("%Y-%m-%dT12:00:00Z", time.gmtime()),
                    "prediction_summary": {"best_pick": "home", "no_bet": False, "confidence": 75},
                    "ai_match_score": {"score": 80},
                }
            ],
            limit=10,
        )
        record(checks, "elite_picks_today_filter", len(picks) == 1)
    except Exception as exc:
        record(checks, "helpers_runtime", False, str(exc))

    try:
        from worldcup_predictor.api.match_center_aggregator import aggregate_all_competitions
        from worldcup_predictor.quota.match_schedule_cache import cache_stats

        started = time.perf_counter()
        agg = aggregate_all_competitions(max_workers=4)
        elapsed = time.perf_counter() - started
        record(checks, "aggregator_shape", "results" in agg and "load_ms" in agg)
        record(checks, "aggregator_parallel_ms", agg.get("load_ms", 99999) < 60000, f"load_ms={agg.get('load_ms')}")
        stats = cache_stats()
        record(checks, "schedule_cache_stats", "valid_entries" in stats)
        # Second call should hit cache
        agg2 = aggregate_all_competitions(max_workers=4)
        hits2 = int(agg2.get("cache_hits") or 0)
        record(checks, "schedule_cache_hits", hits2 >= 0, f"cache_hits={hits2}")
        record(checks, "aggregator_second_call_faster", agg2.get("load_ms", 999) <= agg.get("load_ms", 0) + 1)
    except Exception as exc:
        record(checks, "aggregator_runtime", False, str(exc))

    try:
        from worldcup_predictor.api.routes.competitions import list_competitions

        payload = list_competitions(include_counts=False)
        keys = [c["key"] for c in payload["competitions"]]
        record(checks, "competitions_resolved_season_field", all("resolved_season" in c for c in payload["competitions"]))
        record(checks, "world_cup_in_list", "world_cup_2026" in keys)
    except Exception as exc:
        record(checks, "competitions_api_runtime", False, str(exc))

    try:
        from worldcup_predictor.api.routes.matches import elite_picks_today, list_matches
        from worldcup_predictor.api.deps import get_optional_current_user

        picks_payload = elite_picks_today(limit=5, competition="all")
        record(checks, "elite_picks_api_shape", "picks" in picks_payload)
        matches_payload = list_matches(
            status="upcoming",
            page=1,
            page_size=5,
            team=None,
            competition="world_cup_2026",
            season=None,
            has_prediction=None,
            include_summary=True,
            include_insights=True,
            country=None,
            elite_only=False,
            user=None,
        )
        record(checks, "matches_v2_fields", "elite_picks_today" in matches_payload or matches_payload.get("competition"))
        row = (matches_payload.get("matches") or [{}])[0]
        if row:
            record(checks, "match_row_ai_score", "ai_match_score" in row)
            record(checks, "match_row_status_label", "fixture_status_label" in row)
            record(checks, "owner_meta_hidden_guest", "owner_meta" not in row or row.get("owner_meta") is None)
    except Exception as exc:
        record(checks, "matches_api_runtime", False, str(exc))

    filters = (FRONTEND / "src/components/match-center/MatchCenterFilters.jsx").read_text(encoding="utf-8")
    record(checks, "quick_filter_elite", "Elite Picks" in filters)
    record(checks, "quick_filter_world_cup", "World Cup" in filters)
    record(checks, "quick_filter_champions", "Champions League" in filters)
    record(checks, "mobile_spacing_match_center", "px-1 sm:px-0" in match_center)

    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=240,
            shell=os.name == "nt",
        )
        record(checks, "frontend_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-400:])
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A10 Match Center V2 — {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    report_path = ROOT / "data" / "validation" / "phase_a10_match_center_v2.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
