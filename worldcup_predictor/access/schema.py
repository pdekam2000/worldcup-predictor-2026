"""SQLite DDL for Phase 49 access control tables."""

from __future__ import annotations

ACCESS_SCHEMA_VERSION = 2

ACCESS_DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS app_users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        access_token TEXT NOT NULL,
        created_at TEXT NOT NULL,
        is_anonymous INTEGER NOT NULL DEFAULT 0,
        last_login_at TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_app_users_email
    ON app_users(email)
    """,
    """
    CREATE TABLE IF NOT EXISTS user_usage_limits (
        user_id TEXT NOT NULL,
        usage_date TEXT NOT NULL,
        prediction_count INTEGER NOT NULL DEFAULT 0,
        last_prediction_at TEXT,
        PRIMARY KEY (user_id, usage_date),
        FOREIGN KEY (user_id) REFERENCES app_users(user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_entitlements (
        user_id TEXT PRIMARY KEY,
        plan TEXT NOT NULL DEFAULT 'free',
        paid INTEGER NOT NULL DEFAULT 0,
        paid_at TEXT,
        expires_at TEXT,
        provider TEXT,
        payment_reference TEXT,
        FOREIGN KEY (user_id) REFERENCES app_users(user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        fixture_id INTEGER,
        rating INTEGER NOT NULL,
        comment TEXT,
        prediction_context TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_user_feedback_created
    ON user_feedback(created_at DESC)
    """,
)
