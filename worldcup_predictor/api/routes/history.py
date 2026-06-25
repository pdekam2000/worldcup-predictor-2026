"""Phase 42C/42D — prediction archive list + detail routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from worldcup_predictor.api.deps import get_current_user
from worldcup_predictor.api.global_prediction_archive import (
    fetch_merged_history,
    is_global_entry_id,
    parse_global_fixture_id,
)
from worldcup_predictor.api.prediction_archive_detail import (
    build_global_archive_detail,
    fetch_archive_detail_for_user,
)
from worldcup_predictor.api.saas_serializers import parse_uuid
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.config.settings import get_settings as get_app_settings

router = APIRouter(prefix="/history", tags=["history"])


def _user_id(user: WebAuthUser):
    return parse_uuid(user.id, field="user id")


@router.get("")
def list_prediction_history(
    scope: Literal["my", "global", "all"] = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    result_filter: str = Query(default="all"),
    sort: str = Query(default="newest"),
    competition: str = Query(default="world_cup_2026"),
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List prediction history — my, global archive, or merged all (default)."""
    return fetch_merged_history(
        _user_id(user),
        scope=scope,
        settings=get_app_settings(),
        competition_key=competition,
        limit=limit,
        offset=offset,
        result_filter=result_filter,
        sort=sort,
    )


@router.get("/{entry_id}")
def get_prediction_archive_entry(
    entry_id: str,
    user: WebAuthUser = Depends(get_current_user),
):
    """Return full archive detail for user history or global archive entry."""
    settings = get_app_settings()

    if is_global_entry_id(entry_id):
        fixture_id = parse_global_fixture_id(entry_id)
        if fixture_id is None:
            raise HTTPException(status_code=404, detail="Invalid global archive entry id")
        detail = build_global_archive_detail(fixture_id, settings=settings)
        if detail is None:
            raise HTTPException(status_code=404, detail="Global archive entry not found")
        return detail

    entry_uuid = parse_uuid(entry_id, field="entry id")
    detail = fetch_archive_detail_for_user(_user_id(user), entry_uuid, settings=settings)
    if detail is None:
        raise HTTPException(status_code=404, detail="Prediction history entry not found")
    return detail
