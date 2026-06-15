"""
WorldCup Predictor Pro 2026 — Phase 14 Beautiful GUI.

Polished Streamlit desktop/web app. Analytical only — not betting advice.
API keys are never displayed.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.accuracy.evaluator import evaluate_all
from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.accuracy.service import AccuracyTrackerService
from worldcup_predictor.automation.prematch_scheduler import PreMatchScheduler
from worldcup_predictor.competition.competition_service import CompetitionService
from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY, list_competition_keys
from worldcup_predictor.config.settings import Locale, get_settings
from worldcup_predictor.i18n.translator import get_translator
from worldcup_predictor.orchestration.audit_pipeline import AuditPipeline
from worldcup_predictor.orchestration.pipeline import UpcomingPipeline
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.orchestration.specialists_pipeline import SpecialistsPipeline
from worldcup_predictor.reasoning.openai_reasoning_service import OpenAIReasoningService
from worldcup_predictor.schedule.competition_schedule import create_schedule_service
from worldcup_predictor.results.match_results_store import save_finished_fixtures
from worldcup_predictor.performance.grades import market_league_table
from worldcup_predictor.verification.auto_verification_agent import AutoVerificationAgent
from worldcup_predictor.learning.model_coach_agent import ModelCoachAgent
from worldcup_predictor.learning.patterns import PatternDiscoveryEngine
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.ingestion.sync_service import DataSyncService
from worldcup_predictor.selection.match_selection_engine import MatchSelectionEngine
from worldcup_predictor.ml.ml_predictor import MLPredictor
from worldcup_predictor.ui.verification_display import render_verification_match_card
from worldcup_predictor.schedule.match_center import (
    build_match_center,
    resolve_default_fixture_id,
    winner_label,
)
from worldcup_predictor.search.team_match_search import search_team_matches
from worldcup_predictor.schedule.opening_match import (
    OPENING_CACHE_TTL_SECONDS,
    OpeningMatchResolution,
    resolve_opening_match,
)
from worldcup_predictor.ui.api_health import overall_api_readiness, test_all_apis
from worldcup_predictor.ui.gui_components import (
    inject_theme,
    render_api_inspector_panel,
    render_api_status_card,
    render_api_status_grid,
    render_data_quality_breakdown,
    render_finished_match_card,
    render_fixture_status_badge,
    render_hero,
    render_live_match_card,
    render_match_card,
    render_prediction_analysis_details,
    render_prediction_card,
    render_professional_report_view,
    render_audit_details,
    render_readiness_badge,
    render_source_badge,
)
from worldcup_predictor.ui.fixture_list_ui import (
    render_back_to_top,
    render_fixture_quick_filters,
    render_grouped_fixture_list,
    render_page_top_anchor,
)
from worldcup_predictor.ui.app_auth import require_auth
from worldcup_predictor.ui.app_shell import (
    DEV_NAV_ITEMS,
    GUI_LOCALE_FLAGS,
    LEGACY_USER_NAV_ITEMS,
    USER_MODE_V2_NAV_ITEMS,
    USER_NAV_ITEMS,
    render_creator_footer,
    render_main_disclaimer,
    render_performance_cards,
    render_model_experience_section,
    render_promo_banner,
    render_quick_action_cards,
    render_sidebar_branding,
    resolve_promo_winrate,
)
from worldcup_predictor.ui.gui_mode_v2 import (
    all_page_keys,
    apply_primary_nav_selection,
    dev_expander_nav_items,
    init_gui_mode_state,
    is_developer_mode,
    navigate_to_page,
    normalize_gui_page,
    primary_nav_for_mode,
    render_mode_toggle,
    save_default_gui_mode,
    sync_primary_nav_widget,
)
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.professional_prediction_card import render_professional_prediction_card
from worldcup_predictor.ui.professional_reports_page import render_professional_reports_page
from worldcup_predictor.access.identity import init_access_session, is_registered_user
from worldcup_predictor.access.admin_auth import block_developer_route, enforce_non_admin_restrictions, init_admin_session, is_admin_session
from worldcup_predictor.access.prediction_gate import acquire_prediction_slot, preview_api_access
from worldcup_predictor.access.public_guard import blocks_prediction_actions
from worldcup_predictor.ui.access_display import (
    render_access_home_panel,
    render_access_sidebar,
    render_admin_config_debug,
    render_gate_block,
    render_quota_banner,
)
from worldcup_predictor.ui.admin_entitlements_page import render_admin_entitlements_page
from worldcup_predictor.ui.feedback_display import render_feedback_form, render_feedback_viewer_page
from worldcup_predictor.ui.upgrade_page import render_upgrade_page
from worldcup_predictor.ui.user_home_dashboard import render_user_home_dashboard
from worldcup_predictor.ui.fixture_display import (
    format_group_stage,
    format_match_subtitle,
    render_fixture_summary_panel,
)
from worldcup_predictor.ui.pattern_discovery_display import render_pattern_discovery_panel
from worldcup_predictor.ui.match_action_panel import render_match_action_panel
from worldcup_predictor.ui.match_selector import render_match_selector
from worldcup_predictor.ui.stored_prediction_summary import (
    has_stored_prediction,
    invalidate_stored_prediction_cache,
    predict_button_label,
    render_stored_prediction_summary,
)

REPORT_PATHS = {
    "backtest": ROOT / "reports" / "backtests" / "backtest_summary.json",
    "calibration": ROOT / "reports" / "calibration" / "calibration_summary.json",
    "import": ROOT / "reports" / "imports" / "import_summary.json",
}

_ALL_PAGE_KEYS = all_page_keys(
    USER_MODE_V2_NAV_ITEMS,
    DEV_NAV_ITEMS,
    legacy_user_nav=LEGACY_USER_NAV_ITEMS,
)

GUI_LOCALES: list[Locale] = ["en", "de", "fa", "sr", "bs", "hr"]
GUI_LOCALE_LABELS: dict[str, str] = {
    "en": "English",
    "de": "Deutsch",
    "fa": "فارسی",
    "sr": "Srpski",
    "bs": "Bosanski",
    "hr": "Hrvatski",
}


def main() -> None:
    st.set_page_config(
        page_title="WorldCup Predictor Pro 2026",
        page_icon="⚽",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    _init_state()
    init_access_session()
    init_admin_session()
    locale = _locale()
    require_auth(locale)
    enforce_non_admin_restrictions()
    _render_sidebar()
    page = st.session_state["gui_page"]
    locale = _locale()
    if block_developer_route(page, locale):
        page_home()
    else:
        {
        "home": page_home,
        "match_center": page_match_center,
        "team_search": page_team_search,
        "favorites": page_favorites,
        "accuracy": page_accuracy_tracker,
        "shortlist": page_daily_shortlist,
        "learning": page_learning_agent,
        "learning_center_v2": page_learning_center_v2,
        "automation": page_automation_center,
        "api": page_api_setup,
        "opening": page_opening_match,
        "upcoming": page_upcoming,
        "predict": page_prediction,
        "specialists": page_specialists,
        "report": page_professional_report,
        "audit": page_audit,
        "backtest": page_backtest_calibration,
        "professional_reports": page_professional_reports,
        "upgrade": page_upgrade,
        "admin_entitlements": page_admin_entitlements,
        "feedback_viewer": page_feedback_viewer,
        "settings": page_settings,
        }[page]()
    st.sidebar.markdown("---")
    st.sidebar.caption(gui_t("disclaimer", _locale()))


def _init_state() -> None:
    settings = get_settings()
    fid, src = resolve_default_fixture_id(settings, DEFAULT_COMPETITION_KEY)
    defaults: dict[str, Any] = {
        "locale": settings.default_locale,
        "gui_page": "home",
        "fixture_id": fid,
        "fixture_source": src,
        "competition": DEFAULT_COMPETITION_KEY,
        "_last_competition": DEFAULT_COMPETITION_KEY,
        "api_test_results": None,
        "opening_fixture": None,
        "opening_resolution": None,
        "opening_refreshed_at": None,
        "finished_pred_cache": {},
        "match_center_snapshot": None,
        "accuracy_snapshot": None,
        "automation_snapshot": None,
        "selected_fixture_id": fid,
        "selected_match_name": None,
        "gui_intelligence_cache": None,
        "match_center_action_cache": {},
        "mc_panel_fixture_id": None,
        "mc_panel_tab": "analyze",
        "favorite_fixtures": set(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    init_gui_mode_state()
    init_access_session()
    init_admin_session()
    enforce_non_admin_restrictions()
    dev_mode = is_developer_mode()
    st.session_state["gui_page"] = normalize_gui_page(
        st.session_state.get("gui_page"),
        developer_mode=dev_mode,
    )
    if st.session_state.get("locale") not in GUI_LOCALES:
        st.session_state["locale"] = "en"


def _sync_fixture_for_competition() -> None:
    comp = _competition_key()
    if st.session_state.get("_last_competition") != comp:
        fid, src = resolve_default_fixture_id(get_settings(), comp)
        st.session_state["fixture_id"] = fid
        st.session_state["selected_fixture_id"] = fid
        st.session_state["selected_match_name"] = None
        st.session_state["fixture_source"] = src
        st.session_state["_last_competition"] = comp
        st.session_state["match_center_snapshot"] = None
        st.session_state["overview_avg_quality"] = None


def _default_fixture_id() -> int:
    return int(st.session_state.get("selected_fixture_id") or st.session_state.get("fixture_id", 2026001))


def _selected_match_name() -> str | None:
    return st.session_state.get("selected_match_name")


def _select_fixture(
    fixture_id: int,
    home: str,
    away: str,
    *,
    source: str | None = None,
    goto_page: str | None = None,
) -> None:
    label = f"{home} vs {away}"
    st.session_state["selected_fixture_id"] = fixture_id
    st.session_state["fixture_id"] = fixture_id
    st.session_state["selected_match_name"] = label
    if source:
        st.session_state["fixture_source"] = source
    st.session_state["gui_intelligence_cache"] = None
    st.session_state["gui_last_prediction"] = None
    if goto_page:
        st.session_state["gui_page"] = goto_page
    st.toast(f"Selected: {label}")
    st.rerun()


def _all_fixtures_for_selector() -> list:
    center = _get_match_center()
    return center.upcoming + center.live + center.finished


def _performance_snapshot() -> Any:
    snapshot = st.session_state.get("accuracy_snapshot")
    if snapshot is not None:
        return snapshot
    snapshot = _accuracy_service().load_summary_from_disk()
    if snapshot is None:
        center = _get_match_center()
        snapshot = _accuracy_service().refresh(center.finished + center.live + center.upcoming)
        st.session_state["accuracy_snapshot"] = snapshot
    return snapshot


def _today_stats(snapshot: Any) -> tuple[int, int, int, int]:
    today = date.today().isoformat()
    today_predictions = sum(1 for record in snapshot.recent_predictions if record.date == today)
    today_evaluated = [
        item
        for item in snapshot.evaluated
        if item.date == today or (item.evaluated_at or "").startswith(today)
    ]
    correct = sum(1 for item in today_evaluated if item.one_x_two_correct)
    wrong = sum(1 for item in today_evaluated if not item.one_x_two_correct)
    return today_predictions, len(today_evaluated), correct, wrong


def _get_intelligence_report(fixture_id: int, locale: Locale | None = None):
    gate = preview_api_access()
    if not gate.allowed:
        if locale is not None:
            render_gate_block(gate, locale)
        return None
    cached = st.session_state.get("gui_intelligence_cache") or {}
    if cached.get("fixture_id") == fixture_id and cached.get("report") is not None:
        return cached["report"]
    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient

    report = MatchIntelligenceBuilder(ApiFootballClient(get_settings())).build_by_fixture_id(fixture_id)
    st.session_state["gui_intelligence_cache"] = {"fixture_id": fixture_id, "report": report}
    return report


def _lookup_fixture(fixture_id: int) -> Any | None:
    for fixture in _all_fixtures_for_selector():
        if fixture.fixture_id == fixture_id:
            return fixture
    return None


def _render_selected_fixture_banner(locale: Locale) -> None:
    fid = _default_fixture_id()
    fixture = _lookup_fixture(fid)
    name = _selected_match_name()
    if not name and fixture is not None:
        name = f"{fixture.home_team} vs {fixture.away_team}"
    if name:
        gs = format_group_stage(fixture) if fixture is not None else "—"
        line = f"{gui_t('selected_match', locale)}: **{name}**"
        if gs != "—":
            line += f" · {gui_t('card.group', locale)}: **{gs}**"
        st.success(line)
    else:
        st.caption("Select a match below or from Match Center / Team Search.")
    render_source_badge(st.session_state.get("fixture_source"), locale)


def _get_match_center():
    cached = st.session_state.get("match_center_snapshot")
    if cached is not None:
        return cached
    snapshot = build_match_center(_schedule_service(), get_settings())
    save_finished_fixtures(snapshot.finished)
    _run_auto_verification(snapshot.finished + snapshot.live + snapshot.upcoming)
    st.session_state["match_center_snapshot"] = snapshot
    return snapshot


def _verification_agent() -> AutoVerificationAgent:
    return AutoVerificationAgent()


def _db_repo() -> FootballIntelligenceRepository:
    return FootballIntelligenceRepository()


def _coach_agent() -> ModelCoachAgent:
    return ModelCoachAgent()


def _pattern_engine() -> PatternDiscoveryEngine:
    return PatternDiscoveryEngine()


def _run_auto_verification(fixtures: list) -> None:
    result = _verification_agent().run(fixtures, all_predictions=True)
    st.session_state["verification_snapshot"] = result


def _locale() -> Locale:
    return st.session_state["locale"]  # type: ignore[return-value]


def _translator():
    return get_translator(_locale())


def _competition_key() -> str:
    return st.session_state.get("competition", DEFAULT_COMPETITION_KEY)


def _schedule_service():
    return create_schedule_service(get_settings(), competition_key=_competition_key())


def _placeholder_data_quality(pred: Any) -> float | None:
    if pred is None:
        return None
    breakdown = getattr(pred, "confidence_breakdown", None)
    if breakdown is not None:
        return breakdown.data_quality_score
    score = getattr(pred, "confidence_score", None)
    if score is not None:
        return score / 100.0
    return None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _render_sidebar() -> None:
    locale = _locale()
    render_sidebar_branding(locale)
    render_access_sidebar(locale)
    render_admin_config_debug()

    def _locale_label(code: str) -> str:
        flag = GUI_LOCALE_FLAGS.get(code, "")
        return f"{flag} {GUI_LOCALE_LABELS[code]}".strip()

    st.session_state["locale"] = st.sidebar.selectbox(
        gui_t("locale", locale),
        options=GUI_LOCALES,
        index=GUI_LOCALES.index(st.session_state["locale"])
        if st.session_state["locale"] in GUI_LOCALES
        else 0,
        format_func=_locale_label,
    )
    locale = _locale()

    comp_service = CompetitionService()
    comps = comp_service.list_competitions()
    comp_keys = [c.key for c in comps]
    comp_labels = {c.key: f"🏆 {c.display_name}" for c in comps}
    current = _competition_key()
    if current not in comp_keys:
        current = DEFAULT_COMPETITION_KEY
    st.session_state["competition"] = st.sidebar.selectbox(
        gui_t("competition", locale),
        comp_keys,
        index=comp_keys.index(current),
        format_func=lambda k: comp_labels[k],
    )
    _sync_fixture_for_competition()

    render_mode_toggle(locale)

    st.sidebar.markdown("---")
    dev_mode = is_developer_mode()
    st.session_state["gui_page"] = normalize_gui_page(
        st.session_state.get("gui_page"),
        developer_mode=dev_mode,
    )
    sync_primary_nav_widget(developer_mode=dev_mode)

    primary_nav = primary_nav_for_mode(developer_mode=dev_mode)
    user_keys = [k for k, _, _ in primary_nav]
    user_labels = {k: f"{icon} {gui_t(i18n, locale)}" for k, i18n, icon in primary_nav}
    current_page = st.session_state["gui_page"]

    st.sidebar.radio(
        gui_t("mode.user", locale) if not dev_mode else "Navigation",
        user_keys,
        format_func=lambda k: user_labels[k],
        label_visibility="collapsed",
        key="sidebar_user_nav",
        on_change=apply_primary_nav_selection,
    )

    if dev_mode and is_admin_session():
        dev_keys = [k for k, _, _ in dev_expander_nav_items()]
        with st.sidebar.expander(
            gui_t("shell.for_developer", locale),
            expanded=current_page in dev_keys,
        ):
            for key, i18n, icon in dev_expander_nav_items():
                is_active = current_page == key
                if st.button(
                    f"{icon} {gui_t(i18n, locale)}",
                    key=f"dev_nav_{key}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    navigate_to_page(key, developer_mode=True)
                    st.rerun()

    st.sidebar.markdown("---")
    render_creator_footer(locale)


def _average_data_quality(locale: Locale) -> float | None:
    cached = st.session_state.get("overview_avg_quality")
    if cached is not None:
        return cached
    result = UpcomingPipeline(
        get_settings(), locale=locale, competition_key=_competition_key()
    ).run(limit=5)
    if not result.success or not result.predictions:
        return None
    scores = [_placeholder_data_quality(p) for p in result.predictions]
    scores = [s for s in scores if s is not None]
    if not scores:
        return None
    avg = sum(scores) / len(scores)
    st.session_state["overview_avg_quality"] = avg
    return avg


def page_home() -> None:
    locale = _locale()
    settings = get_settings()

    with st.spinner("Loading dashboard…"):
        center = _get_match_center()
        api_ready_label, api_progress = overall_api_readiness(test_all_apis(settings))
        api_ready = api_ready_label in {"Ready", "Partial"} and api_progress >= 0.5
        last_prediction = st.session_state.get("gui_last_prediction")

    if is_developer_mode():
        perf = _performance_snapshot()
        metrics = perf.metrics
        render_promo_banner(locale, winrate_line=resolve_promo_winrate(metrics))
        render_main_disclaimer(locale)

        st.subheader(gui_t("shell.today_matches", locale))
        from worldcup_predictor.ui.fixture_list_helpers import is_kickoff_today

        today_fixtures = [f for f in center.upcoming if is_kickoff_today(f)]
        if today_fixtures:
            for fixture in today_fixtures[:4]:
                render_match_card(fixture, locale, source=fixture.source)
        elif center.upcoming:
            for fixture in center.upcoming[:3]:
                render_match_card(fixture, locale, source=fixture.source)
        else:
            st.info(gui_t("no_fixture", locale))

        st.subheader("Quick Actions")
        render_quick_action_cards(locale)

        st.subheader(gui_t("shell.performance_summary", locale))
        render_performance_cards(locale, metrics)

        render_model_experience_section(locale, competition_key=_competition_key())

        o1, o2, o3, o4 = st.columns(4)
        with o1:
            st.metric(gui_t("overview.live", locale), center.live_count)
        with o2:
            st.metric(gui_t("overview.upcoming_today", locale), center.upcoming_today_count)
        with o3:
            st.metric(gui_t("overview.finished_today", locale), center.finished_today_count)
        with o4:
            vstats = _verification_agent().today_stats()
            st.metric(gui_t("home.verified_today", locale), vstats["verified_predictions_today"])
    else:
        render_hero(gui_t("nav.home", locale), gui_t("home.user_subtitle", locale))
        render_access_home_panel(locale)

        def _goto_predict() -> None:
            st.session_state["gui_page"] = "predict"
            st.rerun()

        render_user_home_dashboard(
            locale,
            center=center,
            api_ready=api_ready,
            last_prediction=last_prediction,
            goto_predict=_goto_predict,
        )

    render_back_to_top(locale)


def _accuracy_service() -> AccuracyTrackerService:
    return AccuracyTrackerService(get_settings(), competition_key=_competition_key())


def _prematch_scheduler() -> PreMatchScheduler:
    return PreMatchScheduler(get_settings(), competition_key=_competition_key(), locale=_locale())


def _prediction_badge(fixture_id: int) -> tuple[str, float | None]:
    stored = PredictionHistoryStore().latest_by_fixture().get(fixture_id)
    if stored:
        return gui_t("card.prediction_stored", _locale()), stored.confidence_score
    return gui_t("accuracy.no_prediction", _locale()), None


def _finished_evaluations(fixtures: list) -> dict[int, Any]:
    latest = PredictionHistoryStore().latest_by_fixture()
    evaluated = evaluate_all(latest, fixtures)
    return {item.fixture_id: item for item in evaluated}


def page_favorites() -> None:
    locale = _locale()
    settings = get_settings()
    t = _translator()
    comp = _competition_key()
    render_hero(gui_t("nav.favorites", locale), gui_t("filter.favorites", locale))

    fav_ids = set(st.session_state.get("favorite_fixtures") or set())
    if not fav_ids:
        st.info("No favorite matches yet. Tap ☆ on any match card in Match Center.")
        return

    with st.spinner("Loading favorites…"):
        center = _get_match_center()

    all_fixtures = center.upcoming + center.live + center.finished
    favorites = [f for f in all_fixtures if int(getattr(f, "fixture_id", 0) or 0) in fav_ids]

    if not favorites:
        st.warning("Your favorited fixtures are not in the current match list.")
        return

    for fixture in favorites:
        pred_label, conf = _prediction_badge(fixture.fixture_id)
        render_match_card(fixture, locale, source=getattr(fixture, "source", None), confidence=conf)
        render_match_action_panel(
            fixture,
            locale=locale,
            t=t,
            settings=settings,
            competition_key=comp,
            source=getattr(fixture, "source", None),
            key_prefix=f"fav_{fixture.fixture_id}",
        )
    render_back_to_top(locale)


def page_match_center() -> None:
    locale = _locale()
    render_page_top_anchor()

    header_left, header_right = st.columns([3, 2])
    with header_left:
        render_hero(gui_t("nav.match_center", locale), "Live · Upcoming · Finished")
    with header_right:
        st.markdown('<div class="premium-search">', unsafe_allow_html=True)
        quick_query = st.text_input(
            "Search",
            placeholder=gui_t("shell.search_teams", locale),
            key="match_center_quick_search",
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)
        if st.button(gui_t("shell.refresh", locale), type="primary", use_container_width=True):
            st.session_state["match_center_snapshot"] = None
            st.session_state["finished_pred_cache"] = {}
            st.session_state["accuracy_snapshot"] = None
            center = build_match_center(_schedule_service(), get_settings())
            saved = save_finished_fixtures(center.finished)
            verify = _verification_agent().run(center.finished + center.live + center.upcoming)
            st.session_state["verification_snapshot"] = verify
            st.session_state["match_center_snapshot"] = center
            if saved:
                st.toast(f"Saved {saved} finished result(s).")
            if verify.saved_rows:
                st.toast(f"Verified {verify.saved_rows} market row(s).")
            st.rerun()

    if quick_query.strip():
        st.session_state["team_search_query"] = quick_query.strip()
        st.session_state["gui_page"] = "team_search"
        st.rerun()

    render_promo_banner(
        locale,
        winrate_line=resolve_promo_winrate(_performance_snapshot().metrics),
    )
    settings = get_settings()
    t = _translator()
    comp = _competition_key()

    with st.spinner("Loading matches…"):
        center = _get_match_center()

    render_source_badge(center.source_label, locale)
    filter_key = render_fixture_quick_filters(locale, key_prefix="mc")

    def _render_fixture_row(fixture: Any, *, key_prefix: str, card_fn: Callable[..., None], **card_kw: Any) -> None:
        card_fn(fixture, locale, **card_kw)
        fid = int(getattr(fixture, "fixture_id", None) or getattr(fixture, "id", 0) or 0)
        if fid:
            from worldcup_predictor.ui.odds_display import (
                get_cached_phase36_odds,
                render_market_agreement_badge_from_data,
            )

            cache = st.session_state.get("match_center_action_cache", {}).get(str(fid), {})
            if not get_cached_phase36_odds(fid) and cache:
                from worldcup_predictor.ui.match_action_panel import _cache_phase36_odds_from_cache

                _cache_phase36_odds_from_cache(fid, cache)
            cached_odds = get_cached_phase36_odds(fid)
            if cached_odds:
                render_market_agreement_badge_from_data(cached_odds, locale)
        render_match_action_panel(
            fixture,
            locale=locale,
            t=t,
            settings=settings,
            competition_key=comp,
            source=card_kw.get("source") or getattr(fixture, "source", center.source_label),
            key_prefix=key_prefix,
        )

    tab_up, tab_live, tab_fin = st.tabs(
        [
            f"📅 {gui_t('match_center.upcoming', locale)} ({len(center.upcoming)})",
            f"🔴 {gui_t('match_center.live', locale)} ({len(center.live)})",
            f"✅ {gui_t('match_center.finished', locale)} ({len(center.finished)})",
        ]
    )

    with tab_up:
        if not center.upcoming:
            st.info(gui_t("no_fixture", locale))
        else:

            def _render_upcoming_row(fixture: Any) -> None:
                pred_label, conf = _prediction_badge(fixture.fixture_id)
                _render_fixture_row(
                    fixture,
                    key_prefix=f"mc_up_{fixture.fixture_id}",
                    card_fn=render_match_card,
                    source=fixture.source,
                    prediction_status=pred_label,
                    confidence=conf,
                )

            render_grouped_fixture_list(
                center.upcoming,
                locale,
                _render_upcoming_row,
                filter_key=filter_key,
                empty_message=gui_t("no_fixture", locale),
            )

    with tab_live:
        if not center.live:
            st.info("No live matches right now.")
        for fixture in center.live:
            pred_label, conf = _prediction_badge(fixture.fixture_id)
            _render_fixture_row(
                fixture,
                key_prefix=f"mc_live_{fixture.fixture_id}",
                card_fn=render_live_match_card,
                prediction_status=pred_label,
                confidence=conf,
            )

    with tab_fin:
        if not center.finished:
            st.info("No finished matches loaded.")
        latest = PredictionHistoryStore().latest_by_fixture()
        eval_map = _finished_evaluations(center.finished)
        for fixture in center.finished[:20]:
            evaluation = eval_map.get(fixture.fixture_id)
            stored = latest.get(fixture.fixture_id)
            render_finished_match_card(
                fixture,
                locale,
                winner=winner_label(fixture),
                evaluation=evaluation,
                stored_record=stored if evaluation is None else None,
                confidence=stored.confidence_score if stored else None,
            )
            render_match_action_panel(
                fixture,
                locale=locale,
                t=t,
                settings=settings,
                competition_key=comp,
                source=getattr(fixture, "source", center.source_label),
                key_prefix=f"mc_fin_{fixture.fixture_id}",
            )

    render_back_to_top(locale)


def page_accuracy_tracker() -> None:
    locale = _locale()
    render_hero(gui_t("accuracy.title", locale), gui_t("accuracy.subtitle", locale))
    st.warning(gui_t("accuracy.disclaimer", locale))

    if st.button(gui_t("accuracy.refresh", locale), type="primary"):
        with st.spinner("Evaluating stored predictions…"):
            center = _get_match_center()
            all_fixtures = center.finished + center.live + center.upcoming
            snapshot = _accuracy_service().refresh(all_fixtures)
            st.session_state["accuracy_snapshot"] = snapshot
            verify = _verification_agent().run(all_fixtures, all_predictions=True)
            st.session_state["verification_snapshot"] = verify
        st.rerun()

    if st.button(gui_t("verification.run", locale)):
        with st.spinner("Running auto verification…"):
            center = _get_match_center()
            verify = _verification_agent().run(center.finished + center.live + center.upcoming)
            st.session_state["verification_snapshot"] = verify
        st.rerun()

    if st.button(gui_t("coach.run", locale)):
        with st.spinner("Running learning agent…"):
            coach = _coach_agent().run()
            st.session_state["coach_snapshot"] = coach
        st.rerun()

    snapshot = _performance_snapshot()
    st.session_state["accuracy_snapshot"] = snapshot

    metrics = snapshot.metrics
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.metric(gui_t("performance.total_predictions", locale), metrics.total_predictions)
    with c2:
        st.metric(gui_t("performance.evaluated", locale), metrics.total_evaluated)
    with c3:
        st.metric(gui_t("performance.pending", locale), metrics.pending_predictions)
    with c4:
        st.metric(gui_t("performance.grade", locale), metrics.model_grade)
    with c5:
        st.metric(gui_t("performance.best_market", locale), metrics.best_market or "—")
    with c6:
        st.metric(gui_t("performance.worst_market", locale), metrics.worst_market or "—")

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric(gui_t("accuracy.1x2", locale), _pct(metrics.one_x_two_accuracy))
    with m2:
        st.metric(gui_t("accuracy.ou", locale), _pct(metrics.over_under_2_5_accuracy))
    with m3:
        st.metric(gui_t("accuracy.ht", locale), _pct(metrics.halftime_bucket_accuracy))
    with m4:
        st.metric(gui_t("performance.scoreline", locale), _pct(metrics.scoreline_exact_accuracy))
    with m5:
        st.metric(gui_t("performance.first_goal", locale), _pct(metrics.first_goal_accuracy))

    st.subheader(gui_t("accuracy.market_table", locale))
    league = market_league_table(metrics)
    if league:
        league_rows = [
            {
                "Rank": idx + 1,
                "Market": row["market"],
                "Winrate": _pct(row["accuracy"]),
                "Evaluated": row["evaluated"],
            }
            for idx, row in enumerate(league)
        ]
        st.dataframe(pd.DataFrame(league_rows), use_container_width=True, hide_index=True)
        chart_df = pd.DataFrame(
            [{"Market": row["market"], "Winrate %": round((row["accuracy"] or 0) * 100, 1)} for row in league]
        )
        fig = px.bar(
            chart_df,
            x="Market",
            y="Winrate %",
            color="Market",
            title=f"Model grade: {metrics.model_grade} · Best: {metrics.best_market or 'n/a'}",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No evaluated predictions yet.")

    st.subheader(gui_t("accuracy.no_bet_sep", locale))
    nb1, nb2 = st.columns(2)
    with nb1:
        st.metric("No-bet 1X2", _pct(metrics.no_bet_one_x_two_accuracy))
        st.metric("No-bet O/U 2.5", _pct(metrics.no_bet_over_under_accuracy))
    with nb2:
        st.metric("Non-no-bet 1X2", _pct(metrics.non_no_bet_one_x_two_accuracy))
        st.metric("Non-no-bet O/U 2.5", _pct(metrics.non_no_bet_over_under_accuracy))

    bucket_rows = [
        {
            "Bucket": bucket.label,
            "Count": bucket.count,
            "1X2": _pct(bucket.one_x_two_accuracy),
            "O/U": _pct(bucket.over_under_accuracy),
        }
        for bucket in metrics.confidence_buckets
        if bucket.count > 0
    ]
    if bucket_rows:
        st.subheader("Confidence bucket chart")
        chart_df = pd.DataFrame(bucket_rows)
        fig = px.bar(
            chart_df,
            x="Bucket",
            y="Count",
            color="1X2",
            title=f"Best range: {metrics.best_confidence_range or 'n/a'} · "
            f"Weakest: {metrics.worst_confidence_range or 'n/a'}",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(chart_df, use_container_width=True, hide_index=True)

    st.subheader(gui_t("accuracy.recent", locale))
    if snapshot.recent_predictions:
        recent_rows = [
            {
                "Fixture": f"{record.home_team} vs {record.away_team}",
                "Version": record.prediction_version,
                "Date": record.date,
                "1X2": record.predicted_1x2,
                "O/U": record.predicted_over_under_2_5,
                "Confidence": round(record.confidence_score, 1),
                "Preliminary": record.is_preliminary,
                "No-bet": record.no_bet_flag,
                "Source": record.source,
                "Stored": record.created_at[:19],
            }
            for record in snapshot.recent_predictions
        ]
        st.dataframe(pd.DataFrame(recent_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No predictions stored yet. Run **Match Prediction** before kickoff.")

    st.subheader(gui_t("accuracy.finished_eval", locale))
    if snapshot.evaluated:
        eval_rows = []
        for item in snapshot.evaluated[:25]:
            eval_rows.append(
                {
                    "Match": item.match_name,
                    "Score": item.final_score,
                    "1X2": "✓" if item.one_x_two_correct else "✗",
                    "O/U": "✓" if item.over_under_correct else "✗",
                    "HT": "✓" if item.halftime_bucket_correct else ("—" if not item.halftime_evaluated else "✗"),
                    "Scoreline": "✓" if item.scoreline_exact_correct else ("—" if not item.predicted_scoreline else "✗"),
                    "First goal": "✓" if item.first_goal_correct else ("—" if not item.first_goal_evaluated else "✗"),
                    "Confidence": round(item.confidence_score, 1),
                }
            )
        st.dataframe(pd.DataFrame(eval_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No finished matches with stored predictions evaluated yet.")

    st.subheader(gui_t("performance.by_competition", locale))
    from worldcup_predictor.config.competitions import get_competition

    _perf_filter_keys = [
        "all",
        "world_cup_2026",
        "premier_league",
        "bundesliga",
        "la_liga",
        "champions_league",
    ]

    def _perf_filter_label(key: str) -> str:
        if key == "all":
            return "All"
        comp = get_competition(key)
        return comp.display_name if comp else key.replace("_", " ").title()

    perf_comp_filter = st.selectbox(
        gui_t("performance.competition_filter", locale),
        _perf_filter_keys,
        format_func=_perf_filter_label,
        key="perf_competition_filter",
    )
    comp_perf = _db_repo().performance_by_competition()
    if comp_perf:
        filtered = (
            comp_perf
            if perf_comp_filter == "all"
            else [r for r in comp_perf if r["competition_key"] == perf_comp_filter]
        )
        if filtered:
            comp_rows = [
                {
                    "Competition": get_competition(r["competition_key"]).display_name
                    if get_competition(r["competition_key"])
                    else r["competition_key"],
                    "Market": r["market"],
                    "Winrate": _pct(r["winrate"]),
                    "Samples": r["total"],
                }
                for r in filtered
            ]
            st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
        else:
            st.info(gui_t("performance.no_evaluated_data", locale))
    else:
        st.info(gui_t("performance.no_evaluated_data", locale))

    st.subheader(gui_t("performance.by_version", locale))
    version_perf = _db_repo().performance_by_version(
        competition_key=None if perf_comp_filter == "all" else perf_comp_filter
    )
    if version_perf:
        version_rows = [
            {
                "Version": r["prediction_version"],
                "Market": r["market"],
                "Winrate": _pct(r["winrate"]),
                "Samples": r["total"],
            }
            for r in version_perf
        ]
        st.dataframe(pd.DataFrame(version_rows), use_container_width=True, hide_index=True)

    verify = st.session_state.get("verification_snapshot")
    if verify is None:
        verify = _verification_agent().load_summary_from_disk()
    if verify is None:
        verify = _verification_agent().run(_get_match_center().finished, all_predictions=True)
        st.session_state["verification_snapshot"] = verify

    st.subheader(gui_t("verification.title", locale))
    vm = verify.metrics
    st.caption(
        f"Checked: {vm.total_predictions_checked} · Evaluated matches: {vm.evaluated_matches} · "
        f"Pending: {vm.pending_matches} · Grade: {vm.model_grade}"
    )
    summaries = verify.summaries or _verification_agent().match_summaries()
    if summaries:
        for summary in summaries[:12]:
            render_verification_match_card(summary, locale)
    else:
        st.info("No verification rows yet. Run **Run Auto Verification** after matches finish.")

    coach = st.session_state.get("coach_snapshot")
    if coach is None:
        coach = _coach_agent().load_from_disk()
    if coach is None:
        coach = _coach_agent().run(write_reports=True)
        st.session_state["coach_snapshot"] = coach

    st.subheader(gui_t("coach.title", locale))
    st.caption(gui_t("coach.subtitle", locale))
    st.info(gui_t("coach.disclaimer", locale))

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(gui_t("coach.strongest", locale), coach.strongest_market or "—")
    with c2:
        st.metric(gui_t("coach.weakest", locale), coach.weakest_market or "—")
    with c3:
        st.metric(gui_t("coach.focus", locale), coach.suggested_focus_area or "—")

    if coach.warnings_about_small_sample_size:
        st.markdown(f"**{gui_t('coach.warnings', locale)}**")
        for warning in coach.warnings_about_small_sample_size:
            st.warning(warning)

    if coach.decision_agent_advice:
        st.markdown(f"**{gui_t('coach.advice', locale)}**")
        for advice in coach.decision_agent_advice:
            st.markdown(f"- {advice}")

    if coach.recommended_weight_adjustments:
        with st.expander(gui_t("coach.weights", locale), expanded=False):
            for factor, note in coach.recommended_weight_adjustments.items():
                st.markdown(f"**{factor}** — {note}")

    if coach.recommended_market_rules:
        with st.expander(gui_t("coach.rules", locale), expanded=False):
            for rule in coach.recommended_market_rules:
                st.markdown(f"- {rule}")


def page_automation_center() -> None:
    locale = _locale()
    render_hero(gui_t("automation.title", locale), gui_t("automation.subtitle", locale))
    st.warning(gui_t("automation.disclaimer", locale))

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button(gui_t("automation.scan_24h", locale), use_container_width=True, type="primary"):
            with st.spinner("Scanning next 24 hours…"):
                result = _prematch_scheduler().run_window_scan(window_hours=24)
                st.session_state["automation_snapshot"] = result
            st.rerun()
    with b2:
        if st.button(gui_t("automation.scan_6h", locale), use_container_width=True):
            with st.spinner("Scanning next 6 hours…"):
                result = _prematch_scheduler().run_window_scan(window_hours=6)
                st.session_state["automation_snapshot"] = result
            st.rerun()
    with b3:
        if st.button(gui_t("automation.lineup_final", locale), use_container_width=True):
            with st.spinner("Checking official lineups…"):
                result = _prematch_scheduler().run_lineup_final_scan()
                st.session_state["automation_snapshot"] = result
            st.rerun()
    with b4:
        if st.button(gui_t("automation.refresh_accuracy", locale), use_container_width=True):
            with st.spinner("Refreshing model evaluation…"):
                center = _get_match_center()
                snapshot = _accuracy_service().refresh(center.finished + center.live + center.upcoming)
                st.session_state["accuracy_snapshot"] = snapshot
            st.rerun()

    snapshot = st.session_state.get("automation_snapshot")
    if snapshot is None:
        st.info("Run a scan to populate the automation log.")
        center = _get_match_center()
        wc = _prematch_scheduler().count_upcoming_windows()
        st.caption(
            f"Upcoming windows — 24h: {wc.within_24h} · 6h: {wc.within_6h} · 90m: {wc.within_90m}"
        )
        return

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric(gui_t("automation.scanned", locale), snapshot.matches_scanned)
    with m2:
        st.metric(gui_t("automation.created", locale), snapshot.predictions_created)
    with m3:
        st.metric(gui_t("automation.skipped", locale), snapshot.predictions_skipped)
    with m4:
        st.metric(gui_t("automation.refreshed", locale), snapshot.predictions_refreshed)
    with m5:
        st.metric(gui_t("automation.errors", locale), snapshot.errors)

    st.caption(
        f"Windows — 24h: {snapshot.window_counts.within_24h} · "
        f"6h: {snapshot.window_counts.within_6h} · "
        f"90m: {snapshot.window_counts.within_90m}"
    )

    created = [entry for entry in snapshot.log if entry.action == "created"]
    skipped = [entry for entry in snapshot.log if entry.action == "skipped"]
    refreshed = [entry for entry in snapshot.log if entry.action == "refreshed"]
    errors = [entry for entry in snapshot.log if entry.action == "error"]

    tab_log, tab_created, tab_skip, tab_err = st.tabs(
        [
            gui_t("automation.log", locale),
            gui_t("automation.created", locale),
            gui_t("automation.skipped", locale),
            gui_t("automation.errors", locale),
        ]
    )

    def _render_entries(entries: list) -> None:
        if not entries:
            st.info("None")
            return
        for entry in entries:
            version = entry.prediction_version or "—"
            st.markdown(f"**[{entry.action.upper()}]** {entry.match_name} · `{version}` — {entry.message}")

    with tab_log:
        _render_entries(snapshot.log)
    with tab_created:
        _render_entries(created + refreshed)
    with tab_skip:
        _render_entries(skipped)
    with tab_err:
        _render_entries(errors)


def page_api_setup() -> None:
    locale = _locale()
    settings = get_settings()
    render_hero(gui_t("nav.api", locale), "Test connectivity without exposing secret keys.")

    if st.button(gui_t("btn.test_apis", locale), type="primary"):
        with st.spinner("Testing API connections…"):
            st.session_state["api_test_results"] = test_all_apis(settings)

    statuses = st.session_state.get("api_test_results")
    if statuses is None:
        st.info("Press **Test APIs** to run connection checks.")
        statuses = test_all_apis(settings)

    label, progress = overall_api_readiness(statuses)
    render_readiness_badge(label, locale, progress)

    render_api_status_grid(statuses, locale)

    st.markdown(
        f"**Setup:** {gui_t('api.setup_hint', locale)}\n"
        "- `API_FOOTBALL_KEY` — live fixtures & standings\n"
        "- `OPENAI_API_KEY` — narrative professional reports\n"
        "- `WEATHER_API_KEY` / `OPENWEATHER_API_KEY` — optional weather (`WEATHER_PROVIDER=weatherapi|openweather`)\n"
        "- `SPORTMONKS_API_KEY` — optional football enrichment\n"
        "- `THE_ODDS_API_KEY` — optional odds comparison\n"
        "- `RAPID_FOOTBALL_STATS_ENABLED` + `RAPID_FOOTBALL_STATS_KEY` — supplemental stats/odds\n"
        "- `RAPID_XG_ENABLED` + `RAPID_XG_KEY` — Rapid Football XG Statistics enrichment\n"
        "- `RAPID_OPEN_WEATHER_ENABLED` + `RAPID_OPEN_WEATHER_KEY` — Rapid Open Weather backup"
    )


def page_team_search() -> None:
    locale = _locale()
    t = _translator()
    settings = get_settings()
    comp = _competition_key()
    render_hero(gui_t("nav.game_search", locale), gui_t("team_search.subtitle", locale))

    st.markdown(
        '<p style="color:#64748B;margin-bottom:0.5rem;">'
        "Try: <strong>USA</strong>, <strong>Canada</strong>, <strong>Germany</strong>, <strong>Brazil</strong>"
        "</p>",
        unsafe_allow_html=True,
    )

    default_query = st.session_state.get("team_search_query", "")
    st.markdown('<div class="premium-search">', unsafe_allow_html=True)
    query = st.text_input(
        gui_t("team_search.label", locale),
        value=default_query,
        placeholder=gui_t("shell.search_teams", locale),
        key="team_search_input",
        label_visibility="collapsed",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.session_state["team_search_query"] = query

    if not query.strip():
        st.info(gui_t("team_search.hint", locale))
        return

    service = create_schedule_service(settings, competition_key=comp)
    fixtures = service.get_all_worldcup_fixtures()
    results = search_team_matches(fixtures, query)

    total = sum(len(rows) for rows in results.values())
    st.caption(
        gui_t("team_search.results_count", locale).format(count=total, query=query.strip())
    )

    tab_up, tab_live, tab_fin = st.tabs(
        [
            f"📅 {gui_t('match_center.upcoming', locale)} ({len(results['upcoming'])})",
            f"🔴 {gui_t('match_center.live', locale)} ({len(results['live'])})",
            f"✅ {gui_t('match_center.finished', locale)} ({len(results['finished'])})",
        ]
    )

    def _render_rows(rows: list[Any], key_prefix: str) -> None:
        if not rows:
            st.info(gui_t("team_search.no_matches", locale))
            return
        for row in rows:
            fixture = next((f for f in fixtures if f.fixture_id == row.fixture_id), None)
            if fixture is None:
                continue
            render_match_card(fixture, locale, source=row.source)
            render_match_action_panel(
                fixture,
                locale=locale,
                t=t,
                settings=settings,
                competition_key=comp,
                source=row.source,
                key_prefix=f"{key_prefix}_{row.fixture_id}",
            )

    with tab_up:
        _render_rows(results["upcoming"], "ts_up")
    with tab_live:
        _render_rows(results["live"], "ts_live")
    with tab_fin:
        _render_rows(results["finished"], "ts_fin")


def _load_opening_resolution(*, force: bool = False) -> OpeningMatchResolution:
    refreshed_at = st.session_state.get("opening_refreshed_at")
    cached: OpeningMatchResolution | None = st.session_state.get("opening_resolution")
    now = datetime.utcnow()

    if (
        not force
        and cached is not None
        and refreshed_at is not None
        and (now - refreshed_at).total_seconds() < OPENING_CACHE_TTL_SECONDS
    ):
        return cached

    resolution = resolve_opening_match(
        _schedule_service(),
        get_settings(),
        force_refresh=True,
    )
    st.session_state["opening_resolution"] = resolution
    st.session_state["opening_refreshed_at"] = resolution.refreshed_at_utc
    if resolution.display_fixture:
        st.session_state["opening_fixture"] = resolution.display_fixture
    return resolution


def page_opening_match() -> None:
    locale = _locale()
    t = _translator()
    render_hero(gui_t("nav.opening", locale), "Nearest opening / next scheduled match for the selected competition.")

    col_btn, col_meta = st.columns([1, 3])
    with col_btn:
        force_refresh = st.button(gui_t("btn.find_opening", locale), type="primary")
    with col_meta:
        if force_refresh:
            with st.spinner("Refreshing fixtures from API…"):
                resolution = _load_opening_resolution(force=True)
        else:
            resolution = _load_opening_resolution(force=False)

        refreshed = resolution.refreshed_at_utc.strftime("%Y-%m-%d %H:%M UTC")
        st.caption(f"{gui_t('opening.last_refreshed', locale)}: **{refreshed}**")

    render_source_badge(
        resolution.display_fixture.source if resolution.display_fixture else st.session_state.get("fixture_source"),
        locale,
    )

    if resolution.mode == "none" or resolution.display_fixture is None:
        st.warning(gui_t("opening.no_fixtures", locale))
        return

    badge_col, _ = st.columns([1, 4])
    with badge_col:
        render_fixture_status_badge(resolution.status_badge, locale)

    if resolution.mode == "completed_opening" and resolution.opening_fixture:
        st.info(gui_t("opening.completed_message", locale))
        latest = PredictionHistoryStore().latest_by_fixture()
        stored = latest.get(resolution.opening_fixture.fixture_id)
        eval_map = _finished_evaluations([resolution.opening_fixture])
        evaluation = eval_map.get(resolution.opening_fixture.fixture_id)
        render_finished_match_card(
            resolution.opening_fixture,
            locale,
            winner=winner_label(resolution.opening_fixture),
            evaluation=evaluation,
            stored_record=stored if evaluation is None else None,
        )

        if resolution.next_fixture:
            st.subheader(gui_t("opening.next_scheduled", locale))
            gs_next = format_match_subtitle(resolution.next_fixture, locale)
            if gs_next:
                st.caption(gs_next)
            render_match_card(resolution.next_fixture, locale, source=resolution.next_fixture.source)
            if st.button("Use next match for analysis", key="opening_use_next"):
                st.session_state["opening_fixture"] = resolution.next_fixture
                st.session_state["selected_fixture_id"] = resolution.next_fixture.fixture_id
                st.session_state["fixture_id"] = resolution.next_fixture.fixture_id
                st.session_state["selected_match_name"] = (
                    f"{resolution.next_fixture.home_team} vs {resolution.next_fixture.away_team}"
                )
                st.rerun()
            opening = resolution.next_fixture
        else:
            opening = resolution.opening_fixture
    else:
        opening = resolution.display_fixture
        if resolution.mode == "next_match":
            st.caption("Opening fixture not active — showing next scheduled World Cup match.")
        gs_line = format_match_subtitle(opening, locale)
        if gs_line:
            st.caption(gs_line)
        if resolution.status_badge == "Live":
            render_live_match_card(opening, locale)
        else:
            render_match_card(opening, locale, source=opening.source)

    st.session_state["opening_fixture"] = opening
    fid = opening.fixture_id
    st.session_state["fixture_id"] = fid
    st.session_state["selected_fixture_id"] = fid
    st.session_state["selected_match_name"] = f"{opening.home_team} vs {opening.away_team}"

    if resolution.mode == "completed_opening" and resolution.next_fixture is None:
        return

    tab_pred, tab_spec, tab_rep = st.tabs(["🎯 Prediction", "🧠 Specialists", "📋 Report"])
    with tab_pred:
        if st.button(gui_t("btn.run_prediction", locale), key="opening_predict"):
            with st.spinner("…"):
                result = PredictPipeline(
                    get_settings(), locale=locale, competition_key=_competition_key()
                ).run(fid)
            if result.success:
                render_prediction_card(result.prediction, t, locale)
            else:
                st.error("Prediction failed.")
    with tab_spec:
        if st.button(gui_t("btn.run_specialists", locale), key="opening_spec"):
            with st.spinner("…"):
                result = SpecialistsPipeline(
                    get_settings(), locale=locale, competition_key=_competition_key()
                ).run(fid)
            if result.success:
                _render_specialists_summary(result.report, locale)
            else:
                st.error("Specialist analysis failed.")
    with tab_rep:
        if st.button(gui_t("btn.generate_report", locale), key="opening_rep"):
            with st.spinner("…"):
                svc = OpenAIReasoningService(get_settings())
                report, ok = svc.generate_for_fixture(fid, locale=locale, competition=_competition_key())
            if ok and report:
                _render_report_summary(report, t, locale)
            else:
                st.error(t.t("cli.report.pipeline_failed"))


def page_upcoming() -> None:
    locale = _locale()
    t = _translator()
    render_page_top_anchor()
    render_hero(gui_t("nav.upcoming", locale), t.t("cli.upcoming.header"))
    render_source_badge(st.session_state.get("fixture_source"), locale)

    filter_key = render_fixture_quick_filters(locale, key_prefix="upcoming")
    limit = st.slider("Limit", 1, 50, 30)
    with st.spinner("…"):
        result = UpcomingPipeline(
            get_settings(), locale=locale, competition_key=_competition_key()
        ).run(limit=limit)

    if not result.success:
        st.error("Failed to load fixtures.")
        return

    def _render_upcoming_row(fixture: Any) -> None:
        fid = int(getattr(fixture, "fixture_id", None) or getattr(fixture, "id", 0))
        pred_label, conf = _prediction_badge(fid)
        render_match_card(
            fixture,
            locale,
            source=result.fixtures.source,
            status_override=fixture.status,
            prediction_status=pred_label,
            confidence=conf if conf is not None else None,
        )
        render_stored_prediction_summary(
            fid,
            locale,
            compact=True,
            fixture=fixture,
        )
        cols = st.columns([1, 3])
        with cols[0]:
            if st.button("Select", key=f"upcoming_sel_{fid}"):
                _select_fixture(
                    fid,
                    fixture.home_team,
                    fixture.away_team,
                    source=result.fixtures.source,
                )

    render_grouped_fixture_list(
        result.fixtures.fixtures,
        locale,
        _render_upcoming_row,
        filter_key=filter_key,
        empty_message=gui_t("no_fixture", locale),
    )
    render_back_to_top(locale)


def page_prediction() -> None:
    locale = _locale()
    t = _translator()
    subtitle = t.t("cli.predict.header")
    render_hero(gui_t("nav.predict", locale), subtitle)

    fid = render_match_selector(
        _all_fixtures_for_selector(),
        locale,
        key_prefix="gui_predict",
        default_fixture_id=_default_fixture_id(),
    )
    if fid is None:
        return

    fixture = _lookup_fixture(fid)
    render_fixture_summary_panel(fixture, int(fid), locale)

    if blocks_prediction_actions():
        st.warning(gui_t("access.login_required", locale))
        render_access_home_panel(locale)
        return

    render_stored_prediction_summary(int(fid), locale, compact=False, fixture=fixture)
    render_quota_banner(locale)

    with st.spinner("Loading API intelligence…"):
        intel = _get_intelligence_report(int(fid), locale)

    dev_mode = is_developer_mode()

    def _render_prediction_body() -> None:
        pred_label, pred_type, pred_help = predict_button_label(int(fid), locale)

        if st.button(pred_label, type="primary", help=pred_help or None):
            gate = acquire_prediction_slot()
            if not gate.allowed:
                render_gate_block(gate, locale)
                return
            with st.spinner("Running prediction pipeline…"):
                result = PredictPipeline(
                    get_settings(), locale=locale, competition_key=_competition_key()
                ).run(int(fid))
            st.session_state["gui_last_prediction"] = result
            if result.success:
                invalidate_stored_prediction_cache()
                match_name = fixture.match_name if fixture and hasattr(fixture, "match_name") else _selected_match_name()
                if not match_name and fixture:
                    match_name = f"{fixture.home_team} vs {fixture.away_team}"
                st.toast(gui_t("stored.toast_refreshed", locale).format(match=match_name or "match"))
            st.rerun()

        result = st.session_state.get("gui_last_prediction")
        if result is None:
            if has_stored_prediction(int(fid)):
                st.caption(gui_t("stored.refresh_help", locale))
            else:
                st.info("Run prediction for the selected fixture, or pick a match in Match Center.")
            return
        if not result.success:
            st.error("Prediction pipeline failed.")
            return

        specialist_report = None
        for ar in result.agent_results:
            from worldcup_predictor.domain.specialist import MatchSpecialistReport

            if isinstance(ar.data, MatchSpecialistReport):
                specialist_report = ar.data
                if intel is not None:
                    intel.specialist_report = ar.data
                break

        render_professional_prediction_card(
            result.prediction,
            intel,
            locale,
            specialist_report=specialist_report,
        )

        if dev_mode:
            render_prediction_card(result.prediction, t, locale)
        else:
            with st.expander(gui_t("tech.more_prediction", locale), expanded=False):
                render_prediction_card(result.prediction, t, locale)

        if intel is not None:
            if not dev_mode:
                with st.expander(gui_t("tech.data_quality", locale), expanded=False):
                    render_data_quality_breakdown(intel, locale)

            from worldcup_predictor.ui.odds_display import render_phase36_odds_section

            with st.expander(gui_t("tech.odds", locale), expanded=dev_mode):
                render_phase36_odds_section(
                    intel,
                    locale,
                    prediction=result.prediction,
                    specialist_report=specialist_report,
                    fixture_id=int(fid),
                )

        render_prediction_analysis_details(
            result.prediction,
            intel,
            locale,
            t,
            developer_mode=dev_mode,
        )
        render_feedback_form(
            locale,
            fixture_id=int(fid),
            prediction_context=result.prediction.match_name,
            key_prefix=f"predict_fb_{fid}",
        )
        st.caption("Prediction stored in learning memory (data/predictions/prediction_history.jsonl).")

    if dev_mode:
        tab_pred, tab_insp = st.tabs(["🎯 Prediction", "🔍 API Data Inspector"])
        with tab_insp:
            if intel is not None:
                render_api_inspector_panel(intel, locale)
                render_data_quality_breakdown(intel, locale)
            else:
                st.caption("API intelligence unavailable — daily limit may be reached.")
        with tab_pred:
            _render_prediction_body()
    else:
        _render_prediction_body()


def page_specialists() -> None:
    locale = _locale()
    render_hero(gui_t("nav.specialists", locale), "Multi-agent specialist domain analysis.")
    _render_selected_fixture_banner(locale)

    fid = render_match_selector(
        _all_fixtures_for_selector(),
        locale,
        key_prefix="gui_spec",
        default_fixture_id=_default_fixture_id(),
    )
    if fid is None:
        return

    if st.button(gui_t("btn.run_specialists", locale), type="primary"):
        with st.spinner("Running specialist agents…"):
            result = SpecialistsPipeline(
                get_settings(), locale=locale, competition_key=_competition_key()
            ).run(int(fid))
        st.session_state["gui_last_specialists"] = result

    result = st.session_state.get("gui_last_specialists")
    if result is None:
        st.info(gui_t("demo_hint", locale))
        return
    if not result.success:
        st.error("Specialist pipeline failed.")
        return
    _render_specialists_summary(result.report, locale)


def _render_specialists_summary(report: Any, locale: Locale) -> None:
    score = report.aggregated_signal_score
    st.caption(f"Aggregated signal: **{score if score is not None else 'n/a'}** · Source: {report.source}")
    weather_sig = report.signals.get("weather_agent")
    if weather_sig and weather_sig.signals.get("weather_impact_score") is not None:
        st.caption(
            f"Weather impact: **{weather_sig.signals.get('weather_impact_score')}** "
            f"({weather_sig.signals.get('weather_source') or 'live'})"
        )
    for name, signal in report.signals.items():
        with st.expander(f"{name} — {signal.status.upper()}", expanded=False):
            st.markdown(f"**Domain:** {signal.domain}")
            if signal.impact_score is not None:
                st.progress(min(max(signal.impact_score / 100.0, 0.0), 1.0))
            if signal.notes:
                st.write(signal.notes)
            if signal.warnings:
                for w in signal.warnings:
                    st.warning(w)
            if signal.missing_data:
                for item in signal.missing_data:
                    st.caption(f"Missing: {item}")


def page_professional_report() -> None:
    locale = _locale()
    t = _translator()
    fixture = _lookup_fixture(_default_fixture_id())
    subtitle = t.t("cli.report.header")
    gs_line = format_match_subtitle(fixture, locale) if fixture else ""
    if gs_line:
        subtitle = f"{subtitle} · {gs_line}"
    render_hero(gui_t("nav.report", locale), subtitle)
    _render_selected_fixture_banner(locale)

    fid = render_match_selector(
        _all_fixtures_for_selector(),
        locale,
        key_prefix="gui_rep",
        default_fixture_id=_default_fixture_id(),
    )
    if fid is None:
        return

    if st.button(gui_t("btn.generate_report", locale), type="primary"):
        with st.spinner("Generating professional report…"):
            svc = OpenAIReasoningService(get_settings())
            report, ok = svc.generate_for_fixture(
                int(fid), locale=locale, competition=_competition_key()
            )
        st.session_state["gui_last_report"] = report if ok else None
        if not ok:
            st.error(t.t("cli.report.pipeline_failed"))

    report = st.session_state.get("gui_last_report")
    if report is None:
        st.info(gui_t("demo_hint", locale))
        return
    _render_report_summary(report, t, locale)


def _render_report_summary(report: Any, t: Any, locale: Locale) -> None:
    render_professional_report_view(report, t, locale, fixture=_lookup_fixture(_default_fixture_id()))


def page_audit() -> None:
    locale = _locale()
    t = _translator()
    render_hero(gui_t("nav.audit", locale), "Weighted decision audit with confidence trace.")
    _render_selected_fixture_banner(locale)

    fid = render_match_selector(
        _all_fixtures_for_selector(),
        locale,
        key_prefix="gui_audit",
        default_fixture_id=_default_fixture_id(),
    )
    if fid is None:
        return

    if st.button(gui_t("btn.run_audit", locale), type="primary"):
        with st.spinner("Running audit pipeline…"):
            result = AuditPipeline(
                get_settings(), locale=locale, competition_key=_competition_key()
            ).run(int(fid))
        st.session_state["gui_last_audit"] = result

    result = st.session_state.get("gui_last_audit")
    if result is None:
        st.info(gui_t("demo_hint", locale))
        return
    if not result.success:
        st.error("Audit pipeline failed.")
        return

    render_prediction_card(result.prediction, t, locale)
    audit = result.prediction.audit_report
    render_audit_details(audit, locale)


def page_backtest_calibration() -> None:
    locale = _locale()
    render_hero(gui_t("nav.backtest", locale), "Historical model evaluation and weight calibration reports.")

    tab_bt, tab_cal, tab_imp = st.tabs(["📈 Backtest", "🎚️ Calibration", "📥 Import"])

    with tab_bt:
        data = _load_json(REPORT_PATHS["backtest"])
        if data is None:
            st.warning(
                "No backtest report yet. Run from terminal: "
                "`python main.py backtest --csv data/historical/worldcup_sample.csv`"
            )
        else:
            metrics = data.get("metrics", {})
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Matches", metrics.get("total_matches", 0))
            with c2:
                st.metric("1X2 Accuracy", _pct(metrics.get("one_x_two_accuracy")))
            with c3:
                st.metric("O/U 2.5", _pct(metrics.get("over_under_2_5_accuracy")))
            with c4:
                st.metric("Brier (1X2)", f"{metrics.get('brier_one_x_two', 0):.3f}")
            breakdown = metrics.get("confidence_breakdown") or {}
            if breakdown:
                fig = px.bar(
                    x=list(breakdown.keys()),
                    y=list(breakdown.values()),
                    labels={"x": "Band", "y": "Count"},
                    title="Confidence distribution",
                )
                st.plotly_chart(fig, use_container_width=True)

    with tab_cal:
        data = _load_json(REPORT_PATHS["calibration"])
        if data is None:
            st.warning(
                "No calibration report. Run: "
                "`python main.py calibrate --csv data/historical/worldcup_sample.csv`"
            )
        else:
            st.metric("Sample size", data.get("sample_size", 0))
            current = data.get("current_weights", {})
            recommended = data.get("recommended_weights", {})
            rows = [
                {
                    "Factor": k,
                    "Current": current.get(k, 0),
                    "Recommended": recommended.get(k, 0),
                }
                for k in sorted(current.keys())
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab_imp:
        data = _load_json(REPORT_PATHS["import"])
        if data is None:
            st.warning(
                "No import report. Run: "
                "`python main.py import-history --worldcup --seasons 2018 2022`"
            )
        else:
            st.metric("Imported rows", data.get("imported_count", data.get("total_rows", 0)))
            st.json(data)


def page_daily_shortlist() -> None:
    locale = _locale()
    settings = get_settings()
    comp = _competition_key()
    render_hero(gui_t("shortlist.title", locale), gui_t("shortlist.subtitle", locale))
    st.warning(gui_t("disclaimer", locale))

    days = st.slider("Lookahead days", 1, 7, 3, key="shortlist_days")
    if st.button("Refresh shortlist", type="primary"):
        st.session_state.pop("shortlist_snapshot", None)

    schedule = create_schedule_service(settings, competition_key=comp)
    fixtures = schedule.get_all_worldcup_fixtures()
    engine = MatchSelectionEngine()
    shortlist = st.session_state.get("shortlist_snapshot")
    if shortlist is None:
        shortlist = engine.build_shortlist(fixtures, competition_key=comp, days=days)
        st.session_state["shortlist_snapshot"] = shortlist

    def _render_group(title: str, items: list, color: str) -> None:
        st.subheader(f"{title} ({len(items)})")
        if not items:
            st.caption("None in this category.")
            return
        for item in items[:12]:
            with st.container(border=True):
                st.markdown(f"**{item.match_name}** · score **{item.scores.total:.1f}**")
                st.caption(item.reason)
                if item.expected_improvement:
                    st.caption(f"Expected improvement: {item.expected_improvement}")
                st.caption(
                    f"Data readiness: {item.data_quality:.0f}% · "
                    f"Lineups: {'yes' if item.lineups_available else 'no'}"
                )
                render_stored_prediction_summary(item.fixture_id, locale, compact=True)
                pred_label, _, pred_help = predict_button_label(item.fixture_id, locale)
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(pred_label, key=f"sl_pred_{item.fixture_id}", help=pred_help or None):
                        st.session_state["selected_fixture_id"] = item.fixture_id
                        st.session_state["fixture_id"] = item.fixture_id
                        st.session_state["gui_page"] = "predict"
                        st.rerun()
                with c2:
                    if st.button("Report", key=f"sl_rep_{item.fixture_id}"):
                        st.session_state["selected_fixture_id"] = item.fixture_id
                        st.session_state["fixture_id"] = item.fixture_id
                        st.session_state["gui_page"] = "report"
                        st.rerun()

    _render_group("Auto Predict", shortlist.auto_predict, "green")
    _render_group("Watchlist", shortlist.watchlist, "blue")
    _render_group("Wait for Lineups", shortlist.wait_for_lineups, "orange")
    _render_group("Skipped", shortlist.skipped, "gray")


def page_learning_agent() -> None:
    locale = _locale()
    comp = _competition_key()
    render_hero(gui_t("nav.learning", locale), gui_t("coach.subtitle", locale))
    st.warning(gui_t("coach.disclaimer", locale))

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button(gui_t("coach.run", locale), type="primary"):
            with st.spinner("Running learning agent…"):
                coach = _coach_agent().run(competition_key=comp)
                st.session_state["coach_snapshot"] = coach
            st.rerun()
    with btn_col2:
        if st.button(gui_t("patterns.discover", locale)):
            with st.spinner("Discovering patterns…"):
                pattern_report = _pattern_engine().run_all(write_reports=True)
                st.session_state["pattern_snapshot"] = pattern_report
            st.rerun()

    coach = st.session_state.get("coach_snapshot")
    if coach is None:
        coach = _coach_agent().load_from_disk()
    if coach is None:
        loaded = _db_repo().latest_coach_report(competition_key=comp)
        if loaded:
            from worldcup_predictor.learning.models import ModelCoachReport

            coach = ModelCoachReport.from_dict(loaded)
    if coach is None:
        coach = _coach_agent().run(competition_key=comp, write_reports=True)
        st.session_state["coach_snapshot"] = coach

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(gui_t("coach.strongest", locale), coach.strongest_market or "—")
    with c2:
        st.metric(gui_t("coach.weakest", locale), coach.weakest_market or "—")
    with c3:
        st.metric(gui_t("coach.focus", locale), coach.suggested_focus_area or "—")

    if coach.sample_size_warning or coach.warnings_about_small_sample_size:
        st.markdown(f"**{gui_t('coach.warnings', locale)}**")
        if coach.sample_size_warning:
            st.warning(coach.sample_size_warning)
        for warning in coach.warnings_about_small_sample_size:
            st.warning(warning)

    if coach.competition_winrates:
        st.subheader("Competition performance")
        comp_rows = []
        for ck, markets in coach.competition_winrates.items():
            for market, rate in markets.items():
                comp_rows.append({"Competition": ck, "Market": market, "Winrate": _pct(rate)})
        if comp_rows:
            st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

    from worldcup_predictor.odds.league_learning import LeagueLearningEngine
    from worldcup_predictor.ui.odds_display import render_league_learning_table

    league_profiles = st.session_state.get("league_learning_profiles")
    if league_profiles is None:
        league_profiles = LeagueLearningEngine(_db_repo()).build_all_profiles()
        st.session_state["league_learning_profiles"] = league_profiles
    render_league_learning_table(league_profiles, locale)

    if coach.decision_agent_advice:
        st.markdown(f"**{gui_t('coach.advice', locale)}**")
        for advice in coach.decision_agent_advice:
            st.markdown(f"- {advice}")

    if coach.recommended_selection_rules:
        st.markdown("**Recommended selection rules**")
        for rule in coach.recommended_selection_rules:
            st.markdown(f"- {rule}")

    if coach.recommended_weight_adjustments:
        with st.expander(gui_t("coach.weights", locale)):
            for factor, note in coach.recommended_weight_adjustments.items():
                st.markdown(f"**{factor}** — {note}")

    st.divider()
    st.info(gui_t("patterns.disclaimer", locale))

    pattern_report = st.session_state.get("pattern_snapshot")
    if pattern_report is None:
        pattern_report = _pattern_engine().load_from_disk()
    if pattern_report is None:
        pattern_report = _pattern_engine().run(competition_key=comp, write_reports=True)
        st.session_state["pattern_snapshot"] = pattern_report

    render_pattern_discovery_panel(pattern_report, locale)

    st.subheader(gui_t("ml.status", locale))
    ml_models = MLPredictor().status()
    if ml_models:
        st.dataframe(pd.DataFrame(ml_models), use_container_width=True, hide_index=True)
    else:
        st.caption("No trained ML models yet — requires ≥30 verified samples per market.")


def page_learning_center_v2() -> None:
    locale = _locale()
    comp = _competition_key()
    render_hero(gui_t("learning_v2.title", locale), gui_t("coach.subtitle", locale))
    st.warning(gui_t("learning_v2.human_review", locale))
    from worldcup_predictor.ui.self_learning_display import render_learning_accuracy_center_v2

    render_learning_accuracy_center_v2(locale, competition_key=comp)


def page_professional_reports() -> None:
    locale = _locale()
    render_hero(gui_t("nav.professional_reports", locale), gui_t("reports_page.hint", locale))
    render_professional_reports_page(locale)
    render_back_to_top(locale)


def page_upgrade() -> None:
    locale = _locale()
    render_hero(gui_t("nav.upgrade", locale), gui_t("upgrade.disclaimer", locale))
    render_upgrade_page(locale)
    render_back_to_top(locale)


def page_admin_entitlements() -> None:
    locale = _locale()
    if not is_admin_session():
        st.warning(gui_t("admin.dev_required", locale))
        return
    render_hero(gui_t("nav.admin_entitlements", locale), gui_t("admin.hint", locale))
    render_admin_entitlements_page(locale)
    render_back_to_top(locale)


def page_feedback_viewer() -> None:
    locale = _locale()
    if not is_admin_session():
        st.warning(gui_t("admin.dev_required", locale))
        return
    render_hero(gui_t("nav.feedback_viewer", locale), "")
    render_feedback_viewer_page(locale)
    render_back_to_top(locale)


def page_settings() -> None:
    locale = _locale()
    try:
        _render_settings_page(locale)
    except Exception as exc:
        import logging

        logging.getLogger(__name__).exception("Settings page failed: %s", exc)
        st.error(
            "Settings could not load completely. Details were written to the application log — "
            "no raw traceback is shown here."
        )


def _render_settings_page(locale: Locale) -> None:
    settings = get_settings()
    render_hero(gui_t("nav.settings", locale), "Application preferences — secrets stay in `.env`.")

    st.markdown('<div class="settings-section-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="settings-section-title">{gui_t("mode.default", locale)}</div>', unsafe_allow_html=True)
    from worldcup_predictor.ui.gui_mode_v2 import load_default_gui_mode

    mode_options = ["user", "developer"] if is_admin_session() else ["user"]
    current_default = load_default_gui_mode()
    if not is_admin_session():
        current_default = "user"
    picked_default = st.selectbox(
        gui_t("mode.default", locale),
        mode_options,
        index=mode_options.index(current_default) if current_default in mode_options else 0,
        format_func=lambda k: gui_t("mode.user", locale) if k == "user" else gui_t("mode.developer", locale),
        key="settings_default_gui_mode",
    )
    st.caption(gui_t("mode.default_hint", locale))
    if st.button(gui_t("settings.save", locale), key="save_default_gui_mode"):
        save_default_gui_mode(picked_default if is_admin_session() else "user")  # type: ignore[arg-type]
        if is_admin_session():
            st.session_state["gui_mode"] = picked_default
        else:
            st.session_state["gui_mode"] = "user"
        st.toast(gui_t("settings.save", locale))
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.pop("_trigger_sync", False):
        with st.spinner("Syncing API data…"):
            result = DataSyncService(settings).sync_competition(_competition_key())
            st.session_state["last_sync_result"] = result
        st.toast("Sync complete.")

    # Database Status
    st.markdown('<div class="settings-section-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="settings-section-title">{gui_t("settings.database", locale)}</div>', unsafe_allow_html=True)
    db_status = _db_repo().status()
    st.success(f"{gui_t('db.connected', locale)} — `{db_status.path}` (schema v{db_status.schema_version})")
    counts = db_status.table_counts
    dc1, dc2, dc3, dc4 = st.columns(4)
    with dc1:
        st.metric("Fixtures", counts.get("fixtures", 0))
    with dc2:
        st.metric("Predictions", counts.get("predictions", 0))
    with dc3:
        st.metric("Verifications", counts.get("verification_results", 0))
    with dc4:
        st.metric("Coach reports", counts.get("model_coach_reports", 0))
    st.markdown("</div>", unsafe_allow_html=True)

    # Sync Status
    st.markdown('<div class="settings-section-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="settings-section-title">{gui_t("settings.sync", locale)}</div>', unsafe_allow_html=True)
    if st.button(gui_t("db.sync", locale)):
        with st.spinner("Syncing API data…"):
            result = DataSyncService(settings).sync_competition(_competition_key())
            st.session_state["last_sync_result"] = result
        st.rerun()
    sync_result = st.session_state.get("last_sync_result")
    if sync_result:
        st.info(
            f"Last sync: fixtures={sync_result.fixtures_synced}, results={sync_result.results_synced}, "
            f"odds={sync_result.odds_snapshots}, xG={sync_result.xg_snapshots}"
        )
    else:
        st.caption("No sync run in this session yet.")
    st.markdown("</div>", unsafe_allow_html=True)

    # API Status
    st.markdown('<div class="settings-section-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="settings-section-title">{gui_t("settings.api", locale)}</div>', unsafe_allow_html=True)
    st.caption(gui_t("settings.api_hint", locale))
    api_statuses = test_all_apis(settings)
    render_api_status_grid(api_statuses, locale)
    st.markdown("</div>", unsafe_allow_html=True)

    # Application Settings
    st.markdown('<div class="settings-section-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="settings-section-title">{gui_t("settings.application", locale)}</div>', unsafe_allow_html=True)
    st.markdown(
        f"- **Default locale:** `{settings.default_locale}`\n"
        f"- **OpenAI model:** `{settings.openai_model}`\n"
        f"- **Fixture limit:** `{settings.upcoming_fixture_limit}`\n"
        f"- **Cache TTL:** `{settings.api_cache_ttl_seconds}s`"
    )
    st.caption("Optional enrichment providers (API-Sports remains primary):")
    from worldcup_predictor.providers.registry import ProviderRegistry

    for item in ProviderRegistry(settings).status_report():
        if item.provider in ("rapid_football_stats", "rapid_xg_statistics", "rapid_open_weather", "api_football"):
            continue
        tier = "Primary" if item.tier.name == "PRIMARY" else "Enrichment"
        state = "configured" if item.configured else "not set (optional)"
        st.markdown(f"- **{item.label}** ({tier}) — `{item.env_var}` — {state}")
    st.markdown(f"- **Weather provider:** `{settings.weather_provider}`")
    comp = CompetitionService().get_competition(_competition_key())
    st.markdown(f"- **Active competition:** **{comp.display_name}** (`{comp.key}`)")
    st.markdown("</div>", unsafe_allow_html=True)

    st.info(gui_t("disclaimer", locale))


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


if __name__ == "__main__":
    main()
