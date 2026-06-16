"""Premium dark dashboard theme — shared User + Developer Mode."""

from __future__ import annotations

import streamlit as st

DASHBOARD_THEME_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --dash-bg: #070b14;
    --dash-bg2: #0c1222;
    --dash-card: rgba(15, 23, 42, 0.72);
    --dash-card-hover: rgba(30, 41, 59, 0.85);
    --dash-border: rgba(99, 102, 241, 0.28);
    --dash-border-soft: rgba(148, 163, 184, 0.12);
    --dash-accent: #6366f1;
    --dash-accent2: #8b5cf6;
    --dash-accent-glow: rgba(99, 102, 241, 0.35);
    --dash-text: #e2e8f0;
    --dash-muted: #94a3b8;
    --dash-success: #22d3ee;
    --dash-live: #f97316;
    --dash-finished: #f87171;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    color: var(--dash-text);
}

html { scroll-behavior: smooth; }

.stApp {
    background: radial-gradient(ellipse 120% 80% at 50% -20%, rgba(99,102,241,0.12), transparent 50%),
                linear-gradient(180deg, var(--dash-bg) 0%, var(--dash-bg2) 100%) !important;
}

.main .block-container {
    padding-top: 1.25rem;
    max-width: 1280px;
}

header[data-testid="stHeader"] { background: transparent; border: none; }
#MainMenu, footer { visibility: hidden; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #050810 0%, #0a1020 50%, #0d1528 100%) !important;
    border-right: 1px solid var(--dash-border-soft) !important;
}
section[data-testid="stSidebar"] > div { background: transparent !important; }
section[data-testid="stSidebar"] * { color: var(--dash-text); }

section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stExpander label {
    color: var(--dash-muted) !important;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

section[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid var(--dash-border-soft) !important;
    color: var(--dash-text) !important;
    border-radius: 10px !important;
}

section[data-testid="stSidebar"] .stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    transition: all 0.18s ease !important;
}

section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
    background: transparent !important;
    color: var(--dash-muted) !important;
    border: 1px solid transparent !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
    background: rgba(99,102,241,0.1) !important;
    color: var(--dash-text) !important;
    border-color: var(--dash-border-soft) !important;
}

section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, rgba(99,102,241,0.35) 0%, rgba(139,92,246,0.25) 100%) !important;
    color: #c7d2fe !important;
    border: 1px solid var(--dash-border) !important;
    box-shadow: 0 0 20px var(--dash-accent-glow) !important;
}

section[data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 1px solid var(--dash-border-soft) !important;
    border-radius: 12px !important;
    background: rgba(15,23,42,0.5) !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    color: var(--dash-accent) !important;
    font-weight: 700 !important;
}

/* ── Main area buttons ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
    border: none !important;
    font-weight: 700 !important;
    border-radius: 10px !important;
    color: #fff !important;
    box-shadow: 0 4px 18px var(--dash-accent-glow) !important;
}
.stButton > button[kind="primary"]:hover {
    filter: brightness(1.08);
    transform: translateY(-1px);
}
.stButton > button[kind="secondary"] {
    background: var(--dash-card) !important;
    border: 1px solid var(--dash-border-soft) !important;
    color: var(--dash-text) !important;
    border-radius: 10px !important;
}

.main .stTextInput input, .main .stSelectbox > div > div {
    background: var(--dash-card) !important;
    border-color: var(--dash-border-soft) !important;
    color: var(--dash-text) !important;
    border-radius: 10px !important;
}

div[data-testid="stMetric"] {
    background: var(--dash-card);
    border: 1px solid var(--dash-border-soft);
    border-radius: 14px;
    padding: 0.75rem;
    backdrop-filter: blur(12px);
}
div[data-testid="stMetric"] label { color: var(--dash-muted) !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: var(--dash-text) !important; }

[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--dash-card) !important;
    border: 1px solid var(--dash-border-soft) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(12px);
}

.stTabs [data-baseweb="tab-list"] { gap: 0.5rem; }
.stTabs [data-baseweb="tab"] {
    background: var(--dash-card) !important;
    border-radius: 10px !important;
    color: var(--dash-muted) !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(99,102,241,0.3), rgba(139,92,246,0.2)) !important;
    color: #c7d2fe !important;
}

/* ── Branding ── */
.sidebar-brand { padding: 0.5rem 0 1.25rem; }
.sidebar-brand-logo {
    font-size: 1.75rem;
    line-height: 1;
    margin-bottom: 0.5rem;
}
.sidebar-brand-title {
    font-size: 1.05rem;
    font-weight: 800;
    color: #f8fafc;
    letter-spacing: -0.02em;
    line-height: 1.3;
}
.sidebar-brand-sub {
    font-size: 0.78rem;
    color: var(--dash-muted);
    line-height: 1.45;
    margin-top: 0.35rem;
}
.sidebar-nav-label {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--dash-muted);
    margin: 0.75rem 0 0.35rem;
}

