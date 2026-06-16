"""Premium dark dashboard theme — shared User + Developer Mode."""

from __future__ import annotations

import streamlit as st

DASHBOARD_THEME_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Vazirmatn:wght@400;500;600;700;800&display=swap');

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
    --dash-text: #f1f5f9;
    --dash-muted: #b8c5d6;
    --dash-success: #22d3ee;
    --dash-live: #f97316;
    --dash-finished: #f87171;
    --dash-font: 'Inter', 'Vazirmatn', 'Segoe UI', Tahoma, sans-serif;
}

html, body, [class*="css"] {
    font-family: var(--dash-font);
    color: var(--dash-text);
    font-size: 15px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
}

html { scroll-behavior: smooth; }

.stApp {
    background: radial-gradient(ellipse 120% 80% at 50% -20%, rgba(99,102,241,0.12), transparent 50%),
                linear-gradient(180deg, var(--dash-bg) 0%, var(--dash-bg2) 100%) !important;
}

.main .block-container {
    padding-top: 1.25rem;
    padding-bottom: 4.75rem;
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

[data-testid="stSidebar"] .sidebar-login-form .stTextInput input,
[data-testid="stSidebar"] .sidebar-login-form input[type="password"] {
    color: #0a0a0a !important;
    -webkit-text-fill-color: #0a0a0a !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    caret-color: #0a0a0a !important;
}
[data-testid="stSidebar"] .sidebar-login-form .stTextInput input::placeholder {
    color: #64748b !important;
    -webkit-text-fill-color: #64748b !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] .sidebar-login-form label,
[data-testid="stSidebar"] .sidebar-login-form .stCheckbox label p {
    color: #e2e8f0 !important;
    font-weight: 600 !important;
}

div[data-testid="stMetric"] {
    background: var(--dash-card);
    border: 1px solid var(--dash-border-soft);
    border-radius: 14px;
    padding: 0.75rem;
    backdrop-filter: blur(12px);
}
div[data-testid="stMetric"] label { color: var(--dash-muted) !important; font-weight: 600 !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #f8fafc !important; font-weight: 800 !important; }
div[data-testid="stMetric"] [data-testid="stMetricDelta"] { color: #86efac !important; }

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
    font-size: 0.95rem;
    line-height: 1.65;
    color: #e2e8f0;
}
.kickoff-panel div {
    margin: 0.2rem 0;
    color: #e2e8f0;
}
.kickoff-panel strong {
    color: #c7d2fe;
    font-weight: 700;
}
.kickoff-warn {
    color: #fbbf24;
    font-size: 0.88rem;
    margin-top: 0.45rem;
}

.fixture-summary-panel {
    padding: 1.1rem 1.15rem;
    margin: 0.75rem 0 1rem;
}
.fixture-summary-panel .match-header-flags {
    color: #f1f5f9 !important;
    font-size: 1.25rem;
    margin-bottom: 0.5rem;
}
.fixture-summary-panel .team-with-flag .imc-flag-img {
    width: 2.5rem !important;
    max-height: 1.75rem !important;
}
.fixture-meta-grid {
    display: grid;
    gap: 0.65rem;
    margin-top: 0.85rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--dash-border-soft);
}
.fixture-meta-grid.cols-3 { grid-template-columns: repeat(3, 1fr); }
.fixture-meta-grid.cols-4 { grid-template-columns: repeat(4, 1fr); }
.fixture-meta-cell {
    background: rgba(99,102,241,0.06);
    border: 1px solid var(--dash-border-soft);
    border-radius: 10px;
    padding: 0.55rem 0.65rem;
    min-height: 3.25rem;
}
.fixture-meta-label {
    display: block;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--dash-muted);
    margin-bottom: 0.25rem;
}
.fixture-meta-value {
    display: block;
    font-size: 0.92rem;
    font-weight: 700;
    color: #f1f5f9;
    line-height: 1.35;
    direction: auto;
    unicode-bidi: plaintext;
    word-break: break-word;
}

@media (max-width: 768px) {
    .fixture-meta-grid.cols-3,
    .fixture-meta-grid.cols-4 { grid-template-columns: repeat(2, 1fr); }
}

.login-required-callout {
    margin: 1rem 0 1.25rem;
    padding: 1rem 1.15rem;
    border-radius: 14px;
    border: 1px solid rgba(251, 191, 36, 0.35);
    background: rgba(251, 191, 36, 0.08);
}
.login-required-title {
    font-size: 1rem;
    font-weight: 800;
    color: #fde68a;
    margin-bottom: 0.35rem;
}
.login-required-body {
    font-size: 0.92rem;
    line-height: 1.55;
    color: #e2e8f0;
}

.finished-result-head { margin: 0.15rem 0 0.35rem; }
.finished-result-score {
    font-size: 1.15rem;
    font-weight: 800;
    color: #f1f5f9;
    line-height: 1.35;
}
.finished-result-meta {
    margin-top: 0.35rem;
    font-size: 0.88rem;
    color: #94a3b8;
    line-height: 1.45;
}

section.main div[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(15, 23, 42, 0.72) !important;
    border-color: var(--dash-border-soft) !important;
}
section.main div[data-testid="stVerticalBlockBorderWrapper"] p,
section.main div[data-testid="stVerticalBlockBorderWrapper"] label,
section.main div[data-testid="stVerticalBlockBorderWrapper"] .stCaption,
section.main div[data-testid="stVerticalBlockBorderWrapper"] span {
    color: #e2e8f0 !important;
}

.dash-section-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 1.75rem 0 1rem;
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
    font-size: 1.55rem;
    font-weight: 800;
    color: #f8fafc;
    margin: 0 0 0.35rem;
    letter-spacing: -0.02em;
}
.dash-welcome-header p {
    color: var(--dash-muted);
    font-size: 0.95rem;
    margin: 0;
}

