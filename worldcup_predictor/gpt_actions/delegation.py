"""Canonical delegation to owner/MCP runtime (no formula reimplementation)."""

from __future__ import annotations

from datetime import date
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    NormalizedOddsLine,
    _is_match_winner_market,
    normalize_snapshot_odds_lines,
)
from worldcup_predictor.mcp_server import runtime as mcp_runtime
from worldcup_predictor.mcp_server.tools import health as health_tools
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.owner_daily.constants import DEFAULT_TIMEZONE, REPORTS_DIR
from worldcup_predictor.gpt_actions.owner_odds import OwnerOddsBudget, controlled_owner_odds_lookup
from worldcup_predictor.gpt_actions.owner_scope import (
    DiscoveryScope,
    PredictionScope,
    competition_keys_for_scope,
    enrich_discovered_fixture,
    fixture_allowed_for_discovery,
    validate_discovery_scope,
    display_labels_for_tier,
)
from worldcup_predictor.forward_evaluation.fixture_model import enrich_unified_fixture, listing_status
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture, discover_fixtures_from_db, vienna_day_utc_bounds


def get_system_status() -> dict[str, Any]:
    payload = health_tools.server_health()
    model = mcp_runtime.model_status()
    return {
        "service": "worldcup-gpt-actions",
        "mcp_bridge": "canonical_runtime",
        "health": payload,
        "model_status": model,
        "git_sha": payload.get("current_git_sha"),
        "reports_dir": str(REPORTS_DIR),
    }


def discover_today_matches(
    *,
    target_date: str,
    timezone: str = DEFAULT_TIMEZONE,
    scope: str = "production",
) -> dict[str, Any]:
    """Prediction candidate discovery — supported Tier A/B per scope (after broad classification)."""
    from worldcup_predictor.gpt_actions.broad_fixture_discovery import discover_prediction_candidates_from_broad

    discovery_scope: DiscoveryScope = validate_discovery_scope(scope)
    return discover_prediction_candidates_from_broad(
        target_date=target_date,
        timezone=timezone,
        scope=discovery_scope,
    )


def list_today_matches_broad(
    *,
    target_date: str,
    timezone: str = DEFAULT_TIMEZONE,
    listing_filter: str = "all",
) -> dict[str, Any]:
    """
    Broad fixture listing — provider + DB discovery with classification.

    Not prediction-gated. Does not require odds or model availability for visibility.
    """
    from worldcup_predictor.gpt_actions.broad_fixture_discovery import discover_broad_fixtures

    payload = discover_broad_fixtures(target_date=target_date, timezone=timezone)
    matches: list[dict[str, Any]] = list(payload.get("matches") or [])
    filt = (listing_filter or "all").strip().lower()
    if filt == "trusted":
        matches = [m for m in matches if m.get("validation_tier") == "A"]
    elif filt in ("test_phase", "test-phase", "b"):
        matches = [m for m in matches if m.get("validation_tier") == "B"]
    elif filt == "prediction_eligible":
        matches = [
            m
            for m in matches
            if m.get("validation_tier") in ("A", "B")
            and m.get("listing_status") not in ("FRIENDLY", "UNSUPPORTED", "ODDS_MISSING")
        ]
    return {
        "date": target_date,
        "timezone": timezone,
        "mode": "broad_listing",
        "listing_filter": filt,
        "audit": payload.get("audit"),
        "count": len(matches),
        "tier_a_count": sum(1 for m in matches if m.get("validation_tier") == "A"),
        "tier_b_count": sum(1 for m in matches if m.get("validation_tier") == "B"),
        "friendly_count": sum(
            1
            for m in matches
            if m.get("listing_status") == "FRIENDLY" or m.get("prediction_support_status") == "FRIENDLY"
        ),
        "unsupported_count": sum(
            1
            for m in matches
            if m.get("listing_status") == "UNSUPPORTED"
            or m.get("prediction_support_status") == "NO_PREDICTION_SUPPORT"
        ),
        "prediction_candidate_count": sum(1 for m in matches if m.get("validation_tier") in ("A", "B")),
        "matches": matches,
    }


