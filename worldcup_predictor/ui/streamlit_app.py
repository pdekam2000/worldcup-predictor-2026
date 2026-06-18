"""
WorldCup Predictor Pro 2026 — Professional Streamlit Dashboard.

Analytical evaluation only — not betting advice. API keys are never displayed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.competition.competition_service import CompetitionService
from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY
from worldcup_predictor.config.settings import Locale, get_settings
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.i18n.translator import get_translator
from worldcup_predictor.orchestration.audit_pipeline import AuditPipeline
from worldcup_predictor.orchestration.pipeline import UpcomingPipeline
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.orchestration.specialists_pipeline import SpecialistsPipeline
from worldcup_predictor.reasoning.openai_reasoning_service import OpenAIReasoningService
from worldcup_predictor.schedule.competition_schedule import build_schedule_service

REPORT_PATHS = {
    "backtest": ROOT / "reports" / "backtests" / "backtest_summary.json",
    "calibration": ROOT / "reports" / "calibration" / "calibration_summary.json",
    "import": ROOT / "reports" / "imports" / "import_summary.json",
    "data_quality": ROOT / "reports" / "data_quality" / "data_quality_summary.json",
}

DISCLAIMER = (
    "Analytical evaluation only — not betting advice. "
    "Historical performance and model outputs do not guarantee future results. "
    "Use **analysis readiness** scores to gauge data quality, not profit expectations."
)

PAGES = [
    "Home",
    "Upcoming Matches",
    "Predict Match",
    "Specialist Analysis",
    "Audit Report",
    "Professional Report",
    "Schedule & Groups",
    "Backtest Reports",
    "Calibration Reports",
    "Import Reports",
    "Data Quality Reports",
    "Settings / API Status",
]


def main() -> None:
    st.set_page_config(
        page_title="WorldCup Predictor Pro 2026",
        page_icon="⚽",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_session_state()
    _render_sidebar()
    page = st.session_state["page"]
    handlers = {
        "Home": page_home,
        "Upcoming Matches": page_upcoming,
        "Predict Match": page_predict,
        "Specialist Analysis": page_specialists,
        "Audit Report": page_audit,
        "Professional Report": page_professional_report,
        "Schedule & Groups": page_schedule,
        "Backtest Reports": page_backtest,
        "Calibration Reports": page_calibration,
        "Import Reports": page_import,
        "Data Quality Reports": page_data_quality,
        "Settings / API Status": page_settings,
    }
    handlers[page]()
    st.sidebar.markdown("---")
    st.sidebar.caption(DISCLAIMER.replace("**", ""))


def _init_session_state() -> None:
    if "locale" not in st.session_state:
        st.session_state["locale"] = get_settings().default_locale
    if "page" not in st.session_state:
        st.session_state["page"] = "Home"
    if "fixture_id" not in st.session_state:
        st.session_state["fixture_id"] = 2026001
    if "competition" not in st.session_state:
        st.session_state["competition"] = DEFAULT_COMPETITION_KEY


def _competition_key() -> str:
    return st.session_state.get("competition", DEFAULT_COMPETITION_KEY)


def _render_competition_info() -> None:
    service = CompetitionService()
    comp = service.get_competition(_competition_key())
    features = service.get_supported_features(comp.key)
    st.caption(
        f"**{comp.display_name}** ({comp.key}) — "
        f"{features['competition_type']} | "
        f"groups={features['supports_groups']}, "
        f"table={features['supports_table']}, "
        f"knockout={features['supports_knockout']}"
    )


def _render_sidebar() -> None:
    st.sidebar.title("WorldCup Predictor Pro 2026")
    st.sidebar.markdown("**Professional Analysis Dashboard**")
    st.session_state["page"] = st.sidebar.radio(
        "Navigation",
        PAGES,
        index=PAGES.index(st.session_state["page"]),
        label_visibility="collapsed",
    )
    st.session_state["locale"] = st.sidebar.selectbox(
        "Locale",
        options=["en", "de", "fa"],
        index=["en", "de", "fa"].index(st.session_state["locale"]),
        format_func=lambda code: {"en": "English", "de": "Deutsch", "fa": "فارسی"}[code],
    )
    comp_service = CompetitionService()
    comp_options = comp_service.list_competitions()
    comp_keys = [c.key for c in comp_options]
    comp_labels = {c.key: f"{c.display_name} ({c.key})" for c in comp_options}
    current = st.session_state.get("competition", DEFAULT_COMPETITION_KEY)
    if current not in comp_keys:
        current = DEFAULT_COMPETITION_KEY
    st.session_state["competition"] = st.sidebar.selectbox(
        "Competition",
        comp_keys,
        index=comp_keys.index(current),
        format_func=lambda key: comp_labels[key],
    )


def _locale() -> Locale:
    return st.session_state["locale"]  # type: ignore[return-value]


def _translator():
    return get_translator(_locale())


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _api_status_badge(configured: bool) -> str:
    return "✅ Configured" if configured else "❌ Not configured"


def _readiness_label(prediction: MatchPrediction) -> str:
    if prediction.risk_level == "high" or prediction.no_bet_flag:
        return "Watch only — insufficient analysis readiness"
    if prediction.confidence_score >= 60:
        return "Analysis ready (moderate confidence)"
    return "Limited analysis readiness"


def _render_safety_banner(prediction: MatchPrediction | None = None) -> None:
    if prediction is None:
        st.info(DISCLAIMER)
        return
    label = _readiness_label(prediction)
    if prediction.risk_level == "high" or prediction.no_bet_flag:
        st.warning(f"**{label}** — high risk / no-bet flag active. Not a betting recommendation.")
    else:
        st.info(f"**{label}**. {DISCLAIMER}")


def page_home() -> None:
    st.title("Home")
    settings = get_settings()
    t = _translator()

    st.markdown(f"### {t.t('app.title')}")
    st.markdown(DISCLAIMER)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("API-Football", _api_status_badge(settings.api_football_configured).split()[1])
    with col2:
        st.metric("OpenAI", _api_status_badge(settings.openai_configured).split()[1])
    with col3:
        st.metric("Weather API", _api_status_badge(settings.weather_configured).split()[1])

    st.subheader("Project Status")
    st.markdown(
        "- **Phases 1–10**: CLI pipelines, backtesting, calibration, import, data quality\n"
        "- **Phase 11**: This dashboard (read-only analysis + report viewer)\n"
        "- **Demo fixture**: `2026001` (USA vs Mexico) works without API key"
    )

    st.subheader("Latest Reports")
    report_rows = []
    for name, path in REPORT_PATHS.items():
        report_rows.append(
            {
                "Report": name.replace("_", " ").title(),
                "Path": str(path.relative_to(ROOT)) if path.exists() else str(path.relative_to(ROOT)),
                "Available": "Yes" if path.exists() else "No",
                "Modified": _mtime(path),
            }
        )
    st.dataframe(pd.DataFrame(report_rows), use_container_width=True, hide_index=True)

    st.subheader("Quick Actions")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("View Upcoming Matches"):
            st.session_state["page"] = "Upcoming Matches"
            st.rerun()
    with c2:
        if st.button("Run Demo Prediction (2026001)"):
            st.session_state["page"] = "Predict Match"
            st.session_state["fixture_id"] = 2026001
            st.rerun()
    with c3:
        if st.button("Open Settings"):
            st.session_state["page"] = "Settings / API Status"
            st.rerun()


def page_upcoming() -> None:
    st.title("Upcoming Matches")
    _render_safety_banner()
    _render_competition_info()
    limit = st.slider("Fixture limit", min_value=1, max_value=20, value=5)
    locale = _locale()
    settings = get_settings()

    with st.spinner("Loading upcoming fixtures..."):
        result = UpcomingPipeline(
            settings, locale=locale, competition_key=_competition_key()
        ).run(limit=limit)

    if not result.success:
        st.error("Failed to load upcoming fixtures.")
        for agent_result in result.agent_results:
            if not agent_result.success:
                st.caption(f"[{agent_result.agent_name}] {agent_result.message}")
        return

    rows = []
    for fixture, placeholder in zip(result.fixtures.fixtures, result.predictions):
        rows.append(
            {
                "Fixture ID": fixture.id,
                "Match": fixture.display_match,
                "Kickoff (UTC)": fixture.kickoff_utc.strftime("%Y-%m-%d %H:%M"),
                "Venue": fixture.venue,
                "Stage": fixture.stage,
                "Source": fixture.source,
                "Confidence": placeholder.confidence_score,
                "Confidence Level": placeholder.confidence_level.value,
                "Model Ready": placeholder.model_ready,
            }
        )

    if not rows:
        st.warning("No upcoming fixtures found.")
        return

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"Data source: {result.fixtures.source} | Placeholder: {result.fixtures.is_placeholder}")


def _render_prediction_cards(prediction: MatchPrediction) -> None:
    locale = _locale()
    t = _translator()

    st.subheader(prediction.match_name)
    if prediction.kickoff_utc:
        st.caption(f"{t.t('cli.fixture.kickoff')}: {prediction.kickoff_utc:%Y-%m-%d %H:%M} UTC")
    st.caption(f"{t.t('cli.inspect.fixture_id')}: {prediction.fixture_id}")

    _render_safety_banner(prediction)

    c1, c2, c3, c4 = st.columns(4)
    ou_label = (
        prediction.over_under.label.get(locale)
        if prediction.over_under.label
        else prediction.over_under.selection
    )
    x2_label = (
        prediction.one_x_two.label.get(locale)
        if prediction.one_x_two.label
        else prediction.one_x_two.selection
    )
    with c1:
        st.metric("1X2", x2_label)
    with c2:
        st.metric("O/U 2.5", ou_label)
    with c3:
        st.metric("Halftime Goals (est.)", f"{prediction.halftime.estimated_total_goals:.1f}")
    with c4:
        st.metric("Confidence", f"{prediction.confidence_score:.0f}/100")

    c5, c6, c7 = st.columns(3)
    with c5:
        st.metric("First Goal Team", prediction.first_goal.team)
    with c6:
        player = prediction.first_goal.player or t.t("cli.inspect.none")
        st.metric("First Goal Player", player)
    with c7:
        no_bet = t.t("cli.predict.no_bet_true") if prediction.no_bet_flag else t.t("cli.predict.no_bet_false")
        st.metric("No-Bet Flag", no_bet)

    if prediction.first_goal.minute_range:
        st.caption(f"{t.t('cli.predict.first_goal_minute')}: {prediction.first_goal.minute_range}")

    if prediction.explanation:
        st.markdown(f"**{t.t('cli.predict.explanation')}**")
        st.write(prediction.explanation.get(locale))

    if prediction.missing_data_warnings:
        st.warning(prediction.missing_data_warnings.get(locale))

    if prediction.disclaimer:
        st.markdown(f"*{prediction.disclaimer.get(locale)}*")


def page_predict() -> None:
    st.title("Predict Match")
    _render_competition_info()
    fixture_id = st.number_input(
        "Fixture ID",
        min_value=1,
        value=int(st.session_state.get("fixture_id", 2026001)),
        step=1,
    )
    st.session_state["fixture_id"] = int(fixture_id)

    if st.button("Run Prediction Pipeline", type="primary"):
        with st.spinner("Running prediction pipeline..."):
            result = PredictPipeline(
                get_settings(), locale=_locale(), competition_key=_competition_key()
            ).run(int(fixture_id))
        st.session_state["last_prediction"] = result

    result = st.session_state.get("last_prediction")
    if result is None:
        st.info("Enter a fixture ID and run the prediction pipeline. Try demo fixture **2026001**.")
        return

    if not result.success:
        st.error("Prediction pipeline failed.")
        for agent_result in result.agent_results:
            if not agent_result.success:
                st.caption(f"[{agent_result.agent_name}] {agent_result.message}")
        return

    _render_prediction_cards(result.prediction)


def page_specialists() -> None:
    st.title("Specialist Analysis")
    _render_safety_banner()
    _render_competition_info()
    fixture_id = st.number_input(
        "Fixture ID",
        min_value=1,
        value=int(st.session_state.get("fixture_id", 2026001)),
        step=1,
        key="specialists_fixture_id",
    )

    if st.button("Run Specialist Agents", type="primary"):
        with st.spinner("Running specialist analysis..."):
            result = SpecialistsPipeline(
                get_settings(), locale=_locale(), competition_key=_competition_key()
            ).run(int(fixture_id))
        st.session_state["last_specialists"] = result

    result = st.session_state.get("last_specialists")
    if result is None:
        st.info("Run specialist analysis for a fixture. Demo: **2026001**.")
        return

    if not result.success:
        st.error("Specialist pipeline failed.")
        return

    report = result.report
    st.caption(f"Source: {report.source} | Aggregated score: {report.aggregated_signal_score}")

    for name, signal in report.signals.items():
        with st.expander(f"{name} — {signal.status.upper()}", expanded=False):
            st.markdown(f"**Domain:** {signal.domain}")
            st.markdown(f"**Status:** `{signal.status}`")
            if signal.impact_score is not None:
                st.metric("Impact Score", signal.impact_score)
            if signal.signals:
                st.markdown("**Key Signals**")
                st.json(signal.signals)
            if signal.warnings:
                st.markdown("**Warnings**")
                for warning in signal.warnings:
                    st.warning(warning)
            if signal.missing_data:
                st.markdown("**Missing Data**")
                for item in signal.missing_data:
                    st.caption(f"• {item}")
            if signal.notes:
                st.caption(signal.notes)


def page_audit() -> None:
    st.title("Audit Report")
    _render_competition_info()
    fixture_id = st.number_input(
        "Fixture ID",
        min_value=1,
        value=int(st.session_state.get("fixture_id", 2026001)),
        step=1,
        key="audit_fixture_id",
    )

    if st.button("Run Audit Pipeline", type="primary"):
        with st.spinner("Running weighted decision audit..."):
            result = AuditPipeline(
                get_settings(), locale=_locale(), competition_key=_competition_key()
            ).run(int(fixture_id))
        st.session_state["last_audit"] = result

    result = st.session_state.get("last_audit")
    if result is None:
        st.info("Run an audit for factor trace and decision transparency. Demo: **2026001**.")
        return

    if not result.success:
        st.error("Audit pipeline failed.")
        return

    prediction = result.prediction
    audit = prediction.audit_report
    _render_prediction_cards(prediction)

    if audit is None:
        st.warning("No audit report attached to prediction.")
        return

    st.markdown("---")
    st.subheader("Factor Contributions")

    rows = []
    for contrib in audit.all_contributions:
        rows.append(
            {
                "Factor": contrib.factor_name,
                "Direction": contrib.direction,
                "Weight %": contrib.weight_pct,
                "Score": contrib.score,
                "Contribution": contrib.contribution,
                "Note": contrib.note,
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if audit.conflicts:
        st.subheader("Conflicts")
        for conflict in audit.conflicts:
            severity_icon = {"low": "🟡", "medium": "🟠", "high": "🔴"}.get(conflict.severity, "⚪")
            st.markdown(f"{severity_icon} **{conflict.severity.upper()}** — {conflict.description}")

    if audit.limitations:
        st.subheader("Data Limitations")
        for lim in audit.limitations:
            st.caption(f"• **{lim.field}**: {lim.impact}")

    if audit.trace:
        trace = audit.trace
        st.subheader("Final Decision Trace")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Baseline Confidence", f"{trace.baseline_confidence:.0f}")
        with c2:
            st.metric("Final Confidence", f"{trace.final_confidence:.0f}")

        if trace.watch_only:
            st.warning(f"**Watch only** — {trace.analytical_edge_note or 'High risk / low confidence.'}")

        if trace.confidence_caps_applied:
            st.markdown("**Confidence Caps Applied**")
            for cap in trace.confidence_caps_applied:
                st.caption(f"• {cap}")

        if trace.confidence_reductions:
            st.markdown("**Confidence Reductions**")
            for item in trace.confidence_reductions:
                st.caption(f"• {item}")

        if trace.no_bet_reasons:
            st.markdown("**No-Bet Reasons**")
            for reason in trace.no_bet_reasons:
                st.caption(f"• {reason}")

    if audit.market_disagreement_warnings:
        st.subheader("Market Disagreement Warnings")
        for warning in audit.market_disagreement_warnings:
            st.warning(warning)


def page_professional_report() -> None:
    st.title("Professional Report")
    _render_safety_banner()
    _render_competition_info()
    locale = _locale()
    t = get_translator(locale)

    fixture_id = st.number_input(
        "Fixture ID",
        min_value=1,
        value=int(st.session_state.get("fixture_id", 2026001)),
        step=1,
        key="report_fixture_id",
    )
    st.session_state["fixture_id"] = int(fixture_id)

    if st.button("Generate Professional Report", type="primary"):
        with st.spinner("Building narrative report (OpenAI or local rules)…"):
            service = OpenAIReasoningService(get_settings())
            report, ok = service.generate_for_fixture(
                int(fixture_id), locale=locale, competition=_competition_key()
            )
        st.session_state["last_professional_report"] = report if ok else None
        if not ok:
            st.error(t.t("cli.report.pipeline_failed"))

    report = st.session_state.get("last_professional_report")
    if report is None:
        st.info("Generate a professional narrative report. Demo: **2026001**.")
        return

    if report.watch_only:
        st.warning(f"**Watch only** — {t.t('audit.watch_only_message')}")

    st.caption(f"{t.t('cli.report.source')}: {report.source} | {report.match_name}")

    st.subheader(t.t("cli.report.executive_summary"))
    st.write(report.executive_summary)

    st.subheader(t.t("cli.report.prediction_summary"))
    st.json(report.prediction_summary)

    if report.audit_highlights:
        st.subheader(t.t("cli.report.audit_highlights"))
        for item in report.audit_highlights:
            st.markdown(f"- {item}")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader(t.t("cli.report.key_factors"))
        for item in report.key_factors:
            st.markdown(f"- {item}")
    with col2:
        st.subheader(t.t("cli.report.risk_notes"))
        for item in report.risk_notes:
            st.markdown(f"- {item}")

    st.subheader(t.t("cli.report.tactical_context"))
    st.write(report.tactical_context)

    st.subheader(t.t("cli.report.data_limitations"))
    for item in report.data_limitations:
        st.caption(f"• {item}")

    st.subheader(t.t("cli.report.market_analysis"))
    st.info(report.market_analysis_information_only)

    st.subheader(t.t("cli.report.final_view"))
    st.write(report.final_analytical_view)

    if report.safety_warnings:
        st.subheader(t.t("cli.report.safety_warnings"))
        for item in report.safety_warnings:
            st.warning(item)

    st.markdown("---")
    st.caption(report.disclaimer)

    st.subheader("Copy-friendly export")
    st.text_area(
        "Report text",
        value=report.copy_friendly_text(),
        height=400,
        label_visibility="collapsed",
    )


def page_schedule() -> None:
    st.title("Schedule & Groups")
    _render_safety_banner()
    _render_competition_info()
    service = build_schedule_service(get_settings(), competition_key=_competition_key())

    st.subheader("Next 5 Matches")
    upcoming = service.get_upcoming_matches(5)
    if upcoming:
        rows = [
            {
                "Fixture ID": f.fixture_id,
                "Date": f.kickoff_time.strftime("%Y-%m-%d %H:%M"),
                "Match": f"{f.home_team} vs {f.away_team}",
                "Group": f.group,
                "Round": f.round,
                "Venue": f.venue,
                "Source": f.source,
            }
            for f in upcoming
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.warning("No upcoming schedule entries.")

    st.subheader("Group Tables")
    overview = service.get_tournament_overview()
    for group_name in sorted(overview.groups.keys()):
        group = overview.groups[group_name]
        with st.expander(group_name, expanded=group_name == "Group A"):
            if group.disclaimer:
                st.caption(group.disclaimer)
            standings_rows = [
                {
                    "Rank": s.rank,
                    "Team": s.team_name,
                    "P": s.played,
                    "W": s.won,
                    "D": s.drawn,
                    "L": s.lost,
                    "GF": s.goals_for,
                    "GA": s.goals_against,
                    "GD": s.goal_difference,
                    "Pts": s.points,
                    "Status": s.qualification_status,
                }
                for s in group.standings
            ]
            st.dataframe(pd.DataFrame(standings_rows), use_container_width=True, hide_index=True)

    st.subheader("Team Schedule Search")
    team = st.text_input("Team name", value="USA")
    if team.strip():
        matches = service.get_team_schedule(team.strip())
        if matches:
            team_rows = [
                {
                    "Date": m.kickoff_time.strftime("%Y-%m-%d %H:%M"),
                    "Match": f"{m.home_team} vs {m.away_team}",
                    "Group": m.group,
                    "Venue": m.venue,
                }
                for m in matches
            ]
            st.dataframe(pd.DataFrame(team_rows), use_container_width=True, hide_index=True)
        else:
            st.info(f"No matches found for team: {team}")


def page_backtest() -> None:
    st.title("Backtest Reports")
    _render_safety_banner()
    _render_competition_info()
    data = _load_json(REPORT_PATHS["backtest"])
    if data is None:
        st.warning(
            f"No backtest report found at `{REPORT_PATHS['backtest'].relative_to(ROOT)}`. "
            "Run: `python main.py backtest --csv data/historical/worldcup_sample.csv`"
        )
        return

    metrics = data.get("metrics", {})
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Matches", metrics.get("total_matches", 0))
    with c2:
        st.metric("1X2 Accuracy", _pct(metrics.get("one_x_two_accuracy")))
    with c3:
        st.metric("O/U 2.5 Accuracy", _pct(metrics.get("over_under_2_5_accuracy")))
    with c4:
        st.metric("Avg Confidence", f"{metrics.get('average_confidence', 0):.1f}")

    c5, c6 = st.columns(2)
    with c5:
        st.metric("Strongest Market", metrics.get("strongest_market", "n/a"))
    with c6:
        st.metric("Weakest Market", metrics.get("weakest_market", "n/a"))

    buckets = metrics.get("confidence_buckets", [])
    bucket_df = pd.DataFrame(
        [
            {
                "Bucket": b["label"],
                "Count": b["count"],
                "1X2 Accuracy": b.get("one_x_two_accuracy"),
                "O/U Accuracy": b.get("over_under_accuracy"),
            }
            for b in buckets
            if b.get("count", 0) > 0
        ]
    )
    if not bucket_df.empty:
        st.subheader("Confidence Bucket Chart")
        fig = px.bar(
            bucket_df,
            x="Bucket",
            y=["1X2 Accuracy", "O/U Accuracy"],
            barmode="group",
            title="Accuracy by Confidence Bucket",
            labels={"value": "Accuracy", "variable": "Market"},
        )
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    if metrics.get("data_limitations"):
        st.subheader("Data Limitations")
        for item in metrics["data_limitations"]:
            st.caption(f"• {item}")

    st.caption(f"CSV: {data.get('csv_path')} | Demo: {data.get('is_demo_data')}")


def page_calibration() -> None:
    st.title("Calibration Reports")
    _render_safety_banner()
    _render_competition_info()
    data = _load_json(REPORT_PATHS["calibration"])
    if data is None:
        st.warning(
            f"No calibration report at `{REPORT_PATHS['calibration'].relative_to(ROOT)}`. "
            "Run: `python main.py calibrate --csv data/historical/worldcup_sample.csv`"
        )
        return

    st.metric("Sample Size", data.get("sample_size", 0))
    if data.get("is_demo_data"):
        st.warning("Demo CSV — calibration is illustrative only.")

    current = data.get("current_weights", {})
    recommended = data.get("recommended_weights", {})
    weight_rows = [
        {
            "Factor": key,
            "Current": current.get(key, 0),
            "Recommended": recommended.get(key, 0),
            "Delta": recommended.get(key, 0) - current.get(key, 0),
        }
        for key in sorted(current.keys())
    ]
    st.subheader("Factor Weights (Current vs Recommended)")
    df = pd.DataFrame(weight_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    if not df.empty:
        fig = px.bar(
            df.melt(id_vars=["Factor"], value_vars=["Current", "Recommended"], var_name="Set", value_name="Weight"),
            x="Factor",
            y="Weight",
            color="Set",
            barmode="group",
            title="Weight Comparison",
        )
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Thresholds")
    cur_th = data.get("current_thresholds", {})
    rec_th = data.get("recommended_thresholds", {})
    th_rows = [
        {"Threshold": k, "Current": cur_th.get(k), "Recommended": rec_th.get(k)}
        for k in sorted(cur_th.keys())
    ]
    st.dataframe(pd.DataFrame(th_rows), use_container_width=True, hide_index=True)

    overfitting = data.get("overfitting_warnings") or []
    wt_warnings = (data.get("weight_tuning") or {}).get("warnings") or []
    all_warnings = list(dict.fromkeys(overfitting + wt_warnings))
    if all_warnings:
        st.subheader("Overfitting Warnings")
        for warning in all_warnings:
            st.warning(warning)


def page_import() -> None:
    st.title("Import Reports")
    _render_safety_banner()
    _render_competition_info()
    data = _load_json(REPORT_PATHS["import"])
    if data is None:
        st.warning(
            f"No import report at `{REPORT_PATHS['import'].relative_to(ROOT)}`. "
            "Run: `python main.py import-history --worldcup --seasons 2018 2022` (requires API key)"
        )
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Imported", data.get("imported_count", 0))
    with c2:
        st.metric("Skipped", data.get("skipped_count", 0))
    with c3:
        st.metric("Success", "Yes" if data.get("success") else "No")

    st.markdown(f"**Source:** {data.get('source')}")
    st.markdown(f"**Message:** {data.get('message')}")

    if data.get("api_errors"):
        st.subheader("API Errors")
        for err in data["api_errors"]:
            st.error(err)

    if data.get("data_quality_notes"):
        st.subheader("Data Quality Notes")
        for note in data["data_quality_notes"]:
            st.caption(f"• {note}")

    export = data.get("export")
    if export:
        st.subheader("Export")
        st.json(export)


def page_data_quality() -> None:
    st.title("Data Quality Reports")
    _render_safety_banner()
    data = _load_json(REPORT_PATHS["data_quality"])
    if data is None:
        st.warning(
            f"No data quality report at `{REPORT_PATHS['data_quality'].relative_to(ROOT)}`. "
            "Run: `python main.py validate-csv --csv data/historical/worldcup_sample.csv`"
        )
        return

    health = data.get("health") or {}
    score = health.get("score", 0)
    st.metric("Dataset Health Score", f"{score:.0f}/100", delta=health.get("label"))

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Rows", data.get("row_count", 0))
    with c2:
        st.metric("Duplicate fixture_id", data.get("duplicate_fixture_id_count", 0))
    with c3:
        st.metric("Safe for Calibration", "Yes" if data.get("safe_for_calibration") else "No")

    if data.get("warnings"):
        st.subheader("Warnings")
        for warning in data["warnings"]:
            st.warning(warning)

    issues = data.get("row_issues") or []
    if issues:
        st.subheader("Row Issues (sample)")
        st.dataframe(pd.DataFrame(issues), use_container_width=True, hide_index=True)

    if data.get("repair_suggestions"):
        st.subheader("Repair Suggestions (manual only)")
        for suggestion in data["repair_suggestions"]:
            st.caption(f"• {suggestion}")

    st.caption(data.get("disclaimer", ""))


def page_settings() -> None:
    st.title("Settings / API Status")
    settings = get_settings()

    st.markdown(
        "API keys are read from environment / `.env`. "
        "**Secret values are never displayed** in this dashboard."
    )

    st.subheader("API Configuration")
    api_rows = [
        {"Service": "API-Football (API_FOOTBALL_KEY)", "Status": _api_status_badge(settings.api_football_configured)},
        {"Service": "OpenAI (OPENAI_API_KEY)", "Status": _api_status_badge(settings.openai_configured)},
        {"Service": "Weather (WEATHER_API_KEY)", "Status": _api_status_badge(settings.weather_configured)},
    ]
    st.dataframe(pd.DataFrame(api_rows), use_container_width=True, hide_index=True)

    st.subheader("Application Settings")
    st.markdown(
        f"- **Default locale:** `{settings.default_locale}`\n"
        f"- **OpenAI model:** `{settings.openai_model}`\n"
        f"- **Upcoming fixture limit:** `{settings.upcoming_fixture_limit}`\n"
        f"- **API cache TTL:** `{settings.api_cache_ttl_seconds}s`"
    )

    st.subheader("Directories")
    dirs = [
        ("Cache directory", Path(settings.api_cache_dir)),
        ("Backtest reports", ROOT / "reports" / "backtests"),
        ("Calibration reports", ROOT / "reports" / "calibration"),
        ("Import reports", ROOT / "reports" / "imports"),
        ("Data quality reports", ROOT / "reports" / "data_quality"),
        ("Historical data", ROOT / "data" / "historical"),
    ]
    for label, path in dirs:
        exists = path.exists()
        st.markdown(f"- **{label}:** `{path}` {'✅' if exists else '⚠️ missing'}")

    st.info(DISCLAIMER)


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _mtime(path: Path) -> str:
    if not path.exists():
        return "—"
    from datetime import datetime

    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    main()
