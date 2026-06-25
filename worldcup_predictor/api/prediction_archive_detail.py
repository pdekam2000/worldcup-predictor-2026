"""Phase 42C — build prediction archive detail payloads from stored history + snapshots."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.api.prediction_history_evaluation import (
    FixtureOutcome,
    FixtureOutcomeResolver,
    evaluate_history_record,
)
from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY, get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.enums import Prediction1x2
from worldcup_predictor.database.postgres.schemas import PredictionHistoryRecord
from worldcup_predictor.quota.prediction_cache import kickoff_from_payload
from worldcup_predictor.results.match_results_store import MatchResultsStore

SnapshotSource = Literal["sqlite", "cache", "history_only"]

_SELECTION_LABELS: dict[str, str] = {
    "home": "Home Win",
    "home_win": "Home Win",
    "draw": "Draw",
    "away": "Away Win",
    "away_win": "Away Win",
    "over_2_5": "Over 2.5",
    "under_2_5": "Under 2.5",
    "yes": "BTTS Yes",
    "no": "BTTS No",
    "btts_yes": "BTTS Yes",
    "btts_no": "BTTS No",
}

_MARKET_EVAL_KEYS: dict[str, str] = {
    "1x2": "1x2",
    "over_under_2_5": "over_under_2_5",
    "btts": "btts",
    "double_chance": "double_chance",
    "ht_result": "ht_result",
    "correct_score": "correct_score",
    "first_goal_team": "first_goal_team",
    "goalscorer": "goalscorer",
    "goal_minute": "goal_minute",
    "goal_timing": "goal_minute",
    "first_team_to_score": "first_goal_team",
}


def _display_selection(value: Any) -> str:
    if value is None:
        return "—"
    key = str(value).lower()
    return _SELECTION_LABELS.get(key, str(value).replace("_", " ").title())


def _prob_pct(value: Any) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= num <= 1:
        return round(num * 100, 1)
    return round(num, 1)


def _raw_file_cache(
    fixture_id: int,
    *,
    competition_key: str,
    season: int,
    locale: str,
    settings: Settings,
) -> dict[str, Any] | None:
    try:
        from worldcup_predictor.quota.prediction_cache import _cache, _cache_params

        payload = _cache(settings).get(
            "prediction_result",
            _cache_params(fixture_id, competition_key=competition_key, season=season, locale=locale),
        )
        return dict(payload) if isinstance(payload, dict) else None
    except Exception:
        return None


def load_archive_snapshot(
    fixture_id: int,
    *,
    settings: Settings | None = None,
) -> tuple[dict[str, Any] | None, SnapshotSource]:
    """Load the best available stored prediction snapshot — no engine re-run."""
    settings = settings or get_settings()
    comp = get_competition(DEFAULT_COMPETITION_KEY)

    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        row = repo.get_worldcup_stored_prediction(fixture_id, include_inactive=True)
        if row and row.get("payload_json"):
            payload = json.loads(row["payload_json"])
            if isinstance(payload, dict):
                return payload, "sqlite"
    except Exception:
        pass

    cached = _raw_file_cache(
        fixture_id,
        competition_key=comp.key,
        season=comp.season,
        locale="en",
        settings=settings,
    )
    if cached:
        return cached, "cache"

    return None, "history_only"


def _market_block(
    *,
    key: str,
    label: str,
    selection: Any = None,
    probabilities: dict[str, Any] | None = None,
    confidence: float | None = None,
    result_status: str | None = None,
    withheld: bool = False,
    withheld_reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "key": key,
        "label": label,
        "selection": selection,
        "display_selection": _display_selection(selection),
        "probabilities": probabilities or {},
        "confidence": confidence,
        "result_status": result_status,
        "withheld": withheld,
    }
    if withheld_reason:
        block["withheld_reason"] = withheld_reason
    if extra:
        block.update(extra)
    return block


def _consistency_status(raw: dict[str, Any] | None) -> tuple[bool, str | None]:
    if not isinstance(raw, dict):
        return False, None
    status = str(raw.get("consistency_status") or "").lower()
    if status == "withheld" or raw.get("display_allowed") is False:
        return True, raw.get("withheld_reason")
    return False, None


def _advanced_eval_block(
    advanced_markets: dict[str, Any] | None,
    key: str,
) -> dict[str, Any]:
    block = (advanced_markets or {}).get(key) or {}
    if not isinstance(block, dict):
        return {}
    return block


def _build_markets(
    snapshot: dict[str, Any] | None,
    *,
    record: PredictionHistoryRecord,
    market_eval: dict[str, str] | None,
    advanced_markets: dict[str, Any] | None,
    outcome: FixtureOutcome,
) -> list[dict[str, Any]]:
    markets: list[dict[str, Any]] = []
    dm = (snapshot or {}).get("detailed_markets") or {}
    if not isinstance(dm, dict):
        dm = {}

    pending = not outcome.is_finished
    default_status = "pending" if pending else None

    mw = dm.get("match_winner") if isinstance(dm.get("match_winner"), dict) else {}
    mw_sel = mw.get("selection") or (snapshot or {}).get("prediction")
    if not mw_sel and record.prediction_1x2:
        mw_sel = record.prediction_1x2.value
    mw_probs = mw.get("probabilities") if isinstance(mw.get("probabilities"), dict) else {}
    markets.append(
        _market_block(
            key="1x2",
            label="Match Result (1X2)",
            selection=mw_sel,
            probabilities=mw_probs,
            confidence=_prob_pct(mw.get("probability")),
            result_status=(market_eval or {}).get("1x2") or default_status,
        )
    )

    btts = dm.get("btts") if isinstance(dm.get("btts"), dict) else {}
    btts_withheld, btts_reason = _consistency_status(btts)
    markets.append(
        _market_block(
            key="btts",
            label="Both Teams To Score",
            selection=btts.get("selection"),
            probabilities=btts.get("probabilities") if isinstance(btts.get("probabilities"), dict) else {},
            confidence=_prob_pct(btts.get("probability")),
            result_status=(market_eval or {}).get("btts") or default_status,
            withheld=btts_withheld,
            withheld_reason=btts_reason,
        )
    )

    ou = dm.get("over_under_25") if isinstance(dm.get("over_under_25"), dict) else {}
    ou_withheld, ou_reason = _consistency_status(ou)
    markets.append(
        _market_block(
            key="over_under_2_5",
            label="Over/Under 2.5",
            selection=ou.get("selection"),
            probabilities=ou.get("probabilities") if isinstance(ou.get("probabilities"), dict) else {},
            confidence=_prob_pct(ou.get("probability")),
            result_status=(market_eval or {}).get("over_under_2_5") or default_status,
            withheld=ou_withheld,
            withheld_reason=ou_reason,
        )
    )

    fg = dm.get("first_goal") if isinstance(dm.get("first_goal"), dict) else {}
    fg_withheld, fg_reason = _consistency_status(fg)
    fg_eval = _advanced_eval_block(advanced_markets, "first_goal_team")
    gm_eval = _advanced_eval_block(advanced_markets, "goal_minute")
    markets.append(
        _market_block(
            key="first_team_to_score",
            label="First Team To Score",
            selection=fg.get("team"),
            probabilities={},
            confidence=_prob_pct(fg.get("confidence")),
            result_status=(market_eval or {}).get("first_goal_team") or fg_eval.get("status") or default_status,
            withheld=fg_withheld,
            withheld_reason=fg_reason,
            extra={
                "team": fg.get("team"),
                "actual": fg_eval.get("actual"),
                "eval_reason": fg_eval.get("reason"),
            },
        )
    )

    markets.append(
        _market_block(
            key="goal_timing",
            label="Goal Minute",
            selection=fg.get("minute_range") or fg.get("expected_minute"),
            probabilities={},
            confidence=_prob_pct(fg.get("confidence")),
            result_status=(market_eval or {}).get("goal_minute") or gm_eval.get("status") or default_status,
            withheld=fg_withheld,
            withheld_reason=fg_reason,
            extra={
                "minute_range": fg.get("minute_range"),
                "expected_minute": fg.get("expected_minute"),
                "actual": gm_eval.get("actual"),
                "eval_reason": gm_eval.get("reason"),
            },
        )
    )

    gs = dm.get("goalscorer") if isinstance(dm.get("goalscorer"), dict) else {}
    gs_withheld, gs_reason = _consistency_status(gs)
    gs_eval = _advanced_eval_block(advanced_markets, "goalscorer")
    if gs.get("available") is not False or gs.get("player"):
        markets.append(
            _market_block(
                key="goalscorer",
                label="Goalscorer",
                selection=gs.get("player"),
                probabilities={},
                confidence=_prob_pct(gs.get("confidence")),
                result_status=(market_eval or {}).get("goalscorer") or gs_eval.get("status") or default_status,
                withheld=gs_withheld,
                withheld_reason=gs_reason,
                extra={
                    "team": gs.get("team"),
                    "available": bool(gs.get("available", True)),
                    "actual": gs_eval.get("actual"),
                    "eval_reason": gs_eval.get("reason"),
                },
            )
        )

    ht = dm.get("halftime") if isinstance(dm.get("halftime"), dict) else {}
    ht_withheld, ht_reason = _consistency_status(ht)
    ht_eval = _advanced_eval_block(advanced_markets, "ht_result")
    if ht.get("selection") or ht.get("probabilities"):
        markets.append(
            _market_block(
                key="ht_result",
                label="HT Result",
                selection=ht.get("selection") or ht.get("display"),
                probabilities=ht.get("probabilities") if isinstance(ht.get("probabilities"), dict) else {},
                confidence=_prob_pct(ht.get("probability")),
                result_status=(market_eval or {}).get("ht_result") or ht_eval.get("status") or default_status,
                withheld=ht_withheld,
                withheld_reason=ht_reason,
                extra={"actual": ht_eval.get("actual"), "eval_reason": ht_eval.get("reason")},
            )
        )

    cs_raw = dm.get("correct_scores")
    cs_eval = _advanced_eval_block(advanced_markets, "correct_score")
    cs_selection = None
    cs_conf = None
    if isinstance(cs_raw, list) and cs_raw:
        best = max(
            (r for r in cs_raw if isinstance(r, dict)),
            key=lambda r: float(r.get("probability") or 0),
            default=None,
        )
        if best:
            cs_selection = best.get("label") or best.get("scoreline")
            cs_conf = best.get("probability")
    elif isinstance(cs_raw, dict):
        cs_selection = cs_raw.get("selection") or cs_raw.get("label")
    if cs_selection:
        markets.append(
            _market_block(
                key="correct_score",
                label="Correct Score",
                selection=cs_selection,
                probabilities={},
                confidence=_prob_pct(cs_conf),
                result_status=(market_eval or {}).get("correct_score") or cs_eval.get("status") or default_status,
                extra={"actual": cs_eval.get("actual"), "eval_reason": cs_eval.get("reason")},
            )
        )

    dc = dm.get("double_chance") if isinstance(dm.get("double_chance"), dict) else {}
    if dc:
        best_key = max(
            ("home_or_draw", "draw_or_away", "home_or_away"),
            key=lambda k: float(dc.get(k) or 0),
        )
        dc_withheld, dc_reason = _consistency_status(dc)
        markets.append(
            _market_block(
                key="double_chance",
                label="Double Chance",
                selection=best_key,
                probabilities={
                    "home_or_draw": dc.get("home_or_draw"),
                    "draw_or_away": dc.get("draw_or_away"),
                    "home_or_away": dc.get("home_or_away"),
                },
                confidence=float(dc.get(best_key) or 0) if dc.get(best_key) is not None else None,
                result_status=(market_eval or {}).get("double_chance") or default_status,
                withheld=dc_withheld,
                withheld_reason=dc_reason,
            )
        )

    if not snapshot and record.prediction_1x2 and len(markets) == 1:
        pass

    return markets


def _market_outcomes(fixture_id: int, outcome: FixtureOutcome) -> dict[str, Any]:
    results: dict[str, Any] = {}
    if outcome.final_score:
        results["final_score"] = outcome.final_score
    if outcome.actual_result:
        results["winner"] = outcome.actual_result

    jsonl = MatchResultsStore().by_fixture_id().get(fixture_id)
    if jsonl is not None:
        results["over_under_2_5"] = jsonl.over_under_2_5_result
        if jsonl.final_score and "-" in jsonl.final_score:
            parts = jsonl.final_score.split("-", 1)
            try:
                h, a = int(parts[0]), int(parts[1])
                results["btts"] = "yes" if h > 0 and a > 0 else "no"
                results["total_goals"] = h + a
            except ValueError:
                pass
        elif jsonl.total_goals is not None:
            results["total_goals"] = jsonl.total_goals
    elif outcome.is_finished and outcome.final_score and "-" in outcome.final_score:
        parts = outcome.final_score.split("-", 1)
        try:
            h, a = int(parts[0]), int(parts[1])
            total = h + a
            results["over_under_2_5"] = "over_2_5" if total > 2 else "under_2_5"
            results["btts"] = "yes" if h > 0 and a > 0 else "no"
            results["total_goals"] = total
        except ValueError:
            pass

    return results


def _consistency_section(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    guard = (snapshot or {}).get("consistency_guard") or {}
    if not isinstance(guard, dict) or not guard:
        return {
            "available": False,
            "withheld_markets": [],
            "consistency_warnings": [],
        }
    return {
        "available": bool(guard.get("applied")),
        "withheld_markets": list(guard.get("withheld_markets") or []),
        "consistency_warnings": list(guard.get("consistency_warnings") or []),
        "rules_version": guard.get("rules_version"),
        "applied_rules": list(guard.get("applied_rules") or []),
    }


def _metadata_section(
    snapshot: dict[str, Any] | None,
    *,
    snapshot_source: SnapshotSource,
    record: PredictionHistoryRecord,
) -> dict[str, Any]:
    snap = snapshot or {}
    generated_at = snap.get("generated_at") or snap.get("predicted_at")
    if not generated_at and record.viewed_at:
        generated_at = record.viewed_at.isoformat()

    return {
        "prediction_engine_version": snap.get("prediction_engine_version"),
        "adaptive_confidence_version": snap.get("adaptive_confidence_version"),
        "generated_at": generated_at,
        "snapshot_source": snapshot_source,
        "cache_schema_version": snap.get("cache_schema_version"),
        "data_quality": snap.get("data_quality"),
        "kickoff_utc": snap.get("kickoff_utc") or (kickoff_from_payload(snap).isoformat() if kickoff_from_payload(snap) else None),
    }


def build_prediction_archive_detail(
    record: PredictionHistoryRecord,
    *,
    resolver: FixtureOutcomeResolver | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Merge evaluated history row with stored prediction snapshot for archive detail."""
    from worldcup_predictor.api.archive_evaluation_join import (
        compute_row_status_from_evaluation,
        count_market_statuses,
        evaluation_to_market_eval_dict,
        is_quarantined_evaluation,
        market_statuses_from_evaluation_row,
    )
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    settings = settings or get_settings()
    resolver = resolver or FixtureOutcomeResolver(settings=settings)
    evaluated = evaluate_history_record(record, resolver=resolver, settings=settings)
    outcome = resolver.resolve(record.fixture_id)
    snapshot, snapshot_source = load_archive_snapshot(record.fixture_id, settings=settings)

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    db_eval = repo.get_worldcup_prediction_evaluation(record.fixture_id)

    market_eval: dict[str, str] | None = None
    advanced_markets: dict[str, Any] | None = None
    if db_eval and not is_quarantined_evaluation(db_eval):
        market_eval = evaluation_to_market_eval_dict(db_eval)
        row_status, row_reason = compute_row_status_from_evaluation(db_eval)
        counts = count_market_statuses(market_statuses_from_evaluation_row(db_eval))
        evaluated["result_status"] = row_status
        evaluated["result"] = row_status
        evaluated["row_status_reason"] = row_reason
        evaluated["actual_result"] = db_eval.get("actual_result") or evaluated.get("actual_result")
        evaluated["final_score"] = db_eval.get("final_score") or evaluated.get("final_score")
        evaluated["evaluated_at"] = db_eval.get("evaluated_at") or evaluated.get("evaluated_at")
        evaluated.update(counts)
        evaluated["evaluation_status"] = row_status
        evaluated["market_statuses"] = market_statuses_from_evaluation_row(db_eval)
        if row_status in {"correct", "wrong", "partial"}:
            evaluated["is_finished"] = True
    elif snapshot:
        eval_payload = dict(snapshot)
        if not eval_payload.get("prediction") and record.prediction_1x2:
            eval_payload["prediction"] = record.prediction_1x2.value
        stored_eval = evaluate_stored_prediction(eval_payload, outcome)
        raw_markets = stored_eval.get("markets") or {}
        market_eval = {k: str(v) for k, v in raw_markets.items() if k in _MARKET_EVAL_KEYS.values() or k in _MARKET_EVAL_KEYS}
        advanced_markets = stored_eval.get("advanced_markets")

    match_name = f"{record.home_team} vs {record.away_team}"
    confidence = evaluated.get("confidence")
    main_prediction = evaluated.get("predicted_1x2")
    snap = snapshot or {}

    eval_source = "fixture_resolver"
    if db_eval and not is_quarantined_evaluation(db_eval):
        eval_source = "worldcup_prediction_evaluations"
    elif snapshot:
        eval_source = "stored_snapshot"

    return {
        "status": "ok",
        "entry_id": str(record.id),
        "prediction_id": record.prediction_id,
        "fixture_id": record.fixture_id,
        "match_name": match_name,
        "competition": record.league or "World Cup 2026",
        "match_date": evaluated.get("match_date"),
        "prediction_date": evaluated.get("viewed_at"),
        "home_team": record.home_team,
        "away_team": record.away_team,
        "summary": {
            "confidence": confidence,
            "main_prediction": main_prediction,
            "main_prediction_label": _display_selection(main_prediction),
            "result_status": evaluated.get("result_status"),
        },
        "prediction": {
            "markets": _build_markets(
                snapshot,
                record=record,
                market_eval=market_eval,
                advanced_markets=advanced_markets,
                outcome=outcome,
            ),
            "probabilities": (snapshot or {}).get("probabilities") or {},
            "confidence": confidence,
            "detailed_markets_available": snapshot is not None,
        },
        "evaluation": {
            "result_status": evaluated.get("result_status"),
            "evaluation_status": evaluated.get("evaluation_status") or evaluated.get("result_status"),
            "is_correct": evaluated.get("is_correct"),
            "actual_result": evaluated.get("actual_result"),
            "actual_result_label": _display_selection(evaluated.get("actual_result")),
            "final_score": evaluated.get("final_score"),
            "evaluated_at": evaluated.get("evaluated_at"),
            "is_finished": evaluated.get("is_finished"),
            "evaluated_markets_count": evaluated.get("evaluated_markets_count"),
            "correct_markets_count": evaluated.get("correct_markets_count"),
            "wrong_markets_count": evaluated.get("wrong_markets_count"),
            "pending_markets_count": evaluated.get("pending_markets_count"),
            "market_statuses": evaluated.get("market_statuses") or {},
            "market_outcomes": _market_outcomes(record.fixture_id, outcome),
            "advanced_markets": advanced_markets or {},
        },
        "consistency": _consistency_section(snapshot),
        "metadata": _metadata_section(snapshot, snapshot_source=snapshot_source, record=record),
        "evaluation_source": {
            "source": eval_source,
            "evaluated_at": evaluated.get("evaluated_at"),
            "row_status_reason": evaluated.get("row_status_reason"),
            "is_quarantined": bool(db_eval and is_quarantined_evaluation(db_eval)),
        },
        "agent_summary": {
            "available": bool(snap.get("specialist_summary")),
            "specialist_summary": snap.get("specialist_summary"),
            "agent_count": snap.get("specialist_agent_count"),
        },
        "confidence_trace": {
            "available": bool(
                snap.get("adaptive_confidence_trace")
                or snap.get("rule_a_gate")
                or snap.get("rule_a")
            ),
            "adaptive_confidence_trace": snap.get("adaptive_confidence_trace"),
            "rule_a_gate": snap.get("rule_a_gate") or snap.get("rule_a"),
        },
        "prediction_explanation": {
            "available": bool(
                snap.get("audit_trace")
                or snap.get("harmonization")
                or snap.get("harmonization_summary")
                or snap.get("reasoning")
                or snap.get("explanation")
            ),
            "audit_trace": snap.get("audit_trace"),
            "harmonization": snap.get("harmonization") or snap.get("harmonization_summary"),
            "reasoning": snap.get("reasoning") or snap.get("explanation"),
        },
        "premium_placeholders": {
            "specialist_votes": {"available": False, "message": "Premium feature — coming soon"},
            "agent_explanations": {"available": False, "message": "Premium feature — coming soon"},
            "odds_movement": {"available": False, "message": "Premium feature — coming soon"},
            "prediction_snapshots": {"available": False, "message": "Premium feature — coming soon"},
        },
    }


