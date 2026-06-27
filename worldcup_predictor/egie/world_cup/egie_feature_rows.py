"""Persist EGIE feature rows for World Cup fixtures (feature snapshots only)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import postgres_configured
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.world_cup.config import RAW_CACHE_DIR, WORLD_CUP_COMPETITION_KEY
from worldcup_predictor.egie.world_cup.wc_feature_builder import build_wc_timing_features
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository

logger = logging.getLogger(__name__)


def build_egie_feature_rows(
    *,
    settings: Settings | None = None,
    limit: int = 600,
) -> dict[str, Any]:
    """Build and persist goal_timing_features for WC fixtures — no prediction engine run."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    stored = StoredGoalTimingAdapter(settings)
    gt_repo = None
    if postgres_configured(settings):
        try:
            from sqlalchemy import text
            from worldcup_predictor.database.postgres.session import session_scope

            with session_scope(settings) as sess:
                sess.execute(text("SELECT 1"))
            gt_repo = GoalTimingRepository(settings)
        except Exception as exc:
            logger.warning("postgres_probe_failed, using file cache: %s", exc)
    skip_provider = gt_repo is None
    feature_cache = Path.cwd() / RAW_CACHE_DIR / "goal_timing_features"
    feature_cache.mkdir(parents=True, exist_ok=True)

    rows = repo._conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc
        FROM fixtures WHERE competition_key = ?
        ORDER BY kickoff_utc DESC LIMIT ?
        """,
        (WORLD_CUP_COMPETITION_KEY, int(limit)),
    ).fetchall()

    saved = 0
    file_only = 0
    errors = 0
    for r in rows:
        fid = int(r[0])
        home, away, kickoff = str(r[1] or ""), str(r[2] or ""), r[3]
        try:
            kickoff_dt = stored.parse_kickoff(kickoff) if kickoff else None
            ctx = {"home_team": home, "away_team": away, "match_date": kickoff_dt}
            features = build_wc_timing_features(
                fid,
                competition_key=WORLD_CUP_COMPETITION_KEY,
                stored=stored,
                as_of=kickoff_dt,
                context=ctx,
                skip_provider=skip_provider,
            )
            if gt_repo is not None:
                try:
                    gt_repo.save_feature_snapshot(
                        fixture_id=fid,
                        as_of=features.get("as_of") or datetime.now(timezone.utc).isoformat(),
                        features=features,
                        source_manifest=features.get("provider_manifest") or {},
                        competition_key=WORLD_CUP_COMPETITION_KEY,
                    )
                    saved += 1
                    continue
                except Exception as exc:
                    logger.debug("pg_feature_save_failed %s: %s", fid, exc)
            (feature_cache / f"{fid}.json").write_text(
                json.dumps(features, indent=2, default=str),
                encoding="utf-8",
            )
            file_only += 1
        except Exception as exc:
            logger.debug("feature_row_failed %s: %s", fid, exc)
            errors += 1

    return {
        "status": "ok",
        "saved": saved,
        "file_only": file_only,
        "errors": errors,
        "attempted": len(rows),
        "postgres_configured": gt_repo is not None,
    }
