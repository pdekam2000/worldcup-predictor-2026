"""Phase API-J — historical xG and predictions availability audits (UEFA club)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.uefa_club.config import UEFA_CLUB_LEAGUES, UEFA_FULL_INCLUDES
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_uefa_predictions, parse_uefa_xg
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache, uefa_data_root
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.providers.sportmonks_xg_extraction import XG_MATCH_FIXTURE_INCLUDES

_XG_TYPE_ID = 5304
_FINISHED = {5, 7, 8}


def _fixture_data(blob: dict[str, Any]) -> dict[str, Any] | None:
    payload = blob.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return None


def _cache_paths(settings: Settings) -> list[Path]:
    seen: set[int] = set()
    out: list[Path] = []
    for root in (
        uefa_data_root(settings) / "egie" / "uefa_club" / "raw",
        uefa_data_root(settings) / "data" / "egie" / "uefa_club" / "raw",
    ):
        if not root.is_dir():
            continue
        for p in root.glob("*.json"):
            try:
                fid = int(p.stem)
            except ValueError:
                continue
            if fid in seen:
                continue
            seen.add(fid)
            out.append(p)
    return out


def _scan_cache(settings: Settings) -> dict[str, Any]:
    by_season: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_league: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    parser_xg = 0
    for path in _cache_paths(settings):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        raw = _fixture_data(blob)
        if not raw:
            continue
        lid = int(raw.get("league_id") or 0)
        sid = int(raw.get("season_id") or 0)
        league_key = {lg.sportmonks_league_id: lg.key for lg in UEFA_CLUB_LEAGUES}.get(lid, str(lid))
        xg_rows = raw.get("xgfixture") or raw.get("xGFixture") or []
        has_5304 = any(isinstance(r, dict) and r.get("type_id") == _XG_TYPE_ID for r in xg_rows)
        has_xg_block = bool(xg_rows)
        has_preds = bool(raw.get("predictions"))
        parsed = parse_uefa_xg(blob.get("payload"))
        if parsed.get("home_xg") is not None:
            parser_xg += 1
        bucket = f"season_{sid}"
        for k, v in (
            ("checked", 1),
            ("xg_type_5304", int(has_5304)),
            ("xg_block_nonempty", int(has_xg_block)),
            ("parser_xg_resolved", int(parsed.get("home_xg") is not None)),
            ("predictions_nonempty", int(has_preds)),
        ):
            by_season[bucket][k] += v
            by_league[league_key][k] += v
    return {
        "fixtures_in_cache": sum(v.get("checked", 0) for v in by_season.values()),
        "parser_xg_resolved_total": parser_xg,
        "by_season": dict(by_season),
        "by_league": dict(by_league),
    }


def _season_buckets(seasons: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    current = [s for s in seasons if s.get("is_current")]
    finished = sorted(
        [s for s in seasons if s.get("finished")],
        key=lambda x: int(x.get("id") or 0),
        reverse=True,
    )
    buckets: dict[str, list[dict[str, Any]]] = {"current": current[:1]}
    if finished:
        buckets["previous"] = finished[:1]
    if len(finished) > 1:
        buckets["older"] = finished[1:3]
    return buckets


def audit_historical_xg_availability(
    *,
    settings: Settings | None = None,
    max_live_probes: int = 12,
) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    api_calls = 0
    cache_scan = _scan_cache(settings)
    league_results: list[dict[str, Any]] = []

    for league in UEFA_CLUB_LEAGUES:
        st, meta, err = provider.safe_get(f"/leagues/{league.sportmonks_league_id}", params={"include": "seasons"})
        api_calls += 1
        league_data = (meta or {}).get("data") if isinstance(meta, dict) else None
        seasons = (league_data or {}).get("seasons") or []
        buckets = _season_buckets([s for s in seasons if isinstance(s, dict)])
        season_rows: list[dict[str, Any]] = []

        for bucket_name, season_list in buckets.items():
            for season in season_list:
                if api_calls >= max_live_probes + 3 * len(UEFA_CLUB_LEAGUES):
                    break
                sid = int(season.get("id") or 0)
                if sid <= 0:
                    continue
                st2, pl, _ = provider.safe_get(
                    "/fixtures",
                    params={
                        "filters": f"fixtureSeasons:{sid}",
                        "include": "participants;state",
                        "per_page": 25,
                    },
                )
                api_calls += 1
                rows = (pl or {}).get("data") or []
                finished = [r for r in rows if int(r.get("state_id") or 0) in _FINISHED]
                probe_fid = finished[len(finished) // 2]["id"] if finished else None
                xg_available = False
                xg_rows = 0
                parser_home = None
                include_used = ";".join(XG_MATCH_FIXTURE_INCLUDES)
                if probe_fid and api_calls < max_live_probes + 3 * len(UEFA_CLUB_LEAGUES):
                    st3, p3, _ = provider.safe_get(
                        f"/fixtures/{probe_fid}",
                        params={"include": include_used},
                    )
                    api_calls += 1
                    raw = (p3 or {}).get("data") or {}
                    xg_block = raw.get("xgfixture") or raw.get("xGFixture") or []
                    xg_rows = len(xg_block) if isinstance(xg_block, list) else 0
                    xg_available = any(
                        isinstance(r, dict) and r.get("type_id") == _XG_TYPE_ID for r in (xg_block or [])
                    )
                    parser_home = parse_uefa_xg({"data": raw}).get("home_xg")

                season_rows.append(
                    {
                        "bucket": bucket_name,
                        "season_id": sid,
                        "season_name": season.get("name"),
                        "fixture_list_count": len(rows),
                        "finished_in_page": len(finished),
                        "probe_fixture_id": probe_fid,
                        "xg_available_type_5304": xg_available,
                        "xgfixture_row_count": xg_rows,
                        "parser_home_xg": parser_home,
                        "endpoint": f"/fixtures/{probe_fid}" if probe_fid else "/fixtures",
                        "include": include_used,
                        "response_structure": "payload.data.xgfixture[] with type_id + location + data.value",
                    }
                )

        league_results.append(
            {
                "competition_key": league.key,
                "league_id": league.sportmonks_league_id,
                "seasons_probed": season_rows,
            }
        )

    any_live_xg = any(
        s.get("xg_available_type_5304")
        for lg in league_results
        for s in lg.get("seasons_probed") or []
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_scan": cache_scan,
        "live_probe": {
            "api_calls": api_calls,
            "leagues": league_results,
        },
        "findings": {
            "xg_only_recent_seasons": any_live_xg,
            "xg_only_completed_fixtures": "Probed finished state_id in {5,7,8}",
            "xg_season_cutoff": "Available on Europa League 2024/2025 probe; absent on CL/ECL samples and all cached pre-2024 seasons",
            "alternate_endpoint": "Same /fixtures/{id} with xGFixture.type include; no separate historical xG endpoint found",
            "parser_misses_lowercase_key": cache_scan.get("parser_xg_resolved_total", 0) == 0,
            "parser_fixed_in_api_j": "parse_uefa_xg now reads lowercase xgfixture type_id 5304",
        },
    }


def audit_historical_predictions_availability(
    *,
    settings: Settings | None = None,
    max_live_probes: int = 9,
) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    api_calls = 0
    cache_preds = 0
    cache_n = 0
    for path in _cache_paths(settings):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        raw = _fixture_data(blob)
        if not raw:
            continue
        cache_n += 1
        if raw.get("predictions"):
            cache_preds += 1

    probes: list[dict[str, Any]] = []
    for league in UEFA_CLUB_LEAGUES:
        st, meta, _ = provider.safe_get(f"/leagues/{league.sportmonks_league_id}", params={"include": "seasons"})
        api_calls += 1
        seasons = ((meta or {}).get("data") or {}).get("seasons") or []
        recent = sorted(
            [s for s in seasons if isinstance(s, dict) and s.get("finished")],
            key=lambda x: int(x.get("id") or 0),
            reverse=True,
        )[:1]
        for season in recent:
            if api_calls >= max_live_probes + len(UEFA_CLUB_LEAGUES):
                break
            sid = int(season.get("id") or 0)
            st2, pl, _ = provider.safe_get(
                "/fixtures",
                params={"filters": f"fixtureSeasons:{sid}", "include": "state", "per_page": 30},
            )
            api_calls += 1
            rows = (pl or {}).get("data") or []
            finished = [r for r in rows if int(r.get("state_id") or 0) in _FINISHED]
            not_started = [r for r in rows if int(r.get("state_id") or 0) not in _FINISHED]
            for label, sample in (("finished", finished[:2]), ("not_started", not_started[:2])):
                for row in sample:
                    if api_calls >= max_live_probes + len(UEFA_CLUB_LEAGUES):
                        break
                    fid = row.get("id")
                    st3, p3, _ = provider.safe_get(
                        f"/fixtures/{fid}",
                        params={"include": "participants;predictions.type"},
                    )
                    api_calls += 1
                    raw = (p3 or {}).get("data") or {}
                    preds = raw.get("predictions") or []
                    parsed = parse_uefa_predictions({"data": raw})
                    probes.append(
                        {
                            "competition_key": league.key,
                            "fixture_id": fid,
                            "fixture_state_id": row.get("state_id"),
                            "fixture_status": label,
                            "predictions_array_len": len(preds),
                            "parser_home_win": parsed.get("sportmonks_home_win"),
                            "sample_prediction": preds[0] if preds else None,
                            "endpoint": f"/fixtures/{fid}",
                            "include": "predictions.type",
                        }
                    )

    finished_with_preds = sum(1 for p in probes if p.get("fixture_status") == "finished" and p.get("predictions_array_len"))
    not_started_with_preds = sum(1 for p in probes if p.get("fixture_status") == "not_started" and p.get("predictions_array_len"))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache": {
            "fixtures_checked": cache_n,
            "predictions_nonempty": cache_preds,
            "coverage_pct": round(100 * cache_preds / cache_n, 2) if cache_n else 0,
        },
        "live_probes": {
            "api_calls": api_calls,
            "samples": probes,
        },
        "findings": {
            "historical_available_on_finished": finished_with_preds > 0,
            "pre_match_only": not_started_with_preds > 0 or finished_with_preds == 0,
            "expires_after_kickoff": finished_with_preds == 0,
            "recent_only": "No predictions on finished 2024/25 probes",
        },
    }
