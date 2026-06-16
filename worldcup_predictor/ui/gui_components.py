"""Reusable polished UI components for the Phase 14 GUI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.i18n.translator import Translator
from worldcup_predictor.ui.fixture_display import format_group_stage, format_kickoff_times, render_fixture_meta_grid, render_match_card_shell
from worldcup_predictor.ui.international_match_card import render_international_match_card
from worldcup_predictor.ui.adaptive_confidence_display import render_prediction_adaptive_panel
from worldcup_predictor.ui.data_quality_display import (
    render_api_inspector_panel,
    render_data_quality_breakdown,
)
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.halftime_display import halftime_scoreline_outcomes, halftime_total_outcomes
from worldcup_predictor.ui.readiness import ReadinessLabel, analysis_readiness

READINESS_COLORS = {
    "Strong Ready": "#22c55e",
    "Good Analysis": "#4ade80",
    "Moderate Analysis": "#f59e0b",
    "Low Confidence": "#fb923c",
    "Not Ready": "#ef4444",
    # legacy API health labels
    "Ready": "#22c55e",
    "Partial": "#f59e0b",
}


from worldcup_predictor.ui.dashboard_theme import inject_dashboard_theme


def inject_theme() -> None:
    inject_dashboard_theme()
    st.markdown(
        """
<style>
/* Component-specific overrides (dark dashboard base in dashboard_theme.py) */

