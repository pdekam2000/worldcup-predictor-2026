"""Unified A+B forward evaluation automation orchestrator (timers disabled externally)."""

from __future__ import annotations

from datetime import date
from typing import Any

from worldcup_predictor.forward_evaluation.automation import AUTOMATION_ENABLED, automation_status
from worldcup_predictor.forward_evaluation.constants import DEFAULT_TIMEZONE, ELIGIBLE
from worldcup_predictor.forward_evaluation.discovery import discover_forward_evaluation_fixtures, production_conn
from worldcup_predictor.forward_evaluation.evaluate import evaluate_frozen_prediction
from worldcup_predictor.forward_evaluation.freeze import capture_canonical_prediction, store_frozen_prediction
from worldcup_predictor.forward_evaluation.gates import classify_candidate
from worldcup_predictor.forward_evaluation.lock import evaluation_lock
from worldcup_predictor.forward_evaluation.results import sync_actual_result
from worldcup_predictor.forward_evaluation.runner import run_daily_forward_evaluation, sync_and_evaluate_pending
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.batch import batch_id_for
from worldcup_predictor.gpt_actions.delegation import _match_odds


STAGES = (
    "DISCOVER",
    "CLASSIFY",
    "ELIGIBILITY",
    "PREDICT_OR_REUSE",
    "PREMATCH_FREEZE",
    "RESULT_SYNC",
    "EVALUATE_NEWLY_FINISHED",
    "REPORT_STATUS",
)


def run_forward_evaluation_automation_cycle(
    *,
    target_date: str | date | None = None,
    timezone: str = DEFAULT_TIMEZONE,
    dry_run: bool = False,
    skip_lock: bool = False,
) -> dict[str, Any]:
    d = (target_date or date.today()).isoformat() if isinstance(target_date, date) else str(target_date or date.today())
    report: dict[str, Any] = {
        "date": d,
        "timezone": timezone,
        "dry_run": dry_run,
        "automation_enabled": AUTOMATION_ENABLED,
        "stages": list(STAGES),
        "stage_results": {},
    }

    def _run() -> dict[str, Any]:
        settings = get_settings()
        discovery = discover_forward_evaluation_fixtures(target_date=d, timezone=timezone)
        report["stage_results"]["DISCOVER"] = {
            "discovered_count": discovery.get("discovered_count"),
            "tier_a_count": discovery.get("tier_a_count"),
            "tier_b_count": discovery.get("tier_b_count"),
        }

        eval_conn = connect_eval_db()
        prod_conn = production_conn()
        eligible: list[dict] = []
        excluded: list[dict] = []
        frozen_count = 0
        synced = 0
        evaluated = 0
        try:
            for fixture in discovery.get("fixtures") or []:
                status, detail = classify_candidate(prod_conn, fixture=fixture, settings=settings)
                if status != ELIGIBLE:
                    excluded.append({"fixture_id": fixture["fixture_id"], "reason": status, "detail": detail})
                    continue
                eligible.append(fixture)

            report["stage_results"]["CLASSIFY"] = {"excluded_count": len(excluded)}
            report["stage_results"]["ELIGIBILITY"] = {"eligible_count": len(eligible)}

            if not dry_run:
                batch_id = batch_id_for(d)
                for fixture in eligible:
                    fid = int(fixture["fixture_id"])
                    existing = eval_conn.execute(
                        "SELECT prediction_id, evaluation_status FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at DESC LIMIT 1",
                        (fid,),
                    ).fetchone()
                    if existing:
                        report.setdefault("reused_frozen", []).append(fid)
                        continue
                    tier = str(fixture.get("validation_tier") or fixture.get("tier") or "A")
                    frozen = capture_canonical_prediction(prod_conn=prod_conn, fixture=fixture, tier=tier)
                    odds = _match_odds(prod_conn, fid)
                    if tier == "B":
                        from worldcup_predictor.gpt_actions.owner_odds import controlled_owner_odds_lookup
                        from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture

                        daily = DailyFixture(
                            fixture_id=fid,
                            provider_fixture_id=fid,
                            competition_key=str(fixture.get("competition_raw") or fixture.get("competition") or ""),
                            home_team=str(fixture.get("home_team") or ""),
                            away_team=str(fixture.get("away_team") or ""),
                            kickoff_utc=str(fixture.get("kickoff_utc") or ""),
                            status=str(fixture.get("status") or "NS"),
                            season=None,
                        )
                        odds_meta = controlled_owner_odds_lookup(
                            daily, tier="B", settings=settings, budget=None, allow_provider=False
                        )
                        odds = {
                            "home": odds_meta.get("home"),
                            "draw": odds_meta.get("draw"),
                            "away": odds_meta.get("away"),
                            "bookmaker_count": odds_meta.get("bookmaker_count"),
                        }
                    frozen["odds_home"] = odds.get("home")
                    frozen["odds_draw"] = odds.get("draw")
                    frozen["odds_away"] = odds.get("away")
                    frozen["bookmaker_count"] = odds.get("bookmaker_count")
                    sr = store_frozen_prediction(eval_conn, batch_id=batch_id, frozen=frozen)
                    if sr.get("stored"):
                        frozen_count += 1

                pending = eval_conn.execute(
                    "SELECT prediction_id, fixture_id FROM frozen_predictions WHERE evaluation_status='PENDING'"
                ).fetchall()
                for row in pending:
                    fid = int(row["fixture_id"])
                    sr = sync_actual_result(eval_conn, prod_conn, fid)
                    if sr.get("synced"):
                        synced += 1
                    ev = evaluate_frozen_prediction(eval_conn, prediction_id=str(row["prediction_id"]))
                    if ev.get("evaluated"):
                        evaluated += 1

            report["stage_results"]["PREDICT_OR_REUSE"] = {"new_frozen": frozen_count}
            report["stage_results"]["PREMATCH_FREEZE"] = {"frozen_count": frozen_count}
            report["stage_results"]["RESULT_SYNC"] = {"synced": synced}
            report["stage_results"]["EVALUATE_NEWLY_FINISHED"] = {"evaluated": evaluated}
            report["stage_results"]["REPORT_STATUS"] = automation_status()
            report["eligible_count"] = len(eligible)
            report["excluded_count"] = len(excluded)
            report["success"] = True
            return report
        finally:
            eval_conn.close()
            prod_conn.close()

    if skip_lock or dry_run:
        return _run()
    with evaluation_lock("forward_automation_cycle"):
        return _run()
