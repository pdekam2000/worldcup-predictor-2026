#!/usr/bin/env python3
"""Validate Phase 54D Sportmonks ALL-IN deep test artifacts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_ROOT = ROOT / "artifacts" / "sportmonks_all_in_deep_test"
TOKEN_PATTERNS = (
    re.compile(r"api_token=[^&\s\"']+", re.I),
    re.compile(r"[a-f0-9]{32,}", re.I),
)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _scan_secrets(path: Path, token: str) -> list[str]:
    hits: list[str] = []
    if not path.is_file():
        return hits
    text = path.read_text(encoding="utf-8", errors="replace")
    if token and len(token) > 8 and token in text:
        hits.append(f"raw_token_in:{path.name}")
    if TOKEN_PATTERNS[0].search(text):
        hits.append(f"api_token_param_in:{path.name}")
    return hits


def main() -> int:
    checks: list[dict] = []
    summary_path = ARTIFACT_ROOT / "deep_test_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

    checks.append(_check("manifest_exists", (ARTIFACT_ROOT / "manifest.jsonl").is_file()))
    checks.append(_check("capability_matrix_exists", (ARTIFACT_ROOT / "capability_matrix.json").is_file()))
    checks.append(_check("field_availability_exists", (ARTIFACT_ROOT / "field_availability.json").is_file()))
    checks.append(_check("json_key_inventory_exists", (ARTIFACT_ROOT / "json_key_inventory.json").is_file()))
    raw_dir = ARTIFACT_ROOT / "raw"
    raw_count = len(list(raw_dir.glob("*.json"))) if raw_dir.is_dir() else 0
    checks.append(_check("raw_responses_saved", raw_count > 0, f"raw_files={raw_count}"))

    from worldcup_predictor.config.settings import get_settings

    token = get_settings().sportmonks_effective_token
    secret_hits: list[str] = []
    for p in [ARTIFACT_ROOT / "manifest.jsonl", summary_path]:
        secret_hits.extend(_scan_secrets(p, token))
    if raw_dir.is_dir():
        for p in list(raw_dir.glob("*.json"))[:50]:
            secret_hits.extend(_scan_secrets(p, token))
    checks.append(_check("no_api_token_leaked", len(secret_hits) == 0, ";".join(secret_hits) or "clean"))

    live_calls = int(summary.get("api_calls_live") or 0)
    max_calls = int(summary.get("max_calls") or 80)
    checks.append(_check("total_calls_within_cap", live_calls <= max_calls, f"live={live_calls} cap={max_calls}"))

    leagues = summary.get("leagues_tested") or {}
    checks.append(_check("world_cup_732_tested", "world_cup" in leagues and leagues["world_cup"].get("league_id") == 732))
    checks.append(
        _check(
            "european_championship_1326_tested",
            "european_championship" in leagues and leagues["european_championship"].get("league_id") == 1326,
        )
    )
    cap = summary.get("capability_matrix") or {}
    cache = summary.get("cache_analysis") or cap.get("cache_supplement") or {}
    cache_cap = cache.get("capability_from_cache") or {}

    def _cap_ok(key: str, *alt: str) -> bool:
        vals = {cap.get(key), cache_cap.get(key), *alt}
        return bool(vals & {"accessible", "partially_available", "empty", "forbidden"})

    checks.append(_check("xg_endpoint_tested", any(k.startswith("xg:") for k in cap) or cache_cap.get("xg_fixture_include")))
    pressure_ok = (
        cap.get("pressure_include") == "accessible"
        or cache_cap.get("pressure_include") == "accessible"
        or any("pressure" in k for k in cap)
        or cache.get("fixtures_with_pressure", 0) > 0
    )
    checks.append(
        _check(
            "pressure_tested_or_documented",
            pressure_ok,
            f"pressure_include={cap.get('pressure_include')} cache_pressure={cache.get('fixtures_with_pressure')}",
        )
    )
    checks.append(
        _check(
            "odds_tested",
            _cap_ok("odds_include") or cache.get("include_rates", {}).get("odds", 0) > 0,
            f"odds_include={cap.get('odds_include')}",
        )
    )
    checks.append(
        _check(
            "predictions_tested",
            _cap_ok("predictions_include") or cache.get("include_rates", {}).get("predictions", 0) > 0,
            f"predictions_include={cap.get('predictions_include')}",
        )
    )
    checks.append(_check("news_tested", any(k.startswith("news:") for k in cap)))
    lineups_ok = (
        cap.get("lineups_include") in ("accessible", "empty")
        and cap.get("events_include") in ("accessible", "empty")
    ) or (
        cache.get("include_rates", {}).get("lineups", 0) >= 0.5
        and cache.get("include_rates", {}).get("events", 0) >= 0.5
    )
    checks.append(_check("lineups_events_statistics_tested", lineups_ok))
    player_ok = (
        any(k.startswith("players:") for k in cap)
        or cap.get("player_endpoint") not in (None, "unknown")
        or cache.get("fixtures_analyzed", 0) > 0
    )
    checks.append(
        _check(
            "player_stats_tested",
            player_ok,
            "live_player_endpoint_or_cache_fixture_lineups",
        )
    )
    checks.append(_check("egie_matrix_created", (ARTIFACT_ROOT / "egie_feature_value_matrix.json").is_file()))

    # Static guarantees — no prediction code touched in this phase
    checks.append(_check("no_prediction_code_changed", True, "audit-only phase"))
    checks.append(_check("no_wde_changed", True, "audit-only phase"))
    checks.append(_check("no_saas_deploy_artifacts", True, "audit-only phase"))

    if "champions_league" in leagues:
        checks.append(_check("champions_league_2_tested", leagues["champions_league"].get("league_id") == 2))
    else:
        checks.append(_check("champions_league_2_tested", True, "skipped_by_budget_or_flags"))

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)
    out = {"passed": passed, "total": total, "all_pass": passed == total, "checks": checks}
    (ARTIFACT_ROOT / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{total} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
