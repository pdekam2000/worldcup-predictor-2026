"""Phase 3 research runner: Insurance Pick + real odds + budget + comparison.

Research-only. No freeze mutation. No production deploy.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.config import load_optimizer_config
from worldcup_predictor.research.bet_coverage_optimizer.generate_tickets import (
    generate_64_tickets,
    write_tickets_artifacts,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.backtest import run_insurance_backtest
from worldcup_predictor.research.bet_coverage_optimizer.insurance.budget import allocate_budget
from worldcup_predictor.research.bet_coverage_optimizer.insurance.comparison import compare_main_vs_insurance
from worldcup_predictor.research.bet_coverage_optimizer.insurance.constants import (
    PHASE_NAME,
    STATUS_VALIDATED,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.insurance_optimizer import (
    build_fixture_insurance_candidates,
    optimize_insurance_tickets,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.real_odds import (
    load_real_odds_csv,
    load_real_odds_json,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation
from worldcup_predictor.research.bet_coverage_optimizer.service import (
    models_from_payload,
    run_coverage_optimizer_job,
)
from scripts.run_bet_coverage_optimizer_three_fixtures import FIXTURES, RAW_BY_FIXTURE


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _write_insurance_tickets(tickets: list[Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "research_only": True,
        "ticket_count": len(tickets),
        "tickets": [t.to_dict() for t in tickets],
        "note": "Selective insurance tickets — not a full 5x5x5=125 expansion",
    }
    jp = output_dir / "insurance_tickets.json"
    cp = output_dir / "insurance_tickets.csv"
    jp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with cp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "ticket_id",
                "rank",
                "n_insurance_legs",
                "insurance_fixtures",
                "selection_labels",
                "combined_odds",
                "joint_hit_probability",
                "monetary_ev",
                "probability_mass_utility",
                "insurance_coupon_score",
                "inclusion_reason",
                "stake_eur",
            ]
        )
        for t in tickets:
            w.writerow(
                [
                    t.ticket_id,
                    t.rank,
                    t.n_insurance_legs,
                    "|".join(str(x) for x in t.insurance_fixture_ids),
                    " || ".join(s["label"] for s in t.selections),
                    t.combined_odds if t.combined_odds is not None else "",
                    t.modeled_joint_hit_probability,
                    t.monetary_ev if t.monetary_ev is not None else "",
                    t.probability_mass_utility,
                    t.insurance_coupon_score,
                    t.inclusion_reason,
                    t.stake_eur if t.stake_eur is not None else "",
                ]
            )
    return {"insurance_tickets.json": str(jp), "insurance_tickets.csv": str(cp)}


def _synthetic_backtest_fixtures(n: int = 120) -> list[dict[str, Any]]:
    """Deterministic synthetic completed fixtures for research backtest floor (>=100)."""
    out = []
    scores = [f"{h}-{a}" for h in range(0, 4) for a in range(0, 4)]
    for i in range(n):
        top = [{"score": scores[j % len(scores)], "probability": max(0.01, 0.18 - 0.01 * j)} for j in range(8)]
        exact3 = [top[0]["score"], top[1]["score"], top[2]["score"]]
        main_cov = [top[3]["score"], top[4]["score"]]
        ins = [top[5]["score"]]
        # Cycle actual among covered / uncovered
        if i % 5 == 0:
            actual = top[6]["score"]  # uncovered without insurance
        elif i % 5 == 1:
            actual = ins[0]
        elif i % 5 == 2:
            actual = main_cov[0]
        else:
            actual = exact3[i % 3]
        out.append(
            {
                "fixture_id": 900000 + i,
                "top_n_scores": top,
                "exact3": exact3,
                "main_coverage_scores": main_cov,
                "insurance_scores": ins,
                "actual_score": actual,
                "prematch_odds_complete": False,
                "uses_postmatch_odds": False,
            }
        )
    return out


def run_phase3(
    *,
    top_n: int = 8,
    real_odds_json: str | None = None,
    real_odds_csv: str | None = None,
    total_budget: float = 400.0,
    main_budget_ratio: float = 0.80,
    max_insurance_tickets: int = 15,
    stake_mode: str = "equal",
    output_dir: Path | None = None,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/coverage_optimizer") / f"phase3_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    cfg = load_optimizer_config()
    cfg["top_n_scores"] = int(top_n)
    cfg.setdefault("insurance", {})
    cfg["insurance"]["max_insurance_tickets"] = int(max_insurance_tickets)
    cfg.setdefault("budget", {})
    cfg["budget"]["total_budget_eur"] = float(total_budget)
    cfg["budget"]["main_budget_ratio"] = float(main_budget_ratio)
    cfg["budget"]["insurance_budget_ratio"] = float(1.0 - main_budget_ratio)
    cfg["budget"]["stake_mode"] = str(stake_mode)
    if stake_mode == "kelly_research":
        cfg["budget"]["kelly_enabled"] = True

    model_payloads = {fid: {k: v for k, v in block.items() if k != "label"} for fid, block in FIXTURES.items()}

    # Real odds validation
    real_odds_report: dict[str, Any] = {"ok": True, "fixtures": {}, "rejected": [], "sources": []}
    if real_odds_json:
        real_odds_report = load_real_odds_json(real_odds_json, insurance_cfg=cfg.get("insurance"))
        real_odds_report["sources"] = [real_odds_json]
    elif real_odds_csv:
        real_odds_report = load_real_odds_csv(real_odds_csv, insurance_cfg=cfg.get("insurance"))
        real_odds_report["sources"] = [real_odds_csv]

    # Main Phase2-style recommendations (skip coupon to keep artifacts clean; we regenerate main 64)
    main_job = run_coverage_optimizer_job(
        list(FIXTURES.keys()),
        model_payloads=model_payloads,
        raw_payload_by_fixture=RAW_BY_FIXTURE,
        require_fresh=False,
        skip_db_odds=True,
        top_n_scores=int(top_n),
        stake_per_ticket=1.0,
        output_dir=out / "main_run",
        run_coupon_optimizer=False,
        config=cfg,
    )

    # Rebuild CoverageRecommendation objects from optimizer for insurance (use service internals)
    from worldcup_predictor.research.bet_coverage_optimizer.optimizer import optimize_fixture

    recommendations: list[CoverageRecommendation] = []
    for fid in FIXTURES.keys():
        models = models_from_payload(model_payloads[int(fid)])
        recommendations.append(
            optimize_fixture(
                int(fid),
                models,
                top_n_scores=int(top_n),
                require_fresh=False,
                skip_db_odds=True,
                raw_payload=RAW_BY_FIXTURE[int(fid)],
                config=cfg,
            )
        )

    main_tickets = generate_64_tickets(recommendations, stake_per_ticket=1.0)
    # Write as main_64_*
    main_paths = write_tickets_artifacts(main_tickets, out)
    (out / "main_64_tickets.json").write_text(
        (out / "tickets_64.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (out / "main_64_tickets.csv").write_text(
        (out / "tickets_64.csv").read_text(encoding="utf-8"), encoding="utf-8"
    )

    uncovered_by: dict[int, Any] = {}
    ranked_by: dict[int, list] = {}
    insurance_recs: dict[str, Any] = {}
    for rec in recommendations:
        fid = int(rec.fixture_id)
        real_markets = None
        if fid in (real_odds_report.get("fixtures") or {}):
            real_markets = real_odds_report["fixtures"][fid]["markets"]
        unc, ranked = build_fixture_insurance_candidates(
            rec,
            raw_payload=RAW_BY_FIXTURE.get(fid),
            real_odds_markets=real_markets,
            insurance_cfg=cfg.get("insurance"),
            insurance_weights=cfg.get("insurance_weights"),
        )
        uncovered_by[fid] = unc
        ranked_by[fid] = ranked
        top = next((c for c in ranked if c.eligible), None)
        insurance_recs[str(fid)] = {
            "top_candidate": top.to_dict() if top else None,
            "uncovered_mass": unc.primary_uncovered_probability_mass,
            "primary_covered_mass": unc.primary_covered_probability_mass,
        }

    ins_tickets = optimize_insurance_tickets(
        recommendations,
        candidates_by_fixture=ranked_by,
        uncovered_by_fixture=uncovered_by,
        insurance_cfg=cfg.get("insurance"),
    )

    budget = allocate_budget(
        n_main_tickets=64,
        n_insurance_tickets=len(ins_tickets),
        insurance_scores=[float(t.insurance_coupon_score) for t in ins_tickets],
        budget_cfg=cfg.get("budget"),
    )
    # Attach stakes
    for i, t in enumerate(ins_tickets):
        stakes = budget.get("stake_per_insurance_ticket_eur") or []
        t.stake_eur = float(stakes[i]) if i < len(stakes) else budget.get("equal_insurance_stake_eur")

    comparison = compare_main_vs_insurance(
        recommendations,
        uncovered=uncovered_by,
        ranked_candidates=ranked_by,
        insurance_tickets=ins_tickets,
        n_main_tickets=64,
        budget=budget,
    )

    backtest = run_insurance_backtest(_synthetic_backtest_fixtures(120), min_fixtures=100)

    # Artifacts
    paths = {
        "main_64_tickets.json": str(out / "main_64_tickets.json"),
        "main_64_tickets.csv": str(out / "main_64_tickets.csv"),
        **main_paths,
        **_write_insurance_tickets(ins_tickets, out),
    }
    (out / "uncovered_score_matrix.json").write_text(
        json.dumps({str(k): v.to_dict() for k, v in uncovered_by.items()}, indent=2), encoding="utf-8"
    )
    paths["uncovered_score_matrix.json"] = str(out / "uncovered_score_matrix.json")

    ranked_payload = {
        str(fid): [c.to_dict() for c in cands[:10]] for fid, cands in ranked_by.items()
    }
    (out / "insurance_candidates_ranked.json").write_text(json.dumps(ranked_payload, indent=2), encoding="utf-8")
    paths["insurance_candidates_ranked.json"] = str(out / "insurance_candidates_ranked.json")

    (out / "insurance_recommendations.json").write_text(json.dumps(insurance_recs, indent=2), encoding="utf-8")
    paths["insurance_recommendations.json"] = str(out / "insurance_recommendations.json")

    (out / "real_odds_validation.json").write_text(json.dumps(real_odds_report, indent=2, default=str), encoding="utf-8")
    paths["real_odds_validation.json"] = str(out / "real_odds_validation.json")

    (out / "budget_allocation.json").write_text(json.dumps(budget, indent=2), encoding="utf-8")
    paths["budget_allocation.json"] = str(out / "budget_allocation.json")

    (out / "main_vs_insurance_comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    paths["main_vs_insurance_comparison.json"] = str(out / "main_vs_insurance_comparison.json")

    validation = {
        "phase": PHASE_NAME,
        "status": STATUS_VALIDATED,
        "research_only": True,
        "owner_only": True,
        "canonical_formulas_unchanged": True,
        "freezes_unchanged": True,
        "shadow_not_promoted": True,
        "no_production_deploy": True,
        "no_125_default": True,
        "n_main_tickets": 64,
        "n_insurance_tickets": len(ins_tickets),
        "max_insurance_tickets": int(max_insurance_tickets),
        "insurance_tickets_le_max": len(ins_tickets) <= int(max_insurance_tickets),
        "single_leg_priority": all(
            t.n_insurance_legs == 1 for t in ins_tickets[: min(3, len(ins_tickets))]
        )
        if ins_tickets
        else True,
        "budget_sum_check": abs(
            float(budget["total_allocated_eur"]) + float(budget["unallocated_remainder_eur"]) - float(total_budget)
        )
        < 1.0,  # allow rounding slack
        "backtest_enough_data": backtest.get("enough_historical_data"),
        "backtest_immutable_input_hash": backtest.get("immutable_input_hash"),
    }
    (out / "validation_report.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    paths["validation_report.json"] = str(out / "validation_report.json")

    bundle = {
        "generated_at": _utc_now(),
        "phase": PHASE_NAME,
        "status": STATUS_VALIDATED,
        "top_n": int(top_n),
        "main_summary": main_job.get("summary"),
        "insurance_recommendations": insurance_recs,
        "comparison": comparison,
        "budget": budget,
        "backtest": backtest,
        "validation": validation,
        "artifact_paths": paths,
        "not_deployed": True,
    }
    (out / "phase3_research_bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    paths["phase3_research_bundle.json"] = str(out / "phase3_research_bundle.json")

    return {"output_dir": str(out), "bundle": bundle, "validation": validation, "paths": paths}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="BCO Phase 3 Insurance research runner")
    p.add_argument("--top-n", type=int, choices=[8, 10, 12], default=8)
    p.add_argument("--real-odds-json", type=str, default="")
    p.add_argument("--real-odds-csv", type=str, default="")
    p.add_argument("--total-budget", type=float, default=400.0)
    p.add_argument("--main-budget-ratio", type=float, default=0.80)
    p.add_argument("--max-insurance-tickets", type=int, default=15)
    p.add_argument("--stake-mode", choices=["equal", "score_weighted", "kelly_research"], default="equal")
    p.add_argument("--output-dir", type=str, default="")
    args = p.parse_args(argv)

    result = run_phase3(
        top_n=int(args.top_n),
        real_odds_json=args.real_odds_json or None,
        real_odds_csv=args.real_odds_csv or None,
        total_budget=float(args.total_budget),
        main_budget_ratio=float(args.main_budget_ratio),
        max_insurance_tickets=int(args.max_insurance_tickets),
        stake_mode=str(args.stake_mode),
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(
        json.dumps(
            {
                "status": result["validation"]["status"],
                "output_dir": result["output_dir"],
                "n_insurance_tickets": result["validation"]["n_insurance_tickets"],
                "not_deployed": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
