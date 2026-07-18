"""Challenger operational diagnostics."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator


@contextmanager
def timed(section: str) -> Iterator[dict[str, Any]]:
    box: dict[str, Any] = {"section": section}
    t0 = time.perf_counter()
    try:
        yield box
    finally:
        box["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)


def resource_snapshot() -> dict[str, Any]:
    try:
        import os
        import psutil  # type: ignore

        p = psutil.Process(os.getpid())
        return {
            "rss_mb": round(p.memory_info().rss / (1024 * 1024), 2),
            "cpu_percent": p.cpu_percent(interval=0.0),
        }
    except Exception:
        return {"rss_mb": None, "cpu_percent": None, "note": "psutil_unavailable"}
