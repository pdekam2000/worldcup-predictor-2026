"""Developer-only market consensus audit UI."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.market_consensus_audit import audit_market_consensus
from worldcup_predictor.ui.gui_i18n import gui_t


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _odd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def _resolve_intel(fixture_id: int, intel: Any | None) -> Any | None:
    if intel is not None:
        return intel
    cache = st.session_state.get("match_center_action_cache", {}).get(str(fixture_id), {})
    if cache.get("intel"):
        return cache["intel"]
    return None


def _fetch_snapshots(fixture_id: int) -> list[dict[str, Any]]:
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository()
        snapshots = repo.fetch_odds_snapshots(fixture_id)
        repo.close()
        return snapshots
    except Exception:
        return []


def render_market_consensus_debug_panel(
    fixture_id: int,
    locale: Locale,
    *,
    intel: Any | None = None,
) -> None:
    """Render odds audit inside Developer Panel — never raises."""
    st.markdown(f"**{gui_t('dev.odds_audit_title', locale)}**")
    st.caption(gui_t("dev.odds_audit_caption", locale))

    resolved = _resolve_intel(fixture_id, intel)
    if resolved is None:
        if st.button(gui_t("dev.odds_audit_load", locale), key=f"dev_odds_audit_load_{fixture_id}"):
            try:
                from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
                from worldcup_predictor.clients.api_football import ApiFootballClient
                from worldcup_predictor.config.settings import get_settings

                with st.spinner("Loading match intelligence…"):
                    resolved = MatchIntelligenceBuilder(
                        ApiFootballClient(get_settings())
                    ).build_by_fixture_id(fixture_id)
                cache = st.session_state.setdefault("match_center_action_cache", {})
                cache.setdefault(str(fixture_id), {})["intel"] = resolved
            except Exception as exc:
                st.warning(gui_t("dev.odds_audit_unavailable", locale).format(error=str(exc)[:120]))
                return
            st.rerun()
        st.info(gui_t("dev.odds_audit_need_intel", locale))
        return

    try:
        supplemental = getattr(resolved, "supplemental_sources", None) or {}
        snapshots = _fetch_snapshots(fixture_id)
        audit = audit_market_consensus(
            resolved,
            supplemental=supplemental,
            stored_snapshots=snapshots,
        )
    except Exception as exc:
        st.warning(gui_t("dev.odds_audit_unavailable", locale).format(error=str(exc)[:120]))
        return

    st.markdown(f"**{audit.home_team} vs {audit.away_team}** · fixture `{audit.fixture_id}`")

    st.markdown(f"**{gui_t('dev.odds_formula_implied', locale)}**")
    st.code(audit.formula_implied)
    st.markdown(f"**{gui_t('dev.odds_formula_normalize', locale)}**")
    st.code(audit.formula_normalize)
    st.markdown(f"**{gui_t('dev.odds_formula_aggregate', locale)}**")
    st.code(audit.formula_aggregate)

    if audit.notes:
        for note in audit.notes:
            st.caption(f"ℹ️ {note}")

    if audit.bookmaker_rows:
        st.markdown(f"**{gui_t('dev.odds_raw_bookmakers', locale)}**")
        bm_data = []
        for row in audit.bookmaker_rows:
            bm_data.append(
                {
                    "Source": row.source,
                    "Bookmaker": row.bookmaker,
                    "Home (raw)": _odd(row.home_odd),
                    "Draw (raw)": _odd(row.draw_odd),
                    "Away (raw)": _odd(row.away_odd),
                    "Home implied": _pct(row.home_implied_raw),
                    "Draw implied": _pct(row.draw_implied_raw),
                    "Away implied": _pct(row.away_implied_raw),
                    "Raw sum": f"{(row.raw_implied_sum or 0) * 100:.1f}%",
                    "Overround": f"{row.overround_pct:.2f}%" if row.overround_pct is not None else "—",
                    "Used in prod": "✓" if row.used_in_consensus else "",
                }
            )
        st.dataframe(pd.DataFrame(bm_data), use_container_width=True, hide_index=True)

        st.markdown(f"**{gui_t('dev.odds_normalized_per_bm', locale)}**")
        norm_data = []
        for row in audit.bookmaker_rows:
            norm_data.append(
                {
                    "Bookmaker": row.bookmaker,
                    "Home": _pct(row.home_normalized),
                    "Draw": _pct(row.draw_normalized),
                    "Away": _pct(row.away_normalized),
                    "Sum": f"{(row.normalized_sum or 0) * 100:.1f}%",
                    "Used in prod": "✓" if row.used_in_consensus else "",
                }
            )
        st.dataframe(pd.DataFrame(norm_data), use_container_width=True, hide_index=True)
    else:
        st.info(gui_t("dev.odds_no_bookmakers", locale))

    if audit.source_probs_used:
        st.markdown(f"**{gui_t('dev.odds_sources_used', locale)}**")
        src_rows = []
        for name, probs in audit.source_probs_used.items():
            src_rows.append(
                {
                    "Source": name,
                    "Home": _pct(probs.get("home")),
                    "Draw": _pct(probs.get("draw")),
                    "Away": _pct(probs.get("away")),
                    "Sum": f"{sum(probs.values()) * 100:.1f}%",
                }
            )
        st.dataframe(pd.DataFrame(src_rows), use_container_width=True, hide_index=True)

        if audit.source_pre_average and len(audit.source_probs_used) > 1:
            st.markdown(f"**{gui_t('dev.odds_pre_renorm', locale)}**")
            st.markdown(
                f"Home {_pct(audit.source_pre_average.get('home'))} · "
                f"Draw {_pct(audit.source_pre_average.get('draw'))} · "
                f"Away {_pct(audit.source_pre_average.get('away'))}"
            )

    if audit.old_method_1x2_pct or audit.new_method_1x2_pct:
        st.markdown(f"**{gui_t('dev.odds_method_diff', locale)}**")
        diff_rows = [
            {
                "Method": gui_t("dev.odds_old_method", locale),
                "Home": f"{audit.old_method_1x2_pct.get('home', 0):.1f}%",
                "Draw": f"{audit.old_method_1x2_pct.get('draw', 0):.1f}%",
                "Away": f"{audit.old_method_1x2_pct.get('away', 0):.1f}%",
            },
            {
                "Method": gui_t("dev.odds_new_method", locale),
                "Home": f"{audit.new_method_1x2_pct.get('home', 0):.1f}%",
                "Draw": f"{audit.new_method_1x2_pct.get('draw', 0):.1f}%",
                "Away": f"{audit.new_method_1x2_pct.get('away', 0):.1f}%",
            },
            {
                "Method": "Difference (new − old)",
                "Home": f"{audit.method_difference_pct.get('home', 0):+.1f}pp",
                "Draw": f"{audit.method_difference_pct.get('draw', 0):+.1f}pp",
                "Away": f"{audit.method_difference_pct.get('away', 0):+.1f}pp",
            },
        ]
        st.dataframe(pd.DataFrame(diff_rows), use_container_width=True, hide_index=True)

    st.markdown(f"**{gui_t('dev.odds_final_consensus', locale)}**")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Home", f"{audit.final_consensus_pct.get('home', 0):.1f}%")
    with c2:
        st.metric("Draw", f"{audit.final_consensus_pct.get('draw', 0):.1f}%")
    with c3:
        st.metric("Away", f"{audit.final_consensus_pct.get('away', 0):.1f}%")
    with c4:
        st.metric("Sum", f"{audit.final_sum_pct:.1f}%" if audit.final_sum_pct else "—")

    prod = audit.production_signal
    if prod:
        st.caption(
            f"Production signal: Home {_pct(prod.get('home_implied_probability'))} · "
            f"Draw {_pct(prod.get('draw_implied_probability'))} · "
            f"Away {_pct(prod.get('away_implied_probability'))} · "
            f"bookmakers={prod.get('bookmaker_count_1x2')} · "
            f"aggregation={prod.get('aggregation_method')} · "
            f"disagreement={prod.get('bookmaker_disagreement_level')}"
        )

    with st.expander(gui_t("dev.odds_audit_json", locale), expanded=False):
        st.json(audit.to_dict())
