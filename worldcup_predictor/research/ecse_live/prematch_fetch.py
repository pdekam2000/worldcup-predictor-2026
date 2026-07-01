"""PHASE ECSE-LIVE-1 — Fetch prematch data from Sportmonks, OddAlerts, API-Football."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_enrichment import fetch_worldcup_fixture_enrichment
from worldcup_predictor.research.ecse_live.api_log import ApiCallTracker
from worldcup_predictor.research.ecse_live.fixture_resolver import ResolvedFixture
from worldcup_predictor.research.ecse_live.odds_merge import (
    api_football_odds_to_ecse_row,
    merge_ecse_odds_rows,
    oddalerts_history_to_ecse_row,
    sqlite_odds_row,
)

PHASE = "ECSE-LIVE-1"


@dataclass
class PrematchBundle:
    resolved: ResolvedFixture
    odds_row: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, list[str]] = field(default_factory=dict)
    xg: dict[str, Any] | None = None
    lineups: dict[str, Any] | None = None
    injuries: list[dict[str, Any]] | None = None
    correct_score_odds: dict[str, float] = field(default_factory=dict)
    raw_provider_payloads: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": self.resolved.to_dict(),
            "odds_row_keys": sorted(k for k in self.odds_row if not k.startswith("_")),
            "coverage": self.coverage,
            "has_xg": self.xg is not None,
            "has_lineups": self.lineups is not None,
            "injury_count": len(self.injuries or []),
            "correct_score_markets": len(self.correct_score_odds),
        }


def _coverage_from_row(row: dict[str, Any], prefix: str) -> list[str]:
    markets: list[str] = []
    if row.get("ft_home_closing") or row.get("ft_away_closing"):
        markets.append("1x2")
    if row.get("ou_over_25_closing"):
        markets.append("ou_2_5")
    if row.get("btts_yes_closing") or row.get("btts_no_closing"):
        markets.append("btts")
    if row.get("ou_over_15_closing"):
        markets.append("ou_1_5")
    if row.get("team_home_over_05_closing"):
        markets.append("team_goals")
    if row.get("correct_score_odds"):
        markets.append("correct_score")
    return [f"{prefix}:{m}" for m in markets]


def fetch_api_football_prematch(
    resolved: ResolvedFixture,
    *,
    settings: Settings,
    tracker: ApiCallTracker,
    conn,
) -> tuple[dict[str, Any], dict[str, Any]]:
    extras: dict[str, Any] = {}
    if not resolved.fixture_id:
        return {}, extras
    client = ApiFootballClient(settings)
    fid = int(resolved.fixture_id)

    odds_res = client.get_odds(fid)
    tracker.record(
        conn,
        provider="api_football",
        endpoint="odds",
        entity_key=str(fid),
        action="fetch",
        status="ok" if odds_res.ok else "error",
        details={"error": odds_res.error},
    )
    odds_row: dict[str, Any] = {}
    if odds_res.ok and odds_res.data:
        odds_row = api_football_odds_to_ecse_row(odds_res.data, fixture_id=fid)
        odds_row["_provider"] = "api_football"
        extras["odds"] = odds_res.data

    lineups_res = client.get_fixture_lineups(fid)
    tracker.record(
        conn, provider="api_football", endpoint="fixtures/lineups", entity_key=str(fid),
        action="fetch", status="ok" if lineups_res.ok else "error",
    )
    if lineups_res.ok and lineups_res.data:
        extras["lineups"] = lineups_res.data

    injuries_res = client.get_injuries(fid)
    tracker.record(
        conn, provider="api_football", endpoint="injuries", entity_key=str(fid),
        action="fetch", status="ok" if injuries_res.ok else "error",
    )
    if injuries_res.ok and injuries_res.data:
        extras["injuries"] = injuries_res.data

    return odds_row, extras


def fetch_sportmonks_prematch(
    resolved: ResolvedFixture,
    *,
    settings: Settings,
    tracker: ApiCallTracker,
    conn,
) -> dict[str, Any]:
    if not resolved.sportmonks_fixture_id:
        return {}
    sm_id = int(resolved.sportmonks_fixture_id)
    enrichment = fetch_worldcup_fixture_enrichment(sm_id, settings=settings)
    tracker.record(
        conn,
        provider="sportmonks",
        endpoint=enrichment.endpoint_path,
        entity_key=str(sm_id),
        action="fetch",
        status="ok" if enrichment.success else "error",
        details={
            "message": enrichment.message,
            "keys": list(enrichment.keys_present or ()),
            "api_calls": enrichment.api_calls_made,
        },
    )
    if not enrichment.success or not enrichment.fixture:
        return {}
    fixture = enrichment.fixture
    out: dict[str, Any] = {"fixture": fixture, "_provider": "sportmonks"}
    if fixture.get("xGFixture"):
        out["xg"] = fixture.get("xGFixture")
    if fixture.get("lineups"):
        out["lineups"] = fixture.get("lineups")
    if fixture.get("sidelined"):
        out["injuries"] = fixture.get("sidelined")
    return out


def fetch_oddalerts_prematch(
    resolved: ResolvedFixture,
    *,
    tracker: ApiCallTracker,
    conn,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not resolved.oddalerts_fixture_id:
        return {}, {}
    client = OddAlertsClient()
    if not client.is_configured:
        return {}, {}

    oa_id = int(resolved.oddalerts_fixture_id)
    hist = client.get_odds_history(oa_id)
    tracker.record(
        conn,
        provider="oddalerts",
        endpoint="odds/history",
        entity_key=str(oa_id),
        action="fetch",
        status="ok" if hist.data else "error",
        details={"error": hist.error},
    )
    rows = (hist.data or {}).get("data") or []
    odds_row = oddalerts_history_to_ecse_row(rows)
    if odds_row:
        odds_row["_provider"] = "oddalerts"

    fx = client.get_fixture(oa_id, include="odds,probability,stats")
    tracker.record(
        conn,
        provider="oddalerts",
        endpoint=f"fixtures/{oa_id}",
        entity_key=str(oa_id),
        action="fetch",
        status="ok" if fx.data else "error",
    )
    extras: dict[str, Any] = {"odds_history_rows": len(rows)}
    if fx.data:
        extras["fixture"] = fx.data
    return odds_row, extras


def fetch_prematch_bundle(
    resolved: ResolvedFixture,
    *,
    settings: Settings | None = None,
    tracker: ApiCallTracker | None = None,
    conn=None,
) -> PrematchBundle:
    settings = settings or get_settings()
    tracker = tracker or ApiCallTracker()
    bundle = PrematchBundle(resolved=resolved)

    af_row, af_extra = fetch_api_football_prematch(resolved, settings=settings, tracker=tracker, conn=conn)
    if af_row:
        bundle.coverage["api_football"] = _coverage_from_row(af_row, "api_football")
    bundle.raw_provider_payloads["api_football"] = af_extra
    if af_extra.get("lineups"):
        bundle.lineups = {"api_football": af_extra["lineups"]}
    if af_extra.get("injuries"):
        bundle.injuries = list(af_extra["injuries"]) if isinstance(af_extra["injuries"], list) else []

    sm_extra = fetch_sportmonks_prematch(resolved, settings=settings, tracker=tracker, conn=conn)
    bundle.raw_provider_payloads["sportmonks"] = sm_extra
    if sm_extra.get("xg"):
        bundle.xg = sm_extra["xg"] if isinstance(sm_extra["xg"], dict) else {"raw": sm_extra["xg"]}
        bundle.coverage.setdefault("sportmonks", []).append("sportmonks:xg")
    if sm_extra.get("lineups"):
        bundle.lineups = bundle.lineups or {}
        bundle.lineups["sportmonks"] = sm_extra["lineups"]
        bundle.coverage.setdefault("sportmonks", []).append("sportmonks:lineups")
    if sm_extra.get("injuries"):
        bundle.coverage.setdefault("sportmonks", []).append("sportmonks:injuries")

    oa_row, oa_extra = fetch_oddalerts_prematch(resolved, tracker=tracker, conn=conn)
    if oa_row:
        bundle.coverage["oddalerts"] = _coverage_from_row(oa_row, "oddalerts")
    bundle.raw_provider_payloads["oddalerts"] = oa_extra

    sqlite_row = sqlite_odds_row(conn, int(resolved.fixture_id)) if conn is not None and resolved.fixture_id else {}
    if sqlite_row:
        bundle.coverage["sqlite"] = _coverage_from_row(sqlite_row, "sqlite")

    merged = merge_ecse_odds_rows(oa_row, af_row, sqlite_row)
    bundle.odds_row = merged
    cs = merged.get("correct_score_odds") or {}
    if isinstance(cs, dict):
        bundle.correct_score_odds = {str(k): float(v) for k, v in cs.items()}

    return bundle