def fetch_archive_detail_for_user(
    user_id: uuid.UUID,
    entry_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    from worldcup_predictor.database.saas_factory import saas_uow

    with saas_uow() as uow:
        record = uow.prediction_history.get_for_user(user_id, entry_id)
    if record is None:
        return None
    return build_prediction_archive_detail(record, settings=settings)


def _map_prediction_1x2(value: str | None) -> Prediction1x2:
    key = str(value or "home").lower()
    mapping = {
        "home": Prediction1x2.HOME,
        "home_win": Prediction1x2.HOME,
        "draw": Prediction1x2.DRAW,
        "away": Prediction1x2.AWAY,
        "away_win": Prediction1x2.AWAY,
    }
    return mapping.get(key, Prediction1x2.HOME)


def build_global_archive_detail(
    fixture_id: int,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Phase 42D — archive detail for a global SQLite stored prediction."""
    from decimal import Decimal

    from worldcup_predictor.api.global_prediction_archive import _detect_source, _main_prediction, global_entry_id
    from worldcup_predictor.database.postgres.enums import PredictionResult
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    stored = repo.get_worldcup_stored_prediction(fixture_id, include_inactive=True)
    if not stored or not stored.get("payload_json"):
        return None

    snapshot, snapshot_source = load_archive_snapshot(fixture_id, settings=settings)
    if not snapshot:
        return None

    fixture = repo.get_fixture_row(fixture_id) or {}
    home = fixture.get("home_team") or snapshot.get("home_team") or "Home"
    away = fixture.get("away_team") or snapshot.get("away_team") or "Away"
    main_pred = _main_prediction(snapshot) or "home"
    viewed_at_raw = stored.get("predicted_at") or snapshot.get("generated_at")
    viewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if viewed_at_raw:
        try:
            viewed_at = datetime.fromisoformat(str(viewed_at_raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass

    synthetic = PredictionHistoryRecord(
        id=uuid.uuid5(uuid.NAMESPACE_OID, f"global-archive-{fixture_id}"),
        user_id=uuid.UUID(int=0),
        fixture_id=int(fixture_id),
        prediction_id=f"global-{fixture_id}",
        home_team=str(home),
        away_team=str(away),
        league=snapshot.get("competition") or snapshot.get("league") or "World Cup 2026",
        match_date=viewed_at,
        prediction_1x2=_map_prediction_1x2(main_pred),
        confidence=Decimal(str(snapshot.get("confidence") or 0)),
        result=PredictionResult.PENDING,
        viewed_at=viewed_at,
    )
    detail = build_prediction_archive_detail(synthetic, settings=settings)
    detail["entry_id"] = global_entry_id(fixture_id)
    detail["source"] = _detect_source(snapshot, stored)
    detail["scope"] = "global"
    detail["metadata"]["snapshot_source"] = snapshot_source
    return detail
