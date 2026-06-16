"""Phase 33/34 — App shell: sidebar, hero banner, headers, creator footer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale, get_settings
from worldcup_predictor.ui.gui_i18n import gui_t

# Phase 48 — simplified User Mode navigation (see gui_mode_v2.py)
USER_MODE_V2_NAV_ITEMS: list[tuple[str, str, str]] = [
    ("home", "nav.home", "🏠"),
    ("predict", "nav.predict", "🎯"),
    ("team_search", "nav.game_search", "🔎"),
    ("match_center", "nav.match_center", "⚽"),
    ("finished_results", "nav.finished_results", "✅"),
    ("professional_reports", "nav.professional_reports", "📄"),
    ("hall_of_fame", "nav.hall_of_fame", "🏆"),
    ("upgrade", "nav.upgrade", "💳"),
    ("settings", "nav.settings", "⚙️"),
]

# Developer Mode only (team_search moved to User Mode)
LEGACY_USER_NAV_ITEMS: list[tuple[str, str, str]] = [
    ("favorites", "nav.favorites", "⭐"),
    ("shortlist", "nav.shortlist", "📋"),
]

# User-facing navigation (sidebar primary — pre Phase 48)
USER_NAV_ITEMS: list[tuple[str, str, str]] = [
    ("home", "nav.home", "🏠"),
    ("match_center", "nav.match_center", "⚽"),
    ("team_search", "nav.team_search", "🔎"),
    ("favorites", "nav.favorites", "⭐"),
    ("shortlist", "nav.shortlist", "📋"),
]

# Developer / advanced navigation
DEV_NAV_ITEMS: list[tuple[str, str, str]] = [
    ("api", "nav.api", "🔌"),
    ("accuracy", "nav.accuracy", "📈"),
    ("learning", "nav.learning", "🎓"),
    ("learning_center_v2", "nav.learning_center_v2", "📚"),
    ("automation", "nav.automation", "🤖"),
    ("specialists", "nav.specialists", "🧠"),
    ("report", "nav.report", "📋"),
    ("audit", "nav.audit", "🔍"),
    ("backtest", "nav.backtest", "📊"),
    ("admin_entitlements", "nav.admin_entitlements", "🛡️"),
    ("feedback_viewer", "nav.feedback_viewer", "💬"),
    ("settings", "nav.settings", "⚙️"),
]

# Pages reachable via actions but not listed in sidebar
HIDDEN_NAV_KEYS = frozenset({"opening", "upcoming", "predict"})

GUI_LOCALE_FLAGS: dict[str, str] = {
    "en": "🇬🇧",
    "de": "🇩🇪",
    "fa": "🇮🇷",
    "sr": "🇷🇸",
    "bs": "🇧🇦",
    "hr": "🇭🇷",
}

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_DEFAULT_BANNER = _ASSETS_DIR / "hero-banner.png"


def _marketing_enabled() -> bool:
    val = os.getenv("SHOW_MARKETING_WINRATE", "false").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _marketing_text() -> str:
    return os.getenv("MARKETING_WINRATE_TEXT", "Win Rate: 85%+").strip() or "Win Rate: 85%+"


def resolve_promo_winrate(metrics: Any | None = None) -> str:
    """Real winrate when available; never fake 85% unless marketing env is on."""
    if _marketing_enabled():
        return _marketing_text()
    if metrics is not None:
        evaluated = getattr(metrics, "total_evaluated", 0) or 0
        rate = getattr(metrics, "one_x_two_accuracy", None)
        if evaluated >= 5 and rate is not None:
            return f"Win Rate: {rate * 100:.1f}%"
    return "Performance tracking active"


def resolve_banner_path() -> Path | None:
    """Official hero banner — env override or bundled asset."""
    env = os.getenv("BANNER_IMAGE_PATH", "").strip()
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    if _DEFAULT_BANNER.is_file():
        return _DEFAULT_BANNER
    return None


def render_promo_banner(locale: Locale, *, winrate_line: str = "") -> None:
    """Full-width official hero banner image (Home + Match Center)."""
    path = resolve_banner_path()
    if path:
        st.markdown('<div class="hero-banner-container">', unsafe_allow_html=True)
        st.image(str(path), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Fallback if image missing — minimal gradient placeholder
    st.markdown(
        f"""
