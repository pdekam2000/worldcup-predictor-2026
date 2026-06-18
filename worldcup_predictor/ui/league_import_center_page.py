"""Phase 39E — Import Center with quota protection metrics."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from worldcup_predictor.competition.competition_service import CompetitionService
from worldcup_predictor.config.settings import Locale, Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.ingestion.league_history_importer import LeagueHistoryImporter
from worldcup_predictor.quota.quota_tracker import get_quota_tracker
from worldcup_predictor.quota.sync_modes import normalize_sync_mode
from worldcup_predictor.ui.gui_i18n import gui_t


def render_league_import_center(
    locale: Locale,
    settings: Settings | None = None,
    *,
    repository: FootballIntelligenceRepository | None = None,
) -> None:
    active_settings = settings or get_settings()
    repo = repository or FootballIntelligenceRepository()
    leagues = CompetitionService().list_european_leagues()

    st.markdown(
        f'<div class="page-header"><h1>{gui_t("nav.import_center", locale)}</h1>'
        f'<p>{gui_t("import_center.subtitle", locale)}</p></div>',
        unsafe_allow_html=True,
    )

    _render_quota_panel(locale, repo)

    if not active_settings.api_football_key:
        st.warning(gui_t("import_center.api_required", locale))
        return

    sync_mode = normalize_sync_mode(active_settings.api_sync_mode)
    st.caption(f"{gui_t('import_center.sync_mode', locale)}: **{sync_mode.upper()}**")

    league_keys = [c.key for c in leagues]
    labels = {c.key: c.display_name for c in leagues}
    comp_key = st.selectbox(
        gui_t("competition.league", locale),
        league_keys,
        format_func=lambda k: labels[k],
    )
    comp = CompetitionService().get_competition(comp_key)
    seasons = list(comp.default_seasons) or [comp.season]
    season = st.selectbox(gui_t("competition.season", locale), seasons, index=len(seasons) - 1)

    existing = repo.count_fixtures_for_league_season(competition_key=comp_key, season=season)
    st.metric(gui_t("import_center.stored_fixtures", locale), existing)

    sync_state = repo.get_league_sync_state(competition_key=comp_key, season=season)
    if sync_state:
        st.caption(
            f"{gui_t('import_center.last_sync', locale)}: {sync_state.get('last_sync_at') or '—'} · "
            f"{gui_t('import_center.last_fixture', locale)}: {sync_state.get('last_imported_fixture_id') or '—'}"
        )

    if st.button(gui_t("import_center.run", locale), type="primary"):
        with st.spinner(gui_t("import_center.running", locale)):
            importer = LeagueHistoryImporter(active_settings, repository=repo)
            result = importer.import_league_season(league_id=comp.league_id, season=season)
        st.session_state["last_import_result"] = result.to_dict()
        st.rerun()

    last = st.session_state.get("last_import_result")
    if last:
        st.success(last.get("message", gui_t("import_center.done", locale)))
        st.json(last)

    runs = repo.list_league_import_runs(competition_key=comp_key, limit=10)
    if runs:
        st.subheader(gui_t("import_center.history", locale))
        st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)


def _render_quota_panel(locale: Locale, repo: FootballIntelligenceRepository) -> None:
    snap = get_quota_tracker().snapshot()
    db_stats = repo.get_api_quota_stats()
    cols = st.columns(4)
    with cols[0]:
        st.metric(gui_t("import_center.calls_saved", locale), snap.calls_saved)
    with cols[1]:
        rate = snap.cache_hit_rate
        st.metric(
            gui_t("import_center.cache_hit_rate", locale),
            f"{rate * 100:.1f}%" if rate is not None else "—",
        )
    with cols[2]:
        eff = snap.quota_efficiency
        st.metric(
            gui_t("import_center.quota_efficiency", locale),
            f"{eff * 100:.1f}%" if eff is not None else "—",
        )
    with cols[3]:
        last = (db_stats or {}).get("last_sync_at") or snap.last_sync_at
        st.metric(gui_t("import_center.last_sync", locale), last or "—")
