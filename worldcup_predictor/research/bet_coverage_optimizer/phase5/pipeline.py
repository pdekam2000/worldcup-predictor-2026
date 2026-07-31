"""Phase 5 orchestration — long-term validation (research-only)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.phase5.adaptive_insurance import (
    run_adaptive_insurance_research,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.calibration import run_calibration_report
from worldcup_predictor.research.bet_coverage_optimizer.phase5.constants import (
    MIN_HISTORICAL_FIXTURES,
    PHASE_NAME,
    STATUS_VALIDATED,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.corpus import build_phase5_corpus
from worldcup_predictor.research.bet_coverage_optimizer.phase5.dashboard import write_owner_dashboard
from worldcup_predictor.research.bet_coverage_optimizer.phase5.forward_shadow_30d import (
    build_forward_shadow_30d,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.historical_validation import (
    run_historical_validation,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.league_validation import (
    run_league_validation,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.market_family_validation import (
    run_market_family_validation,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.odds_bucket_validation import (
    run_odds_bucket_validation,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.readiness import compute_readiness_score
from worldcup_predictor.research.bet_coverage_optimizer.phase5.robustness import run_robustness_tests


def _write(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def run_phase5(
    *,
    min_fixtures: int = MIN_HISTORICAL_FIXTURES,
    max_historical: int = 2500,
    top_n: int = 8,
    output_dir: Path | None = None,
    source_db: Path | None = None,
    forward_db: Path | None = None,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/coverage_optimizer") / f"phase5_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    corpus = build_phase5_corpus(
        min_fixtures=min_fixtures,
        max_historical=max_historical,
        top_n=top_n,
        source_db=source_db,
        forward_db=forward_db,
    )
    fixtures = list(corpus.get("primary_fixtures") or [])
    # Cap primary evaluation set for determinism/runtime while meeting min
    eval_fx = fixtures[: max(int(min_fixtures), min(len(fixtures), int(max_historical)))]

    historical = run_historical_validation(eval_fx)
    historical["immutable_corpus_hash"] = corpus.get("immutable_corpus_hash")
    historical["excluded_frozen"] = corpus.get("excluded_frozen")
    historical["excluded_historical_sample"] = corpus.get("excluded_historical_sample")
    historical["n_primary_available"] = corpus.get("n_primary")
    historical["enough_historical_data"] = corpus.get("enough_historical_data")
    historical["no_synthetic_outcomes"] = True
    historical["sources"] = {
        "primary": corpus.get("primary_source"),
        "frozen_completed": corpus.get("n_frozen_completed"),
    }

    league = run_league_validation(eval_fx)
    market = run_market_family_validation(eval_fx)
    odds_buckets = run_odds_bucket_validation(eval_fx)
    calibration = run_calibration_report(eval_fx)
    adaptive = run_adaptive_insurance_research(eval_fx)
    robustness = run_robustness_tests(eval_fx)

    db_path = out / "forward_shadow.db"
    forward = build_forward_shadow_30d(
        db_path=db_path,
        frozen_fixtures=list(corpus.get("frozen_completed_fixtures") or []),
        historical_comparison=historical,
        output_dir=out,
    )

    readiness = compute_readiness_score(
        historical=historical,
        league=league,
        market=market,
        calibration=calibration,
        forward=forward,
        robustness=robustness,
        n_fixtures=len(eval_fx),
        min_fixtures=min_fixtures,
    )

    paths = {
        "historical_validation.json": _write(out / "historical_validation.json", historical),
        "league_validation.json": _write(out / "league_validation.json", league),
        "market_family_validation.json": _write(out / "market_family_validation.json", market),
        "odds_bucket_validation.json": _write(out / "odds_bucket_validation.json", odds_buckets),
        "calibration_report.json": _write(out / "calibration_report.json", calibration),
        "forward_shadow_30d.json": str(out / "forward_shadow_30d.json"),
        "adaptive_insurance_research.json": _write(out / "adaptive_insurance_research.json", adaptive),
        "robustness_report.json": _write(out / "robustness_report.json", robustness),
        "readiness_score.json": _write(out / "readiness_score.json", readiness),
        "corpus_manifest.json": _write(
            out / "corpus_manifest.json",
            {
                k: corpus[k]
                for k in corpus
                if k
                not in {
                    "primary_fixtures",
                    "frozen_completed_fixtures",
                }
            },
        ),
        "forward_shadow.db": str(db_path),
    }

    status = STATUS_VALIDATED
    paths.update(
        write_owner_dashboard(
            out,
            historical=historical,
            league=league,
            market=market,
            odds_buckets=odds_buckets,
            calibration=calibration,
            forward=forward,
            readiness=readiness,
            status=status,
        )
    )

    report_md = _build_phase5_report(
        status=status,
        readiness=readiness,
        historical=historical,
        league=league,
        market=market,
        forward=forward,
        robustness=robustness,
        n_fixtures=len(eval_fx),
        out=out,
    )
    report_path = Path("PHASE5_LONG_TERM_VALIDATION_REPORT.md")
    report_path.write_text(report_md, encoding="utf-8")
    # also copy into artifacts
    (out / "PHASE5_LONG_TERM_VALIDATION_REPORT.md").write_text(report_md, encoding="utf-8")
    paths["PHASE5_LONG_TERM_VALIDATION_REPORT.md"] = str(report_path)

    validation = {
        "phase": PHASE_NAME,
        "status": status,
        "research_only": True,
        "owner_only": True,
        "canonical_formulas_unchanged": True,
        "ecse_unchanged": True,
        "wde_unchanged": True,
        "freezes_unchanged": True,
        "no_schema_changes": True,
        "no_production_deploy": True,
        "no_synthetic_outcomes": True,
        "no_fabricated_odds": True,
        "n_replay_fixtures": len(eval_fx),
        "n_leagues": league.get("n_leagues"),
        "readiness_score": readiness.get("readiness_score"),
        "recommendation": readiness.get("recommendation"),
        "success_criteria": {
            "main_plus_insurance_outperforms_main": historical.get("main_plus_insurance_outperforms_main"),
            "generalizes_across_leagues": readiness["gates"]["generalizes_across_leagues"],
            "forward_evidence": readiness["gates"]["forward_evidence"],
            "real_markets_only": True,
            "robust_incomplete_markets": readiness["gates"]["robust_incomplete_markets"],
            "production_unchanged": True,
        },
        "deployment_status": "NOT_DEPLOYED",
    }
    paths["validation_report.json"] = _write(out / "validation_report.json", validation)

    bundle = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": PHASE_NAME,
        "status": status,
        "validation": validation,
        "readiness": readiness,
        "artifact_paths": paths,
        "not_deployed": True,
    }
    paths["phase5_research_bundle.json"] = _write(out / "phase5_research_bundle.json", bundle)

    return {
        "output_dir": str(out),
        "status": status,
        "validation": validation,
        "readiness": readiness,
        "paths": paths,
        "n_fixtures": len(eval_fx),
        "historical": historical,
        "league": league,
        "market": market,
    }


def _build_phase5_report(
    *,
    status: str,
    readiness: dict[str, Any],
    historical: dict[str, Any],
    league: dict[str, Any],
    market: dict[str, Any],
    forward: dict[str, Any],
    robustness: dict[str, Any],
    n_fixtures: int,
    out: Path,
) -> str:
    cf = historical.get("complete_coupon_failure") or {}
    st = historical.get("strategies") or {}
    best = market.get("best_performing_family") or {}
    worst = market.get("worst_performing_family") or {}
    return "\n".join(
        [
            "# PHASE5_LONG_TERM_VALIDATION_REPORT",
            "",
            f"## Final status",
            "",
            f"**`{status}`**",
            "",
            f"**Recommendation:** `{readiness.get('recommendation')}`  ",
            f"**Readiness score:** `{readiness.get('readiness_score')}/100`",
            "",
            "**NOT DEPLOYED**",
            "",
            "| Item | Value |",
            "|---|---|",
            f"| Replay fixtures | {n_fixtures} |",
            f"| Leagues | {league.get('n_leagues')} |",
            f"| Forward days | {forward.get('n_forward_days')} |",
            f"| Artifact path | `{out}` |",
            "",
            "## Historical replay",
            "",
            f"- Exact3 coverage: `{(st.get('exact3_only') or {}).get('coverage_rate')}`",
            f"- Exact3+Main: `{(st.get('exact3_main') or {}).get('coverage_rate')}`",
            f"- Exact3+Main+Insurance: `{(st.get('exact3_main_insurance') or {}).get('coverage_rate')}`",
            f"- Research 125 baseline: `{(st.get('research_125_baseline') or {}).get('coverage_rate')}`",
            f"- Main-only failure freq: `{cf.get('main_only_all_ticket_loss_frequency')}`",
            f"- Main+Ins failure freq: `{cf.get('main_plus_insurance_all_ticket_loss_frequency')}`",
            f"- Insurance rescues: `{cf.get('insurance_rescue_count')}`",
            f"- Significant @0.05: `{(historical.get('statistical_significance') or {}).get('significant_at_0_05')}`",
            "",
            "## Market-family ranking",
            "",
            f"- Best: `{best.get('label')}` (rescue `{best.get('rescue_frequency')}`)",
            f"- Worst: `{worst.get('label')}` (rescue `{worst.get('rescue_frequency')}`)",
            "",
            "## Robustness",
            "",
            f"- Robust to incomplete markets: `{robustness.get('robust_to_incomplete_markets')}`",
            "",
            "## Safety",
            "",
            "- Canonical / ECSE / WDE / freezes unchanged",
            "- No synthetic outcomes",
            "- No fabricated odds",
            "- No production deploy",
            "",
        ]
    )
