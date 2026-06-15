"""Compare odds across API-Sports and supplemental RapidAPI providers."""

from __future__ import annotations

import statistics
from typing import Any, Literal

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence

DisagreementLevel = Literal["Low", "Medium", "High", "unknown"]
AGGREGATION_METHOD = "multi_bookmaker_average"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _implied_from_decimal(odd: Any) -> float | None:
    val = _safe_float(odd)
    if val is None or val <= 1.0:
        return None
    return 1.0 / val


def _normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    if not probs:
        return {}
    total = sum(probs.values())
    if total <= 0:
        return probs
    return {k: round(v / total, 4) for k, v in probs.items()}


def _aggregate_multi_bookmaker(
    normalized_rows: list[dict[str, float]],
    keys: tuple[str, ...],
) -> dict[str, float]:
    if not normalized_rows:
        return {}
    totals = {k: 0.0 for k in keys}
    counts = {k: 0 for k in keys}
    for row in normalized_rows:
        for key in keys:
            if key in row:
                totals[key] += row[key]
                counts[key] += 1
    averaged = {k: totals[k] / counts[k] for k in keys if counts[k] > 0}
    return _normalize_probs(averaged)


def _std_dev_across_bookmakers(
    normalized_rows: list[dict[str, float]],
    keys: tuple[str, ...],
) -> float:
    if len(normalized_rows) < 2:
        return 0.0
    stds: list[float] = []
    for key in keys:
        values = [row[key] for row in normalized_rows if key in row]
        if len(values) >= 2:
            stds.append(statistics.stdev(values))
    return round(max(stds) if stds else 0.0, 4)


def _disagreement_level(std_dev: float) -> DisagreementLevel:
    if std_dev <= 0:
        return "unknown"
    if std_dev < 0.015:
        return "Low"
    if std_dev < 0.035:
        return "Medium"
    return "High"


def _parse_match_winner_implied(bet: dict[str, Any]) -> dict[str, float] | None:
    if bet.get("name") != "Match Winner":
        return None
    implied: dict[str, float] = {}
    for value in bet.get("values", []):
        label = str(value.get("value", "")).lower()
        prob = _implied_from_decimal(value.get("odd"))
        if prob is None:
            continue
        key = {"home": "home", "draw": "draw", "away": "away"}.get(label)
        if key:
            implied[key] = prob
    if len(implied) < 2:
        return None
    return implied


def _is_full_match_ou_market(bet_name: str) -> bool:
    name = bet_name.lower().strip()
    if any(token in name for token in ("first half", "second half", "corner", "team total")):
        return False
    return name in {"goals over/under", "over/under", "match goals over/under"} or (
        "goals over/under" in name and "half" not in name
    )


def _parse_ou25_implied(bet: dict[str, Any]) -> dict[str, float] | None:
    if not _is_full_match_ou_market(str(bet.get("name", ""))):
        return None
    implied: dict[str, float] = {}
    for value in bet.get("values", []):
        label = str(value.get("value", "")).lower().strip()
        prob = _implied_from_decimal(value.get("odd"))
        if prob is None:
            continue
        if label == "over 2.5":
            implied["over_2_5"] = prob
        elif label == "under 2.5":
            implied["under_2_5"] = prob
    if not implied:
        return None
    return implied


def _extract_api_sports_bookmaker_rows(
    report: Any,
    *,
    market: Literal["1x2", "ou25"],
) -> tuple[list[dict[str, float]], list[str], list[str]]:
    """Return normalized per-bookmaker rows, used names, skipped names."""
    odds = getattr(report, "odds", None)
    if odds is None or not odds.available:
        return [], [], []

    normalized_rows: list[dict[str, float]] = []
    used: list[str] = []
    skipped: list[str] = []

    for bookmaker in odds.bookmakers or []:
        if not isinstance(bookmaker, dict):
            continue
        name = str(bookmaker.get("name") or "Unknown")
        parsed: dict[str, float] | None = None
        for bet in bookmaker.get("bets", []):
            if not isinstance(bet, dict):
                continue
            raw = _parse_match_winner_implied(bet) if market == "1x2" else _parse_ou25_implied(bet)
            if raw:
                parsed = _normalize_probs(raw)
                break
        if parsed:
            normalized_rows.append(parsed)
            used.append(name)
        else:
            skipped.append(name)
    return normalized_rows, used, skipped


def extract_api_sports_1x2_meta(report: Any) -> dict[str, Any]:
    rows, used, skipped = _extract_api_sports_bookmaker_rows(report, market="1x2")
    keys = ("home", "draw", "away")
    std_dev = _std_dev_across_bookmakers(rows, keys)
    return {
        "probs": _aggregate_multi_bookmaker(rows, keys),
        "bookmaker_count": len(used),
        "used_bookmakers": used,
        "skipped_bookmakers": skipped,
        "per_bookmaker_normalized": {used[i]: rows[i] for i in range(len(used))},
        "std_dev": std_dev,
        "disagreement_level": _disagreement_level(std_dev),
        "aggregation_method": AGGREGATION_METHOD,
    }


