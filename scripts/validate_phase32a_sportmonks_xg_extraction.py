"""Phase 32A — Sportmonks xG Match extraction validation."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _sample_fixture() -> dict:
    return {
        "id": 88003,
        "league_id": 732,
        "participants": [
            {"id": 10, "meta": {"location": "home"}},
            {"id": 11, "meta": {"location": "away"}},
        ],
        "xGFixture": {
            "expected": [
                {"type_id": 5304, "location": "home", "data": {"value": 1.65}},
                {"type_id": 5304, "location": "away", "data": {"value": 0.92}},
                {"type_id": 5305, "location": "home", "data": {"value": 1.10}},
                {"type_id": 5305, "location": "away", "data": {"value": 0.70}},
                {"type_id": 7939, "location": "home", "data": {"value": 1.8}},
                {"type_id": 7939, "location": "away", "data": {"value": 0.9}},
                {"type_id": 7940, "location": "home", "data": {"value": 0.12}},
                {"type_id": 7941, "location": "away", "data": {"value": 0.05}},
            ]
        },
        "lineups": [
            {
                "player_id": 101,
                "player_name": "Demo Striker",
                "team_id": 10,
                "xGLineup": [
                    {"type_id": 5304, "data": {"value": 0.88}},
                    {"type_id": 5305, "data": {"value": 0.55}},
                ],
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 32A Sportmonks xG extraction.")
    parser.add_argument("--live", action="store_true", help="Allow live Sportmonks API calls.")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass xG file store cache.")
    args = parser.parse_args()

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.providers.sportmonks_enrichment import (
        PREMIUM_WORLD_CUP_FIXTURE_INCLUDES,
        WORLD_CUP_FIXTURE_INCLUDES,
    )
    from worldcup_predictor.providers.sportmonks_xg_extraction import (
        XG_MATCH_FIXTURE_INCLUDES,
        build_sportmonks_xg_api_block,
        extract_dashboard_demo_fixture,
        extract_fixture_xg_match,
        parse_sportmonks_xg_match,
        save_xg_extraction_store,
    )

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    record("xg_match_includes_has_xgfixture_type", "xGFixture.type" in XG_MATCH_FIXTURE_INCLUDES)
    record("xg_match_includes_has_lineups_xglineup", "lineups.xGLineup.type" in XG_MATCH_FIXTURE_INCLUDES)
    record("premium_includes_xgfixture", "xGFixture" in PREMIUM_WORLD_CUP_FIXTURE_INCLUDES)
    record("world_cup_includes_xgfixture", "xGFixture" in WORLD_CUP_FIXTURE_INCLUDES)

    sample = _sample_fixture()
    parsed = parse_sportmonks_xg_match(sample)
    api_block = build_sportmonks_xg_api_block(parsed)
    record("offline_parse_available", parsed.get("available") is True)
    record("offline_home_xg", parsed["team"]["home_xg"] == 1.65)
    record("offline_away_xg", parsed["team"]["away_xg"] == 0.92)
    record("offline_home_xgot", parsed["team"]["home_xgot"] == 1.10)
    record("offline_home_xpts", parsed["team"]["home_xpts"] == 1.8)
    record("offline_xg_penalties", parsed["team"]["home_xg_penalties"] == 0.12)
    record("offline_xg_free_kicks", parsed["team"]["away_xg_free_kicks"] == 0.05)
    record("offline_player_xg", parsed["player_xg_summary"]["players_with_xg"] == 1)
    record("api_block_shape", api_block.get("source") == "sportmonks" and "home_xg" in api_block)

    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    wc_row = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(1489386)
    if wc_row:
        sm_id = int(wc_row["sportmonks_fixture_id"])
        record("wc_mapping_found", True, f"api=1489386 sm={sm_id}")
        wc_result = extract_fixture_xg_match(
            api_fixture_id=1489386,
            sportmonks_fixture_id=sm_id,
            home_team="Mexico",
            away_team="South Africa",
            settings=settings,
            repo=repo,
            force_refresh=False,
        )
        record("wc_cache_first_no_live_by_default", wc_result.api_calls_made == 0 or args.live)
        record("wc_raw_available", wc_result.raw_available is True)
        wc_api = build_sportmonks_xg_api_block(wc_result.parsed)
        record("wc_api_block_present", isinstance(wc_api, dict))
    else:
        record("wc_mapping_found", False, "No mapped WC fixture in SQLite cache")

    settings_for_store = get_settings()
    save_xg_extraction_store(
        settings=settings_for_store,
        sportmonks_fixture_id=88003,
        api_fixture_id=None,
        raw_fixture=sample,
        parsed=parsed,
        includes=XG_MATCH_FIXTURE_INCLUDES,
        source_chain=("validation",),
    )
    store_path = Path(settings_for_store.api_cache_dir) / "sportmonks" / "xg_match" / "88003.json"
    record("store_raw_and_parsed", store_path.is_file())

    live_summary: dict = {"attempted": False}
    if args.live:
        live_summary["attempted"] = True
        demo = extract_dashboard_demo_fixture(settings=settings, force_refresh=args.force_refresh)
        live_summary["dashboard_demo"] = {
            "success": demo.success,
            "api_calls": demo.api_calls_made,
            "message": demo.message,
            "api_block": build_sportmonks_xg_api_block(demo.parsed),
            "includes": list(demo.includes),
            "endpoint": demo.endpoint_path,
        }
        record("live_dashboard_demo_success", demo.success, demo.message)
        record("live_dashboard_has_xg", build_sportmonks_xg_api_block(demo.parsed).get("available") is True)

        if wc_row:
            wc_live = extract_fixture_xg_match(
                api_fixture_id=1489386,
                sportmonks_fixture_id=int(wc_row["sportmonks_fixture_id"]),
                home_team="Mexico",
                away_team="South Africa",
                settings=settings,
                repo=repo,
                force_refresh=args.force_refresh,
            )
            live_summary["wc_fixture"] = {
                "success": wc_live.success,
                "api_calls": wc_live.api_calls_made,
                "message": wc_live.message,
                "api_block": build_sportmonks_xg_api_block(wc_live.parsed),
            }
            record("live_wc_fetch_success", wc_live.success, wc_live.message)

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print("PHASE 32A — Sportmonks xG Extraction Validation")
    print("=" * 56)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    print("-" * 56)
    print(f"Result: {passed}/{total} checks passed")
    if live_summary.get("attempted"):
        print("Live summary:")
        print(json.dumps(live_summary, indent=2, default=str))

    out_path = Path("artifacts/phase32a_xg_extraction_validation.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "passed": passed,
                "total": total,
                "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
                "live": live_summary,
                "api_block_offline_sample": api_block,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
