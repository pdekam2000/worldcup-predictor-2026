"""PostgreSQL enum definitions for SaaS tables."""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class FavoriteType(str, enum.Enum):
    TEAM = "team"
    LEAGUE = "league"
    MATCH = "match"


class AlertType(str, enum.Enum):
    NEW_PREDICTION = "new_prediction"
    HIGH_CONFIDENCE = "high_confidence"
    MATCH_RESULT = "match_result"
    SYSTEM = "system"


class NotificationType(str, enum.Enum):
    PREDICTION = "prediction"
    SYSTEM = "system"
    SUBSCRIPTION = "subscription"
    ACCURACY = "accuracy"


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ELITE = "elite"
    UNLIMITED = "unlimited"


class BillingCycle(str, enum.Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"


class PredictionResult(str, enum.Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PENDING = "pending"


class Prediction1x2(str, enum.Enum):
    HOME = "home"
    DRAW = "draw"
    AWAY = "away"
