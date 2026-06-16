"""Inline match actions for Match Center — Phase 20."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.access.prediction_gate import acquire_prediction_slot, preview_api_access
from worldcup_predictor.accuracy.evaluator import evaluate_prediction
from worldcup_predictor.accuracy.models import PredictionHistoryRecord
from worldcup_predictor.config.settings import Locale, Settings
from worldcup_predictor.schedule.match_center import classify_status
from worldcup_predictor.i18n.translator import Translator
from worldcup_predictor.orchestration.audit_pipeline import AuditPipeline
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.orchestration.specialists_pipeline import SpecialistsPipeline
from worldcup_predictor.reasoning.openai_reasoning_service import OpenAIReasoningService
from worldcup_predictor.ui.access_display import render_gate_block
from worldcup_predictor.ui.first_goal_display import render_first_goal_sections
from worldcup_predictor.ui.gui_components import (
    format_standings_context,
    render_data_quality_breakdown,
    render_prediction_analysis_details,
    render_prediction_card,
)
from worldcup_predictor.ui.fixture_display import format_group_stage
from worldcup_predictor.ui.readiness import analysis_readiness
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.professional_prediction_card import render_professional_prediction_card
from worldcup_predictor.ui.stored_prediction_summary import (
    evaluate_stored_prediction,
    has_stored_prediction,
    invalidate_stored_prediction_cache,
    predict_button_label,
    render_stored_prediction_summary,
)
from worldcup_predictor.ui.fixture_display import format_group_stage, format_kickoff_hero
from worldcup_predictor.ui.team_display import match_showcase_html


def _fixture_id(fixture: Any) -> int:
    return int(getattr(fixture, "fixture_id", None) or getattr(fixture, "id"))


def _fixture_teams(fixture: Any) -> tuple[str, str]:
    return getattr(fixture, "home_team", "?"), getattr(fixture, "away_team", "?")


def _cache_for(fixture_id: int) -> dict[str, Any]:
    root = st.session_state.setdefault("match_center_action_cache", {})
    return root.setdefault(str(fixture_id), {})


def clear_fixture_action_cache(fixture_id: int, action: str | None = None) -> None:
    cache = _cache_for(fixture_id)
    if action is None:
        cache.clear()
        return
    if action == "intel":
        cache.pop("intel", None)
        return
    cache.pop(action, None)
    if action in ("analyze",):
        cache.pop("intel", None)


def select_fixture_only(
    fixture_id: int,
    home: str,
    away: str,
    *,
    source: str | None = None,
) -> None:
    st.session_state["selected_fixture_id"] = fixture_id
    st.session_state["selected_match_name"] = f"{home} vs {away}"
    if source:
        st.session_state["fixture_source"] = source
    st.toast(f"Selected: {home} vs {away}")
    st.rerun()


def _open_panel(fixture_id: int, tab: str, home: str, away: str, *, source: str | None) -> None:
    st.session_state["mc_panel_fixture_id"] = fixture_id
    st.session_state["mc_panel_tab"] = tab
    st.session_state["selected_fixture_id"] = fixture_id
    st.session_state["selected_match_name"] = f"{home} vs {away}"
    if source:
        st.session_state["fixture_source"] = source


def _load_intelligence(fixture_id: int, settings: Settings, locale: Locale) -> Any:
    gate = preview_api_access()
    if not gate.allowed:
        render_gate_block(gate, locale)
        return None
    cache = _cache_for(fixture_id)
    if cache.get("intel") is not None:
        return cache["intel"]
    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient

    report = MatchIntelligenceBuilder(ApiFootballClient(settings)).build_by_fixture_id(fixture_id)
    cache["intel"] = report
    return report


def _run_predict(fixture_id: int, settings: Settings, locale: Locale, competition_key: str) -> Any:
    gate = acquire_prediction_slot()
    if not gate.allowed:
        render_gate_block(gate, locale)
        return None
    return PredictPipeline(settings, locale=locale, competition_key=competition_key).run(fixture_id)


def _run_specialists(fixture_id: int, settings: Settings, locale: Locale, competition_key: str) -> Any:
    return SpecialistsPipeline(settings, locale=locale, competition_key=competition_key).run(fixture_id)


def _run_audit(fixture_id: int, settings: Settings, locale: Locale, competition_key: str) -> Any:
    return AuditPipeline(settings, locale=locale, competition_key=competition_key).run(fixture_id)


def _run_report(fixture_id: int, settings: Settings, locale: Locale, competition_key: str) -> tuple[Any, bool]:
    return OpenAIReasoningService(settings).generate_for_fixture(
        fixture_id, locale=locale, competition=competition_key
    )


def _cache_phase36_odds_from_cache(fixture_id: int, cache: dict[str, Any]) -> None:
    """Cache Phase 36 odds for Match Center badge — never raises."""
    try:
        from worldcup_predictor.domain.specialist import MatchSpecialistReport
        from worldcup_predictor.ui.odds_display import cache_phase36_odds

        intel = cache.get("intel")
        pred_result = cache.get("predict")
        spec_result = cache.get("specialists")
        specialist_report = None
        prediction = None

        if pred_result and getattr(pred_result, "success", False):
            prediction = pred_result.prediction
            for ar in pred_result.agent_results:
                if isinstance(ar.data, MatchSpecialistReport):
                    specialist_report = ar.data
                    if intel is not None:
                        intel.specialist_report = ar.data
                    break

        if specialist_report is None and spec_result and getattr(spec_result, "success", False):
            specialist_report = getattr(spec_result, "report", None)

        if intel is not None or specialist_report is not None or prediction is not None:
            cache_phase36_odds(
                fixture_id,
                intel,
                prediction=prediction,
                specialist_report=specialist_report,
            )
    except Exception:
        pass


def _cached_prediction(cache: dict[str, Any]) -> Any | None:
    pred_result = cache.get("predict")
    if pred_result and getattr(pred_result, "success", False):
        return pred_result.prediction
    audit_result = cache.get("audit")
    if audit_result and getattr(audit_result, "success", False):
        return audit_result.prediction
    return None


def render_analyze_summary(
    intel: Any,
    locale: Locale,
    *,
    prediction: Any | None = None,
    api_configured: bool = True,
    fixture: Any | None = None,
) -> None:
    dq = intel.data_quality
    dq_total = (dq.breakdown_total if dq else 0) or int((dq.score or 0) * 100 if dq else 0)
    pq = getattr(prediction, "prediction_quality_score", 0.0) if prediction else 0.0

    readiness, progress, reason = analysis_readiness(
        prediction,
        placeholder=bool(getattr(intel, "is_placeholder", False)),
        api_configured=api_configured,
        intel=intel,
    )

    st.markdown('<div class="analysis-panel-body">', unsafe_allow_html=True)

    if fixture is not None:
        home = getattr(fixture, "home_team", intel.home_team.team_name)
        away = getattr(fixture, "away_team", intel.away_team.team_name)
        st.markdown(
            match_showcase_html(
                home,
                away,
                fixture=fixture,
                country_hint=getattr(fixture, "country", None),
            ),
            unsafe_allow_html=True,
        )
        time_line, date_line, venue_line = format_kickoff_hero(fixture, locale)
        venue_bit = f" · {venue_line}" if venue_line else ""
        st.markdown(
            f'<div class="analysis-kickoff-line"><span class="showcase-time">{time_line}</span>'
            f'<span class="showcase-date">{date_line}{venue_bit}</span></div>',
            unsafe_allow_html=True,
        )

    pq_display = f"{pq:.0f}/100" if prediction else "—"
    st.markdown(
        f"""
