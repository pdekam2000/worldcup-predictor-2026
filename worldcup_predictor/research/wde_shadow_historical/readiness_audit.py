"""Part A — Historical CSV training readiness audit (staging tables only)."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from worldcup_predictor.data_import.external_historical_zip_importer import IMPORT_SUMMARY_PATH, PROFILE_PATH
from worldcup_predictor.research.wde_shadow_historical.constants import (
    CHUNK_SIZE,
    FT_ODDS_COLUMNS,
    PHASE,
    READINESS_ARTIFACT,
    READINESS_REPORT,
)
from worldcup_predictor.research.wde_shadow_historical.helpers import (
    crosswalk_summary,
    is_future_event,
    is_played_status,
    load_raw_row,
    parse_float,
    parse_int,
    table_count,
    table_exists,
    team_alias_collision_count,
)


@dataclass
class ReadinessAuditResult:
    phase: str = PHASE
    audited_at_utc: str = ""
    staged_match_rows: int = 0
    staged_odds_rows: int = 0
    date_range: dict[str, str | None] = field(default_factory=dict)
    countries: dict[str, int] = field(default_factory=dict)
    leagues: dict[str, int] = field(default_factory=dict)
    completed_matches_with_final_score: int = 0
    rows_with_complete_ft_1x2_odds: int = 0
    rows_with_complete_ou25_odds: int = 0
    rows_with_complete_btts_odds: int = 0
    rows_with_xg: int = 0
    rows_with_corners: int = 0
    duplicate_match_candidates: int = 0
    invalid_odds_rows: int = 0
    missing_teams: int = 0
    team_alias_issues: dict[str, Any] = field(default_factory=dict)
    league_alias_issues: dict[str, Any] = field(default_factory=dict)
    usable_rows: dict[str, int] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    readiness: str = "DO_NOT_TRAIN_YET"

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "audited_at_utc": self.audited_at_utc,
            "staged_match_rows": self.staged_match_rows,
            "staged_odds_rows": self.staged_odds_rows,
            "date_range": self.date_range,
            "countries": self.countries,
            "leagues": self.leagues,
            "completed_matches_with_final_score": self.completed_matches_with_final_score,
            "rows_with_complete_ft_1x2_odds": self.rows_with_complete_ft_1x2_odds,
            "rows_with_complete_ou25_odds": self.rows_with_complete_ou25_odds,
            "rows_with_complete_btts_odds": self.rows_with_complete_btts_odds,
            "rows_with_xg": self.rows_with_xg,
            "rows_with_corners": self.rows_with_corners,
            "duplicate_match_candidates": self.duplicate_match_candidates,
            "invalid_odds_rows": self.invalid_odds_rows,
            "missing_teams": self.missing_teams,
            "team_alias_issues": self.team_alias_issues,
            "league_alias_issues": self.league_alias_issues,
            "usable_rows": self.usable_rows,
            "blockers": self.blockers,
            "readiness": self.readiness,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_import_summary() -> dict[str, Any]:
    if not IMPORT_SUMMARY_PATH.exists():
        return {}
    try:
        return json.loads(IMPORT_SUMMARY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_zip_profile() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        return {}
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _iter_match_chunks(conn: sqlite3.Connection, chunk_size: int = CHUNK_SIZE) -> Iterator[list[sqlite3.Row]]:
    if not table_exists(conn, "external_match_history_staging"):
        return
    last_id = 0
    while True:
        rows = conn.execute(
            """
            SELECT id, row_hash, source_file, league, country_name, home_team, away_team,
                   status, event_date, event_hour, kickoff_utc,
                   home_ft_goals, away_ft_goals, home_xg, away_xg,
                   home_corners, away_corners, home_penalties, away_penalties,
                   raw_row_json
            FROM external_match_history_staging
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (last_id, chunk_size),
        ).fetchall()
        if not rows:
            break
        last_id = int(rows[-1]["id"])
        yield rows


