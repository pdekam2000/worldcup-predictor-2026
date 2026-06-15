"""Public access page guards — login required before predictions/API."""

from __future__ import annotations

from worldcup_predictor.access.config import public_access_enabled
from worldcup_predictor.access.identity import is_registered_user

# Pages reachable without sign-in when public access mode is on
PUBLIC_OPEN_PAGES = frozenset({"home", "upgrade", "settings", "team_search"})

# Pages that trigger prediction / intelligence / paid API usage (handled per-page)
PUBLIC_PROTECTED_PAGES = frozenset({"opening", "upcoming"})


def needs_public_sign_in(page: str | None) -> bool:
    """True when user must sign in before using this page's protected features."""
    if not public_access_enabled():
        return False
    if is_registered_user():
        return False
    key = (page or "home").strip()
    if key in PUBLIC_OPEN_PAGES:
        return False
    if key in PUBLIC_PROTECTED_PAGES:
        return True
    return False


def blocks_prediction_actions(page: str | None = None) -> bool:
    """True when predict/intelligence/API must not run."""
    _ = page
    if not public_access_enabled():
        return False
    return not is_registered_user()
