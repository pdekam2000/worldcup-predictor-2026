"""Fixed-rule search, walk-forward, leaderboards, ECSE filters, Exact Top5 segments."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from worldcup_predictor.research.ou25_regime_mining import (
    LABEL_BASELINE,
    LABEL_DIAGNOSTIC,
    LABEL_NO_EDGE,
    LABEL_PROMISING,
    LABEL_SUPPORTED,
    RAW_OU_BASELINE,
)
from worldcup_predictor.research.ou25_regime_mining.metrics import (
    accuracy_pack,
    bootstrap_accuracy,
    config_hash,
    priced_performance,
    remove_one_win_sensitivity,
    wilson_interval,
)


def _kick_key(row: dict[str, Any]) -> str:
    return str(row.get("kickoff") or "")


def chrono_sort(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (_kick_key(r), int(r["fixture_id"])))


def raw_split(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def pack(subset: list[dict[str, Any]], label: str) -> dict[str, Any]:
        hits = sum(1 for r in subset if r.get("hit"))
        n = len(subset)
        confs = [float(r["confidence"]) for r in subset if r.get("confidence") is not None]
        stakes = []
        for r in subset:
            if r.get("ou_odds_class") != "OFFICIAL_PRICED":
                continue
            side = r.get("selected_side")
            o = r.get("ou_odds_over") if side == "over_2_5" else r.get("ou_odds_under")
            if o is None or float(o) <= 1.0:
                continue
            stakes.append({"hit": bool(r.get("hit")), "odds": float(o), "side": side})
        priced = priced_performance(stakes)
        return {
            "label": label,
            **accuracy_pack(hits, n),
            "average_predicted_probability": (sum(confs) / len(confs)) if confs else None,
            "actual_hit_frequency": hits / n if n else None,
            "priced": priced,
            "odds_class_counts": dict(Counter(r.get("ou_odds_class") for r in subset)),
        }

    over = [r for r in rows if r.get("selected_side") == "over_2_5"]
    under = [r for r in rows if r.get("selected_side") == "under_2_5"]
    return {
        "all": pack(rows, "all"),
        "over_only": pack(over, "over_2_5"),
        "under_only": pack(under, "under_2_5"),
    }


def feature_buckets(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dims = [
        "lambda_bucket",
        "prob_bucket",
        "top5_majority",
        "snapshot_stage",
        "cohort",
        "league",
        "model_agreement",
        "btts_prediction",
    ]
    out: dict[str, Any] = {}
    for dim in dims:
        buckets: dict[str, list[bool]] = defaultdict(list)
        for r in rows:
            buckets[str(r.get(dim) or "MISSING")].append(bool(r.get("hit")))
        out[dim] = {
            k: accuracy_pack(sum(1 for x in v if x), len(v))
            for k, v in sorted(buckets.items(), key=lambda kv: -len(kv[1]))
        }
    # BTTS alignment
    align: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        side = r.get("selected_side")
        b = r.get("btts_prediction")
        if side and b in {"yes", "no"}:
            key = f"{'Over' if side=='over_2_5' else 'Under'}+BTTS_{b.upper()}"
            align[key].append(bool(r.get("hit")))
    out["btts_alignment"] = {k: accuracy_pack(sum(1 for x in v if x), len(v)) for k, v in align.items()}
    return out


Predicate = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class Rule:
    side: str  # over_2_5 | under_2_5
    name: str
    conditions: tuple[str, ...]
    pred: Predicate

    def config(self) -> dict[str, Any]:
        return {"side": self.side, "name": self.name, "conditions": list(self.conditions)}

    @property
    def hash(self) -> str:
        return config_hash(self.config())


def _build_rules() -> list[Rule]:
    rules: list[Rule] = []

    # --- OVER singles ---
    for thr in (2.2, 2.5, 2.8, 3.0, 3.2):
        rules.append(
            Rule(
                "over_2_5",
                f"over_lambda_ge_{thr}",
                (f"total_lambda>={thr}", "selected=over_2_5"),
                lambda r, t=thr: r.get("selected_side") == "over_2_5"
                and r.get("total_lambda") is not None
                and float(r["total_lambda"]) >= t,
            )
        )
    for thr in (0.55, 0.60, 0.65, 0.70, 0.75):
        rules.append(
            Rule(
                "over_2_5",
                f"over_prob_ge_{int(thr*100)}",
                (f"over_probability>={thr}", "selected=over_2_5"),
                lambda r, t=thr: r.get("selected_side") == "over_2_5"
                and r.get("over_probability") is not None
                and float(r["over_probability"]) >= t,
            )
        )
    for k in (3, 4, 5):
        rules.append(
            Rule(
                "over_2_5",
                f"over_top5_count_ge_{k}",
                (f"top5_over_count>={k}", "selected=over_2_5"),
                lambda r, kk=k: r.get("selected_side") == "over_2_5"
                and int(r.get("top5_over_count") or 0) >= kk,
            )
        )
    for thr in (0.35, 0.45, 0.55):
        rules.append(
            Rule(
                "over_2_5",
                f"over_ecse_mass_ge_{int(thr*100)}",
                (f"ecse_over_mass_top5>={thr}", "selected=over_2_5"),
                lambda r, t=thr: r.get("selected_side") == "over_2_5"
                and r.get("ecse_over_mass_top5") is not None
                and float(r["ecse_over_mass_top5"]) >= t,
            )
        )

    # --- UNDER singles ---
    for thr in (2.5, 2.2, 2.0, 1.9, 1.8):
        rules.append(
            Rule(
                "under_2_5",
                f"under_lambda_le_{thr}",
                (f"total_lambda<={thr}", "selected=under_2_5"),
                lambda r, t=thr: r.get("selected_side") == "under_2_5"
                and r.get("total_lambda") is not None
                and float(r["total_lambda"]) <= t,
            )
        )
    for thr in (0.55, 0.60, 0.65, 0.70, 0.75):
        rules.append(
            Rule(
                "under_2_5",
                f"under_prob_ge_{int(thr*100)}",
                (f"under_probability>={thr}", "selected=under_2_5"),
                lambda r, t=thr: r.get("selected_side") == "under_2_5"
                and r.get("under_probability") is not None
                and float(r["under_probability"]) >= t,
            )
        )
    for k in (3, 4, 5):
        rules.append(
            Rule(
                "under_2_5",
                f"under_top5_count_ge_{k}",
                (f"top5_under_count>={k}", "selected=under_2_5"),
                lambda r, kk=k: r.get("selected_side") == "under_2_5"
                and int(r.get("top5_under_count") or 0) >= kk,
            )
        )
    for thr in (0.35, 0.45, 0.55):
        rules.append(
            Rule(
                "under_2_5",
                f"under_ecse_mass_ge_{int(thr*100)}",
                (f"ecse_under_mass_top5>={thr}", "selected=under_2_5"),
                lambda r, t=thr: r.get("selected_side") == "under_2_5"
                and r.get("ecse_under_mass_top5") is not None
                and float(r["ecse_under_mass_top5"]) >= t,
            )
        )

    # --- two/three condition compositions ---
    combos_over = [
        (
            "over_lambda_ge_2_5_prob_ge_60",
            ("total_lambda>=2.5", "over_probability>=0.60", "selected=over_2_5"),
            lambda r: r.get("selected_side") == "over_2_5"
            and r.get("total_lambda") is not None
            and float(r["total_lambda"]) >= 2.5
            and r.get("over_probability") is not None
            and float(r["over_probability"]) >= 0.60,
        ),
        (
            "over_lambda_ge_2_8_top5_ge_4",
            ("total_lambda>=2.8", "top5_over_count>=4", "selected=over_2_5"),
            lambda r: r.get("selected_side") == "over_2_5"
            and r.get("total_lambda") is not None
            and float(r["total_lambda"]) >= 2.8
            and int(r.get("top5_over_count") or 0) >= 4,
        ),
        (
            "over_prob_ge_65_btts_yes",
            ("over_probability>=0.65", "btts=yes", "selected=over_2_5"),
            lambda r: r.get("selected_side") == "over_2_5"
            and r.get("over_probability") is not None
            and float(r["over_probability"]) >= 0.65
            and r.get("btts_prediction") == "yes",
        ),
        (
            "over_lambda_ge_2_5_mass_ge_45_entropy_le_2",
            ("total_lambda>=2.5", "ecse_over_mass_top5>=0.45", "entropy<=2.0", "selected=over_2_5"),
            lambda r: r.get("selected_side") == "over_2_5"
            and r.get("total_lambda") is not None
            and float(r["total_lambda"]) >= 2.5
            and r.get("ecse_over_mass_top5") is not None
            and float(r["ecse_over_mass_top5"]) >= 0.45
            and (r.get("entropy") is None or float(r["entropy"]) <= 2.0),
        ),
        (
            "over_prob_ge_60_top5_ge_3_agree",
            ("over_probability>=0.60", "top5_over_count>=3", "model_agreement=AGREE", "selected=over_2_5"),
            lambda r: r.get("selected_side") == "over_2_5"
            and r.get("over_probability") is not None
            and float(r["over_probability"]) >= 0.60
            and int(r.get("top5_over_count") or 0) >= 3
            and r.get("model_agreement") == "AGREE",
        ),
    ]
    for name, conds, pred in combos_over:
        rules.append(Rule("over_2_5", name, conds, pred))

    combos_under = [
        (
            "under_lambda_le_2_2_prob_ge_60",
            ("total_lambda<=2.2", "under_probability>=0.60", "selected=under_2_5"),
            lambda r: r.get("selected_side") == "under_2_5"
            and r.get("total_lambda") is not None
            and float(r["total_lambda"]) <= 2.2
            and r.get("under_probability") is not None
            and float(r["under_probability"]) >= 0.60,
        ),
        (
            "under_lambda_le_2_0_top5_ge_4",
            ("total_lambda<=2.0", "top5_under_count>=4", "selected=under_2_5"),
            lambda r: r.get("selected_side") == "under_2_5"
            and r.get("total_lambda") is not None
            and float(r["total_lambda"]) <= 2.0
            and int(r.get("top5_under_count") or 0) >= 4,
        ),
        (
            "under_prob_ge_65_btts_no",
            ("under_probability>=0.65", "btts=no", "selected=under_2_5"),
            lambda r: r.get("selected_side") == "under_2_5"
            and r.get("under_probability") is not None
            and float(r["under_probability"]) >= 0.65
            and r.get("btts_prediction") == "no",
        ),
        (
            "under_lambda_le_2_2_lowmass_ge_40_tail_le_15",
            ("total_lambda<=2.2", "low_score_six_mass>=0.40", "high_score_tail_mass<=0.15", "selected=under_2_5"),
            lambda r: r.get("selected_side") == "under_2_5"
            and r.get("total_lambda") is not None
            and float(r["total_lambda"]) <= 2.2
            and float(r.get("low_score_six_mass") or 0) >= 0.40
            and float(r.get("high_score_tail_mass") or 0) <= 0.15,
        ),
        (
            "under_prob_ge_60_top5_ge_3_entropy_le_2",
            ("under_probability>=0.60", "top5_under_count>=3", "entropy<=2.0", "selected=under_2_5"),
            lambda r: r.get("selected_side") == "under_2_5"
            and r.get("under_probability") is not None
            and float(r["under_probability"]) >= 0.60
            and int(r.get("top5_under_count") or 0) >= 3
            and (r.get("entropy") is None or float(r["entropy"]) <= 2.0),
        ),
        (
            "under_prob_ge_55_mass_ge_45",
            ("under_probability>=0.55", "ecse_under_mass_top5>=0.45", "selected=under_2_5"),
            lambda r: r.get("selected_side") == "under_2_5"
            and r.get("under_probability") is not None
            and float(r["under_probability"]) >= 0.55
            and r.get("ecse_under_mass_top5") is not None
            and float(r["ecse_under_mass_top5"]) >= 0.45,
        ),
    ]
    for name, conds, pred in combos_under:
        rules.append(Rule("under_2_5", name, conds, pred))

    # five-condition limited
    rules.append(
        Rule(
            "under_2_5",
            "under_strict_5cond",
            (
                "selected=under_2_5",
                "total_lambda<=2.2",
                "under_probability>=0.60",
                "top5_under_count>=3",
                "btts=no",
            ),
            lambda r: r.get("selected_side") == "under_2_5"
            and r.get("total_lambda") is not None
            and float(r["total_lambda"]) <= 2.2
            and r.get("under_probability") is not None
            and float(r["under_probability"]) >= 0.60
            and int(r.get("top5_under_count") or 0) >= 3
            and r.get("btts_prediction") == "no",
        )
    )
    rules.append(
        Rule(
            "over_2_5",
            "over_strict_5cond",
            (
                "selected=over_2_5",
                "total_lambda>=2.5",
                "over_probability>=0.60",
                "top5_over_count>=3",
                "btts=yes",
            ),
            lambda r: r.get("selected_side") == "over_2_5"
            and r.get("total_lambda") is not None
            and float(r["total_lambda"]) >= 2.5
            and r.get("over_probability") is not None
            and float(r["over_probability"]) >= 0.60
            and int(r.get("top5_over_count") or 0) >= 3
            and r.get("btts_prediction") == "yes",
        )
    )
    return rules


def walk_forward(rows: list[dict[str, Any]], folds: int = 3) -> list[list[dict[str, Any]]]:
    data = chrono_sort(rows)
    if len(data) < folds:
        return [data] if data else []
    size = len(data) // folds
    out = []
    for i in range(folds):
        start = i * size
        end = (i + 1) * size if i < folds - 1 else len(data)
        out.append(data[start:end])
    return out


def evaluate_rule(rule: Rule, rows: list[dict[str, Any]], universe: int) -> dict[str, Any]:
    selected = [r for r in rows if rule.pred(r)]
    hits_list = [bool(r.get("hit")) for r in selected]
    n = len(selected)
    hits = sum(1 for h in hits_list if h)
    pack = accuracy_pack(hits, n)
    stakes = []
    for r in selected:
        if r.get("ou_odds_class") != "OFFICIAL_PRICED":
            continue
        o = r.get("ou_odds_over") if rule.side == "over_2_5" else r.get("ou_odds_under")
        if o is None or float(o) <= 1.0:
            continue
        stakes.append({"hit": bool(r.get("hit")), "odds": float(o), "side": rule.side})
    priced = priced_performance(stakes)
    folds = walk_forward(rows, 3)
    fold_stats = []
    for i, fold in enumerate(folds):
        fs = [r for r in fold if rule.pred(r)]
        fh = sum(1 for r in fs if r.get("hit"))
        fold_stats.append({"fold": i + 1, "n": len(fs), "accuracy": (fh / len(fs)) if fs else None})
    fold_accs = [f["accuracy"] for f in fold_stats if f["accuracy"] is not None]
    leagues = Counter(str(r.get("league") or "UNKNOWN") for r in selected)
    top_league_share = (leagues.most_common(1)[0][1] / n) if n and leagues else None
    sens = remove_one_win_sensitivity(hits_list)
    boot = bootstrap_accuracy(hits_list)
    label = LABEL_DIAGNOSTIC
    material = (pack["accuracy"] or 0) >= (RAW_OU_BASELINE + 0.04)
    stable = len(fold_accs) >= 2 and min(fold_accs) >= 0.50 and (max(fold_accs) - min(fold_accs)) <= 0.25
    concentrated = bool(top_league_share and top_league_share >= 0.50)
    if n >= 100 and material and stable and priced.get("priced_n", 0) >= 30 and (priced.get("roi") or -1) >= 0 and not sens["collapses"] and not concentrated:
        label = LABEL_SUPPORTED
    elif n >= 30 and material and stable and not sens["collapses"] and not concentrated:
        label = LABEL_PROMISING
    elif n >= 20:
        label = LABEL_DIAGNOSTIC
    else:
        label = LABEL_DIAGNOSTIC

    return {
        "config_hash": rule.hash,
        "side": rule.side,
        "name": rule.name,
        "conditions": list(rule.conditions),
        "n": n,
        "wins": hits,
        "losses": n - hits,
        "accuracy": pack["accuracy"],
        "wilson_95": pack["wilson_95"],
        "coverage": (n / universe) if universe else None,
        "priced_n": priced.get("priced_n"),
        "average_odds": priced.get("average_odds"),
        "roi": priced.get("roi"),
        "max_drawdown": priced.get("max_drawdown"),
        "longest_losing_streak": priced.get("longest_losing_streak"),
        "fold_stats": fold_stats,
        "mean_fold_accuracy": (sum(fold_accs) / len(fold_accs)) if fold_accs else None,
        "worst_fold_accuracy": min(fold_accs) if fold_accs else None,
        "fold_stability_range": (max(fold_accs) - min(fold_accs)) if len(fold_accs) >= 2 else None,
        "league_concentration_top_share": top_league_share,
        "league_top": leagues.most_common(3),
        "remove_one_win": sens,
        "bootstrap_95": boot,
        "overfit_risk": (
            "HIGH"
            if sens["collapses"] or concentrated or n < 20
            else ("MEDIUM" if n < 50 or not stable else "LOW")
        ),
        "label": label,
        "complexity": len(rule.conditions),
    }


def search_rules(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    universe = len(rows) or 1
    seen: set[str] = set()
    results = []
    for rule in _build_rules():
        if rule.hash in seen:
            continue
        seen.add(rule.hash)
        results.append(evaluate_rule(rule, rows, universe))
    results.sort(key=lambda r: (-(r.get("accuracy") or 0), -(r.get("n") or 0), r.get("name") or ""))
    return results


def leaderboard(results: list[dict[str, Any]], min_n: int, min_cov: float | None = None) -> list[dict[str, Any]]:
    out = []
    for r in results:
        if (r.get("n") or 0) < min_n:
            continue
        if min_cov is not None and (r.get("coverage") or 0) < min_cov:
            continue
        out.append(r)
    return out


def label_program(results: list[dict[str, Any]], raw_acc: float | None) -> str:
    if any(r.get("label") == LABEL_SUPPORTED for r in results):
        return LABEL_SUPPORTED
    if any(r.get("label") == LABEL_PROMISING for r in results):
        return LABEL_PROMISING
    if raw_acc is not None:
        return LABEL_BASELINE
    return LABEL_NO_EDGE


# ---- ECSE direction filters ----

def ecse_direction_analysis(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """rows should be TF OU ledger rows that also carry WDE/ECSE 1x2 fields + actual from TF results.

    For direction we need actual_1x2 — attach if present; else skip.
    """
    usable = [r for r in rows if r.get("ecse_direction") and r.get("actual_1x2")]
    if not usable:
        # try derive actual_1x2 from total goals? can't. return empty
        return {"raw_n": 0, "note": "no actual_1x2 on ledger rows"}, []

    raw_hits = sum(1 for r in usable if r["ecse_direction"] == r["actual_1x2"])
    raw = accuracy_pack(raw_hits, len(usable))

    filters = []

    def add(name: str, conds: list[str], pred: Predicate) -> None:
        sel = [r for r in usable if pred(r)]
        h = sum(1 for r in sel if r["ecse_direction"] == r["actual_1x2"])
        pack = accuracy_pack(h, len(sel))
        folds = walk_forward(usable, 3)
        fold_acc = []
        for fold in folds:
            fs = [r for r in fold if pred(r)]
            if fs:
                fold_acc.append(sum(1 for r in fs if r["ecse_direction"] == r["actual_1x2"]) / len(fs))
        filters.append(
            {
                "name": name,
                "conditions": conds,
                "config_hash": config_hash({"name": name, "conditions": conds}),
                "n": len(sel),
                "coverage": len(sel) / len(usable) if usable else None,
                **pack,
                "mean_fold_accuracy": (sum(fold_acc) / len(fold_acc)) if fold_acc else None,
                "worst_fold_accuracy": min(fold_acc) if fold_acc else None,
                "side_breakdown": dict(
                    Counter(r["ecse_direction"] for r in sel)
                ),
            }
        )

    add("raw_all", ["all"], lambda r: True)
    add(
        "agree_wde",
        ["ecse==wde"],
        lambda r: r.get("wde_decision") and r.get("ecse_direction") == r.get("wde_decision"),
    )
    add(
        "top5_mass_ge_45",
        ["top5_mass>=0.45"],
        lambda r: r.get("top5_mass") is not None and float(r["top5_mass"]) >= 0.45,
    )
    add(
        "entropy_le_1_8",
        ["entropy<=1.8"],
        lambda r: r.get("entropy") is not None and float(r["entropy"]) <= 1.8,
    )
    add(
        "lambda_ge_2_5",
        ["total_lambda>=2.5"],
        lambda r: r.get("total_lambda") is not None and float(r["total_lambda"]) >= 2.5,
    )
    add(
        "agree_and_top5_ge_45",
        ["ecse==wde", "top5_mass>=0.45"],
        lambda r: r.get("wde_decision")
        and r.get("ecse_direction") == r.get("wde_decision")
        and r.get("top5_mass") is not None
        and float(r["top5_mass"]) >= 0.45,
    )
    add(
        "agree_entropy_le_1_8_lambda_ge_2_2",
        ["ecse==wde", "entropy<=1.8", "total_lambda>=2.2"],
        lambda r: r.get("wde_decision")
        and r.get("ecse_direction") == r.get("wde_decision")
        and r.get("entropy") is not None
        and float(r["entropy"]) <= 1.8
        and r.get("total_lambda") is not None
        and float(r["total_lambda"]) >= 2.2,
    )
    add(
        "home_only_agree",
        ["ecse=home", "ecse==wde"],
        lambda r: r.get("ecse_direction") == "home_win"
        and r.get("wde_decision") == "home_win",
    )
    add(
        "away_only_agree",
        ["ecse=away", "ecse==wde"],
        lambda r: r.get("ecse_direction") == "away_win"
        and r.get("wde_decision") == "away_win",
    )
    add(
        "fav_odds_le_1_8_agree",
        ["min(HDA_odds)<=1.8", "ecse==wde"],
        lambda r: r.get("wde_decision")
        and r.get("ecse_direction") == r.get("wde_decision")
        and r.get("odds_home")
        and r.get("odds_draw")
        and r.get("odds_away")
        and min(float(r["odds_home"]), float(r["odds_draw"]), float(r["odds_away"])) <= 1.8,
    )
    add(
        "final_prematch_or_late",
        ["snapshot in LATE/FINAL"],
        lambda r: r.get("snapshot_stage") in {"LATE", "FINAL_PREMATCH"},
    )

    filters.sort(key=lambda x: (-(x.get("accuracy") or 0), -(x.get("n") or 0)))
    summary = {
        "raw": raw,
        "raw_accuracy": raw.get("accuracy"),
        "n_usable": len(usable),
        "best_filter": filters[0] if filters else None,
        "note": "Filters are research-only; do not force 75%.",
    }
    return summary, filters


def exact_top5_segments(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Requires top5_hit on rows — compute if missing via actual score vs ranks not available here.

    Ledger stores hit for O/U only. For Exact we need separate flag — use actual_total + top1 proxy insufficient.
    We'll accept rows with 'exact_top5_hit' if present.
    """
    usable = [r for r in rows if r.get("exact_top5_hit") is not None]
    if not usable:
        return {"n": 0, "note": "exact_top5_hit not attached"}, []

    def bucket_report(key_fn, name: str) -> dict[str, Any]:
        buckets: dict[str, list[bool]] = defaultdict(list)
        for r in usable:
            buckets[str(key_fn(r))].append(bool(r.get("exact_top5_hit")))
        return {
            k: accuracy_pack(sum(1 for x in v if x), len(v))
            for k, v in sorted(buckets.items(), key=lambda kv: -len(kv[1]))
        }

    analysis = {
        "n": len(usable),
        "overall": accuracy_pack(sum(1 for r in usable if r.get("exact_top5_hit")), len(usable)),
        "by_top5_mass": bucket_report(
            lambda r: (
                "<0.35"
                if (r.get("top5_mass") or 0) < 0.35
                else (
                    "0.35-0.45"
                    if (r.get("top5_mass") or 0) < 0.45
                    else ("0.45-0.55" if (r.get("top5_mass") or 0) < 0.55 else ">=0.55")
                )
            ),
            "top5_mass",
        ),
        "by_entropy": bucket_report(
            lambda r: (
                "MISSING"
                if r.get("entropy") is None
                else ("<=1.5" if float(r["entropy"]) <= 1.5 else ("1.5-2.0" if float(r["entropy"]) <= 2.0 else ">2.0"))
            ),
            "entropy",
        ),
        "by_lambda": bucket_report(lambda r: r.get("lambda_bucket") or "MISSING", "lambda"),
        "by_ou_alignment": bucket_report(
            lambda r: (
                "OU_HIT" if r.get("hit") else "OU_MISS"
            ),
            "ou",
        ),
        "by_btts": bucket_report(lambda r: r.get("btts_prediction") or "MISSING", "btts"),
        "by_agreement": bucket_report(lambda r: r.get("model_agreement") or "MISSING", "agree"),
        "by_league": bucket_report(lambda r: r.get("league") or "UNKNOWN", "league"),
    }

    # coverage candidates: high top5 mass + OU agreement research-only
    candidates = []
    for r in usable:
        if r.get("top5_mass") is not None and float(r["top5_mass"]) >= 0.50 and r.get("hit"):
            candidates.append(
                {
                    "fixture_id": r["fixture_id"],
                    "top5_mass": r.get("top5_mass"),
                    "exact_top5_hit": r.get("exact_top5_hit"),
                    "ou_hit": r.get("hit"),
                    "selected_ou": r.get("selected_side"),
                    "note": "RESEARCH_ONLY_3_EXACT_PLUS_1_COVERAGE_CANDIDATE_SHAPE",
                }
            )
    return analysis, candidates[:100]
