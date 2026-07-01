"""DDL for staged OddAlerts inbox CSV catalog (no odds snapshot promotion)."""

ODDALERTS_INBOX_CATALOG_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS oddalerts_inbox_csv_catalog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file TEXT NOT NULL,
        source_sha256 TEXT NOT NULL UNIQUE,
        csv_type TEXT NOT NULL,
        market TEXT,
        outcome TEXT,
        date_from TEXT,
        date_to TEXT,
        row_count INTEGER NOT NULL DEFAULT 0,
        gmail_message_id TEXT,
        import_status TEXT NOT NULL,
        error TEXT,
        cataloged_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oddalerts_inbox_csv_type
    ON oddalerts_inbox_csv_catalog(csv_type, import_status)
    """,
)


def ensure_oddalerts_inbox_catalog_tables(conn) -> None:
    for ddl in ODDALERTS_INBOX_CATALOG_DDL:
        conn.execute(ddl)
