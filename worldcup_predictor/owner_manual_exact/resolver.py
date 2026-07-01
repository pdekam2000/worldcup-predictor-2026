"""Part A — Resolve manual owner match list to internal fixtures."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner_manual_exact.constants import ARTIFACTS_DIR, DEFAULT_TIMEZONE, PHASE, with_safety_labels
from worldcup_predictor.owner_manual_exact.fixture_import import import_knockout_fixtures, save_import_audit
from worldcup_predictor.owner_manual_exact.manual_matches import MANUAL_MATCH_LIST
from worldcup_predictor.owner_manual_exact.team_aliases import (
    canonical_team_name,
    known_fixture_id,
    normalize_for_match,
    score_fixture_pair,
    teams_match,
)

_EXCLUDED_STATUSES = frozenset(
    {"FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "PST", "POSTP", "POSTPONED", "CANCELLED", "ABANDONED", "FINISHED"}
)
_KICKOFF_WINDOW_HOURS = 6.0
_FUZZY_MIN_SCORE = 0.90


def _date_tag(d: date) -> str:
    return d.isoformat().replace("-", "")


def _next_weekday(base: date, weekday: int) -> date:
    delta = (weekday - base.weekday()) % 7
    if delta == 0:
        delta = 7
    return base + timedelta(days=delta)


def parse_kickoff_label(label: str, *, process_date: date, tz_name: str = DEFAULT_TIMEZONE) -> dict[str, Any]:
    tz = ZoneInfo(tz_name)
    text = (label or "").strip().lower()
    hm = re.search(r"(\d{1,2})[.:](\d{2})", text)
    hour, minute = (int(hm.group(1)), int(hm.group(2))) if hm else (18, 0)

    target_day = process_date
    if re.search(r"\b05\.07\.|\b5\.07\.", text):
        target_day = date(process_date.year, 7, 5)
    elif "samstag" in text:
        target_day = _next_weekday(process_date, 5)
    elif "freitag" in text:
        target_day = _next_weekday(process_date, 4)
    elif "morgen" in text:
        target_day = process_date + timedelta(days=1)
    elif "heute" in text:
        target_day = process_date

    local_dt = datetime.combine(target_day, time(hour, minute), tzinfo=tz)
    utc_dt = local_dt.astimezone(timezone.utc)
    return {
        "kickoff_label": label,
        "kickoff_local": local_dt.isoformat(),
        "kickoff_utc": utc_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "kickoff_date": target_day.isoformat(),
        "timezone": tz_name,
    }


def _fetch_candidate_fixtures(conn: sqlite3.Connection, *, from_date: str = "2026-06-25", to_date: str = "2026-07-10") -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key
        FROM fixtures
        WHERE competition_key = 'world_cup_2026'
          AND kickoff_utc >= ?
          AND kickoff_utc < ?
        ORDER BY kickoff_utc
        """,
        (from_date, to_date),
    ).fetchall()
    return [dict(r) for r in rows]


