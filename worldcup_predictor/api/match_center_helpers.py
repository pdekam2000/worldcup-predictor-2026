"""Match Center API helpers — aggregation and prediction summaries (no engine changes)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from worldcup_predictor.config.competitions import (
    COMPETITION_REGISTRY,
    CompetitionConfig,
    list_competition_keys,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.publication.bet_quality_overlay import (
    build_publication_overlay,
    enrich_summary_with_overlay,
    sanitize_public_summary,
)

_COMPETITION_LOGO: dict[str, str] = {
    "world_cup_2026": "https://media.api-sports.io/football/leagues/1.png",
    "champions_league": "https://media.api-sports.io/football/leagues/2.png",
    "europa_league": "https://media.api-sports.io/football/leagues/3.png",
    "premier_league": "https://media.api-sports.io/football/leagues/39.png",
    "la_liga": "https://media.api-sports.io/football/leagues/140.png",
    "serie_a": "https://media.api-sports.io/football/leagues/135.png",
    "bundesliga": "https://media.api-sports.io/football/leagues/78.png",
    "ligue_1": "https://media.api-sports.io/football/leagues/61.png",
}


def competition_logo_url(comp: CompetitionConfig) -> str | None:
    url = _COMPETITION_LOGO.get(comp.key)
    if url:
        return url
    if comp.league_id > 0:
        return f"https://media.api-sports.io/football/leagues/{comp.league_id}.png"
    return None


_COMPETITION_EMOJI: dict[str, str] = {
    "world_cup_2026": "🏆",
    "champions_league": "🇪🇺",
    "europa_league": "🇪🇺",
    "conference_league": "🇪🇺",
    "premier_league": "🏴",
    "la_liga": "🇪🇸",
    "serie_a": "🇮🇹",
    "bundesliga": "🇩🇪",
    "ligue_1": "🇫🇷",
    "eredivisie": "🇳🇱",
    "primeira_liga": "🇵🇹",
    "super_lig": "🇹🇷",
    "saudi_pro_league": "🇸🇦",
    "mls": "🇺🇸",
}


def competition_emoji(key: str) -> str:
    return _COMPETITION_EMOJI.get(key, "⚽")


def competition_to_api_dict(comp: CompetitionConfig, *, upcoming_count: int = 0) -> dict[str, Any]:
    return {
        "key": comp.key,
        "name": comp.name,
        "country": comp.country,
        "type": comp.compensation_type,
        "season": comp.season,
        "league_id": comp.league_id,
        "enabled": comp.enabled,
        "emoji": competition_emoji(comp.key),
        "logo_url": competition_logo_url(comp),
        "upcoming_count": upcoming_count,
        "supports_table": comp.supports_table,
        "supports_knockout": comp.supports_knockout,
    }


def list_enabled_competitions() -> list[CompetitionConfig]:
    return [COMPETITION_REGISTRY[k] for k in list_competition_keys(enabled_only=True)]


def _parse_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("payload_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def extract_prediction_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Lightweight card summary from stored/cached prediction payload."""
    if not payload:
        return {}

    tier = payload.get("pick_tier") or (payload.get("accuracy_tracking") or {}).get("pick_tier")
    risk = payload.get("risk_level") or "medium"
    no_bet = bool(payload.get("no_bet"))

    pick = (
        payload.get("best_available_pick")
        or payload.get("value_pick")
        or payload.get("safe_pick")
        or payload.get("user_visible_pick")
    )
    market = None
    selection = None
    confidence = payload.get("confidence")
    if isinstance(pick, dict):
        market = pick.get("market") or pick.get("market_id")
        selection = pick.get("pick") or pick.get("selection") or pick.get("label")
        confidence = pick.get("confidence") or pick.get("probability") or confidence
    elif not pick:
        dm = payload.get("detailed_markets") or {}
        mw = dm.get("match_winner") if isinstance(dm, dict) else None
        if isinstance(mw, dict):
            market = mw.get("market") or "1x2"
            selection = mw.get("selection") or mw.get("pick")
            confidence = mw.get("confidence") or mw.get("probability") or confidence
    elif payload.get("prediction") and not no_bet:
        market = "1x2"
        selection = payload.get("prediction")

    # Internal pick resolution (overlay may surface caution pick for no_bet fixtures).
    if no_bet and not selection:
        pass  # overlay derives public_best_pick when market data exists

    stars = 3
    if tier in ("elite", "official", "production_ready"):
        stars = 5
    elif tier in ("value", "paper_ready"):
        stars = 4
    elif tier in ("caution", "research_only"):
        stars = 2
    if no_bet:
        stars = 1

    conf_pct = None
    if confidence is not None:
        try:
            c = float(confidence)
            conf_pct = round(c * 100 if c <= 1 else c, 1)
        except (TypeError, ValueError):
            conf_pct = None

    value_grade = "—"
    if conf_pct is not None:
        if conf_pct >= 80:
            value_grade = "A+"
        elif conf_pct >= 70:
            value_grade = "A"
        elif conf_pct >= 60:
            value_grade = "B"
        else:
            value_grade = "C"

    label_map = {
        "home": "Home Win",
        "away": "Away Win",
        "draw": "Draw",
        "home_win": "Home Win",
        "away_win": "Away Win",
        "over_2_5": "Over 2.5",
        "under_2_5": "Under 2.5",
        "yes": "BTTS Yes",
        "no": "BTTS No",
    }
    best_pick_label = label_map.get(str(selection or "").lower(), selection)
    if market and best_pick_label:
        best_pick_label = f"{market}: {best_pick_label}"

    summary = {
        "best_pick": best_pick_label or None,
        "confidence": conf_pct,
        "value_rating": value_grade,
        "stars": stars,
        "tier": tier,
        "risk_level": risk,
        "is_elite_pick": stars >= 4 and not no_bet,
        "no_bet": no_bet,
    }
    overlay = build_publication_overlay(payload, include_debug=True)
    return enrich_summary_with_overlay(summary, overlay)


