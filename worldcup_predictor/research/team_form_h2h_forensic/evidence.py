"""Prematch evidence loading — cache-first, no fabrication."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.intelligence.national_team.h2h_engine import build_h2h_detail
from worldcup_predictor.research.last8_team_form.profile_builder import build_team_last8_goal_profile


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _venue_form_from_profile(profile: dict[str, Any], *, venue: str) -> dict[str, Any]:
    matches = profile.get("matches") or []
    if venue == "home":
        filtered = [m for m in matches if m.get("is_home")]
    else:
        filtered = [m for m in matches if not m.get("is_home")]
    n = len(filtered)
    if n == 0:
        return {"matches_found": 0, "coverage_status": "unavailable"}
    scored = sum(1 for m in filtered if int(m.get("goals_for") or 0) > 0)
    conceded = sum(1 for m in filtered if int(m.get("goals_against") or 0) > 0)
    clean = sum(1 for m in filtered if int(m.get("goals_against") or 0) == 0)
    btts = sum(
        1
        for m in filtered
        if int(m.get("goals_for") or 0) > 0 and int(m.get("goals_against") or 0) > 0
    )
    over25 = sum(1 for m in filtered if int(m.get("goals_for") or 0) + int(m.get("goals_against") or 0) > 2)
    return {
        "matches_found": n,
        "wins": sum(
            1 for m in filtered if int(m.get("goals_for") or 0) > int(m.get("goals_against") or 0)
        ),
        "draws": sum(
            1 for m in filtered if int(m.get("goals_for") or 0) == int(m.get("goals_against") or 0)
        ),
        "losses": sum(
            1 for m in filtered if int(m.get("goals_for") or 0) < int(m.get("goals_against") or 0)
        ),
        "avg_goals_scored": round(sum(int(m.get("goals_for") or 0) for m in filtered) / n, 3),
        "avg_goals_conceded": round(sum(int(m.get("goals_against") or 0) for m in filtered) / n, 3),
        "scored_in_rate": round(scored / n, 4),
        "conceded_in_rate": round(conceded / n, 4),
        "clean_sheet_rate": round(clean / n, 4),
        "btts_rate": round(btts / n, 4),
        "over_2_5_rate": round(over25 / n, 4),
        "coverage_status": "partial" if n < 5 else "ok",
    }


def _h2h_from_db(
    repo: FootballIntelligenceRepository,
    *,
    home_team: str,
    away_team: str,
    before_kickoff: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = repo._conn.execute(
        """
        SELECT f.fixture_id, f.kickoff_utc, f.competition_key, f.home_team, f.away_team,
               r.home_goals, r.away_goals
        FROM fixtures f
        INNER JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.is_placeholder = 0
          AND f.kickoff_utc < ?
          AND f.status IN ('FT', 'AET', 'PEN', 'FINISHED')
          AND ((f.home_team = ? AND f.away_team = ?) OR (f.home_team = ? AND f.away_team = ?))
        ORDER BY f.kickoff_utc DESC
        LIMIT ?
        """,
        (before_kickoff, home_team, away_team, away_team, home_team, int(limit)),
    ).fetchall()
    meetings = []
    for row in rows:
        item = dict(row)
        meetings.append(
            {
                "fixture": {"date": item.get("kickoff_utc"), "id": item.get("fixture_id")},
                "teams": {"home": {"name": item.get("home_team")}, "away": {"name": item.get("away_team")}},
                "goals": {"home": item.get("home_goals"), "away": item.get("away_goals")},
                "league": {"name": item.get("competition_key")},
                "venue_orientation": "home" if item.get("home_team") == home_team else "away",
            }
        )
    return meetings


def _h2h_relevance(meetings: list[dict[str, Any]], *, competition: str) -> str:
    if not meetings:
        return "H2H_NOT_AVAILABLE"
    if len(meetings) >= 3:
        return "H2H_MEDIUM_RELEVANCE"
    return "H2H_LOW_RELEVANCE"


def _load_prematch_snapshots(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT feature_family, feature_name, provider, source_endpoint, fetched_at_utc,
               mapping_confidence, payload_json
        FROM prematch_feature_snapshots
        WHERE fixture_id = ?
        ORDER BY fetched_at_utc DESC
        """,
        (int(fixture_id),),
    ).fetchall()
    out: dict[str, Any] = {"families": {}, "provenance": []}
    for row in rows:
        fam = str(row["feature_family"])
        if fam in out["families"]:
            continue
        try:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        except json.JSONDecodeError:
            payload = {}
        out["families"][fam] = payload
        out["provenance"].append(
            {
                "feature_family": fam,
                "provider": row["provider"],
                "source_endpoint": row["source_endpoint"],
                "fetched_at": row["fetched_at_utc"],
                "mapping_confidence": row["mapping_confidence"],
            }
        )
    return out


