"""Temporal safety filters for national team history (Phase 32E)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.intelligence.national_team._shared import (
    filter_history_fixtures,
    fixture_item_id,
    resolve_report_kickoff,
)


def history_filter_context(
    report: MatchIntelligenceReport,
    *,
    repo: Any | None = None,
) -> tuple[datetime | None, int | None]:
    kickoff = resolve_report_kickoff(report, repo=repo)
    fixture_id = int(report.fixture_id) if report.fixture_id else None
    return kickoff, fixture_id


def apply_history_filters(
    fixtures: list[dict[str, Any]] | None,
    *,
    before_kickoff: datetime | None,
    exclude_fixture_id: int | None,
) -> list[dict[str, Any]]:
    return filter_history_fixtures(
        fixtures,
        before_kickoff=before_kickoff,
        exclude_fixture_id=exclude_fixture_id,
    )


def count_history_violations(
    fixtures: list[dict[str, Any]] | None,
    *,
    before_kickoff: datetime | None,
    exclude_fixture_id: int | None,
) -> dict[str, int]:
    future = circular = 0
    for item in fixtures or []:
        if not isinstance(item, dict):
            continue
        fid = fixture_item_id(item)
        if exclude_fixture_id is not None and fid is not None and int(fid) == int(exclude_fixture_id):
            circular += 1
        if before_kickoff is not None:
            from worldcup_predictor.intelligence.national_team._shared import fixture_item_kickoff

            kick = fixture_item_kickoff(item)
            if kick is not None and kick >= before_kickoff:
                future += 1
    return {"future_leaks": future, "circular_refs": circular}


__all__ = [
    "apply_history_filters",
    "count_history_violations",
    "history_filter_context",
]
