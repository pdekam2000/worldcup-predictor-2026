"""Pydantic schemas for GPT Actions REST bridge."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from worldcup_predictor.gpt_actions.policies import (
    validate_iso_date,
    validate_odds_threshold,
    validate_select_best,
    validate_timezone,
)


class OddsFilter(BaseModel):
    home_odds_gt: float | None = None
    away_odds_gt: float | None = None

    @field_validator("home_odds_gt", "away_odds_gt")
    @classmethod
    def _odds_bounds(cls, value: float | None, info) -> float | None:
        return validate_odds_threshold(value, field=info.field_name)


class DiscoverMatchesQuery(BaseModel):
    date: str
    timezone: str = "Europe/Vienna"

    @field_validator("date")
    @classmethod
    def _date(cls, value: str) -> str:
        validate_iso_date(value)
        return value

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return validate_timezone(value)


class FilterMatchesRequest(BaseModel):
    date: str
    timezone: str = "Europe/Vienna"
    filter: OddsFilter = Field(default_factory=OddsFilter)

    @field_validator("date")
    @classmethod
    def _date(cls, value: str) -> str:
        validate_iso_date(value)
        return value

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return validate_timezone(value)


class StartPredictionJobRequest(BaseModel):
    date: str
    timezone: str = "Europe/Vienna"
    filter: OddsFilter = Field(default_factory=OddsFilter)
    fixture_ids: list[int] = Field(default_factory=list, max_length=20)
    select_best: int = 3
    include_all_predictions: bool = True
    exact_score_top_n: int = Field(default=5, ge=1, le=5)
    refresh_if_stale: bool = True

    @field_validator("date")
    @classmethod
    def _date(cls, value: str) -> str:
        validate_iso_date(value)
        return value

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return validate_timezone(value)

    @field_validator("select_best")
    @classmethod
    def _select_best(cls, value: int) -> int:
        return validate_select_best(value)


class JobCreateResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running"]
    created_at: str
    poll_after_seconds: int


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "partial", "failed"]
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None