def _parse_utc(kickoff: str | None) -> datetime | None:
    if not kickoff:
        return None
    try:
        return datetime.fromisoformat(str(kickoff).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _closest_candidates(
    home_input: str,
    away_input: str,
    candidates: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in candidates:
        score = score_fixture_pair(home_input, away_input, row["home_team"], row["away_team"])
        scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, row in scored[:limit]:
        out.append(
            {
                "fixture_id": row["fixture_id"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "kickoff_utc": row.get("kickoff_utc"),
                "status": row.get("status"),
                "match_score": round(score, 4),
            }
        )
    return out


def resolve_fixture(
    conn: sqlite3.Connection,
    match: dict[str, Any],
    *,
    kickoff_meta: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    home_input = match["home_team"]
    away_input = match["away_team"]
    home_canon = canonical_team_name(home_input)
    away_canon = canonical_team_name(away_input)
    home_norm = normalize_for_match(home_input)
    away_norm = normalize_for_match(away_input)
    target_utc = _parse_utc(kickoff_meta.get("kickoff_utc"))

    # 1) Known API fixture ID map
    kid = known_fixture_id(home_input, away_input)
    if kid:
        row = conn.execute(
            """
            SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key
            FROM fixtures WHERE fixture_id = ? LIMIT 1
            """,
            (int(kid),),
        ).fetchone()
        if row:
            r = dict(row)
            return {
                "resolution_status": "RESOLVED",
                "resolution_method": "known_fixture_id_map",
                "fixture_id": int(r["fixture_id"]),
                "home_team_canonical": r["home_team"],
                "away_team_canonical": r["away_team"],
                "kickoff_utc": r.get("kickoff_utc"),
                "competition_key": r.get("competition_key"),
                "match_status": r.get("status"),
                "kickoff_delta_hours": 0.0,
            }

    best: dict[str, Any] | None = None
    best_score = 0.0
    best_delta = timedelta(hours=9999)

    for row in candidates:
        status = str(row.get("status") or "").upper()
        if status in _EXCLUDED_STATUSES:
            continue
        pair_score = score_fixture_pair(home_input, away_input, row["home_team"], row["away_team"])
        if pair_score < _FUZZY_MIN_SCORE:
            continue
        kick = _parse_utc(row.get("kickoff_utc"))
        if target_utc and kick:
            delta = abs(kick - target_utc)
            if delta > timedelta(hours=_KICKOFF_WINDOW_HOURS):
                continue
        else:
            delta = timedelta(hours=1)
        combined = pair_score - (delta.total_seconds() / 86400) * 0.05
        if combined > best_score or (combined == best_score and delta < best_delta):
            best_score = combined
            best_delta = delta
            best = row

    if best:
        return {
            "resolution_status": "RESOLVED",
            "resolution_method": "team_alias_fuzzy_kickoff",
            "fixture_id": int(best["fixture_id"]),
            "home_team_canonical": best["home_team"],
            "away_team_canonical": best["away_team"],
            "kickoff_utc": best.get("kickoff_utc"),
            "competition_key": best.get("competition_key"),
            "match_status": best.get("status"),
            "kickoff_delta_hours": round(best_delta.total_seconds() / 3600, 2),
            "match_score": round(best_score, 4),
        }

    closest = _closest_candidates(home_input, away_input, candidates)
    reject_reasons: list[str] = []
    if not closest:
        reject_reasons.append("no_db_candidates_in_date_window")
    elif (closest[0].get("match_score") or 0) < _FUZZY_MIN_SCORE:
        reject_reasons.append(f"best_fuzzy_score_below_threshold_{_FUZZY_MIN_SCORE}")
    if target_utc:
        reject_reasons.append(f"kickoff_window_{_KICKOFF_WINDOW_HOURS}h_not_matched")

    return {
        "resolution_status": "MANUAL_ONLY",
        "fixture_id": None,
        "home_team_canonical": home_canon,
        "away_team_canonical": away_canon,
        "home_normalized": home_norm,
        "away_normalized": away_norm,
        "note": "No matching internal fixture after import",
        "reject_reasons": reject_reasons,
        "closest_candidates": closest,
    }


def resolve_manual_match_list(
    *,
    process_date: date | None = None,
    timezone: str = DEFAULT_TIMEZONE,
    settings: Settings | None = None,
    auto_import: bool = True,
) -> dict[str, Any]:
    settings = settings or get_settings()
    process_date = process_date or date.today()

    import_audit: dict[str, Any] | None = None
    if auto_import:
        imp = import_knockout_fixtures(settings=settings)
        import_path = save_import_audit(imp, process_date=process_date)
        import_audit = imp.to_dict()
        import_audit["artifact_path"] = str(import_path)

    conn = connect(settings.sqlite_path)
    candidates = _fetch_candidate_fixtures(conn)

    resolved_rows: list[dict[str, Any]] = []
    for match in MANUAL_MATCH_LIST:
        kickoff_meta = parse_kickoff_label(match["kickoff_label"], process_date=process_date, tz_name=timezone)
        resolution = resolve_fixture(conn, match, kickoff_meta=kickoff_meta, candidates=candidates)
        resolved_rows.append(
            {
                "match_no": match["match_no"],
                "home_team_input": match["home_team"],
                "away_team_input": match["away_team"],
                "kickoff": kickoff_meta,
                "odds_1x2": match["odds_1x2"],
                "btts_odds": match["btts"],
                "resolution": resolution,
            }
        )
    conn.close()

    resolved_count = sum(1 for r in resolved_rows if r["resolution"]["resolution_status"] == "RESOLVED")
    out = with_safety_labels(
        {
            "phase": PHASE,
            "process_date": process_date.isoformat(),
            "timezone": timezone,
            "match_count": len(resolved_rows),
            "resolved_count": resolved_count,
            "manual_only_count": len(resolved_rows) - resolved_count,
            "import_audit": import_audit,
            "matches": resolved_rows,
        }
    )
    path = ARTIFACTS_DIR / f"manual_owner_match_resolution_{_date_tag(process_date)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    out["artifact_path"] = str(path)
    return out


def load_resolution_artifact(process_date: date) -> dict[str, Any] | None:
    path = ARTIFACTS_DIR / f"manual_owner_match_resolution_{_date_tag(process_date)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
