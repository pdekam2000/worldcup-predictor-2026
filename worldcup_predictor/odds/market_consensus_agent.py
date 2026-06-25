"""Market consensus across API-Sports, RapidAPI, and stored snapshots — Phase 36."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.agents.specialists.odds_control_agent import (
    AGGREGATION_METHOD,
    _average_probs,
    _disagreement,
    _implied_from_decimal,
    _normalize_probs,
    extract_api_sports_1x2_meta,
    extract_api_sports_ou25_meta,
    extract_api_sports_probs,
    extract_over_under_probs,
    extract_rapid_football_probs,
    extract_rapid_xg_probs,
)
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.odds.models import AgreementLevel, MarketConsensusSignal


def _decimal_from_implied(prob: float | None) -> float | None:
    if prob is None or prob <= 0:
        return None
    return round(1.0 / prob, 3)


def _average_decimal_odds(source_probs: dict[str, dict[str, float]]) -> dict[str, float | None]:
    keys = ("home", "draw", "away")
    out: dict[str, float | None] = {}
    for key in keys:
        decimals = [_decimal_from_implied(probs.get(key)) for probs in source_probs.values() if key in probs]
        decimals = [d for d in decimals if d is not None]
        out[key] = round(sum(decimals) / len(decimals), 3) if decimals else None
    return out


def _consensus_strength(disagreement: float, source_count: int) -> float:
    if source_count == 0:
        return 0.0
    base = min(100.0, 42.0 + source_count * 14.0)
    penalty = disagreement * 180.0
    return round(max(0.0, min(100.0, base - penalty)), 1)


def _model_selection_key(selection: str | None) -> str | None:
    if not selection:
        return None
    key = selection.lower().replace(" ", "_")
    if key in {"home_win", "home"}:
        return "home"
    if key in {"away_win", "away"}:
        return "away"
    if key == "draw":
        return "draw"
    return key


def _agreement_level(
    model_selection: str | None,
    market_favorite: str,
    consensus: dict[str, float],
) -> AgreementLevel:
    if not model_selection or not consensus:
        return "unknown"
    model_key = _model_selection_key(model_selection)
    if model_key is None:
        return "unknown"
    model_prob = consensus.get(model_key, 0.0)
    fav_prob = consensus.get(market_favorite, 0.0)
    if model_key == market_favorite:
        if model_prob >= 0.45:
            return "high"
        if model_prob >= 0.35:
            return "medium"
        return "low"
    spread = fav_prob - model_prob
    if spread >= 0.18:
        return "low"
    if spread >= 0.08:
        return "medium"
    return "high"


def _extract_probs_from_snapshot(payload: dict[str, Any]) -> dict[str, float]:
    """Best-effort implied probs from a stored odds snapshot payload."""
    class _Report:
        odds = None

        def __init__(self, bookmakers: list[Any]) -> None:
            from worldcup_predictor.domain.intelligence import OddsSnapshot

            self.odds = OddsSnapshot(
                fixture_id=0,
                bookmakers=bookmakers,
                source="snapshot",
                available=bool(bookmakers),
            )

    api_block = payload.get("api_sports") or {}
    bookmakers = api_block.get("bookmakers") or []
    if bookmakers:
        probs = extract_api_sports_probs(_Report(bookmakers))
        if probs:
            return probs

    supplemental = {
        "rapid_football_stats": payload.get("rapid_football_stats") or {},
        "rapid_xg_statistics": payload.get("rapid_xg_statistics") or {},
    }
    for extractor in (extract_rapid_football_probs, extract_rapid_xg_probs):
        probs = extractor(supplemental)
        if probs:
            return probs
    return {}


def build_market_consensus(
    report: Any,
    *,
    supplemental: dict[str, Any] | None = None,
    stored_snapshots: list[dict[str, Any]] | None = None,
    model_selection: str | None = None,
) -> MarketConsensusSignal:
    """Compute market consensus from live report + optional DB snapshots."""
    supplemental = supplemental or getattr(report, "supplemental_sources", None) or {}
    source_probs: dict[str, dict[str, float]] = {}
    sources_used: list[str] = []
    notes: list[str] = []

    api_1x2 = extract_api_sports_1x2_meta(report)
    api_probs = api_1x2["probs"]
    api_ou = extract_api_sports_ou25_meta(report)
    ou_probs = dict(api_ou["probs"])

    if api_probs:
        source_probs["api_sports"] = api_probs
        sources_used.append("api_sports")

    rapid_stats = extract_rapid_football_probs(supplemental)
    if rapid_stats:
        source_probs["rapid_football_stats"] = rapid_stats
        sources_used.append("rapid_football_stats")

    rapid_xg = extract_rapid_xg_probs(supplemental)
    if rapid_xg:
        source_probs["rapid_xg_statistics"] = rapid_xg
        sources_used.append("rapid_xg_statistics")

    for idx, snap in enumerate(stored_snapshots or []):
        payload = snap.get("payload") if isinstance(snap, dict) else None
        if not isinstance(payload, dict):
            payload = snap if isinstance(snap, dict) else {}
        snap_probs = _extract_probs_from_snapshot(payload)
        if snap_probs:
            source_probs[f"snapshot_{idx}"] = snap_probs
            if "sqlite_snapshot" not in sources_used:
                sources_used.append("sqlite_snapshot")

    if not ou_probs:
        ou_probs = extract_over_under_probs(report, supplemental)

    consensus = _average_probs(source_probs) if source_probs else {}
    source_disagreement = _disagreement(source_probs)
    bm_std_1x2 = float(api_1x2.get("std_dev") or 0.0)
    bm_std_ou25 = float(api_ou.get("std_dev") or 0.0)
    bm_level_1x2 = str(api_1x2.get("disagreement_level") or "unknown")
    bm_level_ou25 = str(api_ou.get("disagreement_level") or "unknown")
    disagreement = round(max(source_disagreement, bm_std_1x2, bm_std_ou25), 4)
    avg_odds = _average_decimal_odds(source_probs)
    favorite = max(consensus, key=consensus.get) if consensus else "unknown"
    market_confidence = round(max(consensus.values()) * 100, 1) if consensus else 0.0
    strength = _consensus_strength(disagreement, len(source_probs))
    agreement = _agreement_level(model_selection, favorite, consensus)
    supports_model = agreement in {"high", "medium"} if model_selection else None
    disagreement_warning = bm_level_1x2 == "High" or bm_level_ou25 == "High" or disagreement >= 0.12

    used_bookmakers = list(dict.fromkeys(api_1x2.get("used_bookmakers", []) + api_ou.get("used_bookmakers", [])))
    skipped_bookmakers = list(
        dict.fromkeys(
            [n for n in api_1x2.get("skipped_bookmakers", []) if n not in used_bookmakers]
            + [n for n in api_ou.get("skipped_bookmakers", []) if n not in used_bookmakers]
        )
    )

    if api_1x2.get("bookmaker_count", 0) > 1:
        notes.append(
            f"1X2 market consensus averaged across {api_1x2['bookmaker_count']} bookmakers "
            f"(bookmaker disagreement: {bm_level_1x2})."
        )
    if api_ou.get("bookmaker_count", 0) > 1:
        notes.append(
            f"Over/Under 2.5 averaged across {api_ou['bookmaker_count']} bookmakers "
            f"(bookmaker disagreement: {bm_level_ou25})."
        )
    if disagreement_warning:
        notes.append(
            f"Bookmaker disagreement score {disagreement:.1%} — treat market read cautiously (analysis only)."
        )
    if not source_probs:
        notes.append("No odds sources available for market consensus.")
    elif agreement == "low" and model_selection:
        notes.append("Market disagrees with model selection — review both signals analytically.")
    elif agreement == "high" and model_selection:
        notes.append("Market supports model direction — informational agreement only.")

    return MarketConsensusSignal(
        market_favorite=favorite,
        home_implied_probability=consensus.get("home"),
        draw_implied_probability=consensus.get("draw"),
        away_implied_probability=consensus.get("away"),
        over_2_5_probability=ou_probs.get("over_2_5"),
        under_2_5_probability=ou_probs.get("under_2_5"),
        consensus_strength=strength,
        bookmaker_disagreement_score=disagreement,
        model_market_agreement=agreement,
        market_supports_model=supports_model,
        disagreement_warning=disagreement_warning,
        average_home_odds=avg_odds.get("home"),
        average_draw_odds=avg_odds.get("draw"),
        average_away_odds=avg_odds.get("away"),
        market_confidence_score=market_confidence,
        sources_used=sources_used,
        notes=notes,
        bookmaker_count_1x2=int(api_1x2.get("bookmaker_count") or 0),
        bookmaker_count_ou25=int(api_ou.get("bookmaker_count") or 0),
        used_bookmakers=used_bookmakers,
        skipped_bookmakers=skipped_bookmakers,
        aggregation_method=AGGREGATION_METHOD,
        bookmaker_disagreement_level=bm_level_1x2,
        bookmaker_disagreement_level_ou25=bm_level_ou25,
        bookmaker_std_dev_1x2=bm_std_1x2,
        bookmaker_std_dev_ou25=bm_std_ou25,
    )


class MarketConsensusAgent(BaseAgent):
    """Specialist agent exposing market consensus — not betting advice."""

    name = "market_consensus_agent"
    domain = "market_consensus"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        fixture_id = int(kwargs.get("fixture_id") or report.fixture_id)
        model_selection = None
        baseline_preds = self.context.shared.get("baseline_predictions") or {}
        baseline = baseline_preds.get(fixture_id)
        if baseline is not None:
            model_selection = getattr(getattr(baseline, "one_x_two", None), "selection", None)

        snapshots: list[dict[str, Any]] = []
        try:
            repo = FootballIntelligenceRepository()
            snapshots = repo.fetch_odds_snapshots(fixture_id)
            repo.close()
        except Exception:
            snapshots = []

        signal_data = build_market_consensus(
            report,
            supplemental=getattr(report, "supplemental_sources", None) or {},
            stored_snapshots=snapshots,
            model_selection=model_selection,
        )

        status = "unavailable" if not signal_data.sources_used else "available"
        warnings: list[str] = []
        if signal_data.disagreement_warning:
            warnings.append("Strong bookmaker disagreement detected.")
        if signal_data.model_market_agreement == "low":
            warnings.append("Market disagrees with model — analysis only, not betting advice.")

        signal = make_signal(
            self.name,
            self.domain,
            status,
            signal_data.to_dict(),
            warnings=warnings,
            missing_data=[] if signal_data.sources_used else ["odds"],
            impact_score=signal_data.consensus_strength,
            notes="; ".join(signal_data.notes) if signal_data.notes else "Market consensus computed.",
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Market consensus analysis complete")
