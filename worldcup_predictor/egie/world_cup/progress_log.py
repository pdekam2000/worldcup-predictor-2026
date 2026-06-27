"""Flush-safe progress logging for long production runs — Phase 62C."""

from __future__ import annotations

import sys
import time
from typing import Any


def log_progress(message: str, *, flush: bool = True) -> None:
    print(message, flush=flush)


def log_fixture_progress(
    *,
    fixture_id: int,
    sportmonks_id: int,
    processed: int,
    total: int,
    api_calls: int,
    cache_hits: int,
    xg_found: int,
    xg_missing: int,
    lineups_found: int,
    lineups_missing: int,
    errors: int,
    started_at: float,
) -> None:
    elapsed = max(0.001, time.monotonic() - started_at)
    rate = processed / elapsed
    remaining = max(0, total - processed)
    eta_s = int(remaining / rate) if rate > 0 else 0
    eta_min = eta_s // 60
    log_progress(
        f"[phase62b] fixture={fixture_id} sm={sportmonks_id} "
        f"progress={processed}/{total} api_calls={api_calls} cache_hits={cache_hits} "
        f"xg={xg_found}/{xg_missing} lineups={lineups_found}/{lineups_missing} "
        f"errors={errors} eta_min={eta_min}"
    )
