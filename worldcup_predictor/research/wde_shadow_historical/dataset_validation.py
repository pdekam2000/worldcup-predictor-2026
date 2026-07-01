"""Part C — Validate WDE shadow training dataset."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.research.wde_shadow_historical.constants import (
    DATASET_PATH,
    DATASET_SUMMARY,
    MIN_SHADOW_TRAINING_ROWS,
    PHASE,
    READINESS_ARTIFACT,
)
from worldcup_predictor.research.wde_shadow_historical.helpers import table_count, table_exists


@dataclass
class DatasetValidationResult:
    phase: str = PHASE
    validated_at_utc: str = ""
    passed: bool = False
    checks: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    production_tables_unchanged: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "validated_at_utc": self.validated_at_utc,
            "passed": self.passed,
            "checks": self.checks,
            "row_count": self.row_count,
            "production_tables_unchanged": self.production_tables_unchanged,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"check": name, "passed": ok, "detail": detail}


def validate_shadow_dataset(
    conn: sqlite3.Connection,
    *,
    wde_before: int | None = None,
    odds_before: int | None = None,
) -> DatasetValidationResult:
    result = DatasetValidationResult(validated_at_utc=_utc_now())
    checks: list[dict[str, Any]] = []

    checks.append(_check("dataset_exists", DATASET_PATH.exists(), str(DATASET_PATH)))
    checks.append(_check("summary_exists", DATASET_SUMMARY.exists(), str(DATASET_SUMMARY)))
    checks.append(_check("readiness_report_exists", READINESS_ARTIFACT.exists(), str(READINESS_ARTIFACT)))

    if not DATASET_PATH.exists():
        result.checks = checks
        result.passed = False
        return result

    df = pd.read_parquet(DATASET_PATH)
    result.row_count = len(df)

    checks.append(_check("enough_rows_for_training", result.row_count >= MIN_SHADOW_TRAINING_ROWS, str(result.row_count)))
    checks.append(_check("no_duplicate_row_hash", df["row_hash"].is_unique, f"dupes={df['row_hash'].duplicated().sum()}"))

    valid_1x2 = set(df["label_1x2"].dropna().unique()) <= {"home_win", "draw", "away_win"}
    checks.append(_check("labels_1x2_valid", valid_1x2, str(sorted(df["label_1x2"].dropna().unique()[:5]))))

    valid_ou = set(df["label_over_2_5"].dropna().unique()) <= {"over_2_5", "under_2_5"}
    checks.append(_check("labels_ou_valid", valid_ou, ""))

    valid_btts = set(df["label_btts"].dropna().unique()) <= {"yes", "no"}
    checks.append(_check("labels_btts_valid", valid_btts, ""))

    today = datetime.now(timezone.utc).date().isoformat()
    future = int((df["date"].astype(str) > today).sum()) if "date" in df.columns else 0
    checks.append(_check("no_future_matches", future == 0, f"future={future}"))

    odds_cols = [c for c in df.columns if c.startswith("oddsFT_")]
    invalid_odds = 0
    for col in odds_cols:
        invalid_odds += int((df[col].notna() & (df[col] <= 1.0)).sum())
    checks.append(_check("no_invalid_odds", invalid_odds == 0, f"invalid={invalid_odds}"))

    missing_source = int(df["source_match_id"].isna().sum()) if "source_match_id" in df.columns else 0
    checks.append(_check("source_trace_preserved", missing_source == 0, f"missing={missing_source}"))

    wde_after = table_count(conn, "worldcup_stored_predictions") if table_exists(conn, "worldcup_stored_predictions") else 0
    odds_after = table_count(conn, "odds_snapshots") if table_exists(conn, "odds_snapshots") else 0
    if wde_before is not None:
        checks.append(_check("no_wde_production_writes", wde_after == wde_before, f"before={wde_before} after={wde_after}"))
    if odds_before is not None:
        checks.append(_check("no_odds_snapshots_writes", odds_after == odds_before, f"before={odds_before} after={odds_after}"))

    result.production_tables_unchanged = all(
        c["passed"] for c in checks if c["check"] in ("no_wde_production_writes", "no_odds_snapshots_writes")
    ) or (wde_before is None and odds_before is None)

    result.checks = checks
    result.passed = all(c["passed"] for c in checks)
    return result