.creator-card {
    background: linear-gradient(145deg, rgba(255,255,255,0.08) 0%, rgba(22,163,74,0.08) 100%);
    border: 1px solid rgba(22,163,74,0.25);
    border-radius: 18px;
    padding: 1.15rem 1rem;
    margin-top: 1.5rem;
    text-align: center;
    box-shadow: 0 8px 24px rgba(0,0,0,0.2);
}
.creator-avatar {
    width: 52px; height: 52px;
    margin: 0 auto 0.55rem;
    border-radius: 50%;
    background: linear-gradient(135deg, #16A34A, #22C55E);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem;
    box-shadow: 0 4px 14px rgba(22,163,74,0.35);
}
.creator-label { font-size: 0.68rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }
.creator-name { font-size: 1rem; font-weight: 800; color: #4ADE80; margin: 0.2rem 0; letter-spacing: -0.01em; }
.creator-role { font-size: 0.72rem; color: #CBD5E1; line-height: 1.4; }
.creator-links {
    display: flex;
    justify-content: center;
    gap: 0.65rem;
    margin: 0.65rem 0 0.45rem;
}
.creator-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: rgba(255,255,255,0.08);
    color: #E2E8F0;
    text-decoration: none;
    transition: background 0.15s, color 0.15s, transform 0.15s;
}
.creator-icon:hover {
    background: rgba(22,163,74,0.25);
    color: #4ADE80;
    transform: translateY(-1px);
}
.creator-copy { font-size: 0.62rem; color: #64748B; }

/* ── Developer sidebar section (Phase 33A) ── */
section[data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 1px solid #1F8F5F !important;
    border-radius: 14px !important;
    background: rgba(14, 27, 46, 0.55) !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    color: #36D27D !important;
    font-weight: 700 !important;
    font-size: 0.88rem !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary * {
    color: #36D27D !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button {
    background: #0E1B2E !important;
    color: #FFFFFF !important;
    border: 1px solid #1F8F5F !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.25) !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button:hover {
    background: #152744 !important;
    color: #FFFFFF !important;
    border-color: #36D27D !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button[kind="primary"] {
    background: #1F8F5F !important;
    color: #FFFFFF !important;
    border-color: #36D27D !important;
    box-shadow: 0 4px 14px rgba(31,143,95,0.35) !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button p,
section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button span,
section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button div {
    color: #FFFFFF !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button svg {
    fill: #FFFFFF !important;
    color: #FFFFFF !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] .stCaption,
section[data-testid="stSidebar"] [data-testid="stExpander"] p {
    color: #B8C7E0 !important;
}

/* ── Settings / API status cards ── */
.settings-section-card {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 18px;
    padding: 1.15rem 1.25rem;
    margin-bottom: 1rem;
    box-shadow: 0 4px 18px rgba(15,23,42,0.05);
}
.settings-section-title {
    font-size: 1rem;
    font-weight: 700;
    color: #0F172A;
    margin-bottom: 0.75rem;
}
.api-status-card {
    background: #F8FAFC;
    border: 1px solid #E5E7EB;
    border-radius: 14px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.55rem;
}
.api-status-card-green { border-left: 4px solid #16A34A; }
.api-status-card-orange { border-left: 4px solid #EA580C; }
.api-status-card-red { border-left: 4px solid #DC2626; }
.api-status-name { font-weight: 700; color: #0F172A; font-size: 0.92rem; }
.api-status-pill { font-weight: 700; font-size: 0.82rem; margin-top: 0.2rem; }
.api-status-pill-green { color: #16A34A; }
.api-status-pill-orange { color: #EA580C; }
.api-status-pill-red { color: #DC2626; }
.api-status-detail { color: #64748B; font-size: 0.78rem; margin-top: 0.25rem; }

/* ── Stored prediction summary (Phase 34A) ── */
.stored-prediction-summary {
    background: #ECFDF5;
    border: 1px solid #86EFAC;
    border-radius: 16px;
    padding: 0.95rem 1.1rem;
    margin: 0.65rem 0 0.85rem;
    box-shadow: 0 4px 16px rgba(22,163,74,0.08);
}
.stored-prediction-compact {
    padding: 0.75rem 0.95rem;
    margin: 0.45rem 0 0.65rem;
}
.stored-pred-header {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 0.35rem 0.75rem;
    margin-bottom: 0.75rem;
}
.stored-pred-title {
    font-weight: 700;
    color: #065F46;
    font-size: 0.95rem;
}
.stored-pred-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
}
.stored-pred-badge {
    background: #DCFCE7;
    color: #166534;
    border: 1px solid #86EFAC;
    border-radius: 999px;
    padding: 0.15rem 0.55rem;
    font-size: 0.72rem;
    font-weight: 700;
}
.stored-pred-updated {
    color: #64748B;
    font-size: 0.75rem;
    font-weight: 600;
}
.stored-pred-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.65rem;
}
.stored-pred-cell {
    background: rgba(255,255,255,0.72);
    border: 1px solid #BBF7D0;
    border-radius: 12px;
    padding: 0.55rem 0.65rem;
}
.stored-pred-label {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748B;
}
.stored-pred-value {
    font-size: 0.92rem;
    font-weight: 700;
    color: #0F172A;
    margin-top: 0.15rem;
}
.stored-pred-conf {
    font-size: 0.68rem;
    color: #64748B;
    margin-top: 0.2rem;
}
.stored-pred-version {
    margin-top: 0.65rem;
    font-size: 0.78rem;
    font-weight: 600;
    color: #047857;
}
.stored-pred-quality {
    margin-top: 0.55rem;
    font-size: 0.78rem;
    font-weight: 600;
    color: #065F46;
}
.stored-pred-warning {
    margin-top: 0.55rem;
    font-size: 0.76rem;
    color: #B45309;
    font-weight: 600;
}
.stored-pred-footer {
    margin-top: 0.65rem;
    font-size: 0.72rem;
    color: #64748B;
    line-height: 1.45;
}
.stored-pred-eval-row {
    display: grid;
    grid-template-columns: 0.9fr 1.4fr 1.4fr;
    gap: 0.35rem;
    padding: 0.35rem 0;
    border-bottom: 1px solid #BBF7D0;
    font-size: 0.82rem;
}
.stored-pred-market { font-weight: 700; color: #065F46; }
.stored-pred-predicted { font-weight: 600; color: #0F172A; }
.stored-pred-actual { color: #64748B; }
.premium-action-row .stButton > button[kind="primary"].stored-predict-refresh {
    background: #16A34A !important;
    border-color: #15803D !important;
}

/* ── Phase 36 odds badges & cards ── */
.odds-market-badge {
    display: inline-block;
    border-radius: 999px;
    padding: 0.15rem 0.55rem;
    font-size: 0.68rem;
    font-weight: 700;
    margin: 0.25rem 0 0.35rem;
}
.odds-agreement-high { background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; }
.odds-agreement-medium { background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; }
.odds-agreement-low { background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }
.odds-agreement-unknown { background: #F1F5F9; color: #64748B; border: 1px solid #CBD5E1; }
.odds-consensus-card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.65rem;
}
.odds-consensus-row { font-size: 0.88rem; color: #0F172A; }

/* ── Official hero banner image ── */
.hero-banner-container {
    margin-bottom: 24px;
}
.hero-banner-container [data-testid="stImage"] {
    border-radius: 20px;
    overflow: hidden;
    box-shadow: 0 12px 40px rgba(15,23,42,0.10);
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
}
.hero-banner-container [data-testid="stImage"] img {
    width: 100%;
    max-height: 280px;
    min-height: 220px;
    object-fit: contain;
    object-position: center;
    display: block;
    border-radius: 20px;
}
.hero-banner-fallback {
    width: 100%;
    min-height: 220px;
    max-height: 280px;
    border-radius: 20px;
    background: linear-gradient(135deg, #ffffff 0%, #f0fdf4 50%, #ecfdf5 100%);
    border: 1px solid #E5E7EB;
    box-shadow: 0 12px 40px rgba(15,23,42,0.08);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 24px;
    padding: 2rem;
}
.hero-banner-fallback-text { text-align: center; }
.hero-banner-fallback-text h2 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 800;
    color: #0F172A;
}
.hero-banner-fallback-text p {
    color: #16A34A;
    font-weight: 700;
    margin: 0.5rem 0;
}

/* ── Legacy promo banner (fallback) ── */
.promo-banner {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 1.5rem;
    background: linear-gradient(135deg, #ffffff 0%, #f0fdf4 45%, #ecfdf5 100%);
    border: 1px solid #DCFCE7;
    border-radius: 24px;
    padding: 1.5rem 1.75rem;
    margin-bottom: 1.25rem;
    box-shadow: 0 8px 32px rgba(15,23,42,0.06);
    align-items: center;
}
.promo-visual {
    background: linear-gradient(160deg, #16A34A 0%, #065F46 100%);
    border-radius: 20px;
    min-height: 140px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #fff;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.15);
}
.promo-trophy { font-size: 2.5rem; }
.promo-confetti { font-size: 0.85rem; opacity: 0.9; margin-top: 0.35rem; }
.promo-content h2 {
    margin: 0;
    font-size: 1.45rem;
    font-weight: 800;
    color: #0F172A;
    letter-spacing: -0.02em;
}
.promo-winrate {
    font-size: 1.15rem;
    font-weight: 800;
    color: #16A34A;
    margin: 0.35rem 0 0.65rem;
}
.promo-bullets {
    margin: 0 0 0.75rem;
    padding-left: 1.1rem;
    color: #475569;
    font-size: 0.92rem;
    line-height: 1.6;
}
.promo-pill {
    display: inline-block;
    background: #0F172A;
    color: #F8FAFC;
    padding: 0.35rem 0.85rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
}

/* ── Page headers ── */
.page-header h1 {
    margin: 0;
    font-size: 1.85rem;
    font-weight: 800;
    color: #0F172A;
    letter-spacing: -0.03em;
}
.page-header p {
    margin: 0.25rem 0 0;
    color: #64748B;
    font-size: 0.95rem;
}
.main-disclaimer {
    background: #FFF7ED;
    border: 1px solid #FED7AA;
    color: #9A3412;
    border-radius: 12px;
    padding: 0.65rem 1rem;
    font-size: 0.82rem;
    margin: 1rem 0;
}

/* ── Premium performance cards ── */
.premium-stat-card {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 18px;
    padding: 1.15rem 1rem;
    box-shadow: 0 6px 24px rgba(15,23,42,0.06);
    margin-bottom: 0.75rem;
    text-align: center;
    transition: transform 0.15s, box-shadow 0.15s;
}
.premium-stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 32px rgba(15,23,42,0.09);
}
.premium-stat-icon { font-size: 1.35rem; margin-bottom: 0.35rem; }
.premium-stat-value {
    font-size: 1.65rem;
    font-weight: 800;
    color: #0F172A;
    line-height: 1.1;
    letter-spacing: -0.02em;
}
.premium-stat-label {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748B;
    margin-top: 0.35rem;
}
.premium-stat-desc {
    font-size: 0.68rem;
    color: #94A3B8;
    margin-top: 0.2rem;
    line-height: 1.35;
}

/* ── Adaptive / learning confidence ── */
.learning-confidence-card {
    background: linear-gradient(135deg, #F0FDF4 0%, #FFFFFF 100%);
    border: 1px solid #BBF7D0;
    border-radius: 16px;
    padding: 1rem 1.15rem;
    margin: 0.75rem 0 0.5rem;
    box-shadow: 0 4px 18px rgba(22,163,74,0.08);
}
.learning-confidence-title {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748B;
}
.learning-confidence-value {
    font-size: 1.75rem;
    font-weight: 800;
    line-height: 1.1;
    margin: 0.25rem 0 0.35rem;
}
.learning-confidence-reason {
    font-size: 0.88rem;
    color: #0F172A;
    line-height: 1.45;
}
.learning-confidence-meta {
    font-size: 0.75rem;
    color: #64748B;
    margin-top: 0.35rem;
}
.model-experience-card { min-height: 120px; }

/* ── Stat / summary cards (legacy) ── */
.stat-card {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 16px;
    padding: 1rem 1.1rem;
    box-shadow: 0 4px 16px rgba(15,23,42,0.04);
    margin-bottom: 0.5rem;
}
.stat-card .stat-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748B;
    font-weight: 600;
}
.stat-card .stat-value {
    font-size: 1.35rem;
    font-weight: 800;
    color: #0F172A;
    margin-top: 0.25rem;
}

/* ── White match cards ── */
.main [data-testid="stVerticalBlockBorderWrapper"] {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 22px !important;
    box-shadow: 0 8px 32px rgba(15,23,42,0.07) !important;
    padding: 0.25rem 0.15rem !important;
}
.imc-today-marker + div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 2px solid #EAB308 !important;
    box-shadow:
        0 0 0 4px rgba(234,179,8,0.12),
        0 12px 40px rgba(234,179,8,0.18) !important;
}

.match-card {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-left: 4px solid #16A34A;
    border-radius: 18px;
    padding: 1.1rem 1.25rem;
    margin: 0.5rem 0 1rem;
    box-shadow: 0 4px 20px rgba(15,23,42,0.05);
}
.match-card .teams { font-size: 1.25rem; font-weight: 800; color: #0F172A; }
.match-card .meta { color: #64748B; }

.match-action-panel {
    background: #F8FAFC;
    border: 1px solid #E5E7EB;
    border-radius: 16px;
    padding: 1rem;
    margin: 0.25rem 0 1.25rem;
}

/* ── Match card hero ── */
.imc-hero {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 1.25rem;
    padding: 0.75rem 0.5rem 1rem;
}
.imc-team { text-align: center; }
.imc-team-home { text-align: left; }
.imc-team-away { text-align: right; }
.imc-flag {
    min-height: 3.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 0.55rem;
}
.imc-team-home .imc-flag { justify-content: flex-start; }
.imc-team-away .imc-flag { justify-content: flex-end; }
.imc-flag-img {
    width: 4rem;
    max-height: 3rem;
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(15,23,42,0.12);
    object-fit: cover;
}
.imc-flag-initials {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2.5rem;
    height: 1.85rem;
    padding: 0 0.4rem;
    font-size: 0.68rem;
    font-weight: 700;
    color: #475569;
    background: #F8FAFC;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
}
.imc-team-name {
    font-size: 1.2rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.02em;
    line-height: 1.25;
}
.imc-center-vs .imc-center-main,
.imc-center-score .imc-center-main {
    font-size: 1.05rem;
    font-weight: 700;
    color: #64748B;
    text-align: center;
}
.imc-center-kickoff {
    text-align: center;
    font-size: 28px;
    font-weight: 800;
    color: #0F172A;
    line-height: 1.05;
    letter-spacing: -0.03em;
}
.imc-center-kickoff-label {
    text-align: center;
    font-size: 0.72rem;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    margin-top: 0.15rem;
}
.imc-center-score.live .imc-center-main { color: #EA580C; font-size: 1.85rem; }
.imc-center-score.finished .imc-center-main { color: #0F172A; font-size: 1.85rem; }
.imc-center-sub { text-align: center; font-size: 0.82rem; color: #64748B; margin-top: 0.2rem; }
.imc-center-today .imc-today-kickoff { color: #CA8A04; font-size: 28px; }
.imc-center-today .imc-center-main { color: #16A34A; }
.imc-center-today .imc-center-kickoff { color: #CA8A04; }

.imc-badges { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.5rem 0 0.85rem; }
.imc-badge {
    display: inline-block;
    padding: 0.28rem 0.75rem;
    border-radius: 999px;
    font-size: 0.74rem;
    font-weight: 700;
    border: 1px solid #E5E7EB;
    background: #F8FAFC;
    color: #475569;
}
.imc-badge-scheduled { color: #16A34A; background: #F0FDF4; border-color: #BBF7D0; }
.imc-badge-live { color: #EA580C; background: #FFF7ED; border-color: #FED7AA; }
.imc-badge-finished { color: #64748B; background: #F1F5F9; border-color: #CBD5E1; }
.imc-badge-today {
    color: #A16207;
    background: linear-gradient(135deg, #FEF9C3, #FDE68A);
    border-color: #FACC15;
    font-weight: 800;
    box-shadow: 0 2px 8px rgba(234,179,8,0.25);
}
.imc-badge-stage { color: #4338CA; background: #EEF2FF; border-color: #C7D2FE; }

.imc-metric-label { font-size: 0.82rem; color: #64748B; margin-bottom: 0.35rem; font-weight: 500; }
.imc-progress-track {
    height: 10px;
    background: #E5E7EB;
    border-radius: 999px;
    overflow: hidden;
}
.imc-progress-fill {
    height: 100%;
    border-radius: 999px;
    transform-origin: left center;
    animation: imcBarGrow 0.85s ease-out forwards;
}
@keyframes imcBarGrow {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
}

/* ── Premium search ── */
.premium-search {
    position: relative;
    margin-bottom: 0.35rem;
}
.premium-search::before {
    content: "🔍";
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    z-index: 2;
    font-size: 0.95rem;
    pointer-events: none;
}
.premium-search .stTextInput input {
    border-radius: 14px !important;
    border: 1px solid #E5E7EB !important;
    box-shadow: 0 2px 12px rgba(15,23,42,0.06) !important;
    padding: 0.65rem 1rem 0.65rem 2.5rem !important;
    background: #FFFFFF !important;
    color: #0F172A !important;
    font-weight: 500 !important;
}
.premium-search .stTextInput input:focus {
    border-color: #16A34A !important;
    box-shadow: 0 0 0 3px rgba(22,163,74,0.15) !important;
}

/* ── Sticky match toolbar ── */
.sticky-match-toolbar {
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(248,250,252,0.95);
    backdrop-filter: blur(8px);
    padding: 0.65rem 0 0.85rem;
    margin-bottom: 0.75rem;
    border-bottom: 1px solid #E5E7EB;
}

/* ── Premium action buttons ── */
.premium-action-row .stButton > button {
    background: #FFFFFF !important;
    color: #0F172A !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    box-shadow: 0 2px 10px rgba(15,23,42,0.06) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s !important;
    padding: 0.5rem 0.35rem !important;
}
.premium-action-row .stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 18px rgba(15,23,42,0.10) !important;
    border-color: #CBD5E1 !important;
    color: #0F172A !important;
}
.premium-action-row .stButton > button[kind="primary"] {
    background: #16A34A !important;
    color: #FFFFFF !important;
    border: none !important;
    box-shadow: 0 4px 14px rgba(22,163,74,0.30) !important;
}
.premium-action-row .stButton > button[kind="primary"]:hover {
    background: #15803D !important;
    color: #FFFFFF !important;
    box-shadow: 0 6px 20px rgba(22,163,74,0.35) !important;
}

.filter-pills .stRadio > div { flex-wrap: wrap; gap: 0.45rem; }
.filter-pills .stRadio label {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 999px !important;
    padding: 0.4rem 0.85rem !important;
    font-weight: 600 !important;
    color: #475569 !important;
    font-size: 0.82rem !important;
}
.filter-pills .stRadio label[data-checked="true"],
.filter-pills .stRadio div[role="radiogroup"] label:has(input:checked) {
    background: #16A34A !important;
    border-color: #16A34A !important;
    color: #FFFFFF !important;
}

.back-to-top {
    position: fixed;
    bottom: 1.25rem;
    right: 1.25rem;
    z-index: 9999;
    padding: 0.55rem 0.9rem;
    background: #16A34A;
    color: #fff !important;
    font-weight: 800;
    font-size: 0.85rem;
    text-decoration: none !important;
    border-radius: 999px;
    box-shadow: 0 6px 24px rgba(22,163,74,0.35);
}
.back-to-top:hover { background: #15803D; color: #fff !important; }

.hero-banner, .page-header-light { margin-bottom: 1rem; }

div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 16px;
    padding: 0.75rem;
    box-shadow: 0 2px 12px rgba(15,23,42,0.04);
}
div[data-testid="stMetric"] label { color: #64748B !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #0F172A !important; }

.stButton > button[kind="primary"] {
    background: #16A34A;
    border: none;
    font-weight: 700;
    border-radius: 12px;
    color: #fff;
}
.stButton > button[kind="primary"]:hover { background: #15803D; }
.stButton > button[kind="secondary"] {
    border-radius: 12px;
    border-color: #E5E7EB;
    color: #0F172A;
    background: #FFFFFF;
    box-shadow: 0 2px 8px rgba(15,23,42,0.04);
}
.main .stTextInput input {
    border-radius: 14px;
    border-color: #E5E7EB;
    color: #0F172A;
}

.status-pill { border-radius: 999px; font-size: 0.78rem; font-weight: 700; }
.phase48-badge { display: inline-block; padding: 0.35rem 0.75rem; margin: 0.15rem 0; }

/* Group browser + match row styling */
.group-card-header { font-size: 1.05rem; margin-bottom: 0.25rem; }
.group-card-teams { font-size: 0.82rem; color: #64748b; margin-bottom: 0.35rem; line-height: 1.4; }
.match-row { padding: 0.35rem 0.5rem; border-radius: 8px; margin: 0.25rem 0; }
.match-row-finished { background: rgba(239, 68, 68, 0.06); opacity: 0.92; border-left: 3px solid #ef4444; }
.match-row-upcoming { background: rgba(59, 130, 246, 0.05); border-left: 3px solid #3b82f6; }
.match-row-live { background: rgba(249, 115, 22, 0.08); border-left: 3px solid #f97316; }
.match-badge { display: inline-block; padding: 0.2rem 0.55rem; border-radius: 999px; font-size: 0.72rem; font-weight: 700; margin-right: 0.35rem; }
.match-badge-finished { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
.match-badge-upcoming { background: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe; }
.match-badge-live { background: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; }
.match-result-text { font-weight: 600; color: #991b1b; font-size: 0.85rem; }
.match-status-struck { color: #94a3b8; font-size: 0.78rem; }
.match-row-divider { border: none; border-top: 1px solid #e2e8f0; margin: 0.35rem 0; }
.pred-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 0.75rem;
    margin-top: 0.75rem;
}
.pred-tile, .api-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 16px;
    color: #0F172A;
}

@media (max-width: 768px) {
    .promo-banner { grid-template-columns: 1fr; }
    .imc-hero { grid-template-columns: 1fr; text-align: center; }
    .imc-team-home, .imc-team-away { text-align: center; }
    .imc-team-home .imc-flag, .imc-team-away .imc-flag { justify-content: center; }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="page-header"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def render_readiness_badge(
    label: ReadinessLabel | str,
    locale: Locale,
    progress: float,
    *,
    reason: str | None = None,
) -> None:
    color = READINESS_COLORS.get(label, "#64748b")
    localized = {
        "Strong Ready": gui_t("readiness.strong_ready", locale),
        "Good Analysis": gui_t("readiness.good_analysis", locale),
        "Moderate Analysis": gui_t("readiness.moderate_analysis", locale),
        "Low Confidence": gui_t("readiness.low_confidence", locale),
        "Not Ready": gui_t("readiness.not_ready", locale),
        "Ready": gui_t("readiness.ready", locale),
        "Partial": gui_t("readiness.partial", locale),
    }.get(label, label)
    st.markdown(
        f'<span class="status-pill" style="background:{color}22;color:{color};border:1px solid {color}55;">'
        f"● {localized}</span>",
        unsafe_allow_html=True,
    )
    st.progress(min(max(progress, 0.0), 1.0))
    if reason:
        st.caption(reason)


def format_standings_context(gh: dict, ga: dict, locale: Locale) -> str:
    """Format rank/points without None placeholders."""
    parts: list[str] = []
    hr, ar = gh.get("rank"), ga.get("rank")
    hp, ap = gh.get("points"), ga.get("points")
    if hr is not None or ar is not None:
        left = str(hr) if hr is not None else gui_t("standings.unavailable", locale)
        right = str(ar) if ar is not None else gui_t("standings.unavailable", locale)
        parts.append(f"{gui_t('standings.position', locale)}: {left} / {right}")
    if hp is not None or ap is not None:
        left = str(hp) if hp is not None else gui_t("standings.unavailable", locale)
        right = str(ap) if ap is not None else gui_t("standings.unavailable", locale)
        parts.append(f"{gui_t('standings.points', locale)}: {left} / {right}")
    return " · ".join(parts)


def format_source_display(source: str | None, locale: Locale) -> str:
    if source in ("live", "cache", "Live API"):
        return gui_t("source.live_api", locale)
    if source in ("placeholder", "Demo"):
        return gui_t("source.demo", locale)
    if source and "placeholder" not in str(source).lower():
        return gui_t("source.live_api", locale)
    return gui_t("source.demo", locale)


def format_kickoff_times(kickoff: datetime | None) -> tuple[str, str]:
    from worldcup_predictor.ui.fixture_display import format_kickoff_times as _fmt

    return _fmt(kickoff)


def _status_class(status: str) -> str:
    code = (status or "").upper()
    if code in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}:
        return "Live"
    if code in {"FT", "AET", "PEN"}:
        return "Finished"
    return "Upcoming"


def render_fixture_status_badge(status: str, locale: Locale) -> None:
    colors = {
        "Upcoming": "#22c55e",
        "Live": "#f97316",
        "Finished": "#ef4444",
    }
    labels = {
        "Upcoming": gui_t("status.upcoming", locale),
        "Live": gui_t("status.live", locale),
        "Finished": gui_t("status.finished", locale),
    }
    color = colors.get(status, "#94a3b8")
    label = labels.get(status, status)
    st.markdown(
        f'<span class="status-pill" style="background:{color}22;color:{color};'
        f'border:1px solid {color}55;">● {label}</span>',
        unsafe_allow_html=True,
    )


def render_source_badge(source: str | None, locale: Locale) -> None:
    label = format_source_display(source, locale)
    color = "#22c55e" if label == gui_t("source.live_api", locale) else "#94a3b8"
    st.markdown(
        f'<span class="status-pill" style="background:{color}22;color:{color};'
        f'border:1px solid {color}55;">Source: {label}</span>',
        unsafe_allow_html=True,
    )


def render_live_match_card(
    fixture: TournamentFixture,
    locale: Locale,
    *,
    show_fixture_id: bool = False,
    prediction_status: str | None = None,
    confidence: float | None = None,
    data_quality: float | None = None,
    tournament_context: dict[str, Any] | None = None,
    key_prefix: str | None = None,
) -> None:
    prefix = key_prefix or f"live_{fixture.fixture_id}"
    render_international_match_card(
        fixture,
        locale,
        variant="live",
        confidence=confidence,
        data_quality=data_quality,
        prediction_subtitle=prediction_status,
        tournament_context=tournament_context,
        key_prefix=prefix,
    )
    if show_fixture_id:
        from worldcup_predictor.ui.international_match_card import render_developer_panel

        render_developer_panel(fixture, locale=locale, source=fixture.source)


def render_finished_match_card(
    fixture: TournamentFixture,
    locale: Locale,
    *,
    prediction_label: str | None = None,
    accuracy_key: str | None = None,
    winner: str | None = None,
    evaluation: Any | None = None,
    stored_record: Any | None = None,
    show_fixture_id: bool = False,
    confidence: float | None = None,
    tournament_context: dict[str, Any] | None = None,
) -> None:
    if evaluation is not None:
        acc_label = gui_t("accuracy.correct" if evaluation.one_x_two_correct else "accuracy.incorrect", locale)
    elif stored_record is not None:
        acc_label = gui_t("accuracy.pending_match", locale)
    else:
        acc_label = gui_t(f"accuracy.{accuracy_key}", locale) if accuracy_key else None

    footer_parts = []
    if evaluation is not None:
        footer_parts.append(
            f"Prediction: {evaluation.predicted_1x2.replace('_', ' ')} · Actual: {evaluation.actual_1x2.replace('_', ' ')}"
        )
    elif stored_record is not None:
        footer_parts.append(f"Stored: {stored_record.predicted_1x2.replace('_', ' ')}")
    elif prediction_label:
        footer_parts.append(f"Prediction: {prediction_label}")
    if winner:
        footer_parts.append(f"Winner: {winner}")
    goals_text = ", ".join(fixture.goal_scorers[:5]) if fixture.goal_scorers else None
    if goals_text:
        footer_parts.append(f"{gui_t('card.goals', locale)}: {goals_text}")

    conf_val = confidence if confidence is not None else (
        stored_record.confidence_score if stored_record is not None else None
    )
    render_international_match_card(
        fixture,
        locale,
        variant="finished",
        confidence=conf_val,
        prediction_subtitle=acc_label,
        tournament_context=tournament_context,
        key_prefix=f"fin_{fixture.fixture_id}",
        extra_footer=" · ".join(footer_parts) if footer_parts else None,
    )
    if show_fixture_id:
        from worldcup_predictor.ui.international_match_card import render_developer_panel

        render_developer_panel(fixture, locale=locale, source=fixture.source)


def render_match_card(
    fixture: TournamentFixture | Any,
    locale: Locale,
    *,
    data_quality: float | None = None,
    source: str | None = None,
    show_fixture_id: bool = False,
    prediction_status: str | None = None,
    confidence: float | None = None,
    status_override: str | None = None,
    tournament_context: dict[str, Any] | None = None,
    key_prefix: str | None = None,
) -> None:
    fid = getattr(fixture, "fixture_id", None) or getattr(fixture, "id", 0)
    prefix = key_prefix or f"up_{fid}"
    render_international_match_card(
        fixture,
        locale,
        variant="upcoming",
        confidence=confidence,
        data_quality=data_quality,
        prediction_subtitle=prediction_status,
        tournament_context=tournament_context,
        key_prefix=prefix,
    )
    if show_fixture_id:
        from worldcup_predictor.ui.international_match_card import render_developer_panel

        render_developer_panel(fixture, locale=locale, source=source or getattr(fixture, "source", None))


def render_prediction_card(prediction: MatchPrediction, translator: Translator, locale: Locale) -> None:
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
    readiness, progress, reason = analysis_readiness(prediction)
    col_r, col_sp = st.columns([1, 3])
    with col_r:
        render_readiness_badge(readiness, locale, progress, reason=reason)
    with col_sp:
        if prediction.no_bet_flag or prediction.risk_level == "high":
            st.warning(gui_t("watch_only", locale))
        elif prediction.confidence_score >= 60:
            st.info(gui_t("analysis_ready", locale))

    with st.container(border=True):
        st.markdown(f"**{prediction.match_name}**")
        gs = format_group_stage(
            prediction,
            prediction.group_context if prediction.group_context else None,
        )
        if gs != "—":
            st.caption(f"{gui_t('card.group', locale)}: {gs}")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("1X2", x2_label)
        with c2:
            st.metric("O/U 2.5", ou_label)
        with c3:
            adj = getattr(prediction, "adaptive_confidence", None)
            conf_label = translator.t("cli.prediction.confidence")
            if adj and abs(adj.total_bonus) >= 0.05:
                st.metric(conf_label, f"{prediction.confidence_score:.0f}/100")
                st.caption(f"Base {adj.base_confidence:.0f} + {adj.total_bonus:+.0f} learning")
            else:
                st.metric(conf_label, f"{prediction.confidence_score:.0f}/100")

        render_prediction_adaptive_panel(prediction, locale)

        ht_expected = prediction.halftime.estimated_total_goals
        st.markdown(f"**Expected first-half goals:** {ht_expected:.2f}")
        totals = halftime_total_outcomes(ht_expected)
        total_bits = [f"{label} ({prob:.0%})" for label, prob in totals[:3]]
        st.caption(f"Most likely first-half totals: {', '.join(total_bits)}")
        scorelines = halftime_scoreline_outcomes(prediction)
        sl_bits = [
            f"{label} ({prob:.0%})" if prob is not None else label
            for label, prob in scorelines[:3]
        ]
        st.caption(f"Most likely first-half scorelines: {', '.join(sl_bits)}")

        c4, c5 = st.columns(2)
        with c4:
            st.metric(translator.t("cli.predict.first_goal"), prediction.first_goal.team)
        with c5:
            st.metric(translator.t("cli.predict.risk_level"), prediction.risk_level.upper())
        st.caption(f"Prediction Quality: **{prediction.prediction_quality_score:.0f}/100**")

    fg = prediction.first_goal
    st.markdown(f"**First goal team:** {fg.team}")
    if fg.scorer_candidates:
        st.markdown("**Top scorer candidates**")
        for idx, candidate in enumerate(fg.scorer_candidates[:3], start=1):
            st.markdown(
                f"{idx}. **{candidate.player}** ({candidate.team}) — "
                f"score {candidate.score:.0f} · {candidate.reason} · _{candidate.data_source}_"
            )
    elif fg.player_data_unavailable:
        st.caption(fg.player_data_message or "Player-level scorer data unavailable")
    elif fg.player:
        st.caption(f"Likely scorer: {fg.player}")

    if prediction.scoreline:
        st.caption(f"{translator.t('cli.predict.scoreline')}: **{prediction.scoreline.label}**")
    if prediction.scoreline_candidates:
        cand = ", ".join(f"{c.label} ({c.probability:.0%})" for c in prediction.scoreline_candidates[:3])
        st.caption(f"Top scorelines: {cand}")
    if prediction.group_context and prediction.group_context.get("available"):
        gc = prediction.group_context
        gh = gc.get("home") or {}
        ga = gc.get("away") or {}
        group = format_group_stage(prediction, gc)
        stand_line = format_standings_context(gh, ga, locale)
        caption = f"{gui_t('card.group', locale)}: **{group}**"
        if stand_line:
            caption += f" · {stand_line}"
        st.caption(caption)
    if prediction.consistency_notes:
        st.caption(f"Consistency: {prediction.consistency_notes[0]}")
    if prediction.explanation:
        st.markdown(f"**{translator.t('cli.predict.explanation')}**")
        st.write(prediction.explanation.get(locale))
    if prediction.disclaimer:
        st.caption(prediction.disclaimer.get(locale))


def _api_status_style(status: Any) -> tuple[str, str, str]:
    """Return (css_class, pill_class, label) for API status card."""
    if not status.configured:
        return "api-status-card-red", "api-status-pill-red", "● Missing Key"
    if status.connected is True:
        return "api-status-card-green", "api-status-pill-green", "● Connected"
    if status.connected is False:
        return "api-status-card-red", "api-status-pill-red", "● Error"
    return "api-status-card-orange", "api-status-pill-orange", "● Configured but no data"


def _display_service_name(service: str) -> str:
    mapping = {
        "API-Football": "API-Sports",
        "RapidAPI Football Stats": "Rapid Football Stats",
        "Rapid Football XG Statistics": "Rapid XG",
        "Rapid Open Weather": "Rapid Weather",
    }
    return mapping.get(service, service)


def render_api_status_card(status: Any, locale: Locale) -> None:
    card_class, pill_class, label = _api_status_style(status)
    name = _display_service_name(status.service)
    latency = f" · {status.latency_ms:.0f} ms" if status.latency_ms else ""
    detail = status.message or gui_t("readiness.partial", locale)
    st.markdown(
        f"""
<div class="api-status-card {card_class}">
  <div class="api-status-name">{name}</div>
  <div class="api-status-pill {pill_class}">{label}</div>
  <div class="api-status-detail">{detail}{latency}</div>
  <div class="api-status-detail">{status.env_var}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_settings_section(title: str, body_html: str) -> None:
    st.markdown(
        f'<div class="settings-section-card"><div class="settings-section-title">{title}</div>{body_html}</div>',
        unsafe_allow_html=True,
    )


def render_api_status_grid(statuses: list[Any], locale: Locale) -> None:
    """Render primary API providers as status cards."""
    priority = {
        "API-Football",
        "RapidAPI Football Stats",
        "Rapid Football XG Statistics",
        "Rapid Open Weather",
        "OpenAI",
    }
    ordered = [s for s in statuses if s.service in priority]
    for status in ordered:
        render_api_status_card(status, locale)


def render_prediction_analysis_details(
    prediction: MatchPrediction,
    report: Any,
    locale: Locale,
    t: Any,
    *,
    developer_mode: bool = False,
) -> None:
    expanded = developer_mode
    dq_total = None
    if report and report.data_quality:
        dq_total = report.data_quality.breakdown_total or int((report.data_quality.score or 0) * 100)
        if report.data_quality.reason_text:
            st.caption(report.data_quality.reason_text)
    if dq_total is not None or prediction.prediction_quality_score:
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Data Quality", f"{dq_total or 0}/100")
        with c2:
            st.metric("Prediction Quality", f"{prediction.prediction_quality_score:.0f}/100")

    weather = getattr(report, "weather", None) or {} if report else {}
    specialist = getattr(report, "specialist_report", None) if report else None
    weather_sig = specialist.signal("weather_agent") if specialist else None
    if weather.get("available") or (weather_sig and weather_sig.signals.get("weather_impact_score") is not None):
        with st.expander("Weather impact", expanded=False):
            source = weather.get("source") or weather.get("provider") or (
                weather_sig.signals.get("weather_source") if weather_sig else "unknown"
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Temp °C", weather.get("temperature_c") or "n/a")
            with c2:
                rain = weather.get("rain_probability")
                st.metric("Rain prob.", f"{rain * 100:.0f}%" if rain is not None else "n/a")
            with c3:
                st.metric("Wind km/h", weather.get("wind_speed_kmh") or "n/a")
            with c4:
                impact = weather.get("weather_impact_score") or (
                    weather_sig.signals.get("weather_impact_score") if weather_sig else None
                )
                st.metric("Impact score", impact if impact is not None else "n/a")
            st.caption(f"Source: {source} · {weather.get('condition') or ''}")
    elif weather_sig and weather_sig.status == "unavailable":
        st.caption("Weather unavailable — prediction continues without weather factor.")

    from worldcup_predictor.ui.lineup_intelligence_display import render_lineup_intelligence_v2

    with st.expander(gui_t("tech.lineup", locale), expanded=expanded):
        render_lineup_intelligence_v2(report, locale, specialist_report=specialist)

    from worldcup_predictor.ui.injury_intelligence_display import render_injury_intelligence_v2

    with st.expander(gui_t("tech.injury", locale), expanded=expanded):
        render_injury_intelligence_v2(report, locale, specialist_report=specialist)

    from worldcup_predictor.ui.sharp_money_intelligence_display import render_sharp_money_intelligence_v2

    with st.expander(gui_t("tech.sharp_money", locale), expanded=expanded):
        render_sharp_money_intelligence_v2(report, locale, specialist_report=specialist)

    from worldcup_predictor.ui.explainability_display import render_prediction_explainability_v2

    with st.expander(gui_t("tech.explainability", locale), expanded=expanded):
        render_prediction_explainability_v2(prediction, report, locale, specialist_report=specialist)

    from worldcup_predictor.ui.tournament_intelligence_display import render_tournament_intelligence_v2

    with st.expander(gui_t("tech.tournament", locale), expanded=expanded):
        render_tournament_intelligence_v2(report, locale, specialist_report=specialist)

    from worldcup_predictor.ui.elo_team_strength_display import render_elo_team_strength_intelligence_v2

    with st.expander(gui_t("tech.elo", locale), expanded=expanded):
        render_elo_team_strength_intelligence_v2(report, locale, specialist_report=specialist)

    from worldcup_predictor.ui.xg_chance_quality_display import render_xg_chance_quality_intelligence_v2

    with st.expander(gui_t("tech.xg", locale), expanded=expanded):
        render_xg_chance_quality_intelligence_v2(report, locale, specialist_report=specialist)

    from worldcup_predictor.ui.final_decision_fusion_display import render_final_decision_fusion_v2

    with st.expander(gui_t("tech.fusion", locale), expanded=expanded):
        render_final_decision_fusion_v2(prediction, report, locale, specialist_report=specialist)

    from worldcup_predictor.ui.match_report_export_display import render_match_report_export_v2

    with st.expander(gui_t("tech.export", locale), expanded=False):
        render_match_report_export_v2(prediction, report, locale, specialist_report=specialist)

    with st.expander(gui_t("tech.audit", locale), expanded=False):
        render_audit_details(getattr(prediction, "audit_report", None), locale)

    if report and getattr(report, "group_context", None) and report.group_context.get("available"):
        with st.expander("Group context", expanded=False):
            for side, label in (("home", "Home"), ("away", "Away")):
                row = report.group_context.get(side) or {}
                if row:
                    st.markdown(
                        f"**{label}** — Group {row.get('group', '—')} · "
                        f"Rank {row.get('rank', '—')} · Points {row.get('points', '—')} · "
                        f"{row.get('description') or row.get('form') or ''}"
                    )

    if report and report.missing_data:
        with st.expander("Missing data", expanded=False):
            for item in report.missing_data[:15]:
                st.caption(f"• {item}")

    if prediction.reasons:
        with st.expander("Confidence reasons", expanded=False):
            for reason in prediction.reasons[:8]:
                desc = reason.description.get(locale) if reason.description else reason.key
                st.markdown(f"- **{reason.key}** ({reason.weight:+.2f}): {desc}")

    if prediction.no_bet_flag:
        st.warning("No-bet / watch-only: data quality or confidence is below the analytical threshold.")
        if prediction.audit_report and prediction.audit_report.trace:
            for note in prediction.audit_report.trace.no_bet_reasons[:5]:
                st.caption(f"• {note}")

    if report and report.data_quality:
        needed = [f for f, pts in (report.data_quality.breakdown or {}).items() if pts == 0]
        if needed:
            st.info("To improve confidence: load " + ", ".join(n.replace("_", " ") for n in needed[:6]))


def render_professional_report_view(report: Any, t: Any, locale: Locale, *, fixture: Any | None = None) -> None:
    """Cards and tables — raw JSON hidden under Advanced expander."""
    import pandas as pd

    if report.watch_only:
        st.warning(gui_t("watch_only", locale))
    gen = getattr(report, "generated_at_utc", "") or ""
    gs = format_group_stage(fixture) if fixture is not None else "—"
    header = f"{t.t('cli.report.source')}: {report.source} · {report.match_name}"
    if gs != "—":
        header += f" · {gui_t('card.group', locale)}: {gs}"
    st.caption(header + (f" · Generated (UTC): {gen[:19]}" if gen else ""))

    st.subheader(t.t("cli.report.executive_summary"))
    st.info(report.executive_summary)

    summary = report.prediction_summary or {}
    st.subheader(t.t("cli.report.prediction_summary"))
    if isinstance(summary, dict):
        rows = []
        for key, value in summary.items():
            if isinstance(value, dict):
                display = ", ".join(f"{k}: {v}" for k, v in value.items())
            else:
                display = str(value)
            rows.append({"Market": key.replace("_", " ").title(), "Prediction": display})
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No structured prediction summary available.")
    else:
        st.write(str(summary))

    st.subheader(t.t("cli.report.final_view"))
    st.write(report.final_analytical_view)
    st.caption(report.disclaimer)

    with st.expander(gui_t("advanced.json", locale), expanded=False):
        st.json(summary if isinstance(summary, dict) else {"summary": summary})


def render_audit_details(audit: Any, locale: Locale) -> None:
    """Audit trace as metrics and table — no raw dict by default."""
    import pandas as pd

    if not audit:
        return
    trace = audit.trace
    if trace:
        st.subheader("Decision Trace")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Baseline confidence", f"{trace.baseline_confidence:.0f}")
        with c2:
            st.metric("Final confidence", f"{trace.final_confidence:.0f}")
        with c3:
            delta = trace.final_confidence - trace.baseline_confidence
            st.metric("Adjustment", f"{delta:+.0f}")
        if trace.watch_only:
            st.warning(gui_t("watch_only", locale))
        if trace.confidence_caps_applied:
            st.caption("Caps applied: " + "; ".join(trace.confidence_caps_applied))
        if trace.confidence_reductions:
            st.caption("Reductions: " + "; ".join(trace.confidence_reductions))

    contributions = getattr(audit, "all_contributions", None) or []
    if contributions:
        st.subheader("Factor contributions")
        rows = [
            {
                "Factor": item.factor_name,
                "Weight %": item.weight_pct,
                "Score": item.score,
                "Contribution": item.contribution,
                "Direction": item.direction,
                "Note": item.note,
            }
            for item in contributions
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if audit.conflicts:
        st.subheader("Conflicts")
        for conflict in audit.conflicts:
            st.warning(f"[{conflict.severity}] {conflict.description}")

    if audit.limitations:
        st.subheader("Data limitations")
        for lim in audit.limitations:
            st.caption(f"• {lim.field}: {lim.impact}")

    if trace and trace.no_bet_reasons:
        st.subheader("No-bet reasons")
        for note in trace.no_bet_reasons:
            st.caption(f"• {note}")

    with st.expander(gui_t("advanced.json", locale), expanded=False):
        payload = {
            "trace": trace.__dict__ if trace else None,
            "supported_factors": [f.__dict__ for f in audit.supported_factors],
            "opposed_factors": [f.__dict__ for f in audit.opposed_factors],
            "neutral_factors": [f.__dict__ for f in audit.neutral_factors],
            "conflicts": [c.__dict__ for c in audit.conflicts],
            "limitations": [l.__dict__ for l in audit.limitations],
        }
        st.json(payload)

