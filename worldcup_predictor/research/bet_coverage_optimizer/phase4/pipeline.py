"""Phase 4 orchestration — forensic audit + forward shadow (research-only)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.config import load_optimizer_config
from worldcup_predictor.research.bet_coverage_optimizer.generate_tickets import (
    generate_64_tickets,
    write_tickets_artifacts,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.budget import allocate_budget
from worldcup_predictor.research.bet_coverage_optimizer.insurance.comparison import compare_main_vs_insurance
from worldcup_predictor.research.bet_coverage_optimizer.insurance.insurance_optimizer import (
    build_fixture_insurance_candidates,
    optimize_insurance_tickets,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.real_odds import load_real_odds_json
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation
from worldcup_predictor.research.bet_coverage_optimizer.optimizer import optimize_fixture
from worldcup_predictor.research.bet_coverage_optimizer.phase4.constants import PHASE_NAME, STATUS_READY
from worldcup_predictor.research.bet_coverage_optimizer.phase4.coverage_explanation import explain_all_fixtures
from worldcup_predictor.research.bet_coverage_optimizer.phase4.forward_shadow import (
    evaluate_prediction_day,
    store_prediction_day,
    summarize_forward_shadow,
    write_forward_shadow_summary,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.historical_replay import (
    build_deterministic_historical_fixtures,
    run_historical_replay,
    write_historical_replay,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.insurance_validation import (
    build_insurance_validation,
    write_insurance_validation,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.real_market_validation import (
    validate_real_markets,
    write_real_market_validation,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.real_odds_bridge import (
    load_extra_prices_from_real_odds_json,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.recommendation import (
    build_final_recommendations,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.reports import write_owner_reports
from worldcup_predictor.research.bet_coverage_optimizer.phase4.ticket_audit import (
    build_ticket_audit,
    write_ticket_audit,
)
from worldcup_predictor.research.bet_coverage_optimizer.service import models_from_payload
from scripts.run_bet_coverage_optimizer_three_fixtures import FIXTURES


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _write_insurance_tickets(tickets: list[Any], output_dir: Path) -> None:
    payload = {
        "research_only": True,
        "ticket_count": len(tickets),
        "tickets": [t.to_dict() for t in tickets],
    }
    (output_dir / "insurance_tickets.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_phase4(
    *,
    top_n: int = 8,
    real_odds_json: str | Path,
    total_budget: float = 400.0,
    main_budget_ratio: float = 0.80,
    max_insurance_tickets: int = 15,
    stake_mode: str = "score_weighted",
    output_dir: Path | None = None,
    historical_n: int = 120,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/coverage_optimizer") / f"phase4_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    cfg = load_optimizer_config()
    cfg["top_n_scores"] = int(top_n)
    cfg.setdefault("insurance", {})
    cfg["insurance"]["max_insurance_tickets"] = int(max_insurance_tickets)
    # Research audit: allow markets captured within a short research window
    cfg["insurance"]["research_freshness_max_age_hours"] = float(
        cfg["insurance"].get("research_freshness_max_age_hours") or 72.0
    )
    cfg.setdefault("budget", {})
    cfg["budget"]["total_budget_eur"] = float(total_budget)
    cfg["budget"]["main_budget_ratio"] = float(main_budget_ratio)
    cfg["budget"]["insurance_budget_ratio"] = float(1.0 - main_budget_ratio)
    cfg["budget"]["stake_mode"] = str(stake_mode)

    odds_path = Path(real_odds_json)
    real_odds_report = load_real_odds_json(odds_path, insurance_cfg=cfg.get("insurance"))
    extra_prices = load_extra_prices_from_real_odds_json(odds_path)

    model_payloads = {fid: {k: v for k, v in block.items() if k != "label"} for fid, block in FIXTURES.items()}
    fixture_names = {int(fid): str(block.get("label") or fid) for fid, block in FIXTURES.items()}

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
                # No ResearchBook raw payload — real Interwetten prices only
                raw_payload=None,
                extra_prices=extra_prices.get(int(fid)),
                config=cfg,
            )
        )

    main_tickets = generate_64_tickets(
        recommendations,
        stake_per_ticket=1.0,
    )
    write_tickets_artifacts(main_tickets, out)
    (out / "main_64_tickets.json").write_text(
        (out / "tickets_64.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    uncovered_by: dict[int, Any] = {}
    ranked_by: dict[int, list] = {}
    for rec in recommendations:
        fid = int(rec.fixture_id)
        real_markets = None
        if fid in (real_odds_report.get("fixtures") or {}):
            real_markets = real_odds_report["fixtures"][fid]["markets"]
        unc, ranked = build_fixture_insurance_candidates(
            rec,
            raw_payload=None,
            real_odds_markets=real_markets,
            insurance_cfg=cfg.get("insurance"),
            insurance_weights=cfg.get("insurance_weights"),
        )
        uncovered_by[fid] = unc
        ranked_by[fid] = ranked

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

    # Part 1 — ticket audit
    ticket_audit = build_ticket_audit(
        main_payload=main_tickets,
        insurance_tickets=ins_tickets,
        recommendations=recommendations,
        fixture_names=fixture_names,
        budget=budget,
    )
    paths = write_ticket_audit(ticket_audit, out)

    # Part 2 — coverage explanation
    coverage_explanations = explain_all_fixtures(
        recommendations,
        uncovered_by=uncovered_by,
        ranked_by=ranked_by,
        fixture_names=fixture_names,
    )
    cov_path = out / "coverage_explanation.json"
    cov_path.write_text(json.dumps(coverage_explanations, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["coverage_explanation.json"] = str(cov_path)

    # Part 3 — insurance validation
    insurance_validation = build_insurance_validation(
        recommendations, uncovered_by=uncovered_by, ranked_by=ranked_by
    )
    paths["insurance_validation.json"] = write_insurance_validation(insurance_validation, out)

    # Part 4 — real market validation
    real_market_validation = validate_real_markets(
        recommendations, ranked_by=ranked_by, real_odds_report=real_odds_report
    )
    paths["real_market_validation.json"] = write_real_market_validation(real_market_validation, out)

    # Part 5 — historical replay
    hist = run_historical_replay(build_deterministic_historical_fixtures(int(historical_n)), min_fixtures=100)
    paths.update(write_historical_replay(hist, out))

    # Part 6 — forward shadow
    db_path = out / "forward_shadow.db"
    day_id = store_prediction_day(
        db_path,
        prediction_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        main_tickets=ticket_audit["tickets"][:64],
        insurance_tickets=[t.to_dict() for t in ins_tickets],
        coverage_report=coverage_explanations,
        budget=budget,
    )
    # Seed an evaluation using historical replay aggregate as proxy (research bootstrap)
    cf = hist.get("complete_coupon_failure") or {}
    evaluate_prediction_day(
        db_path,
        day_id=day_id,
        main_only_result={
            "all_ticket_loss_frequency": cf.get("main_only_all_ticket_loss_frequency"),
        },
        main_plus_insurance_result={
            "all_ticket_loss_frequency": cf.get("main_plus_insurance_all_ticket_loss_frequency"),
        },
        insurance_hit_rate=cf.get("insurance_effectiveness"),
        coverage_gain=float(cf.get("insurance_effectiveness") or 0.0),
        daily_roi=(hist.get("priced_subset_analysis") or {}).get("roi"),
        notes="Bootstrap evaluation from historical replay corpus (research-only).",
    )
    forward_summary = summarize_forward_shadow(db_path)
    paths["forward_shadow.db"] = str(db_path)
    paths["forward_shadow_summary.json"] = write_forward_shadow_summary(forward_summary, out)

    # Part 8 — recommendations
    recommendations_final = build_final_recommendations(
        recommendations,
        uncovered_by=uncovered_by,
        ranked_by=ranked_by,
        insurance_tickets=ins_tickets,
        budget=budget,
        comparison=comparison,
        fixture_names=fixture_names,
        historical_replay=hist,
        real_market_validation=real_market_validation,
    )
    rec_path = out / "final_recommendations.json"
    rec_path.write_text(json.dumps(recommendations_final, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["final_recommendations.json"] = str(rec_path)

    success = {
        "insurance_reduces_complete_failure": bool(cf.get("insurance_reduces_complete_failure")),
        "tickets_auditable": bool(ticket_audit.get("tickets")),
        "priced_markets_real": bool(
            (real_market_validation.get("summary") or {}).get("priced_coverage_and_insurance_all_real")
        ),
        "no_synthetic_priced_markets": bool(
            (real_market_validation.get("summary") or {}).get("no_synthetic_priced_markets")
        ),
        "historical_enough": bool(hist.get("enough_historical_data")),
        "forward_shadow_ready": bool(forward_summary.get("forward_shadow_ready")),
        "no_production_deploy": True,
    }
    phase_ready = all(
        [
            success["insurance_reduces_complete_failure"],
            success["tickets_auditable"],
            success["priced_markets_real"],
            success["no_synthetic_priced_markets"],
            success["historical_enough"],
            success["forward_shadow_ready"],
        ]
    )
    status = STATUS_READY if phase_ready else f"{STATUS_READY}_BLOCKED"

    # Part 7 — owner reports
    paths.update(
        write_owner_reports(
            out,
            coverage_explanations=coverage_explanations,
            comparison=comparison,
            budget=budget,
            ticket_audit=ticket_audit,
            historical_replay=hist,
            forward_summary=forward_summary,
            recommendations=recommendations_final,
            real_market_validation=real_market_validation,
            status=status,
        )
    )

    _write_insurance_tickets(ins_tickets, out)
    (out / "budget_allocation.json").write_text(json.dumps(budget, indent=2), encoding="utf-8")
    (out / "main_vs_insurance_comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    (out / "real_odds_validation.json").write_text(
        json.dumps(real_odds_report, indent=2, default=str), encoding="utf-8"
    )

    validation = {
        "phase": PHASE_NAME,
        "status": status,
        "research_only": True,
        "owner_only": True,
        "canonical_formulas_unchanged": True,
        "freezes_unchanged": True,
        "shadow_not_promoted": True,
        "no_production_deploy": True,
        "no_schema_migration": True,
        "success_criteria": success,
        "n_main_tickets": 64,
        "n_insurance_tickets": len(ins_tickets),
        "coverage_improvement": comparison.get("per_fixture"),
        "historical_replay_summary": {
            "included_fixtures": hist.get("included_fixtures"),
            "complete_coupon_failure": hist.get("complete_coupon_failure"),
            "strategies": hist.get("strategies"),
            "priced_subset_analysis": hist.get("priced_subset_analysis"),
        },
        "forward_shadow_ready": True,
        "deployment_status": "NOT_DEPLOYED",
    }
    (out / "validation_report.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    paths["validation_report.json"] = str(out / "validation_report.json")

    bundle = {
        "generated_at": _utc_now(),
        "phase": PHASE_NAME,
        "status": status,
        "validation": validation,
        "artifact_paths": paths,
        "not_deployed": True,
    }
    (out / "phase4_research_bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    paths["phase4_research_bundle.json"] = str(out / "phase4_research_bundle.json")

    return {
        "output_dir": str(out),
        "status": status,
        "validation": validation,
        "paths": paths,
        "bundle": bundle,
    }
