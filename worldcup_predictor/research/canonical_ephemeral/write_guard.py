"""Write-protection guard for CANONICAL_RESEARCH_EPHEMERAL execution."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from worldcup_predictor.research.canonical_ephemeral.constants import (
    EXECUTION_MODE,
    PROTECTED_TABLES,
    PROTECTED_WRITE_OPS,
)

_EPHEMERAL_ACTIVE: ContextVar[bool] = ContextVar("canonical_research_ephemeral_active", default=False)
_ATTEMPTS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "canonical_research_ephemeral_write_attempts", default=None
)

_TABLE_RE = re.compile(
    r"\b(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+[\"`]?(\w+)[\"`]?",
    re.IGNORECASE,
)


class EphemeralWriteBlocked(RuntimeError):
    """Raised when ephemeral research execution attempts a prohibited canonical write."""

    def __init__(self, message: str, *, table: str | None = None, operation: str | None = None):
        super().__init__(message)
        self.table = table
        self.operation = operation


@dataclass
class WriteGuardState:
    active: bool = False
    attempts: list[dict[str, Any]] = field(default_factory=list)
    blocked_count: int = 0

    def record(self, *, table: str, operation: str, detail: str) -> None:
        self.attempts.append(
            {
                "table": table,
                "operation": operation,
                "detail": detail,
                "execution_mode": EXECUTION_MODE,
            }
        )
        self.blocked_count += 1


def ephemeral_mode_active() -> bool:
    return bool(_EPHEMERAL_ACTIVE.get())


def get_write_attempts() -> list[dict[str, Any]]:
    return list(_ATTEMPTS.get() or [])


def block_canonical_write(*, table: str, operation: str, detail: str = "") -> None:
    """Call from canonical write entry points. No-op unless ephemeral mode is active."""
    if not ephemeral_mode_active():
        return
    attempts = _ATTEMPTS.get()
    if attempts is not None:
        attempts.append(
            {
                "table": table,
                "operation": operation,
                "detail": detail,
                "execution_mode": EXECUTION_MODE,
            }
        )
    raise EphemeralWriteBlocked(
        f"EPHEMERAL_WRITE_BLOCKED: attempted {operation} on {table}"
        + (f" ({detail})" if detail else ""),
        table=table,
        operation=operation,
    )


def _sql_write_target(sql: str) -> tuple[str, str] | None:
    text = " ".join(str(sql or "").split())
    if not text:
        return None
    first = text.split(None, 1)[0].upper()
    if first not in PROTECTED_WRITE_OPS and not text.upper().startswith("INSERT"):
        return None
    m = _TABLE_RE.search(text)
    if not m:
        return None
    table = m.group(1)
    op = "INSERT" if text.upper().startswith("INSERT") or text.upper().startswith("REPLACE") else first
    if table in PROTECTED_TABLES:
        return op, table
    return None


class GuardedConnection:
    """sqlite3.Connection proxy that blocks prohibited writes while ephemeral mode is active."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql, parameters=()):
        hit = _sql_write_target(sql)
        if hit and ephemeral_mode_active():
            op, table = hit
            block_canonical_write(table=table, operation=op, detail=str(sql)[:180])
        return self._conn.execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        hit = _sql_write_target(sql)
        if hit and ephemeral_mode_active():
            op, table = hit
            block_canonical_write(table=table, operation=op, detail=str(sql)[:180])
        return self._conn.executemany(sql, seq_of_parameters)

    def executescript(self, sql_script):
        # Block scripts that touch protected tables while ephemeral
        for stmt in str(sql_script or "").split(";"):
            hit = _sql_write_target(stmt)
            if hit and ephemeral_mode_active():
                op, table = hit
                block_canonical_write(table=table, operation=op, detail=stmt[:180])
        return self._conn.executescript(sql_script)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


@contextmanager
def ephemeral_write_guard() -> Iterator[WriteGuardState]:
    """Activate ephemeral write protection for the current context."""
    state = WriteGuardState(active=True)
    token = _EPHEMERAL_ACTIVE.set(True)
    attempts: list[dict[str, Any]] = []
    attempts_token = _ATTEMPTS.set(attempts)
    try:
        yield state
    finally:
        state.attempts = list(attempts)
        state.blocked_count = len(attempts)
        _ATTEMPTS.reset(attempts_token)
        _EPHEMERAL_ACTIVE.reset(token)