def _odds_complete(raw: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        val = parse_float(raw.get(key))
        if val is None or val <= 1.0:
            return False
    return True


def _row_usable_flags(row: sqlite3.Row, raw: dict[str, Any]) -> dict[str, bool]:
    hg = parse_int(row["home_ft_goals"])
    ag = parse_int(row["away_ft_goals"])
    status = row["status"]
    event_date = row["event_date"]
    home = str(row["home_team"] or "").strip()
    away = str(row["away_team"] or "").strip()

    if not home or not away:
        return {"played": False, "score": False, "future": True}
    if is_future_event(event_date):
        return {"played": False, "score": False, "future": True}
    if hg is None or ag is None:
        return {"played": False, "score": False, "future": False}

    played = not is_future_event(event_date)
    if not played:
        return {"played": False, "score": False, "future": True}

    has_1x2 = _odds_complete(raw, ("oddsFT_1", "oddsFT_X", "oddsFT_2"))
    has_ou = _odds_complete(raw, ("oddsFT_Over_2_5", "oddsFT_Under_2_5"))
    has_btts = _odds_complete(raw, ("oddsFT_BTTS_Yes", "oddsFT_BTTS_No"))
    has_xg = row["home_xg"] is not None or row["away_xg"] is not None
    has_corners = row["home_corners"] is not None or row["away_corners"] is not None

    return {
        "played": True,
        "score": True,
        "future": False,
        "wde_1x2": has_1x2,
        "wde_ou25": has_ou,
        "wde_btts": has_btts,
        "odds_baseline": has_1x2,
        "xg_enhanced": has_xg and has_1x2,
        "xg": has_xg,
        "corners": has_corners,
    }


def audit_training_readiness(conn: sqlite3.Connection) -> ReadinessAuditResult:
    result = ReadinessAuditResult(audited_at_utc=_utc_now())
    result.staged_match_rows = table_count(conn, "external_match_history_staging")
    result.staged_odds_rows = table_count(conn, "external_match_odds_staging")

    if result.staged_match_rows == 0:
        summary = _load_import_summary()
        profile = _load_zip_profile()
        if summary.get("match_rows_staged"):
            result.staged_match_rows = int(summary["match_rows_staged"])
            result.staged_odds_rows = int(summary.get("odds_rows_staged") or 0)
            result.date_range = {
                "min": profile.get("min_event_date"),
                "max": profile.get("max_event_date"),
            }
            result.blockers.append("staging_empty_local_db_use_server_or_reimport")
            result.readiness = "NEED_TEAM_ALIAS_MAPPING"
            result.usable_rows = {
                "wde_1x2": result.staged_match_rows,
                "note": "estimated_from_import_summary_artifact",
            }
            return result
        result.blockers.append("no_staged_match_rows")
        result.readiness = "DO_NOT_TRAIN_YET"
        return result

    date_row = conn.execute(
        """
        SELECT MIN(event_date) AS min_d, MAX(event_date) AS max_d
        FROM external_match_history_staging
        WHERE event_date IS NOT NULL AND event_date != ''
        """
    ).fetchone()
    result.date_range = {
        "min": date_row["min_d"] if date_row else None,
        "max": date_row["max_d"] if date_row else None,
    }

    country_rows = conn.execute(
        """
        SELECT country_name, COUNT(*) c FROM external_match_history_staging
        WHERE country_name IS NOT NULL AND country_name != ''
        GROUP BY country_name ORDER BY c DESC LIMIT 30
        """
    ).fetchall()
    result.countries = {str(r["country_name"]): int(r["c"]) for r in country_rows}

    league_rows = conn.execute(
        """
        SELECT league, COUNT(*) c FROM external_match_history_staging
        WHERE league IS NOT NULL AND league != ''
        GROUP BY league ORDER BY c DESC LIMIT 30
        """
    ).fetchall()
    result.leagues = {str(r["league"]): int(r["c"]) for r in league_rows}

    dup_row = conn.execute(
        """
        SELECT COUNT(*) c FROM (
            SELECT home_team, away_team, event_date, COUNT(*) n
            FROM external_match_history_staging
            WHERE home_team IS NOT NULL AND away_team IS NOT NULL AND event_date IS NOT NULL
            GROUP BY home_team, away_team, event_date
            HAVING n > 1
        )
        """
    ).fetchone()
    result.duplicate_match_candidates = int(dup_row["c"] or 0)

    if table_exists(conn, "external_match_odds_staging"):
        inv = conn.execute(
            """
            SELECT COUNT(*) c FROM external_match_odds_staging
            WHERE odds IS NULL OR odds <= 1
               OR implied_probability IS NULL OR implied_probability <= 0 OR implied_probability > 1
            """
        ).fetchone()
        result.invalid_odds_rows = int(inv["c"] or 0)

    missing = conn.execute(
        """
        SELECT COUNT(*) c FROM external_match_history_staging
        WHERE home_team IS NULL OR home_team = '' OR away_team IS NULL OR away_team = ''
        """
    ).fetchone()
    result.missing_teams = int(missing["c"] or 0)

    collision_count, collision_samples = team_alias_collision_count(conn)
    cw = crosswalk_summary()
    cw_status = cw.get("status_counts") or {}
    result.team_alias_issues = {
        "internal_normalized_collisions": collision_count,
        "collision_samples": collision_samples[:10],
        "crosswalk_no_match": int(cw_status.get("NO_MATCH", 0)),
        "crosswalk_high_confidence": int(cw_status.get("MATCHED_HIGH_CONFIDENCE", 0)),
        "crosswalk_low_confidence": int(cw_status.get("MATCHED_LOW_CONFIDENCE", 0)),
        "note": "Crosswalk NO_MATCH is expected for historical-only rows; internal collisions affect model quality",
    }

    league_variants = conn.execute(
        """
        SELECT league, country_name, COUNT(*) c FROM external_match_history_staging
        WHERE league IS NOT NULL GROUP BY league, country_name ORDER BY c DESC LIMIT 50
        """
    ).fetchall()
    league_codes = Counter()
    for r in league_variants:
        league_codes[str(r["league"])] += 1
    multi_country_leagues = [lg for lg, cnt in league_codes.items() if cnt > 3]
    result.league_alias_issues = {
        "distinct_leagues": len(result.leagues),
        "leagues_spanning_many_countries": multi_country_leagues[:15],
        "note": "League codes like EN1/SP1 are stable within export; mapping to competition_key is separate",
    }

    usable = Counter()
    for chunk in _iter_match_chunks(conn):
        for row in chunk:
            raw = load_raw_row(row["raw_row_json"])
            flags = _row_usable_flags(row, raw)
            if flags.get("future"):
                continue
            if flags.get("score"):
                result.completed_matches_with_final_score += 1
            if _odds_complete(raw, ("oddsFT_1", "oddsFT_X", "oddsFT_2")):
                result.rows_with_complete_ft_1x2_odds += 1
            if _odds_complete(raw, ("oddsFT_Over_2_5", "oddsFT_Under_2_5")):
                result.rows_with_complete_ou25_odds += 1
            if _odds_complete(raw, ("oddsFT_BTTS_Yes", "oddsFT_BTTS_No")):
                result.rows_with_complete_btts_odds += 1
            if flags.get("xg"):
                result.rows_with_xg += 1
            if flags.get("corners"):
                result.rows_with_corners += 1
            if flags.get("wde_1x2") and flags.get("score"):
                usable["wde_1x2"] += 1
            if flags.get("wde_ou25") and flags.get("score"):
                usable["wde_ou25"] += 1
            if flags.get("wde_btts") and flags.get("score"):
                usable["wde_btts"] += 1
            if flags.get("odds_baseline") and flags.get("score"):
                usable["odds_only_baseline"] += 1
            if flags.get("xg_enhanced") and flags.get("score"):
                usable["xg_enhanced_model"] += 1

    result.usable_rows = dict(usable)
    result.blockers = _derive_blockers(result)
    result.readiness = _derive_readiness(result)
    return result


def _derive_blockers(result: ReadinessAuditResult) -> list[str]:
    blockers: list[str] = []
    if result.staged_match_rows == 0:
        blockers.append("no_staged_data")
    if result.missing_teams > 0:
        blockers.append(f"missing_teams:{result.missing_teams}")
    if result.team_alias_issues.get("internal_normalized_collisions", 0) > 100:
        blockers.append("high_internal_team_alias_collisions")
    if result.duplicate_match_candidates > 1000:
        blockers.append(f"duplicate_match_groups:{result.duplicate_match_candidates}")
    if result.usable_rows.get("wde_1x2", 0) < 5_000:
        blockers.append("insufficient_usable_wde_1x2_rows")
    if result.invalid_odds_rows > 0:
        blockers.append(f"invalid_odds_in_staging:{result.invalid_odds_rows}")
    return blockers


def _derive_readiness(result: ReadinessAuditResult) -> str:
    if result.staged_match_rows == 0:
        return "DO_NOT_TRAIN_YET"
    if result.missing_teams > 0:
        return "NEED_TEAM_ALIAS_MAPPING"
    usable_1x2 = result.usable_rows.get("wde_1x2", 0)
    if usable_1x2 < 1_000:
        return "DO_NOT_TRAIN_YET"
    if result.team_alias_issues.get("internal_normalized_collisions", 0) > 500:
        return "NEED_TEAM_ALIAS_MAPPING"
    if len(result.league_alias_issues.get("leagues_spanning_many_countries") or []) > 10:
        return "NEED_LEAGUE_MAPPING"
    if result.duplicate_match_candidates > 5_000 or result.invalid_odds_rows > 10_000:
        return "NEED_DATA_CLEANING"
    if usable_1x2 >= 5_000:
        return "READY_FOR_SHADOW_TRAINING"
    return "NEED_DATA_CLEANING"


def write_readiness_outputs(result: ReadinessAuditResult) -> None:
    READINESS_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    READINESS_ARTIFACT.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Historical CSV Training Readiness Report",
        "",
        f"**Phase:** {PHASE}",
        f"**Audited:** {result.audited_at_utc}",
        f"**Readiness:** `{result.readiness}`",
        "",
        "## Staging inventory",
        "",
        f"- Match rows: **{result.staged_match_rows:,}**",
        f"- Odds rows: **{result.staged_odds_rows:,}**",
        f"- Date range: **{result.date_range.get('min')}** → **{result.date_range.get('max')}**",
        f"- Countries (top): {len(result.countries)} sampled in report",
        f"- Leagues (top): {len(result.leagues)} sampled in report",
        "",
        "## Match quality",
        "",
        f"- Completed matches with final score: **{result.completed_matches_with_final_score:,}**",
        f"- Complete FT 1X2 odds: **{result.rows_with_complete_ft_1x2_odds:,}**",
        f"- Complete O/U 2.5 odds: **{result.rows_with_complete_ou25_odds:,}**",
        f"- Complete BTTS odds: **{result.rows_with_complete_btts_odds:,}**",
        f"- Rows with xG: **{result.rows_with_xg:,}**",
        f"- Rows with corners: **{result.rows_with_corners:,}**",
        f"- Duplicate match groups: **{result.duplicate_match_candidates:,}**",
        f"- Invalid odds rows (odds staging): **{result.invalid_odds_rows:,}**",
        f"- Missing team names: **{result.missing_teams:,}**",
        "",
        "## Usable rows for shadow training",
        "",
    ]
    for key, val in sorted(result.usable_rows.items()):
        lines.append(f"- {key}: **{val:,}**")

    lines.extend(
        [
            "",
            "## Team alias issues",
            "",
            f"- Internal normalized collisions: **{result.team_alias_issues.get('internal_normalized_collisions', 0)}**",
            f"- Crosswalk NO_MATCH (local DB): **{result.team_alias_issues.get('crosswalk_no_match', 0)}**",
            f"- Crosswalk high confidence: **{result.team_alias_issues.get('crosswalk_high_confidence', 0)}**",
            "",
            "## League alias issues",
            "",
            f"- Distinct leagues (top sample): **{result.league_alias_issues.get('distinct_leagues', 0)}**",
            "",
            "## Blockers",
            "",
        ]
    )
    if result.blockers:
        for b in result.blockers:
            lines.append(f"- {b}")
    else:
        lines.append("- None critical")

    lines.extend(["", f"Artifact: `{READINESS_ARTIFACT}`", ""])
    READINESS_REPORT.write_text("\n".join(lines), encoding="utf-8")
