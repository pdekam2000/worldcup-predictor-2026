"""Read-only audit trail for market consensus math — Phase 36 debug (UI layer)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from worldcup_predictor.agents.specialists.odds_control_agent import (
    _average_probs,
    _implied_from_decimal,
    _normalize_probs,
    extract_api_sports_1x2_meta,
    extract_api_sports_probs_first_bookmaker,
    extract_rapid_football_probs,
    extract_rapid_xg_probs,
)


@dataclass
class BookmakerOddsRow:
    source: str
    bookmaker: str
    home_odd: float | None
    draw_odd: float | None
    away_odd: float | None
    home_implied_raw: float | None
    draw_implied_raw: float | None
    away_implied_raw: float | None
    raw_implied_sum: float | None
    overround_pct: float | None
    home_normalized: float | None
    draw_normalized: float | None
    away_normalized: float | None
    normalized_sum: float | None
    used_in_consensus: bool = False


@dataclass
class MarketConsensusAudit:
    fixture_id: int | None
    home_team: str
    away_team: str
    formula_implied: str = "implied = 1 / decimal_odd"
    formula_normalize: str = "normalized = implied / sum(home, draw, away implied)"
    formula_aggregate: str = (
        "per bookmaker: normalize implied probs; "
        "aggregate: average normalized probs across all bookmakers; "
        "final: re-normalize to sum ≈ 100%"
    )
    bookmaker_rows: list[BookmakerOddsRow] = field(default_factory=list)
    source_probs_used: dict[str, dict[str, float]] = field(default_factory=dict)
    source_pre_average: dict[str, float] = field(default_factory=dict)
    final_consensus: dict[str, float] = field(default_factory=dict)
    final_consensus_pct: dict[str, float] = field(default_factory=dict)
    final_sum_pct: float | None = None
    production_signal: dict[str, Any] = field(default_factory=dict)
    old_method_1x2: dict[str, float] = field(default_factory=dict)
    old_method_1x2_pct: dict[str, float] = field(default_factory=dict)
    new_method_1x2: dict[str, float] = field(default_factory=dict)
    new_method_1x2_pct: dict[str, float] = field(default_factory=dict)
    method_difference_pct: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _row_from_match_winner(
    *,
    source: str,
    bookmaker: str,
    values: list[dict[str, Any]],
    used_in_consensus: bool = False,
) -> BookmakerOddsRow | None:
    odds_map: dict[str, float | None] = {"home": None, "draw": None, "away": None}
    for value in values:
        label = str(value.get("value", "")).lower()
        key = {"home": "home", "draw": "draw", "away": "away"}.get(label)
        if key is None:
            continue
        try:
            odds_map[key] = float(value.get("odd")) if value.get("odd") is not None else None
        except (TypeError, ValueError):
            odds_map[key] = None

    if not any(odds_map.values()):
        return None

    implied = {k: _implied_from_decimal(v) for k, v in odds_map.items()}
    raw_sum = sum(v for v in implied.values() if v is not None)
    normalized = _normalize_probs({k: v for k, v in implied.items() if v is not None})
    overround = (raw_sum - 1.0) * 100 if raw_sum else None

    return BookmakerOddsRow(
        source=source,
        bookmaker=bookmaker,
        home_odd=odds_map["home"],
        draw_odd=odds_map["draw"],
        away_odd=odds_map["away"],
        home_implied_raw=implied.get("home"),
        draw_implied_raw=implied.get("draw"),
        away_implied_raw=implied.get("away"),
        raw_implied_sum=round(raw_sum, 6) if raw_sum else None,
        overround_pct=round(overround, 2) if overround is not None else None,
        home_normalized=normalized.get("home"),
        draw_normalized=normalized.get("draw"),
        away_normalized=normalized.get("away"),
        normalized_sum=round(sum(normalized.values()), 4) if normalized else None,
        used_in_consensus=used_in_consensus,
    )


def _extract_api_sports_bookmakers(report: Any) -> list[BookmakerOddsRow]:
    rows: list[BookmakerOddsRow] = []
    odds = getattr(report, "odds", None)
    if odds is None or not getattr(odds, "available", False):
        return rows

    meta = extract_api_sports_1x2_meta(report)
    used_names = set(meta.get("used_bookmakers") or [])
    for bookmaker in odds.bookmakers or []:
        if not isinstance(bookmaker, dict):
            continue
        name = str(bookmaker.get("name") or "Unknown")
        for bet in bookmaker.get("bets", []):
            if bet.get("name") != "Match Winner":
                continue
            row = _row_from_match_winner(
                source="api_sports",
                bookmaker=name,
                values=bet.get("values") or [],
                used_in_consensus=name in used_names,
            )
            if row:
                rows.append(row)
            break
    return rows


def _extract_rapid_bookmakers(supplemental: dict[str, Any], source_key: str) -> list[BookmakerOddsRow]:
    rows: list[BookmakerOddsRow] = []
    block = supplemental.get(source_key) or {}
    if source_key == "rapid_football_stats":
        odds_payload = block.get("prematch_odds") or block.get("live_odds") or {}
    else:
        upcoming = block.get("upcoming_odds") or []
        odds_payload = upcoming[0] if isinstance(upcoming, list) and upcoming else {}

    if isinstance(odds_payload, list):
        odds_payload = odds_payload[0] if odds_payload else {}

    if not isinstance(odds_payload, dict):
        return rows

    bookmakers = odds_payload.get("bookmakers") or [odds_payload]
    first_used = False
    for bookmaker in bookmakers:
        if not isinstance(bookmaker, dict):
            continue
        name = str(bookmaker.get("name") or bookmaker.get("bookmaker") or "Unknown")
        if source_key == "rapid_football_stats":
            markets = bookmaker.get("markets") or {}
            match_odds = markets.get("match_odds") or {}
            values = []
            for side, label in (("home", "Home"), ("draw", "Draw"), ("away", "Away")):
                side_block = match_odds.get(side) or {}
                odd = side_block.get("last_seen") or side_block.get("opening")
                if odd is not None:
                    values.append({"value": label, "odd": odd})
        else:
            values = []
            for side, label in (("home", "Home"), ("draw", "Draw"), ("away", "Away")):
                odd = bookmaker.get(side) or bookmaker.get(f"{side}_odd")
                if odd is not None:
                    values.append({"value": label, "odd": odd})

        used = not first_used
        row = _row_from_match_winner(
            source=source_key,
            bookmaker=name,
            values=values,
            used_in_consensus=used,
        )
        if row:
            rows.append(row)
            if used:
                first_used = True
    return rows


def audit_market_consensus(
    report: Any,
    *,
    supplemental: dict[str, Any] | None = None,
    stored_snapshots: list[dict[str, Any]] | None = None,
) -> MarketConsensusAudit:
    """Build a full read-only audit — does not alter prediction pipeline."""
    from worldcup_predictor.odds.market_consensus_agent import (
        _extract_probs_from_snapshot,
        build_market_consensus,
    )

    supplemental = supplemental or getattr(report, "supplemental_sources", None) or {}
    fixture_id = getattr(report, "fixture_id", None)
    home = getattr(report, "home_team", None)
    away = getattr(report, "away_team", None)
    if hasattr(report, "home_team") and hasattr(report.home_team, "team_name"):
        home = report.home_team.team_name
        away = report.away_team.team_name

    rows = _extract_api_sports_bookmakers(report)
    rows.extend(_extract_rapid_bookmakers(supplemental, "rapid_football_stats"))
    rows.extend(_extract_rapid_bookmakers(supplemental, "rapid_xg_statistics"))

    source_probs: dict[str, dict[str, float]] = {}
    api_meta = extract_api_sports_1x2_meta(report)
    api_probs = api_meta["probs"]
    if api_probs:
        source_probs["api_sports"] = api_probs
    rapid_stats = extract_rapid_football_probs(supplemental)
    if rapid_stats:
        source_probs["rapid_football_stats"] = rapid_stats
    rapid_xg = extract_rapid_xg_probs(supplemental)
    if rapid_xg:
        source_probs["rapid_xg_statistics"] = rapid_xg

    for idx, snap in enumerate(stored_snapshots or []):
        payload = snap.get("payload") if isinstance(snap, dict) else None
        if not isinstance(payload, dict):
            payload = snap if isinstance(snap, dict) else {}
        snap_probs = _extract_probs_from_snapshot(payload)
        if snap_probs:
            source_probs[f"snapshot_{idx}"] = snap_probs

    pre_average: dict[str, float] = {}
    keys = ("home", "draw", "away")
    for key in keys:
        vals = [probs[key] for probs in source_probs.values() if key in probs]
        if vals:
            pre_average[key] = round(sum(vals) / len(vals), 6)

    final = _average_probs(source_probs) if source_probs else {}
    signal = build_market_consensus(
        report,
        supplemental=supplemental,
        stored_snapshots=stored_snapshots,
    )
    old_1x2 = extract_api_sports_probs_first_bookmaker(report)
    new_1x2 = {
        "home": signal.home_implied_probability,
        "draw": signal.draw_implied_probability,
        "away": signal.away_implied_probability,
    }
    new_1x2 = {k: v for k, v in new_1x2.items() if v is not None}
    old_pct = {k: round(v * 100, 1) for k, v in old_1x2.items()}
    new_pct = {k: round(v * 100, 1) for k, v in new_1x2.items()}
    diff_pct = {
        k: round(new_pct.get(k, 0) - old_pct.get(k, 0), 1)
        for k in ("home", "draw", "away")
        if k in old_pct or k in new_pct
    }

    notes: list[str] = []
    api_rows = [r for r in rows if r.source == "api_sports"]
    if len(api_rows) > 1:
        notes.append(
            f"API-Sports returned {len(api_rows)} bookmakers; production now averages all "
            f"({signal.bookmaker_count_1x2} used) via multi_bookmaker_average."
        )
        if old_1x2:
            notes.append(
                f"Old first-bookmaker method ({api_rows[0].bookmaker}): "
                f"Home {old_pct.get('home', 0):.1f}% · Draw {old_pct.get('draw', 0):.1f}% · "
                f"Away {old_pct.get('away', 0):.1f}%."
            )
    if len(source_probs) > 1:
        notes.append(
            f"Final consensus averages {len(source_probs)} source(s), then re-normalizes."
        )
    elif len(source_probs) == 1:
        notes.append("Final consensus equals the single source's normalized probabilities.")
    if not source_probs:
        notes.append("No odds sources available for this fixture.")

    final_pct = {k: round(v * 100, 1) for k, v in final.items()}
    return MarketConsensusAudit(
        fixture_id=int(fixture_id) if fixture_id else None,
        home_team=str(home or "Home"),
        away_team=str(away or "Away"),
        bookmaker_rows=rows,
        source_probs_used=source_probs,
        source_pre_average=pre_average,
        final_consensus=final,
        final_consensus_pct=final_pct,
        final_sum_pct=round(sum(final.values()) * 100, 1) if final else None,
        production_signal={
            "home_implied_probability": signal.home_implied_probability,
            "draw_implied_probability": signal.draw_implied_probability,
            "away_implied_probability": signal.away_implied_probability,
            "sources_used": signal.sources_used,
            "bookmaker_count_1x2": signal.bookmaker_count_1x2,
            "aggregation_method": signal.aggregation_method,
            "bookmaker_disagreement_level": signal.bookmaker_disagreement_level,
            "average_home_odds": signal.average_home_odds,
            "average_draw_odds": signal.average_draw_odds,
            "average_away_odds": signal.average_away_odds,
            "bookmaker_disagreement_score": signal.bookmaker_disagreement_score,
        },
        old_method_1x2=old_1x2,
        old_method_1x2_pct=old_pct,
        new_method_1x2=new_1x2,
        new_method_1x2_pct=new_pct,
        method_difference_pct=diff_pct,
        notes=notes,
    )
