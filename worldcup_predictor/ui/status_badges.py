"""Phase 48 — Visual status badges for confidence, risk, and decision quality."""

from __future__ import annotations

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t

_BADGE_COLORS: dict[str, str] = {
    "Low": "#94a3b8",
    "Medium": "#f59e0b",
    "High": "#22c55e",
    "Very High": "#059669",
    "Moderate": "#f59e0b",
    "Weak": "#94a3b8",
    "Strong": "#22c55e",
    "Very Strong": "#059669",
}


def confidence_band(score: float | None) -> str:
    if score is None:
        return "Low"
    if score >= 80:
        return "Very High"
    if score >= 65:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def risk_display(risk_level: str | None) -> str:
    raw = (risk_level or "moderate").strip().lower()
    if raw in {"low", "minimal"}:
        return "Low"
    if raw in {"high", "very_high", "very high"}:
        return "High"
    return "Moderate"


def decision_quality_display(
    band: str | None = None,
    *,
    score: float | None = None,
) -> str:
    if band:
        normalized = band.strip()
        mapping = {
            "weak": "Weak",
            "moderate": "Moderate",
            "strong": "Strong",
            "very strong": "Very Strong",
            "very_strong": "Very Strong",
        }
        if normalized.lower() in mapping:
            return mapping[normalized.lower()]
        if normalized in _BADGE_COLORS:
            return normalized
    if score is not None:
        if score >= 80:
            return "Very Strong"
        if score >= 65:
            return "Strong"
        if score >= 45:
            return "Moderate"
        return "Weak"
    return "Moderate"


def render_status_badge(label: str, *, kind: str, locale: Locale) -> None:
    """Render a colored pill badge — never raises."""
    try:
        color = _BADGE_COLORS.get(label, "#64748b")
        prefix = {
            "confidence": gui_t("badge.confidence", locale),
            "risk": gui_t("badge.risk", locale),
            "quality": gui_t("badge.decision_quality", locale),
        }.get(kind, kind)
        st.markdown(
            f'<span class="status-pill phase48-badge" '
            f'style="background:{color}22;color:{color};border:1px solid {color}55;">'
            f"{prefix}: {label}</span>",
            unsafe_allow_html=True,
        )
    except Exception:
        st.caption(f"{kind}: {label}")
