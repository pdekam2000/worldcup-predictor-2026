"""Daily fixture eligibility for two-fixture shadow portfolios."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.correct_score_odds.store import best_odds_map, single_bookmaker_maps
from worldcup_predictor.research.two_fixture_forward_shadow.constants import BOOK_MIN_STAKE
from worldcup_predictor.research.two_fixture_forward_shadow.ddl import ensure_tfps_schema
from worldcup_predictor.research.two_fixture_forward_shadow.windows import parse_utc
from worldcup_predictor.research.two_fixture_portfolio.engine import fixture_profile


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_friendly(league: str | None) -> bool:
    lg = (league or "").lower()
    return "friendly" in lg or "freundschaft" in lg


def classify_fixture(
    conn,
    *,
    fixture_id: int,
    kickoff_utc: str | None,
    league: str | None,
    lambda_home: float | None,
    lambda_away: float | None,
    data_quality: float | None = None,
    has_prediction_freeze: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    ko = parse_utc(kickoff_utc)
    if ko is None:
        return {
            "fixture_id": fixture_id,
            "eligibility": "PORTFOLIO_MAPPING_CONFLICT",
            "reasons": ["missing_kickoff"],
            "top5_mass": None,
            "entropy": None,
            "top5_priced_n": 0,
            "top5_scores": [],
            "profile": None,
        }
    if ko <= now:
        return {
            "fixture_id": fixture_id,
            "eligibility": "PORTFOLIO_POST_KICKOFF",
            "reasons": ["kickoff_passed"],
            "top5_mass": None,
            "entropy": None,
            "top5_priced_n": 0,
            "top5_scores": [],
            "profile": None,
        }
    if _is_friendly(league):
        return {
            "fixture_id": fixture_id,
            "eligibility": "PORTFOLIO_UNSUPPORTED",
            "reasons": ["friendly_excluded"],
            "top5_mass": None,
            "entropy": None,
            "top5_priced_n": 0,
            "top5_scores": [],
            "profile": None,
        }
    if lambda_home is None or lambda_away is None:
        return {
            "fixture_id": fixture_id,
            "eligibility": "PORTFOLIO_LOW_QUALITY",
            "reasons": ["missing_lambdas"],
            "top5_mass": None,
            "entropy": None,
            "top5_priced_n": 0,
            "top5_scores": [],
            "profile": None,
        }
    if not has_prediction_freeze:
        reasons.append("no_prediction_freeze")

    prof = fixture_profile(float(lambda_home), float(lambda_away))
    odds = best_odds_map(conn, fixture_id)
    top5 = prof["top5_scores"]
    priced = sum(1 for s in top5 if s in odds)
    dq = float(data_quality or 0)

    eligibility = "PORTFOLIO_ELIGIBLE"
    if priced < 5:
        eligibility = "PORTFOLIO_ODDS_INCOMPLETE" if priced == 0 else "PORTFOLIO_PARTIAL_ODDS"
        reasons.append(f"top5_priced_{priced}_of_5")
    if prof["suitability"] in {"EXACT_SCORE_WEAK", "NO_PORTFOLIO"} or dq < 0.35:
        if eligibility == "PORTFOLIO_ELIGIBLE":
            eligibility = "PORTFOLIO_LOW_QUALITY"
        reasons.append(f"suitability_{prof['suitability']}")
    if not has_prediction_freeze and eligibility == "PORTFOLIO_ELIGIBLE":
        # allow shadow if CS + lambdas ok but mark partial
        eligibility = "PORTFOLIO_PARTIAL_ODDS"
        reasons.append("awaiting_or_missing_freeze")

    # stale: no prematch lines within 48h of now for this fixture
    last = conn.execute(
        """
        SELECT MAX(fetched_at_utc) AS last_f
        FROM correct_score_odds_lines
        WHERE fixture_id=? AND prematch_status='prematch'
        """,
        (fixture_id,),
    ).fetchone()
    last_f = parse_utc(str(last["last_f"])) if last and last["last_f"] else None
    if last_f is None and priced == 0:
        eligibility = "PORTFOLIO_ODDS_INCOMPLETE"
    elif last_f and (now - last_f).total_seconds() > 48 * 3600 and ko - now < timedelta_hours(36):
        if eligibility == "PORTFOLIO_ELIGIBLE":
            eligibility = "PORTFOLIO_ODDS_STALE"
        reasons.append("odds_stale_gt_48h")

    return {
        "fixture_id": fixture_id,
        "eligibility": eligibility,
        "reasons": reasons,
        "top5_mass": prof["top5_mass"],
        "entropy": prof["entropy"],
        "top5_priced_n": priced,
        "top5_scores": top5,
        "top10_scores": prof["top10_scores"],
        "shifted": prof["shifted_complementary"],
        "profile": prof,
        "cs_odds": {k: float(v["decimal_odds"]) for k, v in odds.items()},
        "bm_maps": single_bookmaker_maps(conn, fixture_id),
        "kickoff_utc": kickoff_utc,
        "league": league,
        "model_p_home": prof["model_p_home"],
        "model_p_draw": prof["model_p_draw"],
        "model_p_away": prof["model_p_away"],
        "book_min_stake": BOOK_MIN_STAKE,
    }


def timedelta_hours(h: float):
    from datetime import timedelta

    return timedelta(hours=h)


def persist_eligibility(conn, report_date: str, rows: list[dict[str, Any]]) -> None:
    ensure_tfps_schema(conn)
    now = _utc_now()
    for r in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO tfps_fixture_eligibility (
                report_date, fixture_id, eligibility, reasons_json, top5_mass, entropy,
                top5_priced_n, kickoff_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_date,
                int(r["fixture_id"]),
                r["eligibility"],
                json.dumps(r.get("reasons") or []),
                r.get("top5_mass"),
                r.get("entropy"),
                r.get("top5_priced_n"),
                r.get("kickoff_utc"),
                now,
            ),
        )
    conn.commit()