def extract_api_sports_ou25_meta(report: Any) -> dict[str, Any]:
    rows, used, skipped = _extract_api_sports_bookmaker_rows(report, market="ou25")
    keys = ("over_2_5", "under_2_5")
    std_dev = _std_dev_across_bookmakers(rows, keys)
    return {
        "probs": _aggregate_multi_bookmaker(rows, keys),
        "bookmaker_count": len(used),
        "used_bookmakers": used,
        "skipped_bookmakers": skipped,
        "per_bookmaker_normalized": {used[i]: rows[i] for i in range(len(used))},
        "std_dev": std_dev,
        "disagreement_level": _disagreement_level(std_dev),
        "aggregation_method": AGGREGATION_METHOD,
    }


def extract_api_sports_probs_first_bookmaker(report: Any) -> dict[str, float]:
    """Legacy: first bookmaker with Match Winner only — for audit comparison."""
    odds = getattr(report, "odds", None)
    if odds is None or not odds.available:
        return {}
    for bookmaker in odds.bookmakers or []:
        if not isinstance(bookmaker, dict):
            continue
        for bet in bookmaker.get("bets", []):
            raw = _parse_match_winner_implied(bet)
            if raw:
                return _normalize_probs(raw)
    return {}


def extract_api_sports_ou25_first_bookmaker(report: Any) -> dict[str, float]:
    """Legacy: first bookmaker with full-match O/U 2.5 only."""
    odds = getattr(report, "odds", None)
    if odds is None or not odds.available:
        return {}
    for bookmaker in odds.bookmakers or []:
        if not isinstance(bookmaker, dict):
            continue
        for bet in bookmaker.get("bets", []):
            raw = _parse_ou25_implied(bet)
            if raw:
                return _normalize_probs(raw)
    return {}


def extract_api_sports_probs(report: Any) -> dict[str, float]:
    return extract_api_sports_1x2_meta(report)["probs"]


def extract_api_sports_ou25_probs(report: Any) -> dict[str, float]:
    return extract_api_sports_ou25_meta(report)["probs"]

def extract_rapid_football_probs(supplemental: dict[str, Any]) -> dict[str, float]:
    block = supplemental.get("rapid_football_stats") or {}
    odds_payload = block.get("prematch_odds") or block.get("live_odds") or {}
    if isinstance(odds_payload, list):
        odds_payload = odds_payload[0] if odds_payload else {}
    if not isinstance(odds_payload, dict):
        return {}
    bookmakers = odds_payload.get("bookmakers") or [odds_payload]
    for bookmaker in bookmakers:
        if not isinstance(bookmaker, dict):
            continue
        markets = bookmaker.get("markets") or {}
        match_odds = markets.get("match_odds") or {}
        probs: dict[str, float] = {}
        for side in ("home", "draw", "away"):
            side_block = match_odds.get(side) or {}
            implied = _implied_from_decimal(side_block.get("last_seen") or side_block.get("opening"))
            if implied is not None:
                probs[side] = implied
        if probs:
            return _normalize_probs(probs)
    return {}


def extract_rapid_xg_probs(supplemental: dict[str, Any]) -> dict[str, float]:
    block = supplemental.get("rapid_xg_statistics") or {}
    rows = block.get("upcoming_odds") or []
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        probs: dict[str, float] = {}
        for side in ("home", "draw", "away"):
            implied = _implied_from_decimal(row.get(side) or row.get(f"{side}_odd"))
            if implied is not None:
                probs[side] = implied
        if probs:
            return _normalize_probs(probs)
        markets = row.get("markets") or row.get("odds") or {}
        if isinstance(markets, dict):
            match_odds = markets.get("match_odds") or markets.get("1x2") or {}
            for side in ("home", "draw", "away"):
                side_block = match_odds.get(side) if isinstance(match_odds, dict) else None
                if isinstance(side_block, dict):
                    implied = _implied_from_decimal(side_block.get("last_seen") or side_block.get("odd"))
                else:
                    implied = _implied_from_decimal(side_block)
                if implied is not None:
                    probs[side] = implied
            if probs:
                return _normalize_probs(probs)
    return {}


def extract_over_under_probs(report: Any, supplemental: dict[str, Any]) -> dict[str, float]:
    """Return over_2_5 / under_2_5 implied probabilities when available."""
    api_probs = extract_api_sports_ou25_probs(report)
    if api_probs:
        return api_probs

    block = supplemental.get("rapid_football_stats") or {}
    odds_payload = block.get("prematch_odds") or {}
    if isinstance(odds_payload, dict):
        for bookmaker in odds_payload.get("bookmakers") or [odds_payload]:
            if not isinstance(bookmaker, dict):
                continue
            markets = bookmaker.get("markets") or {}
            total_goals = markets.get("total_goals") or {}
            over_block = (total_goals.get("2.5") or total_goals.get("2") or {}).get("over", {})
            under_block = (total_goals.get("2.5") or total_goals.get("2") or {}).get("under", {})
            probs: dict[str, float] = {}
            over_imp = _implied_from_decimal(over_block.get("last_seen") or over_block.get("opening"))
            under_imp = _implied_from_decimal(under_block.get("last_seen") or under_block.get("opening"))
            if over_imp is not None:
                probs["over_2_5"] = over_imp
            if under_imp is not None:
                probs["under_2_5"] = under_imp
            if probs:
                return _normalize_probs(probs)
    return {}


