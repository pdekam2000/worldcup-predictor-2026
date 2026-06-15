"""The Odds API credit guard limits — env / Streamlit secrets."""

from __future__ import annotations

import os


def _env_or_secret(key: str, default: str) -> str:
    val = os.getenv(key)
    if val is not None and str(val).strip():
        return str(val).strip()
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key]).strip()
        for section in ("general", "env", "secrets"):
            if section in st.secrets and key in st.secrets[section]:
                return str(st.secrets[section][key]).strip()
    except Exception:
        pass
    return default


def _int_env(key: str, default: int) -> int:
    try:
        return max(0, int(_env_or_secret(key, str(default))))
    except ValueError:
        return default


def odds_api_monthly_limit() -> int:
    return _int_env("ODDS_API_MONTHLY_LIMIT", 500)


def odds_api_daily_soft_limit() -> int:
    return _int_env("ODDS_API_DAILY_SOFT_LIMIT", 15)


def odds_api_daily_hard_limit() -> int:
    return _int_env("ODDS_API_DAILY_HARD_LIMIT", 16)


def odds_api_cache_hours() -> int:
    return _int_env("ODDS_API_CACHE_HOURS", 6)


def odds_api_low_bookmaker_count() -> int:
    return _int_env("ODDS_API_LOW_BOOKMAKER_COUNT", 3)


def odds_api_low_sharp_score() -> float:
    try:
        return float(_env_or_secret("ODDS_API_LOW_SHARP_SCORE", "40"))
    except ValueError:
        return 40.0


def odds_api_credits_per_call() -> int:
    return max(1, _int_env("ODDS_API_CREDITS_PER_CALL", 1))
