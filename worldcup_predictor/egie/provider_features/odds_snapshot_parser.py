"""Parse stored odds_snapshots payloads into normalized market lines."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

MarketKind = Literal["1x2", "over_under_2_5", "btts", "other"]


@dataclass(frozen=True)
class NormalizedOddsLine:
    fixture_id: int | None
    bookmaker: str
    market_name: str
    selection: str
    odd: float
    source: str
    captured_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _float_odd(value: Any) -> float | None:
    try:
        if value is None:
            return None
        num = float(value)
        return num if num > 1.0 else None
    except (TypeError, ValueError):
        return None


def _implied_prob(odd: float | None) -> float | None:
    if odd is None or odd <= 1.0:
        return None
    return round(1.0 / odd, 6)


def _normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    if not probs:
        return {}
    total = sum(probs.values())
    if total <= 0:
        return probs
    return {k: round(v / total, 4) for k, v in probs.items()}


def _is_match_winner_market(name: str) -> bool:
    n = name.lower().strip()
    return n in {"match winner", "1x2", "ft_result", "match result", "home/draw/away"}


def _is_ou25_market(name: str, selection: str = "") -> bool:
    n = name.lower().strip()
    if any(t in n for t in ("first half", "second half", "corner", "team total")):
        return False
    if "over/under" in n or "goals over" in n or n in {"totals", "total_goals"}:
        sel = selection.lower()
        return "2.5" in sel or not selection
    return False


def _is_btts_market(name: str) -> bool:
    n = name.lower().strip()
    return n in {"both teams score", "btts", "both teams to score"}


def _selection_key_1x2(label: str) -> str | None:
    key = label.lower().strip()
    return {"home": "home", "draw": "draw", "away": "away"}.get(key)


def _selection_key_ou25(label: str) -> str | None:
    key = label.lower().strip()
    if key == "over 2.5":
        return "over_2_5"
    if key == "under 2.5":
        return "under_2_5"
    return None


def _selection_key_btts(label: str) -> str | None:
    key = label.lower().strip()
    if key in {"yes", "btts: yes", "both teams score - yes"}:
        return "yes"
    if key in {"no", "btts: no", "both teams score - no"}:
        return "no"
    return None


def extract_bookmakers_from_payload(payload: Any) -> list[dict[str, Any]]:
    """Collect API-Football-style bookmaker dicts from all known snapshot shapes."""
    if not payload:
        return []
    if isinstance(payload, str):
        return []

    bookmakers: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        api_sports = payload.get("api_sports")
        if isinstance(api_sports, dict):
            inner = api_sports.get("bookmakers")
            if isinstance(inner, list):
                bookmakers.extend(b for b in inner if isinstance(b, dict))

        top = payload.get("bookmakers")
        if isinstance(top, list):
            bookmakers.extend(b for b in top if isinstance(b, dict))

        response = payload.get("response")
        if isinstance(response, list):
            for item in response:
                if not isinstance(item, dict):
                    continue
                inner = item.get("bookmakers")
                if isinstance(inner, list):
                    bookmakers.extend(b for b in inner if isinstance(b, dict))

        the_odds = payload.get("the_odds_api")
        if isinstance(the_odds, dict):
            for bm in the_odds.get("bookmakers") or []:
                if isinstance(bm, dict):
                    bookmakers.append(_the_odds_api_to_api_football_bookmaker(bm))

    elif isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and "bookmakers" in payload[0]:
            for item in payload:
                if isinstance(item, dict):
                    inner = item.get("bookmakers")
                    if isinstance(inner, list):
                        bookmakers.extend(b for b in inner if isinstance(b, dict))
        else:
            bookmakers.extend(b for b in payload if isinstance(b, dict))

    return bookmakers


def _the_odds_api_to_api_football_bookmaker(bm: dict[str, Any]) -> dict[str, Any]:
    """Convert The Odds API bookmaker block to bets/values shape."""
    name = str(bm.get("title") or bm.get("key") or "Unknown")
    bets: list[dict[str, Any]] = []
    for market in bm.get("markets") or []:
        if not isinstance(market, dict):
            continue
        mkey = str(market.get("key") or "").lower()
        if mkey == "h2h":
            bet_name = "Match Winner"
        elif mkey in {"totals", "alternate_totals"}:
            bet_name = "Goals Over/Under"
        elif mkey == "btts":
            bet_name = "Both Teams Score"
        else:
            bet_name = str(market.get("key") or "Market")
        values = []
        for outcome in market.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            label = str(outcome.get("name") or "")
            point = outcome.get("point")
            if mkey in {"totals", "alternate_totals"} and point is not None:
                label = f"{'Over' if label.lower() == 'over' else 'Under'} {point}"
            values.append({"value": label, "odd": str(outcome.get("price") or "")})
        if values:
            bets.append({"name": bet_name, "values": values})
    return {"name": name, "bets": bets}


def normalize_snapshot_odds_lines(
    payload: Any,
    *,
    fixture_id: int | None = None,
    captured_at: str | None = None,
    source: str | None = None,
) -> list[NormalizedOddsLine]:
    """Flatten bookmaker bets into stable normalized lines."""
    if isinstance(payload, dict) and "payload" in payload and "snapshot_at" not in payload:
        payload = payload.get("payload")

    src = source or (payload.get("source") if isinstance(payload, dict) else None) or "unknown"
    stamp = captured_at or (payload.get("snapshot_at") if isinstance(payload, dict) else None)

    lines: list[NormalizedOddsLine] = []
    for bookmaker in extract_bookmakers_from_payload(payload):
        bm_name = str(bookmaker.get("name") or "Unknown")
        for bet in bookmaker.get("bets") or []:
            if not isinstance(bet, dict):
                continue
            market_name = str(bet.get("name") or "")
            for value in bet.get("values") or []:
                if not isinstance(value, dict):
                    continue
                selection = str(value.get("value") or "")
                odd = _float_odd(value.get("odd"))
                if odd is None:
                    continue
                lines.append(
                    NormalizedOddsLine(
                        fixture_id=fixture_id,
                        bookmaker=bm_name,
                        market_name=market_name,
                        selection=selection,
                        odd=odd,
                        source=str(src),
                        captured_at=stamp,
                    )
                )
    return lines


def _aggregate_implied(
    lines: list[NormalizedOddsLine],
    *,
    market_filter,
    selection_mapper,
    min_keys: int = 2,
) -> dict[str, float]:
    per_bm: dict[str, dict[str, float]] = {}
    for line in lines:
        if not market_filter(line.market_name, line.selection):
            continue
        key = selection_mapper(line.selection)
        if key is None:
            continue
        implied = _implied_prob(line.odd)
        if implied is None:
            continue
        per_bm.setdefault(line.bookmaker, {})[key] = implied

    rows = [_normalize_probs(v) for v in per_bm.values() if len(v) >= min_keys]
    if not rows and per_bm:
        rows = [_normalize_probs(v) for v in per_bm.values() if v]
    if not rows:
        return {}

    keys = tuple(rows[0].keys())
    totals = {k: 0.0 for k in keys}
    counts = {k: 0 for k in keys}
    for row in rows:
        for k in keys:
            if k in row:
                totals[k] += row[k]
                counts[k] += 1
    return _normalize_probs({k: totals[k] / counts[k] for k in keys if counts[k] > 0})


def parse_implied_1x2(lines: list[NormalizedOddsLine]) -> dict[str, float]:
    return _aggregate_implied(
        lines,
        market_filter=lambda name, _sel: _is_match_winner_market(name),
        selection_mapper=_selection_key_1x2,
        min_keys=2,
    )


def parse_implied_ou25(lines: list[NormalizedOddsLine]) -> dict[str, float]:
    return _aggregate_implied(
        lines,
        market_filter=lambda name, sel: _is_ou25_market(name, sel) and _selection_key_ou25(sel) is not None,
        selection_mapper=_selection_key_ou25,
        min_keys=1,
    )


def parse_implied_btts(lines: list[NormalizedOddsLine]) -> dict[str, float]:
    return _aggregate_implied(
        lines,
        market_filter=lambda name, _sel: _is_btts_market(name),
        selection_mapper=_selection_key_btts,
        min_keys=1,
    )


def parse_snapshot_payload(
    payload: Any,
    *,
    fixture_id: int | None = None,
    captured_at: str | None = None,
) -> dict[str, float | None]:
    """Parse one snapshot payload into implied probability fields."""
    lines = normalize_snapshot_odds_lines(payload, fixture_id=fixture_id, captured_at=captured_at)
    x12 = parse_implied_1x2(lines)
    ou = parse_implied_ou25(lines)
    btts = parse_implied_btts(lines)
    return {
        "odds_implied_home": x12.get("home"),
        "odds_implied_draw": x12.get("draw"),
        "odds_implied_away": x12.get("away"),
        "odds_implied_over_25": ou.get("over_2_5"),
        "odds_implied_under_25": ou.get("under_2_5"),
        "odds_implied_btts_yes": btts.get("yes"),
        "odds_implied_btts_no": btts.get("no"),
        "normalized_line_count": float(len(lines)),
    }


def has_parseable_1x2(parsed: dict[str, float | None]) -> bool:
    return parsed.get("odds_implied_home") is not None
