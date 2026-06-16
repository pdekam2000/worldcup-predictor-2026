"""Extended prediction markets UI — FT 1X2, O/U, BTTS, HT, FG minute, scorers, correct score."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.prediction.extended_markets import (
    ExtendedMarketsSnapshot,
    build_extended_markets,
    is_reliable_player_name,
    load_extended_markets_from_prediction,
)
from worldcup_predictor.ui.first_goal_display import resolve_first_goal_v2
from worldcup_predictor.ui.gui_i18n import gui_t


def _resolve_markets(
    prediction: MatchPrediction,
    report: Any | None,
    *,
    specialist_report: Any | None = None,
) -> ExtendedMarketsSnapshot:
    cached = load_extended_markets_from_prediction(prediction)
    if cached is not None:
        return cached
    fg_v2 = resolve_first_goal_v2(prediction, report, specialist_report=specialist_report)
    return build_extended_markets(prediction, report, fg_v2=fg_v2)


def _pct_bar(label: str, value: float) -> None:
    st.caption(f"**{label}** — {value:.1f}%")
    st.progress(min(max(value / 100.0, 0.0), 1.0))


def _three_way_block(title: str, probs: dict[str, float], locale: Locale) -> None:
    st.markdown(f"**{title}**")
    c1, c2, c3 = st.columns(3)
    with c1:
        _pct_bar(gui_t("markets.home_win", locale), probs["home"])
    with c2:
        _pct_bar(gui_t("markets.draw", locale), probs["draw"])
    with c3:
        _pct_bar(gui_t("markets.away_win", locale), probs["away"])


def _two_way_block(title: str, label_a: str, label_b: str, pct_a: float, pct_b: float) -> None:
    st.markdown(f"**{title}**")
    c1, c2 = st.columns(2)
    with c1:
        _pct_bar(label_a, pct_a)
    with c2:
        _pct_bar(label_b, pct_b)


def _scorer_line(label: str, name: str | None, team: str | None, locale: Locale) -> None:
    if is_reliable_player_name(name):
        team_bit = f" ({team})" if team else ""
        st.markdown(f"**{label}:** {name}{team_bit}")
    else:
        st.caption(f"**{label}:** {gui_t('markets.not_enough_player_data', locale)}")


def render_extended_prediction_markets(
    prediction: MatchPrediction,
    report: Any | None,
    locale: Locale,
    *,
    specialist_report: Any | None = None,
) -> None:
    """Render all extended prediction sections — never raises."""
    try:
        markets = _resolve_markets(prediction, report, specialist_report=specialist_report)
    except Exception:
        st.info(gui_t("markets.unavailable", locale))
        return

    ft = markets.full_time_1x2.as_percent()
    _three_way_block(gui_t("markets.ft_1x2", locale), ft, locale)

    ou_a, ou_b = markets.over_under_2_5.as_percent()
    _two_way_block(
        gui_t("markets.ou_2_5", locale),
        gui_t("markets.over_2_5", locale),
        gui_t("markets.under_2_5", locale),
        ou_a,
        ou_b,
    )

    btts_a, btts_b = markets.btts.as_percent()
    _two_way_block(
        gui_t("markets.btts", locale),
        gui_t("markets.yes", locale),
        gui_t("markets.no", locale),
        btts_a,
        btts_b,
    )

    ht = markets.halftime_1x2.as_percent()
    _three_way_block(gui_t("markets.ht_result", locale), ht, locale)

    st.markdown(f"**{gui_t('markets.first_goal_time', locale)}**")
    fg = markets.first_goal_time
    minute_text = (
        gui_t("markets.minute_label", locale).format(minute=fg.expected_minute)
        if fg.expected_minute
        else "—"
    )
    band_text = fg.minute_band if fg.minute_band and fg.minute_band != "—" else "—"
    c_fg1, c_fg2 = st.columns(2)
    with c_fg1:
        st.metric(gui_t("markets.expected_minute", locale), minute_text)
    with c_fg2:
        st.metric(gui_t("markets.time_bucket", locale), band_text)

    st.markdown(f"**{gui_t('markets.likely_scorer', locale)}**")
    has_any_scorer = any(
        is_reliable_player_name(p)
        for p in (
            markets.top_scorer.player,
            markets.home_scorer.player,
            markets.away_scorer.player,
        )
    )
    if has_any_scorer:
        _scorer_line(gui_t("markets.top_scorer", locale), markets.top_scorer.player, markets.top_scorer.team, locale)
        home_name = prediction.match_name.split(" vs ", 1)[0] if " vs " in prediction.match_name else "Home"
        away_name = prediction.match_name.split(" vs ", 1)[1] if " vs " in prediction.match_name else "Away"
        _scorer_line(home_name, markets.home_scorer.player, markets.home_scorer.team, locale)
        _scorer_line(away_name, markets.away_scorer.player, markets.away_scorer.team, locale)
    else:
        st.info(gui_t("markets.not_enough_player_data", locale))

    st.markdown(f"**{gui_t('markets.correct_score', locale)}**")
    if markets.correct_scores:
        score_cols = st.columns(min(3, len(markets.correct_scores)))
        for col, row in zip(score_cols, markets.correct_scores):
            with col:
                st.metric(str(row.get("label", "—")), f"{row.get('probability', 0):.1f}%")
    else:
        st.caption(gui_t("markets.correct_score_unavailable", locale))

    st.divider()
    c_conf, c_dq = st.columns(2)
    with c_conf:
        st.metric(gui_t("markets.confidence", locale), f"{markets.confidence_score:.0f}/100")
    with c_dq:
        dq = markets.data_quality_score
        st.metric(
            gui_t("markets.data_quality", locale),
            f"{dq:.0f}/100" if dq else "—",
        )
