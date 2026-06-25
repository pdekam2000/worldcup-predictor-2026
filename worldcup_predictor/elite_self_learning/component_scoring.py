"""Part C — rolling component scoring."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.elite_self_learning.models import ROLLING_WINDOWS, ComponentScore


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def compute_rolling_scores(
    evaluations: list[dict[str, Any]],
    *,
    windows: tuple[int, ...] = ROLLING_WINDOWS,
) -> list[ComponentScore]:
    """Aggregate help/hurt/hit rates per component, market, league, and window."""
    # Flatten attribution rows with context
    rows: list[dict[str, Any]] = []
    for ev in evaluations:
        league_id = ev.get("league_id")
        for m in ev.get("markets") or []:
            market_id = m.get("market_id")
            reality = m.get("reality")
            for a in ev.get("attributions") or []:
                if a.get("component_id") == "hybrid_confidence_engine":
                    continue
                rows.append(
                    {
                        "component_id": a.get("component_id"),
                        "market_id": market_id,
                        "league_id": league_id,
                        "helped": bool(a.get("helped")),
                        "hurt": bool(a.get("hurt")),
                        "confidence": float(a.get("confidence") or 0),
                        "hit": _component_hit(a, reality),
                    }
                )

    scores: list[ComponentScore] = []
    grouped: dict[tuple[str, str, int | None], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[(r["component_id"], r["market_id"], r["league_id"])].append(r)

    for (cid, market_id, league_id), bucket in grouped.items():
        for window in windows:
            slice_rows = bucket[-window:]
            n = len(slice_rows)
            if n == 0:
                continue
            hits = sum(1 for r in slice_rows if r["hit"])
            helped = sum(1 for r in slice_rows if r["helped"])
            hurt = sum(1 for r in slice_rows if r["hurt"])
            mean_conf = sum(r["confidence"] for r in slice_rows) / n
            scores.append(
                ComponentScore(
                    component_id=cid,
                    market_id=market_id,
                    league_id=league_id,
                    window=window,
                    n=n,
                    hit_rate=_rate(hits, n),
                    help_rate=_rate(helped, n),
                    hurt_rate=_rate(hurt, n),
                    mean_confidence=round(mean_conf, 4),
                )
            )
    return scores


def _component_hit(attribution: dict[str, Any], reality: Any) -> bool:
    pred = attribution.get("prediction")
    if pred is None or reality is None:
        return False
    if isinstance(pred, list):
        return str(reality) in [str(p) for p in pred]
    return str(pred).lower() == str(reality).lower()


def league_rollup(scores: list[ComponentScore]) -> list[ComponentScore]:
    """Aggregate across leagues for each component/market/window."""
    buckets: dict[tuple[str, str, int], list[ComponentScore]] = defaultdict(list)
    for s in scores:
        if s.league_id is not None:
            buckets[(s.component_id, s.market_id, s.window)].append(s)

    rolled: list[ComponentScore] = []
    for (cid, market_id, window), items in buckets.items():
        n = sum(i.n for i in items)
        if n == 0:
            continue
        hits = sum(i.hit_rate * i.n for i in items)
        helped = sum(i.help_rate * i.n for i in items)
        hurt = sum(i.hurt_rate * i.n for i in items)
        conf = sum(i.mean_confidence * i.n for i in items)
        rolled.append(
            ComponentScore(
                component_id=cid,
                market_id=market_id,
                league_id=None,
                window=window,
                n=n,
                hit_rate=round(hits / n, 4),
                help_rate=round(helped / n, 4),
                hurt_rate=round(hurt / n, 4),
                mean_confidence=round(conf / n, 4),
            )
        )
    return rolled
