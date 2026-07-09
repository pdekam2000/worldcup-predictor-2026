"""MCP prediction tools."""

from __future__ import annotations

from worldcup_predictor.mcp_server.policies import (
    MAX_PREDICTION_FIXTURES,
    validate_fixture_id_list,
    validate_positive_fixture_id,
)
from worldcup_predictor.mcp_server import runtime


def run_fixture_prediction(fixture_id: int, refresh_if_stale: bool = True) -> dict[str, object]:
    fid = validate_positive_fixture_id(fixture_id)
    return runtime.run_fixture_prediction(fid, refresh_if_stale=refresh_if_stale)


def run_batch_predictions(fixture_ids: list[int], refresh_if_stale: bool = True) -> dict[str, object]:
    ids = validate_fixture_id_list(
        fixture_ids, max_count=MAX_PREDICTION_FIXTURES, label="fixture_ids"
    )
    return runtime.run_batch_predictions(ids, refresh_if_stale=refresh_if_stale)
