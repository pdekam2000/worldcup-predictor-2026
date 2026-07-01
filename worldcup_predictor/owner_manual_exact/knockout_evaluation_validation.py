"""Validation for owner knockout prediction evaluation artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from worldcup_predictor.accuracy.evaluator import actual_1x2, actual_over_under
from worldcup_predictor.owner_manual_exact.knockout_evaluation import (
    EVAL_PHASE,
    SAFETY_LABELS,
    artifact_json_path,
    jsonl_path,
    load_evaluation_artifact,
)
from worldcup_predictor.owner_manual_exact.resolver import _date_tag
from worldcup_predictor.owner_manual_exact.constants import ARTIFACTS_DIR
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date
from worldcup_predictor.elite_orchestrator.shadow_jsonl_io import load_jsonl


def _load_predictions_artifact(process_date: date) -> dict[str, Any] | None:
    path = ARTIFACTS_DIR / f"manual_owner_exact_score_predictions_{_date_tag(process_date)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_scoreline(scoreline: str) -> tuple[int, int] | None:
    if not scoreline or "-" not in scoreline:
        return None
    parts = scoreline.split("-", 1)
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _normalize_scoreline(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).replace(":", "-").strip()


def _expected_production_eval(pred: dict[str, Any], actual_score: str) -> dict[str, Any]:
    parsed = _parse_scoreline(actual_score)
    if not parsed:
        return {}
    hg, ag = parsed
    top1 = _normalize_scoreline(pred.get("exact_top1"))
    top3 = [_normalize_scoreline(s) or s for s in (pred.get("exact_top3") or [])]
    actual_x2 = actual_1x2(hg, ag)
    actual_ou = actual_over_under(hg, ag)
    actual_btts = "yes" if hg > 0 and ag > 0 else "no"
    return {
        "exact_top1_hit": top1 == actual_score,
        "exact_top3_hit": actual_score in top3,
        "one_x_two_hit": pred.get("pick_1x2") == actual_x2,
        "btts_hit": pred.get("pick_btts") == actual_btts,
        "over_under_2_5_hit": pred.get("pick_ou25") == actual_ou,
    }


@dataclass
class ValidationCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class KnockoutEvalValidationResult:
    phase: str = EVAL_PHASE
    passed: bool = False
    process_date: str = ""
    checks: list[ValidationCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "process_date": self.process_date,
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            **{k: v for k, v in SAFETY_LABELS.items()},
        }


def _chk(checks: list[ValidationCheck], name: str, ok: bool, detail: str = "") -> None:
    checks.append(ValidationCheck(name=name, passed=ok, detail=detail))


def validate_owner_knockout_prediction_evaluation(
    *,
    date_arg: str = "today",
    timezone: str = "Europe/Vienna",
) -> KnockoutEvalValidationResult:
    process_date = resolve_process_date(date_arg, timezone)
    checks: list[ValidationCheck] = []
    preds_payload = _load_predictions_artifact(process_date)
    eval_payload = load_evaluation_artifact(process_date)

    _chk(checks, "predictions_artifact_exists", preds_payload is not None)
    _chk(checks, "evaluation_artifact_exists", eval_payload is not None)
    if not eval_payload:
        return KnockoutEvalValidationResult(
            process_date=process_date.isoformat(),
            passed=False,
            checks=checks,
        )

    _chk(checks, "evaluation_phase", eval_payload.get("phase") == EVAL_PHASE)
    _chk(checks, "fixture_count_is_12", int(eval_payload.get("fixture_count") or 0) == 12)

    for key, expected in SAFETY_LABELS.items():
        _chk(
            checks,
            f"safety_{key.lower()}",
            eval_payload.get(key) is expected,
            f"got={eval_payload.get(key)} expected={expected}",
        )

    pred_by_fid: dict[int, dict[str, Any]] = {}
    if preds_payload:
        for p in preds_payload.get("predictions") or []:
            if p.get("fixture_id"):
                pred_by_fid[int(p["fixture_id"])] = p

    fixtures = eval_payload.get("fixtures") or []
    evaluated = [r for r in fixtures if r.get("evaluation_status") == "EVALUATED"]
    waiting = [r for r in fixtures if r.get("evaluation_status") == "WAITING_FOR_RESULT"]

    _chk(
        checks,
        "evaluated_plus_waiting_equals_12",
        len(evaluated) + len(waiting) == 12,
        f"evaluated={len(evaluated)} waiting={len(waiting)}",
    )
    _chk(
        checks,
        "counts_match_summary",
        int(eval_payload.get("evaluated_count") or 0) == len(evaluated)
        and int(eval_payload.get("waiting_result_count") or 0) == len(waiting),
    )

    for row in waiting:
        _chk(
            checks,
            f"waiting_no_final_score_{row.get('fixture_id')}",
            not row.get("final_score"),
            "pending fixture must not have final_score",
        )
        _chk(
            checks,
            f"waiting_not_counted_as_loss_{row.get('fixture_id')}",
            row.get("production_evaluation") is None,
            "pending fixture must not have production_evaluation",
        )

    math_ok = True
    for row in evaluated:
        fid = int(row["fixture_id"])
        final_score = str(row.get("final_score") or "")
        _chk(
            checks,
            f"evaluated_has_final_score_{fid}",
            bool(final_score and "-" in final_score),
        )
        pred = pred_by_fid.get(fid)
        if pred and final_score:
            expected = _expected_production_eval(pred, final_score)
            pe = row.get("production_evaluation") or {}
            for metric in (
                "exact_top1_hit",
                "exact_top3_hit",
                "one_x_two_hit",
                "btts_hit",
                "over_under_2_5_hit",
            ):
                ok = pe.get(metric) == expected.get(metric)
                if not ok:
                    math_ok = False
                _chk(
                    checks,
                    f"{metric}_{fid}",
                    ok,
                    f"got={pe.get(metric)} expected={expected.get(metric)}",
                )

        mc = row.get("model_comparison") or {}
        shadow = mc.get("wde_shadow") or {}
        _chk(
            checks,
            f"wde_shadow_not_production_{fid}",
            shadow.get("production_counted") is not True,
            "shadow must not be production_counted",
        )
        _chk(
            checks,
            f"wde_shadow_marked_shadow_only_{fid}",
            shadow.get("shadow_only") is True or shadow.get("status") != "EVALUATED",
            detail=str(shadow.get("shadow_only")),
        )

    _chk(checks, "production_math_correct", math_ok)

    metrics = eval_payload.get("metrics") or {}
    if evaluated:
        pe_list = [r.get("production_evaluation") or {} for r in evaluated]
        top1_acc = sum(1 for p in pe_list if p.get("exact_top1_hit")) / len(pe_list)
        reported = metrics.get("exact_top1_accuracy")
        _chk(
            checks,
            "metrics_exact_top1_accuracy",
            reported is not None and abs(float(reported) - top1_acc) < 0.0001,
            f"reported={reported} recomputed={round(top1_acc, 4)}",
        )

    jpath = jsonl_path(process_date)
    _chk(checks, "jsonl_exists", jpath.exists(), str(jpath))
    if jpath.exists() and evaluated:
        rows = load_jsonl(jpath)
        eval_fids = {int(r["fixture_id"]) for r in evaluated}
        jsonl_fids = {int(r["fixture_id"]) for r in rows if r.get("fixture_id")}
        _chk(
            checks,
            "jsonl_covers_evaluated_fixtures",
            eval_fids.issubset(jsonl_fids),
            f"missing={eval_fids - jsonl_fids}",
        )
        dup_count = 0
        seen: set[tuple[Any, ...]] = set()
        for row in rows:
            key = (row.get("process_date"), int(row.get("fixture_id") or 0))
            if key in seen:
                dup_count += 1
            seen.add(key)
        _chk(
            checks,
            "jsonl_append_only_no_duplicate_keys",
            dup_count == 0,
            f"duplicate_rows={dup_count} total_rows={len(rows)}",
        )
        for row in rows:
            _chk(
                checks,
                f"jsonl_no_public_publish_{row.get('fixture_id')}",
                row.get("PUBLIC_PUBLISH") is False,
            )

    art_path = artifact_json_path(process_date)
    _chk(checks, "artifact_path_matches", art_path.exists())

    passed = all(c.passed for c in checks)
    return KnockoutEvalValidationResult(
        process_date=process_date.isoformat(),
        passed=passed,
        checks=checks,
    )
