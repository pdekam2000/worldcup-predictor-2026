"""Phase A23 — rolling market accuracy statistics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.lifecycle.config import MARKET_WINDOWS
from worldcup_predictor.lifecycle.store import LifecycleStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _window_cutoff(window_key: str) -> datetime | None:
    now = _utc_now()
    if window_key == "7d":
        return now - timedelta(days=7)
    if window_key == "30d":
        return now - timedelta(days=30)
    if window_key == "90d":
        return now - timedelta(days=90)
    return None


def rebuild_market_accuracy_rollups(*, store: LifecycleStore | None = None) -> dict[str, Any]:
    owned = store is None
    store = store or LifecycleStore()
    try:
        rows = store._conn.execute(  # noqa: SLF001
            """
            SELECT market_id, result, confidence, bet_quality_score, odds, evaluated_at
            FROM prediction_market_evaluations
            """
        ).fetchall()

        by_market_window: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            market_id = str(item["market_id"])
            for window in MARKET_WINDOWS:
                cutoff = _window_cutoff(window)
                if cutoff is not None:
                    try:
                        ev_at = datetime.fromisoformat(str(item["evaluated_at"]).replace("Z", ""))
                        if ev_at < cutoff:
                            continue
                    except ValueError:
                        continue
                by_market_window.setdefault((market_id, window), []).append(item)

        updated = 0
        for (market_id, window), items in by_market_window.items():
            predictions = len(items)
            correct = sum(1 for i in items if str(i.get("result")) == "correct")
            wrong = sum(1 for i in items if str(i.get("result")) == "wrong")
            pending = sum(1 for i in items if str(i.get("result")) == "pending")
            push_count = sum(1 for i in items if str(i.get("result")) == "push")
            void_count = sum(1 for i in items if str(i.get("result")) in {"void", "unavailable", "unknown"})

            decided = correct + wrong
            accuracy = (correct / decided) if decided > 0 else None

            conf_vals = [float(i["confidence"]) for i in items if i.get("confidence") is not None]
            bq_vals = [float(i["bet_quality_score"]) for i in items if i.get("bet_quality_score") is not None]
            odds_vals = [float(i["odds"]) for i in items if i.get("odds") is not None]

            roi = None
            if odds_vals and decided > 0:
                roi = ((correct * (sum(odds_vals) / len(odds_vals) - 1)) - wrong) / decided

            store.upsert_accuracy_rollup(
                market_id=market_id,
                window_key=window,
                predictions=predictions,
                correct=correct,
                wrong=wrong,
                pending=pending,
                push_count=push_count,
                void_count=void_count,
                accuracy=accuracy,
                roi=roi,
                avg_confidence=(sum(conf_vals) / len(conf_vals)) if conf_vals else None,
                avg_bet_quality=(sum(bq_vals) / len(bq_vals)) if bq_vals else None,
                avg_odds=(sum(odds_vals) / len(odds_vals)) if odds_vals else None,
            )
            updated += 1

        return {"status": "ok", "rollups_updated": updated}
    finally:
        if owned:
            store.close()