.dash-badge {
    display: inline-block;
    padding: 0.28rem 0.7rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
}
.dash-badge-user { background: rgba(99,102,241,0.2); color: #a5b4fc; border: 1px solid var(--dash-border); }
.dash-badge-live { background: rgba(249,115,22,0.15); color: #fdba74; border: 1px solid rgba(249,115,22,0.35); }
.dash-badge-finished { background: rgba(248,113,113,0.12); color: #fca5a5; border: 1px solid rgba(248,113,113,0.3); }

/* ── Hero banner ── */
.dash-hero {
    position: relative;
    border-radius: 20px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.5rem;
    overflow: hidden;
    background: linear-gradient(135deg, rgba(99,102,241,0.22) 0%, rgba(139,92,246,0.12) 40%, rgba(15,23,42,0.6) 100%);
    border: 1px solid var(--dash-border);
}
.dash-hero-glow {
    position: absolute;
    top: -40%;
    right: -10%;
    width: 55%;
    height: 180%;
    background: radial-gradient(circle, rgba(99,102,241,0.25) 0%, transparent 70%);
    pointer-events: none;
}
.dash-hero-content { position: relative; z-index: 1; }
.dash-hero-kicker {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #a5b4fc;
    margin-bottom: 0.4rem;
}
.dash-hero h1 {
    font-size: clamp(1.35rem, 3vw, 1.85rem);
    font-weight: 800;
    color: #f8fafc;
    margin: 0 0 0.45rem;
    letter-spacing: -0.02em;
    line-height: 1.25;
}
.dash-hero p {
    color: var(--dash-muted);
    font-size: 0.95rem;
    margin: 0 0 0.85rem;
    max-width: 36rem;
}
.dash-hero-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
}
.dash-hero-stat {
    font-size: 0.88rem;
    font-weight: 600;
    color: #cbd5e1;
}

.dash-section-featured {
    font-size: 1.15rem !important;
    margin-top: 0.25rem !important;
}

/* ── Flag showcase cards ── */
.showcase-card {
    background: linear-gradient(160deg, rgba(30,41,59,0.85) 0%, rgba(15,23,42,0.92) 100%);
    border: 1px solid var(--dash-border-soft);
    border-radius: 18px;
    padding: 1.15rem 1rem 1.25rem;
    margin-bottom: 0.5rem;
    transition: border-color 0.22s, box-shadow 0.22s, transform 0.22s;
    height: 100%;
}
.showcase-card:hover {
    border-color: var(--dash-border);
    box-shadow: 0 12px 40px rgba(0,0,0,0.35), 0 0 24px var(--dash-accent-glow);
    transform: translateY(-2px);
}
.showcase-card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.85rem;
    gap: 0.5rem;
}
.showcase-group {
    font-size: 0.78rem;
    font-weight: 600;
    color: #a5b4fc;
    text-align: right;
    direction: auto;
}

.match-showcase {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.35rem;
    padding: 0.5rem 0 0.75rem;
}
.match-showcase-team {
    flex: 1;
    text-align: center;
    min-width: 0;
}
.match-showcase-flag {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 4.5rem;
    margin-bottom: 0.55rem;
}
.match-showcase-flag .imc-flag-img {
    width: 5.25rem !important;
    max-height: 3.75rem !important;
    border-radius: 10px !important;
    box-shadow: 0 6px 24px rgba(0,0,0,0.45);
    object-fit: cover;
    border: 2px solid rgba(255,255,255,0.08);
}
.match-showcase-flag .imc-flag-initials {
    min-width: 3.5rem;
    height: 2.75rem;
    font-size: 0.85rem;
    background: rgba(99,102,241,0.2);
    color: #c7d2fe;
    border: 1px solid var(--dash-border);
}
.match-showcase-name {
    font-size: 0.92rem;
    font-weight: 700;
    color: #f1f5f9;
    line-height: 1.3;
    direction: auto;
    unicode-bidi: plaintext;
    word-break: break-word;
}
.match-showcase-vs {
    flex-shrink: 0;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: var(--dash-muted);
    padding: 0.35rem 0.5rem;
    background: rgba(255,255,255,0.04);
    border-radius: 8px;
}

.showcase-kickoff {
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 0.65rem;
    padding-top: 0.35rem;
    border-top: 1px solid var(--dash-border-soft);
}
.showcase-time {
    font-size: 1.45rem;
    font-weight: 800;
    color: #c7d2fe;
    letter-spacing: -0.02em;
}
.showcase-date {
    font-size: 0.88rem;
    font-weight: 600;
    color: var(--dash-muted);
}
.showcase-venue {
    text-align: center;
    font-size: 0.82rem;
    color: var(--dash-muted);
    margin-top: 0.35rem;
    direction: auto;
}

.dash-insight-sub {
    font-size: 0.82rem;
    color: var(--dash-muted);
    margin-top: 0.2rem;
}

/* Dark-theme flag initials (global) */
.imc-flag-initials {
    background: rgba(99,102,241,0.18) !important;
    color: #c7d2fe !important;
    border: 1px solid var(--dash-border-soft) !important;
}

/* ── Match cards (legacy compact) ── */
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
    font-size: 1.45rem;
    font-weight: 800;
    color: #c7d2fe;
}
.dash-insight-label { font-size: 0.82rem; color: var(--dash-muted); text-transform: uppercase; letter-spacing: 0.05em; }

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
.page-header h1 { color: #f8fafc !important; font-weight: 800; letter-spacing: -0.02em; font-size: 1.65rem !important; }
.page-header p { color: #b8c5d6 !important; font-size: 0.98rem !important; line-height: 1.55 !important; }

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
    position: fixed; bottom: 1.35rem; right: 1.35rem; z-index: 9999;
    padding: 0.62rem 1.05rem;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: #fff !important; font-weight: 800; font-size: 0.88rem;
    text-decoration: none !important; border-radius: 999px;
    box-shadow: 0 8px 28px var(--dash-accent-glow);
    border: 1px solid rgba(199,210,254,0.35);
    transition: transform 0.18s ease, filter 0.18s ease, box-shadow 0.18s ease;
}
.back-to-top:hover {
    filter: brightness(1.08);
    transform: translateY(-2px);
    box-shadow: 0 12px 32px rgba(99,102,241,0.45);
    color: #fff !important;
}

/* ── Global readability on dark surfaces ── */
section.main, .main {
    color: var(--dash-text) !important;
}
section.main p,
section.main span,
section.main label,
section.main li,
section.main small,
.main p,
.main span,
.main label,
.main li {
    color: inherit;
}
section.main h1, section.main h2, section.main h3, section.main h4, section.main h5,
.main h1, .main h2, .main h3, .main h4, .main h5 {
    color: #f8fafc !important;
    font-weight: 700 !important;
}
section.main .stMarkdown, section.main .stMarkdown p,
.main .stMarkdown, .main .stMarkdown p {
    color: var(--dash-text) !important;
}
section.main .stMarkdown strong, .main .stMarkdown strong {
    color: #ffffff !important;
}
section.main .stMarkdown em, .main .stMarkdown em {
    color: var(--dash-muted) !important;
}
section.main .stMarkdown a, .main .stMarkdown a {
    color: #a5b4fc !important;
}
section.main .stCaption,
section.main [data-testid="stCaptionContainer"],
.main .stCaption,
.main [data-testid="stCaptionContainer"] {
    color: var(--dash-muted) !important;
    font-size: 0.9rem !important;
    line-height: 1.5 !important;
}
section.main .stSelectbox label,
section.main .stTextInput label,
section.main .stSlider label,
section.main .stRadio label,
section.main .stCheckbox label p,
.main .stSelectbox label,
.main .stTextInput label,
.main .stSlider label,
.main .stRadio label p,
.main .stCheckbox label p {
    color: #cbd5e1 !important;
    font-weight: 600 !important;
}
section.main .streamlit-expanderHeader,
section.main [data-testid="stExpander"] summary,
.main .streamlit-expanderHeader,
.main [data-testid="stExpander"] summary {
    color: #f1f5f9 !important;
    font-weight: 600 !important;
}
section.main [data-testid="stExpander"] .stMarkdown p,
.main [data-testid="stExpander"] .stMarkdown p {
    color: #dbe4ef !important;
}
section.main div[data-testid="stVerticalBlockBorderWrapper"] p,
section.main div[data-testid="stVerticalBlockBorderWrapper"] label,
section.main div[data-testid="stVerticalBlockBorderWrapper"] span,
section.main div[data-testid="stVerticalBlockBorderWrapper"] .stCaption,
section.main div[data-testid="stVerticalBlockBorderWrapper"] small {
    color: #e8eef6 !important;
}
section.main code, .main code {
    background: rgba(99,102,241,0.15) !important;
    color: #c7d2fe !important;
    padding: 0.12rem 0.35rem;
    border-radius: 6px;
}
section.main .stAlert p { color: inherit !important; }

/* Light cards on dark pages — keep internal contrast */
.stored-prediction-summary:not(.stored-prediction-evaluated) .stored-pred-label {
    color: #475569 !important;
}
.stored-prediction-summary:not(.stored-prediction-evaluated) .stored-pred-value {
    color: #0f172a !important;
}
.stored-prediction-summary:not(.stored-prediction-evaluated) .stored-pred-conf {
    color: #64748b !important;
}

.group-card-header { color: #f1f5f9 !important; font-weight: 700 !important; }
.group-card-teams { color: #b8c5d6 !important; }

.match-action-panel .stCaption,
.match-action-panel p,
.match-action-panel label {
    color: #cbd5e1 !important;
}

@media (max-width: 768px) {
    .dash-quick-grid { grid-template-columns: repeat(2, 1fr); }
}
"""


def inject_dashboard_theme() -> None:
    st.markdown(f"<style>{DASHBOARD_THEME_CSS}</style>", unsafe_allow_html=True)
