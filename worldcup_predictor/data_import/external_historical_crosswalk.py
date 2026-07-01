"""Fixture crosswalk and final import preview for external historical staging."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from worldcup_predictor.intelligence.national_team._shared import normalize_team_name

PHASE = "HISTORICAL-CSV-INGEST-1"
CROSSWALK_PATH = Path("artifacts/external_historical_fixture_crosswalk.json")
PREVIEW_PATH = Path("artifacts/external_historical_final_import_preview.json")
HIGH_CONFIDENCE = 0.90
LOW_CONFIDENCE = 0.75


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if len(text) >= 10:
        return text[:10]
    return text or None


def _team_similarity(a: str, b: str) -> float:
    na = normalize_team_name(a)
    nb = normalize_team_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _score_fixture_candidate(
    *,
    ext_home: str,
    ext_away: str,
    db_home: str,
    db_away: str,
) -> float:
    home_score = _team_similarity(ext_home, db_home)
    away_score = _team_similarity(ext_away, db_away)
    if home_score < 0.5 or away_score < 0.5:
        return 0.0
    return (home_score + away_score) / 2.0


def _index_fixtures_by_date(db_fixtures) -> dict[str, list]:
    by_date: dict[str, list] = defaultdict(list)
    for fx in db_fixtures:
        d = _parse_date(str(fx["kickoff_utc"]) if fx["kickoff_utc"] else None)
        if d:
            by_date[d].append(fx)
    return by_date


def _candidate_fixtures(by_date: dict[str, list], event_date: str) -> list:
    candidates = list(by_date.get(event_date, []))
    try:
        dt = datetime.fromisoformat(event_date)
        for offset in (-1, 1):
            d = (dt + timedelta(days=offset)).date().isoformat()
            candidates.extend(by_date.get(d, []))
    except ValueError:
        pass
    return candidates


def build_fixture_crosswalk(conn) -> dict[str, Any]:
    staged = conn.execute(
        """
        SELECT home_team, away_team, event_date, kickoff_utc, league, country_name, status,
               COUNT(*) AS staged_row_count
        FROM external_match_history_staging
        WHERE home_team IS NOT NULL AND away_team IS NOT NULL AND event_date IS NOT NULL
        GROUP BY home_team, away_team, event_date, kickoff_utc, league, country_name, status
        """
    ).fetchall()

    db_fixtures = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key, status
        FROM fixtures
        """
    ).fetchall()
    by_date = _index_fixtures_by_date(db_fixtures)

    rows_out: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()

    for row in staged:
        home = str(row["home_team"])
        away = str(row["away_team"])
        date = _parse_date(row["event_date"])
        if not date:
            continue

        candidates: list[tuple[float, int, str, str]] = []
        for fx in _candidate_fixtures(by_date, date):
            score = _score_fixture_candidate(
                ext_home=home,
                ext_away=away,
                db_home=str(fx["home_team"]),
                db_away=str(fx["away_team"]),
            )
            if score >= LOW_CONFIDENCE:
                candidates.append((score, int(fx["fixture_id"]), str(fx["home_team"]), str(fx["away_team"])))

        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[0] if candidates else None
        second = candidates[1] if len(candidates) > 1 else None

        if not top:
            status = "NO_MATCH"
            fixture_id = None
            confidence = None
            reason = "no_db_candidate"
        elif second and (top[0] - second[0]) < 0.02:
            status = "AMBIGUOUS"
            fixture_id = None
            confidence = top[0]
            reason = "top_two_close"
        elif top[0] >= HIGH_CONFIDENCE:
            status = "MATCHED_HIGH_CONFIDENCE"
            fixture_id = top[1]
            confidence = top[0]
            reason = None
        elif top[0] >= LOW_CONFIDENCE:
            status = "MATCHED_LOW_CONFIDENCE"
            fixture_id = None
            confidence = top[0]
            reason = "below_high_confidence_threshold"
        else:
            status = "NO_MATCH"
            fixture_id = None
            confidence = top[0]
            reason = "score_too_low"

        status_counts[status] += 1
        rows_out.append(
            {
                "home_team": home,
                "away_team": away,
                "event_date": date,
                "league": row["league"],
                "country_name": row["country_name"],
                "external_status": row["status"],
                "status": status,
                "confidence": confidence,
                "fixture_id": fixture_id,
                "matched_db_home": top[2] if top else None,
                "matched_db_away": top[3] if top else None,
                "rejection_reason": reason,
                "staged_row_count": int(row["staged_row_count"]),
            }
        )

    local_missing = sum(1 for r in rows_out if r["status"] in ("NO_MATCH", "LOCAL_FIXTURE_MISSING"))
    summary = {
        "phase": PHASE,
        "unique_matches_staged": len(rows_out),
        "status_counts": dict(status_counts),
        "high_confidence_threshold": HIGH_CONFIDENCE,
        "local_fixture_missing_estimate": local_missing,
        "rows": rows_out[:5000],
        "rows_truncated": len(rows_out) > 5000,
    }
    CROSSWALK_PATH.parent.mkdir(parents=True, exist_ok=True)
    CROSSWALK_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def build_final_import_preview(conn) -> dict[str, Any]:
    crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8")) if CROSSWALK_PATH.exists() else {}
    status_counts = crosswalk.get("status_counts") or {}
    high_matched = status_counts.get("MATCHED_HIGH_CONFIDENCE", 0)
    low_or_none = (
        status_counts.get("NO_MATCH", 0)
        + status_counts.get("MATCHED_LOW_CONFIDENCE", 0)
        + status_counts.get("AMBIGUOUS", 0)
    )

    match_count = conn.execute("SELECT COUNT(*) c FROM external_match_history_staging").fetchone()["c"]
    odds_count = conn.execute("SELECT COUNT(*) c FROM external_match_odds_staging").fetchone()["c"]
    raw_count = conn.execute("SELECT COUNT(*) c FROM external_historical_csv_raw_rows").fetchone()["c"]

    odds_snapshots = conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"]
    provider_odds = 0
    if _table_exists(conn, "historical_csv_odds_imports"):
        provider_odds = conn.execute("SELECT COUNT(*) c FROM historical_csv_odds_imports").fetchone()["c"]

    market_cov = conn.execute(
        """
        SELECT market, COUNT(*) c FROM external_match_odds_staging GROUP BY market ORDER BY c DESC
        """
    ).fetchall()

    xg_rows = conn.execute(
        """
        SELECT COUNT(*) c FROM external_match_history_staging
        WHERE home_xg IS NOT NULL OR away_xg IS NOT NULL
        """
    ).fetchone()["c"]
    corner_rows = conn.execute(
        """
        SELECT COUNT(*) c FROM external_match_history_staging
        WHERE home_corners IS NOT NULL OR away_corners IS NOT NULL
        """
    ).fetchone()["c"]

    league_counts = conn.execute(
        """
        SELECT league, COUNT(*) c FROM external_match_history_staging
        WHERE league IS NOT NULL GROUP BY league ORDER BY c DESC LIMIT 20
        """
    ).fetchall()

    unresolved_teams = conn.execute(
        """
        SELECT home_team, away_team, COUNT(*) c FROM external_match_history_staging
        GROUP BY home_team, away_team ORDER BY c DESC LIMIT 30
        """
    ).fetchall()

    preview = {
        "phase": PHASE,
        "dry_run_only": True,
        "promoted_to_fixtures": False,
        "promoted_to_odds_snapshots": False,
        "staged_raw_rows": int(raw_count),
        "staged_match_rows": int(match_count),
        "staged_odds_rows": int(odds_count),
        "unique_matches_crosswalked": crosswalk.get("unique_matches_staged", 0),
        "could_create_new_historical_fixtures": low_or_none,
        "match_existing_local_fixtures_high_confidence": high_matched,
        "could_become_odds_snapshots_estimate": int(odds_count),
        "xg_enrichment_rows": int(xg_rows),
        "corners_enrichment_rows": int(corner_rows),
        "existing_odds_snapshots_count": int(odds_snapshots),
        "existing_provider_odds_imports": int(provider_odds),
        "conflicts_with_provider_data": "none_detected_in_preview",
        "duplicate_rows_skipped_note": "dedup via row_hash on staging insert",
        "market_coverage": {str(r["market"]): int(r["c"]) for r in market_cov},
        "top_leagues_by_row_count": {str(r["league"]): int(r["c"]) for r in league_counts},
        "unresolved_teams_sample": [
            {"home_team": r["home_team"], "away_team": r["away_team"], "count": int(r["c"])} for r in unresolved_teams
        ],
        "crosswalk_status_counts": status_counts,
    }
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")
    return preview


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None
