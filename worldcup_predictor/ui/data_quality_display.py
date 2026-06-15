"""Data quality breakdown + API source inspector UI — Phase 35A."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale, get_settings
from worldcup_predictor.data_quality.transparency import DISPLAY_LABELS, KICKOFF_NOTE, LIVE_WEIGHTS
from worldcup_predictor.providers.registry import ProviderRegistry
from worldcup_predictor.ui.gui_i18n import gui_t


def _status_icon(ok: bool | None) -> str:
    if ok is True:
        return "✅"
    if ok is False:
        return "❌"
    return "➖"


def _endpoint_status(endpoints: list[Any], needle: str) -> tuple[str, str]:
    for ep in endpoints:
        if needle in ep.endpoint:
            if ep.error:
                return "error", ep.error
            if ep.loaded:
                return "loaded", ""
            return "empty", ep.error or "empty response"
    return "not_called", ""


def render_data_quality_breakdown(report: Any, locale: Locale) -> None:
    dq = getattr(report, "data_quality", None)
    if dq is None:
        st.caption(gui_t("dq.unavailable", locale))
        return

    total = dq.breakdown_total or 0
    st.markdown(f"### {gui_t('card.data_quality', locale)} **{total}/100**")

    if dq.reason_text:
        st.info(dq.reason_text)

    phase = getattr(dq, "match_phase", "pre_match") or "pre_match"
    p1, p2, p3 = st.columns(3)
    with p1:
        st.metric(gui_t("dq.pre_match", locale), f"{getattr(dq, 'pre_match_data_quality', total)}/100")
    with p2:
        st.metric(gui_t("dq.live", locale), f"{getattr(dq, 'live_data_quality', total)}/100")
    with p3:
        st.metric(gui_t("dq.post_match", locale), f"{getattr(dq, 'post_match_data_quality', total)}/100")

    st.caption(getattr(dq, "kickoff_note", None) or KICKOFF_NOTE)

    component_max = getattr(dq, "component_max", None) or {}
    breakdown = dq.breakdown or {}
    rows: list[str] = []

    ordered_keys = [
        "fixture_identity",
        "team_ids",
        "recent_form",
        "standings_context",
        "odds",
        "stats",
        "lineups",
        "injuries",
        "weather",
        "referee",
        "fixture_events",
        "match_statistics_live",
        "supplemental_xg",
        "supplemental_player_stats",
        "supplemental_squad",
        "supplemental_odds",
        "supplemental_weather",
    ]

    for key in ordered_keys:
        max_pts = component_max.get(key)
        if max_pts is None:
            continue
        pts = breakdown.get(key, 0)
        label = DISPLAY_LABELS.get(key, key.replace("_", " ").title())
        if key in LIVE_WEIGHTS and phase == "pre_match" and pts == 0:
            rows.append(f"- **{label}:** _{gui_t('dq.not_expected', locale)}_")
        else:
            rows.append(f"- **{label}:** {pts}/{max_pts}")

    if rows:
        st.markdown("**Breakdown:**")
        st.markdown("\n".join(rows))


def render_api_inspector_panel(report: Any, locale: Locale) -> None:
    st.subheader(gui_t("dq.api_inspector", locale))
    settings = get_settings()
    registry = ProviderRegistry(settings)
    inspection = getattr(report, "api_inspection", None)
    endpoints = inspection.endpoints if inspection else []

    st.markdown(f"#### {gui_t('dq.source_api_sports', locale)}")
    api_ok = settings.api_football_configured
    st.markdown(f"{_status_icon(api_ok)} **Configured:** {'yes' if api_ok else 'no'}")

    checks = [
        ("Fixtures", _endpoint_loaded(endpoints, "fixtures") or bool(getattr(report, "fixture", None))),
        ("Standings", bool(getattr(report, "standings_context", None) and report.standings_context.get("available"))),
        ("Odds", bool(report.odds and report.odds.available)),
        (
            "Lineups",
            bool(report.lineups and report.lineups.get("available")),
        ),
        (
            "Injuries",
            "injuries" not in (report.missing_data or [])
            and bool(
                (report.home_team.injuries and report.home_team.injuries.players)
                or (report.away_team.injuries and report.away_team.injuries.players)
            ),
        ),
        ("Team statistics", _team_stats_loaded(report)),
        ("Recent form", bool(getattr(report, "home_recent_fixtures", None) or getattr(report, "away_recent_fixtures", None))),
    ]
    for label, ok in checks:
        state = "loaded" if ok else "empty"
        if label == "Injuries" and "injuries" in (report.missing_data or []):
            state = "empty"
        st.markdown(f"- **{label}:** {state}")

    st.markdown(f"#### {gui_t('dq.source_rapid_xg', locale)}")
    xg_client = registry.rapid_xg_statistics
    rapid_xg = (getattr(report, "supplemental_sources", None) or {}).get("rapid_xg_statistics") or {}
    st.markdown(f"- **Configured:** {'yes' if xg_client.is_configured else 'no'}")
    connected = bool(rapid_xg.get("endpoints_loaded")) or _endpoint_loaded(endpoints, "rapid_xg/")
    st.markdown(f"- **Connected:** {'yes' if connected else 'no'}")
    xg_status, xg_err = _rapid_xg_endpoint_summary(endpoints, rapid_xg)
    st.markdown(f"- **Endpoint:** {xg_status}" + (f" — _{xg_err}_" if xg_err else ""))
    has_xg = bool(rapid_xg.get("xg") or rapid_xg.get("npxg") or rapid_xg.get("fixture_detail"))
    st.markdown(f"- **xG found:** {'yes' if has_xg else 'no'}")

    st.markdown(f"#### {gui_t('dq.source_rapid_football', locale)}")
    rfs = registry.rapid_football_stats
    rapid = (getattr(report, "supplemental_sources", None) or {}).get("rapid_football_stats") or {}
    st.markdown(f"- **Configured:** {'yes' if rfs.is_configured else 'no'}")
    st.markdown(f"- **Connected:** {'yes' if rapid.get('endpoints_loaded') else 'no'}")
    st.markdown(f"- **Player stats found:** {'yes' if rapid.get('player_statistics') else 'no'}")
    st.markdown(f"- **Squad found:** {'yes' if rapid.get('team_squad') else 'no'}")
    st.markdown(
        f"- **Odds found:** {'yes' if rapid.get('prematch_odds') or rapid.get('live_odds') or rapid.get('historical_odds') else 'no'}"
    )
    if rapid.get("endpoints_called"):
        st.caption(
            f"Endpoints: **{rapid.get('endpoints_loaded', 0)}/{rapid.get('endpoints_called', 0)}** returned data"
        )

    st.markdown(f"#### {gui_t('dq.source_rapid_weather', locale)}")
    rw = registry.rapid_open_weather
    rapid_weather = (getattr(report, "supplemental_sources", None) or {}).get("rapid_open_weather") or {}
    weather = getattr(report, "weather", None) or {}
    weather_found = bool(weather.get("available")) or bool(rapid_weather.get("weather"))
    st.markdown(f"- **Configured:** {'yes' if rw.is_configured else 'no'}")
    st.markdown(f"- **Weather found:** {'yes' if weather_found else 'no'}")
    if weather.get("available"):
        src = weather.get("source") or weather.get("provider") or "unknown"
        st.caption(f"Primary weather source: **{src}**")

    if endpoints:
        with st.expander(gui_t("dq.endpoint_diagnostics", locale), expanded=False):
            import pandas as pd

            ep_rows = [
                {
                    "Endpoint": ep.endpoint,
                    "Status": getattr(ep, "status", "unknown"),
                    "Loaded": ep.loaded,
                    "Count": ep.response_count,
                    "Source": ep.source,
                    "Error": ep.error or "",
                }
                for ep in endpoints
            ]
            st.dataframe(pd.DataFrame(ep_rows), use_container_width=True, hide_index=True)


def _rapid_xg_endpoint_summary(endpoints: list[Any], rapid_xg: dict[str, Any]) -> tuple[str, str]:
    for ep in endpoints:
        if "rapid_xg" in ep.endpoint or ep.endpoint.startswith("rapid/"):
            if ep.error:
                return "error", ep.error
            if ep.loaded:
                return "loaded", ""
            return "empty", ep.error or ""
    if rapid_xg.get("endpoints_called"):
        if rapid_xg.get("endpoints_loaded"):
            return "loaded", ""
        return "empty", "no matching fixture"
    return "not_called", ""


def _endpoint_loaded(endpoints: list, needle: str) -> bool:
    for ep in endpoints:
        if needle in ep.endpoint and ep.loaded:
            return True
    return False


def _team_stats_loaded(report: Any) -> bool:
    home = getattr(report, "home_team", None)
    away = getattr(report, "away_team", None)
    return bool(home and home.statistics) or bool(away and away.statistics)
