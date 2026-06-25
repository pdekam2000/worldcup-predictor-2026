"""Phase 41D — authenticated password change for logged-in users."""

from __future__ import annotations

import uuid

from worldcup_predictor.auth.passwords import hash_password, verify_password
from worldcup_predictor.database.saas_factory import saas_uow

MIN_PASSWORD_LENGTH = 8


def change_password_for_user(
    user_id: uuid.UUID,
    *,
    current_password: str,
    new_password: str,
    confirm_password: str,
) -> tuple[bool, str | None, str | None]:
    """Return (ok, error_message, error_code)."""
    current = (current_password or "").strip()
    new = (new_password or "").strip()
    confirm = (confirm_password or "").strip()

    if new != confirm:
        return False, "New password and confirmation do not match.", "password_mismatch"

    if len(new) < MIN_PASSWORD_LENGTH:
        return (
            False,
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            "password_too_weak",
        )

    if current == new:
        return (
            False,
            "New password must be different from your current password.",
            "password_same_as_old",
        )

    with saas_uow() as uow:
        record = uow.users.get_by_id(user_id)
        if record is None or not record.email:
            return False, "Authentication required.", "unauthorized"

        stored_hash = uow.users.get_password_hash(record.email)
        if not stored_hash or not verify_password(current, stored_hash):
            return False, "Current password is incorrect.", "current_password_invalid"

        uow.users.update_password_hash(user_id, hash_password(new))
        uow.users.bump_token_version(user_id)

    return True, None, None
