"""Phase 42C — prediction archive detail routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from worldcup_predictor.api.deps import get_current_user
from worldcup_predictor.api.prediction_archive_detail import fetch_archive_detail_for_user
from worldcup_predictor.api.saas_serializers import parse_uuid
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.config.settings import get_settings as get_app_settings

router = APIRouter(prefix="/history", tags=["history"])


def _user_id(user: WebAuthUser):
    return parse_uuid(user.id, field="user id")


@router.get("/{entry_id}")
def get_prediction_archive_entry(
    entry_id: str,
    user: WebAuthUser = Depends(get_current_user),
):
    """Return full archive detail for one user prediction history entry."""
    entry_uuid = parse_uuid(entry_id, field="entry id")
    detail = fetch_archive_detail_for_user(_user_id(user), entry_uuid, settings=get_app_settings())
    if detail is None:
        raise HTTPException(status_code=404, detail="Prediction history entry not found")
    return detail
