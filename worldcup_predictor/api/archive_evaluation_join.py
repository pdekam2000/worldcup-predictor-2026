"""Shared archive ↔ production evaluation join (Phase 45B quarantine-safe)."""

from __future__ import annotations

from typing import Any

# Keys match pick_evaluator / worldcup_prediction_evaluations columns.
ARCHIVE_MARKET_STATUS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("1x2", "market_1x2_status"),
    ("over_under_2_5", "market_ou_status"),
    ("btts", "market_btts_status"),
    ("double_chance", "market_dc_status"),
    ("ht_result", "market_ht_status"),
    ("correct_score", "market_cs_status"),
    ("first_goal_team", "market_fg_team_status"),
    ("goalscorer", "market_goalscorer_status"),
    ("goal_minute", "market_goal_minute_status"),
)


def normalize_eval_status(raw: str | None) -> str:
    value = str(raw or "pending").lower().strip()
    if value in {"correct", "wrong", "partial", "pending", "unavailable"}:
        return value
    if value in {"unknown", "void", ""}:
        return "unavailable"
    return "pending"


def is_quarantined_evaluation(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    return bool(int(row.get("is_quarantined") or 0))


def market_statuses_from_evaluation_row(
    evaluation: dict[str, Any] | None,
    *,
    include_quarantined: bool = False,
) -> dict[str, str]:
    if not evaluation:
        return {}
    if is_quarantined_evaluation(evaluation) and not include_quarantined:
        return {}
    out: dict[str, str] = {}
    for market_key, col in ARCHIVE_MARKET_STATUS_COLUMNS:
        out[market_key] = normalize_eval_status(evaluation.get(col))
    return out


def count_market_statuses(market_statuses: dict[str, str]) -> dict[str, int]:
    correct = wrong = pending = unavailable = 0
    for status in market_statuses.values():
        if status == "correct":
            correct += 1
        elif status == "wrong":
            wrong += 1
        elif status == "unavailable":
            unavailable += 1
        else:
            pending += 1
    evaluated = correct + wrong
    return {
        "evaluated_markets_count": evaluated,
        "correct_markets_count": correct,
        "wrong_markets_count": wrong,
        "pending_markets_count": pending,
        "unavailable_markets_count": unavailable,
        "total_markets_tracked": len(market_statuses),
    }


def compute_row_status_from_evaluation(
    evaluation: dict[str, Any] | None,
    *,
    include_quarantined: bool = False,
) -> tuple[str, str]:
    """Return (row_status, row_status_reason) using market-level card aggregate."""
    if not evaluation:
        return "pending", "no_valid_evaluation"
    if is_quarantined_evaluation(evaluation) and not include_quarantined:
        return "pending", "no_valid_evaluation"

    detail_raw = evaluation.get("detail_json")
    if detail_raw:
        try:
            import json

            detail = json.loads(detail_raw) if isinstance(detail_raw, str) else dict(detail_raw)
            card = str(detail.get("card_status") or "").lower()
            reason = str(detail.get("card_status_reason") or "market_card_aggregate")
            if card in {"correct", "wrong", "partial", "pending", "unavailable"}:
                return card, reason
        except (json.JSONDecodeError, TypeError):
            pass

    market_statuses = market_statuses_from_evaluation_row(
        evaluation,
        include_quarantined=include_quarantined,
    )
    counts = count_market_statuses(market_statuses)
    if counts["evaluated_markets_count"] == 0:
        overall = normalize_eval_status(evaluation.get("overall_status"))
        if overall in {"correct", "wrong", "partial", "unavailable"}:
            return overall, "overall_status_fallback"
        return "pending", "no_valid_evaluation"

    if counts["correct_markets_count"] > 0 and counts["wrong_markets_count"] > 0:
        return "partial", "mixed_market_results"
    if counts["wrong_markets_count"] > 0 and counts["correct_markets_count"] == 0:
        return "wrong", "evaluated_markets_all_wrong"
    if counts["correct_markets_count"] > 0 and counts["wrong_markets_count"] == 0:
        return "correct", "evaluated_markets_all_correct"
    return "pending", "markets_unsettled"


def evaluation_to_market_eval_dict(evaluation: dict[str, Any] | None) -> dict[str, str]:
    """Map DB evaluation row to pick_evaluator-style market_eval keys."""
    statuses = market_statuses_from_evaluation_row(evaluation)
    return {k: v for k, v in statuses.items() if v in {"correct", "wrong", "partial", "pending"}}


def enrich_row_with_evaluation(
    row: dict[str, Any],
    evaluation: dict[str, Any] | None,
    *,
    prefer_evaluation: bool = True,
) -> dict[str, Any]:
    """Attach production evaluation status fields to an archive/history list row."""
    if not evaluation or is_quarantined_evaluation(evaluation):
        return row

    row_status, reason = compute_row_status_from_evaluation(evaluation)
    counts = count_market_statuses(market_statuses_from_evaluation_row(evaluation))
    market_statuses = market_statuses_from_evaluation_row(evaluation)

    # Always apply production evaluation when present (never let stale pending hide truth).
    row = dict(row)
    if prefer_evaluation or normalize_eval_status(row.get("result_status")) == "pending" or row_status in {
        "correct",
        "wrong",
        "partial",
    }:
        row["result_status"] = row_status
        row["result"] = row_status
        row["evaluation_status"] = row_status
        row["row_status_reason"] = reason
        row["actual_result"] = evaluation.get("actual_result") or row.get("actual_result")
        row["final_score"] = evaluation.get("final_score") or row.get("final_score")
        row["evaluated_at"] = evaluation.get("evaluated_at") or row.get("evaluated_at")
        row["is_finished"] = row_status in {"correct", "wrong", "partial"} or bool(row.get("is_finished"))
        row.update(counts)
        row["market_statuses"] = market_statuses
    return row


def merge_history_row_pair(global_row: dict[str, Any], my_row: dict[str, Any]) -> dict[str, Any]:
    """Merge user + global rows — never let pending personal row hide production evaluation."""
    g_status = normalize_eval_status(global_row.get("result_status"))
    m_status = normalize_eval_status(my_row.get("result_status"))
    settled = {"correct", "wrong", "partial"}

    def _evaluation_strength(row: dict[str, Any]) -> int:
        status = normalize_eval_status(row.get("result_status"))
        if status in settled:
            return 4
        if int(row.get("evaluated_markets_count") or 0) > 0:
            return 3
        if row.get("evaluated_at"):
            return 2
        if row.get("is_finished"):
            return 1
        return 0

    if g_status in settled and m_status == "pending":
        merged = dict(global_row)
        merged["entry_id"] = my_row.get("entry_id") or global_row.get("entry_id")
        merged["id"] = my_row.get("id") or global_row.get("id")
        merged["source"] = "my"
        merged["viewed_at"] = my_row.get("viewed_at") or global_row.get("viewed_at")
        return merged

    if m_status in settled:
        return my_row

    if g_status in settled:
        merged = dict(global_row)
        merged["entry_id"] = my_row.get("entry_id") or global_row.get("entry_id")
        merged["source"] = my_row.get("source") or global_row.get("source")
        return merged

    if _evaluation_strength(global_row) > _evaluation_strength(my_row):
        merged = dict(global_row)
        merged["entry_id"] = my_row.get("entry_id") or global_row.get("entry_id")
        merged["id"] = my_row.get("id") or global_row.get("id")
        merged["source"] = my_row.get("source") or global_row.get("source")
        merged["viewed_at"] = my_row.get("viewed_at") or global_row.get("viewed_at")
        return merged

    return my_row
