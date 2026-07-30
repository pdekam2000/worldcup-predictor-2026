"""Non-blocking shadow orchestration for form + totals + Lambda V2 families."""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from worldcup_predictor.research.football_strength_foundation.lambda_v2 import (
    football_only,
    market_only_from_odds_row,
    uncertainty_aware_blend,
)
from worldcup_predictor.research.football_strength_foundation.score_v2 import (
    dist_dc,
    dist_overdispersed,
    dist_poisson,
    exact_metrics,
)
from worldcup_predictor.research.football_strength_foundation.shadow_store import persist_shadow
from worldcup_predictor.research.football_strength_foundation.team_form_snapshot_writer import (
    TeamFormSnapshotWriter,
)
from worldcup_predictor.research.football_strength_foundation.team_strength_engine import (
    TeamStrengthEngine,
)
from worldcup_predictor.research.football_strength_foundation.totals_market import TotalsLine
from worldcup_predictor.research.infra_l2f_forward.alternate_totals_capture_service import (
    capture_alternate_totals,
    lines_from_ecse_odds_row,
)
from worldcup_predictor.research.infra_l2f_forward.adaptive_blend import l2f_adaptive


@dataclass
class StageResult:
    stage: str
    ok: bool
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ShadowOrchestrationResult:
    fixture_id: int
    stages: list[StageResult]
    canonical_blocked: bool = False  # always False — shadow never blocks

    @property
    def all_ok(self) -> bool:
        return all(s.ok for s in self.stages)


def _run_stage(name: str, fn: Callable[[], dict[str, Any] | None]) -> StageResult:
    try:
        data = fn() or {}
        return StageResult(name, True, "ok", data)
    except Exception as exc:  # noqa: BLE001 — intentional isolation
        return StageResult(name, False, f"{type(exc).__name__}: {exc}", {"traceback": traceback.format_exc()[-800:]})


def run_shadow_pipeline(
    *,
    conn,
    fixture_id: int,
    home_team: str,
    away_team: str,
    league: str,
    cutoff: datetime,
    engine: TeamStrengthEngine,
    odds_row: dict[str, Any] | None,
    canonical_lh: float,
    canonical_la: float,
    canonical_prediction_id: str | None = None,
    odds_fresh: bool = True,
    bookmaker_count: int | None = None,
    actual_home: int | None = None,
    actual_away: int | None = None,
) -> ShadowOrchestrationResult:
    """
    Run shadow stages. Never raises to caller for stage failures.
    Canonical prediction must be invoked separately and is never invalidated here.
    """
    stages: list[StageResult] = []
    bundle_holder: dict[str, Any] = {}
    lines_holder: dict[str, Any] = {"lines": []}

    def stage_form():
        writer = TeamFormSnapshotWriter(conn)
        ids = writer.persist_derived(
            fixture_id=fixture_id,
            home_team=home_team,
            away_team=away_team,
            cutoff=cutoff,
            engine=engine,
            league=league,
        )
        bundle = engine.build_match(home_team, away_team, cutoff, league, target_fixture_id=fixture_id)
        bundle_holder["bundle"] = bundle
        return {"snapshot_ids": ids, "home_n": bundle.home.n_total, "away_n": bundle.away.n_total}

    def stage_totals():
        cap = capture_alternate_totals(conn, fixture_id=fixture_id, odds_row=odds_row)
        lines = lines_from_ecse_odds_row(odds_row)
        lines_holder["lines"] = lines
        return cap

    stages.append(_run_stage("form_snapshot", stage_form))
    stages.append(_run_stage("totals_snapshot", stage_totals))

    def stage_models():
        bundle = bundle_holder.get("bundle")
        if bundle is None:
            bundle = engine.build_match(home_team, away_team, cutoff, league, target_fixture_id=fixture_id)
            bundle_holder["bundle"] = bundle
        lines: list[TotalsLine] = list(lines_holder.get("lines") or [])
        mkt = market_only_from_odds_row(odds_row, fallback_lh=canonical_lh, fallback_la=canonical_la)
        models = {
            "LAMBDA_V2_FOOTBALL": football_only(bundle),
            "LAMBDA_V2_MARKET_TOTAL": mkt,
            "LAMBDA_V2_BLENDED": uncertainty_aware_blend(
                bundle, lines, mkt, odds_fresh=odds_fresh, bookmaker_count=bookmaker_count
            ),
            "LAMBDA_V2_BLENDED_ADAPTIVE": l2f_adaptive(
                bundle, lines, mkt, odds_fresh=odds_fresh, bookmaker_count=bookmaker_count
            ),
        }
        dist_map = {
            "EXACT_V2_POISSON": ("LAMBDA_V2_BLENDED_ADAPTIVE", dist_poisson),
            "EXACT_V2_DC": ("LAMBDA_V2_BLENDED_ADAPTIVE", dist_dc),
            "EXACT_V2_OVERDISPERSED": ("LAMBDA_V2_BLENDED_ADAPTIVE", dist_overdispersed),
            "EXACT_V2_SELECTED": ("LAMBDA_V2_BLENDED_ADAPTIVE", dist_dc),
        }
        written = []
        for mid, outp in models.items():
            tops = []
            if actual_home is not None and actual_away is not None:
                em = exact_metrics(dist_poisson(outp.lambda_home, outp.lambda_away), actual_home, actual_away)
                tops = em["tops"]
            else:
                dist = dist_poisson(outp.lambda_home, outp.lambda_away)
                tops = [e["scoreline"] for e in dist if e.get("scoreline") != "OTHER"][:10]
            persist_shadow(
                conn,
                fixture_id=fixture_id,
                model_id=mid,
                model_version="LAMBDA-V2-1",
                lambda_home=outp.lambda_home,
                lambda_away=outp.lambda_away,
                tops=tops,
                dist_type="poisson",
                canonical_prediction_id=canonical_prediction_id,
                meta={
                    "feature_cutoff": cutoff.isoformat(),
                    "lambda_uncertainty": outp.uncertainty,
                    "football_w": outp.football_contribution,
                    "market_w": outp.market_contribution,
                    "history_count_home": bundle.home.n_total,
                    "history_count_away": bundle.away.n_total,
                    "fallback_count": bundle.home.fallback_count + bundle.away.fallback_count,
                    "totals_lines": [ln.line for ln in lines],
                    "odds_freshness": "FRESH" if odds_fresh else "STALE",
                    "shadow_only": True,
                },
            )
            written.append(mid)
        for fam, (src, dfn) in dist_map.items():
            outp = models[src]
            dist = dfn(outp.lambda_home, outp.lambda_away)
            tops = [e["scoreline"] for e in dist if e.get("scoreline") != "OTHER"][:10]
            persist_shadow(
                conn,
                fixture_id=fixture_id,
                model_id=fam,
                model_version="EXACT-V2-1",
                lambda_home=outp.lambda_home,
                lambda_away=outp.lambda_away,
                tops=tops,
                dist_type=fam,
                canonical_prediction_id=canonical_prediction_id,
                meta={"inner": src, "shadow_only": True, "feature_cutoff": cutoff.isoformat()},
            )
            written.append(fam)
        return {"written": written}

    stages.append(_run_stage("lambda_exact_shadow", stage_models))
    return ShadowOrchestrationResult(fixture_id=fixture_id, stages=stages, canonical_blocked=False)
