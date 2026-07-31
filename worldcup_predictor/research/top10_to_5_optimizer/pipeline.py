"""Top10-to-5 research pipeline — orchestrates all parts, writes artifacts."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.top10_to_5_optimizer import (
    BASELINE_COMMIT,
    PHASE_NAME,
    STATUS_COMPLETE,
    STATUS_HOLD,
    STATUS_RESEARCH_MORE,
)
from worldcup_predictor.research.top10_to_5_optimizer.config import load_config
from worldcup_predictor.research.top10_to_5_optimizer.constants import (
    STATUS_MARKET_INSUFFICIENT,
    STATUS_PARTIAL,
    STATUS_READY,
    STATUS_RESEARCH,
    STATUS_STALE,
    STATUS_UNPRICED,
)
from worldcup_predictor.research.top10_to_5_optimizer.coupon_generator import generate_coupon_universe
from worldcup_predictor.research.top10_to_5_optimizer.evidence import evidence_hash, immutable_flags
from worldcup_predictor.research.top10_to_5_optimizer.exact_consensus import build_consensus_top10, lock_exact_three
from worldcup_predictor.research.top10_to_5_optimizer.forward_shadow import (
    persist_forward_shadow,
    summarize_forward_shadow,
)
from worldcup_predictor.research.top10_to_5_optimizer.historical_backtest import run_historical_backtest
from worldcup_predictor.research.top10_to_5_optimizer.market_pair_search import search_market_pairs
from worldcup_predictor.research.top10_to_5_optimizer.odds_loader import (
    load_real_odds_csv,
    load_real_odds_json,
    markets_from_odds_doc,
)
from worldcup_predictor.research.top10_to_5_optimizer.scenario_engine import evaluate_top10_scenarios
from worldcup_predictor.research.top10_to_5_optimizer.stake_optimizer import allocate_stakes


DEMO_FIXTURES: dict[int, dict[str, Any]] = {
    1556628: {
        "label": "Dundee United vs Rangers",
        "home_team": "Dundee United",
        "away_team": "Rangers",
        "league": "Scottish Premiership",
        "country": "Scotland",
        "kickoff_utc": "2026-07-31T18:45:00Z",
        "kickoff_vienna": "2026-07-31T20:45:00+02:00",
        "actual_score": "0-2",
        "canonical": {
            "scores": [
                {"score": "0-1", "probability": 0.190, "rank": 1},
                {"score": "0-2", "probability": 0.163, "rank": 2},
                {"score": "1-2", "probability": 0.100, "rank": 3},
                {"score": "0-0", "probability": 0.111, "rank": 4},
                {"score": "0-3", "probability": 0.093, "rank": 5},
                {"score": "1-1", "probability": 0.092, "rank": 6},
                {"score": "1-3", "probability": 0.070, "rank": 7},
                {"score": "2-2", "probability": 0.040, "rank": 8},
                {"score": "2-1", "probability": 0.035, "rank": 9},
                {"score": "1-0", "probability": 0.030, "rank": 10},
            ]
        },
        "exact_v2": {
            "scores": [
                {"score": "0-2", "probability": 0.129, "rank": 1},
                {"score": "1-2", "probability": 0.090, "rank": 2},
                {"score": "0-1", "probability": 0.085, "rank": 3},
                {"score": "0-3", "probability": 0.106, "rank": 4},
                {"score": "1-3", "probability": 0.073, "rank": 5},
                {"score": "1-1", "probability": 0.083, "rank": 6},
                {"score": "2-2", "probability": 0.050, "rank": 7},
                {"score": "0-0", "probability": 0.060, "rank": 8},
                {"score": "2-1", "probability": 0.040, "rank": 9},
                {"score": "1-0", "probability": 0.035, "rank": 10},
            ]
        },
    },
    1494717: {
        "label": "Bodo/Glimt vs Lillestrom",
        "home_team": "Bodo/Glimt",
        "away_team": "Lillestrom",
        "league": "Eliteserien",
        "country": "Norway",
        "kickoff_utc": "2026-07-31T17:00:00Z",
        "kickoff_vienna": "2026-07-31T19:00:00+02:00",
        "actual_score": "2-0",
        "canonical": {
            "scores": [
                {"score": "2-0", "probability": 0.193, "rank": 1},
                {"score": "3-0", "probability": 0.152, "rank": 2},
                {"score": "3-1", "probability": 0.090, "rank": 3},
                {"score": "1-0", "probability": 0.162, "rank": 4},
                {"score": "4-0", "probability": 0.090, "rank": 5},
                {"score": "2-1", "probability": 0.080, "rank": 6},
                {"score": "0-0", "probability": 0.068, "rank": 7},
                {"score": "5-0", "probability": 0.050, "rank": 8},
                {"score": "4-1", "probability": 0.040, "rank": 9},
                {"score": "1-1", "probability": 0.035, "rank": 10},
            ]
        },
        "exact_v2": {
            "scores": [
                {"score": "2-0", "probability": 0.156, "rank": 1},
                {"score": "3-0", "probability": 0.153, "rank": 2},
                {"score": "4-0", "probability": 0.112, "rank": 3},
                {"score": "5-0", "probability": 0.066, "rank": 4},
                {"score": "1-0", "probability": 0.065, "rank": 5},
                {"score": "3-1", "probability": 0.070, "rank": 6},
                {"score": "2-1", "probability": 0.060, "rank": 7},
                {"score": "0-0", "probability": 0.040, "rank": 8},
                {"score": "4-1", "probability": 0.035, "rank": 9},
                {"score": "1-1", "probability": 0.030, "rank": 10},
            ]
        },
    },
    1567860: {
        "label": "Admira Wacker vs Rapid Wien II",
        "home_team": "Admira Wacker",
        "away_team": "Rapid Wien II",
        "league": "2. Liga",
        "country": "Austria",
        "kickoff_utc": "2026-07-31T16:00:00Z",
        "kickoff_vienna": "2026-07-31T18:00:00+02:00",
        "actual_score": "1-1",
        "canonical": {
            "scores": [
                {"score": "1-1", "probability": 0.134, "rank": 1},
                {"score": "1-2", "probability": 0.090, "rank": 2},
                {"score": "0-1", "probability": 0.128, "rank": 3},
                {"score": "2-1", "probability": 0.080, "rank": 4},
                {"score": "1-0", "probability": 0.153, "rank": 5},
                {"score": "0-0", "probability": 0.147, "rank": 6},
                {"score": "3-1", "probability": 0.050, "rank": 7},
                {"score": "2-0", "probability": 0.080, "rank": 8},
                {"score": "2-2", "probability": 0.040, "rank": 9},
                {"score": "0-2", "probability": 0.035, "rank": 10},
            ]
        },
        "exact_v2": {
            "scores": [
                {"score": "1-1", "probability": 0.139, "rank": 1},
                {"score": "2-1", "probability": 0.089, "rank": 2},
                {"score": "0-0", "probability": 0.086, "rank": 3},
                {"score": "1-0", "probability": 0.082, "rank": 4},
                {"score": "1-2", "probability": 0.074, "rank": 5},
                {"score": "0-1", "probability": 0.070, "rank": 6},
                {"score": "2-0", "probability": 0.060, "rank": 7},
                {"score": "3-1", "probability": 0.045, "rank": 8},
                {"score": "2-2", "probability": 0.040, "rank": 9},
                {"score": "0-2", "probability": 0.035, "rank": 10},
            ]
        },
    },
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _matrix_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "Top10 Score",
        "Probability",
        "Exact1",
        "Exact2",
        "Exact3",
        "Market1",
        "Market2",
        "Winning Bets",
        "Gross Return",
        "Net P/L",
        "Classification",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def optimize_fixture(
    fixture_id: int,
    payload: dict[str, Any],
    odds_doc: dict[str, Any] | None,
    *,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    top10_source = str(cfg.get("top10_source") or "consensus")
    top10 = build_consensus_top10(payload, top10_source=top10_source, top_n=int(cfg.get("top_n") or 10))
    exact_rows = lock_exact_three(top10)
    exact_scores = [r["scoreline"] for r in exact_rows]
    blockers: list[str] = []

    stake_plan = allocate_stakes(
        mode=str(cfg.get("stake_mode") or "profit_floor"),
        budget=float(cfg.get("fixture_budget_eur") or 25),
        minimum=float(cfg.get("minimum_stake_eur") or 1),
        maximum=float(cfg.get("maximum_stake_eur") or 10),
        step=float(cfg.get("rounding_step_eur") or 0.5),
        exact_probs=[float(r.get("probability") or 0) for r in exact_rows],
        kelly_enabled=bool(cfg.get("fractional_kelly_enabled")),
        kelly_fraction=float(cfg.get("kelly_fraction") or 0.25),
    )

    exact_odds = dict(payload.get("exact_odds") or {})
    # Never fabricate exact odds
    for sc in exact_scores:
        if sc not in exact_odds:
            exact_odds[sc] = None

    market_validation: dict[str, Any] = {"fixture_id": fixture_id, "markets": []}
    markets = []
    if odds_doc is None:
        blockers.append("missing_real_odds")
        status = STATUS_MARKET_INSUFFICIENT
    else:
        markets, market_validation = markets_from_odds_doc(
            odds_doc, top10_scores=[r["scoreline"] for r in top10]
        )
        if market_validation.get("stale_blocked") and cfg.get("stale_odds_block", True):
            blockers.append("stale_odds")
            status = STATUS_STALE
        elif len(markets) < 2:
            blockers.append("fewer_than_two_eligible_markets")
            status = STATUS_MARKET_INSUFFICIENT
        else:
            status = STATUS_RESEARCH

    pair_search = {"n_pairs_evaluated": 0, "selected": None, "candidates": [], "rejected": []}
    scenarios = None
    matrix_rows: list[dict[str, Any]] = []
    if status not in {STATUS_STALE, STATUS_MARKET_INSUFFICIENT} and len(markets) >= 2:
        pair_search = search_market_pairs(
            markets,
            top10=top10,
            exact_scores=exact_scores,
            stake_plan=stake_plan,
            exact_odds=exact_odds,
            weights=dict(cfg.get("pair_score_weights") or {}),
            max_candidates=int(cfg.get("max_market_pair_candidates") or 5000),
        )
        selected = pair_search.get("selected")
        if not selected:
            blockers.append("no_valid_market_pair")
            status = STATUS_MARKET_INSUFFICIENT
        else:
            m1 = selected["market_1"]
            m2 = selected["market_2"]
            scenarios = evaluate_top10_scenarios(
                top10,
                exact_scores=exact_scores,
                market1=m1,
                market2=m2,
                stakes=stake_plan["stakes"],
                exact_odds=exact_odds,
            )
            # Coverage matrix
            for r in scenarios.get("rows") or []:
                sc = r["actual_scoreline"]
                wins = set(r.get("winning_selections") or [])
                matrix_rows.append(
                    {
                        "Top10 Score": sc,
                        "Probability": r.get("probability"),
                        "Exact1": "WIN" if "exact_1" in wins else ("PUSH" if "exact_1" in (r.get("push_selections") or []) else "LOSS"),
                        "Exact2": "WIN" if "exact_2" in wins else ("PUSH" if "exact_2" in (r.get("push_selections") or []) else "LOSS"),
                        "Exact3": "WIN" if "exact_3" in wins else ("PUSH" if "exact_3" in (r.get("push_selections") or []) else "LOSS"),
                        "Market1": "WIN" if "market_1" in wins else ("PUSH" if "market_1" in (r.get("push_selections") or []) else "LOSS"),
                        "Market2": "WIN" if "market_2" in wins else ("PUSH" if "market_2" in (r.get("push_selections") or []) else "LOSS"),
                        "Winning Bets": ",".join(r.get("winning_selections") or []),
                        "Gross Return": r.get("gross_return"),
                        "Net P/L": r.get("net_profit_loss"),
                        "Classification": r.get("classification"),
                    }
                )
            unknown = float(scenarios.get("unknown_mass") or 0)
            profitable = float(scenarios.get("profitable_outcome_coverage_mass") or 0)
            if unknown > 0.5:
                status = STATUS_UNPRICED
            elif profitable > 0 and float(scenarios.get("full_loss_mass") or 0) < float(scenarios.get("top10_probability_mass") or 1):
                status = STATUS_READY if not blockers else STATUS_PARTIAL
            else:
                status = STATUS_PARTIAL

    metrics = {
        "top10_probability_mass": round(sum(float(r.get("probability") or 0) for r in top10), 8),
        "raw_covered_top10_mass": (scenarios or {}).get("raw_outcome_coverage_mass"),
        "profitable_top10_mass": (scenarios or {}).get("profitable_outcome_coverage_mass"),
        "break_even_mass": (scenarios or {}).get("break_even_mass"),
        "partial_recovery_mass": (scenarios or {}).get("partial_recovery_mass"),
        "full_loss_mass": (scenarios or {}).get("full_loss_mass"),
        "estimated_expected_return": (scenarios or {}).get("expected_net"),
        "estimated_roi": None,
        "worst_top10_loss": (scenarios or {}).get("worst_top10_loss"),
        "best_top10_profit": (scenarios or {}).get("best_top10_profit"),
        "total_fixture_budget": stake_plan.get("total_budget"),
    }
    if metrics["estimated_expected_return"] is not None and stake_plan.get("total_budget"):
        metrics["estimated_roi"] = round(
            float(metrics["estimated_expected_return"]) / float(stake_plan["total_budget"]), 8
        )

    coverage_markets = []
    sel = pair_search.get("selected") or {}
    if sel:
        coverage_markets = [sel.get("market_1"), sel.get("market_2")]

    payload_out = {
        "fixture_id": fixture_id,
        "label": payload.get("label"),
        "home_team": payload.get("home_team"),
        "away_team": payload.get("away_team"),
        "league": payload.get("league"),
        "country": payload.get("country"),
        "kickoff_utc": payload.get("kickoff_utc"),
        "kickoff_vienna": payload.get("kickoff_vienna"),
        "top10_source": top10_source,
        "top10": top10,
        "exact_selection": exact_rows,
        "exact_scores": exact_scores,
        "exact_odds": exact_odds,
        "stake_plan": stake_plan,
        "market_validation": market_validation,
        "pair_search": {
            "n_pairs_evaluated": pair_search.get("n_pairs_evaluated"),
            "selected_pair_rank": 1 if sel else None,
            "selected": sel,
            "candidates_preview": (pair_search.get("candidates") or [])[:20],
            "rejected": pair_search.get("rejected") or [],
        },
        "scenarios": scenarios,
        "coverage_matrix": matrix_rows,
        "metrics": metrics,
        "recommendation_status": status,
        "blocker_reasons": blockers,
        "coverage_markets": coverage_markets,
        "actual_score": payload.get("actual_score"),
        "research_only": True,
        "not_deployed": True,
    }
    payload_out["evidence_hash"] = evidence_hash(
        {
            "fixture_id": fixture_id,
            "exact_scores": exact_scores,
            "markets": [m.get("market_key") if isinstance(m, dict) else None for m in coverage_markets],
            "stakes": stake_plan.get("stakes"),
            "top10_source": top10_source,
        }
    )
    return payload_out


def run_top10_to_5_research(
    *,
    fixture_ids: list[int] | None = None,
    fixtures_payload: dict[int, dict[str, Any]] | None = None,
    real_odds_json: str | Path | None = None,
    real_odds_csv: str | Path | None = None,
    output_dir: Path | None = None,
    config_path: str | Path | None = None,
    top10_source: str | None = None,
    stake_mode: str | None = None,
    fixture_budget: float | None = None,
    coupon_ticket_cap: int | None = None,
    forward_shadow: bool = False,
    historical_backtest: bool = True,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/top10_to_5") / f"run_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    cfg = load_config(config_path)
    if top10_source:
        cfg["top10_source"] = top10_source
    if stake_mode:
        cfg["stake_mode"] = stake_mode
    if fixture_budget is not None:
        cfg["fixture_budget_eur"] = float(fixture_budget)
    if coupon_ticket_cap is not None:
        cfg["coupon_ticket_cap"] = int(coupon_ticket_cap)

    payloads = dict(fixtures_payload or DEMO_FIXTURES)
    ids = list(fixture_ids or payloads.keys())
    odds_by: dict[int, dict[str, Any]] = {}
    if real_odds_json:
        odds_by.update(load_real_odds_json(real_odds_json))
    elif Path("data/research/interwetten_three_fixture_markets.json").exists():
        odds_by.update(load_real_odds_json("data/research/interwetten_three_fixture_markets.json"))
    elif Path(
        "worldcup_predictor/research/bet_coverage_optimizer/fixtures/interwetten_three_fixture_markets.json"
    ).exists():
        odds_by.update(
            load_real_odds_json(
                "worldcup_predictor/research/bet_coverage_optimizer/fixtures/interwetten_three_fixture_markets.json"
            )
        )
    if real_odds_csv:
        odds_by.update(load_real_odds_csv(real_odds_csv))

    recommendations = []
    for fid in ids:
        payload = payloads.get(int(fid)) or {"fixture_id": fid}
        payload = {**payload, "fixture_id": int(fid)}
        rec = optimize_fixture(int(fid), payload, odds_by.get(int(fid)), cfg=cfg)
        recommendations.append(rec)

    # Aggregate artifacts
    input_top10 = {str(r["fixture_id"]): r.get("top10") for r in recommendations}
    exact_selection = {str(r["fixture_id"]): r.get("exact_selection") for r in recommendations}
    real_market_validation = {str(r["fixture_id"]): r.get("market_validation") for r in recommendations}
    market_pair_candidates = {
        str(r["fixture_id"]): (r.get("pair_search") or {}).get("candidates_preview") for r in recommendations
    }
    selected_market_pair = {
        str(r["fixture_id"]): (r.get("pair_search") or {}).get("selected") for r in recommendations
    }
    stake_plan = {str(r["fixture_id"]): r.get("stake_plan") for r in recommendations}
    rejected = {str(r["fixture_id"]): (r.get("pair_search") or {}).get("rejected") for r in recommendations}
    scenario_pl = {str(r["fixture_id"]): r.get("scenarios") for r in recommendations}

    # Combined matrix
    all_matrix = []
    for r in recommendations:
        for row in r.get("coverage_matrix") or []:
            all_matrix.append({"fixture_id": r["fixture_id"], **row})
    _matrix_csv(out / "top10_coverage_matrix.csv", all_matrix)

    # Coupon for first 3 fixtures
    coupon = {"error": "need_three_fixtures"}
    if len(recommendations) >= 3:
        fx_sels = []
        for r in recommendations[:3]:
            sels = []
            for i, sc in enumerate(r.get("exact_scores") or [], start=1):
                sels.append(
                    {
                        "selection_id": f"exact_{i}:{sc}",
                        "label": f"Exact {sc}",
                        "decimal_odds": (r.get("exact_odds") or {}).get(sc),
                        "modeled_probability": next(
                            (float(x.get("probability") or 0) for x in (r.get("top10") or []) if x.get("scoreline") == sc),
                            0.05,
                        ),
                    }
                )
            for i, m in enumerate(r.get("coverage_markets") or [], start=1):
                if not m:
                    continue
                sels.append(
                    {
                        "selection_id": f"market_{i}:{m.get('market_key')}",
                        "label": m.get("label"),
                        "decimal_odds": m.get("decimal_odds"),
                        "modeled_probability": float(m.get("modeled_probability") or 0.15),
                    }
                )
            while len(sels) < 5:
                sels.append({"selection_id": f"pad_{len(sels)}", "label": "UNAVAILABLE", "decimal_odds": None, "modeled_probability": 0.0})
            fx_sels.append({"fixture_id": r["fixture_id"], "selections": sels[:5]})
        coupon = generate_coupon_universe(fx_sels, ticket_cap=int(cfg.get("coupon_ticket_cap") or 25))
        coupon_64 = generate_coupon_universe(fx_sels, ticket_cap=64)
        coupon_125 = generate_coupon_universe(fx_sels, ticket_cap=125)
    else:
        coupon_64 = {}
        coupon_125 = {}

    # Historical backtest from recommendations with actuals
    bt_fixtures = []
    for r in recommendations:
        if not r.get("actual_score"):
            continue
        sel = (r.get("pair_search") or {}).get("selected") or {}
        bt_fixtures.append(
            {
                "fixture_id": r["fixture_id"],
                "actual_score": r["actual_score"],
                "top10": r.get("top10"),
                "exact3": r.get("exact_scores"),
                "stakes": (r.get("stake_plan") or {}).get("stakes") or {},
                "exact_odds": r.get("exact_odds") or {},
                "main_market": sel.get("market_1"),
                "insurance_market": sel.get("market_2"),
                "top10_source": r.get("top10_source"),
                "profitable_mass": (r.get("metrics") or {}).get("profitable_top10_mass") or 0,
                "full_loss_mass": (r.get("metrics") or {}).get("full_loss_mass") or 0,
                "selected_pair_families": [
                    (sel.get("market_1") or {}).get("market_type"),
                    (sel.get("market_2") or {}).get("market_type"),
                ],
            }
        )
    if len(recommendations) >= 3:
        bt_fixtures.append(
            {
                "is_coupon_group": True,
                "fixture_selections": fx_sels,
                "total_stake": float(cfg.get("fixture_budget_eur") or 25) * 3,
            }
        )
    backtest = run_historical_backtest(bt_fixtures) if historical_backtest else {"skipped": True}

    # Forward shadow
    forward_summary = {"enabled": False}
    if forward_shadow:
        dbp = out / "top10_to_5_forward_shadow.db"
        for r in recommendations:
            persist_forward_shadow(
                {
                    "fixture_id": r["fixture_id"],
                    "exact_scores": r.get("exact_scores"),
                    "coverage_markets": r.get("coverage_markets"),
                    "stake_plan": r.get("stake_plan"),
                    "coverage_matrix": r.get("coverage_matrix"),
                    "status": r.get("recommendation_status"),
                },
                db_path=dbp,
            )
        forward_summary = summarize_forward_shadow(dbp)
        forward_summary["enabled"] = True
        _write_json(out / "daily_forward_report.json", {"date": ts[:8], "fixtures": [r["fixture_id"] for r in recommendations], **forward_summary})

    # Metrics averages
    def _avg(key: str) -> float | None:
        vals = [float((r.get("metrics") or {}).get(key)) for r in recommendations if (r.get("metrics") or {}).get(key) is not None]
        return round(sum(vals) / len(vals), 8) if vals else None

    priced_n = sum(1 for r in recommendations if r.get("recommendation_status") not in {STATUS_UNPRICED, STATUS_MARKET_INSUFFICIENT, STATUS_STALE})
    hit_rates = []
    for r in recommendations:
        actual = r.get("actual_score")
        if not actual:
            continue
        tops = [x.get("scoreline") for x in (r.get("top10") or [])]
        hit_rates.append(1.0 if str(actual).replace(" ", "") in {str(t).replace(" ", "") for t in tops} else 0.0)

    strat = (backtest.get("strategies") or {}) if isinstance(backtest, dict) else {}

    def _sroi(name: str) -> float | None:
        return ((strat.get(name) or {}).get("priced_monetary") or {}).get("roi")

    # Decision (research statuses only — never deploy)
    t5_roi = _sroi("top10_to_5")
    e3_roi = _sroi("exact3_only")
    avg_prof = _avg("profitable_top10_mass") or 0
    avg_full = _avg("full_loss_mass") or 1
    avg_raw = _avg("raw_covered_top10_mass") or 0
    all_unpriced_monetary = t5_roi is None and e3_roi is None
    if t5_roi is not None and e3_roi is not None and t5_roi > e3_roi and avg_prof > avg_full:
        final_status = STATUS_COMPLETE
        recommendation = (
            "COMPLETE research scaffold with priced edge vs Exact3 on this sample; "
            "still NOT DEPLOYED — owner approval required before any activation."
        )
    elif all_unpriced_monetary and avg_raw >= 0.5:
        final_status = STATUS_RESEARCH_MORE
        recommendation = (
            "RESEARCH_MORE — Top10-to-5 pair search and raw coverage work, but exact-score "
            "odds are missing so monetary ROI is unpriced (no fabricated odds). "
            "Next: attach real exact-score prematch odds and expand historical freezes."
        )
    elif avg_prof > 0.2:
        final_status = STATUS_RESEARCH_MORE
        recommendation = (
            "RESEARCH_MORE — promising profitable mass; expand priced historical corpus before any activation."
        )
    else:
        final_status = STATUS_HOLD
        recommendation = "HOLD — insufficient priced edge vs baselines on current sample."

    summary = {
        "status": final_status,
        "phase": PHASE_NAME,
        "baseline_commit": BASELINE_COMMIT,
        "not_deployed": True,
        **immutable_flags(),
        "artifact_dir": str(out),
        "historical_fixture_count": backtest.get("historical_fixture_count") if isinstance(backtest, dict) else len(bt_fixtures),
        "priced_fixture_count": priced_n,
        "selected_top10_source": cfg.get("top10_source"),
        "average_top10_hit_rate": round(sum(hit_rates) / len(hit_rates), 8) if hit_rates else None,
        "average_raw_covered_mass": _avg("raw_covered_top10_mass"),
        "average_profitable_covered_mass": _avg("profitable_top10_mass"),
        "average_full_loss_mass": _avg("full_loss_mass"),
        "exact3_roi": _sroi("exact3_only"),
        "exact3_main_roi": _sroi("exact3_main"),
        "exact3_main_insurance_roi": _sroi("exact3_main_insurance"),
        "top10_to_5_roi": _sroi("top10_to_5"),
        "optimized_25_ticket_roi": _sroi("optimized_25"),
        "optimized_64_ticket_roi": _sroi("optimized_64"),
        "max_drawdown": ((strat.get("top10_to_5") or {}).get("priced_monetary") or {}).get("max_drawdown"),
        "best_market_pair_families": backtest.get("best_market_pair_families") if isinstance(backtest, dict) else [],
        "forward_shadow_readiness": bool(forward_shadow),
        "recommendation": recommendation,
        "fixture_ids": ids,
    }

    # Write all required artifacts
    _write_json(out / "run_manifest.json", {"ts": ts, "config": cfg, **immutable_flags(), "package_baseline": BASELINE_COMMIT})
    _write_json(out / "input_top10.json", input_top10)
    _write_json(out / "real_market_validation.json", real_market_validation)
    _write_json(out / "exact_selection.json", exact_selection)
    _write_json(out / "market_pair_candidates.json", market_pair_candidates)
    _write_json(out / "selected_market_pair.json", selected_market_pair)
    _write_json(out / "stake_plan.json", stake_plan)
    _write_json(out / "top10_coverage_matrix.json", all_matrix)
    _write_json(out / "scenario_profit_loss.json", scenario_pl)
    _write_json(out / "rejected_market_pairs.json", rejected)
    _write_json(out / "fixture_recommendations.json", recommendations)
    _write_json(out / "coupon_universe_125.json", coupon_125 if coupon_125 else coupon)
    _write_json(out / "optimized_coupon.json", coupon)
    # optimized coupon csv
    with (out / "optimized_coupon.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["rank", "legs", "joint_modeled_probability", "combined_odds", "expected_value", "priced"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in coupon.get("optimized_tickets") or []:
            w.writerow(
                {
                    "rank": t.get("rank"),
                    "legs": " | ".join(t.get("legs") or []),
                    "joint_modeled_probability": t.get("joint_modeled_probability"),
                    "combined_odds": t.get("combined_odds"),
                    "expected_value": t.get("expected_value"),
                    "priced": t.get("priced"),
                }
            )
    _write_json(out / "historical_backtest.json", backtest)
    _write_json(out / "model_source_comparison.json", (backtest.get("model_source_comparison") if isinstance(backtest, dict) else {}))
    _write_json(out / "forward_shadow_summary.json", forward_summary)
    _write_json(out / "validation_report.json", summary)

    md = _dashboard_md(summary, recommendations)
    _write_text(out / "owner_top10_to_5_dashboard.md", md)
    _write_text(out / "owner_top10_to_5_dashboard.html", _dashboard_html(summary))
    report = _final_report(summary, recommendations, backtest)
    _write_text(out / "TOP10_TO_5_PROFIT_AWARE_REPORT.md", report)
    # Root report only for default/demo historical runs (avoid test pollution).
    if fixtures_payload is None:
        Path("TOP10_TO_5_PROFIT_AWARE_REPORT.md").write_text(report, encoding="utf-8")
    return summary


def _dashboard_md(summary: dict[str, Any], recs: list[dict[str, Any]]) -> str:
    lines = [
        "# Owner Top10-to-5 Dashboard",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Top10 source: `{summary.get('selected_top10_source')}`",
        f"- Avg Top10 hit rate: `{summary.get('average_top10_hit_rate')}`",
        f"- Avg profitable mass: `{summary.get('average_profitable_covered_mass')}`",
        f"- Top10-to-5 ROI: `{summary.get('top10_to_5_roi')}`",
        f"- Exact3 ROI: `{summary.get('exact3_roi')}`",
        "",
        "**NOT DEPLOYED**",
        "",
        "## Fixtures",
    ]
    for r in recs:
        lines.append(
            f"- `{r.get('fixture_id')}` status=`{r.get('recommendation_status')}` exacts=`{r.get('exact_scores')}`"
        )
    return "\n".join(lines) + "\n"


def _dashboard_html(summary: dict[str, Any]) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Top10-to-5</title>
<style>body{{font-family:Georgia,serif;background:#102018;color:#e8eef4;margin:2rem}}
h1{{color:#7dd3c0}}.card{{background:#1b2630;padding:1rem;border-left:4px solid #7dd3c0}}
code{{color:#f0c674}}</style></head><body>
<h1>Top10-to-5 Profit-Aware Optimizer</h1>
<div class="card">
<strong>Status:</strong> <code>{summary.get('status')}</code><br/>
<strong>Top10-to-5 ROI:</strong> <code>{summary.get('top10_to_5_roi')}</code><br/>
<strong>Exact3 ROI:</strong> <code>{summary.get('exact3_roi')}</code><br/>
<strong>Avg profitable mass:</strong> <code>{summary.get('average_profitable_covered_mass')}</code><br/>
<strong>Deployment:</strong> NOT DEPLOYED
</div></body></html>
"""


