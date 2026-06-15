"""Odds movement from SQLite snapshots and RapidAPI opening/last — Phase 36."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.agents.specialists.odds_control_agent import _implied_from_decimal, _safe_float
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.odds.models import OddsMovementSignal

STEAM_MOVE_PCT = 8.0
VOLATILITY_PCT = 15.0


def _pct_move(opening: float | None, latest: float | None) -> float | None:
    if opening is None or latest is None or opening <= 0:
        return None
    return round(((latest - opening) / opening) * 100.0, 2)


def _extract_side_odds_from_rapid(supplemental: dict[str, Any]) -> dict[str, tuple[float | None, float | None]]:
    """Return home/draw/away -> (opening, latest) decimal odds."""
    out: dict[str, tuple[float | None, float | None]] = {
        "home": (None, None),
        "draw": (None, None),
        "away": (None, None),
    }
    block = supplemental.get("rapid_football_stats") or {}
    prematch = block.get("prematch_odds") or {}
    if not isinstance(prematch, dict):
        return out
    for bookmaker in prematch.get("bookmakers") or [prematch]:
        if not isinstance(bookmaker, dict):
            continue
        match_odds = (bookmaker.get("markets") or {}).get("match_odds") or {}
        for side in ("home", "draw", "away"):
            side_block = match_odds.get(side) or {}
            opening = _safe_float(side_block.get("opening"))
            latest = _safe_float(side_block.get("last_seen")) or opening
            if opening is not None:
                out[side] = (opening, latest)
        break
    return out


def _extract_ou_from_rapid(supplemental: dict[str, Any]) -> dict[str, tuple[float | None, float | None]]:
    out: dict[str, tuple[float | None, float | None]] = {
        "over": (None, None),
        "under": (None, None),
    }
    block = supplemental.get("rapid_football_stats") or {}
    prematch = block.get("prematch_odds") or {}
    if not isinstance(prematch, dict):
        return out
    for bookmaker in prematch.get("bookmakers") or [prematch]:
        if not isinstance(bookmaker, dict):
            continue
        total_goals = (bookmaker.get("markets") or {}).get("total_goals") or {}
        line = total_goals.get("2.5") or total_goals.get("2") or {}
        over_block = line.get("over") or {}
        under_block = line.get("under") or {}
        out["over"] = (_safe_float(over_block.get("opening")), _safe_float(over_block.get("last_seen")))
        out["under"] = (_safe_float(under_block.get("opening")), _safe_float(under_block.get("last_seen")))
        break
    return out


def _consensus_from_snapshot_bookmakers(bookmakers: list[Any]) -> dict[str, float]:
    totals = {"home": 0.0, "draw": 0.0, "away": 0.0}
    counts = {"home": 0, "draw": 0, "away": 0}
    for bookmaker in bookmakers:
        if not isinstance(bookmaker, dict):
            continue
        for bet in bookmaker.get("bets", []):
            if bet.get("name") != "Match Winner":
                continue
            for value in bet.get("values", []):
                label = str(value.get("value", "")).lower()
                implied = _implied_from_decimal(value.get("odd"))
                key = {"home": "home", "draw": "draw", "away": "away"}.get(label)
                if key and implied is not None:
                    totals[key] += implied
                    counts[key] += 1
    probs = {k: totals[k] / counts[k] for k in totals if counts[k] > 0}
    return probs


def build_odds_movement(
    *,
    fixture_id: int,
    supplemental: dict[str, Any] | None = None,
    stored_snapshots: list[dict[str, Any]] | None = None,
) -> OddsMovementSignal:
    supplemental = supplemental or {}
    snapshots = stored_snapshots or []
    notes: list[str] = []

    rapid_sides = _extract_side_odds_from_rapid(supplemental)
    rapid_ou = _extract_ou_from_rapid(supplemental)

    home_open, home_latest = rapid_sides["home"]
    draw_open, draw_latest = rapid_sides["draw"]
    away_open, away_latest = rapid_sides["away"]
    over_open, over_latest = rapid_ou["over"]
    under_open, under_latest = rapid_ou["under"]

    if len(snapshots) >= 2:
        first_payload = snapshots[0].get("payload", snapshots[0])
        last_payload = snapshots[-1].get("payload", snapshots[-1])
        first_books = (first_payload.get("api_sports") or {}).get("bookmakers") or []
        last_books = (last_payload.get("api_sports") or {}).get("bookmakers") or []
        first_probs = _consensus_from_snapshot_bookmakers(first_books)
        last_probs = _consensus_from_snapshot_bookmakers(last_books)
        if first_probs and last_probs:
            for side, open_p, latest_p in (
                ("home", first_probs.get("home"), last_probs.get("home")),
                ("draw", first_probs.get("draw"), last_probs.get("draw")),
                ("away", first_probs.get("away"), last_probs.get("away")),
            ):
                if open_p and latest_p:
                    open_dec = 1.0 / open_p
                    latest_dec = 1.0 / latest_p
                    if side == "home" and home_open is None:
                        home_open, home_latest = open_dec, latest_dec
                    elif side == "draw" and draw_open is None:
                        draw_open, draw_latest = open_dec, latest_dec
                    elif side == "away" and away_open is None:
                        away_open, away_latest = open_dec, latest_dec
            notes.append(f"Movement derived from {len(snapshots)} SQLite odds snapshots.")

    home_move = _pct_move(home_open, home_latest)
    draw_move = _pct_move(draw_open, draw_latest)
    away_move = _pct_move(away_open, away_latest)
    over_move = _pct_move(over_open, over_latest)
    under_move = _pct_move(under_open, under_latest)

    moves = {
        "home": home_move,
        "draw": draw_move,
        "away": away_move,
        "over_2_5": over_move,
        "under_2_5": under_move,
    }
    valid_moves = {k: abs(v) for k, v in moves.items() if v is not None}
    strongest = max(valid_moves, key=valid_moves.get) if valid_moves else None

    steam = any(v is not None and abs(v) >= STEAM_MOVE_PCT for v in moves.values())
    volatile = any(v is not None and abs(v) >= VOLATILITY_PCT for v in moves.values())

    drift = None
    if home_move is not None and away_move is not None:
        if home_move < -3 and away_move > 3:
            drift = "Market drifting toward away"
        elif away_move < -3 and home_move > 3:
            drift = "Market drifting toward home"

    movement_confidence = 0.0
    if valid_moves:
        movement_confidence = round(min(100.0, 35.0 + len(valid_moves) * 12.0 + max(valid_moves.values())), 1)

    warning = None
    if len(snapshots) < 2 and not any(v is not None for v in moves.values()):
        warning = "Odds movement unavailable — only one snapshot."
        notes.append(warning)
    elif steam:
        warning = "Steam move detected — market shifting quickly (analysis only)."
    elif volatile:
        warning = "Suspicious volatility in odds movement — interpret cautiously."

    return OddsMovementSignal(
        home_movement=home_move,
        draw_movement=draw_move,
        away_movement=away_move,
        over_movement=over_move,
        under_movement=under_move,
        strongest_move=strongest,
        movement_confidence=movement_confidence,
        warning=warning,
        opening_home_odds=home_open,
        latest_home_odds=home_latest,
        opening_draw_odds=draw_open,
        latest_draw_odds=draw_latest,
        opening_away_odds=away_open,
        latest_away_odds=away_latest,
        steam_move_detected=steam,
        suspicious_volatility=volatile,
        market_drift=drift,
        snapshot_count=len(snapshots),
        notes=notes,
    )


class OddsMovementAgent(BaseAgent):
    """Specialist agent for odds movement — informational only."""

    name = "odds_movement_agent"
    domain = "odds_movement"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        fixture_id = int(kwargs.get("fixture_id") or report.fixture_id)
        supplemental = getattr(report, "supplemental_sources", None) or {}

        snapshots: list[dict[str, Any]] = []
        try:
            repo = FootballIntelligenceRepository()
            snapshots = repo.fetch_odds_snapshots(fixture_id)
            repo.close()
        except Exception:
            snapshots = []

        signal_data = build_odds_movement(
            fixture_id=fixture_id,
            supplemental=supplemental,
            stored_snapshots=snapshots,
        )

        status = "partial" if signal_data.snapshot_count < 2 else "available"
        if signal_data.warning and "unavailable" in signal_data.warning.lower():
            status = "unavailable"

        warnings: list[str] = []
        if signal_data.warning:
            warnings.append(signal_data.warning)
        if signal_data.steam_move_detected:
            warnings.append("Steam move detected — not betting advice.")

        signal = make_signal(
            self.name,
            self.domain,
            status,
            signal_data.to_dict(),
            warnings=warnings,
            missing_data=["odds_snapshots"] if signal_data.snapshot_count < 2 else [],
            impact_score=signal_data.movement_confidence,
            notes="; ".join(signal_data.notes) if signal_data.notes else "Odds movement computed.",
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Odds movement analysis complete")