<div class="analysis-metric-grid">
  <div class="analysis-metric">
    <div class="analysis-metric-label">{gui_t("badge.data_quality", locale)}</div>
    <div class="analysis-metric-value">{dq_total}/100</div>
  </div>
  <div class="analysis-metric">
    <div class="analysis-metric-label">{gui_t("badge.prediction_quality", locale)}</div>
    <div class="analysis-metric-value">{pq_display}</div>
  </div>
  <div class="analysis-metric">
    <div class="analysis-metric-label">{gui_t("badge.readiness", locale)}</div>
    <div class="analysis-metric-value" style="font-size:1rem;">{readiness}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    if reason:
        st.caption(reason)

    if prediction:
        from worldcup_predictor.ui.adaptive_confidence_display import render_prediction_adaptive_panel
        from worldcup_predictor.ui.data_quality_display import render_data_quality_breakdown

        render_data_quality_breakdown(intel, locale)
        render_prediction_adaptive_panel(prediction, locale)

    if prediction and (prediction.no_bet_flag or dq_total < 45):
        st.warning(gui_t("watch_only", locale))

    if intel.missing_data:
        missing = ", ".join(intel.missing_data[:12])
        st.markdown(
            f'<div class="analysis-missing">{gui_t("analysis.missing_data", locale)}: {missing}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
<div class="analysis-form-row">
  <div class="analysis-form-card"><strong>{intel.home_team.team_name}</strong> form: <code>{intel.home_team.form or "—"}</code></div>
  <div class="analysis-form-card"><strong>{intel.away_team.team_name}</strong> form: <code>{intel.away_team.form or "—"}</code></div>
</div>
""",
        unsafe_allow_html=True,
    )

    if intel.odds and intel.odds.available:
        st.caption(f"✓ Odds — {len(intel.odds.bookmakers)} bookmaker snapshot(s)")
    else:
        st.caption("Odds: not loaded")

    gc = getattr(intel, "group_context", None) or (getattr(prediction, "group_context", None) if prediction else None)
    fx = fixture or getattr(intel, "fixture", None)
    if gc and gc.get("available"):
        gh = gc.get("home") or {}
        ga = gc.get("away") or {}
        stage_label = format_group_stage(fx, gc) if fx is not None else format_group_stage(gc)
        stand_line = format_standings_context(gh, ga, locale)
        caption = f"{gui_t('card.group', locale)}: **{stage_label}**"
        if stand_line:
            caption += f" · {stand_line}"
        st.caption(caption)
    elif getattr(intel, "standings_context", None) and intel.standings_context.get("available"):
        st.caption("Standings loaded — group positions in full prediction view.")
    elif fx is not None:
        stage_label = format_group_stage(fx)
        if stage_label != "—":
            st.caption(f"{gui_t('card.group', locale)}: **{stage_label}**")

    st.markdown("</div>", unsafe_allow_html=True)


def _render_audit_tab(result: Any, locale: Locale, t: Translator) -> None:
    if not result or not result.success:
        st.error("Audit not available. Click **Audit** or **Refresh** to run.")
        return
    pred = result.prediction
    render_prediction_card(pred, t, locale)
    audit = pred.audit_report
    if not audit:
        st.info("No audit report attached to this prediction.")
        return
    if audit.trace:
        trace = audit.trace
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Baseline confidence", f"{trace.baseline_confidence:.0f}")
        with c2:
            st.metric("Final confidence", f"{trace.final_confidence:.0f}")
        if trace.watch_only:
            st.warning(gui_t("watch_only", locale))
        if trace.no_bet_reasons:
            st.markdown("**No-bet reasons**")
            for reason in trace.no_bet_reasons:
                st.caption(f"• {reason}")
    if audit.supported_factors:
        st.markdown("**Supporting factors**")
        for factor in audit.supported_factors[:8]:
            st.caption(f"• {factor.factor_name}: {factor.direction} ({factor.contribution:+.3f})")
    if audit.opposed_factors:
        st.markdown("**Opposing factors**")
        for factor in audit.opposed_factors[:6]:
            st.caption(f"• {factor.factor_name} ({factor.contribution:+.3f})")


def _render_report_tab(report: Any | None, ok: bool, t: Translator, locale: Locale) -> None:
    if not ok or report is None:
        st.error(t.t("cli.report.pipeline_failed"))
        return
    if report.watch_only:
        st.warning(gui_t("watch_only", locale))
    gen = getattr(report, "generated_at_utc", "") or ""
    st.caption(
        f"{t.t('cli.report.source')}: {report.source} · {report.match_name}"
        + (f" · Generated (UTC): {gen[:19]}" if gen else "")
    )
    st.subheader(t.t("cli.report.executive_summary"))
    st.write(report.executive_summary)
    st.subheader(t.t("cli.report.prediction_summary"))
    st.json(report.prediction_summary)
    st.subheader(t.t("cli.report.final_view"))
    st.write(report.final_analytical_view)
    st.caption(report.disclaimer)


def _render_specialists_tab(result: Any, locale: Locale) -> None:
    if not result or not result.success:
        st.error("Specialists not available. Click **Specialists** or **Refresh**.")
        return
    report = result.report
    score = report.aggregated_signal_score
    st.caption(f"Aggregated signal: **{score if score is not None else 'n/a'}** · Source: {report.source}")
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


def render_match_action_panel(
    fixture: Any,
    *,
    locale: Locale,
    t: Translator,
    settings: Settings,
    competition_key: str,
    source: str | None,
    key_prefix: str,
) -> None:
    fid = _fixture_id(fixture)
    home, away = _fixture_teams(fixture)
    cache = _cache_for(fid)
    has_stored = has_stored_prediction(fid)
    predict_label, predict_type, predict_help = predict_button_label(fid, locale)

    labels = (
        "📊 Analyze",
        predict_label,
        "🧠 Specialists",
        "📋 Report",
        "🔍 Audit",
    )
    actions = (
        "analyze",
        "predict",
        "specialists",
        "report",
        "audit",
    )
    st.markdown('<div class="premium-action-row">', unsafe_allow_html=True)
    cols = st.columns(len(labels))
    for col, label, action in zip(cols, labels, actions):
        with col:
            btn_type = predict_type if action == "predict" else "secondary"
            if st.button(
                label,
                key=f"{key_prefix}_btn_{action}",
                type=btn_type,
                use_container_width=True,
                help=predict_help if action == "predict" and predict_help else None,
            ):
                _open_panel(fid, action, home, away, source=source)
                if action == "analyze":
                    with st.spinner("Loading API data…"):
                        _load_intelligence(fid, settings, locale)
                elif action == "predict":
                    with st.spinner("Running prediction…"):
                        cache["predict"] = _run_predict(fid, settings, locale, competition_key)
                    if cache.get("predict") and getattr(cache["predict"], "success", False):
                        invalidate_stored_prediction_cache()
                        st.session_state["gui_last_prediction"] = cache["predict"]
                        _cache_phase36_odds_from_cache(fid, cache)
                        st.toast(gui_t("stored.toast_refreshed", locale).format(match=f"{home} vs {away}"))
                elif action == "specialists":
                    with st.spinner("Running specialists…"):
                        cache["specialists"] = _run_specialists(fid, settings, locale, competition_key)
                    if cache.get("specialists") and getattr(cache["specialists"], "success", False):
                        _cache_phase36_odds_from_cache(fid, cache)
                elif action == "report":
                    with st.spinner("Generating report…"):
                        report, ok = _run_report(fid, settings, locale, competition_key)
                        cache["report"] = report
                        cache["report_ok"] = ok
                elif action == "audit":
                    with st.spinner("Running audit…"):
                        cache["audit"] = _run_audit(fid, settings, locale, competition_key)
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    evaluation = evaluate_stored_prediction(fid, fixture)
    render_stored_prediction_summary(
        fid,
        locale,
        compact=classify_status(getattr(fixture, "status", "")) != "finished",
        fixture=fixture,
        evaluation=evaluation,
    )

    from worldcup_predictor.ui.international_match_card import render_developer_panel

    render_developer_panel(fixture, locale=locale, source=source, intel=cache.get("intel"))

    if st.session_state.get("mc_panel_fixture_id") != fid:
        return

    st.markdown(
        '<div class="match-action-panel">',
        unsafe_allow_html=True,
    )

    hdr, ref = st.columns([4, 1])
    with hdr:
        st.markdown(f'<div class="analysis-panel-title">{gui_t("analysis.inline_title", locale)}</div>', unsafe_allow_html=True)
    with ref:
        if st.button("Refresh", key=f"{key_prefix}_refresh", use_container_width=True):
            tab = st.session_state.get("mc_panel_tab", "analyze")
            if tab == "analyze":
                clear_fixture_action_cache(fid, "intel")
                with st.spinner("Refreshing API data…"):
                    _load_intelligence(fid, settings, locale)
            elif tab == "predict":
                clear_fixture_action_cache(fid, "predict")
                with st.spinner("Refreshing prediction…"):
                    cache["predict"] = _run_predict(fid, settings, locale, competition_key)
                if cache.get("predict") and getattr(cache["predict"], "success", False):
                    invalidate_stored_prediction_cache()
                    st.session_state["gui_last_prediction"] = cache["predict"]
                    _cache_phase36_odds_from_cache(fid, cache)
                    st.toast(gui_t("stored.toast_refreshed", locale).format(match=f"{home} vs {away}"))
            elif tab == "specialists":
                clear_fixture_action_cache(fid, "specialists")
                with st.spinner("Refreshing specialists…"):
                    cache["specialists"] = _run_specialists(fid, settings, locale, competition_key)
            elif tab == "report":
                clear_fixture_action_cache(fid, "report")
                cache.pop("report_ok", None)
                with st.spinner("Refreshing report…"):
                    report, ok = _run_report(fid, settings, locale, competition_key)
                    cache["report"] = report
                    cache["report_ok"] = ok
            elif tab == "audit":
                clear_fixture_action_cache(fid, "audit")
                with st.spinner("Refreshing audit…"):
                    cache["audit"] = _run_audit(fid, settings, locale, competition_key)
            st.rerun()

    intel = cache.get("intel")
    if intel is None and st.session_state.get("mc_panel_tab") in ("analyze", None):
        with st.spinner("Loading match intelligence…"):
            intel = _load_intelligence(fid, settings, locale)

    prediction = _cached_prediction(cache)
    if intel:
        render_analyze_summary(
            intel,
            locale,
            prediction=prediction,
            api_configured=settings.api_football_configured,
            fixture=fixture,
        )

    tab_labels = ["Prediction", "Specialists", "Report", "Audit"]
    tab_keys = ["predict", "specialists", "report", "audit"]
    active = st.session_state.get("mc_panel_tab", "analyze")
    if active not in tab_keys:
        active = "predict"
    picked = st.radio(
        "Panel view",
        tab_labels,
        index=tab_keys.index(active),
        horizontal=True,
        key=f"{key_prefix}_tab_pick",
        label_visibility="collapsed",
    )
    st.session_state["mc_panel_tab"] = tab_keys[tab_labels.index(picked)]

    if st.session_state["mc_panel_tab"] == "predict":
        pred_result = cache.get("predict")
        if pred_result is None and has_stored:
            st.caption(gui_t("stored.refresh_help", locale))
        elif pred_result is None:
            st.info("Click **Predict** above to run the prediction pipeline for this match.")
        elif not pred_result.success:
            st.error("Prediction pipeline failed.")
        else:
            specialist_report = None
            for ar in pred_result.agent_results:
                from worldcup_predictor.domain.specialist import MatchSpecialistReport

                if isinstance(ar.data, MatchSpecialistReport):
                    specialist_report = ar.data
                    if intel is not None:
                        intel.specialist_report = ar.data
                    break
            render_professional_prediction_card(
                pred_result.prediction,
                intel,
                locale,
                specialist_report=specialist_report,
                fixture=fixture,
            )
            with st.expander(gui_t("tech.more_prediction", locale), expanded=False):
                render_prediction_card(pred_result.prediction, t, locale)
            render_first_goal_sections(
                pred_result.prediction,
                intel,
                locale,
                specialist_report=specialist_report,
                key_suffix=f"mc_{fid}",
            )
            from worldcup_predictor.ui.odds_display import render_phase36_odds_section

            render_phase36_odds_section(
                intel,
                locale,
                prediction=pred_result.prediction,
                specialist_report=specialist_report,
                fixture_id=fid,
            )
            if intel:
                render_prediction_analysis_details(pred_result.prediction, intel, locale, t)

    elif st.session_state["mc_panel_tab"] == "specialists":
        _render_specialists_tab(cache.get("specialists"), locale)

    elif st.session_state["mc_panel_tab"] == "report":
        _render_report_tab(cache.get("report"), bool(cache.get("report_ok")), t, locale)

    elif st.session_state["mc_panel_tab"] == "audit":
        _render_audit_tab(cache.get("audit"), locale, t)

    st.markdown("**Open in page**")
    nav1, nav2, nav3 = st.columns(3)
    with nav1:
        if st.button("Open in Prediction Page", key=f"{key_prefix}_nav_pred", use_container_width=True):
            st.session_state["gui_page"] = "predict"
            st.session_state["selected_fixture_id"] = fid
            st.session_state["fixture_id"] = fid
            st.session_state["selected_match_name"] = f"{home} vs {away}"
            st.rerun()
    with nav2:
        if st.button("Open in Report Page", key=f"{key_prefix}_nav_rep", use_container_width=True):
            st.session_state["gui_page"] = "report"
            st.session_state["selected_fixture_id"] = fid
            st.session_state["fixture_id"] = fid
            st.session_state["selected_match_name"] = f"{home} vs {away}"
            st.rerun()
    with nav3:
        if st.button("Open in Audit Page", key=f"{key_prefix}_nav_audit", use_container_width=True):
            st.session_state["gui_page"] = "audit"
            st.session_state["selected_fixture_id"] = fid
            st.session_state["fixture_id"] = fid
            st.session_state["selected_match_name"] = f"{home} vs {away}"
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
