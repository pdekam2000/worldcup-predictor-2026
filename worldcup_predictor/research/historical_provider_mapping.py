"""PHASE MAP-1 — Historical provider mapping engine (read-only matching, no API)."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterator

from worldcup_predictor.data_import.historical_csv_odds import _norm_team, build_fixture_index, match_fixture
from worldcup_predictor.data_import.historical_fixture_registry import _norm_league
from worldcup_predictor.providers.sportmonks_fixture_lookup import team_names_match

PHASE = "MAP-1"
METHOD_VERSION = "MAP-1-v1"
TABLE_NAME = "historical_provider_mapping"

PROVIDER_API_FOOTBALL = "api_football"
PROVIDER_SPORTMONKS = "sportmonks"
PROVIDER_ODDALERTS = "oddalerts"
PROVIDERS = (PROVIDER_API_FOOTBALL, PROVIDER_SPORTMONKS, PROVIDER_ODDALERTS)

SPORTMONKS_CACHE_DIRS = (
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/egie/uefa_club/raw"),
)

FUZZY_TEAM_THRESHOLD = 0.88
DATETIME_TOLERANCE_MINUTES = 1

DDL: tuple[str, ...] = (
    f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        registry_fixture_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        provider_fixture_id INTEGER NOT NULL,
        confidence_score REAL NOT NULL,
        match_method TEXT NOT NULL,
        kickoff_delta_minutes INTEGER,
        league_match INTEGER NOT NULL DEFAULT 0,
        season_match INTEGER NOT NULL DEFAULT 0,
        score_validated INTEGER NOT NULL DEFAULT 0,
        ambiguous_flag INTEGER NOT NULL DEFAULT 0,
        candidate_count INTEGER NOT NULL DEFAULT 1,
        build_batch TEXT NOT NULL,
        method_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(registry_fixture_id, provider),
        FOREIGN KEY (registry_fixture_id) REFERENCES historical_fixture_registry(registry_fixture_id)
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS idx_historical_provider_mapping_provider
    ON {TABLE_NAME}(provider, provider_fixture_id)
    """,
    f"""
    CREATE INDEX IF NOT EXISTS idx_historical_provider_mapping_registry
    ON {TABLE_NAME}(registry_fixture_id)
    """,
)


@dataclass
class ProviderCandidate:
    provider: str
    provider_fixture_id: int
    kickoff_utc: str | None
    match_date: str
    home_team: str
    away_team: str
    home_team_normalized: str
    away_team_normalized: str
    league_normalized: str
    season: str
    home_goals: int | None = None
    away_goals: int | None = None
    source: str = ""


@dataclass
class MatchResult:
    candidate: ProviderCandidate
    confidence_score: float
    match_method: str
    kickoff_delta_minutes: int | None
    league_match: bool
    season_match: bool
    score_validated: bool
    ambiguous_flag: bool
    candidate_count: int


@dataclass
class MappingBuildStats:
    registry_rows_scanned: int = 0
    mappings_inserted: int = 0
    mappings_updated: int = 0
    mappings_skipped_existing: int = 0
    by_provider: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)
    ambiguous_count: int = 0
    unmatched_count: int = 0
    build_batch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_rows_scanned": self.registry_rows_scanned,
            "mappings_inserted": self.mappings_inserted,
            "mappings_updated": self.mappings_updated,
            "mappings_skipped_existing": self.mappings_skipped_existing,
            "by_provider": self.by_provider,
            "by_method": self.by_method,
            "ambiguous_count": self.ambiguous_count,
            "unmatched_count": self.unmatched_count,
            "build_batch": self.build_batch,
            "method_version": METHOD_VERSION,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _build_batch_id() -> str:
    return f"MAP-1-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


def ensure_historical_provider_mapping_table(conn: sqlite3.Connection) -> None:
    for ddl in DDL:
        conn.execute(ddl)
    conn.commit()


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(text[:19] if "T" not in fmt else text[:25], fmt)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    if len(text) >= 10:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return None


