"""Validate Phase 40A SQLite + file API cache."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys
import tempfile

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool]] = []
    try:
        from worldcup_predictor.cache.api_cache import ApiCache
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.quota.cache_policy import DAILY_TTL_SECONDS, MATCH_TTL_SECONDS, ttl_for_endpoint

        checks.append(("daily_ttl_24h", DAILY_TTL_SECONDS == 86400))
        checks.append(("match_ttl_30m", MATCH_TTL_SECONDS == 1800))
        checks.append(("standings_daily", ttl_for_endpoint("standings") == DAILY_TTL_SECONDS))
        checks.append(("lineups_match", ttl_for_endpoint("fixtures/lineups") == MATCH_TTL_SECONDS))

        path = Path(tempfile.mkstemp(suffix=".db")[1])
        repo = FootballIntelligenceRepository(str(path))
        key = ApiCache.build_key("standings", {"league": 39, "season": 2023})
        repo.set_api_cache_payload(
            cache_key=key,
            endpoint="standings",
            params={"league": 39, "season": 2023},
            payload=[{"ok": True}],
            expires_at="2099-01-01T00:00:00",
        )
        loaded = repo.get_api_cache_payload(key)
        checks.append(("sqlite_cache_roundtrip", loaded == [{"ok": True}]))
        checks.append(("api_response_cache_table", "api_response_cache" in repo.TABLE_NAMES))
    except Exception as exc:
        print(f"FAIL: {exc}")
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
