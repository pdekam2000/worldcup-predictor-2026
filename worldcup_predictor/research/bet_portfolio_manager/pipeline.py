"""Bet Portfolio Manager pipeline — research-only orchestration."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.phase5.corpus import build_phase5_corpus
from worldcup_predictor.research.bet_portfolio_manager.capital_allocation import (
    allocate_capital,
    allocate_for_bankrolls,
)
from worldcup_predictor.research.bet_portfolio_manager.constants import (
    DEFAULT_BANKROLLS,
    PHASE_NAME,
    STATUS_COMPLETE,
)
from worldcup_predictor.research.bet_portfolio_manager.correlation import analyze_diversification
from worldcup_predictor.research.bet_portfolio_manager.daily_score import compute_daily_portfolio_score
from worldcup_predictor.research.bet_portfolio_manager.dashboard import write_dashboard
from worldcup_predictor.research.bet_portfolio_manager.explainability import build_explanation
from worldcup_predictor.research.bet_portfolio_manager.fixture_ranking import rank_fixtures
from worldcup_predictor.research.bet_portfolio_manager.forward_shadow import (
    store_forward_day,
    summarize_forward,
)
from worldcup_predictor.research.bet_portfolio_manager.historical_validation import (
    run_historical_portfolio_validation,
)
from worldcup_predictor.research.bet_portfolio_manager.input_adapter import (
    attach_outcomes,
    normalize_fixture,
)
from worldcup_predictor.research.bet_portfolio_manager.no_bet import decide_no_bet
from worldcup_predictor.research.bet_portfolio_manager.risk import compute_portfolio_risk


def _write(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _league_reliability_from_rows(rows: list[dict[str, Any]]) -> dict[str, float]:
    by: dict[str, list[int]] = defaultdict(list)
    for fx in rows:
        n = attach_outcomes(fx)
        if n.get("hit_insurance") is None:
            continue
        by[str(n.get("league") or "unknown")].append(1 if n["hit_insurance"] else 0)
    return {k: (sum(v) / len(v) if v else 0.55) for k, v in by.items()}


def evaluate_day(
    fixtures_raw: list[dict[str, Any]],
    *,
    bankroll: float = 500.0,
    mode: str = "score_weighted",
    league_reliability: dict[str, float] | None = None,
) -> dict[str, Any]:
    fixtures = [attach_outcomes(normalize_fixture(x)) for x in fixtures_raw]
    lr = league_reliability or _league_reliability_from_rows(fixtures)
    daily = compute_daily_portfolio_score(fixtures, league_reliability=lr)
    ranking = rank_fixtures(fixtures, league_reliability=lr)
    diversification = analyze_diversification(fixtures)
    decision = decide_no_bet(daily, ranking, diversification)
    by_id = {int(f["fixture_id"]): f for f in fixtures}
    allocation = allocate_capital(
        bankroll=bankroll,
        selected=decision.get("selected_fixtures") or [],
        fixtures_by_id=by_id,
        mode=mode,
    )
    bankrolls = allocate_for_bankrolls(
        selected=decision.get("selected_fixtures") or [],
        fixtures_by_id=by_id,
        bankrolls=DEFAULT_BANKROLLS,
        mode=mode,
    )
    risk = compute_portfolio_risk(
        allocation=allocation,
        selected=decision.get("selected_fixtures") or [],
        fixtures_by_id=by_id,
        diversification=diversification,
    )
    explanation = build_explanation(
        daily=daily, decision=decision, allocation=allocation, risk=risk
    )
    return {
        "daily": daily,
        "ranking": ranking,
        "diversification": diversification,
        "decision": decision,
        "allocation": allocation,
        "bankrolls": bankrolls,
        "risk": risk,
        "explanation": explanation,
        "fixtures": fixtures,
    }


def run_portfolio_manager(
    *,
    bankroll: float = 500.0,
    mode: str = "score_weighted",
    min_historical: int = 600,
    max_historical: int = 1200,
    output_dir: Path | None = None,
    fixtures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_dir) if output_dir else Path("artifacts/bet_portfolio_manager") / f"run_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    if fixtures is None:
        corpus = build_phase5_corpus(
            min_fixtures=min(min_historical, 1000),
            max_historical=max_historical,
            top_n=8,
        )
        fixtures = list(corpus.get("primary_fixtures") or [])[:max_historical]
        frozen = list(corpus.get("frozen_completed_fixtures") or [])
    else:
        frozen = []

    # Historical validation
    historical = run_historical_portfolio_validation(fixtures, bankroll=1000.0, mode=mode)

    # Demo / latest day: take last chronological bucket of up to 5 fixtures
    normed = [normalize_fixture(x) for x in fixtures]
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i, fx in enumerate(normed):
        day = fx.get("kickoff") or f"bucket_{i // 3:05d}"
        by_day[str(day)[:16]].append(fixtures[i])
    day_keys = sorted(by_day.keys())
    today_key = day_keys[-1] if day_keys else "unknown"
    today_raw = by_day.get(today_key) or fixtures[:3]
    day_eval = evaluate_day(today_raw, bankroll=bankroll, mode=mode)

    # Forward shadow: store up to 30 recent days from frozen or historical buckets
    db_path = out / "forward_portfolio_shadow.db"
    forward_days = 0
    source_days = sorted(by_day.keys())[-30:]
    if frozen:
        fby: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fr in frozen:
            fby[str(fr.get("kickoff") or "")[:10]].append(fr)
        source_days = sorted(d for d in fby if len(d) >= 10)[-30:] or source_days
        for d in source_days:
            rows = fby.get(d) or by_day.get(d) or []
            if not rows:
                continue
            ev = evaluate_day(rows, bankroll=bankroll, mode=mode)
            payload = {
                "daily_portfolio_score": ev["daily"]["daily_portfolio_score"],
                "grade": ev["daily"]["grade"],
                "action": ev["decision"]["action"],
                "recommended_bankroll": bankroll,
                "recommended_exposure": ev["allocation"]["allocated_eur"],
                "recommended_fixtures": ev["decision"]["selected_fixture_ids"],
                "capital_allocation": ev["allocation"],
                "risk_summary": ev["risk"],
                "no_production_execution": True,
            }
            store_forward_day(db_path, prediction_date=d[:10], report=payload)
            forward_days += 1
    else:
        for d in source_days:
            rows = by_day[d]
            ev = evaluate_day(rows, bankroll=bankroll, mode=mode)
            payload = {
                "daily_portfolio_score": ev["daily"]["daily_portfolio_score"],
                "grade": ev["daily"]["grade"],
                "action": ev["decision"]["action"],
                "recommended_bankroll": bankroll,
                "recommended_exposure": ev["allocation"]["allocated_eur"],
                "recommended_fixtures": ev["decision"]["selected_fixture_ids"],
                "capital_allocation": ev["allocation"],
                "risk_summary": ev["risk"],
                "no_production_execution": True,
            }
            store_forward_day(db_path, prediction_date=str(d)[:10], report=payload)
            forward_days += 1

    forward = summarize_forward(db_path)
    forward["n_days_written"] = forward_days

    paths = {
        "portfolio_score.json": _write(out / "portfolio_score.json", day_eval["daily"]),
        "fixture_portfolio_ranking.json": _write(out / "fixture_portfolio_ranking.json", day_eval["ranking"]),
        "capital_allocation.json": _write(
            out / "capital_allocation.json",
            {"primary": day_eval["allocation"], "bankroll_matrix": day_eval["bankrolls"]},
        ),
        "no_bet_analysis.json": _write(out / "no_bet_analysis.json", day_eval["decision"]),
        "diversification_report.json": _write(
            out / "diversification_report.json", day_eval["diversification"]
        ),
        "portfolio_risk.json": _write(out / "portfolio_risk.json", day_eval["risk"]),
        "historical_portfolio_validation.json": _write(
            out / "historical_portfolio_validation.json", historical
        ),
        "forward_portfolio_shadow.json": _write(out / "forward_portfolio_shadow.json", forward),
        "explanation.json": _write(out / "explanation.json", day_eval["explanation"]),
        "forward_portfolio_shadow.db": str(db_path),
    }

    status = STATUS_COMPLETE
    paths.update(
        write_dashboard(
            out,
            daily=day_eval["daily"],
            decision=day_eval["decision"],
            ranking=day_eval["ranking"],
            allocation=day_eval["allocation"],
            risk=day_eval["risk"],
            diversification=day_eval["diversification"],
            historical=historical,
            forward=forward,
            explanation=day_eval["explanation"],
            status=status,
        )
    )

    report = _build_report(
        status=status,
        historical=historical,
        forward=forward,
        day_eval=day_eval,
        out=out,
        n_fixtures=len(fixtures),
    )
    report_path = Path("BET_PORTFOLIO_MANAGER_REPORT.md")
    report_path.write_text(report, encoding="utf-8")
    (out / "BET_PORTFOLIO_MANAGER_REPORT.md").write_text(report, encoding="utf-8")
    paths["BET_PORTFOLIO_MANAGER_REPORT.md"] = str(report_path)

    validation = {
        "phase": PHASE_NAME,
        "status": status,
        "research_only": True,
        "owner_only": True,
        "canonical_unchanged": True,
        "ecse_unchanged": True,
        "wde_unchanged": True,
        "freezes_unchanged": True,
        "coverage_optimizer_unchanged": True,
        "insurance_optimizer_unchanged": True,
        "predictions_not_modified": True,
        "no_production_deploy": True,
        "n_historical_fixtures": len(fixtures),
        "historical_improvement": historical.get("improvement"),
        "grade_distribution": (historical.get("portfolio_managed") or {}).get("grade_distribution"),
        "deployment_status": "NOT_DEPLOYED",
    }
    paths["validation_report.json"] = _write(out / "validation_report.json", validation)

    return {
        "output_dir": str(out),
        "status": status,
        "validation": validation,
        "paths": paths,
        "historical": historical,
        "day_eval": day_eval,
        "forward": forward,
        "n_fixtures": len(fixtures),
    }


def _build_report(
    *,
    status: str,
    historical: dict[str, Any],
    forward: dict[str, Any],
    day_eval: dict[str, Any],
    out: Path,
    n_fixtures: int,
) -> str:
    imp = historical.get("improvement") or {}
    pm = historical.get("portfolio_managed") or {}
    ab = historical.get("always_bet") or {}
    return "\n".join(
        [
            "# BET_PORTFOLIO_MANAGER_REPORT",
            "",
            f"## Final status",
            "",
            f"**`{status}`**",
            "",
            "**NOT DEPLOYED**",
            "",
            "| Item | Value |",
            "|---|---|",
            f"| Historical fixtures | {n_fixtures} |",
            f"| Artifact path | `{out}` |",
            f"| Sample day score | {day_eval['daily'].get('daily_portfolio_score')} |",
            f"| Sample day grade | {day_eval['daily'].get('grade')} |",
            f"| Sample day action | {day_eval['decision'].get('action')} |",
            "",
            "## Historical portfolio improvement",
            "",
            f"- Always-bet ROI: `{ab.get('roi')}`",
            f"- Managed ROI: `{pm.get('roi')}`",
            f"- ROI delta: `{imp.get('roi_delta')}`",
            f"- Always-bet drawdown: `{ab.get('max_drawdown')}`",
            f"- Managed drawdown: `{pm.get('max_drawdown')}`",
            f"- Drawdown improvement: `{imp.get('drawdown_delta')}`",
            f"- Capital efficiency delta: `{imp.get('capital_efficiency_delta')}`",
            f"- Skipped days: `{imp.get('average_skipped_bad_days')}` (rate `{imp.get('skip_rate')}`)",
            f"- Grade distribution: `{pm.get('grade_distribution')}`",
            "",
            "## Forward shadow",
            "",
            f"- Days stored: `{forward.get('n_days')}`",
            f"- Action distribution: `{forward.get('action_distribution')}`",
            "",
            "## Architecture safety",
            "",
            "- Does not modify WDE / ECSE / freezes / Coverage / Insurance",
            "- Does not change football predictions",
            "- Distinct from OBPE market selector — this layer decides capital & day quality only",
            "- Research-only · no production execution",
            "",
        ]
    )