def load_prediction_summaries(
    settings: Settings | None = None,
    *,
    competition_key: str | None = None,
) -> dict[int, dict[str, Any]]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    summaries: dict[int, dict[str, Any]] = {}
    keys = [competition_key] if competition_key else list_competition_keys(enabled_only=True)
    for key in keys:
        rows = repo.list_worldcup_stored_predictions(competition_key=key, limit=500, offset=0)
        for row in rows:
            fid = row.get("fixture_id")
            if fid is None:
                continue
            payload = _parse_payload(row)
            if payload:
                summaries[int(fid)] = extract_prediction_summary(payload)
    return summaries


def apply_season_override(comp: CompetitionConfig, season: int | None) -> CompetitionConfig:
    if season is not None:
        return replace(comp, season=season)
    return comp


def load_prediction_payloads(
    settings: Settings | None = None,
    *,
    competition_key: str | None = None,
) -> dict[int, dict[str, Any]]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    payloads: dict[int, dict[str, Any]] = {}
    keys = [competition_key] if competition_key else list_competition_keys(enabled_only=True)

    predops_payloads: dict[int, dict[str, Any]] = {}
    if getattr(settings, "predops_enabled", True):
        try:
            from worldcup_predictor.predops.store import PredOpsStore

            store = PredOpsStore(settings)
            for key in keys:
                for row in repo.list_worldcup_stored_predictions(competition_key=key, limit=500, offset=0):
                    fid = row.get("fixture_id")
                    if fid is not None:
                        snap = store.get_latest_snapshot(int(fid))
                        if snap and isinstance(snap.get("payload"), dict):
                            predops_payloads[int(fid)] = snap["payload"]
        except Exception:
            predops_payloads = {}

    for key in keys:
        for row in repo.list_worldcup_stored_predictions(competition_key=key, limit=500, offset=0):
            fid = row.get("fixture_id")
            if fid is None:
                continue
            fid = int(fid)
            if fid in predops_payloads:
                payload = dict(predops_payloads[fid])
            else:
                payload = _parse_payload(row)
            if payload:
                payload["_store_meta"] = {
                    "predicted_at": row.get("predicted_at"),
                    "source": row.get("source"),
                    "competition_key": row.get("competition_key"),
                    "updated_at": row.get("updated_at"),
                    "predops_snapshot": fid in predops_payloads,
                }
                payloads[fid] = payload
    return payloads


