"""Phase 40A — super-admin user management guards and audit."""

from __future__ import annotations

import uuid

from worldcup_predictor.access.admin_gate import write_admin_audit_event
from worldcup_predictor.database.postgres.enums import UserRole
from worldcup_predictor.database.postgres.schemas import UserRecord
from worldcup_predictor.database.saas_factory import saas_uow


class UserManagementError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _ensure_super_admin_remains(exclude_user_id: uuid.UUID | None = None) -> None:
    with saas_uow() as uow:
        count = uow.users.count_by_role(UserRole.SUPER_ADMIN)
        if exclude_user_id is not None:
            user = uow.users.get_by_id(exclude_user_id)
            if user and user.role == UserRole.SUPER_ADMIN:
                count -= 1
        if count < 1:
            raise UserManagementError("At least one super_admin account must remain.", status_code=409)


def validate_role_change(
    *,
    actor_id: str,
    target: UserRecord,
    new_role: UserRole,
    confirm_self: bool = False,
) -> None:
    if target.role == UserRole.SUPER_ADMIN and new_role != UserRole.SUPER_ADMIN:
        _ensure_super_admin_remains(exclude_user_id=target.id)
    if str(target.id) == actor_id and target.role != new_role:
        if not confirm_self:
            raise UserManagementError("Confirmation required to change your own role.", status_code=409)
    if target.role == UserRole.SUPER_ADMIN and new_role == UserRole.USER:
        _ensure_super_admin_remains(exclude_user_id=target.id)


def validate_ban(*, actor_id: str, target: UserRecord, confirm_self: bool = False) -> None:
    if str(target.id) == actor_id and not confirm_self:
        raise UserManagementError("Confirmation required to ban your own account.", status_code=409)
    if target.role == UserRole.SUPER_ADMIN:
        _ensure_super_admin_remains(exclude_user_id=target.id)


def audit_user_event(event: str, *, actor_id: str, target_id: str, detail: str | None = None) -> None:
    write_admin_audit_event(event, user_id=actor_id, detail=f"target={target_id};{detail or ''}")
