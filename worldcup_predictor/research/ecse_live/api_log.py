"""PHASE ECSE-LIVE-1 — API call audit log (internal)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL

PHASE = "ECSE-LIVE-1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_api_log_table(conn: sqlite3.Connection) -> None:
    for ddl in PHASE_ECSE_LIVE_DDL:
        if "ecse_live_api_log" in ddl:
            conn.execute(ddl)
    conn.commit()


@dataclass
class ApiCallTracker:
    calls: int = 0
    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self,
        conn: sqlite3.Connection | None,
        *,
        provider: str,
        endpoint: str,
        entity_key: str | None,
        action: str,
        status: str,
        details: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> None:
        self.calls += 1
        entry = {
            "provider": provider,
            "endpoint": endpoint,
            "entity_key": entity_key,
            "action": action,
            "status": status,
            "details": details or {},
            "created_at": _utc_now(),
        }
        self.entries.append(entry)
        if conn is not None and persist:
            ensure_api_log_table(conn)
            conn.execute(
                """
                INSERT INTO ecse_live_api_log (
                    phase, provider, endpoint, entity_key, action, status, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    PHASE,
                    provider,
                    endpoint,
                    entity_key,
                    action,
                    status,
                    json.dumps(details or {}, default=str),
                    entry["created_at"],
                ),
            )
            conn.commit()

    def to_dict(self) -> dict[str, Any]:
        return {"api_calls": self.calls, "entries": self.entries[-100:]}
