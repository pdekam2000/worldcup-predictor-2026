"""Forward result evaluation for timing snapshots (pure)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_timing_experiment.compare import compare_snapshots
from worldcup_predictor.research.ecse_timing_experiment.constants import FINISHED, UNRESOLVED
from worldcup_predictor.research.ecse_timing_experiment.hashing import as_float, as_prob
from worldcup_predictor.research.ecse_timing_experiment.stable_union import build_stable_union


def normalize_score(home_goals: Any, away_goals: Any) -> str | None:
    try:
        h = int(home_goals)
        a = int(away_goals)
    except (TypeError, ValueError):
        return None
    if h < 0 or a < 0:
        return None
    return f"{h}-{a}"


def result_eligible(status: str | None, score: str | None) -> tuple[bool, str]:
    st = str(status or "").upper().strip()
    if st in {"CANC", "ABD", "PST", "SUSP", "INT", "AWD", "WO"}:
        return False, "postponed_or_cancelled"
    if st in FINISHED:
        if not score:
            return False, "finished_without_score"
        return True, "ok"
    if st in UNRESOLVED or st in {"NS", "TBD", "SCHEDULED", "TIMED", "LIVE", "1H", "HT", "2H", "ET", "BT", "P"}:
        return False, "pending_or_unresolved"
    if score and st:
        return False, f"non_finished_status:{st}"
    return False, "pending_or_unresolved"


def _top_scores(payload: dict[str, Any]) -> list[str]:
    ecse = payload.get("ecse") or {}
    scores = [str(s) for s in (ecse.get("scores") or []) if s]
    if len(scores) >= 5:
        return scores[:5]
    for i in range(1, 6):
        t = ecse.get(f"top{i}") or {}
        if isinstance(t, dict) and t.get("score") and str(t["score"]) not in scores:
            scores.append(str(t["score"]))
    return scores[:5]


def _norm_side(v: Any) -> str:
    s = str(v or "").lower().strip()
    if s in {"1", "home", "home_win", "h"}:
        return "home_win"
    if s in {"x", "draw", "d"}:
        return "draw"
    if s in {"2", "away", "away_win", "a"}:
        return "away_win"
    return s


def _winner_from_score(score: str) -> str:
    h, a = score.split("-", 1)
    hi, ai = int(h), int(a)
    if hi > ai:
        return "home_win"
    if hi < ai:
        return "away_win"
    return "draw"


def evaluate_snapshot_against_result(
    payload: dict[str, Any],
    *,
    actual_score: str,
    snapshot_class: str,
) -> dict[str, Any]:
    scores = _top_scores(payload)
    rank = scores.index(actual_score) + 1 if actual_score in scores else None
    hits = {f"top{k}_hit": bool(rank is not None and rank <= k) for k in range(1, 6)}

    # probability of final score if present in top5
    final_prob = None
    for i in range(1, 6):
        t = (payload.get("ecse") or {}).get(f"top{i}") or {}
        if isinstance(t, dict) and str(t.get("score")) == actual_score:
            final_prob = as_prob(t.get("probability"))
            break

    wde = _norm_side((payload.get("wde") or {}).get("decision"))
    actual_w = _winner_from_score(actual_score)
    wde_hit = wde == actual_w if wde else None

    hg, ag = [int(x) for x in actual_score.split("-", 1)]
    btts_actual = "yes" if hg > 0 and ag > 0 else "no"
    ou_actual = "over" if (hg + ag) > 2.5 else "under"
    btts_pred = str(((payload.get("btts") or {}).get("prediction") or "")).lower()
    ou_pred = str(((payload.get("ou25") or {}).get("preferred_side") or "")).lower()
    if "yes" in btts_pred:
        btts_pred_n = "yes"
    elif "no" in btts_pred:
        btts_pred_n = "no"
    else:
        btts_pred_n = ""
    if "over" in ou_pred:
        ou_pred_n = "over"
    elif "under" in ou_pred:
        ou_pred_n = "under"
    else:
        ou_pred_n = ""

    return {
        "snapshot_class": snapshot_class,
        "actual_score": actual_score,
        "final_score_rank": rank,
        **hits,
        "wde_hit": wde_hit,
        "btts_hit": (btts_pred_n == btts_actual) if btts_pred_n else None,
        "ou25_hit": (ou_pred_n == ou_actual) if ou_pred_n else None,
        "final_score_probability": final_prob,
        "top5_scores": scores,
        "research_only": True,
        "canonical": False,
    }


def evaluate_fixture_timeline(
    snapshots: dict[str, dict[str, Any]],
    *,
    actual_score: str,
    status: str | None,
    freeze_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ok, reason = result_eligible(status, actual_score)
    if not ok:
        return {
            "eligible": False,
            "exclusion_reason": reason,
            "actual_score": actual_score,
            "status": status,
            "research_only": True,
        }

    per_class = {}
    for sc, payload in snapshots.items():
        if payload:
            per_class[sc] = evaluate_snapshot_against_result(
                payload, actual_score=actual_score, snapshot_class=sc
            )

    event_labels: list[str] = []
    classes_with = [c for c, ev in per_class.items() if actual_score in (ev.get("top5_scores") or [])]
    if not classes_with:
        event_labels.append("CORRECT_SCORE_NEVER_IN_TOP5")
    if classes_with and set(classes_with) >= set(snapshots.keys()) and len(snapshots) >= 2:
        event_labels.append("CORRECT_SCORE_STABLE_ALL_SNAPSHOTS")

    def _refresh_events(earlier: str, later: str, improved: str, degraded: str) -> None:
        if earlier not in snapshots or later not in snapshots:
            return
        a = set(_top_scores(snapshots[earlier]))
        b = set(_top_scores(snapshots[later]))
        in_a = actual_score in a
        in_b = actual_score in b
        if in_a and not in_b:
            event_labels.append(degraded)
            event_labels.append("BOUNDARY_SCORE_INSTABILITY")
        elif (not in_a) and in_b:
            event_labels.append(improved)

    _refresh_events("EARLY", "MID", "MID_REFRESH_IMPROVED_TOP5", "MID_REFRESH_DEGRADED_TOP5")
    _refresh_events("MID", "LATE", "LATE_REFRESH_IMPROVED_TOP5", "LATE_REFRESH_DEGRADED_TOP5")
    _refresh_events("EARLY", "LATE", "LATE_REFRESH_IMPROVED_TOP5", "LATE_REFRESH_DEGRADED_TOP5")
    # de-dupe while preserving order
    seen = set()
    event_labels = [x for x in event_labels if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

    comparisons = {}
    for a, b in (("EARLY", "MID"), ("MID", "LATE"), ("EARLY", "LATE")):
        if a in snapshots and b in snapshots:
            comparisons[f"{a}_vs_{b}"] = compare_snapshots(
                snapshots[a], snapshots[b], from_class=a, to_class=b
            )

    union = build_stable_union(snapshots)
    union_eval = None
    if union.get("scores"):
        union_payload = {
            "ecse": {
                "scores": union["scores"],
                **{
                    f"top{i}": {"score": t["score"], "probability": t.get("avg_probability")}
                    for i, t in enumerate(union.get("top5") or [], start=1)
                },
            },
            "wde": {},
            "btts": {},
            "ou25": {},
        }
        union_eval = evaluate_snapshot_against_result(
            union_payload, actual_score=actual_score, snapshot_class="STABLE_UNION_TOP5"
        )
        union_eval["research_only"] = True
        union_eval["canonical"] = False
        union_eval["final_decision_authority"] = False

    freeze_eval = None
    if freeze_payload:
        freeze_eval = evaluate_snapshot_against_result(
            freeze_payload, actual_score=actual_score, snapshot_class="CANONICAL_FREEZE"
        )

    return {
        "eligible": True,
        "actual_score": actual_score,
        "status": status,
        "per_snapshot": per_class,
        "event_labels": event_labels,
        "comparisons": comparisons,
        "stable_union": union,
        "stable_union_eval": union_eval,
        "canonical_freeze_eval": freeze_eval,
        "later_added_correct": any(
            x.endswith("IMPROVED_TOP5") for x in event_labels
        ),
        "later_removed_correct": any(
            x.endswith("DEGRADED_TOP5") for x in event_labels
        ),
        "correct_stable_all": "CORRECT_SCORE_STABLE_ALL_SNAPSHOTS" in event_labels,
        "research_only": True,
        "canonical": False,
        "final_decision_authority": False,
    }


def aggregate_timing_metrics(fixture_evals: list[dict[str, Any]]) -> dict[str, Any]:
    from worldcup_predictor.research.ecse_timing_experiment.stats import (
        interpretation_band,
        mcnemar_exact,
        rate_block,
    )

    eligible = [e for e in fixture_evals if e.get("eligible")]
    by_class: dict[str, dict[str, Any]] = {}
    for sc in ("EARLY", "MID", "LATE", "STABLE_UNION_TOP5"):
        hits1 = hits3 = hits5 = 0
        n = 0
        mass_vals: list[float] = []
        ent_vals: list[float] = []
        hours_vals: list[float] = []
        for fe in eligible:
            if sc == "STABLE_UNION_TOP5":
                ev = fe.get("stable_union_eval")
            else:
                ev = (fe.get("per_snapshot") or {}).get(sc)
            if not ev:
                continue
            n += 1
            hits1 += int(bool(ev.get("top1_hit")))
            hits3 += int(bool(ev.get("top3_hit")))
            hits5 += int(bool(ev.get("top5_hit")))
            # mass/entropy/hours pulled from nested if present
            snap = (fe.get("snapshot_meta") or {}).get(sc) or {}
            m = as_float(snap.get("top5_mass"))
            if m is not None:
                mass_vals.append(m)
            e = as_float(snap.get("entropy"))
            if e is not None:
                ent_vals.append(e)
            h = as_float(snap.get("hours_to_kickoff"))
            if h is not None:
                hours_vals.append(h)
        by_class[sc] = {
            "sample_size": n,
            "top1": rate_block(hits1, n),
            "top3": rate_block(hits3, n),
            "top5": rate_block(hits5, n),
            "avg_top5_mass": round(sum(mass_vals) / len(mass_vals), 6) if mass_vals else None,
            "avg_entropy": round(sum(ent_vals) / len(ent_vals), 6) if ent_vals else None,
            "avg_hours_to_kickoff": round(sum(hours_vals) / len(hours_vals), 4) if hours_vals else None,
        }

    # Paired McNemar EARLY vs LATE Top5
    b = c = 0
    paired_n = 0
    for fe in eligible:
        pe = (fe.get("per_snapshot") or {})
        if "EARLY" not in pe or "LATE" not in pe:
            continue
        paired_n += 1
        e_hit = bool(pe["EARLY"].get("top5_hit"))
        l_hit = bool(pe["LATE"].get("top5_hit"))
        if e_hit and not l_hit:
            b += 1
        elif l_hit and not e_hit:
            c += 1

    improvements = sum(1 for fe in eligible if fe.get("later_added_correct"))
    degradations = sum(1 for fe in eligible if fe.get("later_removed_correct"))
    boundary_removals = sum(
        1
        for fe in eligible
        for lab in (fe.get("event_labels") or [])
        if lab.endswith("DEGRADED_TOP5")
    )
    boundary_additions = sum(
        1
        for fe in eligible
        for lab in (fe.get("event_labels") or [])
        if lab.endswith("IMPROVED_TOP5")
    )

    return {
        "eligible_fixtures": len(eligible),
        "excluded_fixtures": len(fixture_evals) - len(eligible),
        "by_class": by_class,
        "paired_early_vs_late": {
            "n": paired_n,
            "mcnemar_top5": mcnemar_exact(b, c),
            "interpretation": interpretation_band(paired_n),
        },
        "refresh_improvements": improvements,
        "refresh_degradations": degradations,
        "boundary_score_removals": boundary_removals,
        "boundary_score_additions": boundary_additions,
        "declare_winner": False,
        "winner_note": "Do not declare a timing-class winner until sample sizes meet promotion policy.",
        "research_only": True,
    }
