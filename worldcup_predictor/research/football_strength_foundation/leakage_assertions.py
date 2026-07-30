"""Leakage assertions for prematch feature construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class LeakageViolation:
    code: str
    detail: str


def assert_kickoff_before_cutoff(kickoff: datetime, cutoff: datetime) -> LeakageViolation | None:
    if kickoff >= cutoff:
        return LeakageViolation("KICKOFF_NOT_BEFORE_CUTOFF", f"{kickoff} >= {cutoff}")
    return None


def assert_not_same_fixture(hist_fixture_id: Any, target_fixture_id: Any) -> LeakageViolation | None:
    if hist_fixture_id is None or target_fixture_id is None:
        return None
    if int(hist_fixture_id) == int(target_fixture_id):
        return LeakageViolation("SAME_FIXTURE_CONTAMINATION", f"fixture_id={target_fixture_id}")
    return None


def assert_result_timestamp(result_ts: datetime | None, cutoff: datetime, *, required: bool = False) -> LeakageViolation | None:
    if result_ts is None:
        if required:
            return LeakageViolation("MISSING_RESULT_TIMESTAMP", "required but absent")
        return None
    if result_ts > cutoff:
        return LeakageViolation("RESULT_AFTER_CUTOFF", f"{result_ts} > {cutoff}")
    return None


def validate_history_row(
    *,
    hist_kickoff: datetime,
    cutoff: datetime,
    hist_fixture_id: Any = None,
    target_fixture_id: Any = None,
    result_ts: datetime | None = None,
    require_result_ts: bool = False,
) -> list[LeakageViolation]:
    out: list[LeakageViolation] = []
    for fn in (
        assert_kickoff_before_cutoff(hist_kickoff, cutoff),
        assert_not_same_fixture(hist_fixture_id, target_fixture_id),
        assert_result_timestamp(result_ts, cutoff, required=require_result_ts),
    ):
        if fn is not None:
            out.append(fn)
    return out


def raise_if_leaks(violations: list[LeakageViolation]) -> None:
    if violations:
        msg = "; ".join(f"{v.code}:{v.detail}" for v in violations)
        raise ValueError(f"LEAKAGE_DETECTED: {msg}")
