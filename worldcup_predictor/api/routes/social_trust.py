"""Social sharing & public trust APIs — Phase A20."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from worldcup_predictor.api.deps import get_current_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.social_trust.constants import DISCLAIMER, OG_IMAGE_DEFAULT
from worldcup_predictor.social_trust.service import (
    create_combo_share,
    create_paper_report_share,
    create_pick_share,
    create_plan_share,
    get_public_accuracy,
    get_share,
)

router = APIRouter(tags=["social-trust"])


class PickShareBody(BaseModel):
    fixture_id: int | None = None
    home_team: str | None = None
    away_team: str | None = None
    league: str | None = None
    competition_key: str | None = None
    kickoff_utc: str | None = None
    market: str = Field(..., min_length=1)
    market_label: str | None = None
    prediction: str = Field(..., min_length=1)
    bet_quality_score: float | None = Field(default=None, ge=0, le=100)
    bet_quality_tier: str | None = None
    confidence: float | None = None
    odds_decimal: float | None = None
    reason: str | None = None


class ComboShareBody(BaseModel):
    combo_type: str | None = None
    label: str | None = None
    combined_odds: float | None = None
    legs: list[dict[str, Any]] = Field(default_factory=list)


class PlanShareBody(BaseModel):
    date: str | None = None
    day_quality: dict[str, Any] | None = None
    best_singles: list[dict[str, Any]] = Field(default_factory=list)
    combos: list[dict[str, Any]] | None = None


class PaperReportShareBody(BaseModel):
    opt_in: bool = False
    month: str | None = None
    starting_bankroll: float | None = None
    ending_bankroll: float | None = None
    net_profit_loss: float | None = None
    roi_pct: float | None = None
    winrate: float | None = None
    total_bets: int | None = None
    best_market: str | None = None
    worst_market: str | None = None
    best_combo_type: str | None = None
    currency: str | None = None
    headline: str | None = None
    recommendation_next_month: str | None = None


@router.post("/share/pick")
def api_share_pick_create(
    body: PickShareBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return create_pick_share(user.id, body.model_dump())


@router.post("/share/combo")
def api_share_combo_create(
    body: ComboShareBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return create_combo_share(user.id, body.model_dump())


@router.post("/share/betting-plan")
def api_share_plan_create(
    body: PlanShareBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return create_plan_share(user.id, body.model_dump())


@router.post("/share/paper-report")
def api_share_paper_create(
    body: PaperReportShareBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    data = body.model_dump()
    opt_in = bool(data.pop("opt_in", False))
    result = create_paper_report_share(user.id, data, opt_in=opt_in)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/share/pick/{share_id}")
def api_share_pick_get(share_id: str) -> dict[str, Any]:
    result = get_share(share_id, expected_type="pick")
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/share/combo/{share_id}")
def api_share_combo_get(share_id: str) -> dict[str, Any]:
    result = get_share(share_id, expected_type="combo")
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/share/plan/{share_id}")
def api_share_plan_get(share_id: str) -> dict[str, Any]:
    result = get_share(share_id, expected_type="betting_plan")
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/share/paper-report/{share_id}")
def api_share_paper_get(share_id: str) -> dict[str, Any]:
    result = get_share(share_id, expected_type="paper_report")
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/public/accuracy")
def api_public_accuracy() -> dict[str, Any]:
    return get_public_accuracy()


@router.get("/share/og/{share_id}", response_class=HTMLResponse)
def api_share_og_html(share_id: str) -> str:
    """Minimal HTML with OG tags for crawlers."""
    result = get_share(share_id)
    if result.get("status") == "error":
        return f"<html><head><title>Share not found</title></head><body><p>Not found</p></body></html>"
    og = result.get("og") or {}
    title = og.get("title") or "WorldCup Predictor"
    desc = og.get("description") or DISCLAIMER
    image = og.get("image") or OG_IMAGE_DEFAULT
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<meta property="og:title" content="{_esc(title)}"/>
<meta property="og:description" content="{_esc(desc)}"/>
<meta property="og:image" content="{_esc(image)}"/>
<meta property="og:type" content="article"/>
<title>{_esc(title)}</title>
</head><body><p>{_esc(desc)}</p></body></html>"""


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
