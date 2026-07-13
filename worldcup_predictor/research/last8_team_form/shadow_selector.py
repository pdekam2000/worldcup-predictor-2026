"""Shadow Top5/Top3 selectors — canonical probabilities unchanged, selection only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_rerank.features import (
    is_btts,
    is_clean_sheet,
    parse_scoreline,
    winner_side,
)
from worldcup_predictor.research.last8_team_form.coverage_diagnostics import diagnose_top5_coverage


def _normalize_candidates(distribution: list[dict[str, Any]], *, limit: int = 15) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(distribution[:limit], 1):
        if isinstance(item, dict):
            line = str(item.get("scoreline") or "")
            prob = float(item.get("probability") or 0.0)
            rank = int(item.get("rank") or i)
        else:
            line = str(item)
            prob = 0.0
            rank = i
        parsed = parse_scoreline(line)
        if not parsed:
            continue
        h, a = parsed
        out.append(
            {
                "scoreline": line,
                "probability": prob,
                "rank": rank,
                "home_goals": h,
                "away_goals": a,
                "winner": winner_side(line),
                "btts": is_btts(line),
                "clean_sheet": is_clean_sheet(line),
            }
        )
    return out


def select_baseline_top5(distribution: list[dict[str, Any]]) -> list[str]:
    return [c["scoreline"] for c in _normalize_candidates(distribution)[:5]]


def _implied_wde_from_odds(odds_home: float, odds_draw: float, odds_away: float) -> str:
    ph = 1.0 / max(odds_home, 1.01)
    pd = 1.0 / max(odds_draw, 1.01)
    pa = 1.0 / max(odds_away, 1.01)
    total = ph + pd + pa
    ph, pd, pa = ph / total, pd / total, pa / total
    if ph >= pd and ph >= pa:
        return "home_win"
    if pa >= pd and pa >= ph:
        return "away_win"
    return "draw"


def select_wde_aligned_top5(
    distribution: list[dict[str, Any]],
    *,
    wde_direction: str | None = None,
    odds_home: float | None = None,
    odds_draw: float | None = None,
    odds_away: float | None = None,
) -> list[str]:
    candidates = _normalize_candidates(distribution)
    if not candidates:
        return []
    direction = wde_direction
    if not direction and all(x is not None for x in (odds_home, odds_draw, odds_away)):
        direction = _implied_wde_from_odds(float(odds_home), float(odds_draw), float(odds_away))
    if not direction:
        return select_baseline_top5(distribution)

    aligned = [c for c in candidates if c["winner"] == direction]
    pool = aligned if len(aligned) >= 5 else candidates
    pool.sort(key=lambda x: (-x["probability"], x["rank"]))
    return [c["scoreline"] for c in pool[:5]]


def _scenario_bucket(c: dict[str, Any], *, perspective: str = "home") -> str:
    h, a = c["home_goals"], c["away_goals"]
    if h == a:
        return "draw"
    if perspective == "home":
        if a == 0:
            return "opponent_clean_sheet"
        if a == 1:
            return "opponent_one_goal"
        if a >= 2:
            return "opponent_multi_goal"
        if h >= 3 and a <= 1:
            return "high_home_tail"
    if h == 0:
        return "home_clean_sheet_fail"
    if is_btts(c["scoreline"]):
        return "btts"
    if h + a >= 5:
        return "high_total_tail"
    return "other"


def select_scenario_diversified_top5(
    distribution: list[dict[str, Any]],
    *,
    scenario_profile: dict[str, Any] | None = None,
) -> list[str]:
    candidates = _normalize_candidates(distribution)
    if not candidates:
        return []
    risks = (scenario_profile or {}).get("scenario_risks") or {}
    selected: list[dict[str, Any]] = []
    remaining = list(candidates)

    # Anchor: highest probability
    remaining.sort(key=lambda x: (-x["probability"], x["rank"]))
    selected.append(remaining.pop(0))

    target_buckets: list[str] = []
    if (risks.get("opponent_scores_one_risk") or 0) >= 0.5:
        target_buckets.append("opponent_one_goal")
    if (risks.get("opponent_scores_two_plus_risk") or 0) >= 0.35:
        target_buckets.append("opponent_multi_goal")
    if (risks.get("draw_score_risk") or 0) >= 0.35:
        target_buckets.append("draw")
    if (risks.get("high_score_tail_risk") or 0) >= 0.45:
        target_buckets.append("high_total_tail")
    if (risks.get("home_clean_sheet_risk") or 0) >= 0.5:
        target_buckets.append("btts")

    covered: set[str] = {_scenario_bucket(selected[0])}
    for bucket in target_buckets:
        if len(selected) >= 5:
            break
        if bucket in covered:
            continue
        pool = [c for c in remaining if _scenario_bucket(c) == bucket]
        if not pool:
            continue
        pool.sort(key=lambda x: (-x["probability"], x["rank"]))
        pick = pool[0]
        selected.append(pick)
        remaining.remove(pick)
        covered.add(bucket)

    remaining.sort(key=lambda x: (-x["probability"], x["rank"]))
    for c in remaining:
        if len(selected) >= 5:
            break
        if c["scoreline"] not in {s["scoreline"] for s in selected}:
            selected.append(c)

    return [c["scoreline"] for c in selected[:5]]


def select_last8_aware_top5(
    distribution: list[dict[str, Any]],
    *,
    scenario_profile: dict[str, Any] | None = None,
    wde_direction: str | None = None,
) -> list[str]:
    """Greedy selection using Last-8 evidence + canonical probabilities."""
    candidates = _normalize_candidates(distribution)
    if not candidates:
        return []
    risks = (scenario_profile or {}).get("scenario_risks") or {}
    opp_one = float(risks.get("opponent_scores_one_risk") or 0)
    opp_two = float(risks.get("opponent_scores_two_plus_risk") or 0)
    high_tail = float(risks.get("high_score_tail_risk") or 0)
    home_cs_risk = float(risks.get("home_clean_sheet_risk") or 0)

    scored: list[tuple[float, dict[str, Any]]] = []
    for c in candidates:
        bonus = 0.0
        h, a = c["home_goals"], c["away_goals"]
        if a == 1 and opp_one >= 0.4:
            bonus += 0.15 * opp_one
        if a >= 2 and opp_two >= 0.3:
            bonus += 0.12 * opp_two
        if h + a >= 5 and high_tail >= 0.4:
            bonus += 0.10 * high_tail
        if is_btts(c["scoreline"]) and home_cs_risk >= 0.45:
            bonus += 0.08 * home_cs_risk
        if wde_direction and c["winner"] == wde_direction:
            bonus += 0.05
        # Penalize duplicate clean-sheet home-win cluster
        if a == 0 and h >= 2:
            bonus -= 0.02
        score = c["probability"] * (1.0 + bonus)
        scored.append((score, c))

    scored.sort(key=lambda x: (-x[0], x[1]["rank"]))
    picked: list[str] = []
    buckets: set[str] = set()
    for _, c in scored:
        if len(picked) >= 5:
            break
        b = _scenario_bucket(c)
        if c["scoreline"] in picked:
            continue
        # encourage diversity after first two picks
        if len(picked) >= 2 and b in buckets and len(buckets) < 4:
            continue
        picked.append(c["scoreline"])
        buckets.add(b)

    if len(picked) < 5:
        for _, c in scored:
            if c["scoreline"] not in picked:
                picked.append(c["scoreline"])
            if len(picked) >= 5:
                break
    return picked[:5]


def select_hybrid_top5(
    distribution: list[dict[str, Any]],
    *,
    scenario_profile: dict[str, Any] | None = None,
    wde_direction: str | None = None,
    odds_home: float | None = None,
    odds_draw: float | None = None,
    odds_away: float | None = None,
) -> list[str]:
    diversified = select_scenario_diversified_top5(distribution, scenario_profile=scenario_profile)
    last8 = select_last8_aware_top5(distribution, scenario_profile=scenario_profile, wde_direction=wde_direction)
    if not wde_direction and all(x is not None for x in (odds_home, odds_draw, odds_away)):
        wde_direction = _implied_wde_from_odds(float(odds_home), float(odds_draw), float(odds_away))

    candidates = _normalize_candidates(distribution)
    rank_map = {c["scoreline"]: c for c in candidates}
    votes: dict[str, float] = {}
    for i, line in enumerate(diversified):
        votes[line] = votes.get(line, 0) + (5 - i) * 0.4
    for i, line in enumerate(last8):
        votes[line] = votes.get(line, 0) + (5 - i) * 0.6
    for c in candidates[:10]:
        votes[c["scoreline"]] = votes.get(c["scoreline"], 0) + c["probability"] * 10.0
        if wde_direction and c["winner"] == wde_direction:
            votes[c["scoreline"]] += 0.3

    ordered = sorted(votes.items(), key=lambda x: -x[1])
    picked: list[str] = []
    for line, _ in ordered:
        if line not in picked:
            picked.append(line)
        if len(picked) >= 5:
            break
    return picked


def select_top3_variants(
    distribution: list[dict[str, Any]],
    *,
    top5_lines: list[str] | None = None,
    scenario_profile: dict[str, Any] | None = None,
    wde_direction: str | None = None,
    odds_home: float | None = None,
    odds_draw: float | None = None,
    odds_away: float | None = None,
) -> dict[str, list[str]]:
    candidates = _normalize_candidates(distribution)
    raw_top3 = [c["scoreline"] for c in candidates[:3]]
    top5 = top5_lines or select_baseline_top5(distribution)
    wde_top5 = select_wde_aligned_top5(
        distribution,
        wde_direction=wde_direction,
        odds_home=odds_home,
        odds_draw=odds_draw,
        odds_away=odds_away,
    )
    last8_top5 = select_last8_aware_top5(distribution, scenario_profile=scenario_profile, wde_direction=wde_direction)
    hybrid_top5 = select_hybrid_top5(
        distribution,
        scenario_profile=scenario_profile,
        wde_direction=wde_direction,
        odds_home=odds_home,
        odds_draw=odds_draw,
        odds_away=odds_away,
    )

    return {
        "raw_ecse_top3": raw_top3,
        "wde_aligned_top3": wde_top5[:3],
        "last8_aware_top3": last8_top5[:3],
        "hybrid_coverage_top3": hybrid_top5[:3],
        "baseline_top5": top5,
    }


def shadow_selection_bundle(
    distribution: list[dict[str, Any]],
    *,
    scenario_profile: dict[str, Any] | None = None,
    wde_direction: str | None = None,
    odds_home: float | None = None,
    odds_draw: float | None = None,
    odds_away: float | None = None,
) -> dict[str, Any]:
    canonical_top5 = select_baseline_top5(distribution)
    shadow_last8_top5 = select_last8_aware_top5(
        distribution, scenario_profile=scenario_profile, wde_direction=wde_direction
    )
    return {
        "shadow_only": True,
        "canonical_top5": canonical_top5,
        "canonical_top5_diagnostics": diagnose_top5_coverage(canonical_top5),
        "shadow_last8_top5": shadow_last8_top5,
        "shadow_last8_top5_diagnostics": diagnose_top5_coverage(shadow_last8_top5),
        "methods": {
            "baseline": canonical_top5,
            "wde_aligned": select_wde_aligned_top5(
                distribution,
                wde_direction=wde_direction,
                odds_home=odds_home,
                odds_draw=odds_draw,
                odds_away=odds_away,
            ),
            "scenario_diversified": select_scenario_diversified_top5(distribution, scenario_profile=scenario_profile),
            "last8_aware": shadow_last8_top5,
            "hybrid": select_hybrid_top5(
                distribution,
                scenario_profile=scenario_profile,
                wde_direction=wde_direction,
                odds_home=odds_home,
                odds_draw=odds_draw,
                odds_away=odds_away,
            ),
        },
        "top3_variants": select_top3_variants(
            distribution,
            scenario_profile=scenario_profile,
            wde_direction=wde_direction,
            odds_home=odds_home,
            odds_draw=odds_draw,
            odds_away=odds_away,
        ),
    }
