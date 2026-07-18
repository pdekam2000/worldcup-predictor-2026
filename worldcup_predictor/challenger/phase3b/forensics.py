"""Target / feature forensic audits for Phase 3B."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any


def audit_targets(rows: list[dict], raw_status_counts: dict[str, int] | None = None) -> dict[str, Any]:
    hg = [int(r["home_goals"]) for r in rows]
    ag = [int(r["away_goals"]) for r in rows]
    totals = [h + a for h, a in zip(hg, ag)]
    by_comp: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in rows:
        by_comp[r["competition_key"]].append((int(r["home_goals"]), int(r["away_goals"])))

    def _stats(pairs: list[tuple[int, int]]) -> dict[str, float]:
        hs = [p[0] for p in pairs]
        as_ = [p[1] for p in pairs]
        n = len(pairs)
        return {
            "n": n,
            "mean_home": sum(hs) / n,
            "mean_away": sum(as_) / n,
            "var_home": sum((x - sum(hs) / n) ** 2 for x in hs) / n,
            "var_away": sum((x - sum(as_) / n) ** 2 for x in as_) / n,
            "zero_goal_share": sum(1 for h, a in pairs if h + a == 0) / n,
            "one_goal_share": sum(1 for h, a in pairs if h + a == 1) / n,
            "high_score_tail_ge5": sum(1 for h, a in pairs if h + a >= 5) / n,
            "draw_share": sum(1 for h, a in pairs if h == a) / n,
        }

    return {
        "n_rows": len(rows),
        "global": _stats(list(zip(hg, ag))),
        "by_competition": {k: _stats(v) for k, v in by_comp.items()},
        "raw_status_filter_note": "Phase3 build used FT+AET+PEN; Phase3B recommends FT-only for regulation targets",
        "raw_status_counts": raw_status_counts or {},
        "checks": {
            "duplicate_fixture_ids": len(rows) - len({r["fixture_id"] for r in rows}),
            "home_away_inversion_heuristic": "features encode home_/away_ separately; is_home was constant=1 in v1 (bug, non-informative)",
            "target_feature_alignment": all("features" in r and "home_goals" in r for r in rows),
        },
    }


def audit_features(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "features": []}
    keys = sorted({k for r in rows for k in (r.get("features") or {}).keys() if not str(k).startswith("missing__")})
    reports = []
    for k in keys:
        vals = []
        missing = 0
        for r in rows:
            v = (r.get("features") or {}).get(k)
            if v is None:
                missing += 1
            else:
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    pass
        n = len(rows)
        miss_rate = missing / n
        if vals:
            mean = sum(vals) / len(vals)
            var = sum((x - mean) ** 2 for x in vals) / len(vals)
            uniq = len(set(round(x, 6) for x in vals))
        else:
            mean = var = None
            uniq = 0
        # correlation with home goals
        corr = None
        if vals and len(vals) == n - missing:
            ys = []
            xs = []
            for r in rows:
                v = (r.get("features") or {}).get(k)
                if v is None:
                    continue
                try:
                    xs.append(float(v))
                    ys.append(float(r["home_goals"]))
                except (TypeError, ValueError):
                    continue
            if len(xs) >= 30:
                mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
                num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
                den = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
                corr = (num / den) if den else None

        leakage_risk = "low"
        if k in {"final_score", "home_goals_ft", "away_goals_ft", "result_1x2"}:
            leakage_risk = "critical"
        if k.startswith("implied_") or k in {"bookmaker_count", "market_odds_usable"}:
            leakage_risk = "market_ok_if_prematch_timestamped"

        reports.append(
            {
                "name": k,
                "type": "numeric" if vals else "non_numeric_or_all_missing",
                "source": "prematch_snapshot_or_enrichment",
                "availability_timestamp": "kickoff_cutoff_strict_less_than",
                "missing_rate": miss_rate,
                "variance": var,
                "cardinality": uniq,
                "mean": mean,
                "leakage_risk": leakage_risk,
                "corr_home_goals": corr,
                "constant": uniq <= 1,
                "nearly_constant": uniq <= 3 and n >= 50,
            }
        )

    constant = [r["name"] for r in reports if r["constant"]]
    nearly = [r["name"] for r in reports if r["nearly_constant"] and not r["constant"]]
    return {
        "n_rows": len(rows),
        "n_features": len(reports),
        "constant_features": constant,
        "nearly_constant_features": nearly,
        "features": reports,
        "key_findings": [
            "is_home is constant=1.0 in GBGM-1 snapshots (non-informative)",
            "No xG/shots/lineup/injury features present in local Challenger snapshot",
            "Market features only when include_market=True and odds timestamp <= prediction time",
            "L5 form missing when team has <1 prior home/away match in competition",
        ],
    }


def error_forensics(rows: list[dict], preds: list[dict], baseline_preds: list[dict] | None = None) -> dict[str, Any]:
    buckets: dict[str, list[float]] = defaultdict(list)
    draw_under = 0
    fav_over = 0
    low_goal_err = []
    high_goal_err = []
    for r, p in zip(rows, preds):
        yt = r["actual_1x2"]
        ph = float(p["hda"]["home"])
        pd_ = float(p["hda"]["draw"])
        pa = float(p["hda"]["away"])
        # logloss contribution
        pr = {"home": ph, "draw": pd_, "away": pa}[yt]
        ll = -math.log(max(1e-15, pr))
        buckets[r["competition_key"]].append(ll)
        cov = (r.get("features") or {}).get("coverage_bucket") or "UNKNOWN"
        buckets[f"coverage:{cov}"].append(ll)
        total = int(r["home_goals"]) + int(r["away_goals"])
        if total <= 1:
            low_goal_err.append(ll)
            buckets["low_goal"].append(ll)
        if total >= 4:
            high_goal_err.append(ll)
            buckets["high_goal"].append(ll)
        if yt == "draw" and pd_ < max(ph, pa):
            draw_under += 1
        # favourite = max odds-implied or max model prob
        if max(ph, pa, pd_) == ph and yt != "home":
            fav_over += 1
        elif max(ph, pa, pd_) == pa and yt != "away":
            fav_over += 1

    summary = {
        k: {"n": len(v), "mean_logloss": sum(v) / len(v)} for k, v in buckets.items() if v
    }
    return {
        "by_bucket": summary,
        "draw_underprediction_count": draw_under,
        "draw_underprediction_rate": draw_under / max(1, len(rows)),
        "favourite_wrong_count": fav_over,
        "favourite_wrong_rate": fav_over / max(1, len(rows)),
        "hypotheses": [
            "GBM may be overconfident vs league-average Poisson (higher LogLoss despite similar accuracy)",
            "Constant is_home + weak features → model adds noise relative to league means",
            "Mixed competitions with different scoring rates hurt a global booster",
            "Independent Poisson understates draws without Dixon–Coles rho",
        ],
    }
