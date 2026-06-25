"""Enhanced market consensus scoring for national teams (Phase 32B/32E)."""



from __future__ import annotations



from typing import Any



from worldcup_predictor.domain.intelligence import MatchIntelligenceReport

from worldcup_predictor.domain.specialist import MatchSpecialistReport

from worldcup_predictor.intelligence.national_team._shared import clamp, safe_list





def _coerce_source_count(value: Any, *, fallback: int = 1) -> int:

    if value is None:

        return fallback

    if isinstance(value, (list, tuple, set)):

        return max(len(value), fallback)

    try:

        return max(int(value), fallback)

    except (TypeError, ValueError):

        return fallback





def _bookmaker_spread(odds) -> float | None:

    if odds is None or not odds.available:

        return None

    home_odds = draw_odds = away_odds = None

    for bookmaker in safe_list(odds.bookmakers):

        if not isinstance(bookmaker, dict):

            continue

        for bet in safe_list(bookmaker.get("bets")):

            if bet.get("name") != "Match Winner":

                continue

            for value in safe_list(bet.get("values")):

                label = str(value.get("value") or "")

                try:

                    odd = float(value.get("odd"))

                except (TypeError, ValueError):

                    continue

                if label == "Home":

                    home_odds = odd

                elif label == "Draw":

                    draw_odds = odd

                elif label == "Away":

                    away_odds = odd

    if not all([home_odds, draw_odds, away_odds]):

        return None

    inv = [1 / home_odds, 1 / draw_odds, 1 / away_odds]  # type: ignore[operator]

    total = sum(inv)

    probs = [x / total for x in inv]

    fav = max(probs)

    return round((1 - fav) * 100, 1)





def _dampen_specialist_raw(raw: float) -> float:

    """Map specialist 50–100 raw signal into a modest 50–72 band (Phase 32E)."""

    if raw <= 50:

        return 50.0 + raw * 0.12

    return 50.0 + (raw - 50.0) * 0.38





def consensus_strength_score(

    report: MatchIntelligenceReport,

    specialist_report: MatchSpecialistReport | None = None,

) -> tuple[float, dict[str, Any]]:

    base = 55.0

    detail: dict[str, Any] = {"explanation": [], "calibration": "32e"}



    mc = None

    if specialist_report:

        sig = specialist_report.signal("market_consensus_agent")

        if sig and sig.is_usable:

            mc = sig.signals



    if mc:

        raw = float(mc.get("consensus_strength") or 50)

        agreement = mc.get("model_market_agreement")

        disagreement = float(mc.get("disagreement_index") or mc.get("disagreement") or 0)

        source_count = _coerce_source_count(mc.get("source_count"))

        if source_count <= 1:

            source_count = _coerce_source_count(mc.get("sources_used"), fallback=source_count)

        base = _dampen_specialist_raw(raw)

        detail.update(

            {

                "consensus_strength_raw": raw,

                "model_market_agreement": agreement,

                "disagreement_index": disagreement,

                "source_count": source_count,

                "market_favorite": mc.get("market_favorite"),

            }

        )

        if agreement == "high":

            base += 3

        elif agreement == "medium":

            base += 1

        elif agreement == "low":

            base -= 8

        if mc.get("disagreement_warning"):

            base -= 6

        base -= disagreement * 12



    spread = _bookmaker_spread(report.odds)

    bookmakers = len(safe_list(report.odds.bookmakers)) if report.odds and report.odds.available else 0

    detail["bookmaker_count"] = bookmakers

    if spread is not None:

        detail["favorite_margin_pct"] = spread

        if spread <= 8:

            base += 2

        elif spread <= 14:

            base += 1

        elif spread >= 22:

            base -= 4

    if bookmakers >= 5:

        base += min(bookmakers - 4, 6) * 0.2

    elif bookmakers >= 3:

        base += 0.5



    sharp = None

    if specialist_report:

        sharp_sig = specialist_report.signal("sharp_money_intelligence_agent")

        if sharp_sig and sharp_sig.is_usable:

            sharp = sharp_sig.signals

    if sharp:

        sharp_conf = min(float(sharp.get("market_confidence") or sharp.get("consensus_strength") or 55), 85)

        disagreement_level = str(sharp.get("disagreement_level") or "")

        detail["sharp_market_confidence"] = sharp_conf

        detail["sharp_disagreement_level"] = disagreement_level

        base = (base * 0.82) + (sharp_conf * 0.18)

        if disagreement_level in {"High", "Extreme"}:

            base -= 5



    # Exceptional agreement only when multiple signals align — avoid routine 95 saturation

    exceptional = (

        spread is not None

        and spread <= 8

        and bookmakers >= 8

        and (not mc or float(mc.get("disagreement_index") or mc.get("disagreement") or 0) <= 0.05)

    )

    ceiling = 93.0 if exceptional else 82.0

    score = round(clamp(base, 45, ceiling), 1)

    detail["exceptional_agreement"] = exceptional

    detail["score_ceiling"] = ceiling

    if not detail.get("explanation"):

        detail["explanation"] = [

            f"Calibrated consensus {score} from {bookmakers} bookmakers "

            f"(spread {spread}, ceiling {ceiling}).",

        ]

    return score, detail

