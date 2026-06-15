"""Sharp Money & Market Intelligence V2 UI — Phase 40."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.ui.gui_i18n import gui_t


def render_sharp_money_intelligence_v2(
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> None:
    """Render sharp money intelligence card — never raises."""
    try:
        data = _resolve_data(report, specialist_report)
        if not data:
            return
        _render_card(data, locale)
    except Exception:
        st.caption(gui_t("market_v2.unavailable", locale))


def _resolve_data(report: Any, specialist_report: MatchSpecialistReport | None) -> dict[str, Any] | None:
    if specialist_report:
        sig = specialist_report.signal("sharp_money_intelligence_agent")
        if sig and sig.signals:
            return dict(sig.signals)
    if report is None:
        return None
    try:
        from worldcup_predictor.odds.sharp_money_intelligence_engine import build_sharp_money_intelligence

        return build_sharp_money_intelligence(report).to_dict()
    except Exception:
        return None


def _render_card(data: dict[str, Any], locale: Locale) -> None:
    impact = data.get("prediction_impact") or {}
    tracking = data.get("odds_tracking") or {}

    with st.container(border=True):
        st.markdown(f"#### {gui_t('market_v2.title', locale)}")
        if data.get("summary"):
            st.caption(str(data["summary"]))

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(gui_t("market_v2.sharp_score", locale), f"{data.get('sharp_money_score', 0):.0f}/100")
            st.caption(gui_t("market_v2.band", locale).format(band=data.get("sharp_money_band", "—")))
        with c2:
            st.metric(gui_t("market_v2.consensus", locale), f"{data.get('consensus_strength', 0):.0f}/100")
            st.caption(gui_t("market_v2.disagreement", locale).format(level=data.get("disagreement_level", "—")))
        with c3:
            st.metric(gui_t("market_v2.confidence", locale), f"{data.get('market_confidence', 0):.0f}%")

        rlm = data.get("reverse_line_movement")
        steam = data.get("steam_move_detected")
        st.caption(
            f"{gui_t('market_v2.rlm', locale)}: {'Yes' if rlm else 'No'}"
            + (f" ({data.get('reverse_line_confidence', 0):.0f}%)" if rlm else "")
            + f" · {gui_t('market_v2.steam', locale)}: {'Yes' if steam else 'No'}"
        )

        if data.get("movement_summary"):
            st.caption(f"**{gui_t('market_v2.movement', locale)}** — {data['movement_summary']}")

        home = tracking.get("home") or {}
        away = tracking.get("away") or {}
        over = tracking.get("over_2_5") or {}
        under = tracking.get("under_2_5") or {}
        st.caption(
            f"1X2: H {home.get('movement_class', '—')} · D {(tracking.get('draw') or {}).get('movement_class', '—')} · "
            f"A {away.get('movement_class', '—')} · O/U: Over {over.get('movement_class', '—')} · Under {under.get('movement_class', '—')}"
        )

        st.caption(
            f"O/U bias — Over {data.get('over_market_bias', 50):.0f} · Under {data.get('under_market_bias', 50):.0f} · "
            f"Goals conf {data.get('goals_market_confidence', 0):.0f}%"
        )

        flags = data.get("risk_flags") or []
        if flags:
            st.markdown(f"**{gui_t('market_v2.risk_flags', locale)}**")
            st.caption(" · ".join(flags))

        if any(impact.get(k) for k in ("home_adjustment", "away_adjustment", "over25_adjustment")):
            st.markdown(f"**{gui_t('market_v2.prediction_impact', locale)}**")
            st.caption(
                f"Home {impact.get('home_adjustment', 0):+.1f} · "
                f"Away {impact.get('away_adjustment', 0):+.1f} · "
                f"Draw {impact.get('draw_adjustment', 0):+.1f} · "
                f"Over 2.5 {impact.get('over25_adjustment', 0):+.1f} · "
                f"Under 2.5 {impact.get('under25_adjustment', 0):+.1f}"
            )
        st.caption(gui_t("market_v2.disclaimer", locale))