/* ── Glass cards ── */
.glass-card {
    background: var(--dash-card);
    border: 1px solid var(--dash-border-soft);
    border-radius: 16px;
    padding: 1.1rem 1.15rem;
    backdrop-filter: blur(14px);
    transition: border-color 0.2s, box-shadow 0.2s;
}
.glass-card:hover {
    border-color: var(--dash-border);
    box-shadow: 0 8px 32px rgba(0,0,0,0.25);
}

.kickoff-panel {
    margin: 0.75rem 0;
    font-size: 0.92rem;
    line-height: 1.55;
}
.kickoff-panel div {
    margin: 0.15rem 0;
}
.kickoff-warn {
    color: #fbbf24;
    font-size: 0.85rem;
    margin-top: 0.35rem;
}

.dash-section-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 1.5rem 0 0.85rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.dash-welcome-header {
    background: linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(139,92,246,0.08) 100%);
    border: 1px solid var(--dash-border);
    border-radius: 18px;
    padding: 1.35rem 1.5rem;
    margin-bottom: 1.25rem;
}
.dash-welcome-header h1 {
    font-size: 1.45rem;
    font-weight: 800;
    color: #f8fafc;
    margin: 0 0 0.35rem;
    letter-spacing: -0.02em;
}
.dash-welcome-header p {
    color: var(--dash-muted);
    font-size: 0.88rem;
    margin: 0;
}