def _kickoff_delta_minutes(a: str | None, b: str | None) -> int | None:
    da = _parse_kickoff(a)
    db = _parse_kickoff(b)
    if not da or not db:
        return None
    return int(abs((da - db).total_seconds()) // 60)


def _datetime_exact(a: str | None, b: str | None) -> bool:
    delta = _kickoff_delta_minutes(a, b)
    return delta is not None and delta <= DATETIME_TOLERANCE_MINUTES


def _teams_exact(reg: dict[str, Any], cand: ProviderCandidate) -> bool:
    return (
        reg["home_team_normalized"] == cand.home_team_normalized
        and reg["away_team_normalized"] == cand.away_team_normalized
    )


def _teams_fuzzy(reg: dict[str, Any], cand: ProviderCandidate) -> bool:
    if _teams_exact(reg, cand):
        return True
    if team_names_match(reg["home_team"], cand.home_team) and team_names_match(
        reg["away_team"], cand.away_team
    ):
        return True
    h_ratio = SequenceMatcher(None, reg["home_team_normalized"], cand.home_team_normalized).ratio()
    a_ratio = SequenceMatcher(None, reg["away_team_normalized"], cand.away_team_normalized).ratio()
    return h_ratio >= FUZZY_TEAM_THRESHOLD and a_ratio >= FUZZY_TEAM_THRESHOLD


def _league_match(reg: dict[str, Any], cand: ProviderCandidate) -> bool:
    reg_lg = _norm_league(reg.get("league_normalized") or reg.get("league"))
    cand_lg = _norm_league(cand.league_normalized)
    if not reg_lg or reg_lg == "unknown":
        return False
    if reg_lg == cand_lg:
        return True
    return reg_lg in cand_lg or cand_lg in reg_lg


def _season_match(reg: dict[str, Any], cand: ProviderCandidate) -> bool:
    rs = str(reg.get("season") or "").strip()
    cs = str(cand.season or "").strip()
    if not rs or not cs:
        return False
    return rs == cs or rs in cs or cs in rs


def _score_match(reg: dict[str, Any], cand: ProviderCandidate) -> bool:
    rh, ra = reg.get("home_goals"), reg.get("away_goals")
    if rh is None or ra is None:
        return False
    if cand.home_goals is None or cand.away_goals is None:
        return False
    return int(rh) == int(cand.home_goals) and int(ra) == int(cand.away_goals)


def _date_team_key(match_date: str, home_norm: str, away_norm: str) -> str:
    return f"{match_date[:10]}|{home_norm}|{away_norm}"


def _index_candidates(candidates: list[ProviderCandidate]) -> tuple[dict[str, list[ProviderCandidate]], dict[str, list[ProviderCandidate]]]:
    exact: dict[str, list[ProviderCandidate]] = defaultdict(list)
    by_date: dict[str, list[ProviderCandidate]] = defaultdict(list)
    for c in candidates:
        exact[_date_team_key(c.match_date, c.home_team_normalized, c.away_team_normalized)].append(c)
        by_date[c.match_date[:10]].append(c)
    return exact, by_date


def _score_candidate(reg: dict[str, Any], cand: ProviderCandidate) -> MatchResult | None:
    reg_kickoff = reg.get("kickoff_utc") or reg.get("match_date")
    cand_kickoff = cand.kickoff_utc or cand.match_date
    dt_exact = _datetime_exact(reg_kickoff, cand_kickoff)
    team_exact = _teams_exact(reg, cand)
    team_fuzzy = _teams_fuzzy(reg, cand)
    if not team_fuzzy:
        return None

    lg = _league_match(reg, cand)
    sn = _season_match(reg, cand)
    sc = _score_match(reg, cand)
    delta = _kickoff_delta_minutes(reg_kickoff, cand_kickoff)

    if team_exact and dt_exact and sc:
        conf, method = 1.0, "exact_datetime_teams_score"
    elif team_exact and dt_exact:
        conf, method = 0.98, "exact_datetime_teams"
    elif team_exact and sc and lg:
        conf, method = 0.96, "exact_date_teams_score"
    elif team_exact and lg and sn:
        conf, method = 0.95, "exact_date_teams_league_season"
    elif team_exact and lg:
        conf, method = 0.92, "exact_date_teams_league"
    elif team_exact:
        conf, method = 0.88, "exact_date_teams"
    elif team_fuzzy and dt_exact:
        conf, method = 0.85, "exact_datetime_fuzzy_teams"
    elif team_fuzzy and lg:
        conf, method = 0.82, "fuzzy_date_teams_league"
    elif team_fuzzy:
        conf, method = 0.78, "fuzzy_date_teams"
    else:
        return None

    if sc:
        conf = min(1.0, conf + 0.02)
    return MatchResult(
        candidate=cand,
        confidence_score=round(conf, 4),
        match_method=method,
        kickoff_delta_minutes=delta,
        league_match=lg,
        season_match=sn,
        score_validated=sc,
        ambiguous_flag=False,
        candidate_count=1,
    )


def _pick_best_match(reg: dict[str, Any], candidates: list[ProviderCandidate]) -> MatchResult | None:
    scored: list[MatchResult] = []
    for cand in candidates:
        hit = _score_candidate(reg, cand)
        if hit:
            scored.append(hit)
    if not scored:
        return None
    scored.sort(key=lambda x: x.confidence_score, reverse=True)
    best = scored[0]
    if len(scored) > 1 and scored[1].confidence_score >= best.confidence_score - 0.02:
        best.ambiguous_flag = True
        best.candidate_count = len(scored)
        best.match_method = "ambiguous_multiple_candidates"
        best.confidence_score = round(min(best.confidence_score, 0.65), 4)
    return best


def _load_registry_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            r.registry_fixture_id,
            r.match_date,
            r.league,
            r.league_normalized,
            r.season,
            r.home_team,
            r.away_team,
            r.home_team_normalized,
            r.away_team_normalized,
            r.kickoff_utc,
            r.internal_fixture_id,
            res.home_goals,
            res.away_goals
        FROM historical_fixture_registry r
        LEFT JOIN historical_fixture_results res
            ON res.registry_fixture_id = r.registry_fixture_id
        ORDER BY r.registry_fixture_id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _competition_to_league_normalized(competition_key: str | None) -> str:
    key = (competition_key or "unknown").replace("_", " ")
    return _norm_league(key)


def build_api_football_candidates(conn: sqlite3.Connection) -> list[ProviderCandidate]:
    out: list[ProviderCandidate] = []
    rows = conn.execute(
        """
        SELECT
            f.fixture_id,
            f.home_team,
            f.away_team,
            f.kickoff_utc,
            f.competition_key,
            f.season,
            fr.home_goals,
            fr.away_goals
        FROM fixtures f
        LEFT JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
        WHERE f.is_placeholder = 0 AND f.kickoff_utc IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        kickoff = row["kickoff_utc"] or ""
        out.append(
            ProviderCandidate(
                provider=PROVIDER_API_FOOTBALL,
                provider_fixture_id=int(row["fixture_id"]),
                kickoff_utc=kickoff,
                match_date=kickoff[:10],
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                home_team_normalized=_norm_team(row["home_team"]),
                away_team_normalized=_norm_team(row["away_team"]),
                league_normalized=_competition_to_league_normalized(row["competition_key"]),
                season=str(row["season"] or ""),
                home_goals=row["home_goals"],
                away_goals=row["away_goals"],
                source="fixtures",
            )
        )
    return out


def _participants_from_sm_payload(data: dict[str, Any]) -> tuple[str, str, str, str]:
    home_name = away_name = ""
    for p in data.get("participants") or []:
        if not isinstance(p, dict):
            continue
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        name = str(p.get("name") or "")
        if loc == "home":
            home_name = name
        elif loc == "away":
            away_name = name
    league = ""
    lg = data.get("league")
    if isinstance(lg, dict):
        league = str(lg.get("name") or "")
    return home_name, away_name, league, str(data.get("starting_at") or "")


def build_sportmonks_candidates(conn: sqlite3.Connection) -> list[ProviderCandidate]:
    seen: set[int] = set()
    out: list[ProviderCandidate] = []

    def add(sm_id: int, *, home: str, away: str, kickoff: str, league: str, season: str, source: str, hg=None, ag=None):
        if sm_id in seen or not home or not away:
            return
        seen.add(sm_id)
        md = kickoff[:10] if kickoff else ""
        if len(md) < 10:
            return
        out.append(
            ProviderCandidate(
                provider=PROVIDER_SPORTMONKS,
                provider_fixture_id=sm_id,
                kickoff_utc=kickoff,
                match_date=md,
                home_team=home,
                away_team=away,
                home_team_normalized=_norm_team(home),
                away_team_normalized=_norm_team(away),
                league_normalized=_norm_league(league),
                season=season,
                home_goals=hg,
                away_goals=ag,
                source=source,
            )
        )

    for row in conn.execute(
        """
        SELECT e.sportmonks_fixture_id, e.fixture_id_api_football, f.home_team, f.away_team,
               f.kickoff_utc, f.competition_key, f.season, fr.home_goals, fr.away_goals
        FROM sportmonks_fixture_enrichment e
        LEFT JOIN fixtures f ON f.fixture_id = e.fixture_id_api_football
        LEFT JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
        """
    ):
        add(
            int(row["sportmonks_fixture_id"]),
            home=str(row["home_team"] or ""),
            away=str(row["away_team"] or ""),
            kickoff=str(row["kickoff_utc"] or ""),
            league=str(row["competition_key"] or ""),
            season=str(row["season"] or ""),
            source="sportmonks_fixture_enrichment",
            hg=row["home_goals"],
            ag=row["away_goals"],
        )

    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wc_fixture_mapping'"
    ).fetchone():
        for row in conn.execute(
            """
            SELECT m.sportmonks_fixture_id, f.home_team, f.away_team, f.kickoff_utc,
                   f.competition_key, f.season, fr.home_goals, fr.away_goals
            FROM wc_fixture_mapping m
            JOIN fixtures f ON f.fixture_id = m.api_football_fixture_id
            LEFT JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
            WHERE m.sportmonks_fixture_id IS NOT NULL AND m.blocked = 0
            """
        ):
            add(
                int(row["sportmonks_fixture_id"]),
                home=str(row["home_team"]),
                away=str(row["away_team"]),
                kickoff=str(row["kickoff_utc"] or ""),
                league=str(row["competition_key"] or ""),
                season=str(row["season"] or ""),
                source="wc_fixture_mapping",
                hg=row["home_goals"],
                ag=row["away_goals"],
            )

    for cache_dir in SPORTMONKS_CACHE_DIRS:
        if not cache_dir.is_dir():
            continue
        for path in cache_dir.glob("*.json"):
            try:
                sm_id = int(path.stem)
            except ValueError:
                continue
            if sm_id in seen:
                continue
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            data = blob.get("payload", blob)
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
            if not isinstance(data, dict):
                continue
            home, away, league, kickoff = _participants_from_sm_payload(data)
            season = ""
            if kickoff and len(kickoff) >= 4:
                try:
                    season = str(int(kickoff[:4]) if int(kickoff[5:7]) >= 7 else int(kickoff[:4]) - 1)
                except ValueError:
                    season = kickoff[:4]
            add(sm_id, home=home, away=away, kickoff=kickoff, league=league, season=season, source=f"cache:{cache_dir.name}")

    return out


def build_oddalerts_candidates(conn: sqlite3.Connection) -> list[ProviderCandidate]:
    out: list[ProviderCandidate] = []
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='oddalerts_fixture_map'"
    ).fetchone():
        return out

    for row in conn.execute(
        """
        SELECT oddalerts_fixture_id, home_team, away_team, kickoff, league, season
        FROM oddalerts_fixture_map
        """
    ):
        kickoff = str(row["kickoff"] or "")
        md = kickoff[:10] if kickoff else ""
        if len(md) < 10:
            continue
        out.append(
            ProviderCandidate(
                provider=PROVIDER_ODDALERTS,
                provider_fixture_id=int(row["oddalerts_fixture_id"]),
                kickoff_utc=kickoff,
                match_date=md,
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                home_team_normalized=_norm_team(row["home_team"]),
                away_team_normalized=_norm_team(row["away_team"]),
                league_normalized=_norm_league(row["league"]),
                season=str(row["season"] or ""),
                source="oddalerts_fixture_map",
            )
        )

    for row in conn.execute(
        """
        SELECT DISTINCT h.oddalerts_fixture_id, m.home_team, m.away_team, m.kickoff, m.league, m.season
        FROM oddalerts_odds_history h
        LEFT JOIN oddalerts_fixture_map m ON m.oddalerts_fixture_id = h.oddalerts_fixture_id
        WHERE m.oddalerts_fixture_id IS NOT NULL
        """
    ):
        kickoff = str(row["kickoff"] or "")
        md = kickoff[:10] if kickoff else ""
        if len(md) < 10:
            continue
        out.append(
            ProviderCandidate(
                provider=PROVIDER_ODDALERTS,
                provider_fixture_id=int(row["oddalerts_fixture_id"]),
                kickoff_utc=kickoff,
                match_date=md,
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                home_team_normalized=_norm_team(row["home_team"]),
                away_team_normalized=_norm_team(row["away_team"]),
                league_normalized=_norm_league(row["league"]),
                season=str(row["season"] or ""),
                source="oddalerts_odds_history",
            )
        )
    return out


def _match_registry_to_provider(
    reg: dict[str, Any],
    *,
    provider: str,
    exact_index: dict[str, list[ProviderCandidate]],
    date_index: dict[str, list[ProviderCandidate]],
) -> MatchResult | None:
    if provider == PROVIDER_API_FOOTBALL and reg.get("internal_fixture_id"):
        fid = int(reg["internal_fixture_id"])
        return MatchResult(
            candidate=ProviderCandidate(
                provider=provider,
                provider_fixture_id=fid,
                kickoff_utc=reg.get("kickoff_utc"),
                match_date=str(reg["match_date"])[:10],
                home_team=reg["home_team"],
                away_team=reg["away_team"],
                home_team_normalized=reg["home_team_normalized"],
                away_team_normalized=reg["away_team_normalized"],
                league_normalized=reg.get("league_normalized") or "",
                season=str(reg.get("season") or ""),
                source="prelinked_internal_fixture_id",
            ),
            confidence_score=1.0,
            match_method="prelinked_internal_fixture_id",
            kickoff_delta_minutes=0,
            league_match=True,
            season_match=True,
            score_validated=reg.get("home_goals") is not None,
            ambiguous_flag=False,
            candidate_count=1,
        )

    date = str(reg["match_date"])[:10]
    key = _date_team_key(date, reg["home_team_normalized"], reg["away_team_normalized"])
    hits = exact_index.get(key, [])
    if hits:
        result = _pick_best_match(reg, hits)
        if result:
            return result

    day_pool = date_index.get(date, [])
    if day_pool:
        fuzzy_hits = [c for c in day_pool if _teams_fuzzy(reg, c)]
        if fuzzy_hits:
            return _pick_best_match(reg, fuzzy_hits)
    return None


def build_historical_provider_mappings(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    upgrade_better: bool = True,
) -> MappingBuildStats:
    ensure_historical_provider_mapping_table(conn)
    stats = MappingBuildStats(build_batch=_build_batch_id())

    provider_candidates = {
        PROVIDER_API_FOOTBALL: build_api_football_candidates(conn),
        PROVIDER_SPORTMONKS: build_sportmonks_candidates(conn),
        PROVIDER_ODDALERTS: build_oddalerts_candidates(conn),
    }
    provider_indexes = {
        p: _index_candidates(cands) for p, cands in provider_candidates.items()
    }

    registry_rows = _load_registry_rows(conn)
    stats.registry_rows_scanned = len(registry_rows)
    created_at = _utc_now()

    insert_sql = f"""
        INSERT INTO {TABLE_NAME} (
            registry_fixture_id, provider, provider_fixture_id, confidence_score, match_method,
            kickoff_delta_minutes, league_match, season_match, score_validated,
            ambiguous_flag, candidate_count, build_batch, method_version, created_at
        ) VALUES (
            :registry_fixture_id, :provider, :provider_fixture_id, :confidence_score, :match_method,
            :kickoff_delta_minutes, :league_match, :season_match, :score_validated,
            :ambiguous_flag, :candidate_count, :build_batch, :method_version, :created_at
        )
        ON CONFLICT(registry_fixture_id, provider) DO NOTHING
    """
    upgrade_sql = f"""
        INSERT INTO {TABLE_NAME} (
            registry_fixture_id, provider, provider_fixture_id, confidence_score, match_method,
            kickoff_delta_minutes, league_match, season_match, score_validated,
            ambiguous_flag, candidate_count, build_batch, method_version, created_at
        ) VALUES (
            :registry_fixture_id, :provider, :provider_fixture_id, :confidence_score, :match_method,
            :kickoff_delta_minutes, :league_match, :season_match, :score_validated,
            :ambiguous_flag, :candidate_count, :build_batch, :method_version, :created_at
        )
        ON CONFLICT(registry_fixture_id, provider) DO UPDATE SET
            provider_fixture_id = excluded.provider_fixture_id,
            confidence_score = excluded.confidence_score,
            match_method = excluded.match_method,
            kickoff_delta_minutes = excluded.kickoff_delta_minutes,
            league_match = excluded.league_match,
            season_match = excluded.season_match,
            score_validated = excluded.score_validated,
            ambiguous_flag = excluded.ambiguous_flag,
            candidate_count = excluded.candidate_count,
            build_batch = excluded.build_batch,
            method_version = excluded.method_version,
            created_at = excluded.created_at
        WHERE excluded.confidence_score > {TABLE_NAME}.confidence_score
    """

    for reg in registry_rows:
        rid = int(reg["registry_fixture_id"])
        matched_any = False
        for provider in PROVIDERS:
            exact_idx, date_idx = provider_indexes[provider]
            result = _match_registry_to_provider(
                reg, provider=provider, exact_index=exact_idx, date_index=date_idx
            )
            if not result:
                continue
            matched_any = True
            payload = {
                "registry_fixture_id": rid,
                "provider": provider,
                "provider_fixture_id": result.candidate.provider_fixture_id,
                "confidence_score": result.confidence_score,
                "match_method": result.match_method,
                "kickoff_delta_minutes": result.kickoff_delta_minutes,
                "league_match": int(result.league_match),
                "season_match": int(result.season_match),
                "score_validated": int(result.score_validated),
                "ambiguous_flag": int(result.ambiguous_flag),
                "candidate_count": result.candidate_count,
                "build_batch": stats.build_batch,
                "method_version": METHOD_VERSION,
                "created_at": created_at,
            }
            stats.by_provider[provider] = stats.by_provider.get(provider, 0) + 1
            stats.by_method[result.match_method] = stats.by_method.get(result.match_method, 0) + 1
            if result.ambiguous_flag:
                stats.ambiguous_count += 1
            if dry_run:
                stats.mappings_inserted += 1
                continue

            before = conn.total_changes
            conn.execute(upgrade_sql if upgrade_better else insert_sql, payload)
            delta = conn.total_changes - before
            if delta:
                stats.mappings_inserted += 1
            else:
                stats.mappings_skipped_existing += 1

        if not matched_any:
            stats.unmatched_count += 1

    if not dry_run:
        conn.commit()
    return stats


def audit_mappings(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_historical_provider_mapping_table(conn)
    total = conn.execute(f"SELECT COUNT(1) FROM {TABLE_NAME}").fetchone()[0]
    if total == 0:
        return {"rows": 0}

    by_provider = [
        dict(r)
        for r in conn.execute(
            f"""
            SELECT provider, COUNT(1) AS mappings,
                   AVG(confidence_score) AS avg_confidence,
                   SUM(ambiguous_flag) AS ambiguous,
                   SUM(score_validated) AS score_validated
            FROM {TABLE_NAME}
            GROUP BY provider
            """
        )
    ]
    by_method = [
        dict(r)
        for r in conn.execute(
            f"""
            SELECT match_method, COUNT(1) AS n
            FROM {TABLE_NAME}
            GROUP BY match_method ORDER BY n DESC
            """
        )
    ]
    dup_provider_fixture = conn.execute(
        f"""
        SELECT provider, provider_fixture_id, COUNT(1) c
        FROM {TABLE_NAME}
        GROUP BY provider, provider_fixture_id
        HAVING c > 1
        LIMIT 10
        """
    ).fetchall()
    registry_coverage = conn.execute(
        f"""
        SELECT COUNT(DISTINCT registry_fixture_id) FROM {TABLE_NAME}
        """
    ).fetchone()[0]
    ecse_coverage = conn.execute(
        f"""
        SELECT COUNT(DISTINCT m.registry_fixture_id)
        FROM {TABLE_NAME} m
        INNER JOIN ecse_training_dataset e ON e.registry_fixture_id = m.registry_fixture_id
        """
    ).fetchone()[0]
    ecse_total = conn.execute("SELECT COUNT(DISTINCT registry_fixture_id) FROM ecse_training_dataset").fetchone()[0]

    return {
        "rows": total,
        "distinct_registry_fixtures": registry_coverage,
        "ecse_mapped_fixtures": ecse_coverage,
        "ecse_total_fixtures": ecse_total,
        "ecse_coverage_pct": round(100.0 * ecse_coverage / max(ecse_total, 1), 4),
        "by_provider": by_provider,
        "by_method": by_method,
        "duplicate_provider_fixture_pairs": [dict(r) for r in dup_provider_fixture],
    }


def mapping_report_md(build: MappingBuildStats, audit: dict[str, Any], candidate_counts: dict[str, int]) -> str:
    lines = [
        "# MAP-1 — Historical Provider Mapping Report",
        "",
        f"**Method:** `{METHOD_VERSION}`  ",
        f"**Build batch:** `{build.build_batch}`  ",
        f"**Generated:** {_utc_now()}  ",
        "**Mode:** Read-only local matching (no API calls)",
        "",
        "## Summary",
        "",
        f"- Registry rows scanned: **{build.registry_rows_scanned:,}**",
        f"- Mappings written: **{build.mappings_inserted:,}**",
        f"- Skipped (existing equal/better): **{build.mappings_skipped_existing:,}**",
        f"- Unmatched registry rows (all providers): **{build.unmatched_count:,}**",
        f"- Ambiguous mappings: **{build.ambiguous_count:,}**",
        "",
        "## Provider candidate pools (local)",
        "",
    ]
    for p, n in candidate_counts.items():
        lines.append(f"- **{p}:** {n:,} candidates")
    lines.extend(["", "## Mapping coverage", ""])
    for row in audit.get("by_provider", []):
        lines.append(
            f"- **{row['provider']}**: {row['mappings']:,} mappings, "
            f"avg confidence {round(float(row['avg_confidence'] or 0), 4)}, "
            f"score-validated {int(row['score_validated'] or 0):,}, "
            f"ambiguous {int(row['ambiguous'] or 0):,}"
        )
    lines.extend(
        [
            "",
            f"- Distinct registry fixtures mapped: **{audit.get('distinct_registry_fixtures', 0):,}**",
            f"- ECSE fixtures with ≥1 mapping: **{audit.get('ecse_mapped_fixtures', 0):,}** "
            f"({audit.get('ecse_coverage_pct', 0)}% of {audit.get('ecse_total_fixtures', 0):,})",
            "",
            "## Match methods",
            "",
            "| Method | Count |",
            "|--------|-------|",
        ]
    )
    for row in audit.get("by_method", []):
        lines.append(f"| {row['match_method']} | {row['n']:,} |")
    dups = audit.get("duplicate_provider_fixture_pairs", [])
    lines.extend(
        [
            "",
            "## Duplicate / ambiguity checks",
            "",
            f"- Provider fixture ID reused across registry rows: **{len(dups)}** pairs (sample in JSON)",
            "",
            "---",
            "",
            "*Staging table `historical_provider_mapping` only. No production prediction changes.*",
        ]
    )
    return "\n".join(lines)