<div class="hero-banner-fallback">
  <div class="hero-banner-fallback-text">
    <h2>{gui_t("shell.promo_title", locale)}</h2>
    <p>{winrate_line or "Performance tracking active"}</p>
    <span class="promo-pill">{gui_t("shell.promo_pill", locale)}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_creator_footer(locale: Locale) -> None:
    st.sidebar.markdown(
        """
<div class="creator-card">
  <div class="creator-avatar">⚽</div>
  <div class="creator-label">Created by</div>
  <div class="creator-name">Pedram Kamangar</div>
  <div class="creator-role">Developer &amp; Football Data Analyst</div>
  <div class="creator-links">
    <a href="#" class="creator-icon" title="GitHub" aria-label="GitHub">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.395-.135-.345-.72-1.395-1.23-1.665-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 1.005 0 2.01.345 3.075 1.305.885-.24 1.815-.36 2.745-.36.93 0 1.86.12 2.745.36 1.065-.96 2.07-1.305 3.075-1.305.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
    </a>
    <a href="#" class="creator-icon" title="Telegram" aria-label="Telegram">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M11.944 0A12 12 0 000 12a12 12 0 0012 12 12 12 0 0012-12A12 12 0 0012 0a12 12 0 00-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 01.171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
    </a>
    <a href="#" class="creator-icon" title="LinkedIn" aria-label="LinkedIn">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 114.126 0 2.063 2.063 0 01-2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
    </a>
    <a href="mailto:pedram@example.com" class="creator-icon" title="Email" aria-label="Email">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
    </a>
  </div>
  <div class="creator-copy">© 2026 All rights reserved.</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_sidebar_branding(locale: Locale) -> None:
    st.sidebar.markdown(
        f"""
<div class="sidebar-brand">
  <div class="sidebar-brand-title">⚽ WorldCup Predictor Pro</div>
  <div class="sidebar-brand-sub">{gui_t("shell.tagline", locale)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_page_header(
    title: str,
    subtitle: str,
    *,
    search_placeholder: str | None = None,
    search_key: str = "page_search",
    show_refresh: bool = False,
    refresh_label: str = "Refresh",
    on_search: str | None = None,
) -> str | None:
    """Page title row with optional search + refresh. Returns search query if entered."""
    left, right = st.columns([3, 2])
    with left:
        st.markdown(
            f'<div class="page-header"><h1>{title}</h1><p>{subtitle}</p></div>',
            unsafe_allow_html=True,
        )
    query = ""
    with right:
        if search_placeholder:
            st.markdown('<div class="premium-search">', unsafe_allow_html=True)
            query = st.text_input(
                "Search",
                placeholder=search_placeholder,
                key=search_key,
                label_visibility="collapsed",
            )
            st.markdown("</div>", unsafe_allow_html=True)
        if show_refresh:
            if st.button(refresh_label, type="primary", use_container_width=True):
                st.session_state["_refresh_requested"] = True
    return query.strip() if query else None


def render_light_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="page-header"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def render_performance_cards(locale: Locale, metrics: Any) -> None:
    items = [
        ("🏅", gui_t("performance.grade", locale), getattr(metrics, "model_grade", "—") or "—", "Model performance grade"),
        ("🎯", gui_t("accuracy.1x2", locale), _fmt_pct(getattr(metrics, "one_x_two_accuracy", None)), "1X2 market accuracy"),
        ("⚽", gui_t("accuracy.ou", locale), _fmt_pct(getattr(metrics, "over_under_2_5_accuracy", None)), "Over/Under 2.5 accuracy"),
        ("✅", gui_t("performance.verified", locale), str(getattr(metrics, "total_evaluated", 0)), "Verified finished predictions"),
        ("⏳", gui_t("performance.pending", locale), str(getattr(metrics, "pending_predictions", 0)), "Awaiting match results"),
    ]
    cols = st.columns(len(items))
    for col, (icon, label, value, desc) in zip(cols, items):
        with col:
            st.markdown(
                f'<div class="premium-stat-card">'
                f'<div class="premium-stat-icon">{icon}</div>'
                f'<div class="premium-stat-value">{value}</div>'
                f'<div class="premium-stat-label">{label}</div>'
                f'<div class="premium-stat-desc">{desc}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )


def render_quick_action_cards(locale: Locale) -> None:
    from worldcup_predictor.ui.gui_mode_v2 import navigate_to_page

    dev_mode = st.session_state.get("gui_mode") == "developer"
    actions = [
        ("match_center", gui_t("btn.match_center", locale), "🏟️"),
        ("team_search", gui_t("nav.team_search", locale), "🔎"),
        ("shortlist", gui_t("nav.shortlist", locale), "📋"),
        ("sync", gui_t("db.sync", locale), "🔄"),
    ]
    cols = st.columns(len(actions))
    for col, (page, label, icon) in zip(cols, actions):
        with col:
            if st.button(f"{icon} {label}", key=f"qa_{page}", use_container_width=True):
                if page == "sync":
                    st.session_state["_trigger_sync"] = True
                    navigate_to_page("settings", developer_mode=dev_mode)
                else:
                    navigate_to_page(page, developer_mode=dev_mode)
                st.rerun()


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def render_model_experience_section(locale: Locale, *, competition_key: str | None = None) -> None:
    from worldcup_predictor.adaptive_confidence.engine import AdaptiveConfidenceEngine
    from worldcup_predictor.ui.adaptive_confidence_display import render_model_experience_cards

    summary = AdaptiveConfidenceEngine().model_experience(competition_key=competition_key)
    st.subheader(gui_t("adaptive.model_experience", locale))
    render_model_experience_cards(summary, locale)


def render_main_disclaimer(locale: Locale) -> None:
    st.markdown(
        f'<div class="main-disclaimer">{gui_t("disclaimer", locale)}</div>',
        unsafe_allow_html=True,
    )