def _fixture_from_db(conn, fixture_id: int) -> DailyFixture | None:
    row = conn.execute(
        """SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season
           FROM fixtures WHERE fixture_id=? AND is_placeholder=0 LIMIT 1""",
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    return DailyFixture(
        fixture_id=int(data["fixture_id"]),
        provider_fixture_id=int(data["fixture_id"]),
        competition_key=str(data["competition_key"]),
        home_team=str(data["home_team"]),
        away_team=str(data["away_team"]),
        kickoff_utc=str(data.get("kickoff_utc") or ""),
        status=str(data.get("status") or "NS"),
        season=int(data["season"]) if data.get("season") is not None else None,
    )


def _median_decimal_odds(lines: list[NormalizedOddsLine]) -> dict[str, float | None]:
    per_bm: dict[str, dict[str, float]] = {}
    for line in lines:
        if not _is_match_winner_market(line.market_name):
            continue
        key = line.selection.lower().strip()
        if key not in {"home", "draw", "away"}:
            continue
        per_bm.setdefault(line.bookmaker, {})[key] = float(line.odd)
    if not per_bm:
        return {"home": None, "draw": None, "away": None, "bookmaker_count": 0}
    out: dict[str, float | None] = {}
    for side in ("home", "draw", "away"):
        vals = sorted(r[side] for r in per_bm.values() if side in r)
        out[side] = vals[len(vals) // 2] if vals else None
    return {**out, "bookmaker_count": len(per_bm)}


def _match_odds(conn, fixture_id: int) -> dict[str, float | int | None]:
    snap = get_latest_valid_1x2_odds_snapshot(conn, int(fixture_id))
    if snap.freshness_class in {"ODDS_MISSING", "ODDS_MARKET_NOT_SUPPORTED", "ODDS_INCOMPLETE"}:
        return {"home": None, "draw": None, "away": None, "bookmaker_count": 0}
    return {
        "home": snap.home_odds,
        "draw": snap.draw_odds,
        "away": snap.away_odds,
        "bookmaker_count": snap.bookmaker_count,
        "provider": snap.provider,
        "fetched_at_utc": snap.fetched_at_utc,
        "canonical_row_id": snap.row_id,
        "freshness_class": snap.freshness_class,
    }


def filter_matches_by_odds(
    *,
    target_date: str,
    timezone: str,
    home_odds_gt: float | None = None,
    away_odds_gt: float | None = None,
    scope: str = "production",
) -> dict[str, Any]:
    discovery_scope = validate_discovery_scope(scope)
    discovered = discover_today_matches(target_date=target_date, timezone=timezone, scope=discovery_scope)
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    budget = OwnerOddsBudget()
    filtered: list[dict[str, Any]] = []
    odds_audit: list[dict[str, Any]] = []
    try:
        for match in discovered.get("matches") or []:
            fid = int(match["fixture_id"])
            tier = match.get("tier")
            daily = _fixture_from_db(conn, fid)
            if daily and tier == "B":
                odds_meta = controlled_owner_odds_lookup(
                    daily, tier="B", settings=settings, budget=budget, allow_provider=True
                )
                odds = {
                    "home": odds_meta.get("home"),
                    "draw": odds_meta.get("draw"),
                    "away": odds_meta.get("away"),
                    "bookmaker_count": odds_meta.get("bookmaker_count"),
                }
                odds_audit.append(odds_meta)
            else:
                odds = _match_odds(conn, fid)
                odds_audit.append(
                    {
                        "fixture_id": fid,
                        "tier": tier,
                        "cache_hit": odds.get("bookmaker_count", 0) > 0,
                        "provider_called": False,
                        "odds_found": odds.get("bookmaker_count", 0) > 0,
                        "bookmaker_count": odds.get("bookmaker_count"),
                    }
                )
            if home_odds_gt is not None and (odds["home"] is None or odds["home"] <= home_odds_gt):
                continue
            if away_odds_gt is not None and (odds["away"] is None or odds["away"] <= away_odds_gt):
                continue
            filtered.append({**match, "odds": odds})
        return {
            "date": target_date,
            "timezone": timezone,
            "scope": discovery_scope,
            "filter": {"home_odds_gt": home_odds_gt, "away_odds_gt": away_odds_gt},
            "count": len(filtered),
            "provider_calls": budget.provider_calls,
            "odds_audit": odds_audit,
            "matches": filtered,
        }
    finally:
        conn.close()


def _ecse_mass(scores: list[dict[str, Any]], n: int) -> float | None:
    if not scores:
        return None
    total = sum(float(s.get("probability") or 0) for s in scores[:n])
    return round(total, 6)


def _enrich_odds_block(mcp_result: dict[str, Any], conn, fixture_id: int) -> dict[str, Any]:
    odds_meta = mcp_result.get("odds") or {}
    decimals = _match_odds(conn, fixture_id)
    return {
        "home": decimals.get("home"),
        "draw": decimals.get("draw"),
        "away": decimals.get("away"),
        "bookmaker_count": decimals.get("bookmaker_count"),
        "provider": odds_meta.get("provider"),
        "freshness": odds_meta.get("freshness"),
        "age_minutes": odds_meta.get("age_minutes"),
    }


def format_fixture_evidence(
    mcp_result: dict[str, Any],
    *,
    timezone: str,
    tier_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fixture = mcp_result.get("fixture") or {}
    fixture_id = int(fixture.get("fixture_id") or 0)
    wde = mcp_result.get("wde") or {}
    btts = mcp_result.get("btts") or {}
    ou = mcp_result.get("over_under_2_5") or {}
    ecse_scores = (mcp_result.get("ecse") or {}).get("top_scores") or []
    quality = mcp_result.get("quality") or {}

    top: list[dict[str, Any]] = []
    for item in ecse_scores[:5]:
        top.append(
            {
                "rank": item.get("rank"),
                "score": item.get("score"),
                "probability": item.get("probability"),
            }
        )

    settings = get_settings()
    conn = connect(settings.sqlite_path)
    try:
        odds_block = _enrich_odds_block(mcp_result, conn, fixture_id) if fixture_id else {
            "home": None,
            "draw": None,
            "away": None,
            "bookmaker_count": None,
            "provider": None,
            "freshness": None,
            "age_minutes": None,
        }
    finally:
        conn.close()

    raw_pick = wde.get("decision_pick") or wde.get("prediction")
    effective_pick = wde.get("effective_pick") or raw_pick
    tier = (tier_meta or {}).get("tier") or (tier_meta or {}).get("validation_tier")
    is_shadow = tier == "B" or (tier_meta or {}).get("owner_shadow") is True
    labels = display_labels_for_tier(tier)
    out = {
        "match": f"{fixture.get('home_team')} vs {fixture.get('away_team')}",
        "fixture_id": fixture_id or None,
        "competition": (tier_meta or {}).get("competition") or fixture.get("competition"),
        "kickoff": fixture.get("kickoff_utc"),
        "timezone": timezone,
        "tier": tier,
        "validation_tier": tier,
        "display_status": labels.get("display_status"),
        "display_label": labels.get("display_label"),
        "validation_note": labels.get("validation_note"),
        "prediction_mode": "TIER_B_OWNER_SHADOW" if is_shadow else "TIER_A_PRODUCTION",
        "public_visible": False if is_shadow else True,
        "owner_visible": True,
        "owner_shadow": is_shadow,
        "mapping_quality": (tier_meta or {}).get("mapping_quality"),
        "data_quality": quality.get("status"),
        "odds": odds_block,
        "provider": odds_block.get("provider"),
        "freshness": odds_block.get("freshness"),
        "wde": {
            "home_probability": wde.get("home_probability"),
            "draw_probability": wde.get("draw_probability"),
            "away_probability": wde.get("away_probability"),
            "prediction": raw_pick,
            "decision_pick": raw_pick,
            "effective_pick": effective_pick,
            "probability_argmax": wde.get("probability_argmax"),
            "decision_source": wde.get("decision_source"),
            "confidence": wde.get("confidence"),
            "wde_execution_status": wde.get("wde_execution_status"),
            "wde_result_source": wde.get("wde_result_source"),
            "wde_warning": wde.get("wde_warning"),
            "wde_failure_code": wde.get("wde_failure_code"),
            "wde_failure_stage": wde.get("wde_failure_stage"),
            "wde_failure_dependency": wde.get("wde_failure_dependency"),
            "wde_failure_module": wde.get("wde_failure_module"),
            "wde_failure_message_sanitized": wde.get("wde_failure_message_sanitized"),
            "wde_inputs_available": wde.get("wde_inputs_available"),
            "wde_inputs_missing": wde.get("wde_inputs_missing"),
            "raw_pick": raw_pick,
        },
        "btts": {
            "prediction": btts.get("prediction"),
            "yes_probability": btts.get("yes_probability"),
            "no_probability": btts.get("no_probability"),
            "btts_execution_status": btts.get("btts_execution_status"),
            "btts_failure_code": btts.get("btts_failure_code"),
        },
        "over_under_2_5": {
            "prediction": ou.get("prediction"),
            "over_probability": ou.get("over_probability"),
            "under_probability": ou.get("under_probability"),
            "ou_execution_status": ou.get("ou_execution_status"),
            "ou_failure_code": ou.get("ou_failure_code"),
        },
        "ecse": {
            "top1": top[0] if len(top) > 0 else None,
            "top2": top[1] if len(top) > 1 else None,
            "top3": top[2] if len(top) > 2 else None,
            "top4": top[3] if len(top) > 3 else None,
            "top5": top[4] if len(top) > 4 else None,
            "top3_mass": _ecse_mass(ecse_scores, 3),
            "top5_mass": _ecse_mass(ecse_scores, 5),
        },
        "consensus": quality.get("owner_label"),
        "quality": quality.get("status"),
        "warnings": quality.get("warnings") or [],
    }
    if tier_meta:
        out["prediction_scope"] = tier_meta.get("prediction_scope")
    if mcp_result.get("forward_evaluation"):
        out["forward_evaluation"] = mcp_result["forward_evaluation"]
    return out


def run_predictions_for_fixtures(
    fixture_ids: list[int],
    *,
    refresh_if_stale: bool = False,
    timezone: str = DEFAULT_TIMEZONE,
    prediction_scope: str = "production",
    tier_meta_by_fixture: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for fixture_id in fixture_ids:
        meta = (tier_meta_by_fixture or {}).get(int(fixture_id))
        is_tier_b = (meta or {}).get("tier") == "B"
        raw = mcp_runtime.run_fixture_prediction(
            int(fixture_id),
            refresh_if_stale=refresh_if_stale and not is_tier_b,
        )
        results.append(format_fixture_evidence(raw, timezone=timezone, tier_meta=meta))
    return results


def rank_best_matches(predictions: list[dict[str, Any]], *, select_best: int = 3) -> dict[str, Any]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in predictions:
        conf = (item.get("wde") or {}).get("confidence")
        try:
            score = float(conf) if conf is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    best = [row[1] for row in scored[: max(0, select_best)]]
    ranking = [
        {
            "fixture_id": p.get("fixture_id"),
            "match": p.get("match"),
            "wde_confidence": (p.get("wde") or {}).get("confidence"),
            "wde_pick": (p.get("wde") or {}).get("decision_pick") or (p.get("wde") or {}).get("effective_pick"),
            "ecse_top1": (p.get("ecse") or {}).get("top1"),
        }
        for p in predictions
    ]
    ranking.sort(key=lambda r: float(r.get("wde_confidence") or 0), reverse=True)
    return {"all_match_ranking": ranking, "best_3": best[:3]}


def get_latest_prediction_report(*, max_bytes: int = 200_000) -> dict[str, Any]:
    return mcp_runtime.latest_prediction_report(max_bytes=max_bytes)


def get_prediction_report_by_date(*, report_date: str, max_bytes: int = 200_000) -> dict[str, Any]:
    target = date.fromisoformat(report_date)
    return mcp_runtime.prediction_report_by_date(target, max_bytes=max_bytes)
