"""Part E — elite_learning_store knowledge persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STORE_DIR = ROOT / "data" / "shadow" / "elite_learning_store"
EVALUATIONS_PATH = STORE_DIR / "post_match_evaluations.jsonl"
PATTERNS_PATH = STORE_DIR / "patterns.json"
COMPONENT_HEALTH_PATH = STORE_DIR / "component_health.json"
MARKET_HEALTH_PATH = STORE_DIR / "market_health.json"
LEAGUE_HEALTH_PATH = STORE_DIR / "league_health.json"
CALIBRATION_PATH = STORE_DIR / "confidence_calibration.json"
WEIGHTS_PATH = STORE_DIR / "adaptive_weight_recommendations.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EliteLearningStore:
    """Shadow knowledge store — no production writes."""

    base_dir: Path = STORE_DIR

    def ensure_dirs(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def append_evaluation(self, record: dict[str, Any]) -> None:
        self.ensure_dirs()
        with EVALUATIONS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    def write_snapshot(self, name: str, payload: dict[str, Any]) -> Path:
        self.ensure_dirs()
        path = self.base_dir / f"{name}.json"
        payload = {"generated_at": _utc_now(), **payload}
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def save_knowledge(
        self,
        *,
        patterns: dict[str, Any],
        component_health: dict[str, Any],
        market_health: dict[str, Any],
        league_health: dict[str, Any],
        calibration: dict[str, Any],
        weight_recommendations: list[dict[str, Any]],
    ) -> dict[str, str]:
        self.ensure_dirs()
        paths = {
            "patterns": self.write_snapshot("patterns", patterns),
            "component_health": self.write_snapshot("component_health", component_health),
            "market_health": self.write_snapshot("market_health", market_health),
            "league_health": self.write_snapshot("league_health", league_health),
            "calibration": self.write_snapshot("confidence_calibration", calibration),
        }
        weights_payload = {"generated_at": _utc_now(), "recommendations": weight_recommendations}
        WEIGHTS_PATH.write_text(json.dumps(weights_payload, indent=2), encoding="utf-8")
        paths["weights"] = str(WEIGHTS_PATH)
        return {k: str(v) for k, v in paths.items()}


def build_component_health(scores: list[Any]) -> dict[str, Any]:
    by_comp: dict[str, list[dict[str, Any]]] = {}
    for s in scores:
        if s.window != 100 or s.league_id is not None:
            continue
        by_comp.setdefault(s.component_id, []).append(s.to_dict())
    health: dict[str, Any] = {}
    for cid, rows in by_comp.items():
        avg_help = sum(r["help_rate"] for r in rows) / len(rows) if rows else 0
        avg_hurt = sum(r["hurt_rate"] for r in rows) / len(rows) if rows else 0
        status = "healthy" if avg_help > avg_hurt + 0.05 else ("degraded" if avg_hurt > avg_help + 0.05 else "stable")
        health[cid] = {"status": status, "markets": rows, "avg_help_rate": round(avg_help, 4), "avg_hurt_rate": round(avg_hurt, 4)}
    return health


def build_market_health(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, int]] = {}
    tier_hits: dict[str, dict[str, int]] = {}
    for ev in evaluations:
        for m in ev.get("markets") or []:
            mk = m.get("market_id")
            out = m.get("outcome")
            tier = m.get("tier") or "C"
            b = buckets.setdefault(mk, {"correct": 0, "incorrect": 0, "total": 0})
            b["total"] += 1
            if out == "correct":
                b["correct"] += 1
            else:
                b["incorrect"] += 1
            th = tier_hits.setdefault(mk, {}).setdefault(tier, {"correct": 0, "total": 0})
            th["total"] += 1
            if out == "correct":
                th["correct"] += 1

    health: dict[str, Any] = {}
    for mk, b in buckets.items():
        acc = round(b["correct"] / b["total"], 4) if b["total"] else 0
        tiers = {
            t: round(v["correct"] / v["total"], 4) if v["total"] else 0
            for t, v in tier_hits.get(mk, {}).items()
        }
        health[mk] = {"accuracy": acc, "n": b["total"], "tier_accuracy": tiers}
    return health


def build_league_health(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, int]] = {}
    for ev in evaluations:
        lid = str(ev.get("league_id") or "unknown")
        for m in ev.get("markets") or []:
            if m.get("market_id") != "first_goal_team":
                continue
            key = lid
            b = buckets.setdefault(key, {"correct": 0, "total": 0})
            b["total"] += 1
            if m.get("outcome") == "correct":
                b["correct"] += 1
    return {
        lid: {"fgt_accuracy": round(v["correct"] / v["total"], 4) if v["total"] else 0, "n": v["total"]}
        for lid, v in buckets.items()
    }


def build_calibration(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    bins: dict[str, list[tuple[float, int]]] = {}
    for ev in evaluations:
        for m in ev.get("markets") or []:
            mk = m.get("market_id")
            conf = float(m.get("confidence") or 0)
            hit = 1 if m.get("outcome") == "correct" else 0
            bins.setdefault(mk, []).append((conf, hit))

    out: dict[str, Any] = {}
    for mk, pairs in bins.items():
        if not pairs:
            continue
        brier = sum((p - y) ** 2 for p, y in pairs) / len(pairs)
        mean_conf = sum(p for p, _ in pairs) / len(pairs)
        mean_hit = sum(y for _, y in pairs) / len(pairs)
        out[mk] = {
            "n": len(pairs),
            "brier": round(brier, 4),
            "mean_confidence": round(mean_conf, 4),
            "mean_hit_rate": round(mean_hit, 4),
            "calibration_gap": round(mean_hit - mean_conf, 4),
        }
    return out


def build_patterns(scores: list[Any], recommendations: list[Any]) -> dict[str, Any]:
    top_help = sorted(
        [s for s in scores if s.window == 100 and s.league_id is None],
        key=lambda s: s.help_rate - s.hurt_rate,
        reverse=True,
    )[:5]
    top_hurt = sorted(
        [s for s in scores if s.window == 100 and s.league_id is None],
        key=lambda s: s.hurt_rate - s.help_rate,
        reverse=True,
    )[:5]
    return {
        "top_outperformers": [s.to_dict() for s in top_help],
        "top_underperformers": [s.to_dict() for s in top_hurt],
        "pending_weight_shifts": [r.to_dict() for r in recommendations if r.direction != "hold"],
    }
