"""Unit of work — bundles PostgreSQL SaaS repositories per session."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.repositories import (
    AlertsRepository,
    FavoritesRepository,
    NotificationsRepository,
    PredictionHistoryRepository,
    SubscriptionsRepository,
    UserRepository,
    UserSettingsRepository,
)


@dataclass
class SaasUnitOfWork:
    session: Session
    users: UserRepository
    settings: UserSettingsRepository
    favorites: FavoritesRepository
    alerts: AlertsRepository
    notifications: NotificationsRepository
    subscriptions: SubscriptionsRepository
    prediction_history: PredictionHistoryRepository

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()


def build_uow(session: Session) -> SaasUnitOfWork:
    return SaasUnitOfWork(
        session=session,
        users=UserRepository(session),
        settings=UserSettingsRepository(session),
        favorites=FavoritesRepository(session),
        alerts=AlertsRepository(session),
        notifications=NotificationsRepository(session),
        subscriptions=SubscriptionsRepository(session),
        prediction_history=PredictionHistoryRepository(session),
    )
