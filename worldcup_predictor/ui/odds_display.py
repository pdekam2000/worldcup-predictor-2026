"""Market consensus and odds movement UI — Phase 36."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.ui.gui_i18n import gui_t

_PHASE36_CACHE_KEY = "phase36_odds_cache"


def _agreement_label(level: str | None, locale: Locale) -> str:
    mapping = {
        "high": gui_t("odds.agreement_high", locale),
        "medium": gui_t("odds.agreement_medium", locale),
        "low": gui_t("odds.agreement_low", locale),
    }
    return mapping.get(level or "", gui_t("odds.agreement_unknown", locale))


def _agreement_class(level: str | None) -> str:
    if level == "high":
        return "odds-agreement-high"
    if level == "medium":
        return "odds-agreement-medium"
    if level == "low":
        return "odds-agreement-low"
    return "odds-agreement-unknown"


def _format_model_1x2(selection: str | None, home: str, away: str) -> str:
    if not selection:
        return "—"
    key = selection.lower().replace(" ", "_")
    if key == "home_win":
        return f"{home} Win"
    if key == "away_win":
        return f"{away} Win"
    if key == "draw":
        return "Draw"
    return selection.replace("_", " ").title()


def _fetch_snapshots(fixture_id: int) -> list[dict[str, Any]]:
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository()
        snapshots = repo.fetch_odds_snapshots(fixture_id)
        repo.close()
        return snapshots
    except Exception:
        return []


def resolve_phase36_odds_data(
    intel: Any | None,
    *,
    prediction: Any | None = None,
    specialist_report: MatchSpecialistReport | None = None,
    fixture_id: int | None = None,
) -> dict[str, Any]:
    """Resolve consensus + movement from specialist signals or live computation."""
    fid = fixture_id or (getattr(intel, "fixture_id", None) if intel else None)
    model_selection = None
    home = getattr(intel, "home_team", None) if intel else None
    away = getattr(intel, "away_team", None) if intel else None
    if intel and hasattr(intel, "home_team") and hasattr(intel.home_team, "team_name"):
        home = intel.home_team.team_name
        away = intel.away_team.team_name
    if prediction is not None:
        model_selection = getattr(getattr(prediction, "one_x_two", None), "selection", None)
        if not home:
            parts = (getattr(prediction, "match_name", "") or "").split(" vs ")
            if len(parts) == 2:
                home, away = parts[0], parts[1]

    if specialist_report is None and intel is not None:
        specialist_report = getattr(intel, "specialist_report", None)

    consensus: dict[str, Any] | None = None
    movement: dict[str, Any] | None = None

    if specialist_report:
        cs = specialist_report.signal("market_consensus_agent")
        if cs and cs.status != "unavailable" and cs.signals:
            consensus = dict(cs.signals)
        ms = specialist_report.signal("odds_movement_agent")
        if ms and ms.signals:
            movement = dict(ms.signals)

    if intel is not None:
        supplemental = getattr(intel, "supplemental_sources", None) or {}
        snapshots = _fetch_snapshots(int(fid)) if fid else []
        if consensus is None or not consensus.get("sources_used"):
            try:
                from worldcup_predictor.odds.market_consensus_agent import build_market_consensus

                signal = build_market_consensus(
                    intel,
                    supplemental=supplemental,
                    stored_snapshots=snapshots,
                    model_selection=model_selection,
                )
                if signal.sources_used:
                    consensus = signal.to_dict()
            except Exception:
                pass
        if movement is None:
            try:
                from worldcup_predictor.odds.odds_movement_agent import build_odds_movement

                signal = build_odds_movement(
                    fixture_id=int(fid or 0),
                    supplemental=supplemental,
                    stored_snapshots=snapshots,
                )
                movement = signal.to_dict()
            except Exception:
                pass

    return {
        "consensus": consensus,
        "movement": movement,
        "model_selection": model_selection,
        "home_team": home or "Home",
        "away_team": away or "Away",
        "fixture_id": fid,
    }


def cache_phase36_odds(
    fixture_id: int,
    intel: Any | None,
    *,
    prediction: Any | None = None,
    specialist_report: MatchSpecialistReport | None = None,
) -> dict[str, Any]:
    data = resolve_phase36_odds_data(
        intel,
        prediction=prediction,
        specialist_report=specialist_report,
        fixture_id=fixture_id,
    )
    cache: dict[str, dict[str, Any]] = st.session_state.setdefault(_PHASE36_CACHE_KEY, {})
    cache[str(fixture_id)] = data
    return data


def get_cached_phase36_odds(fixture_id: int) -> dict[str, Any] | None:
    return st.session_state.get(_PHASE36_CACHE_KEY, {}).get(str(fixture_id))


def render_market_agreement_badge_from_data(data: dict[str, Any] | None, locale: Locale) -> None:
    """Compact badge — silent if no data."""
    if not data:
        return
    consensus = data.get("consensus")
    if not consensus or not consensus.get("sources_used"):
        return
    level = consensus.get("model_market_agreement")
    if not level or level == "unknown":
        return
    label = _agreement_label(level, locale)
    css = _agreement_class(level)
    st.markdown(
        f'<span class="odds-market-badge {css}">'
        f'{gui_t("odds.market_agreement", locale)}: {label}</span>',
        unsafe_allow_html=True,
    )


def render_market_agreement_badge(
    specialist_report: MatchSpecialistReport | None,
    locale: Locale,
) -> None:
    if not specialist_report:
        return
    sig = specialist_report.signal("market_consensus_agent")
    if not sig or sig.status == "unavailable":
        return
    render_market_agreement_badge_from_data({"consensus": sig.signals}, locale)


def render_model_market_agreement_card(data: dict[str, Any], locale: Locale) -> None:
    consensus = data.get("consensus") or {}
    home = data.get("home_team", "Home")
    away = data.get("away_team", "Away")
    model_sel = data.get("model_selection")
    favorite = str(consensus.get("market_favorite", "—")).replace("_", " ").title()
    agreement = _agreement_label(consensus.get("model_market_agreement"), locale)
    supports = consensus.get("market_supports_model")
    support_text = (
        gui_t("odds.market_supports_yes", locale)
        if supports is True
        else gui_t("odds.market_supports_no", locale)
        if supports is False
        else "—"
    )
    model_label = _format_model_1x2(model_sel, home, away)

    with st.container(border=True):
        st.markdown(f"#### {gui_t('odds.agreement_card_title', locale)}")
        level = consensus.get("model_market_agreement")
        css = _agreement_class(level)
        st.markdown(
            f'<span class="odds-market-badge {css}" style="font-size:0.85rem;padding:0.25rem 0.75rem;">'
            f'{_agreement_label(level, locale)}</span>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            st.metric(gui_t("odds.market_favorite", locale), favorite)
            st.metric(gui_t("odds.model_prediction", locale), model_label)
        with c2:
            st.metric(gui_t("odds.model_market_agreement", locale), agreement)
            st.metric(gui_t("odds.market_supports_model", locale), support_text)
        st.caption(gui_t("odds.disclaimer", locale))


def render_market_consensus_card_from_data(data: dict[str, Any], locale: Locale) -> None:
    consensus = data.get("consensus")
    with st.container(border=True):
        st.markdown(f"#### {gui_t('odds.consensus_title', locale)}")
        if not consensus or not consensus.get("sources_used"):
            st.info(gui_t("odds.consensus_empty", locale))
            return

        s = consensus
        favorite = str(s.get("market_favorite", "—")).replace("_", " ").title()
        bm_count = int(s.get("bookmaker_count_1x2") or 0)
        bm_disagreement = s.get("bookmaker_disagreement_level") or "—"
        st.caption(
            f"{gui_t('odds.market_favorite', locale)}: **{favorite}** · "
            f"{gui_t('odds.consensus_strength', locale)}: **{s.get('consensus_strength', '—')}/100**"
        )
        meta1, meta2, meta3 = st.columns(3)
        with meta1:
            st.metric(gui_t("odds.bookmakers_used", locale), bm_count or "—")
        with meta2:
            st.metric(gui_t("odds.aggregation_method", locale), gui_t("odds.aggregation_multi", locale))
        with meta3:
            st.metric(gui_t("odds.bookmaker_disagreement_level", locale), bm_disagreement)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Home implied", _pct(s.get("home_implied_probability")))
        with c2:
            st.metric("Draw implied", _pct(s.get("draw_implied_probability")))
        with c3:
            st.metric("Away implied", _pct(s.get("away_implied_probability")))

        c4, c5, c6 = st.columns(3)
        with c4:
            st.metric("Over 2.5", _pct(s.get("over_2_5_probability")))
        with c5:
            st.metric("Under 2.5", _pct(s.get("under_2_5_probability")))
        with c6:
            st.metric(
                gui_t("odds.disagreement", locale),
                bm_disagreement if bm_disagreement != "—" else "—",
            )
        if s.get("disagreement_warning"):
            st.warning(gui_t("odds.disagreement_warning", locale))
        st.caption(gui_t("odds.disclaimer", locale))


def render_odds_movement_card_from_data(data: dict[str, Any], locale: Locale) -> None:
    movement = data.get("movement")
    with st.container(border=True):
        st.markdown(f"#### {gui_t('odds.movement_title', locale)}")
        if not movement:
            st.info(gui_t("odds.movement_empty", locale))
            return

        s = movement
        snap_count = int(s.get("snapshot_count") or 0)
        if snap_count < 2 and not any(
            s.get(k) is not None for k in ("home_movement", "draw_movement", "away_movement")
        ):
            st.info(gui_t("odds.movement_one_snapshot", locale))
            return

        if s.get("warning"):
            st.info(str(s["warning"]))

        st.markdown("**Opening → Latest odds (home / draw / away)**")
        oc1, oc2, oc3 = st.columns(3)
        with oc1:
            st.caption(
                f"Home: {_odds_pair(s.get('opening_home_odds'), s.get('latest_home_odds'))}"
            )
        with oc2:
            st.caption(
                f"Draw: {_odds_pair(s.get('opening_draw_odds'), s.get('latest_draw_odds'))}"
            )
        with oc3:
            st.caption(
                f"Away: {_odds_pair(s.get('opening_away_odds'), s.get('latest_away_odds'))}"
            )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Home move %", _move(s.get("home_movement")))
        with c2:
            st.metric("Draw move %", _move(s.get("draw_movement")))
        with c3:
            st.metric("Away move %", _move(s.get("away_movement")))

        if s.get("strongest_move"):
            st.caption(f"Strongest move: **{str(s['strongest_move']).replace('_', ' ').title()}**")
        if s.get("market_drift"):
            st.caption(str(s["market_drift"]))
        if s.get("steam_move_detected"):
            st.warning(gui_t("odds.steam_move", locale))
        st.caption(gui_t("odds.disclaimer", locale))


def render_phase36_odds_section(
    intel: Any | None,
    locale: Locale,
    *,
    prediction: Any | None = None,
    specialist_report: MatchSpecialistReport | None = None,
    fixture_id: int | None = None,
) -> None:
    """Render all three Phase 36 cards — never raises."""
    try:
        data = resolve_phase36_odds_data(
            intel,
            prediction=prediction,
            specialist_report=specialist_report,
            fixture_id=fixture_id,
        )
        if fixture_id:
            cache_phase36_odds(
                fixture_id,
                intel,
                prediction=prediction,
                specialist_report=specialist_report,
            )
        st.subheader(gui_t("odds.section_title", locale))
        render_model_market_agreement_card(data, locale)
        render_market_consensus_card_from_data(data, locale)
        render_odds_movement_card_from_data(data, locale)
    except Exception:
        st.caption(gui_t("odds.consensus_empty", locale))


def render_market_consensus_card(
    specialist_report: MatchSpecialistReport | None,
    locale: Locale,
) -> None:
    data = {"consensus": None}
    if specialist_report:
        sig = specialist_report.signal("market_consensus_agent")
        if sig and sig.signals:
            data["consensus"] = sig.signals
    render_market_consensus_card_from_data(data, locale)


def render_odds_movement_card(
    specialist_report: MatchSpecialistReport | None,
    locale: Locale,
) -> None:
    data: dict[str, Any] = {"movement": None}
    if specialist_report:
        sig = specialist_report.signal("odds_movement_agent")
        if sig and sig.signals:
            data["movement"] = sig.signals
    render_odds_movement_card_from_data(data, locale)


def render_league_learning_table(profiles: list[Any], locale: Locale) -> None:
    st.subheader(gui_t("learning.league_specific", locale))
    rows: list[dict[str, Any]] = []
    for profile in profiles:
        if profile.evaluated_matches <= 0 and not profile.sample_size_warning:
            continue
        winrates = profile.market_winrates or {}
        rules = "; ".join(profile.recommended_rules[:2]) if profile.recommended_rules else "—"
        rows.append(
            {
                "Competition": profile.competition_name,
                "Evaluated matches": profile.evaluated_matches,
                "Strongest market": profile.strongest_market or "—",
                "Weakest market": profile.weakest_market or "—",
                "1X2 winrate": _pct_rate(winrates.get("1X2")),
                "O/U winrate": _pct_rate(winrates.get("Over/Under 2.5")),
                "Recommended rules": rules,
            }
        )
    if not rows:
        st.info(gui_t("learning.league_no_data", locale))
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    for profile in profiles:
        if profile.sample_size_warning:
            st.warning(f"{profile.competition_name}: {profile.sample_size_warning}")


def _pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _pct_rate(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _move(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "—"


def _odds_pair(opening: Any, latest: Any) -> str:
    if opening is None and latest is None:
        return "—"
    o = f"{float(opening):.2f}" if opening is not None else "—"
    l = f"{float(latest):.2f}" if latest is not None else "—"
    return f"{o} → {l}"
