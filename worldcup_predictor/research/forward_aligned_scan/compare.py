"""Baseline vs fresh scan comparison (research-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.research.forward_aligned_scan.constants import ARTIFACT_ROOT, TIER_A, TIER_B, TIER_S
from worldcup_predictor.research.wde_vs_ecse_forensics.directions import norm_dir


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _implied(odd: float | None) -> float | None:
    o = _f(odd)
    if o is None or o <= 1.0:
        return None
    return round(1.0 / o, 6)


def _scores(row: dict[str, Any] | None) -> list[str]:
    if not row:
        return []
    pred = row.get("prediction") or {}
    ecse = pred.get("ecse") or {}
    scores = [str(s) for s in (ecse.get("scores") or []) if s]
    if len(scores) >= 5:
        return scores[:5]
    ranks = (row.get("directions") or {}).get("ranks") or []
    return [str(r.get("score")) for r in ranks if r.get("score")][:5]


def _top_probs(row: dict[str, Any] | None) -> list[float | None]:
    if not row:
        return []
    ecse = (row.get("prediction") or {}).get("ecse") or {}
    out: list[float | None] = []
    for i in range(1, 6):
        t = ecse.get(f"top{i}")
        if isinstance(t, dict):
            out.append(_f(t.get("probability")))
        else:
            out.append(None)
    return out


def _index_by_fid(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for r in payload.get("fixtures") or []:
        try:
            out[int(r["fixture_id"])] = r
        except (KeyError, TypeError, ValueError):
            continue
    # also fold selection-only rows if fixtures missing
    sel = payload.get("selection") or {}
    for bucket in ("tier_s", "tier_a", "tier_b", "rejected"):
        for r in sel.get(bucket) or []:
            try:
                fid = int(r["fixture_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if fid not in out:
                out[fid] = r
    return out


def load_scan(scan_id: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or project_root()
    path = root / ARTIFACT_ROOT / scan_id / "summary.json"
    if not path.is_file():
        raise FileNotFoundError(f"baseline scan missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _movement_labels(
    *,
    old: dict[str, Any] | None,
    new: dict[str, Any] | None,
    odds_changed: bool,
    wde_changed: bool,
    top1_changed: bool,
    top5_jaccard: float | None,
    scores_added: list[str],
    scores_removed: list[str],
    old_tier: str | None,
    new_tier: str | None,
    alignment_delta: float | None,
    started_excluded: bool,
    new_only: bool,
) -> list[str]:
    labels: list[str] = []
    if new_only:
        labels.append("NEW_FIXTURE")
        return labels
    if started_excluded:
        labels.append("FIXTURE_STARTED_EXCLUDED")
        return labels
    if new is None and old is not None:
        labels.append("NO_LONGER_ELIGIBLE")
        return labels

    model_stable = (not wde_changed) and (not top1_changed) and (top5_jaccard == 1.0)
    if not odds_changed and model_stable and old_tier == new_tier:
        labels.append("FULLY_STABLE")
    if odds_changed and model_stable:
        labels.append("ODDS_CHANGED_MODEL_STABLE")
    if top1_changed:
        labels.append("TOP1_CHANGED")
    if wde_changed:
        labels.append("WDE_CHANGED")
    if scores_added or scores_removed:
        if top5_jaccard is not None and top5_jaccard < 1.0:
            labels.append("TOP5_BOUNDARY_CHANGED")
        else:
            labels.append("TOP5_RANK_REORDERED")
    elif top5_jaccard is not None and 0 < top5_jaccard < 1.0:
        labels.append("TOP5_RANK_REORDERED")

    if old_tier != TIER_S and new_tier == TIER_S:
        labels.append("PROMOTED_TO_TIER_S")
    if old_tier not in {TIER_S, TIER_A} and new_tier == TIER_A:
        labels.append("PROMOTED_TO_TIER_A")
    if old_tier == TIER_A and new_tier not in {TIER_S, TIER_A}:
        labels.append("DEMOTED_FROM_TIER_A")
    if alignment_delta is not None:
        if alignment_delta > 0:
            labels.append("ALIGNMENT_IMPROVED")
        elif alignment_delta < 0:
            labels.append("ALIGNMENT_DEGRADED")
    return labels or ["FULLY_STABLE"]


def compare_fixture(old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
    if old is None and new is None:
        return {}
    fid = int((new or old or {}).get("fixture_id"))
    match = f"{(new or old).get('home_team')} vs {(new or old).get('away_team')}"

    if new is not None and (
        "FIXTURE_STARTED_EXCLUDED" in (new.get("reject_reasons") or [])
        or str(new.get("prediction_status") or "") == "FIXTURE_STARTED_EXCLUDED"
    ):
        return {
            "fixture_id": fid,
            "match": match,
            "movement_labels": ["FIXTURE_STARTED_EXCLUDED"],
            "old_tier": old.get("alignment_tier") if old else None,
            "new_tier": new.get("alignment_tier"),
            "started_excluded": True,
        }

    if old is None:
        return {
            "fixture_id": fid,
            "match": match,
            "movement_labels": ["NEW_FIXTURE"],
            "old_tier": None,
            "new_tier": (new or {}).get("alignment_tier"),
            "new_only": True,
        }
    if new is None:
        return {
            "fixture_id": fid,
            "match": match,
            "movement_labels": ["NO_LONGER_ELIGIBLE"],
            "old_tier": old.get("alignment_tier"),
            "new_tier": None,
            "missing_in_new": True,
        }

    old_odds = old.get("odds_prep") or {}
    new_odds = new.get("odds_prep") or {}
    oh, od, oa = _f(old_odds.get("home")), _f(old_odds.get("draw")), _f(old_odds.get("away"))
    nh, nd, na = _f(new_odds.get("home")), _f(new_odds.get("draw")), _f(new_odds.get("away"))
    abs_moves = {
        "home": None if oh is None or nh is None else round(abs(nh - oh), 6),
        "draw": None if od is None or nd is None else round(abs(nd - od), 6),
        "away": None if oa is None or na is None else round(abs(na - oa), 6),
    }
    max_move = max([v for v in abs_moves.values() if v is not None] or [0.0])
    odds_changed = max_move > 1e-9

    old_wde = (old.get("prediction") or {}).get("wde") or {}
    new_wde = (new.get("prediction") or {}).get("wde") or {}
    old_dirs = old.get("directions") or {}
    new_dirs = new.get("directions") or {}
    wde_changed = norm_dir(old_dirs.get("wde_decision")) != norm_dir(new_dirs.get("wde_decision"))

    old_scores = _scores(old)
    new_scores = _scores(new)
    old_set, new_set = set(old_scores), set(new_scores)
    inter = old_set & new_set
    union = old_set | new_set
    jaccard = round(len(inter) / len(union), 6) if union else None
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    old_top1 = old_scores[0] if old_scores else None
    new_top1 = new_scores[0] if new_scores else None
    top1_changed = old_top1 != new_top1

    old_ecse = (old.get("prediction") or {}).get("ecse") or {}
    new_ecse = (new.get("prediction") or {}).get("ecse") or {}
    old_mass = _f(old_ecse.get("top5_mass"))
    new_mass = _f(new_ecse.get("top5_mass"))
    # Baseline often had null mass — note reconstruction was research-only
    old_mass3 = _f(old_ecse.get("top3_mass"))
    new_mass3 = _f(new_ecse.get("top3_mass"))
    old_ent = _f(old_ecse.get("entropy"))
    new_ent = _f(new_ecse.get("entropy"))
    old_top1p = _f(old_ecse.get("top1_probability"))
    new_top1p = _f(new_ecse.get("top1_probability"))

    old_score = _f(old.get("alignment_score"))
    new_score = _f(new.get("alignment_score"))
    align_delta = None if old_score is None or new_score is None else round(new_score - old_score, 4)

    labels = _movement_labels(
        old=old,
        new=new,
        odds_changed=odds_changed,
        wde_changed=wde_changed,
        top1_changed=top1_changed,
        top5_jaccard=jaccard,
        scores_added=added,
        scores_removed=removed,
        old_tier=old.get("alignment_tier"),
        new_tier=new.get("alignment_tier"),
        alignment_delta=align_delta,
        started_excluded=False,
        new_only=False,
    )
    if (
        old.get("alignment_tier") != TIER_S
        and new.get("alignment_tier") == TIER_S
        and old_mass is None
        and new_mass is not None
        and new_mass >= 0.52
    ):
        labels.append("PROMOTED_TO_TIER_S_AFTER_PERSISTED_MASS_FIX")

    return {
        "fixture_id": fid,
        "match": match,
        "kickoff_vienna": new.get("kickoff_vienna") or old.get("kickoff_vienna"),
        "odds_movement": {
            "old_hda": [oh, od, oa],
            "new_hda": [nh, nd, na],
            "abs_movement": abs_moves,
            "implied_old": [_implied(oh), _implied(od), _implied(oa)],
            "implied_new": [_implied(nh), _implied(nd), _implied(na)],
            "max_odds_movement": max_move,
            "bookmaker_count_old": old_odds.get("bookmaker_count"),
            "bookmaker_count_new": new_odds.get("bookmaker_count"),
            "odds_source_old": old_odds.get("odds_source"),
            "odds_source_new": new_odds.get("odds_source"),
            "odds_age_hours_old": old_odds.get("odds_age_hours"),
            "odds_age_hours_new": new_odds.get("odds_age_hours"),
            "odds_changed": odds_changed,
        },
        "wde_movement": {
            "old_wde": old_dirs.get("wde_decision"),
            "new_wde": new_dirs.get("wde_decision"),
            "old_ft": old_dirs.get("ft_marginal"),
            "new_ft": new_dirs.get("ft_marginal"),
            "old_probs": [
                old_wde.get("home_probability"),
                old_wde.get("draw_probability"),
                old_wde.get("away_probability"),
            ],
            "new_probs": [
                new_wde.get("home_probability"),
                new_wde.get("draw_probability"),
                new_wde.get("away_probability"),
            ],
            "confidence_old": old_wde.get("confidence"),
            "confidence_new": new_wde.get("confidence"),
            "confidence_delta": (
                None
                if _f(old_wde.get("confidence")) is None or _f(new_wde.get("confidence")) is None
                else round(float(new_wde["confidence"]) - float(old_wde["confidence"]), 4)
            ),
            "wde_stable": not wde_changed,
        },
        "ecse_movement": {
            "old_top5": old_scores,
            "new_top5": new_scores,
            "old_top5_probabilities": _top_probs(old),
            "new_top5_probabilities": _top_probs(new),
            "top1_old": old_top1,
            "top1_new": new_top1,
            "top1_stable": not top1_changed,
            "top5_set_overlap": len(inter),
            "top5_jaccard": jaccard,
            "scores_added": added,
            "scores_removed": removed,
            "top1_probability_old": old_top1p,
            "top1_probability_new": new_top1p,
            "top3_mass_old": old_mass3,
            "top3_mass_new": new_mass3,
            "top3_mass_delta": None if old_mass3 is None or new_mass3 is None else round(new_mass3 - old_mass3, 6),
            "top5_mass_old": old_mass,
            "top5_mass_new": new_mass,
            "top5_mass_delta": None if old_mass is None or new_mass is None else round(new_mass - old_mass, 6),
            "entropy_old": old_ent,
            "entropy_new": new_ent,
            "entropy_delta": None if old_ent is None or new_ent is None else round(new_ent - old_ent, 6),
            "baseline_mass_was_null": old_mass is None,
        },
        "alignment_movement": {
            "old_market": old_dirs.get("market_direction"),
            "new_market": new_dirs.get("market_direction"),
            "old_top1_dir": old_dirs.get("ecse_top1_direction"),
            "new_top1_dir": new_dirs.get("ecse_top1_direction"),
            "old_top3_maj": old_dirs.get("ecse_top3_majority"),
            "new_top3_maj": new_dirs.get("ecse_top3_majority"),
            "old_top5_maj": old_dirs.get("ecse_top5_majority"),
            "new_top5_maj": new_dirs.get("ecse_top5_majority"),
            "old_consensus": (old.get("prediction") or {}).get("consensus"),
            "new_consensus": (new.get("prediction") or {}).get("consensus"),
            "old_no_bet": (old.get("prediction") or {}).get("no_bet"),
            "new_no_bet": (new.get("prediction") or {}).get("no_bet"),
            "old_alignment_score": old_score,
            "new_alignment_score": new_score,
            "alignment_score_delta": align_delta,
            "old_tier": old.get("alignment_tier"),
            "new_tier": new.get("alignment_tier"),
            "old_tier_s_failure_reasons": old.get("tier_s_failure_reasons"),
            "new_tier_s_failure_reasons": new.get("tier_s_failure_reasons"),
        },
        "movement_labels": labels,
    }


def compare_scans(
    *,
    baseline_scan_id: str,
    fresh_payload: dict[str, Any],
    root: Path | None = None,
) -> dict[str, Any]:
    baseline = load_scan(baseline_scan_id, root=root)
    old_idx = _index_by_fid(baseline)
    new_idx = _index_by_fid(fresh_payload)
    all_ids = sorted(set(old_idx) | set(new_idx))
    rows = [compare_fixture(old_idx.get(i), new_idx.get(i)) for i in all_ids]

    def has(label: str) -> list[dict[str, Any]]:
        return [r for r in rows if label in (r.get("movement_labels") or [])]

    return {
        "baseline_scan_id": baseline_scan_id,
        "fresh_scan_id": fresh_payload.get("scan_id"),
        "baseline_status": baseline.get("status"),
        "fresh_status": fresh_payload.get("status"),
        "overlap_count": len(set(old_idx) & set(new_idx)),
        "baseline_only": sorted(set(old_idx) - set(new_idx)),
        "fresh_only": sorted(set(new_idx) - set(old_idx)),
        "fixtures": rows,
        "promotions_to_tier_s": has("PROMOTED_TO_TIER_S") + has("PROMOTED_TO_TIER_S_AFTER_PERSISTED_MASS_FIX"),
        "promotions_to_tier_a": has("PROMOTED_TO_TIER_A"),
        "demotions_from_tier_a": has("DEMOTED_FROM_TIER_A"),
        "started_excluded": has("FIXTURE_STARTED_EXCLUDED"),
        "summary_labels": {
            lab: sum(1 for r in rows if lab in (r.get("movement_labels") or []))
            for lab in sorted({lab for r in rows for lab in (r.get("movement_labels") or [])})
        },
    }
