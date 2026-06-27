"""Sportmonks xG + lineups import for mapped World Cup fixtures — Phase 62B."""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.world_cup.config import (
    PROGRESS_CHECKPOINT_PATH,
    RAW_CACHE_DIR,
    SPORTMONKS_LEAGUE_ID,
    WORLD_CUP_COMPETITION_KEY,
)
from worldcup_predictor.egie.world_cup.progress_checkpoint import (
    is_fixture_complete,
    load_checkpoint,
    mark_fixture_complete,
    save_checkpoint,
)
from worldcup_predictor.egie.world_cup.progress_log import log_fixture_progress, log_progress
from worldcup_predictor.egie.world_cup.raw_cache import save_raw_with_fallback
from worldcup_predictor.feature_store.normalizers import build_fixture_summary_from_records, normalize_fixture_xg_records
from worldcup_predictor.providers.sportmonks_consumption import normalize_sportmonks_fixture
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.providers.sportmonks_xg_extraction import (
    XG_MATCH_FALLBACK_INCLUDES,
    XG_MATCH_FIXTURE_INCLUDES,
    parse_sportmonks_xg_match,
)

logger = logging.getLogger(__name__)

_XG_INCLUDES = ";".join(XG_MATCH_FIXTURE_INCLUDES)
_FALLBACK_INCLUDES = ";".join(XG_MATCH_FALLBACK_INCLUDES)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sm_cache_path(sm_id: int) -> Path:
    return Path.cwd() / RAW_CACHE_DIR / "sportmonks" / f"{sm_id}.json"


def _lineup_strength(lineup: dict[str, Any] | None) -> float | None:
    if not lineup:
        return None
    startxi = lineup.get("startXI") or lineup.get("startxi") or lineup.get("players") or []
    if not isinstance(startxi, list):
        return None
    starters = [p for p in startxi if isinstance(p, dict)]
    if not starters:
        return None
    return round(min(1.0, len(starters) / 11.0), 4)


def _goalkeeper_present(lineup: dict[str, Any] | None) -> bool:
    if not lineup:
        return False
    for block in (lineup.get("startXI") or lineup.get("startxi") or []):
        if not isinstance(block, dict):
            continue
        player = block.get("player") if isinstance(block.get("player"), dict) else block
        pos = str((player or {}).get("pos") or (player or {}).get("position") or "").upper()
        if pos in ("G", "GK", "GOALKEEPER"):
            return True
    return False


def _normalize_lineup_features(
    *,
    home_lineup: dict[str, Any] | None,
    away_lineup: dict[str, Any] | None,
    home_injuries: list[Any],
    away_injuries: list[Any],
) -> dict[str, Any]:
    home_strength = _lineup_strength(home_lineup)
    away_strength = _lineup_strength(away_lineup)
    return {
        "home_lineup_strength": home_strength,
        "away_lineup_strength": away_strength,
        "lineup_strength_home": home_strength,
        "lineup_strength_away": away_strength,
        "home_goalkeeper_identified": _goalkeeper_present(home_lineup),
        "away_goalkeeper_identified": _goalkeeper_present(away_lineup),
        "key_absences_home": len(home_injuries or []),
        "key_absences_away": len(away_injuries or []),
        "injuries_impact_home": min(1.0, len(home_injuries or []) * 0.08) if home_injuries else 0.0,
        "injuries_impact_away": min(1.0, len(away_injuries or []) * 0.08) if away_injuries else 0.0,
        "formation_home": (home_lineup or {}).get("formation"),
        "formation_away": (away_lineup or {}).get("formation"),
        "lineup_available": bool(home_strength or away_strength),
    }


def _xg_missing_reason(
    *,
    sm_id: int | None,
    configured: bool,
    http_error: str | None,
    parsed: dict[str, Any],
) -> str | None:
    if parsed.get("available"):
        return None
    if sm_id is None:
        return "fixture_not_mapped"
    if not configured:
        return "subscription_missing"
    if http_error:
        if "401" in http_error or "403" in http_error:
            return "subscription_missing"
        if "404" in http_error:
            return "provider_no_data"
        return "endpoint_error"
    return "provider_no_data"


def _fetch_sm_payload(
    provider: SportmonksProvider,
    sm_id: int,
    *,
    max_api_calls: int,
    api_calls: int,
    use_premium_includes: bool = True,
) -> tuple[dict[str, Any] | None, str, int, bool, str | None]:
    cache_path = _sm_cache_path(sm_id)
    if cache_path.is_file():
        try:
            blob = json.loads(cache_path.read_text(encoding="utf-8"))
            payload = blob.get("payload") or blob
            return payload, "cache", api_calls, True, None
        except (json.JSONDecodeError, OSError):
            pass
    if api_calls >= max_api_calls:
        return None, "api_budget", api_calls, False, "api_budget_exhausted"
    includes = _XG_INCLUDES if use_premium_includes else _FALLBACK_INCLUDES
    status, payload, error = provider.safe_get(f"/fixtures/{sm_id}", params={"include": includes})
    api_calls += 1
    if error or not isinstance(payload, dict) or not payload.get("data"):
        if use_premium_includes:
            return _fetch_sm_payload(provider, sm_id, max_api_calls=max_api_calls, api_calls=api_calls, use_premium_includes=False)
        return None, "error", api_calls, False, error
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {"sportmonks_fixture_id": sm_id, "fetched_at": _utc_now(), "payload": payload},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return payload, "live", api_calls, False, None