def _average_probs(sources: dict[str, dict[str, float]]) -> dict[str, float]:
    keys = ("home", "draw", "away")
    totals = {k: 0.0 for k in keys}
    counts = {k: 0 for k in keys}
    for probs in sources.values():
        for key in keys:
            if key in probs:
                totals[key] += probs[key]
                counts[key] += 1
    averaged = {k: totals[k] / counts[k] for k in keys if counts[k] > 0}
    return _normalize_probs(averaged)


def _disagreement(sources: dict[str, dict[str, float]]) -> float:
    if len(sources) < 2:
        return 0.0
    keys = ("home", "draw", "away")
    spreads: list[float] = []
    for key in keys:
        values = [probs[key] for probs in sources.values() if key in probs]
        if len(values) >= 2:
            spreads.append(max(values) - min(values))
    return round(max(spreads) if spreads else 0.0, 4)


class OddsControlAgent(BaseAgent):
    """Cross-provider odds comparison — informational only, not betting advice."""

    name = "odds_control_agent"
    domain = "odds_control"

    STRONG_DISAGREEMENT = 0.12

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        supplemental = getattr(report, "supplemental_sources", None) or {}
        source_probs: dict[str, dict[str, float]] = {}
        sources_available: list[str] = []

        api_probs = extract_api_sports_probs(report)
        if api_probs:
            source_probs["api_sports"] = api_probs
            sources_available.append("api_sports")

        rapid_stats_probs = extract_rapid_football_probs(supplemental)
        if rapid_stats_probs:
            source_probs["rapid_football_stats"] = rapid_stats_probs
            sources_available.append("rapid_football_stats")

        rapid_xg_probs = extract_rapid_xg_probs(supplemental)
        if rapid_xg_probs:
            source_probs["rapid_xg_statistics"] = rapid_xg_probs
            sources_available.append("rapid_xg_statistics")

        ou_probs = extract_over_under_probs(report, supplemental)
        consensus = _average_probs(source_probs) if source_probs else {}
        disagreement = _disagreement(source_probs)
        favorite = max(consensus, key=consensus.get) if consensus else "unknown"
        odds_confidence = round(max(consensus.values()) * 100, 1) if consensus else 40.0

        warnings: list[str] = []
        if disagreement >= self.STRONG_DISAGREEMENT:
            warnings.append(
                f"Strong bookmaker/source disagreement ({disagreement:.1%} spread) — treat market read cautiously."
            )
        if not source_probs:
            warnings.append("No odds sources available for cross-check.")

        movement_notes: list[str] = []
        rapid_block = supplemental.get("rapid_football_stats") or {}
        prematch = rapid_block.get("prematch_odds")
        if isinstance(prematch, dict):
            for bookmaker in prematch.get("bookmakers") or [prematch]:
                if not isinstance(bookmaker, dict):
                    continue
                markets = bookmaker.get("markets") or {}
                match_odds = markets.get("match_odds") or {}
                for side in ("home", "draw", "away"):
                    side_block = match_odds.get(side) or {}
                    opening = side_block.get("opening")
                    last_seen = side_block.get("last_seen")
                    if opening and last_seen and opening != last_seen:
                        movement_notes.append(f"{side}: {opening} → {last_seen}")

        status = "unavailable" if not source_probs else ("partial" if len(source_probs) == 1 else "available")

        signal = make_signal(
            self.name,
            self.domain,
            status,
            {
                "sources_available": sources_available,
                "source_probabilities": source_probs,
                "home_implied_probability": consensus.get("home"),
                "draw_implied_probability": consensus.get("draw"),
                "away_implied_probability": consensus.get("away"),
                "over_2_5_implied_probability": ou_probs.get("over_2_5"),
                "under_2_5_implied_probability": ou_probs.get("under_2_5"),
                "bookmaker_disagreement": disagreement,
                "market_favorite": favorite,
                "odds_confidence_signal": odds_confidence,
                "odds_movement": movement_notes or None,
                "strong_disagreement_warning": disagreement >= self.STRONG_DISAGREEMENT,
                "informational_disclaimer": "Odds comparison is informational only — not betting advice.",
            },
            warnings=warnings,
            missing_data=[] if source_probs else ["odds"],
            impact_score=odds_confidence,
            notes="Consensus implied probabilities across available odds providers.",
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Odds control analysis complete")
