"""PHASE EURO-B — Canonical upcoming UEFA fixture selector (owner/internal)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.data_import.european_fixture_feed import ensure_euro_fixture_feed_tables
from worldcup_predictor.data_import.uefa_result_matching import (
    FeedIndex,
    infer_provider_source,
    kickoff_delta_hours,
    lookup_feed_api_id,
    normalize_team_name,
    parse_kickoff,
    teams_exact,
)

PHASE = "EURO-B"
MIN_CROSSWALK_CONFIDENCE = 0.95

_EXCLUDED_STATUSES = frozenset(
    {
        "FT",
        "AET",
        "PEN",
        "AWD",
        "WO",
        "CANC",
        "ABD",
        "PST",
        "POSTP",
        "POSTPONED",
        "CANCELLED",
        "ABANDONED",
        "SUSP",
        "INT",
        "FINISHED",
    }
)


@dataclass
class UefaFixtureSelection:
    fixture_id: int
    provider_fixture_id: int
    competition_key: str
    home_team: str
    away_team: str
    kickoff_utc: str
    status: str
    provider_source: str
    crosswalk_confidence: float
    crosswalk_status: Literal["canonical_api", "crosswalked_api", "sportmonks_only", "unknown"]
    has_odds: bool
    has_wde: bool
    has_ecse: bool
    duplicate_risk: bool = False
    duplicate_group_key: str | None = None
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "provider_fixture_id": self.provider_fixture_id,
            "competition_key": self.competition_key,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "kickoff_utc": self.kickoff_utc,
            "status": self.status,
            "provider_source": self.provider_source,
            "crosswalk_confidence": self.crosswalk_confidence,
            "crosswalk_status": self.crosswalk_status,
            "has_odds": self.has_odds,
            "has_wde": self.has_wde,
            "has_ecse": self.has_ecse,
            "duplicate_risk": self.duplicate_risk,
            "duplicate_group_key": self.duplicate_group_key,
            "skip_reason": self.skip_reason,
        }


def _resolve_canonical(
    row: dict[str, Any],
    feed_index: FeedIndex,
) -> tuple[int, str, float, str]:
    fid = int(row["fixture_id"])
    comp = str(row["competition_key"])
    if (comp, "api-football", fid) in feed_index.by_provider_id:
        return fid, "api-football", 1.0, "canonical_api"
    api_id = lookup_feed_api_id(row, feed_index)
    if api_id:
        return int(api_id), "api-football", 0.99, "crosswalked_api"
    inferred = infer_provider_source(row, feed_index)
    if inferred == "api-football" or fid < 10_000_000:
        return fid, "api-football", 0.92, "canonical_api"
    if inferred == "sportmonks":
        return fid, "sportmonks", 0.0, "sportmonks_only"
    return fid, inferred or "unknown", 0.5, "unknown"


def _odds_flags(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, snapshot_at, payload_json, competition_key
        FROM odds_snapshots
        WHERE fixture_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return {
            "has_odds": False,
            "odds_1x2": False,
            "odds_ou": False,
            "odds_btts": False,
            "odds_correct_score": False,
            "odds_source": None,
            "odds_snapshot_at": None,
        }
    import json

    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        payload = {}
    text = json.dumps(payload).lower()
    return {
        "has_odds": True,
        "odds_1x2": any(x in text for x in ("match winner", "1x2", "home/draw/away")),
        "odds_ou": "over/under" in text or "goals over" in text,
        "odds_btts": "both teams" in text or "btts" in text,
        "odds_correct_score": "correct score" in text,
        "odds_source": row["competition_key"],
        "odds_snapshot_at": row["snapshot_at"],
    }


def select_upcoming_uefa_fixtures(
    conn: sqlite3.Connection,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
) -> list[UefaFixtureSelection]:
    ensure_euro_fixture_feed_tables(conn)
    keys = tuple(competition_keys or UEFA_CUP_KEYS)
    feed_index = FeedIndex.build(conn, keys)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end = now + timedelta(days=max(1, days_ahead))
    placeholders = ",".join("?" for _ in keys)
    excluded = ",".join("?" for _ in _EXCLUDED_STATUSES)

    rows = conn.execute(
        f"""
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, source
        FROM fixtures
        WHERE competition_key IN ({placeholders})
          AND is_placeholder = 0
          AND kickoff_utc IS NOT NULL
          AND kickoff_utc >= ?
          AND kickoff_utc <= ?
          AND UPPER(COALESCE(status, 'NS')) NOT IN ({excluded})
        ORDER BY kickoff_utc ASC
        """,
        (*keys, now.isoformat(), end.isoformat(), *_EXCLUDED_STATUSES),
    ).fetchall()

    selections: list[UefaFixtureSelection] = []
    for raw in rows:
        row = dict(raw)
        provider_id, provider_source, confidence, cross_status = _resolve_canonical(row, feed_index)
        if cross_status == "sportmonks_only" and confidence < MIN_CROSSWALK_CONFIDENCE:
            sel = UefaFixtureSelection(
                fixture_id=int(row["fixture_id"]),
                provider_fixture_id=provider_id,
                competition_key=str(row["competition_key"]),
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                kickoff_utc=str(row["kickoff_utc"]),
                status=str(row.get("status") or "NS"),
                provider_source=provider_source,
                crosswalk_confidence=confidence,
                crosswalk_status=cross_status,
                has_odds=False,
                has_wde=False,
                has_ecse=False,
                skip_reason="provider_mapping_missing",
            )
            selections.append(sel)
            continue

        canonical_id = provider_id if cross_status != "sportmonks_only" else int(row["fixture_id"])
        odds = _odds_flags(conn, canonical_id)
        has_wde = bool(
            conn.execute(
                """
                SELECT 1 FROM worldcup_stored_predictions
                WHERE fixture_id = ? AND competition_key = ?
                  AND (is_active IS NULL OR is_active = 1)
                LIMIT 1
                """,
                (canonical_id, row["competition_key"]),
            ).fetchone()
        )
        has_ecse = bool(
            conn.execute(
                "SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id = ? LIMIT 1",
                (canonical_id,),
            ).fetchone()
        )
        selections.append(
            UefaFixtureSelection(
                fixture_id=int(row["fixture_id"]),
                provider_fixture_id=canonical_id,
                competition_key=str(row["competition_key"]),
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                kickoff_utc=str(row["kickoff_utc"]),
                status=str(row.get("status") or "NS"),
                provider_source=provider_source,
                crosswalk_confidence=confidence,
                crosswalk_status=cross_status,
                has_odds=bool(odds["has_odds"]),
                has_wde=has_wde,
                has_ecse=has_ecse,
            )
        )

    _mark_duplicate_risks(selections)
    return selections


def _mark_duplicate_risks(selections: list[UefaFixtureSelection]) -> None:
    groups: dict[str, list[UefaFixtureSelection]] = {}
    for sel in selections:
        if sel.skip_reason:
            continue
        kick = parse_kickoff(sel.kickoff_utc)
        date_key = kick.date().isoformat() if kick else str(sel.kickoff_utc)[:10]
        gkey = "|".join(
            [
                sel.competition_key,
                date_key,
                normalize_team_name(sel.home_team),
                normalize_team_name(sel.away_team),
            ]
        )
        groups.setdefault(gkey, []).append(sel)

    for gkey, items in groups.items():
        if len(items) < 2:
            continue
        for i, a in enumerate(items):
            for b in items[i + 1 :]:
                if a.provider_fixture_id == b.provider_fixture_id:
                    continue
                delta = kickoff_delta_hours(a.kickoff_utc, b.kickoff_utc)
                if delta is not None and delta <= 3 and teams_exact(
                    a.home_team, a.away_team, b.home_team, b.away_team
                ):
                    a.duplicate_risk = True
                    b.duplicate_risk = True
                    a.duplicate_group_key = gkey
                    b.duplicate_group_key = gkey


def build_duplicate_candidate_report(
    conn: sqlite3.Connection,
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
) -> dict[str, Any]:
    selections = select_upcoming_uefa_fixtures(
        conn, competition_keys=competition_keys, days_ahead=days_ahead
    )
    candidates: list[dict[str, Any]] = []
    for sel in selections:
        if not sel.duplicate_risk:
            continue
        candidates.append(
            {
                "competition_key": sel.competition_key,
                "kickoff_utc": sel.kickoff_utc,
                "home_team": sel.home_team,
                "away_team": sel.away_team,
                "fixture_id": sel.fixture_id,
                "provider_fixture_id": sel.provider_fixture_id,
                "provider_source": sel.provider_source,
                "duplicate_group_key": sel.duplicate_group_key,
                "suggested_action": "use_api_football_canonical_id_only",
            }
        )
    return {
        "phase": PHASE,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def odds_readiness_audit(conn: sqlite3.Connection, selection: UefaFixtureSelection) -> dict[str, Any]:
    flags = _odds_flags(conn, selection.provider_fixture_id)
    lambda_available = False
    if flags["has_odds"]:
        from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row
        from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas

        row = build_odds_feature_row(conn, selection.provider_fixture_id)
        if row:
            lambda_available = extract_lambdas(row) is not None
    return {
        "fixture_id": selection.provider_fixture_id,
        "competition_key": selection.competition_key,
        **flags,
        "lambda_inputs_available": lambda_available,
    }
