"""PostgreSQL SaaS repository implementations."""

from worldcup_predictor.database.postgres.repositories.alerts import AlertsRepository
from worldcup_predictor.database.postgres.repositories.billing_invoices import BillingInvoicesRepository
from worldcup_predictor.database.postgres.repositories.favorites import FavoritesRepository
from worldcup_predictor.database.postgres.repositories.notifications import NotificationsRepository
from worldcup_predictor.database.postgres.repositories.prediction_history import PredictionHistoryRepository
from worldcup_predictor.database.postgres.repositories.settings import UserSettingsRepository
from worldcup_predictor.database.postgres.repositories.subscriptions import SubscriptionsRepository
from worldcup_predictor.database.postgres.repositories.users import UserRepository
from worldcup_predictor.database.postgres.repositories.webhook_events import WebhookEventsRepository

__all__ = [
    "AlertsRepository",
    "BillingInvoicesRepository",
    "FavoritesRepository",
    "NotificationsRepository",
    "PredictionHistoryRepository",
    "SubscriptionsRepository",
    "UserRepository",
    "UserSettingsRepository",
    "WebhookEventsRepository",
]
