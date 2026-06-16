"""First Goal Intelligence V2 — GUI display."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.intelligence.first_goal_intelligence_v2 import (
    FirstGoalIntelligenceV2Result,
    build_first_goal_intelligence_v2,
    load_first_goal_v2_from_prediction,
)
from worldcup_predictor.ui.gui_i18n import gui_t


def resolve_first_goal_v2(
    prediction: MatchPrediction,
    report: Any | None,
    *,
    specialist_report: Any | None = None,
) -> FirstGoalIntelligenceV2Result | None:
    loaded = load_first_goal_v2_from_prediction(prediction)
    if loaded:
        return loaded
    if report is None:
        return None
    try:
        return build_first_goal_intelligence_v2(
            report,
            prediction=prediction,
            specialist_report=specialist_report,
        )
    except Exception:
        return None


def render_first_goal_sections(
    prediction: MatchPrediction,
    report: Any | None,
    locale: Locale,
    *,
    specialist_report: Any | None = None,
    key_suffix: str = "",
) -> None:
    """Always show First Goal + Likely Scorers — never silently hide."""
    fg_v2: FirstGoalIntelligenceV2Result | None = None
    try:
        fg_v2 = resolve_first_goal_v2(prediction, report, specialist_report=specialist_report)
    except Exception:
        fg_v2 = None
    try:
        render_first_goal_prediction_card(prediction, fg_v2, locale)
    except Exception:
        st.markdown(f"### {gui_t('first_goal.card_title', locale)}")
        with st.container(border=True):
            st.info(gui_t("first_goal.fallback_unavailable", locale))
    try:
        render_likely_goal_scorers_card(prediction, fg_v2, locale)
    except Exception:
        st.markdown(f"### {gui_t('first_goal.scorers_title', locale)}")
        with st.container(border=True):
            st.info(gui_t("first_goal.no_reliable_scorers", locale))
    try:
        render_first_goal_intelligence_expander(
            fg_v2, locale, key_suffix=key_suffix or str(prediction.fixture_id)
        )
    except Exception:
        pass


def render_first_goal_prediction_card(
    prediction: MatchPrediction,
    fg_v2: FirstGoalIntelligenceV2Result | None,
    locale: Locale,
) -> None:
    """Visible First Goal Prediction card on Match Prediction page."""
    st.markdown(f"### {gui_t('first_goal.card_title', locale)}")
    with st.container(border=True):
        team_label = fg_v2.first_goal_team_display if fg_v2 else prediction.first_goal.team
        band = fg_v2.first_goal_minute_band if fg_v2 else (prediction.first_goal.minute_range or "—")
        prob = fg_v2.confidence if fg_v2 else None
        st.markdown(f"**{gui_t('pro_card.first_goal_team', locale)}:** {team_label}")
        st.markdown(f"**{gui_t('pro_card.first_goal_band', locale)}:** {band}")
        st.caption(gui_t("first_goal.band_disclaimer", locale))
        if prob is not None:
            st.progress(min(max(prob / 100.0, 0.0), 1.0))
            st.caption(f"{gui_t('badge.confidence', locale)}: {prob:.0f}/100")
        if fg_v2 and fg_v2.reasoning:
            for line in fg_v2.reasoning[:3]:
                st.caption(f"• {line}")
        if fg_v2 and not fg_v2.data_available:
            st.info(gui_t("first_goal.limited_data", locale))


def render_likely_goal_scorers_card(
    prediction: MatchPrediction,
    fg_v2: FirstGoalIntelligenceV2Result | None,
    locale: Locale,
) -> None:
    """Top 3–5 likely goal scorers — never invents names."""
    scorers = []
    if fg_v2 and fg_v2.likely_first_goal_scorers:
        scorers = fg_v2.likely_first_goal_scorers[:5]
    elif prediction.first_goal.scorer_candidates:
        scorers = prediction.first_goal.scorer_candidates[:5]

    st.markdown(f"### {gui_t('first_goal.scorers_title', locale)}")
    with st.container(border=True):
        if not scorers:
            msg = (
                prediction.first_goal.player_data_message
                or gui_t("first_goal.no_reliable_scorers", locale)
            )
            st.info(msg)
            return
        for idx, cand in enumerate(scorers, start=1):
            if hasattr(cand, "player"):
                name = cand.player or "—"
                team = getattr(cand, "team", "") or ""
                pos = getattr(cand, "position", "") or ""
                conf = getattr(cand, "confidence", None) or getattr(cand, "score", None)
                reason = getattr(cand, "reason", "") or ""
            else:
                name = cand.get("player_name") or cand.get("player", "—")
                team = cand.get("team", "")
                pos = cand.get("position", "")
                conf = cand.get("confidence") or cand.get("score")
                reason = cand.get("reason", "")
            if pos.upper() in {"G", "GK", "GOALKEEPER"}:
                continue
            conf_txt = f"{conf:.0f}/100" if isinstance(conf, (int, float)) else "—"
            st.markdown(
                f"**{idx}. {name}** ({team}{f' · {pos}' if pos else ''}) — "
                f"{gui_t('badge.confidence', locale)} {conf_txt}"
            )
            if reason:
                st.caption(reason)


def render_first_goal_pro_card_section(
    prediction: MatchPrediction,
    fg_v2: FirstGoalIntelligenceV2Result | None,
    locale: Locale,
) -> None:
    """Compact first-goal row on professional prediction card."""
    team_label = fg_v2.first_goal_team_display if fg_v2 else prediction.first_goal.team
    band = (
        fg_v2.first_goal_minute_band
        if fg_v2
        else (prediction.first_goal.minute_range or "—")
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(gui_t("pro_card.first_goal_team", locale), team_label)
    with c2:
        st.metric(gui_t("pro_card.first_goal_band", locale), band)
    with c3:
        scorers = fg_v2.likely_first_goal_scorers if fg_v2 else prediction.first_goal.scorer_candidates
        if scorers:
            top = scorers[0]
            name = top.player if hasattr(top, "player") else top.get("player_name") or top.get("player", "—")
            st.metric(gui_t("pro_card.top_scorer", locale), name)
        elif prediction.first_goal.player and not str(prediction.first_goal.player).startswith("TBD"):
            st.metric(gui_t("pro_card.top_scorer", locale), prediction.first_goal.player)
        else:
            st.metric(gui_t("pro_card.top_scorer", locale), "—")
            st.caption(gui_t("first_goal.player_unavailable", locale))
    with c4:
        fg_conf = fg_v2.confidence if fg_v2 else None
        st.metric(
            gui_t("pro_card.first_goal_confidence", locale),
            f"{fg_conf:.0f}/100" if fg_conf is not None else "—",
        )


def render_first_goal_intelligence_expander(
    fg_v2: FirstGoalIntelligenceV2Result | None,
    locale: Locale,
    *,
    key_suffix: str = "",
) -> None:
    if fg_v2 is None:
        with st.expander(
            gui_t("first_goal.expander_title", locale),
            expanded=False,
            key=f"fg_intel_exp_{key_suffix or 'default'}",
        ):
            st.info(gui_t("first_goal.fallback_unavailable", locale))
        return
    with st.expander(
        gui_t("first_goal.expander_title", locale),
        expanded=False,
        key=f"fg_intel_exp_{key_suffix or 'default'}",
    ):
        st.caption(fg_v2.summary)
        st.progress(min(max(fg_v2.confidence / 100.0, 0.0), 1.0))
        st.caption(f"{gui_t('badge.confidence', locale)}: {fg_v2.confidence:.0f}/100")

        if fg_v2.reasoning:
            st.markdown(f"**{gui_t('first_goal.reasoning', locale)}**")
            for line in fg_v2.reasoning:
                st.markdown(f"- {line}")

        if fg_v2.likely_first_goal_scorers:
            st.markdown(f"**{gui_t('first_goal.scorer_candidates', locale)}**")
            for cand in fg_v2.likely_first_goal_scorers:
                pos = f" · {cand.position}" if cand.position else ""
                st.markdown(
                    f"- **{cand.player}** ({cand.team}{pos}) — "
                    f"{cand.confidence:.0f}/100 — {cand.reason}"
                )

        if not fg_v2.data_available:
            st.info(gui_t("first_goal.limited_data", locale))

        if fg_v2.risk_flags:
            st.markdown(f"**{gui_t('first_goal.risk_flags', locale)}**")
            for flag in fg_v2.risk_flags:
                st.warning(flag)

        st.markdown(f"**{gui_t('first_goal.data_availability', locale)}**")
        for key, ok in sorted(fg_v2.data_availability.items()):
            st.caption(f"{'✓' if ok else '✗'} {key.replace('_', ' ')}")

        if fg_v2.player_data_unavailable and fg_v2.player_data_message:
            st.info(fg_v2.player_data_message)

        st.caption(fg_v2.disclaimer)
