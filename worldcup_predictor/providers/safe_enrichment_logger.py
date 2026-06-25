"""Structured logging for optional prediction enrichments — Phase 44B."""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def log_enrichment_failure(
    module: str,
    exc: BaseException,
    *,
    fixture_id: int | None = None,
    layer: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log enrichment failure without interrupting prediction generation."""
    parts = [
        f"enrichment_failure module={module}",
        f"layer={layer or module}",
        f"fixture_id={fixture_id if fixture_id is not None else '-'}",
        f"error_type={type(exc).__name__}",
        f"error={exc}",
    ]
    if extra:
        for key, value in extra.items():
            parts.append(f"{key}={value}")
    logger.warning(" ".join(parts), exc_info=logger.isEnabledFor(logging.DEBUG))


def safe_enrichment_call(
    module: str,
    layer: str,
    func: Callable[..., T],
    *args: Any,
    fixture_id: int | None = None,
    **kwargs: Any,
) -> T | None:
    """Run enrichment step; log and return None on failure."""
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        log_enrichment_failure(module, exc, fixture_id=fixture_id, layer=layer)
        return None


def safe_enrichment_logger(
    module: str,
    layer: str,
    *,
    fixture_id: int | None = None,
) -> Callable[[BaseException], None]:
    """Return a callback for except blocks: `except Exception as exc: safe_enrichment_logger(...)(exc)`."""

    def _log(exc: BaseException) -> None:
        log_enrichment_failure(module, exc, fixture_id=fixture_id, layer=layer)

    return _log
