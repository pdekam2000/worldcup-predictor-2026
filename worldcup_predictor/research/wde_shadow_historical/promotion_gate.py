"""Part E — Validation gate + final recommendation (no auto-promote)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.wde_shadow_historical.constants import (
    BACKTEST_ARTIFACT,
    METRICS_ARTIFACT,
    MIN_TEST_ROWS,
    PHASE,
    SPLIT_ARTIFACT,
    TRAINING_BACKTEST_REPORT,
    VALIDATION_ARTIFACT,
)
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _production_counts(conn) -> dict[str, int]:
    return {
        "worldcup_stored_predictions": table_count(conn, "worldcup_stored_predictions")
        if table_exists(conn, "worldcup_stored_predictions")
        else 0,
        "odds_snapshots": table_count(conn, "odds_snapshots") if table_exists(conn, "odds_snapshots") else 0,
    }


def derive_final_recommendation(
    *,
    backtest: dict[str, Any],
    metrics: dict[str, Any],
    split: dict[str, Any],
) -> str:
    if metrics.get("status") == "skipped":
        return "DO_NOT_PROMOTE_MODEL"

    test_rows = int((split.get("test") or {}).get("count", 0))
    if test_rows < MIN_TEST_ROWS:
        return "NEED_MORE_RECENT_DATA"

    test_cmp = (backtest.get("comparison") or {}).get("test") or {}
    val_cmp = (backtest.get("comparison") or {}).get("validation") or {}

    def _beats_book(cmp: dict) -> bool:
        wins = 0
        for m in ("1x2", "ou25", "btts"):
            s = (cmp.get(m) or {}).get("shadow")
            b = (cmp.get(m) or {}).get("bookmaker")
            if s is not None and b is not None and s > b:
                wins += 1
        return wins >= 2

    def _beats_wde(cmp: dict) -> bool:
        for m in ("1x2", "ou25", "btts"):
            s = (cmp.get(m) or {}).get("shadow")
            w = (cmp.get(m) or {}).get("current_wde")
            if s is not None and w is not None and s > w:
                return True
        return False

    def _market_wins(cmp: dict) -> list[str]:
        wins = []
        for m in ("1x2", "ou25", "btts"):
            s = (cmp.get(m) or {}).get("shadow")
            b = (cmp.get(m) or {}).get("bookmaker")
            if s is not None and b is not None and s > b:
                wins.append(m)
        return wins

    if _beats_wde(test_cmp):
        return "SHADOW_MODEL_BEATS_CURRENT_WDE"
    if _beats_book(test_cmp):
        return "SHADOW_MODEL_BEATS_BOOKMAKER_BASELINE"

    market_wins = _market_wins(test_cmp)
    if market_wins:
        return "SHADOW_MODEL_USEFUL_FOR_SPECIFIC_MARKETS"

    train_acc = (metrics.get("markets") or {}).get("1x2", {}).get("val_accuracy")
    test_acc = (test_cmp.get("1x2") or {}).get("shadow")
    if train_acc is not None and test_acc is not None and train_acc - test_acc > 0.08:
        return "NEED_FEATURE_ENGINEERING"

    val_book = _beats_book(val_cmp)
    test_book = _beats_book(test_cmp)
    if val_book and not test_book:
        return "NEED_FEATURE_ENGINEERING"

    return "SHADOW_MODEL_NOT_BETTER"


def validate_promotion_gate(
    split: dict[str, Any],
    metrics: dict[str, Any],
    backtest: dict[str, Any],
    *,
    model_dir: Path | None = None,
    production_before: dict[str, int] | None = None,
    require_report: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": ok, "detail": detail})

    chk("split_artifact", SPLIT_ARTIFACT.exists())
    chk("metrics_artifact", METRICS_ARTIFACT.exists())
    chk("backtest_artifact", BACKTEST_ARTIFACT.exists())
    if require_report:
        chk("training_backtest_report", TRAINING_BACKTEST_REPORT.exists())

    verification = split.get("verification") or {}
    chk("no_leakage_strict_time_order", bool(verification.get("strict_time_order")))
    chk("no_duplicate_row_hash", bool(verification.get("no_duplicate_row_hash")))
    chk("no_future_rows", bool(verification.get("no_future_rows")))
    chk("labels_valid", bool(verification.get("labels_valid")))

    test_count = int((split.get("test") or {}).get("count", 0))
    chk("test_sample_sufficient", test_count >= MIN_TEST_ROWS, f"test_rows={test_count}")

    mdir = model_dir or Path(metrics.get("model_dir", ""))
    model_files = list(mdir.glob("shadow_*.joblib")) if mdir.exists() else []
    chk("model_artifacts_saved", len(model_files) >= 3, f"found={len(model_files)}")

    train_acc = (metrics.get("markets") or {}).get("1x2", {}).get("val_accuracy")
    test_acc = ((backtest.get("comparison") or {}).get("test") or {}).get("1x2", {}).get("shadow")
    gap = (train_acc - test_acc) if train_acc is not None and test_acc is not None else None
    chk("no_suspicious_train_test_gap", gap is None or gap < 0.12, f"gap={gap}")

    if production_before:
        try:
            from worldcup_predictor.config.settings import get_settings

            conn = connect_readonly(get_settings().sqlite_path)
            after = _production_counts(conn)
            conn.close()
            for table, before in production_before.items():
                chk(
                    f"production_{table}_unchanged",
                    after.get(table) == before,
                    f"before={before} after={after.get(table)}",
                )
        except Exception as exc:
            chk("production_tables_unchanged", False, str(exc))

    recommendation = derive_final_recommendation(backtest=backtest, metrics=metrics, split=split)

    out = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "checks": checks,
        "passed": sum(1 for c in checks if c["passed"]),
        "failed": sum(1 for c in checks if not c["passed"]),
        "promotion_allowed": False,
        "final_recommendation": recommendation,
    }
    VALIDATION_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_ARTIFACT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
