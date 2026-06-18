"""PostgreSQL SaaS repository implementations."""

from worldcup_predictor.database.postgres.repositories.alerts import AlertsRepository
from worldcup_predictor.database.postgres.repositories.favorites import FavoritesRepository
from worldcup_predictor.database.postgres.repositories.notifications import NotificationsRepository
from worldcup_predictor.database.postgres.repositories.prediction_history import PredictionHistoryRepository
from worldcup_predictor.database.postgres.repositories.settings import UserSettingsRepository
from worldcup_predictor.database.postgres.repositories.subscriptions import SubscriptionsRepository
from worldcup_predictor.database.postgres.repositories.users import UserRepository

__all__ = [
    "AlertsRepository",
    "FavoritesRepository",
    "NotificationsRepository",
    "PredictionHistoryRepository",
    "SubscriptionsRepository",
    "UserRepository",
    "UserSettingsRepository",
]