def compute_ai_match_score(
    summary: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    score = 42.0
    if summary:
        conf = float(summary.get("confidence") or 0)
        score += min(28.0, conf * 0.32)
        if summary.get("is_elite_pick"):
            score += 12.0
        if summary.get("no_bet"):
            score -= 18.0
        stars = int(summary.get("stars") or 0)
        score += stars * 2.0

    if payload:
        dq = payload.get("data_quality") or {}
        if isinstance(dq, dict):
            comp_score = dq.get("completeness_score") or dq.get("score") or dq.get("overall_score")
            if comp_score is not None:
                try:
                    c = float(comp_score)
                    score += (c * 100 if c <= 1 else c) * 0.15
                except (TypeError, ValueError):
                    pass
        agents = (payload.get("specialist_summary") or {}).get("agents") or {}
        if isinstance(agents, dict) and agents:
            ok = sum(1 for a in agents.values() if str((a or {}).get("status", "")).lower() in ("ok", "active", "success"))
            score += min(10.0, ok * 1.5)
        if payload.get("sportmonks_xg"):
            score += 4.0
        if (payload.get("weather_intelligence") or {}).get("available"):
            score += 2.0

    score = max(0, min(100, round(score)))
    if score >= 95:
        label = "Elite"
    elif score >= 87:
        label = "Strong"
    elif score >= 73:
        label = "Good"
    elif score >= 58:
        label = "Watch"
    else:
        label = "Skip"
    return {"score": score, "label": label}


def extract_match_insights(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    insights: list[str] = []
    agents = (payload.get("specialist_summary") or {}).get("agents") or {}
    if isinstance(agents, dict):
        form = agents.get("form") or agents.get("form_agent")
        if form and str(form.get("status", "")).lower() in ("ok", "active", "success"):
            insights.append("Strong home form")
        lineup = agents.get("lineup") or agents.get("lineup_agent") or agents.get("expected_lineup_agent")
        if lineup and str(lineup.get("status", "")).lower() in ("ok", "active", "success"):
            insights.append("Lineup advantage")
        odds = agents.get("odds") or agents.get("odds_market_agent")
        if odds and str(odds.get("status", "")).lower() in ("ok", "active", "success"):
            insights.append("Odds movement")
    xg = payload.get("sportmonks_xg")
    if isinstance(xg, dict) and xg:
        insights.append("xG advantage")
    pressure = payload.get("pressure_intelligence") or payload.get("sportmonks_pressure")
    if pressure:
        insights.append("Pressure advantage")
    if payload.get("head_to_head") or payload.get("h2h"):
        insights.append("Historical H2H")
    return insights[:6]


def fixture_status_label(
    *,
    bucket: str | None,
    status: str | None,
    has_prediction: bool,
    payload: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
) -> str:
    b = str(bucket or "").lower()
    st = str(status or "").upper()
    if b == "live" or st in {"1H", "HT", "2H", "ET", "LIVE"}:
        return "Live"
    if b == "finished" or st in {"FT", "AET", "PEN"}:
        tracking = (payload or {}).get("accuracy_tracking") or {}
        if tracking.get("evaluated") or tracking.get("result"):
            return "Evaluated"
        return "Finished"
    if has_prediction:
        if not summary.get("best_pick") and not summary.get("publication_overlay", {}).get("public_best_pick"):
            return "Awaiting pick"
        return "Prediction Ready"
    if payload and (payload.get("detailed_markets") or {}).get("lineup"):
        return "Prediction Updating"
    return "Waiting for Lineups"


def extract_owner_meta(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    meta = payload.get("_store_meta") or {}
    return {
        "prediction_version": payload.get("pipeline_version") or payload.get("version"),
        "engine_version": payload.get("engine_version") or "production-wde",
        "cache_age_hint": meta.get("updated_at") or meta.get("predicted_at"),
        "data_source": meta.get("source") or payload.get("source_label"),
        "api_provider": payload.get("provider") or "api-football",
        "prediction_generated_at": meta.get("predicted_at"),
        "competition_key": meta.get("competition_key"),
    }


def enrich_match_row(
    base: dict[str, Any],
    *,
    summary: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    include_insights: bool = True,
    include_owner_meta: bool = False,
) -> dict[str, Any]:
    row = dict(base)
    if summary:
        if not include_owner_meta:
            summary = sanitize_public_summary(summary)
        row["prediction_summary"] = summary
    ai = compute_ai_match_score(summary, payload)
    row["ai_match_score"] = ai
    row["fixture_status_label"] = fixture_status_label(
        bucket=row.get("bucket"),
        status=row.get("status"),
        has_prediction=bool(row.get("has_prediction")),
        payload=payload,
        summary=summary,
    )
    if include_insights:
        row["match_insights"] = extract_match_insights(payload)
    if include_owner_meta:
        row["owner_meta"] = extract_owner_meta(payload)
    return row


def get_todays_elite_picks(
    matches: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()

    def _kickoff_date(m: dict[str, Any]):
        raw = m.get("date") or m.get("match_date")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            return None

    candidates = []
    for m in matches:
        if _kickoff_date(m) != today:
            continue
        summary = m.get("prediction_summary") or {}
        ai = m.get("ai_match_score") or {}
        if not summary.get("best_pick") and not (summary.get("publication_overlay") or {}).get("public_best_pick"):
            continue
        if summary.get("no_bet") and summary.get("display_status") != "caution_best_available":
            # Owner path may still filter strict elite; public uses overlay pick
            if summary.get("publication_overlay", {}).get("public_recommendation_status") != "caution_best_available":
                continue
        candidates.append(m)

    candidates.sort(
        key=lambda m: (
            -(m.get("ai_match_score") or {}).get("score", 0),
            -(m.get("prediction_summary") or {}).get("confidence", 0) or 0,
        )
    )
    return candidates[:limit]
