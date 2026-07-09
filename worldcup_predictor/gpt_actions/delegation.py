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
from worldcup_predictor.owner.euro_c_odds_import import _latest_odds_snapshot, is_fake_odds_payload
from worldcup_predictor.owner_daily.constants import DEFAULT_TIMEZONE, REPORTS_DIR
from worldcup_predictor.owner_daily.fixture_discovery import discover_fixtures_from_db, vienna_day_utc_bounds


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


def discover_today_matches(*, target_date: str, timezone: str = DEFAULT_TIMEZONE) -> dict[str, Any]:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    try:
        d = date.fromisoformat(target_date)
        start_utc, end_utc = vienna_day_utc_bounds(d, timezone)
        from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS

        fixtures = discover_fixtures_from_db(
            conn,
            competition_keys=list(DAILY_SUPPORTED_COMPETITIONS),
            start_utc=start_utc,
            end_utc=end_utc,
            limit=500,
        )
        matches = [
            {
                "fixture_id": f.fixture_id,
                "home_team": f.home_team,
                "away_team": f.away_team,
                "kickoff_utc": f.kickoff_utc,
                "competition": f.competition_key,
                "status": f.status,
            }
            for f in fixtures
        ]
        return {"date": target_date, "timezone": timezone, "count": len(matches), "matches": matches}
    finally:
        conn.close()


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
    snap = _latest_odds_snapshot(conn, int(fixture_id))
    if not snap:
        return {"home": None, "draw": None, "away": None, "bookmaker_count": 0}
    payload = snap.get("payload")
    source = None
    if isinstance(payload, dict):
        source = str(payload.get("provider") or payload.get("source") or "")
    if is_fake_odds_payload(payload, source=source):
        return {"home": None, "draw": None, "away": None, "bookmaker_count": 0}
    lines = normalize_snapshot_odds_lines(payload, fixture_id=int(fixture_id))
    return _median_decimal_odds(lines)


def filter_matches_by_odds(
    *,
    target_date: str,
    timezone: str,
    home_odds_gt: float | None = None,
    away_odds_gt: float | None = None,
) -> dict[str, Any]:
    discovered = discover_today_matches(target_date=target_date, timezone=timezone)
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    filtered: list[dict[str, Any]] = []
    try:
        for match in discovered.get("matches") or []:
            fid = int(match["fixture_id"])
            odds = _match_odds(conn, fid)
            if home_odds_gt is not None and (odds["home"] is None or odds["home"] <= home_odds_gt):
                continue
            if away_odds_gt is not None and (odds["away"] is None or odds["away"] <= away_odds_gt):
                continue
            filtered.append({**match, "odds": odds})
        return {
            "date": target_date,
            "timezone": timezone,
            "filter": {"home_odds_gt": home_odds_gt, "away_odds_gt": away_odds_gt},
            "count": len(filtered),
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


def format_fixture_evidence(mcp_result: dict[str, Any], *, timezone: str) -> dict[str, Any]:
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

    raw_pick = wde.get("prediction")
    return {
        "match": f"{fixture.get('home_team')} vs {fixture.get('away_team')}",
        "fixture_id": fixture_id or None,
        "competition": fixture.get("competition"),
        "kickoff": fixture.get("kickoff_utc"),
        "timezone": timezone,
        "odds": odds_block,
        "provider": odds_block.get("provider"),
        "freshness": odds_block.get("freshness"),
        "wde": {
            "home_probability": wde.get("home_probability"),
            "draw_probability": wde.get("draw_probability"),
            "away_probability": wde.get("away_probability"),
            "raw_pick": raw_pick,
            "effective_pick": raw_pick,
            "confidence": wde.get("confidence"),
        },
        "btts": {
            "prediction": btts.get("prediction"),
            "yes_probability": btts.get("yes_probability"),
            "no_probability": btts.get("no_probability"),
        },
        "over_under_2_5": {
            "prediction": ou.get("prediction"),
            "over_probability": ou.get("over_probability"),
            "under_probability": ou.get("under_probability"),
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
        "consensus": None,
        "quality": quality.get("status"),
        "warnings": quality.get("warnings") or [],
    }


def run_predictions_for_fixtures(
    fixture_ids: list[int],
    *,
    refresh_if_stale: bool = False,
    timezone: str = DEFAULT_TIMEZONE,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for fixture_id in fixture_ids:
        raw = mcp_runtime.run_fixture_prediction(int(fixture_id), refresh_if_stale=refresh_if_stale)
        results.append(format_fixture_evidence(raw, timezone=timezone))
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
            "wde_pick": (p.get("wde") or {}).get("effective_pick"),
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
