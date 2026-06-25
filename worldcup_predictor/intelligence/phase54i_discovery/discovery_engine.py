"""Phase 54I discovery orchestrator — cache-first + capped API probes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.intelligence.phase54i_discovery.auditors import audit_fixture_blob

ARTIFACT_DIR = Path("artifacts/phase54i_lineups_player_goalscorer_discovery")

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
)

_TARGET_LEAGUES: dict[int, str] = {
    732: "world_cup",
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
}

_DEEP_INCLUDES = (
    "participants;league;season;state;events.type;events.player;"
    "statistics.type;lineups.player;lineups.details.type;lineups.xGLineup.type;"
    "formations;sidelined.sideline;odds.bookmaker;odds.market"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _league_label(league_id: int) -> str:
    return _TARGET_LEAGUES.get(league_id, f"league_{league_id}")


def scan_cache_roots() -> dict[str, Any]:
    seen: set[int] = set()
    fixtures: list[dict[str, Any]] = []
    for root in _CACHE_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json")):
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            audit = audit_fixture_blob(blob)
            if not audit.get("valid"):
                continue
            fid = int(audit.get("sportmonks_fixture_id") or 0)
            if fid in seen:
                continue
            seen.add(fid)
            audit["cache_path"] = str(path)
            fixtures.append(audit)

    by_league: dict[str, dict[str, int]] = {}
    by_season: dict[str, dict[str, int]] = {}
    totals = {
        "fixtures_scanned": len(fixtures),
        "with_starting_xi": 0,
        "with_bench": 0,
        "with_formations": 0,
        "with_player_minutes": 0,
        "with_goalscorer_odds": 0,
        "with_player_xg": 0,
        "prematch_usable": 0,
        "historical_usable": 0,
    }
    for fx in fixtures:
        lid = str(fx.get("league_id") or "unknown")
        sid = str(fx.get("season_id") or "unknown")
        by_league.setdefault(lid, {"fixtures": 0, "starting_xi": 0, "goalscorer_odds": 0})
        by_season.setdefault(sid, {"fixtures": 0, "starting_xi": 0, "goalscorer_odds": 0})
        by_league[lid]["fixtures"] += 1
        by_season[sid]["fixtures"] += 1
        lu = fx.get("lineups") or {}
        ps = fx.get("player_stats") or {}
        go = fx.get("goalscorer_odds") or {}
        if lu.get("has_starting_xi"):
            totals["with_starting_xi"] += 1
            by_league[lid]["starting_xi"] += 1
            by_season[sid]["starting_xi"] += 1
        if lu.get("has_bench"):
            totals["with_bench"] += 1
        if lu.get("formations_available"):
            totals["with_formations"] += 1
        if ps.get("players_with_minutes", 0) >= 20:
            totals["with_player_minutes"] += 1
        if go.get("has_goalscorer_odds"):
            totals["with_goalscorer_odds"] += 1
            by_league[lid]["goalscorer_odds"] += 1
            by_season[sid]["goalscorer_odds"] += 1
        if ps.get("player_xg_available"):
            totals["with_player_xg"] += 1
        if lu.get("usable_prematch"):
            totals["prematch_usable"] += 1
        if lu.get("usable_historical_backtest"):
            totals["historical_usable"] += 1

    return {
        "generated_at": _utc_now(),
        "source": "cache_scan",
        "cache_roots": [str(r) for r in _CACHE_ROOTS if r.is_dir()],
        "totals": totals,
        "by_league": by_league,
        "by_season": by_season,
        "fixtures": fixtures,
    }


def probe_api(*, max_calls: int = 35) -> dict[str, Any]:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider, redact_sportmonks_secrets

    settings = get_settings()
    provider = SportmonksProvider(settings)
    token = settings.sportmonks_effective_token
    calls = 0
    probes: list[dict[str, Any]] = []

    def _call(group: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        nonlocal calls
        if calls >= max_calls:
            return {"group": group, "skipped": True, "reason": "max_calls"}
        calls += 1
        status, payload, err = provider.safe_get(path, params=params or {})
        err_safe = redact_sportmonks_secrets(str(err or ""), token) if err else None
        return {
            "group": group,
            "path": path,
            "status": status,
            "error": err_safe,
            "ok": status == 200 and isinstance(payload, dict),
            "payload_keys": sorted((payload or {}).get("data") or {})[:20] if isinstance(payload, dict) else [],
        }

    league_seasons: dict[str, Any] = {}
    for league_id in _TARGET_LEAGUES:
        if calls >= max_calls:
            break
        _, payload, err = provider.safe_get(
            f"/leagues/{league_id}",
            params={"include": "seasons;currentSeason"},
        )
        calls += 1
        season_id = None
        if isinstance(payload, dict):
            data = payload.get("data") or {}
            cur = data.get("currentseason") or data.get("currentSeason")
            if isinstance(cur, dict):
                season_id = cur.get("id")
        league_seasons[str(league_id)] = {"season_id": season_id, "error": err}
        if season_id and calls < max_calls:
            status, payload, err = provider.safe_get(f"/topscorers/seasons/{season_id}")
            calls += 1
            rows = (payload or {}).get("data") if isinstance(payload, dict) else []
            n_rows = len(rows) if isinstance(rows, list) else 0
            league_seasons[str(league_id)]["topscorer_rows"] = n_rows
            probes.append(
                {
                    "group": "topscorers",
                    "path": f"/topscorers/seasons/{season_id}",
                    "status": status,
                    "ok": status == 200,
                    "rows": n_rows,
                    "error": redact_sportmonks_secrets(str(err or ""), token) if err else None,
                }
            )

    # Deep fixture probe per league (1 call each)
    for league_id, label in _TARGET_LEAGUES.items():
        if calls >= max_calls:
            break
        season_id = (league_seasons.get(str(league_id)) or {}).get("season_id")
        filters = f"fixtureSeasons:{season_id}" if season_id else f"fixtureLeagues:{league_id}"
        _, fx_payload, _ = provider.safe_get(
            "/fixtures",
            params={"filters": filters, "include": "state", "per_page": 25, "page": 1},
        )
        calls += 1
        fx_id = None
        if isinstance(fx_payload, dict):
            rows = fx_payload.get("data") or []
            finished = [r for r in rows if isinstance(r, dict) and int(r.get("state_id") or 0) in {5, 7, 8}]
            if finished:
                fx_id = int(finished[0].get("id") or 0)
        if fx_id and calls < max_calls:
            _, deep, _ = provider.safe_get(
                f"/fixtures/{fx_id}",
                params={"include": _DEEP_INCLUDES},
            )
            calls += 1
            blob = {"payload": {"data": (deep or {}).get("data")}}
            audit = audit_fixture_blob(blob) if isinstance(deep, dict) else {"valid": False}
            probes.append(
                {
                    "group": "deep_fixture",
                    "league_id": league_id,
                    "league_label": label,
                    "fixture_id": fx_id,
                    "audit": {k: audit.get(k) for k in ("lineups", "player_stats", "goalscorer_odds") if k in audit},
                }
            )

    return {
        "generated_at": _utc_now(),
        "source": "api_probe",
        "api_calls_used": calls,
        "max_calls": max_calls,
        "configured": provider.is_configured,
        "league_seasons": league_seasons,
        "probes": probes,
    }


def build_feature_potential_matrix(
    cache: dict[str, Any],
    api: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    totals = cache.get("totals") or {}
    n = max(1, int(totals.get("fixtures_scanned") or 1))
    pct_xi = round(100.0 * int(totals.get("with_starting_xi") or 0) / n, 1)
    pct_odds = round(100.0 * int(totals.get("with_goalscorer_odds") or 0) / n, 1)
    pct_xg = round(100.0 * int(totals.get("with_player_xg") or 0) / n, 1)
    pct_min = round(100.0 * int(totals.get("with_player_minutes") or 0) / n, 1)

    def _rec(
        feature: str,
        coverage: str,
        quality: str,
        egie: str,
        gs: str,
        rec: str,
    ) -> dict[str, str]:
        return {
            "feature": feature,
            "coverage": coverage,
            "quality": quality,
            "egie_value": egie,
            "goalscorer_value": gs,
            "recommendation": rec,
        }

    api_has_topscorer = any(
        int((v or {}).get("topscorer_rows") or 0) > 0 for v in (api or {}).get("league_seasons", {}).values()
    )
    return [
        _rec("Starting XI", f"{pct_xi}%", "high", "medium", "high", "BUILD_LINEUP_PLAYER_FEATURE_STORE"),
        _rec("Bench", f"{round(100*totals.get('with_bench',0)/n,1)}%", "high", "low", "medium", "BUILD_LINEUP_PLAYER_FEATURE_STORE"),
        _rec("Formation", f"{round(100*totals.get('with_formations',0)/n,1)}%", "high", "medium", "low", "BUILD_LINEUP_PLAYER_FEATURE_STORE"),
        _rec("Player minutes", f"{pct_min}%", "high", "low", "high", "BUILD_LINEUP_PLAYER_FEATURE_STORE"),
        _rec("Player goals/assists", f"{pct_min}%", "medium", "low", "high", "BUILD_LINEUP_PLAYER_FEATURE_STORE"),
        _rec("Player shots", "partial", "medium", "low", "medium", "BUILD_LINEUP_PLAYER_FEATURE_STORE"),
        _rec("Player xG", f"{pct_xg}%", "low" if pct_xg < 30 else "medium", "low", "high", "BUILD_LINEUP_PLAYER_FEATURE_STORE" if pct_xg < 30 else "BUILD_GOALSCORER_FEATURE_STORE"),
        _rec("Player rating", "partial", "medium", "low", "medium", "BUILD_LINEUP_PLAYER_FEATURE_STORE"),
        _rec("Topscorers API", "API" if api_has_topscorer else "unknown", "high" if api_has_topscorer else "unknown", "medium", "high", "BUILD_GOALSCORER_FEATURE_STORE"),
        _rec("First goalscorer odds", f"{pct_odds}%", "medium", "low", "high", "GOALSCORER_ODDS_RESEARCH_ONLY"),
        _rec("Anytime goalscorer odds", f"{pct_odds}%", "medium", "low", "high", "GOALSCORER_ODDS_RESEARCH_ONLY"),
        _rec("Team to score first odds", "high", "high", "high", "medium", "existing_odds_parser"),
        _rec("Sidelined/injuries", "low", "low", "medium", "medium", "BUILD_LINEUP_PLAYER_FEATURE_STORE"),
    ]


def recommend_final(cache: dict[str, Any], api: dict[str, Any] | None = None) -> str:
    totals = cache.get("totals") or {}
    n = int(totals.get("fixtures_scanned") or 0)
    if n < 20:
        return "INSUFFICIENT_PLAYER_DATA"
    if int(totals.get("with_starting_xi") or 0) < n * 0.5:
        return "INSUFFICIENT_PLAYER_DATA"
    if int(totals.get("with_goalscorer_odds") or 0) >= n * 0.5:
        if int(totals.get("with_player_minutes") or 0) >= n * 0.5:
            return "BUILD_GOALSCORER_FEATURE_STORE"
    if int(totals.get("prematch_usable") or 0) >= 30:
        return "BUILD_LINEUP_PLAYER_FEATURE_STORE"
    return "GOALSCORER_ODDS_RESEARCH_ONLY"


def run_discovery(*, max_api_calls: int = 35, skip_api: bool = False) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    cache = scan_cache_roots()
    api = None if skip_api else probe_api(max_calls=max_api_calls)
    matrix = build_feature_potential_matrix(cache, api)
    recommendation = recommend_final(cache, api)

    # Slim cache fixtures for JSON (drop per-fixture detail in summary file)
    cache_summary = {k: v for k, v in cache.items() if k != "fixtures"}
    cache_summary["fixture_sample_count"] = len(cache.get("fixtures") or [])

    out = {
        "generated_at": _utc_now(),
        "phase": "54I",
        "backtest_only": True,
        "production_changes": False,
        "lineups_discovery": cache_summary,
        "player_stats_discovery": {
            "totals": cache.get("totals"),
            "by_league": cache.get("by_league"),
        },
        "goalscorer_odds_discovery": {
            "fixtures_with_goalscorer_odds": int((cache.get("totals") or {}).get("with_goalscorer_odds") or 0),
            "fixtures_scanned": int((cache.get("totals") or {}).get("fixtures_scanned") or 0),
        },
        "api_probe": api,
        "feature_potential_matrix": matrix,
        "recommendation": recommendation,
    }

    (ARTIFACT_DIR / "lineups_discovery.json").write_text(
        json.dumps(cache_summary, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACT_DIR / "player_stats_discovery.json").write_text(
        json.dumps(out["player_stats_discovery"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACT_DIR / "goalscorer_odds_discovery.json").write_text(
        json.dumps(out["goalscorer_odds_discovery"], indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACT_DIR / "feature_potential_matrix.json").write_text(
        json.dumps(matrix, indent=2, default=str), encoding="utf-8"
    )
    if api:
        (ARTIFACT_DIR / "api_probe.json").write_text(json.dumps(api, indent=2, default=str), encoding="utf-8")
    (ARTIFACT_DIR / "discovery_summary.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    # Full per-fixture cache detail
    (ARTIFACT_DIR / "fixture_audits.json").write_text(
        json.dumps(cache.get("fixtures") or [], indent=2, default=str), encoding="utf-8"
    )
    return out