def _load_frozen_prediction(eval_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = eval_conn.execute(
        "SELECT * FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at DESC LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return _load_frozen_from_daily_artifact(fixture_id)
    frozen = dict(row)
    ranks = [
        dict(r)
        for r in eval_conn.execute(
            "SELECT rank, score, probability FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
            (frozen["prediction_id"],),
        ).fetchall()
    ]
    frozen["rank_rows"] = ranks
    if not ranks or all(float(r.get("probability") or 0) <= 0 for r in ranks):
        artifact = _load_frozen_from_daily_artifact(fixture_id)
        if artifact:
            for key in ("rank_rows", "top5_mass", "wde_decision", "btts_prediction", "ou25_prediction"):
                if artifact.get(key) is not None:
                    frozen[key] = artifact[key]
    return frozen


def _load_frozen_from_daily_artifact(fixture_id: int) -> dict[str, Any] | None:
    """Read-only fallback to daily pipeline predictions when eval ranks lack probabilities."""
    from worldcup_predictor.config.env_loading import project_root
    from worldcup_predictor.owner_daily.pipeline.constants import PIPELINE_ARTIFACTS_ROOT

    root = PIPELINE_ARTIFACTS_ROOT
    if not root.is_absolute():
        root = project_root() / root
    candidates = sorted(root.glob("*/top3_rerun/all_predictions.json"), reverse=True)
    candidates += sorted(root.glob("*/all_predictions.json"), reverse=True)
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rows = payload if isinstance(payload, list) else payload.get("predictions") or []
        for item in rows:
            if int(item.get("fixture_id") or 0) != int(fixture_id):
                continue
            ecse = item.get("ecse") or {}
            rank_rows = []
            for i in range(1, 6):
                block = ecse.get(f"top{i}") or {}
                if not block.get("score"):
                    continue
                rank_rows.append(
                    {
                        "rank": int(block.get("rank") or i),
                        "score": block.get("score"),
                        "probability": float(block.get("probability") or 0),
                    }
                )
            if len(rank_rows) < 5:
                continue
            return {
                "fixture_id": fixture_id,
                "prediction_id": f"daily-artifact:{path.parent.name}:{fixture_id}",
                "wde_decision": item.get("wde_decision") or (item.get("wde") or {}).get("decision_pick"),
                "home_probability": item.get("home_probability"),
                "draw_probability": item.get("draw_probability"),
                "away_probability": item.get("away_probability"),
                "btts_prediction": (item.get("btts") or {}).get("prediction"),
                "ou25_prediction": (item.get("over_under_2_5") or {}).get("prediction"),
                "odds_home": item.get("home_odds"),
                "odds_draw": item.get("draw_odds"),
                "odds_away": item.get("away_odds"),
                "bookmaker_count": item.get("bookmaker_count"),
                "top5_mass": ecse.get("top5_mass"),
                "rank_rows": rank_rows,
                "source": str(path),
            }
    return None


def load_fixture_evidence(
    *,
    fixture_id: int,
    home_team: str,
    away_team: str,
    kickoff_utc: str,
    competition_key: str,
    prod_conn: sqlite3.Connection,
    eval_conn: sqlite3.Connection | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    provenance: list[dict[str, Any]] = []

    home_profile = build_team_last8_goal_profile(
        team_name=home_team,
        fixture_kickoff_utc=kickoff_utc,
        competition_context=competition_key,
        target_fixture_id=fixture_id,
        competition_keys=[competition_key] if competition_key else None,
        settings=settings,
    )
    provenance.append({"category": "home_recent_form", "source": "last8_team_form.profile_builder", "fallback_used": False})

    away_profile = build_team_last8_goal_profile(
        team_name=away_team,
        fixture_kickoff_utc=kickoff_utc,
        competition_context=competition_key,
        target_fixture_id=fixture_id,
        competition_keys=[competition_key] if competition_key else None,
        settings=settings,
    )
    provenance.append({"category": "away_recent_form", "source": "last8_team_form.profile_builder", "fallback_used": False})

    home_venue = _venue_form_from_profile(home_profile, venue="home")
    away_venue = _venue_form_from_profile(away_profile, venue="away")

    meetings = _h2h_from_db(
        repo, home_team=home_team, away_team=away_team, before_kickoff=kickoff_utc, limit=10
    )
    h2h_detail = build_h2h_detail(meetings, home_team_id=1, away_team_id=2) if meetings else {"meetings_used": 0}
    h2h_relevance = _h2h_relevance(meetings, competition=competition_key)
    if meetings:
        provenance.append({"category": "h2h", "source": "sqlite_fixtures_results", "fallback_used": False})
    else:
        provenance.append({"category": "h2h", "source": None, "fallback_used": False, "missing": True})

    snapshots = _load_prematch_snapshots(prod_conn, fixture_id)
    frozen = _load_frozen_prediction(eval_conn, fixture_id) if eval_conn else None
    if frozen and str(frozen.get("source") or "").endswith("all_predictions.json"):
        provenance.append(
            {
                "category": "frozen_prediction",
                "source": frozen.get("source"),
                "fallback_used": True,
            }
        )
    elif frozen:
        provenance.append({"category": "frozen_prediction", "source": "forward_evaluation.frozen_predictions", "fallback_used": False})

    fx_row = prod_conn.execute(
        "SELECT * FROM fixtures WHERE fixture_id=? LIMIT 1", (int(fixture_id),)
    ).fetchone()
    fixture_context = dict(fx_row) if fx_row else {}

    odds = {}
    if frozen:
        odds = {
            "home": frozen.get("odds_home"),
            "draw": frozen.get("odds_draw"),
            "away": frozen.get("odds_away"),
            "bookmaker_count": frozen.get("bookmaker_count"),
            "freshness": frozen.get("odds_freshness") or frozen.get("odds_freshness_status"),
        }

    return {
        "fixture_id": fixture_id,
        "home_team": home_team,
        "away_team": away_team,
        "kickoff_utc": kickoff_utc,
        "competition_key": competition_key,
        "home_profile": home_profile,
        "away_profile": away_profile,
        "home_venue_form": home_venue,
        "away_venue_form": away_venue,
        "h2h_meetings": meetings,
        "h2h_detail": h2h_detail,
        "h2h_relevance": h2h_relevance,
        "prematch_snapshots": snapshots,
        "frozen_prediction": frozen,
        "fixture_context": fixture_context,
        "odds": odds,
        "provenance": provenance,
        "loaded_at": _utc_now(),
    }