def _fixture_already_imported(repo: FootballIntelligenceRepository, api_id: int, sm_id: int) -> bool:
    if _sm_cache_path(sm_id).is_file():
        return True
    if repo.has_xg_snapshot(api_id):
        row = repo.get_fixture_enrichment_row(api_id)
        if row and row.get("lineups_json"):
            return True
    return False


def import_sportmonks_xg_lineups(
    mappings: list[dict[str, Any]],
    *,
    settings: Settings | None = None,
    max_api_calls: int = 120,
    resume: bool = True,
    progress_every: int = 5,
    checkpoint_path: str | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    provider = SportmonksProvider(settings)
    configured = bool(getattr(provider, "is_configured", False))

    ckpt = load_checkpoint(checkpoint_path or PROGRESS_CHECKPOINT_PATH)
    if ckpt.get("status") == "completed" and resume:
        log_progress("[phase62b] checkpoint status=completed; use --no-resume to force full rerun")
    ckpt["status"] = "running"
    save_checkpoint(ckpt, checkpoint_path)

    api_calls = int(ckpt.get("api_calls_used") or 0)
    cache_hits = int(ckpt.get("cache_hits") or 0)
    xg_saved = 0
    lineup_saved = 0
    skipped = 0
    skipped_cached = int(ckpt.get("skipped_cached_count") or 0)
    success_count = int(ckpt.get("success_count") or 0)
    failed_count = int(ckpt.get("failed_count") or 0)
    xg_found = int(ckpt.get("xg_found") or 0)
    xg_missing = int(ckpt.get("xg_missing") or 0)
    lineups_found = int(ckpt.get("lineups_found") or 0)
    lineups_missing = int(ckpt.get("lineups_missing") or 0)
    errors: list[str] = []

    total = len(mappings)
    started = time.monotonic()
    processed = 0

    for row in mappings:
        api_id = int(row.get("api_football_fixture_id") or row.get("fixture_id") or 0)
        sm_id = int(row.get("sportmonks_fixture_id") or 0)
        if api_id <= 0 or sm_id <= 0:
            skipped += 1
            continue

        if resume and (is_fixture_complete(ckpt, api_id) or _fixture_already_imported(repo, api_id, sm_id)):
            skipped_cached += 1
            mark_fixture_complete(ckpt, api_id)
            processed += 1
            if processed % progress_every == 0:
                log_fixture_progress(
                    fixture_id=api_id,
                    sportmonks_id=sm_id,
                    processed=processed,
                    total=total,
                    api_calls=api_calls,
                    cache_hits=cache_hits,
                    xg_found=xg_found,
                    xg_missing=xg_missing,
                    lineups_found=lineups_found,
                    lineups_missing=lineups_missing,
                    errors=failed_count,
                    started_at=started,
                )
            continue

        fx = repo._conn.execute(
            "SELECT home_team, away_team FROM fixtures WHERE fixture_id = ?",
            (api_id,),
        ).fetchone()
        home = str(fx[0] or "") if fx else ""
        away = str(fx[1] or "") if fx else ""

        payload_wrap, source, api_calls, from_cache, http_error = _fetch_sm_payload(
            provider, sm_id, max_api_calls=max_api_calls, api_calls=api_calls
        )
        if from_cache:
            cache_hits += 1
        if not payload_wrap:
            skipped += 1
            failed_count += 1
            errors.append(f"{api_id}:fetch_failed:{http_error or source}"[:120])
            processed += 1
            ckpt.update(
                {
                    "last_fixture_id": api_id,
                    "processed_count": processed,
                    "failed_count": failed_count,
                    "api_calls_used": api_calls,
                    "cache_hits": cache_hits,
                    "skipped_cached_count": skipped_cached,
                }
            )
            save_checkpoint(ckpt, checkpoint_path)
            continue

        raw = payload_wrap.get("data") if isinstance(payload_wrap.get("data"), dict) else payload_wrap
        if not isinstance(raw, dict):
            skipped += 1
            continue

        parsed_xg = parse_sportmonks_xg_match(raw)
        team_xg = parsed_xg.get("team") or {}
        missing = _xg_missing_reason(
            sm_id=sm_id, configured=configured, http_error=http_error, parsed=parsed_xg
        )
        xg_block = {
            "home_xg": team_xg.get("home_xg"),
            "away_xg": team_xg.get("away_xg"),
            "home_xgot": team_xg.get("home_xgot"),
            "away_xgot": team_xg.get("away_xgot"),
            "home_npxg": team_xg.get("home_npxg"),
            "away_npxg": team_xg.get("away_npxg"),
            "player_xg_summary": parsed_xg.get("player_xg_summary"),
            "xg_timeline": team_xg.get("timeline"),
            "xg_source": parsed_xg.get("source") or source,
            "xg_freshness": _utc_now(),
            "xg_available": bool(parsed_xg.get("available")),
            "xg_missing_reason": missing,
            "sportmonks_fixture_id": sm_id,
        }

        if xg_block["xg_available"] and not repo.has_xg_snapshot(api_id):
            repo.save_snapshot(
                "xg_snapshots",
                fixture_id=api_id,
                competition_key=WORLD_CUP_COMPETITION_KEY,
                payload=xg_block,
            )
            xg_saved += 1
        if xg_block["xg_available"]:
            xg_found += 1
        else:
            xg_missing += 1

        norm = normalize_sportmonks_fixture(raw, home_team_name=home, away_team_name=away)
        lineups_api = norm.get("lineups_api") or []
        home_lu = lineups_api[0] if lineups_api else None
        away_lu = lineups_api[1] if len(lineups_api) > 1 else None
        lineup_feats = _normalize_lineup_features(
            home_lineup=home_lu,
            away_lineup=away_lu,
            home_injuries=norm.get("home_injuries") or [],
            away_injuries=norm.get("away_injuries") or [],
        )
        if not lineup_feats["lineup_available"]:
            lineup_feats["lineup_missing_reason"] = (
                "provider_no_data" if configured else "subscription_missing"
            )
        else:
            lineup_feats["lineup_missing_reason"] = None
        if lineup_feats["lineup_available"]:
            lineups_found += 1
        else:
            lineups_missing += 1

        repo._conn.execute(
            """
            INSERT INTO fixture_enrichment(fixture_id, competition_key, lineups_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                lineups_json=excluded.lineups_json,
                updated_at=excluded.updated_at
            """,
            (
                api_id,
                WORLD_CUP_COMPETITION_KEY,
                json.dumps(lineups_api, default=str),
                _utc_now(),
            ),
        )
        lineup_saved += 1

        save_raw_with_fallback(
            settings=settings,
            provider="sportmonks",
            resource_type="fixture_enrichment",
            fixture_id=api_id,
            payload_json={"xg": xg_block, "lineups": lineup_feats, "raw_meta": {"sm_id": sm_id}},
            request_endpoint=f"/fixtures/{sm_id}",
            request_params={"include": _XG_INCLUDES},
            source=source,
            sportmonks_fixture_id=sm_id,
            competition_key=WORLD_CUP_COMPETITION_KEY,
            league_id=SPORTMONKS_LEAGUE_ID,
        )

        try:
            records = normalize_fixture_xg_records(raw, sportmonks_fixture_id=sm_id)
            if records:
                summary = build_fixture_summary_from_records(records)
                if summary:
                    xg_block["feature_store_summary"] = summary
        except Exception:
            pass

        success_count += 1
        mark_fixture_complete(ckpt, api_id)
        processed += 1
        ckpt.update(
            {
                "last_fixture_id": api_id,
                "processed_count": processed,
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_cached_count": skipped_cached,
                "api_calls_used": api_calls,
                "cache_hits": cache_hits,
                "xg_found": xg_found,
                "xg_missing": xg_missing,
                "lineups_found": lineups_found,
                "lineups_missing": lineups_missing,
                "status": "running",
            }
        )
        if processed % progress_every == 0 or processed == total:
            save_checkpoint(ckpt, checkpoint_path)
            log_fixture_progress(
                fixture_id=api_id,
                sportmonks_id=sm_id,
                processed=processed,
                total=total,
                api_calls=api_calls,
                cache_hits=cache_hits,
                xg_found=xg_found,
                xg_missing=xg_missing,
                lineups_found=lineups_found,
                lineups_missing=lineups_missing,
                errors=failed_count,
                started_at=started,
            )
            sys.stdout.flush()

    repo._conn.commit()
    ckpt["status"] = "completed"
    save_checkpoint(ckpt, checkpoint_path)
    total_calls = max(1, api_calls)
    return {
        "status": "ok",
        "configured": configured,
        "mappings_processed": len(mappings),
        "xg_saved": xg_saved,
        "lineup_saved": lineup_saved,
        "skipped": skipped,
        "skipped_cached": skipped_cached,
        "success_count": success_count,
        "failed_count": failed_count,
        "xg_found": xg_found,
        "xg_missing": xg_missing,
        "lineups_found": lineups_found,
        "lineups_missing": lineups_missing,
        "checkpoint": str(checkpoint_path or PROGRESS_CHECKPOINT_PATH),
        "api_calls": api_calls,
        "cache_hits": cache_hits,
        "cache_hit_ratio": round(cache_hits / total, 4),
        "errors": errors[:20],
    }
