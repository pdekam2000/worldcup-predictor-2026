"""PostgreSQL favorites repository."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.enums import FavoriteType
from worldcup_predictor.database.postgres.models import UserFavorite
from worldcup_predictor.database.postgres.schemas import FavoriteRecord


def _to_record(row: UserFavorite) -> FavoriteRecord:
    return FavoriteRecord(
        id=row.id,
        user_id=row.user_id,
        type=row.type,
        item_id=row.item_id,
        item_name=row.item_name,
        item_meta=dict(row.item_meta) if row.item_meta else None,
        created_at=row.created_at,
    )


class FavoritesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_user(self, user_id: uuid.UUID, *, limit: int = 100) -> list[FavoriteRecord]:
        rows = self._session.scalars(
            select(UserFavorite)
            .where(UserFavorite.user_id == user_id)
            .order_by(UserFavorite.created_at.desc())
            .limit(limit)
        ).all()
        return [_to_record(row) for row in rows]

    def add(
        self,
        user_id: uuid.UUID,
        *,
        type: FavoriteType,
        item_id: str,
        item_name: str,
        item_meta: dict[str, Any] | None = None,
    ) -> FavoriteRecord:
        row = UserFavorite(
            user_id=user_id,
            type=type,
            item_id=item_id,
            item_name=item_name,
            item_meta=item_meta,
        )
        self._session.add(row)
        self._session.flush()
        return _to_record(row)

    def delete(self, user_id: uuid.UUID, favorite_id: uuid.UUID) -> bool:
        row = self._session.get(UserFavorite, favorite_id)
        if row is None or row.user_id != user_id:
            return False
        self._session.delete(row)
        self._session.flush()
        return True
