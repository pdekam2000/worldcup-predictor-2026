"""Validate Phase 40A API quota protection."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool]] = []
    try:
        from worldcup_predictor.config.settings import Settings
        from worldcup_predictor.quota.quota_tracker import QuotaTracker, get_quota_tracker
        from worldcup_predictor.quota.request_throttle import ApiRequestThrottle, _is_rate_limit_error
        from worldcup_predictor.quota.sync_modes import DEFAULT_SYNC_MODE, fixture_query_params_for_mode

        checks.append(("default_fast_mode", DEFAULT_SYNC_MODE == "fast"))

        fast = fixture_query_params_for_mode({"league": 39, "season": 2024}, "fast")
        checks.append(("fast_has_from_to", "from" in fast and "to" in fast))
        full = fixture_query_params_for_mode({"league": 39, "season": 2024}, "full")
        checks.append(("full_keeps_season", full.get("season") == 2024))

        tracker = QuotaTracker()
        tracker.record_cache_hit()
        tracker.record_local_hit()
        snap = tracker.snapshot()
        checks.append(("calls_saved_tracked", snap.calls_saved >= 2))

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

        settings = Settings()
        checks.append(("settings_sync_mode", settings.api_sync_mode == "fast"))
        checks.append(("settings_throttle", settings.api_throttle_delay_seconds >= 0.5))

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
