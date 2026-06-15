"""UI display for adaptive confidence and model experience — Phase 35."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.adaptive_confidence.models import (
    AdaptiveConfidenceAdjustment,
    ModelExperienceSummary,
)
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.ui.gui_i18n import gui_t


def render_learning_confidence_section(
    adjustment: AdaptiveConfidenceAdjustment | None,
    locale: Locale,
) -> None:
    if adjustment is None or abs(adjustment.total_bonus) < 0.05:
        return
    sign = "+" if adjustment.total_bonus >= 0 else ""
    color = "#16A34A" if adjustment.total_bonus >= 0 else "#EA580C"
    st.markdown(
        f"""
<div class="learning-confidence-card">
  <div class="learning-confidence-title">{gui_t("adaptive.learning_confidence", locale)}</div>
  <div class="learning-confidence-value" style="color:{color};">{sign}{adjustment.total_bonus:.0f}</div>
  <div class="learning-confidence-reason">{adjustment.reason}</div>
  <div class="learning-confidence-meta">
    {gui_t("adaptive.base_confidence", locale)}: {adjustment.base_confidence:.0f}
    → {adjustment.final_confidence:.0f}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_model_experience_cards(summary: ModelExperienceSummary, locale: Locale) -> None:
    cols = st.columns(3)
    items = [
        ("✅", gui_t("adaptive.verified_matches", locale), str(summary.verified_matches)),
        ("🧠", gui_t("adaptive.patterns_learned", locale), str(summary.patterns_learned)),
        ("📐", gui_t("adaptive.confidence_calibration", locale), summary.confidence_calibration),
    ]
    for col, (icon, label, value) in zip(cols, items):
        with col:
            st.markdown(
                f'<div class="premium-stat-card model-experience-card">'
                f'<div class="premium-stat-icon">{icon}</div>'
                f'<div class="premium-stat-value">{value}</div>'
                f'<div class="premium-stat-label">{label}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )


def render_prediction_adaptive_panel(prediction: MatchPrediction, locale: Locale) -> None:
    adj = getattr(prediction, "adaptive_confidence", None)
    if adj is None:
        base = prediction.metadata.get("base_confidence")
        bonus = prediction.metadata.get("learning_confidence_bonus")
        if base and bonus:
            try:
                adj = AdaptiveConfidenceAdjustment(
                    base_confidence=float(base),
                    final_confidence=float(prediction.confidence_score),
                    total_bonus=float(bonus.replace("+", "")),
                    pattern_bonus=0.0,
                    competition_bonus=0.0,
                    similar_situation_bonus=0.0,
                    bucket_bonus=0.0,
                    reason=gui_t("adaptive.from_metadata", locale),
                    base_prediction_quality=float(
                        prediction.metadata.get("base_prediction_quality", prediction.prediction_quality_score)
                    ),
                    final_prediction_quality=prediction.prediction_quality_score,
                )
            except ValueError:
                adj = None
    render_learning_confidence_section(adj, locale)

    base_pq = None
    if adj:
        base_pq = adj.base_prediction_quality
    elif prediction.metadata.get("base_prediction_quality"):
        try:
            base_pq = float(prediction.metadata["base_prediction_quality"])
        except ValueError:
            base_pq = None

    if base_pq is not None and abs(base_pq - prediction.prediction_quality_score) >= 0.5:
        st.caption(
            f"{gui_t('adaptive.prediction_quality', locale)}: "
            f"**{prediction.prediction_quality_score:.0f}/100** "
            f"({gui_t('adaptive.base', locale)} {base_pq:.0f} → "
            f"{gui_t('adaptive.adaptive', locale)} {prediction.prediction_quality_score:.0f})"
        )


def confidence_for_display(prediction: Any) -> float | None:
    """Final adaptive confidence when available."""
    score = getattr(prediction, "confidence_score", None)
    if score is None:
        return None
    return float(score)
