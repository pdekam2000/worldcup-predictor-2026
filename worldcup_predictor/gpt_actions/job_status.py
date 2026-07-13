"""Terminal vs non-terminal prediction job status semantics for GPT Actions polling."""

from __future__ import annotations

from typing import Any, Literal

JobStatus = Literal["queued", "running", "completed", "partial", "failed", "cancelled"]

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "partial", "failed", "cancelled"})
NON_TERMINAL_STATUSES: frozenset[str] = frozenset({"queued", "running"})

CONTINUATION_CODE = "PREDICTION_JOB_STILL_RUNNING"
COMPLETED_RESULT_MISSING = "completed_result_missing_internal"


def is_terminal_status(status: str | None) -> bool:
    return str(status or "").lower() in TERMINAL_STATUSES


def should_poll_again(status: str | None) -> bool:
    return str(status or "").lower() in NON_TERMINAL_STATUSES


def polling_message(status: str | None) -> str | None:
    if not should_poll_again(status):
        return None
    return (
        "Prediction job is not finished. Poll getPredictionJob with the same job_id. "
        "Do not present final WDE/ECSE output while status is queued or running."
    )


def continuation_code(status: str | None) -> str | None:
    if should_poll_again(status):
        return CONTINUATION_CODE
    return None


def sanitize_completed_result(
    *,
    status: str,
    result: dict[str, Any] | None,
    error: str | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Reject completed+null result; preserve partial/failed semantics."""
    st = str(status).lower()
    if st == "completed" and result is None:
        return "failed", None, COMPLETED_RESULT_MISSING
    if st == "failed" and not error:
        return st, result, "prediction_job_failed"
    return st, result, error


def build_job_status_fields(
    record: dict[str, Any],
    *,
    poll_after_seconds: int,
) -> dict[str, Any]:
    """Build explicit polling fields from a stored job record."""
    status = str(record.get("status") or "queued")
    result = record.get("result")
    error = record.get("error")
    status, result, error = sanitize_completed_result(status=status, result=result, error=error)

    terminal = is_terminal_status(status)
    poll_again = should_poll_again(status)

    out: dict[str, Any] = {
        "job_id": record["job_id"],
        "status": status,
        "terminal": terminal,
        "should_poll_again": poll_again,
        "poll_after_seconds": poll_after_seconds if poll_again else 0,
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "started_at": record.get("started_at"),
        "completed_at": record.get("completed_at"),
        "result": result if terminal and status in ("completed", "partial") else (None if poll_again else result),
        "error": error if terminal and status == "failed" else (None if poll_again else error),
        "continuation_code": continuation_code(status),
        "polling_message": polling_message(status),
    }
    return out


def build_job_create_fields(record: dict[str, Any], *, poll_after_seconds: int) -> dict[str, Any]:
    status = str(record.get("status") or "queued")
    return {
        "job_id": record["job_id"],
        "status": status,
        "terminal": False,
        "should_poll_again": True,
        "poll_after_seconds": poll_after_seconds,
        "created_at": record.get("created_at"),
        "polling_message": polling_message(status),
        "continuation_code": CONTINUATION_CODE,
    }
