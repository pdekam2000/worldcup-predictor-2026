"""Remember-me login — opaque browser token, never stores access code or admin password."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import streamlit as st
import streamlit.components.v1 as components

from worldcup_predictor.access.config import credentials_login_available
from worldcup_predictor.access.repository import AccessRepository, get_access_repository

_REMEMBER_DAYS = 30
_STORAGE_KEY = "wc_pred_remember"
_QUERY_KEY = "rt"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_remember_token(user_id: str, *, repo: AccessRepository | None = None) -> str:
    """Issue opaque remember token — stored as hash in SQLite only."""
    token = secrets.token_urlsafe(32)
    db = repo or get_access_repository()
    db.save_remember_token(user_id, _hash_token(token), days=_REMEMBER_DAYS)
    return token


def validate_remember_token(token: str, *, repo: AccessRepository | None = None) -> str | None:
    """Return user_id if token valid and not expired."""
    if not token or not token.strip():
        return None
    db = repo or get_access_repository()
    return db.get_user_id_for_remember_token(_hash_token(token.strip()))


def persist_token_in_browser(token: str) -> None:
    """Write opaque token to browser localStorage — not the access code."""
    safe = token.replace("'", "")
    components.html(
        f"<script>try{{localStorage.setItem('{_STORAGE_KEY}','{safe}');}}catch(e){{}}</script>",
        height=0,
    )


def clear_token_in_browser() -> None:
    components.html(
        f"<script>try{{localStorage.removeItem('{_STORAGE_KEY}');}}catch(e){{}}</script>",
        height=0,
    )


def inject_remember_restore_probe() -> None:
    """Once per session: read localStorage and reload with ?rt= token if present."""
    if st.session_state.get("_remember_probe_done"):
        return
    st.session_state["_remember_probe_done"] = True
    if st.query_params.get(_QUERY_KEY):
        return
    components.html(
        f"""
<script>
(function() {{
  try {{
    const t = localStorage.getItem('{_STORAGE_KEY}');
    if (!t) return;
    const u = new URL(window.parent.location.href);
    if (u.searchParams.get('{_QUERY_KEY}')) return;
    u.searchParams.set('{_QUERY_KEY}', t);
    window.parent.location.replace(u.toString());
  }} catch (e) {{}}
}})();
</script>
""",
        height=0,
    )


def try_restore_remembered_login(*, repo: AccessRepository | None = None) -> bool:
    """Restore registered session from ?rt= query param — never raises."""
    if not credentials_login_available():
        return False
    if st.session_state.get("access_user_id"):
        return False
    token = st.query_params.get(_QUERY_KEY)
    if not token:
        return False
    user_id = validate_remember_token(str(token), repo=repo)
    if not user_id:
        clear_token_in_browser()
        return False
    user = (repo or get_access_repository()).get_user_by_id(user_id)
    if user is None:
        clear_token_in_browser()
        return False
    st.session_state["access_user_id"] = user.user_id
    st.session_state["access_user_email"] = user.email
    st.session_state.pop("anonymous_user_id", None)
    (repo or get_access_repository()).touch_login(user.user_id)
    return True
