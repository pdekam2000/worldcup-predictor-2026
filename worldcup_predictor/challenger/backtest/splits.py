"""Leakage-safe time splits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence


@dataclass(frozen=True)
class TimeSplit:
    train_ids: tuple[int, ...]
    validation_ids: tuple[int, ...]
    holdout_ids: tuple[int, ...]
    train_end: str | None
    validation_end: str | None
    holdout_end: str | None
    method: str = "expanding_60_20_20"


def chronological_split(
    rows: Sequence[dict[str, Any]],
    *,
    time_key: str = "kickoff_utc",
    id_key: str = "fixture_id",
    train_frac: float = 0.60,
    val_frac: float = 0.20,
) -> TimeSplit:
    ordered = sorted(rows, key=lambda r: str(r.get(time_key) or ""))
    n = len(ordered)
    i1 = int(n * train_frac)
    i2 = int(n * (train_frac + val_frac))
    train = ordered[:i1]
    val = ordered[i1:i2]
    hold = ordered[i2:]
    return TimeSplit(
        train_ids=tuple(int(r[id_key]) for r in train),
        validation_ids=tuple(int(r[id_key]) for r in val),
        holdout_ids=tuple(int(r[id_key]) for r in hold),
        train_end=str(train[-1].get(time_key)) if train else None,
        validation_end=str(val[-1].get(time_key)) if val else None,
        holdout_end=str(hold[-1].get(time_key)) if hold else None,
    )
