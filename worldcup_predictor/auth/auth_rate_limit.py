"""Phase 41B — in-memory auth rate limits (per-process; restart clears)."""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_buckets: dict[str, list[float]] = {}
_lockouts_until: dict[str, float] = {}

# Login: 5 failures per email+IP → 15 min lockout; 20 attempts per IP/hour
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 900
LOGIN_IP_MAX_PER_HOUR = 20

# Register: 5 per IP per hour
REGISTER_MAX_PER_HOUR = 5
REGISTER_MIN_INTERVAL_SECONDS = 30

# Forgot password: 10 per IP per hour (email limits remain in password_reset.py)
FORGOT_PASSWORD_IP_MAX_PER_HOUR = 10


def _prune(key: str, window_seconds: float) -> list[float]:
    now = time.time()
    window = [t for t in _buckets.get(key, []) if now - t < window_seconds]
    _buckets[key] = window
    return window


def _is_locked(key: str) -> tuple[bool, int]:
    now = time.time()
    until = _lockouts_until.get(key, 0)
    if until > now:
        return True, int(until - now)
    return False, 0


def check_login_allowed(*, email: str, ip: str | None) -> tuple[bool, int]:
    email_key = f"login:email:{email.strip().lower()}"
    ip_key = f"login:ip:{ip or 'unknown'}"
    now = time.time()
    with _lock:
        for key in (email_key, ip_key):
            locked, retry = _is_locked(key)
            if locked:
                return False, retry
        ip_window = _prune(ip_key, 3600)
        if len(ip_window) >= LOGIN_IP_MAX_PER_HOUR:
            return False, int(3600 - (now - ip_window[0]))
    return True, 0


def record_login_failure(*, email: str, ip: str | None) -> tuple[bool, int]:
    """Record failed login; returns (locked, retry_after_seconds)."""
    email_key = f"login:email:{email.strip().lower()}:{ip or 'unknown'}"
    now = time.time()
    with _lock:
        window = _prune(email_key, LOGIN_LOCKOUT_SECONDS)
        window.append(now)
        _buckets[email_key] = window
        if len(window) >= LOGIN_MAX_FAILURES:
            _lockouts_until[email_key] = now + LOGIN_LOCKOUT_SECONDS
            return True, LOGIN_LOCKOUT_SECONDS
        ip_key = f"login:ip:{ip or 'unknown'}"
        ip_window = _prune(ip_key, 3600)
        ip_window.append(now)
        _buckets[ip_key] = ip_window
    return False, 0


def clear_login_failures(*, email: str, ip: str | None) -> None:
    email_key = f"login:email:{email.strip().lower()}:{ip or 'unknown'}"
    with _lock:
        _buckets.pop(email_key, None)
        _lockouts_until.pop(email_key, None)


def check_register_allowed(*, ip: str | None) -> tuple[bool, int]:
    key = f"register:ip:{ip or 'unknown'}"
    now = time.time()
    with _lock:
        window = _prune(key, 3600)
        if window and now - window[-1] < REGISTER_MIN_INTERVAL_SECONDS:
            return False, int(REGISTER_MIN_INTERVAL_SECONDS - (now - window[-1]))
        if len(window) >= REGISTER_MAX_PER_HOUR:
            return False, int(3600 - (now - window[0]))
    return True, 0


def record_register_attempt(*, ip: str | None) -> None:
    key = f"register:ip:{ip or 'unknown'}"
    with _lock:
        window = _prune(key, 3600)
        window.append(time.time())
        _buckets[key] = window


def check_forgot_password_ip_allowed(*, ip: str | None) -> tuple[bool, int]:
    key = f"forgot:ip:{ip or 'unknown'}"
    now = time.time()
    with _lock:
        window = _prune(key, 3600)
        if len(window) >= FORGOT_PASSWORD_IP_MAX_PER_HOUR:
            return False, int(3600 - (now - window[0]))
    return True, 0


def record_forgot_password_ip(*, ip: str | None) -> None:
    key = f"forgot:ip:{ip or 'unknown'}"
    with _lock:
        window = _prune(key, 3600)
        window.append(time.time())
        _buckets[key] = window


def reset_auth_rate_limits() -> None:
    """Clear in-memory buckets (validation / local dev only)."""
    with _lock:
        _buckets.clear()
        _lockouts_until.clear()
