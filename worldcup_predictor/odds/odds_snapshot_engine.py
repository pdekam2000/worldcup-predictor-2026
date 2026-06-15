"""API-Football odds snapshot tracking — first vs latest, never overwrites history."""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.agents.specialists.odds_control_agent import (
    _implied_from_decimal,
    _is_full_match_ou_market,
    _parse_match_winner_implied,
)
from worldcup_predictor.odds.models import OddsSnapshotTrack, OutcomeOddsTrack

MovementClass = Literal["Stable", "Small Move", "Moderate Move", "Large Move", "Extreme Move"]


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_movement(abs_pct: float | None) -> MovementClass:
    if abs_pct is None:
        return "Stable"
    if abs_pct < 2.0:
        return "Stable"
    if abs_pct < 5.0:
        return "Small Move"
    if abs_pct < 10.0:
        return "Moderate Move"
    if abs_pct < 15.0:
        return "Large Move"
    return "Extreme Move"


def _pct_move(opening: float | None, latest: float | None) -> float | None:
    if opening is None or latest is None or opening <= 0:
        return None
    return round(((latest - opening) / opening) * 100.0, 2)


def _movement_direction(pct: float | None) -> str | None:
    if pct is None or abs(pct) < 0.5:
        return "stable"
    return "drifting" if pct > 0 else "shortening"


def _parse_ou25_decimal(bet: dict[str, Any]) -> dict[str, float]:
    if not _is_full_match_ou_market(str(bet.get("name", ""))):
        return {}
    out: dict[str, float] = {}
    for value in bet.get("values", []):
        label = str(value.get("value", "")).lower().strip()
        odd = _safe_float(value.get("odd"))
        if odd is None or odd <= 1.0:
            continue
        if label == "over 2.5":
            out["over_2_5"] = odd
        elif label == "under 2.5":
            out["under_2_5"] = odd
    return out


def _avg_decimal_from_api_sports_bookmakers(bookmakers: list[Any]) -> dict[str, float]:
    """Average decimal odds across API-Football bookmakers."""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for bookmaker in bookmakers:
        if not isinstance(bookmaker, dict):
            continue
        for bet in bookmaker.get("bets", []):
            if not isinstance(bet, dict):
                continue
            match_winner = _parse_match_winner_implied(bet)
            if match_winner:
                for key, implied in match_winner.items():
                    decimal = 1.0 / implied if implied > 0 else None
                    if decimal and decimal > 1.0:
                        totals[key] = totals.get(key, 0.0) + decimal
                        counts[key] = counts.get(key, 0) + 1
                continue
            ou = _parse_ou25_decimal(bet)
            for key, decimal in ou.items():
                totals[key] = totals.get(key, 0.0) + decimal
                counts[key] = counts.get(key, 0) + 1
    return {k: round(totals[k] / counts[k], 3) for k in totals if counts.get(k, 0) > 0}


def _bookmakers_from_report(report: Any) -> list[Any]:
    odds = getattr(report, "odds", None)
    if odds is None or not getattr(odds, "available", False):
        return []
    return list(odds.bookmakers or [])


def _bookmakers_from_snapshot_payload(payload: dict[str, Any]) -> list[Any]:
    api = payload.get("api_sports") or {}
    books = api.get("bookmakers") or []
    return books if isinstance(books, list) else []


def _build_outcome_track(opening: float | None, latest: float | None) -> OutcomeOddsTrack:
    pct = _pct_move(opening, latest)
    return OutcomeOddsTrack(
        opening_odds=opening,
        latest_odds=latest,
        movement_pct=pct,
        movement_direction=_movement_direction(pct),
        movement_class=_classify_movement(abs(pct) if pct is not None else None),
    )


def build_odds_snapshot_track(
    report: Any,
    *,
    stored_snapshots: list[dict[str, Any]] | None = None,
) -> OddsSnapshotTrack:
    """Track 1X2 and O/U 2.5 from API-Football snapshots + current report."""
    snapshots = stored_snapshots or []
    opening_avg: dict[str, float] = {}
    latest_avg: dict[str, float] = {}

    api_only_snapshots = [
        s for s in snapshots if _bookmakers_from_snapshot_payload(s.get("payload", s))
    ]

    if api_only_snapshots:
        first_books = _bookmakers_from_snapshot_payload(api_only_snapshots[0].get("payload", {}))
        last_books = _bookmakers_from_snapshot_payload(api_only_snapshots[-1].get("payload", {}))
        opening_avg = _avg_decimal_from_api_sports_bookmakers(first_books)
        latest_avg = _avg_decimal_from_api_sports_bookmakers(last_books)

    current_books = _bookmakers_from_report(report)
    if current_books:
        current_avg = _avg_decimal_from_api_sports_bookmakers(current_books)
        if not opening_avg:
            opening_avg = dict(current_avg)
        latest_avg = current_avg

    if not opening_avg and not latest_avg:
        empty = OutcomeOddsTrack(None, None, None, None, "Stable")
        return OddsSnapshotTrack(
            home=empty,
            draw=empty,
            away=empty,
            over_2_5=empty,
            under_2_5=empty,
            snapshot_count=len(api_only_snapshots),
            history_available=False,
        )

    if not opening_avg:
        opening_avg = dict(latest_avg)
    if not latest_avg:
        latest_avg = dict(opening_avg)

    return OddsSnapshotTrack(
        home=_build_outcome_track(opening_avg.get("home"), latest_avg.get("home")),
        draw=_build_outcome_track(opening_avg.get("draw"), latest_avg.get("draw")),
        away=_build_outcome_track(opening_avg.get("away"), latest_avg.get("away")),
        over_2_5=_build_outcome_track(opening_avg.get("over_2_5"), latest_avg.get("over_2_5")),
        under_2_5=_build_outcome_track(opening_avg.get("under_2_5"), latest_avg.get("under_2_5")),
        snapshot_count=len(api_only_snapshots),
        history_available=len(api_only_snapshots) >= 1 or bool(current_books),
    )
