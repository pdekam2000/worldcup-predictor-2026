"""Unit of work — bundles PostgreSQL SaaS repositories per session."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.repositories import (
    AlertsRepository,
    BillingInvoicesRepository,
    FavoritesRepository,
    NotificationsRepository,
    PredictionHistoryRepository,
    SubscriptionsRepository,
    UserRepository,
    UserSettingsRepository,
    WebhookEventsRepository,
)
from worldcup_predictor.database.postgres.repositories.email_verification import EmailVerificationRepository
from worldcup_predictor.database.postgres.repositories.password_reset import PasswordResetRepository


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
    email_verification: EmailVerificationRepository
    password_reset: PasswordResetRepository
    webhook_events: WebhookEventsRepository
    billing_invoices: BillingInvoicesRepository

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
        email_verification=EmailVerificationRepository(session),
        password_reset=PasswordResetRepository(session),
        webhook_events=WebhookEventsRepository(session),
        billing_invoices=BillingInvoicesRepository(session),
    )
