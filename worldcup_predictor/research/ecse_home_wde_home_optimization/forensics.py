"""Win/loss forensic diffs, clustering, threshold search for HOME∩HOME rule."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Callable

from worldcup_predictor.research.ecse_home_wde_home_optimization import (
    MAX_LEAGUE_SHARE,
    MIN_COVERAGE,
    MIN_N,
    MIN_WORST_FOLD,
    TARGET_ACC,
)
from worldcup_predictor.research.ou25_regime_mining.metrics import (
    accuracy_pack,
    bootstrap_accuracy,
    config_hash,
    priced_performance,
    remove_one_win_sensitivity,
)
from worldcup_predictor.research.ou25_regime_mining.mining import walk_forward

NUMERIC_FEATURES = [
    "odds_home",
    "odds_draw",
    "odds_away",
    "favorite_odds",
    "favorite_strength",
    "market_margin",
    "bookmaker_count",
    "wde_home_p",
    "wde_draw_p",
    "wde_away_p",
    "wde_confidence",
    "ecse_home_mass",
    "ecse_draw_mass",
    "ecse_away_mass",
    "ecse_home_gap",
    "top3_mass",
    "top5_mass",
    "top10_mass",
    "entropy",
    "lambda_home",
    "lambda_away",
    "total_lambda",
    "goal_balance",
    "btts_yes_probability",
    "over_probability",
    "under_probability",
    "hours_to_kickoff",
]

CATEGORICAL_FEATURES = [
    "league",
    "snapshot_stage",
    "market_agreement",
    "market_favorite",
    "btts_prediction",
    "ou25_prediction",
    "tier",
    "prediction_scope",
    "data_quality",
]


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def feature_importance(wins: list[dict[str, Any]], losses: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"numeric": {}, "categorical": {}}
    for feat in NUMERIC_FEATURES:
        w = [float(r[feat]) for r in wins if r.get(feat) is not None]
        l = [float(r[feat]) for r in losses if r.get(feat) is not None]
        if not w or not l:
            continue
        wm, lm = _mean(w), _mean(l)
        out["numeric"][feat] = {
            "win_mean": wm,
            "loss_mean": lm,
            "win_median": _median(w),
            "loss_median": _median(l),
            "diff_mean": (wm - lm) if wm is not None and lm is not None else None,
            "win_n": len(w),
            "loss_n": len(l),
            "direction_hint": (
                "wins_higher"
                if wm is not None and lm is not None and wm > lm
                else ("wins_lower" if wm is not None and lm is not None and wm < lm else "similar")
            ),
        }
    for feat in CATEGORICAL_FEATURES:
        wc = Counter(str(r.get(feat) or "MISSING") for r in wins)
        lc = Counter(str(r.get(feat) or "MISSING") for r in losses)
        keys = set(wc) | set(lc)
        rows = []
        for k in sorted(keys):
            wn, ln = wc.get(k, 0), lc.get(k, 0)
            rows.append(
                {
                    "value": k,
                    "wins": wn,
                    "losses": ln,
                    "win_rate_in_value": (wn / (wn + ln)) if (wn + ln) else None,
                    "loss_share": (ln / len(losses)) if losses else None,
                }
            )
        # sort by loss share
        rows.sort(key=lambda x: -(x["loss_share"] or 0))
        out["categorical"][feat] = rows
    return out


def cluster_failures(losses: list[dict[str, Any]]) -> dict[str, Any]:
    """Assign each loss to evidence-based clusters (non-invented labels from frozen fields)."""
    clusters: dict[str, list[int]] = defaultdict(list)
    assignments = []
    for r in losses:
        labels = []
        actual = r.get("actual_1x2")
        if actual == "draw":
            labels.append("unexpected_draw")
        elif actual == "away_win":
            labels.append("away_upset")
        if r.get("market_agreement") == "DISAGREE":
            labels.append("market_contradiction")
        if r.get("odds_home") is not None and float(r["odds_home"]) > 2.2:
            labels.append("home_not_strong_favorite")
        if r.get("entropy") is not None and float(r["entropy"]) >= 2.0:
            labels.append("high_entropy")
        if r.get("wde_confidence") is not None and float(r["wde_confidence"]) < 0.45:
            labels.append("low_wde_confidence")
        if r.get("ecse_home_gap") is not None and float(r["ecse_home_gap"]) < 0.10:
            labels.append("weak_ecse_home_dominance")
        if r.get("top5_mass") is not None and float(r["top5_mass"]) < 0.40:
            labels.append("low_top5_mass")
        if r.get("actual_home_goals") is not None and r.get("actual_away_goals") is not None:
            tot = int(r["actual_home_goals"]) + int(r["actual_away_goals"])
            if tot >= 4:
                labels.append("goal_explosion")
            if tot <= 1:
                labels.append("low_scoring_draw_or_upset")
        if r.get("ecse_draw_mass") is not None and float(r["ecse_draw_mass"]) >= 0.30:
            labels.append("elevated_draw_mass")
        if not labels:
            labels.append("unclassified")
        primary = labels[0]
        clusters[primary].append(int(r["fixture_id"]))
        assignments.append(
            {
                "fixture_id": r["fixture_id"],
                "match_name": r.get("match_name"),
                "actual_1x2": actual,
                "actual_score": r.get("actual_score"),
                "odds_home": r.get("odds_home"),
                "primary_cluster": primary,
                "all_clusters": labels,
            }
        )
    return {
        "n_losses": len(losses),
        "cluster_counts": {k: len(v) for k, v in sorted(clusters.items(), key=lambda kv: -len(kv[1]))},
        "clusters": {k: v for k, v in clusters.items()},
        "assignments": assignments,
        "note": "Clusters derived only from frozen prematch fields + actual outcomes; not invented narratives.",
    }


Predicate = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class ExtraFilter:
    name: str
    conditions: tuple[str, ...]
    pred: Predicate

    @property
    def hash(self) -> str:
        return config_hash({"name": self.name, "conditions": list(self.conditions)})


def _league_concentration(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    c = Counter(str(r.get("league") or "UNKNOWN") for r in rows)
    return c.most_common(1)[0][1] / len(rows)


def _season_concentration(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    # month proxy for season phase concentration
    c = Counter(str(r.get("date") or "UNKNOWN")[:7] for r in rows)
    return c.most_common(1)[0][1] / len(rows)


def evaluate_subset(
    selected: list[dict[str, Any]],
    *,
    universe_n: int,
    base_n: int,
    name: str,
    conditions: list[str],
) -> dict[str, Any]:
    hits_list = [bool(r.get("direction_hit")) for r in selected]
    n = len(selected)
    hits = sum(1 for h in hits_list if h)
    pack = accuracy_pack(hits, n)
    # walk-forward on chronological selected? Better: folds on base set then apply filter
    # Standard: fold the selected chronologically
    folds = walk_forward(selected, 3)
    fold_accs = []
    fold_stats = []
    for i, fold in enumerate(folds):
        if not fold:
            continue
        fh = sum(1 for r in fold if r.get("direction_hit"))
        acc = fh / len(fold)
        fold_accs.append(acc)
        fold_stats.append({"fold": i + 1, "n": len(fold), "accuracy": acc})
    stakes = []
    for r in selected:
        o = r.get("odds_home")
        if o is None or float(o) <= 1.0:
            continue
        stakes.append({"hit": bool(r.get("direction_hit")), "odds": float(o), "side": "home_win"})
    priced = priced_performance(stakes)
    sens1 = remove_one_win_sensitivity(hits_list)
    # leave-two-win-out
    win_idxs = [i for i, h in enumerate(hits_list) if h]
    min_two = None
    if len(win_idxs) >= 2 and n > 2:
        mins = []
        for a in range(min(20, len(win_idxs))):
            for b in range(a + 1, min(a + 6, len(win_idxs))):
                rem = [h for j, h in enumerate(hits_list) if j not in {win_idxs[a], win_idxs[b]}]
                mins.append(sum(1 for x in rem if x) / len(rem))
        min_two = min(mins) if mins else None
    boot = bootstrap_accuracy(hits_list, n_boot=300, seed=20260803)
    league_share = _league_concentration(selected)
    month_share = _season_concentration(selected)
    worst = min(fold_accs) if fold_accs else None
    mean_fold = sum(fold_accs) / len(fold_accs) if fold_accs else None
    coverage_univ = n / universe_n if universe_n else None
    coverage_base = n / base_n if base_n else None

    passes = (
        n >= MIN_N
        and (pack["accuracy"] or 0) >= TARGET_ACC
        and (coverage_univ or 0) >= MIN_COVERAGE
        and (worst is not None and worst >= MIN_WORST_FOLD)
        and (league_share is None or league_share <= MAX_LEAGUE_SHARE)
        and not sens1.get("collapses")
        and (month_share is None or month_share <= 0.55)
    )

    return {
        "name": name,
        "conditions": conditions,
        "config_hash": config_hash({"name": name, "conditions": conditions}),
        "n": n,
        "wins": hits,
        "losses": n - hits,
        "accuracy": pack["accuracy"],
        "wilson_95": pack["wilson_95"],
        "coverage_of_universe": coverage_univ,
        "coverage_of_base62": coverage_base,
        "worst_fold": worst,
        "mean_fold": mean_fold,
        "fold_stats": fold_stats,
        "league_concentration": league_share,
        "month_concentration": month_share,
        "remove_one_win": sens1,
        "leave_two_win_min_accuracy": min_two,
        "bootstrap_95": boot,
        "priced": {
            "priced_n": priced.get("priced_n"),
            "average_odds": priced.get("average_odds"),
            "roi": priced.get("roi"),
            "max_drawdown": priced.get("max_drawdown"),
            "profit_factor": priced.get("profit_factor"),
        },
        "passes_optimization_constraints": passes,
        "stability": (
            "HIGH"
            if passes
            else (
                "MEDIUM"
                if n >= 40 and (pack["accuracy"] or 0) >= 0.72 and not sens1.get("collapses")
                else "LOW"
            )
        ),
    }


def build_candidate_filters(base: list[dict[str, Any]]) -> list[ExtraFilter]:
    """Deterministic threshold grid around forensic features (1–2 conditions)."""
    filters: list[ExtraFilter] = []

    # single-condition odds / confidence / mass / entropy / lambda
    for thr in [1.30, 1.40, 1.50, 1.60, 1.70, 1.80, 1.90, 2.00, 2.10, 2.20, 2.40, 2.60]:
        filters.append(
            ExtraFilter(
                f"odds_home_le_{thr}",
                (f"odds_home<={thr}",),
                lambda r, t=thr: r.get("odds_home") is not None and float(r["odds_home"]) <= t,
            )
        )
        filters.append(
            ExtraFilter(
                f"odds_home_ge_{thr}",
                (f"odds_home>={thr}",),
                lambda r, t=thr: r.get("odds_home") is not None and float(r["odds_home"]) >= t,
            )
        )

    for thr in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
        filters.append(
            ExtraFilter(
                f"wde_home_p_ge_{int(thr*100)}",
                (f"wde_home_p>={thr}",),
                lambda r, t=thr: r.get("wde_home_p") is not None and float(r["wde_home_p"]) >= t,
            )
        )
        filters.append(
            ExtraFilter(
                f"ecse_home_mass_ge_{int(thr*100)}",
                (f"ecse_home_mass>={thr}",),
                lambda r, t=thr: r.get("ecse_home_mass") is not None and float(r["ecse_home_mass"]) >= t,
            )
        )

    for thr in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40]:
        filters.append(
            ExtraFilter(
                f"ecse_draw_mass_le_{int(thr*100)}",
                (f"ecse_draw_mass<={thr}",),
                lambda r, t=thr: r.get("ecse_draw_mass") is not None and float(r["ecse_draw_mass"]) <= t,
            )
        )
        filters.append(
            ExtraFilter(
                f"ecse_home_gap_ge_{int(thr*100)}",
                (f"ecse_home_gap>={thr}",),
                lambda r, t=thr: r.get("ecse_home_gap") is not None and float(r["ecse_home_gap"]) >= t,
            )
        )

    for thr in [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        filters.append(
            ExtraFilter(
                f"top5_mass_ge_{int(thr*100)}",
                (f"top5_mass>={thr}",),
                lambda r, t=thr: r.get("top5_mass") is not None and float(r["top5_mass"]) >= t,
            )
        )

    for thr in [1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2]:
        filters.append(
            ExtraFilter(
                f"entropy_le_{str(thr).replace('.', '_')}",
                (f"entropy<={thr}",),
                lambda r, t=thr: r.get("entropy") is not None and float(r["entropy"]) <= t,
            )
        )

    for thr in [1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0]:
        filters.append(
            ExtraFilter(
                f"total_lambda_ge_{str(thr).replace('.', '_')}",
                (f"total_lambda>={thr}",),
                lambda r, t=thr: r.get("total_lambda") is not None and float(r["total_lambda"]) >= t,
            )
        )
        filters.append(
            ExtraFilter(
                f"total_lambda_le_{str(thr).replace('.', '_')}",
                (f"total_lambda<={thr}",),
                lambda r, t=thr: r.get("total_lambda") is not None and float(r["total_lambda"]) <= t,
            )
        )

    filters.append(
        ExtraFilter(
            "market_agree_home",
            ("market_favorite=home_win",),
            lambda r: r.get("market_favorite") == "home_win",
        )
    )
    filters.append(
        ExtraFilter(
            "snapshot_late_or_final",
            ("snapshot in LATE/FINAL_PREMATCH",),
            lambda r: r.get("snapshot_stage") in {"LATE", "FINAL_PREMATCH"},
        )
    )

    # two-condition compositions (limited, forensic-motivated)
    two_conds = [
        (
            "odds_home_le_1_8_entropy_le_1_8",
            ("odds_home<=1.8", "entropy<=1.8"),
            lambda r: r.get("odds_home") is not None
            and float(r["odds_home"]) <= 1.8
            and r.get("entropy") is not None
            and float(r["entropy"]) <= 1.8,
        ),
        (
            "odds_home_le_2_0_wde_home_ge_55",
            ("odds_home<=2.0", "wde_home_p>=0.55"),
            lambda r: r.get("odds_home") is not None
            and float(r["odds_home"]) <= 2.0
            and r.get("wde_home_p") is not None
            and float(r["wde_home_p"]) >= 0.55,
        ),
        (
            "odds_home_le_1_7_draw_mass_le_25",
            ("odds_home<=1.7", "ecse_draw_mass<=0.25"),
            lambda r: r.get("odds_home") is not None
            and float(r["odds_home"]) <= 1.7
            and r.get("ecse_draw_mass") is not None
            and float(r["ecse_draw_mass"]) <= 0.25,
        ),
        (
            "home_gap_ge_20_entropy_le_1_9",
            ("ecse_home_gap>=0.20", "entropy<=1.9"),
            lambda r: r.get("ecse_home_gap") is not None
            and float(r["ecse_home_gap"]) >= 0.20
            and r.get("entropy") is not None
            and float(r["entropy"]) <= 1.9,
        ),
        (
            "top5_mass_ge_45_odds_home_le_2_0",
            ("top5_mass>=0.45", "odds_home<=2.0"),
            lambda r: r.get("top5_mass") is not None
            and float(r["top5_mass"]) >= 0.45
            and r.get("odds_home") is not None
            and float(r["odds_home"]) <= 2.0,
        ),
        (
            "wde_home_ge_60_market_agree",
            ("wde_home_p>=0.60", "market_favorite=home_win"),
            lambda r: r.get("wde_home_p") is not None
            and float(r["wde_home_p"]) >= 0.60
            and r.get("market_favorite") == "home_win",
        ),
        (
            "odds_home_le_1_6_lambda_ge_2_2",
            ("odds_home<=1.6", "total_lambda>=2.2"),
            lambda r: r.get("odds_home") is not None
            and float(r["odds_home"]) <= 1.6
            and r.get("total_lambda") is not None
            and float(r["total_lambda"]) >= 2.2,
        ),
        (
            "odds_home_le_1_5_wde_home_ge_65",
            ("odds_home<=1.5", "wde_home_p>=0.65"),
            lambda r: r.get("odds_home") is not None
            and float(r["odds_home"]) <= 1.5
            and r.get("wde_home_p") is not None
            and float(r["wde_home_p"]) >= 0.65,
        ),
        (
            "draw_mass_le_25_home_gap_ge_15",
            ("ecse_draw_mass<=0.25", "ecse_home_gap>=0.15"),
            lambda r: r.get("ecse_draw_mass") is not None
            and float(r["ecse_draw_mass"]) <= 0.25
            and r.get("ecse_home_gap") is not None
            and float(r["ecse_home_gap"]) >= 0.15,
        ),
        (
            "entropy_le_1_7_top5_ge_40",
            ("entropy<=1.7", "top5_mass>=0.40"),
            lambda r: r.get("entropy") is not None
            and float(r["entropy"]) <= 1.7
            and r.get("top5_mass") is not None
            and float(r["top5_mass"]) >= 0.40,
        ),
    ]
    for name, conds, pred in two_conds:
        filters.append(ExtraFilter(name, conds, pred))

    # league whitelist: keep leagues with win_rate >= 70% and n>=3 in base
    by_league: dict[str, list[bool]] = defaultdict(list)
    for r in base:
        by_league[str(r.get("league") or "UNKNOWN")].append(bool(r.get("direction_hit")))
    good = []
    for lg, hits in by_league.items():
        if len(hits) >= 3 and (sum(1 for h in hits if h) / len(hits)) >= 0.70:
            good.append(lg)
    if good:
        good_set = frozenset(good)
        filters.append(
            ExtraFilter(
                "league_whitelist_wr70_n3",
                (f"league in {sorted(good_set)}",),
                lambda r, s=good_set: str(r.get("league") or "UNKNOWN") in s,
            )
        )

    return filters


def parameter_perturbation(base: list[dict[str, Any]], filt: ExtraFilter, universe_n: int) -> dict[str, Any]:
    """Slightly loosen/tighten numeric thresholds embedded in name when possible."""
    # For simplicity: evaluate neighborhood by modifying odds/entropy style filters via re-parse
    # Report selected N sensitivity only for filters with odds_home_le
    results = []
    name = filt.name
    if name.startswith("odds_home_le_"):
        try:
            base_thr = float(name.split("odds_home_le_")[1].replace("_", "."))
        except ValueError:
            return {"applicable": False}
        for delta in (-0.1, -0.05, 0.0, 0.05, 0.1):
            thr = round(base_thr + delta, 2)
            if thr <= 1.01:
                continue
            sel = [r for r in base if r.get("odds_home") is not None and float(r["odds_home"]) <= thr]
            ev = evaluate_subset(
                sel,
                universe_n=universe_n,
                base_n=len(base),
                name=f"odds_home_le_{thr}",
                conditions=[f"odds_home<={thr}"],
            )
            results.append({"thr": thr, "n": ev["n"], "accuracy": ev["accuracy"], "worst_fold": ev["worst_fold"]})
        return {"applicable": True, "neighborhood": results}
    return {"applicable": False}


def run_threshold_search(
    base: list[dict[str, Any]],
    *,
    universe_n: int,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    # baseline
    base_ev = evaluate_subset(
        base,
        universe_n=universe_n,
        base_n=len(base),
        name="BASE_ecse_home_and_wde_home",
        conditions=["ecse_direction=home_win", "wde_decision=home_win"],
    )
    out.append(base_ev)
    seen.add(base_ev["config_hash"])

    for filt in build_candidate_filters(base):
        if filt.hash in seen:
            continue
        seen.add(filt.hash)
        selected = [r for r in base if filt.pred(r)]
        # full rule conditions
        conds = ["ecse_direction=home_win", "wde_decision=home_win", *filt.conditions]
        ev = evaluate_subset(
            selected,
            universe_n=universe_n,
            base_n=len(base),
            name=f"BASE+{filt.name}",
            conditions=conds,
        )
        ev["extra_filter_hash"] = filt.hash
        ev["perturbation"] = parameter_perturbation(base, filt, universe_n)
        out.append(ev)

    out.sort(
        key=lambda r: (
            -int(bool(r.get("passes_optimization_constraints"))),
            -(r.get("accuracy") or 0),
            -(r.get("n") or 0),
            -(r.get("worst_fold") or 0),
        )
    )
    return out
