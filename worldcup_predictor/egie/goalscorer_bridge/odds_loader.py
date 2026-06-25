"""Load API-Football goalscorer odds for bridged fixtures."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from worldcup_predictor.egie.goalscorer_bridge.team_mapper import side_for_market
from worldcup_predictor.egie.goalscorer_odds_acquisition.inventory import DB_PATH, _scan_api_football_payload
from worldcup_predictor.egie.goalscorer_odds_mapping.models import RawOddsSelection

_GS_MARKET = re.compile(r"(anytime|first|last)\s+goal\s+scorer", re.I)
_TEAM_GS = re.compile(r"team\s+goalscorer", re.I)


def _label_from_market(market_name: str) -> str:
    low = market_name.lower()
    if "first" in low:
        return "First"
    if "last" in low:
        return "Last"
    return "Anytime"


def load_api_goalscorer_odds(
    api_fixture_id: int,
    *,
    sportmonks_fixture_id: int,
) -> list[RawOddsSelection]:
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY rowid DESC LIMIT 1",
        (int(api_fixture_id),),
    ).fetchone()
    conn.close()
    if not row:
        return []

    payload = json.loads(row[0])
    lines, _, _ = _scan_api_football_payload(payload, fixture_id=int(api_fixture_id))
    out: list[RawOddsSelection] = []
    for item in lines:
        market = str(item.get("market") or "")
        if not _GS_MARKET.search(market) or _TEAM_GS.search(market):
            continue
        selection = str(item.get("selection") or "").strip()
        if not selection or selection.lower() in {"no goalscorer", "no goal"}:
            continue
        try:
            odds = float(item.get("odds") or 0)
        except (TypeError, ValueError):
            continue
        if odds <= 1.0:
            continue
        out.append(
            RawOddsSelection(
                sportmonks_fixture_id=int(sportmonks_fixture_id),
                bookmaker=str(item.get("bookmaker") or "unknown"),
                market=market,
                label=_label_from_market(market),
                selection_name=selection,
                odds=round(odds, 4),
                implied_probability=round(1.0 / odds, 6),
                timestamp=None,
                finished=True,
                league_id=732,
                season_id=None,
            )
        )
    return out


def load_all_bridged_odds(bridges: list[Any]) -> list[RawOddsSelection]:
    rows: list[RawOddsSelection] = []
    for bridge in bridges:
        sm_id = getattr(bridge, "sportmonks_fixture_id", None) or (bridge.get("sportmonks_fixture_id") if isinstance(bridge, dict) else None)
        api_id = getattr(bridge, "api_football_fixture_id", None) or (bridge.get("api_football_fixture_id") if isinstance(bridge, dict) else None)
        conf = getattr(bridge, "bridge_confidence", None) or (bridge.get("bridge_confidence") if isinstance(bridge, dict) else None)
        if not sm_id or conf == "UNMAPPED":
            continue
        rows.extend(load_api_goalscorer_odds(int(api_id), sportmonks_fixture_id=int(sm_id)))
    return rows
