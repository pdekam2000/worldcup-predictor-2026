"""PHASE EURO-A2 — UEFA fixture result provider matching (data repair only)."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Literal

from worldcup_predictor.integrations.fixture_api_parser import FINISHED_STATUSES

PHASE = "EURO-A2"
FUZZY_TEAM_THRESHOLD = 0.88
MIN_PERSIST_CONFIDENCE = 0.88
KICKOFF_WINDOW_HOURS = 3
HIGH_CONFIDENCE = 0.95

_TEAM_SUFFIX_RE = re.compile(
    r"\b(fc|fk|cf|sc|sk|ac|as|afc|bsc|sv|vfb|tsg|ud|cd|sd|rc|ssc|us|ss|bk|if|ff|ik)\b",
    re.IGNORECASE,
)

_FINISHED_DB_STATUSES = tuple(FINISHED_STATUSES) + ("FINISHED", "AWD", "WO", "COMPLETED")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def normalize_team_name(name: str | None) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = _TEAM_SUFFIX_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def parse_kickoff(kickoff_utc: str | None) -> datetime | None:
    if not kickoff_utc:
        return None
    raw = str(kickoff_utc).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        pass
    try:
        return datetime.strptime(str(kickoff_utc)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def kickoff_delta_hours(a: str | None, b: str | None) -> float | None:
    da = parse_kickoff(a)
    db = parse_kickoff(b)
    if not da or not db:
        return None
    return abs((da - db).total_seconds()) / 3600.0


def team_similarity(a: str | None, b: str | None) -> float:
    na = normalize_team_name(a)
    nb = normalize_team_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    return SequenceMatcher(None, na, nb).ratio()


def teams_exact(home: str, away: str, item_home: str, item_away: str) -> bool:
    return normalize_team_name(home) == normalize_team_name(item_home) and normalize_team_name(
        away
    ) == normalize_team_name(item_away)


def teams_fuzzy_score(home: str, away: str, item_home: str, item_away: str) -> float:
    h = team_similarity(home, item_home)
    a = team_similarity(away, item_away)
    return min(h, a)


def teams_fuzzy_match(home: str, away: str, item_home: str, item_away: str) -> bool:
    return teams_fuzzy_score(home, away, item_home, item_away) >= FUZZY_TEAM_THRESHOLD


def item_has_goals(item: dict[str, Any]) -> bool:
    goals = item.get("goals") or {}
    return goals.get("home") is not None and goals.get("away") is not None


def api_item_teams(item: dict[str, Any]) -> tuple[str, str]:
    teams = item.get("teams") or {}
    home = str((teams.get("home") or {}).get("name") or "")
    away = str((teams.get("away") or {}).get("name") or "")
    return home, away


def api_item_fixture_id(item: dict[str, Any]) -> int | None:
    try:
        fid = int((item.get("fixture") or {}).get("id") or 0)
        return fid if fid > 0 else None
    except (TypeError, ValueError):
        return None


def api_item_kickoff(item: dict[str, Any]) -> str | None:
    return str((item.get("fixture") or {}).get("date") or "") or None


def outcome_source_tag(
    *,
    provider: str,
    provider_fixture_id: int,
    confidence: float,
    method: str,
) -> str:
    return f"euro_a2|{provider}|{provider_fixture_id}|{confidence:.3f}|{method}"


@dataclass
class ProviderMatch:
    provider: Literal["api-football", "sportmonks", "cache"]
    provider_fixture_id: int
    method: str
    confidence: float
    item: dict[str, Any]
    api_calls: int = 0
    ambiguous: bool = False
    candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def persistable(self) -> bool:
        return (
            not self.ambiguous
            and self.confidence >= MIN_PERSIST_CONFIDENCE
            and self.item is not None
        )


@dataclass
class FeedIndex:
    by_provider_id: dict[tuple[str, str, int], dict[str, Any]] = field(default_factory=dict)
    api_by_date_teams: dict[tuple[str, str, str, str], list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    sportmonks_by_date_teams: dict[tuple[str, str, str, str], list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    @classmethod
    def build(cls, conn: sqlite3.Connection, competition_keys: tuple[str, ...]) -> FeedIndex:
        idx = cls()
        placeholders = ",".join("?" for _ in competition_keys)
        rows = conn.execute(
            f"""
            SELECT fixture_id, provider, provider_fixture_id, competition_key,
                   home_team, away_team, kickoff_utc, status, raw_payload_ref
            FROM euro_fixture_feed
            WHERE competition_key IN ({placeholders})
            """,
            competition_keys,
        ).fetchall()
        for row in rows:
            d = dict(row)
            provider = str(d["provider"])
            pid = int(d["provider_fixture_id"])
            comp = str(d["competition_key"])
            idx.by_provider_id[(comp, provider, pid)] = d
            kick = str(d.get("kickoff_utc") or "")[:10]
            ht = normalize_team_name(str(d.get("home_team")))
            at = normalize_team_name(str(d.get("away_team")))
            key = (comp, kick, ht, at)
            if provider == "api-football":
                idx.api_by_date_teams[key].append(d)
            elif provider == "sportmonks":
                idx.sportmonks_by_date_teams[key].append(d)
        return idx


def infer_provider_source(row: dict[str, Any], feed_index: FeedIndex) -> str:
    comp = str(row["competition_key"])
    fid = int(row["fixture_id"])
    if (comp, "api-football", fid) in feed_index.by_provider_id:
        return "api-football"
    if (comp, "sportmonks", fid) in feed_index.by_provider_id:
        return "sportmonks"
    src = str(row.get("source") or "").lower()
    if "sportmonks" in src:
        return "sportmonks"
    if "api" in src or "historical" in src:
        return "api-football"
    if fid > 10_000_000:
        return "sportmonks"
    return src or "unknown"


def load_raw_payload(conn: sqlite3.Connection, ref: str | None) -> dict[str, Any] | None:
    if not ref:
        return None
    row = conn.execute(
        "SELECT payload_json FROM euro_fixture_raw_payload WHERE ref = ?",
        (ref,),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def load_file_payload(path_str: str) -> dict[str, Any] | None:
    from pathlib import Path

    path = Path(path_str)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def sportmonks_item_teams(item: dict[str, Any]) -> tuple[str, str]:
    home = away = ""
    for participant in item.get("participants") or []:
        if not isinstance(participant, dict):
            continue
        loc = str((participant.get("meta") or {}).get("location") or "").lower()
        name = str(participant.get("name") or "")
        if loc == "home":
            home = name
        elif loc == "away":
            away = name
    if not home or not away:
        blob = str(item.get("name") or "")
        if " vs " in blob.lower():
            parts = blob.split(" vs ", 1)
            home, away = parts[0].strip(), parts[1].strip()
    return home, away


def sportmonks_has_scores(item: dict[str, Any]) -> bool:
    from worldcup_predictor.mbi.outcomes import _scores_from_sportmonks_data

    h, a = _scores_from_sportmonks_data(item)
    return h is not None and a is not None


def sportmonks_to_api_shape(item: dict[str, Any], *, provider_fixture_id: int) -> dict[str, Any] | None:
    from worldcup_predictor.mbi.outcomes import _scores_from_sportmonks_data

    home_goals, away_goals = _scores_from_sportmonks_data(item)
    if home_goals is None or away_goals is None:
        return None
    home, away = sportmonks_item_teams(item)
    kickoff = str(item.get("starting_at") or item.get("starting_at_timestamp") or "")
    status = "FT"
    state = item.get("state") or {}
    if isinstance(state, dict):
        short = str(state.get("short_name") or state.get("state") or "").upper()
        if short:
            status = short
    return {
        "fixture": {"id": provider_fixture_id, "date": kickoff, "status": {"short": status}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": home_goals, "away": away_goals},
        "score": {},
    }


def score_api_candidates(
    row: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    method_prefix: str,
    require_goals: bool = True,
) -> list[ProviderMatch]:
    home = str(row.get("home_team") or "")
    away = str(row.get("away_team") or "")
    kickoff = str(row.get("kickoff_utc") or "")
    date_part = kickoff[:10]
    matches: list[ProviderMatch] = []

    for item in items:
        if require_goals and not item_has_goals(item):
            continue
        ih, ia = api_item_teams(item)
        fid = api_item_fixture_id(item) or 0
        item_kick = api_item_kickoff(item) or ""
        delta_h = kickoff_delta_hours(kickoff, item_kick)

        if teams_exact(home, away, ih, ia):
            if item_kick[:10] == date_part:
                conf = 0.98
                method = f"{method_prefix}_date_exact_teams"
            elif delta_h is not None and delta_h <= KICKOFF_WINDOW_HOURS:
                conf = 0.95
                method = f"{method_prefix}_window_exact_teams"
            else:
                continue
        else:
            fuzzy = teams_fuzzy_score(home, away, ih, ia)
            if fuzzy < FUZZY_TEAM_THRESHOLD:
                continue
            if delta_h is None or delta_h > KICKOFF_WINDOW_HOURS:
                if item_kick[:10] != date_part:
                    continue
                conf = fuzzy * 0.95
                method = f"{method_prefix}_date_fuzzy_teams"
            else:
                conf = fuzzy * 0.97
                method = f"{method_prefix}_window_fuzzy_teams"
            if conf < MIN_PERSIST_CONFIDENCE:
                continue

        matches.append(
            ProviderMatch(
                provider="api-football",
                provider_fixture_id=fid,
                method=method,
                confidence=conf,
                item=item,
            )
        )
    return matches


def pick_best_match(matches: list[ProviderMatch]) -> ProviderMatch | None:
    if not matches:
        return None
    matches = sorted(matches, key=lambda m: (-m.confidence, m.method))
    best = matches[0]
    if len(matches) > 1 and matches[1].confidence >= best.confidence - 0.02:
        best.ambiguous = True
        best.candidates = [
            {
                "provider_fixture_id": m.provider_fixture_id,
                "confidence": m.confidence,
                "method": m.method,
            }
            for m in matches[:5]
        ]
    return best


def lookup_feed_api_id(row: dict[str, Any], feed_index: FeedIndex) -> int | None:
    comp = str(row["competition_key"])
    kick = str(row.get("kickoff_utc") or "")[:10]
    ht = normalize_team_name(str(row.get("home_team")))
    at = normalize_team_name(str(row.get("away_team")))
    exact = feed_index.api_by_date_teams.get((comp, kick, ht, at)) or []
    if len(exact) == 1:
        return int(exact[0]["provider_fixture_id"])
    if len(exact) > 1:
        return None
    # scan ±3h across feed api rows for same comp/date
    candidates: list[dict[str, Any]] = []
    for key, rows in feed_index.api_by_date_teams.items():
        if key[0] != comp or key[1] != kick:
            continue
        for feed_row in rows:
            if teams_fuzzy_match(
                str(row.get("home_team")),
                str(row.get("away_team")),
                str(feed_row.get("home_team")),
                str(feed_row.get("away_team")),
            ):
                dh = kickoff_delta_hours(str(row.get("kickoff_utc")), str(feed_row.get("kickoff_utc")))
                if dh is not None and dh <= KICKOFF_WINDOW_HOURS:
                    candidates.append(feed_row)
    if len(candidates) == 1:
        return int(candidates[0]["provider_fixture_id"])
    return None


def list_missing_uefa_fixtures(
    conn: sqlite3.Connection,
    competition_key: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    placeholders = ",".join("?" for _ in _FINISHED_DB_STATUSES)
    query = f"""
        SELECT f.fixture_id, f.competition_key, f.home_team, f.away_team,
               f.kickoff_utc, f.status, f.league_id, f.season, f.source
        FROM fixtures f
        LEFT JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.competition_key = ?
          AND f.is_placeholder = 0
          AND UPPER(COALESCE(f.status, '')) IN ({placeholders})
          AND r.fixture_id IS NULL
          AND f.kickoff_utc IS NOT NULL
          AND f.kickoff_utc < ?
        ORDER BY f.kickoff_utc DESC
    """
    params: list[Any] = [competition_key, *_FINISHED_DB_STATUSES, now]
    if limit is not None:
        query += " LIMIT ?"
        params.append(int(limit))
    return [dict(r) for r in conn.execute(query, params).fetchall()]
