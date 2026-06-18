"""Phase 39E — League Learning Center."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from worldcup_predictor.config.league_registry import LEARNING_PROFILE_KEYS
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.odds.league_learning import LeagueLearningEngine
from worldcup_predictor.ui.gui_i18n import gui_t


def render_league_learning_center(locale: Locale, *, repository: FootballIntelligenceRepository | None = None) -> None:
    repo = repository or FootballIntelligenceRepository()
    engine = LeagueLearningEngine(repo)

    st.markdown(
        f'<div class="page-header"><h1>{gui_t("nav.league_learning", locale)}</h1>'
        f'<p>{gui_t("league_learning.subtitle", locale)}</p></div>',
        unsafe_allow_html=True,
    )

    if st.button(gui_t("league_learning.refresh", locale), type="primary"):
        st.session_state.pop("phase39_league_profiles", None)
        st.rerun()

    profiles = st.session_state.get("phase39_league_profiles")
    if profiles is None:
        profiles = engine.build_all_profiles()
        st.session_state["phase39_league_profiles"] = profiles

    rows: list[dict[str, str | int | float]] = []
    for profile in profiles:
        winrates = profile.market_winrates or {}
        rows.append(
            {
                "Profile": profile.learning_profile_key,
                "Competition": profile.competition_name,
                "Sample (matches)": profile.evaluated_matches,
                "Market rows": profile.total_market_rows,
                "Strongest": profile.strongest_market or "—",
                "Weakest": profile.weakest_market or "—",
                "1X2": _pct(winrates.get("1X2")),
                "O/U 2.5": _pct(winrates.get("Over/Under 2.5")),
                "BTTS": _pct(winrates.get("BTTS")),
                "HT Result": _pct(winrates.get("Half Time Result")),
                "Last updated": profile.last_updated_at or "—",
            }
        )

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(gui_t("league_learning.no_data", locale))

    st.markdown(f"**{gui_t('league_learning.profiles_tracked', locale)}:** {', '.join(LEARNING_PROFILE_KEYS)}")

    for profile in profiles:
        if profile.sample_size_warning:
            st.warning(f"{profile.competition_name}: {profile.sample_size_warning}")
        if profile.recommended_rules:
            with st.expander(f"{profile.competition_name} — rules"):
                for rule in profile.recommended_rules:
                    st.markdown(f"- {rule}")


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"
