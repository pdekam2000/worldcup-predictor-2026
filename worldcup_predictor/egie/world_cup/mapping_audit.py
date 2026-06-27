"""API-Football ↔ Sportmonks World Cup fixture mapping audit — Phase 62B."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.world_cup.competition_tags import classify_fixture_competition_type
from worldcup_predictor.egie.world_cup.config import (
    COMPETITION_TYPE_FINALS,
    MAPPING_AUDIT_OUTPUT,
    SPORTMONKS_LEAGUE_ID,
    WORLD_CUP_COMPETITION_KEY,
)
from worldcup_predictor.providers.sportmonks_fixture_lookup import team_names_match

logger = logging.getLogger(__name__)

_SPORTMONKS_CACHE_ROOTS = (
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/egie/world_cup/raw/sportmonks"),
    Path("data/egie/uefa_club/raw"),
)


def _kickoff_date(kickoff: str | None) -> str:
    if not kickoff:
        return ""
    return str(kickoff)[:10]


def _load_sportmonks_index() -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    seen: set[int] = set()
    for root in _SPORTMONKS_CACHE_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.json"):
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            payload = blob.get("payload") or blob.get("response") or blob
            data = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(data, dict):
                continue
            try:
                lid = int(data.get("league_id") or 0)
            except (TypeError, ValueError):
                lid = 0
            if lid not in (0, SPORTMONKS_LEAGUE_ID):
                continue
            sm_id = int(data.get("id") or 0)
            if sm_id <= 0 or sm_id in seen:
                continue
            seen.add(sm_id)
            home = away = ""
            for part in data.get("participants") or []:
                if not isinstance(part, dict):
                    continue
                loc = str((part.get("meta") or {}).get("location") or "").lower()
                name = str(part.get("name") or "")
                if loc == "home":
                    home = name
                elif loc == "away":
                    away = name
            index.append(
                {
                    "sportmonks_fixture_id": sm_id,
                    "home_team": home,
                    "away_team": away,
                    "match_date": str(data.get("starting_at") or "")[:10],
                    "cache_path": str(path),
                }
            )
    return index


def _match_from_index(
    *,
    home_team: str,
    away_team: str,
    kickoff: str | None,
    index: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float, str]:
    date = _kickoff_date(kickoff)
    best: dict[str, Any] | None = None
    best_score = 0.0
    for row in index:
        score = 0.0
        if date and row.get("match_date") == date:
            score += 0.5
        home_ok = team_names_match(home_team, str(row.get("home_team") or ""))
        away_ok = team_names_match(away_team, str(row.get("away_team") or ""))
        if home_ok:
            score += 0.25
        if away_ok:
            score += 0.25
        if score > best_score:
            best_score = score
            best = row
    if best and best_score >= 0.75:
        return best, best_score, "cache_index"
    return None, best_score, "unmapped"


def _persist_mapping(
    repo: FootballIntelligenceRepository,
    *,
    api_id: int,
    sm_id: int | None,
    confidence: float,
    source: str,
    date_match: bool,
    team_match: bool,
    blocked: bool = False,
    block_reason: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    repo._conn.execute(
        """
        INSERT INTO wc_fixture_mapping(
            api_football_fixture_id, sportmonks_fixture_id, mapping_confidence,
            mapping_source, date_match, team_match, blocked, block_reason, mapped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(api_football_fixture_id) DO UPDATE SET
            sportmonks_fixture_id=excluded.sportmonks_fixture_id,
            mapping_confidence=excluded.mapping_confidence,
            mapping_source=excluded.mapping_source,
            date_match=excluded.date_match,
            team_match=excluded.team_match,
            blocked=excluded.blocked,
            block_reason=excluded.block_reason,
            mapped_at=excluded.mapped_at
        """,
        (
            api_id,
            sm_id,
            confidence,
            source,
            int(date_match),
            int(team_match),
            int(blocked),
            block_reason,
            now,
        ),
    )


def run_mapping_audit(
    *,
    settings: Settings | None = None,
    finals_only: bool = True,
    max_live_lookups: int = 0,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    rows = repo._conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, season, round_name,
               COALESCE(competition_type, 'world_cup_finals') AS competition_type
        FROM fixtures
        WHERE competition_key = ?
        ORDER BY kickoff_utc DESC
        """,
        (WORLD_CUP_COMPETITION_KEY,),
    ).fetchall()

    sm_index = _load_sportmonks_index()
    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    duplicates: dict[int, list[int]] = {}
    sm_to_api: dict[int, int] = {}

    for row in rows:
        api_id = int(row[0])
        comp_type = str(row[6] or COMPETITION_TYPE_FINALS)
        if finals_only and comp_type != COMPETITION_TYPE_FINALS:
            continue
        home, away, kickoff = str(row[1] or ""), str(row[2] or ""), row[3]

        sm_id = None
        confidence = 0.0
        source = "none"
        date_match = False
        team_match = False

        enrich = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(api_id)
        if enrich and enrich.get("sportmonks_fixture_id"):
            sm_id = int(enrich["sportmonks_fixture_id"])
            confidence = 1.0
            source = "sportmonks_fixture_enrichment"
            date_match = team_match = True
        else:
            cache_row, score, src = _match_from_index(
                home_team=home, away_team=away, kickoff=kickoff, index=sm_index
            )
            if cache_row:
                sm_id = int(cache_row["sportmonks_fixture_id"])
                confidence = score
                source = src
                date_match = _kickoff_date(kickoff) == cache_row.get("match_date")
                team_match = score >= 0.5

        if sm_id is not None:
            if sm_id in sm_to_api and sm_to_api[sm_id] != api_id:
                duplicates.setdefault(sm_id, [sm_to_api[sm_id]]).append(api_id)
                blocked.append(
                    {
                        "api_football_fixture_id": api_id,
                        "sportmonks_fixture_id": sm_id,
                        "reason": "duplicate_sportmonks_mapping",
                    }
                )
                _persist_mapping(
                    repo,
                    api_id=api_id,
                    sm_id=None,
                    confidence=0.0,
                    source="blocked",
                    date_match=date_match,
                    team_match=team_match,
                    blocked=True,
                    block_reason="duplicate_sportmonks_mapping",
                )
                continue
            sm_to_api[sm_id] = api_id
            mapped.append(
                {
                    "api_football_fixture_id": api_id,
                    "sportmonks_fixture_id": sm_id,
                    "confidence": round(confidence, 4),
                    "source": source,
                }
            )
            _persist_mapping(
                repo,
                api_id=api_id,
                sm_id=sm_id,
                confidence=confidence,
                source=source,
                date_match=date_match,
                team_match=team_match,
            )
        else:
            unmapped.append({"api_football_fixture_id": api_id, "home_team": home, "away_team": away})
            _persist_mapping(
                repo,
                api_id=api_id,
                sm_id=None,
                confidence=0.0,
                source="unmapped",
                date_match=False,
                team_match=False,
            )

    repo._conn.commit()
    total = len(mapped) + len(unmapped) + len(blocked)
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_wc_fixtures": total,
        "mapped_fixtures": len(mapped),
        "unmapped_fixtures": len(unmapped),
        "blocked_mappings": len(blocked),
        "duplicate_sportmonks_ids": len(duplicates),
        "mapping_rate": round(len(mapped) / total, 4) if total else 0.0,
        "avg_confidence": round(
            sum(m["confidence"] for m in mapped) / len(mapped), 4
        )
        if mapped
        else 0.0,
        "sportmonks_cache_index_size": len(sm_index),
        "mapped_sample": mapped[:25],
        "unmapped_sample": unmapped[:25],
        "blocked_sample": blocked[:15],
        "duplicate_sample": dict(list(duplicates.items())[:10]),
    }
    out = Path(MAPPING_AUDIT_OUTPUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit
