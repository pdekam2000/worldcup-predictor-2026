"""EGIE runtime guards — external APIs allowed only during ingest jobs."""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)

_ingest_mode: contextvars.ContextVar[bool] = contextvars.ContextVar("egie_ingest_mode", default=False)
_backtest_mode: contextvars.ContextVar[bool] = contextvars.ContextVar("egie_backtest_mode", default=False)


def is_ingest_mode() -> bool:
    return bool(_ingest_mode.get())


def is_backtest_mode() -> bool:
    return bool(_backtest_mode.get())


def external_api_allowed(*, operation: str) -> bool:
    """Live provider HTTP is permitted only inside an EGIE ingest context."""
    if is_backtest_mode():
        logger.debug("egie_api_blocked backtest operation=%s", operation)
        return False
    if not is_ingest_mode():
        logger.debug("egie_api_blocked non_ingest operation=%s", operation)
        return False
    return True


@contextmanager
def ingest_mode() -> Iterator[None]:
    token = _ingest_mode.set(True)
    try:
        yield
    finally:
        _ingest_mode.reset(token)


@contextmanager
def backtest_mode() -> Iterator[None]:
    token = _backtest_mode.set(True)
    try:
        yield
    finally:
        _backtest_mode.reset(token)
