"""Validate API quota protection — prediction cache, guards, fixtures list cache."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys
import tempfile

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool]] = []
    try:
        from datetime import datetime, timedelta, timezone

        from worldcup_predictor.config.settings import Settings
        from worldcup_predictor.quota.fixtures_list_cache import get_cached, store
        from worldcup_predictor.quota.prediction_cache import get_cached_prediction, store_prediction
        from worldcup_predictor.quota.prediction_cache_policy import PHASE_22_REQUIRED_AGENT_KEYS, stamp_prediction_cache
        from worldcup_predictor.quota.quota_guard import QuotaGuardError, assert_force_refresh_allowed, quota_risk_level
        from worldcup_predictor.quota.quota_tracker import QuotaTracker, get_quota_tracker
        from worldcup_predictor.quota.request_throttle import ApiRequestThrottle, _is_rate_limit_error
        from worldcup_predictor.quota.sync_modes import DEFAULT_SYNC_MODE, fixture_query_params_for_mode
        from worldcup_predictor.quota.cache_policy import should_fetch_lineups

        checks.append(("default_fast_mode", DEFAULT_SYNC_MODE == "fast"))

        fast = fixture_query_params_for_mode({"league": 39, "season": 2024}, "fast")
        checks.append(("fast_has_from_to", "from" in fast and "to" in fast))
        full = fixture_query_params_for_mode({"league": 39, "season": 2024}, "full")
        checks.append(("full_keeps_season", full.get("season") == 2024))

        tracker = QuotaTracker()
        tracker.record_cache_hit()
        tracker.record_local_hit()
        tracker.record_prediction_cache_hit()
        tracker.record_prediction_cache_miss()
        snap = tracker.snapshot()
        checks.append(("calls_saved_tracked", snap.calls_saved >= 3))
        checks.append(("prediction_cache_counters", snap.prediction_cache_hits >= 1 and snap.prediction_cache_misses >= 1))

        throttle = ApiRequestThrottle(base_delay_seconds=0.01, rate_limit_delay_seconds=0.01)
        calls = {"n": 0}

        def _fn():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("HTTP 429 rate limit")
            return "ok"

        out = throttle.execute(_fn, quota_tracker=tracker)
        checks.append(("429_retry", out == "ok" and calls["n"] == 2))
        checks.append(("rate_limit_detect", _is_rate_limit_error(RuntimeError("request limit for the day"))))

        settings = Settings(
            prediction_cache_dir=str(Path(tempfile.mkdtemp()) / "predictions"),
            fixtures_list_cache_ttl_seconds=60,
            prediction_refresh_cooldown_seconds=30,
        )

        agents = {f"legacy_{i}": {"status": "available"} for i in range(18)}
        for key in PHASE_22_REQUIRED_AGENT_KEYS:
            agents[key] = {"status": "available"}
        payload = stamp_prediction_cache({
            "status": "ok",
            "fixture_id": 123,
            "home_team": "A",
            "away_team": "B",
            "prediction": "home",
            "confidence": 70,
            "cache_source": "live",
            "specialist_summary": {"agents": agents},
        })
        store_prediction(123, payload, competition_key="world_cup_2026", season=2026, locale="en", settings=settings)
        cached = get_cached_prediction(123, competition_key="world_cup_2026", season=2026, locale="en", settings=settings)
        checks.append(("prediction_cache_roundtrip", cached is not None and cached.get("fixture_id") == 123))

        list_payload = {"status": "ok", "count": 1, "matches": []}
        store("world_cup_2026", 2026, 10, list_payload, settings=settings)
        list_cached = get_cached("world_cup_2026", 2026, 10, settings=settings)
        checks.append(("fixtures_list_cache", list_cached is not None and list_cached.get("count") == 1))

        far_kickoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=48)
        checks.append(("lineups_skip_far", should_fetch_lineups(far_kickoff) is False))
        near_kickoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        checks.append(("lineups_fetch_near", should_fetch_lineups(near_kickoff) is True))

        try:
            assert_force_refresh_allowed(999, user_id="u1", is_admin=False, settings=settings)
            assert_force_refresh_allowed(999, user_id="u1", is_admin=False, settings=settings)
            checks.append(("refresh_cooldown", False))
        except QuotaGuardError:
            checks.append(("refresh_cooldown", True))

        risk = quota_risk_level(settings=settings)
        checks.append(("quota_risk_shape", "risk_level" in risk))

        checks.append(("settings_sync_mode", settings.api_sync_mode == "fast"))
        checks.append(("settings_daily_limit", settings.api_daily_live_limit > 0))

        global_tracker = get_quota_tracker()
        checks.append(("global_tracker", global_tracker is not None))
    except Exception as exc:
        print(f"FAIL: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print(f"\nAll {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