.dash-badge {
    display: inline-block;
    padding: 0.25rem 0.65rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
}
.dash-badge-user { background: rgba(99,102,241,0.2); color: #a5b4fc; border: 1px solid var(--dash-border); }
.dash-badge-live { background: rgba(249,115,22,0.15); color: #fdba74; border: 1px solid rgba(249,115,22,0.35); }

/* ── Match cards ── */
.dash-match-card {
    background: var(--dash-card);
    border: 1px solid var(--dash-border-soft);
    border-radius: 14px;
    padding: 1rem;
    height: 100%;
    transition: all 0.2s;
}
.dash-match-card:hover { border-color: var(--dash-border); }
.dash-match-teams {
    font-size: 0.95rem;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 0.5rem;
}
.dash-match-meta { font-size: 0.78rem; color: var(--dash-muted); line-height: 1.5; }
.dash-match-group {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 6px;
    background: rgba(99,102,241,0.15);
    color: #a5b4fc;
    font-size: 0.72rem;
    font-weight: 600;
}

/* ── Quick actions grid ── */
.dash-quick-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.65rem;
}
.dash-quick-tile {
    background: var(--dash-card);
    border: 1px solid var(--dash-border-soft);
    border-radius: 12px;
    padding: 0.85rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
}
.dash-quick-tile:hover {
    border-color: var(--dash-accent);
    box-shadow: 0 0 16px var(--dash-accent-glow);
}

/* ── AI insights ── */
.dash-insight-card {
    background: linear-gradient(145deg, rgba(99,102,241,0.12) 0%, rgba(15,23,42,0.8) 100%);
    border: 1px solid var(--dash-border);
    border-radius: 16px;
    padding: 1.15rem;
}
.dash-insight-value {
    font-size: 1.35rem;
    font-weight: 800;
    color: #c7d2fe;
}
.dash-insight-label { font-size: 0.75rem; color: var(--dash-muted); text-transform: uppercase; letter-spacing: 0.05em; }

/* ── Group browser ── */
.group-card-glass {
    background: var(--dash-card);
    border: 1px solid var(--dash-border-soft);
    border-radius: 14px;
    padding: 0.85rem;
    backdrop-filter: blur(10px);
}
.group-card-header { font-size: 1rem; font-weight: 800; color: #e2e8f0; margin-bottom: 0.35rem; }
.group-card-teams { font-size: 0.8rem; color: var(--dash-muted); line-height: 1.45; margin-bottom: 0.35rem; }
.group-card-stats { font-size: 0.72rem; color: var(--dash-muted); }

.match-row { padding: 0.45rem 0.65rem; border-radius: 10px; margin: 0.3rem 0; }
.match-row-finished { background: rgba(248,113,113,0.08); border-left: 3px solid var(--dash-finished); opacity: 0.9; }
.match-row-upcoming { background: rgba(34,211,238,0.06); border-left: 3px solid var(--dash-success); }
.match-row-live { background: rgba(249,115,22,0.1); border-left: 3px solid var(--dash-live); }
.match-badge { display: inline-block; padding: 0.18rem 0.55rem; border-radius: 999px; font-size: 0.68rem; font-weight: 700; margin-right: 0.35rem; }
.match-badge-finished { background: rgba(248,113,113,0.2); color: #fca5a5; border: 1px solid rgba(248,113,113,0.35); }
.match-badge-upcoming { background: rgba(34,211,238,0.15); color: #67e8f9; border: 1px solid rgba(34,211,238,0.3); }
.match-badge-live { background: rgba(249,115,22,0.2); color: #fdba74; border: 1px solid rgba(249,115,22,0.35); }
.match-result-text { font-weight: 600; color: #fca5a5; font-size: 0.85rem; }
.match-status-struck { color: var(--dash-muted); font-size: 0.78rem; }
.match-row-divider { border: none; border-top: 1px solid var(--dash-border-soft); margin: 0.35rem 0; }

/* ── Page headers ── */
.page-header h1 { color: #f8fafc !important; font-weight: 800; letter-spacing: -0.02em; }
.page-header p { color: var(--dash-muted) !important; }

/* ── Premium upgrade card ── */
.premium-upgrade-card {
    background: linear-gradient(135deg, rgba(99,102,241,0.2) 0%, rgba(139,92,246,0.15) 100%);
    border: 1px solid var(--dash-border);
    border-radius: 14px;
    padding: 1rem;
    margin-top: 0.75rem;
    text-align: center;
}
.premium-upgrade-card h4 { color: #c7d2fe; font-size: 0.9rem; margin: 0 0 0.35rem; }
.premium-upgrade-card p { color: var(--dash-muted); font-size: 0.75rem; margin: 0; }

/* ── Footer ── */
.dash-footer {
    margin-top: 2rem;
    padding: 1rem 0;
    border-top: 1px solid var(--dash-border-soft);
    font-size: 0.72rem;
    color: var(--dash-muted);
    text-align: center;
    line-height: 1.6;
}

.creator-card {
    background: var(--dash-card);
    border: 1px solid var(--dash-border-soft);
    border-radius: 14px;
    padding: 0.85rem;
    margin-top: 0.75rem;
    text-align: center;
}
.creator-name { font-size: 0.85rem; font-weight: 700; color: #a5b4fc; }
.creator-copy { font-size: 0.62rem; color: var(--dash-muted); }

.status-pill { border-radius: 999px; font-size: 0.78rem; font-weight: 700; }
.phase48-badge { display: inline-block; padding: 0.35rem 0.75rem; margin: 0.15rem 0; }

.back-to-top {
    position: fixed; bottom: 1.25rem; right: 1.25rem; z-index: 9999;
    padding: 0.55rem 0.9rem;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: #fff !important; font-weight: 800; font-size: 0.85rem;
    text-decoration: none !important; border-radius: 999px;
    box-shadow: 0 6px 24px var(--dash-accent-glow);
}

@media (max-width: 768px) {
    .dash-quick-grid { grid-template-columns: repeat(2, 1fr); }
}
"""


def inject_dashboard_theme() -> None:
    st.markdown(f"<style>{DASHBOARD_THEME_CSS}</style>", unsafe_allow_html=True)
