"""Verification cards for Performance Center."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.verification.models import MatchVerificationSummary, VerificationMarketRecord


def obj_get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _ensure_market_record(record: Any) -> VerificationMarketRecord:
    if isinstance(record, VerificationMarketRecord):
        return record
    if isinstance(record, dict):
        return VerificationMarketRecord.from_dict(record)
    raise TypeError(f"Expected VerificationMarketRecord or dict, got {type(record)!r}")


def _market_icon(record: VerificationMarketRecord) -> str:
    result = obj_get(record, "result")
    if result == "correct":
        return "✅"
    if result == "wrong":
        return "❌"
    return "⚪"


def _market_color(record: VerificationMarketRecord) -> str:
    color = obj_get(record, "color")
    if color == "green":
        return "#22c55e"
    if color == "red":
        return "#ef4444"
    return "#94a3b8"


def _market_label(market: str) -> str:
    return {
        "1x2": "1X2",
        "over_under_2_5": "O/U 2.5",
        "halftime_bucket": "Halftime",
        "scoreline_exact": "Scoreline",
        "first_goal_team": "First goal team",
        "first_goal_scorer": "First goal scorer",
    }.get(market, market.replace("_", " ").title())


def render_verification_match_card(
    summary: dict[str, Any] | MatchVerificationSummary,
    locale: Locale,
) -> None:
    markets_raw = obj_get(summary, "markets") or []
    if not markets_raw:
        return

    markets = [_ensure_market_record(m) for m in markets_raw]
    match_name = obj_get(summary, "match_name") or markets[0].match_name
    final_score = obj_get(summary, "final_score") or markets[0].final_score or "—"

    with st.container(border=True):
        st.markdown(f"**Match:** {match_name}")
        st.caption(f"**Score:** {final_score}")
        for record in markets:
            icon = _market_icon(record)
            color = _market_color(record)
            label = _market_label(obj_get(record, "market", ""))
            predicted = obj_get(record, "predicted", "—")
            actual = obj_get(record, "actual", "—")
            st.markdown(
                f"<span style='color:{color};'>{icon} **{label}:** "
                f"predicted {predicted} / actual {actual}</span>",
                unsafe_allow_html=True,
            )


def render_verification_market_row(record: VerificationMarketRecord | dict[str, Any], locale: Locale) -> None:
    row = _ensure_market_record(record)
    icon = _market_icon(row)
    color = _market_color(row)
    label = _market_label(obj_get(row, "market", ""))
    predicted = obj_get(row, "predicted", "—")
    actual = obj_get(row, "actual", "—")
    st.markdown(
        f"<span style='color:{color};'>{icon} {label}: predicted `{predicted}` · "
        f"actual `{actual}`</span>",
        unsafe_allow_html=True,
    )