def _final_report(summary: dict[str, Any], recs: list[dict[str, Any]], backtest: Any) -> str:
    return "\n".join(
        [
            "# TOP10_TO_5_PROFIT_AWARE_REPORT",
            "",
            f"**Status:** `{summary.get('status')}`  ",
            f"**Baseline commit:** `{BASELINE_COMMIT}`  ",
            "**Deployment:** NOT DEPLOYED",
            "",
            "## Summary metrics",
            "",
            f"- Historical fixtures: `{summary.get('historical_fixture_count')}`",
            f"- Priced fixtures: `{summary.get('priced_fixture_count')}`",
            f"- Top10 source: `{summary.get('selected_top10_source')}`",
            f"- Avg Top10 hit rate: `{summary.get('average_top10_hit_rate')}`",
            f"- Avg raw covered mass: `{summary.get('average_raw_covered_mass')}`",
            f"- Avg profitable covered mass: `{summary.get('average_profitable_covered_mass')}`",
            f"- Avg full-loss mass: `{summary.get('average_full_loss_mass')}`",
            f"- Exact3 ROI: `{summary.get('exact3_roi')}`",
            f"- Exact3+Main ROI: `{summary.get('exact3_main_roi')}`",
            f"- Exact3+Main+Insurance ROI: `{summary.get('exact3_main_insurance_roi')}`",
            f"- Top10-to-5 ROI: `{summary.get('top10_to_5_roi')}`",
            f"- Optimized 25 ROI: `{summary.get('optimized_25_ticket_roi')}`",
            f"- Optimized 64 ROI: `{summary.get('optimized_64_ticket_roi')}`",
            f"- Max drawdown: `{summary.get('max_drawdown')}`",
            f"- Best pair families: `{summary.get('best_market_pair_families')}`",
            f"- Forward shadow readiness: `{summary.get('forward_shadow_readiness')}`",
            "",
            f"**Recommendation:** {summary.get('recommendation')}",
            "",
            "**NOT DEPLOYED** — no production activation.",
            "",
        ]
    )
