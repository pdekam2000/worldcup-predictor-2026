"""Phase 63 — enterprise role-based access control (centralized)."""

from __future__ import annotations

from typing import Final

# Higher rank = more privilege. Owner inherits all permissions.
ROLE_RANK: Final[dict[str, int]] = {
    "guest": 0,
    "free_user": 10,
    "user": 10,  # legacy alias for free_user
    "starter": 20,
    "pro": 30,
    "premium": 40,
    "admin": 50,
    "super_admin": 60,
    "owner": 100,
}

ALL_ROLES: Final[tuple[str, ...]] = tuple(ROLE_RANK.keys())

ADMIN_ROLES: Final[frozenset[str]] = frozenset({"admin", "super_admin", "owner"})
SUPER_ADMIN_ROLES: Final[frozenset[str]] = frozenset({"super_admin", "owner"})
OWNER_ROLES: Final[frozenset[str]] = frozenset({"owner"})

DEFAULT_OWNER_EMAIL = "kamangar.pedram@gmail.com"


def normalize_role(role: str | None) -> str:
    raw = (role or "guest").strip().lower()
    if raw == "user":
        return "free_user"
    return raw if raw in ROLE_RANK else "guest"


def role_rank(role: str | None) -> int:
    return ROLE_RANK.get(normalize_role(role), 0)


def has_minimum_role(role: str | None, minimum: str) -> bool:
    return role_rank(role) >= role_rank(minimum)


def is_owner(role: str | None) -> bool:
    return normalize_role(role) == "owner"


def is_super_admin(role: str | None) -> bool:
    return normalize_role(role) in SUPER_ADMIN_ROLES


def is_admin(role: str | None) -> bool:
    return normalize_role(role) in ADMIN_ROLES


def can_access_predictions(role: str | None) -> bool:
    """Guests cannot; all registered tiers and above can (subject to account flags)."""
    return role_rank(role) >= role_rank("free_user")


def role_inherits(required: str, actor: str | None) -> bool:
    """True when actor role satisfies required role (owner satisfies everything)."""
    actor_n = normalize_role(actor)
    required_n = normalize_role(required)
    if actor_n == "owner":
        return True
    return role_rank(actor_n) >= role_rank(required_n)
