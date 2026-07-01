"""PHASE ECSE-X2-M7 — Live shadow collection and evaluation watch."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT, SHADOW_ARTIFACT
from worldcup_predictor.research.ecse_x2_m6.store import _artifact_path


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def aggregate_shadow_collection(*, since_generated_at: str | None = None) -> dict[str, Any]:
    rows = _load_jsonl(_artifact_path(SHADOW_ARTIFACT))
    if since_generated_at:
        rows = [r for r in rows if (r.get("generated_at") or "") >= since_generated_at]

    exclusions = Counter()
    for r in rows:
        if not r.get("applied"):
            exclusions[str(r.get("exclusion_reason") or "unknown")] += 1

    dup_keys: set[str] = set()
    dup_count = 0
    for r in rows:
        key = f"{r.get('fixture_id')}|{r.get('odds_snapshot_id') or 'na'}|{r.get('method_version')}"
        if key in dup_keys:
            dup_count += 1
        dup_keys.add(key)

    strong = sum(1 for r in rows if r.get("strong_segment"))
    balanced_excl = exclusions.get("balanced_match", 0)
    missing_odds = exclusions.get("missing_ft_home", 0) + exclusions.get("invalid_odds_snapshot", 0)

    return {
        "total_rows": len(rows),
        "applied": sum(1 for r in rows if r.get("applied")),
        "excluded": sum(1 for r in rows if not r.get("applied")),
        "exclusion_reasons": dict(exclusions),
        "strong_home_prob_ge_60": strong,
        "balanced_excluded": balanced_excl,
        "missing_odds": missing_odds,
        "pending_evaluation": sum(1 for r in rows if r.get("evaluation_status") == "pending"),
        "public_output_changed_false": all(r.get("public_output_changed") is False for r in rows),
        "duplicate_row_keys": dup_count,
        "membership_checks": _membership_checks(rows),
    }


def _membership_checks(rows: list[dict[str, Any]]) -> dict[str, int]:
    ok = 0
    bad = 0
    for r in rows:
        base = {x.get("scoreline") for x in (r.get("baseline_top10") or [])}
        enh = {x.get("scoreline") for x in (r.get("enhanced_top10") or [])}
        if base == enh:
            ok += 1
        else:
            bad += 1
    return {"membership_ok": ok, "membership_bad": bad}


def aggregate_evaluation_watch() -> dict[str, Any]:
    evals = _load_jsonl(_artifact_path(EVAL_ARTIFACT))
    if not evals:
        return {"count": 0}

    def _rate(top_key: str) -> dict[str, float]:
        base_hits = sum(1 for e in evals if (e.get("baseline_hits") or {}).get(top_key))
        enh_hits = sum(1 for e in evals if (e.get("enhanced_hits") or {}).get(top_key))
        n = len(evals)
        return {
            "baseline_pct": round(100.0 * base_hits / n, 4),
            "enhanced_pct": round(100.0 * enh_hits / n, 4),
            "delta_pp": round(100.0 * (enh_hits - base_hits) / n, 4),
        }

    segment_stats: dict[str, Any] = {}
    for label in ("home_ge_60", "home_ge_55", "balanced_control", "strong_home_favorite"):
        seg = [e for e in evals if label in (e.get("segment_labels") or [])]
        if not seg:
            continue
        segment_stats[label] = {
            "n": len(seg),
            "top5_delta_pp": round(
                sum(int((e.get("delta") or {}).get("top5", 0)) for e in seg) / len(seg) * 100, 4
            ),
            "top3_delta_pp": round(
                sum(int((e.get("delta") or {}).get("top3", 0)) for e in seg) / len(seg) * 100, 4
            ),
        }

    return {
        "count": len(evals),
        "top1": _rate("hit_top1"),
        "top3": _rate("hit_top3"),
        "top5": _rate("hit_top5"),
        "top10": _rate("hit_top10"),
        "segment_stats": segment_stats,
        "applied_only_n": sum(1 for e in evals if e.get("applied")),
    }
