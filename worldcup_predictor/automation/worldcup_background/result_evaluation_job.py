"""Evaluate finished World Cup fixtures against stored predictions — Phase 33 / 44A."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

logger = logging.getLogger(__name__)

EvaluationMode = Literal["stored_first", "finished_scan"]


@dataclass
class EvaluationJobResult:
    scanned: int = 0
    evaluated: int = 0
    updated: int = 0
    skipped_not_finished: int = 0
    skipped_unchanged: int = 0
    skipped_no_stored: int = 0
    pending: int = 0
    errors: int = 0
    summary_rebuilt: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def skipped(self) -> int:
        return self.skipped_not_finished + self.skipped_unchanged + self.skipped_no_stored

    def to_log_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("details", None)
        payload["skipped_total"] = self.skipped
        return payload


def _load_stored_payload(
    fixture_id: int,
    *,
    store: WorldcupPredictionStore,
    repo: FootballIntelligenceRepository,
    stored_row: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    cached = store.get(fixture_id, locale="en")
    if cached is not None:
        return cached

    row = stored_row or repo.get_worldcup_stored_prediction(fixture_id)
    if not row or not row.get("payload_json"):
        return None

    try:
        payload = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        logger.warning("Invalid payload_json for fixture_id=%s", fixture_id)
        return None
    return payload if isinstance(payload, dict) else None


def _existing_evaluation(repo: FootballIntelligenceRepository, fixture_id: int) -> dict[str, Any] | None:
    row = repo.get_worldcup_prediction_evaluation(fixture_id)
    return row


def _evaluation_unchanged(
    existing: dict[str, Any] | None,
    *,
    outcome_final_score: str | None,
    evaluation_status: str | None,
) -> bool:
    if not existing:
        return False
    if not outcome_final_score:
        return False
    if existing.get("market_ht_status") is None and existing.get("market_cs_status") is None:
        detail_raw = existing.get("detail_json")
        if detail_raw:
            try:
                detail = json.loads(detail_raw) if isinstance(detail_raw, str) else detail_raw
            except (json.JSONDecodeError, TypeError):
                detail = {}
            adv = detail.get("advanced_markets") or {}
            if not detail.get("advanced_markets") or "goal_minute" not in adv:
                return False
        else:
            return False
    elif existing.get("market_goal_minute_status") is None:
        return False
    prior_score = str(existing.get("final_score") or "")
    prior_status = str(existing.get("overall_status") or "")
    if prior_status in {"pending", "unknown", "void", ""}:
        return False
    return prior_score == str(outcome_final_score) and prior_status == str(evaluation_status or "")


def _evaluate_one_fixture(
    fixture_id: int,
    *,
    stored: dict[str, Any],
    resolver: FixtureOutcomeResolver,
    repo: FootballIntelligenceRepository,
    skip_unchanged: bool,
    result: EvaluationJobResult,
) -> None:
    outcome = resolver.resolve(fixture_id)
    if not outcome.is_finished:
        result.skipped_not_finished += 1
        result.details.append({"fixture_id": fixture_id, "status": "skipped_not_finished"})
        return

    evaluation = evaluate_stored_prediction(stored, outcome)
    eval_status = str(evaluation.get("status") or "pending")

    existing = _existing_evaluation(repo, fixture_id)
    if skip_unchanged and _evaluation_unchanged(
        existing,
        outcome_final_score=outcome.final_score,
        evaluation_status=eval_status,
    ):
        result.skipped_unchanged += 1
        result.details.append({"fixture_id": fixture_id, "status": "skipped_unchanged"})
        return

    repo.upsert_worldcup_prediction_evaluation(
        fixture_id=fixture_id,
        evaluation=evaluation,
        outcome={
            "actual_result": outcome.actual_result,
            "final_score": outcome.final_score,
            "is_finished": outcome.is_finished,
        },
    )

    if existing:
        result.updated += 1
    else:
        result.evaluated += 1

    if eval_status == "pending":
        result.pending += 1

    result.details.append(
        {
            "fixture_id": fixture_id,
            "status": eval_status,
            "final_score": outcome.final_score,
            "action": "updated" if existing else "created",
        }
    )

    try:
        from worldcup_predictor.lifecycle.hooks import hook_after_worldcup_evaluation

        hook_after_worldcup_evaluation(
            fixture_id,
            payload=stored,
            competition_key=stored.get("competition_key"),
        )
    except Exception:
        pass


def run_evaluate_worldcup_results(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    limit: int | None = None,
    mode: EvaluationMode = "stored_first",
    skip_unchanged: bool = True,
    rebuild_summary: bool = True,
) -> EvaluationJobResult:
    """Evaluate stored predictions for finished fixtures (read-only on payloads)."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    store = WorldcupPredictionStore(settings)
    resolver = FixtureOutcomeResolver(settings)
    result = EvaluationJobResult()

    try:
        if mode == "stored_first":
            stored_rows = repo.list_worldcup_stored_prediction_rows(competition_key=competition_key)
            if limit is not None:
                stored_rows = stored_rows[: max(0, int(limit))]
            result.scanned = len(stored_rows)

            for row in stored_rows:
                fixture_id = int(row["fixture_id"])
                stored = _load_stored_payload(fixture_id, store=store, repo=repo, stored_row=row)
                if stored is None:
                    result.skipped_no_stored += 1
                    result.details.append({"fixture_id": fixture_id, "status": "skipped_no_stored"})
                    continue
                try:
                    _evaluate_one_fixture(
                        fixture_id,
                        stored=stored,
                        resolver=resolver,
                        repo=repo,
                        skip_unchanged=skip_unchanged,
                        result=result,
                    )
                except Exception as exc:
                    logger.exception("Evaluation failed fixture_id=%s", fixture_id)
                    result.errors += 1
                    result.details.append({"fixture_id": fixture_id, "status": "error", "reason": str(exc)})
        else:
            finished = [
                dict(row)
                for row in repo.list_fixtures(
                    competition_key=competition_key, status_class="finished", limit=limit or 100
                )
            ]
            result.scanned = len(finished)
            for row in finished:
                fixture_id = int(row["fixture_id"])
                stored = _load_stored_payload(fixture_id, store=store, repo=repo)
                if stored is None:
                    result.skipped_no_stored += 1
                    result.details.append({"fixture_id": fixture_id, "status": "skipped_no_stored"})
                    continue
                try:
                    _evaluate_one_fixture(
                        fixture_id,
                        stored=stored,
                        resolver=resolver,
                        repo=repo,
                        skip_unchanged=skip_unchanged,
                        result=result,
                    )
                except Exception as exc:
                    logger.exception("Evaluation failed fixture_id=%s", fixture_id)
                    result.errors += 1
                    result.details.append({"fixture_id": fixture_id, "status": "error", "reason": str(exc)})

        if rebuild_summary:
            from worldcup_predictor.automation.worldcup_background.accuracy_summary import rebuild_accuracy_summary

            rebuild_accuracy_summary(settings=settings, competition_key=competition_key)
            result.summary_rebuilt = True
    finally:
        repo.close()
        store._repo.close()

    logger.info("worldcup_auto_evaluation %s", result.to_log_dict())
    return result
