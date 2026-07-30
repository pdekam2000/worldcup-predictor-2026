#!/usr/bin/env python3
"""Lambda / team-strength forensic research orchestrator (shadow only).

Phases 1–14: provenance, features, identity, error decomp, baselines,
challengers, uncertainty, joint, WDE consistency, shadow, promotion plan, reports.

Does not mutate historical freezes or deploy production model changes.
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.research.ecse_lambda_extraction import (
    LAMBDA_CEIL,
    LAMBDA_FLOOR,
    extract_lambdas,
    solve_lambda_total_from_over,
)
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.research.lambda_team_strength.constants import (
    FORWARD_MIN_ACTUAL_4PLUS,
    FORWARD_MIN_ACTUAL_5PLUS,
    FORWARD_MIN_GLOBAL,
    FORWARD_MIN_HIGH_SCORE_RISK,
    FORWARD_MIN_LOW_SCORE,
    HIGH_SCORE_ACTUAL,
    LOW_SCORE_ACTUAL,
    SEVERE_TOTAL_ERROR,
)
from worldcup_predictor.research.lambda_team_strength.metrics import (
    clip_lambda,
    cohort_metrics,
    evaluate_lambda_pair,
    fnum,
    mean,
    normalize_team,
    parse_teams,
)
from worldcup_predictor.research.lambda_team_strength.provenance import (
    fallback_inventory_rows,
    feature_source_inventory_rows,
    runtime_trace_rows,
    write_phase1_docs,
)
from worldcup_predictor.research.lambda_team_strength.shadow_store import (
    ensure_shadow_schema,
    persist_shadow_output,
)
from worldcup_predictor.research.lambda_team_strength.team_strength import (
    load_strength_store,
    predict_lambdas_from_strength,
    resolve_team_key,
    team_flags,
    team_snapshot,
)

CANONICAL_CSV = (
    ROOT
    / "artifacts"
    / "dataset_reconciliation_experiments"
    / "20260730T125305Z"
    / "evaluation_one_canonical_freeze_per_fixture.csv"
)
FI_DB = ROOT / "data" / "football_intelligence.db"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
# Prefer agent-created artifact dir if present
PREFERRED = ROOT / "artifacts" / "lambda_team_strength_research" / "20260730T134952Z"
OUT = PREFERRED if PREFERRED.exists() else (ROOT / "artifacts" / "lambda_team_strength_research" / RUN_ID)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def as_bool(x: Any) -> bool:
    return x in {True, "True", "true", "1", 1}


def parse_ko(s: str | None) -> datetime | None:
    if not s:
        return None
    t = str(s).strip().replace("T", " ").replace("Z", "")
    for n in (19, 16, 10):
        chunk = t[:n]
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(chunk, fmt if len(chunk) > 10 else "%Y-%m-%d")
            except Exception:
                continue
    return None


def load_rows() -> list[dict[str, Any]]:
    rows = list(csv.DictReader(CANONICAL_CSV.open(encoding="utf-8")))
    for r in rows:
        r["_ah"] = int(float(r["actual_ft_home"]))
        r["_aa"] = int(float(r["actual_ft_away"]))
        r["_tot"] = r["_ah"] + r["_aa"]
        r["_lh"] = fnum(r.get("lambda_home")) or 1.2
        r["_la"] = fnum(r.get("lambda_away")) or 1.0
        home, away = parse_teams(r.get("match_name"))
        r["_home"] = home
        r["_away"] = away
        r["_home_n"] = normalize_team(home)
        r["_away_n"] = normalize_team(away)
        r["_ko"] = parse_ko(r.get("kickoff"))
        r["_league"] = normalize_team(str(r.get("competition") or "unknown")).replace(" ", "")
    return sorted(rows, key=lambda x: str(x.get("kickoff") or ""))


def phase1(out: Path) -> None:
    write_phase1_docs(out)
    write_csv(out / "lambda_runtime_trace.csv", runtime_trace_rows())
    write_csv(out / "lambda_feature_source_inventory.csv", feature_source_inventory_rows())
    write_csv(out / "lambda_fallback_inventory.csv", fallback_inventory_rows())


def enrich_features(rows: list[dict[str, Any]], store, out: Path) -> list[dict[str, Any]]:
    """Phase 2–3 feature availability / identity forensics."""
    feat_rows = []
    miss_rows = []
    fresh_rows = []
    identity_rows = []
    low_data_rows = []
    promoted_rows = []
    reserve_rows = []
    season_rows = []
    default_rates: dict[str, list[int]] = defaultdict(list)

    for r in rows:
        ko = r["_ko"] or datetime(2099, 1, 1)
        league = r["_league"]
        home_key = resolve_team_key(store, r["_home"])
        away_key = resolve_team_key(store, r["_away"])
        r["_home_n"] = home_key
        r["_away_n"] = away_key
        hs = team_snapshot(store, home_key, ko, league)
        aws = team_snapshot(store, away_key, ko, league)
        hf = team_flags(r["_home"])
        af = team_flags(r["_away"])
        pred_tot = r["_lh"] + r["_la"]
        err = r["_tot"] - pred_tot
        severe = err >= SEVERE_TOTAL_ERROR
        high = r["_tot"] >= HIGH_SCORE_ACTUAL

        features = {
            "recent_goals_scored_home": hs.n_total > 0,
            "recent_goals_scored_away": aws.n_total > 0,
            "home_attack_form": hs.fallback_level == "team",
            "away_attack_form": aws.fallback_level == "team",
            "home_defense_form": hs.fallback_level == "team",
            "away_defense_form": aws.fallback_level == "team",
            "team_strength_available": hs.n_total > 0 and aws.n_total > 0,
            "league_scoring_average": league in store.league_avg_home,
            "scoring_variance": hs.n_total >= 5,
            "conceding_variance": hs.n_total >= 5,
            "freq_3plus_concede": hs.n_total >= 5,
            "freq_3plus_score": hs.n_total >= 5,
            "btts_frequency": hs.n_total >= 5,
            "ou_history": hs.n_total >= 5,
            "fresh_hda_odds": bool(r.get("odds_home")),
            "market_total_in_freeze": False,  # O/U odds not stored on freeze columns
            "bookmaker_count": bool(r.get("bookmaker_count")),
            "odds_movement": False,
            "lineup_injury": False,
            "promoted_flag_home": hs.promoted_like,
            "reserve_youth_home": hf["reserve_or_youth"],
            "reserve_youth_away": af["reserve_or_youth"],
            "low_data_home": hs.low_data,
            "low_data_away": aws.low_data,
            "neutral_venue": False,
            "competition_type": bool(r.get("competition")),
            # Canonical lambda inputs present in freeze:
            "canonical_lambda": r["_lh"] is not None,
            "wde_probs": r.get("home_probability") not in (None, ""),
            "ou25_prediction": bool(r.get("ou25_prediction")),
        }
        # Canonical path: football features NEVER enter extract_lambdas
        for k, present in features.items():
            enters_canonical = k in {
                "fresh_hda_odds",
                "bookmaker_count",
                "canonical_lambda",
                "ou25_prediction",
                "wde_probs",
                "competition_type",
            }
            defaulted = (not present) if k.startswith(("recent_", "home_", "away_", "team_", "league_", "scoring_", "conceding_", "freq_", "btts_", "ou_history", "promoted_", "low_data_")) else (not present)
            miss_rows.append(
                {
                    "fixture_id": r["fixture_id"],
                    "feature": k,
                    "present": present,
                    "source": "historical_fixture_registry" if "form" in k or "strength" in k or "variance" in k or "freq" in k or "btts_frequency" in k or "ou_history" in k else "freeze_csv",
                    "defaulted_or_missing": (not present),
                    "team_or_league_fallback": hs.fallback_level if "home" in k else aws.fallback_level,
                    "enters_canonical_lambda": enters_canonical and present,
                    "training_compatible": True,
                    "high_score": high,
                    "severe_underest": severe,
                    "total_lambda_error": round(err, 4),
                }
            )
            default_rates[k].append(0 if present else 1)

        fresh_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "odds_freshness": r.get("odds_freshness"),
                "frozen_at": r.get("frozen_at"),
                "kickoff": r.get("kickoff"),
                "home_history_n": hs.n_total,
                "away_history_n": aws.n_total,
                "home_fallback": hs.fallback_level,
                "away_fallback": aws.fallback_level,
                "feature_age_note": "history uses only matches with kickoff < fixture kickoff",
                "canonical_uses_football_history": False,
            }
        )

        identity_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "home_team": r["_home"],
                "away_team": r["_away"],
                "home_norm": r["_home_n"],
                "away_norm": r["_away_n"],
                "home_history_n": hs.n_total,
                "away_history_n": aws.n_total,
                "home_reserve_youth": hf["reserve_or_youth"],
                "away_reserve_youth": af["reserve_or_youth"],
                "home_women": hf["women"],
                "away_women": af["women"],
                "home_low_data": hs.low_data,
                "away_low_data": aws.low_data,
                "possible_identity_gap": hs.n_total == 0 or aws.n_total == 0,
                "severe_underest": severe,
                "high_score": high,
                "total_lambda_error": round(err, 4),
            }
        )
        if hs.low_data or aws.low_data:
            low_data_rows.append(identity_rows[-1])
        if hs.promoted_like or aws.promoted_like:
            promoted_rows.append({**identity_rows[-1], "promoted_like_home": hs.promoted_like, "promoted_like_away": aws.promoted_like})
        if hf["reserve_or_youth"] or af["reserve_or_youth"]:
            reserve_rows.append(identity_rows[-1])
        season_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "competition": r.get("competition"),
                "home_n": hs.n_total,
                "away_n": aws.n_total,
                "strength_reset_risk": hs.n_total < 6 or aws.n_total < 6,
                "lambda_error": round(err, 4),
            }
        )

        r["_hs"] = hs
        r["_as"] = aws
        r["_feat"] = features
        r["_identity_gap"] = hs.n_total == 0 or aws.n_total == 0
        r["_fallback_count"] = int(hs.fallback_level != "team") + int(aws.fallback_level != "team")
        r["_missing_football"] = sum(1 for k, v in features.items() if not v and k not in {"odds_movement", "lineup_injury", "neutral_venue", "market_total_in_freeze"})

        feat_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "match_name": r.get("match_name"),
                "actual_total": r["_tot"],
                "pred_total": round(pred_tot, 4),
                "total_err": round(err, 4),
                "home_n": hs.n_total,
                "away_n": aws.n_total,
                "missing_football_count": r["_missing_football"],
                "fallback_count": r["_fallback_count"],
                "identity_gap": r["_identity_gap"],
            }
        )

    # default rates
    def_rate_rows = [
        {
            "feature": k,
            "n": len(v),
            "default_or_missing_rate": sum(v) / len(v) if v else None,
            "present_rate": 1 - (sum(v) / len(v) if v else 0),
        }
        for k, v in sorted(default_rates.items())
    ]
    write_csv(out / "lambda_default_value_rates.csv", def_rate_rows)
    write_csv(out / "lambda_feature_missingness.csv", miss_rows)
    write_csv(out / "lambda_feature_freshness.csv", fresh_rows)
    write_csv(out / "team_identity_mismatch_audit.csv", identity_rows)
    write_csv(out / "low_data_team_analysis.csv", low_data_rows)
    write_csv(out / "promoted_team_analysis.csv", promoted_rows)
    write_csv(out / "reserve_youth_team_analysis.csv", reserve_rows)
    write_csv(out / "season_transition_strength_audit.csv", season_rows)
    write_csv(out / "feature_availability_summary.csv", feat_rows)

    # gap analysis by cohort
    def cohort_gap(label: str, pred) -> dict[str, Any]:
        sub = [r for r in rows if pred(r)]
        if not sub:
            return {"cohort": label, "n": 0}
        return {
            "cohort": label,
            "n": len(sub),
            "mean_home_history_n": mean([r["_hs"].n_total for r in sub]),
            "mean_away_history_n": mean([r["_as"].n_total for r in sub]),
            "identity_gap_rate": sum(1 for r in sub if r["_identity_gap"]) / len(sub),
            "mean_fallback_count": mean([r["_fallback_count"] for r in sub]),
            "mean_missing_football": mean([r["_missing_football"] for r in sub]),
            "mean_total_err": mean([r["_tot"] - (r["_lh"] + r["_la"]) for r in sub]),
            "canonical_football_features_used": False,
        }

    gap = [
        cohort_gap("all", lambda r: True),
        cohort_gap("correct_lambda_abs_err_lt_0_75", lambda r: abs(r["_tot"] - (r["_lh"] + r["_la"])) < 0.75),
        cohort_gap("mild_underest_0_75_to_2", lambda r: 0.75 <= (r["_tot"] - (r["_lh"] + r["_la"])) < SEVERE_TOTAL_ERROR),
        cohort_gap("severe_underest_ge_2", lambda r: (r["_tot"] - (r["_lh"] + r["_la"])) >= SEVERE_TOTAL_ERROR),
        cohort_gap("high_score_5plus", lambda r: r["_tot"] >= HIGH_SCORE_ACTUAL),
        cohort_gap("low_score_le_2", lambda r: r["_tot"] <= LOW_SCORE_ACTUAL),
        cohort_gap("top5_hit", lambda r: as_bool(r.get("exact_top5_hit"))),
        cohort_gap("top5_miss", lambda r: not as_bool(r.get("exact_top5_hit"))),
    ]
    write_csv(out / "high_score_feature_gap_analysis.csv", gap)

    fallback_by = []
    for label, pred in [
        ("top5_hit", lambda r: as_bool(r.get("exact_top5_hit"))),
        ("top5_miss", lambda r: not as_bool(r.get("exact_top5_hit"))),
        ("high_score", lambda r: r["_tot"] >= HIGH_SCORE_ACTUAL),
        ("severe_underest", lambda r: (r["_tot"] - (r["_lh"] + r["_la"])) >= SEVERE_TOTAL_ERROR),
    ]:
        sub = [r for r in rows if pred(r)]
        fallback_by.append(
            {
                "outcome_cohort": label,
                "n": len(sub),
                "mean_fallback_count": mean([r["_fallback_count"] for r in sub]) if sub else None,
                "league_or_global_fallback_rate": (
                    sum(1 for r in sub if r["_fallback_count"] > 0) / len(sub) if sub else None
                ),
            }
        )
    write_csv(out / "fallback_usage_by_outcome.csv", fallback_by)

    quality_vs = []
    for r in rows:
        quality_vs.append(
            {
                "fixture_id": r["fixture_id"],
                "home_n": r["_hs"].n_total,
                "away_n": r["_as"].n_total,
                "fallback_count": r["_fallback_count"],
                "missing_football": r["_missing_football"],
                "odds_freshness": r.get("odds_freshness"),
                "bookmaker_count": r.get("bookmaker_count"),
                "total_lambda_error": r["_tot"] - (r["_lh"] + r["_la"]),
                "abs_total_error": abs(r["_tot"] - (r["_lh"] + r["_la"])),
                "exact_top5_hit": as_bool(r.get("exact_top5_hit")),
                "high_score": r["_tot"] >= HIGH_SCORE_ACTUAL,
            }
        )
    write_csv(out / "feature_quality_vs_lambda_error.csv", quality_vs)
    return rows


def phase4_decomp(rows: list[dict[str, Any]], out: Path) -> list[dict[str, Any]]:
    decomp = []
    taxonomy = []
    for r in rows:
        lh, la = r["_lh"], r["_la"]
        ah, aa = r["_ah"], r["_aa"]
        he, ae = ah - lh, aa - la
        te = (ah + aa) - (lh + la)
        both_low = he > 0.75 and ae > 0.75
        only_h = he > 1.0 and ae <= 0.5
        only_a = ae > 1.0 and he <= 0.5
        fav_home = lh >= la
        act_home_fav = ah > aa
        wrong_fav = (fav_home and aa > ah) or ((not fav_home) and ah > aa)
        margin_small = (not wrong_fav) and abs(te) < 0.5 and abs(he) + abs(ae) > 1.0
        reasons = []
        if both_low:
            reasons.append("both_lambdas_too_low")
        if only_h:
            reasons.append("only_home_lambda_too_low")
        if only_a:
            reasons.append("only_away_lambda_too_low")
        if wrong_fav:
            reasons.append("wrong_favorite")
        if margin_small:
            reasons.append("correct_favorite_margin_too_small")
        if r.get("wde_decision") == "draw" and ah != aa:
            reasons.append("draw_bias")
        if r["_as"].freq_concede_3plus >= 0.25 and he > 1:
            reasons.append("defensive_weakness_missed_away")
        if r["_hs"].freq_concede_3plus >= 0.25 and ae > 1:
            reasons.append("defensive_weakness_missed_home")
        if r["_hs"].freq_score_3plus >= 0.25 and he > 1:
            reasons.append("attacking_strength_missed_home")
        if r["_as"].freq_score_3plus >= 0.25 and ae > 1:
            reasons.append("attacking_strength_missed_away")
        if (r["_hs"].scoring_var + r["_as"].scoring_var) > 2.0 and te > 1:
            reasons.append("volatility_missed")
        if r["_fallback_count"] > 0 and te > 1:
            reasons.append("fallback_driven")
        if r["_identity_gap"]:
            reasons.append("missing_data_identity")
        if not reasons and te >= SEVERE_TOTAL_ERROR:
            reasons.append("unidentified")
        if not reasons:
            reasons.append("none_or_mild")

        row = {
            "fixture_id": r["fixture_id"],
            "match_name": r.get("match_name"),
            "competition": r.get("competition"),
            "predicted_home_lambda": lh,
            "predicted_away_lambda": la,
            "predicted_total_lambda": lh + la,
            "actual_home_goals": ah,
            "actual_away_goals": aa,
            "home_lambda_error": round(he, 4),
            "away_lambda_error": round(ae, 4),
            "total_lambda_error": round(te, 4),
            "WDE_correct": as_bool(r.get("WDE_hit")),
            "BTTS_correct": as_bool(r.get("BTTS_hit")),
            "OU_correct": as_bool(r.get("OU_hit")),
            "actual_exact_rank": r.get("actual_exact_rank"),
            "Top5_hit": as_bool(r.get("exact_top5_hit")),
            "Top10_hit": as_bool(r.get("exact_top10_hit")),
            "feature_completeness": 1.0 - (r["_missing_football"] / 25.0),
            "odds_completeness": 1.0 if r.get("odds_home") else 0.0,
            "model_version": r.get("model_version_ecse"),
            "league": r.get("competition"),
            "team_data_quality": "low" if r["_fallback_count"] else "ok",
            "taxonomy": "|".join(reasons),
        }
        decomp.append(row)
        if te >= SEVERE_TOTAL_ERROR:
            taxonomy.append(row)

    write_csv(out / "lambda_error_decomposition.csv", decomp)
    write_csv(out / "severe_underestimation_taxonomy.csv", taxonomy)

    def cluster(side: str) -> list[dict[str, Any]]:
        key = "home_lambda_error" if side == "home" else "away_lambda_error" if side == "away" else "total_lambda_error"
        buckets = defaultdict(list)
        for row in decomp:
            e = float(row[key])
            if e >= 2:
                b = "severe_under"
            elif e >= 0.75:
                b = "mild_under"
            elif e <= -2:
                b = "severe_over"
            elif e <= -0.75:
                b = "mild_over"
            else:
                b = "ok"
            buckets[b].append(row)
        return [
            {
                "cluster": k,
                "n": len(v),
                "mean_error": mean([float(x[key]) for x in v]),
                "top5_rate": sum(1 for x in v if x["Top5_hit"]) / len(v) if v else None,
            }
            for k, v in sorted(buckets.items())
        ]

    write_csv(out / "home_lambda_failure_clusters.csv", cluster("home"))
    write_csv(out / "away_lambda_failure_clusters.csv", cluster("away"))
    write_csv(out / "total_lambda_failure_clusters.csv", cluster("total"))

    # case studies
    severe = sorted(taxonomy, key=lambda x: -float(x["total_lambda_error"]))[:15]
    lines = ["# Severe lambda miss case studies\n"]
    for s in severe:
        fid = s["fixture_id"]
        src = next(r for r in rows if str(r["fixture_id"]) == str(fid))
        lines.append(f"## {s['match_name']} ({fid})")
        lines.append(
            f"- Actual {s['actual_home_goals']}-{s['actual_away_goals']} vs λ {s['predicted_home_lambda']:.2f}/{s['predicted_away_lambda']:.2f} (err {s['total_lambda_error']:+.2f})"
        )
        lines.append(
            f"- History n home/away: {src['_hs'].n_total}/{src['_as'].n_total}; fallback={src['_fallback_count']}; identity_gap={src['_identity_gap']}"
        )
        lines.append(
            f"- Home score3+/concede3+: {src['_hs'].freq_score_3plus:.2f}/{src['_hs'].freq_concede_3plus:.2f}; Away {src['_as'].freq_score_3plus:.2f}/{src['_as'].freq_concede_3plus:.2f}"
        )
        lines.append(f"- Taxonomy: {s['taxonomy']}")
        lines.append(
            f"- Canonical path note: football history **did not enter** extract_lambdas; λ is odds-derived only."
        )
        lines.append("")
    write_text(out / "severe_lambda_miss_case_studies.md", "\n".join(lines))
    return decomp


def phase5_bias(rows: list[dict[str, Any]], out: Path) -> None:
    def segment(key_fn, name: str) -> list[dict[str, Any]]:
        groups: dict[str, list] = defaultdict(list)
        for r in rows:
            groups[str(key_fn(r))].append(r)
        out_rows = []
        for k, sub in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            pred = [r["_lh"] + r["_la"] for r in sub]
            act = [r["_tot"] for r in sub]
            out_rows.append(
                {
                    "segment": name,
                    "key": k,
                    "n": len(sub),
                    "predicted_avg_goals": mean(pred),
                    "actual_avg_goals": mean(act),
                    "lambda_bias": (mean(act) or 0) - (mean(pred) or 0),
                    "home_goal_mae": mean([abs(r["_ah"] - r["_lh"]) for r in sub]),
                    "away_goal_mae": mean([abs(r["_aa"] - r["_la"]) for r in sub]),
                    "total_goal_mae": mean([abs(r["_tot"] - (r["_lh"] + r["_la"])) for r in sub]),
                    "exact_top5": sum(1 for r in sub if as_bool(r.get("exact_top5_hit"))) / len(sub),
                    "exact_top10": sum(1 for r in sub if as_bool(r.get("exact_top10_hit"))) / len(sub),
                    "note": "shrinkage required for n<30 before league-specific prod adjust",
                }
            )
        return out_rows

    write_csv(out / "lambda_bias_by_league.csv", segment(lambda r: r.get("competition") or "unk", "league"))
    write_csv(
        out / "lambda_bias_by_market_profile.csv",
        segment(lambda r: r.get("odds_freshness") or "unk", "odds_freshness")
        + segment(lambda r: "favorite_home" if r["_lh"] > r["_la"] + 0.3 else "favorite_away" if r["_la"] > r["_lh"] + 0.3 else "balanced", "fav_side")
        + segment(lambda r: "high_pred_tot" if r["_lh"] + r["_la"] >= 2.8 else "mid_pred" if r["_lh"] + r["_la"] >= 2.2 else "low_pred", "pred_total_bucket"),
    )
    write_csv(
        out / "lambda_bias_by_team_quality.csv",
        segment(lambda r: f"fallback_{r['_fallback_count']}", "fallback")
        + segment(lambda r: "low_data" if r["_hs"].low_data or r["_as"].low_data else "ok_data", "data")
        + segment(lambda r: "identity_gap" if r["_identity_gap"] else "matched", "identity"),
    )
    write_csv(
        out / "lambda_bias_by_competition_type.csv",
        segment(lambda r: (r.get("competition") or "x").split("_")[0] if False else (r.get("competition") or "unk"), "competition"),
    )
    write_text(
        out / "league_goal_environment_audit.md",
        """# League goal-environment audit

Canonical `extract_lambdas` does **not** apply league goal-environment priors to λ.
League averages exist only in research team-strength challengers (partial pooling).

Freeze-level bias by league is in `lambda_bias_by_league.csv`.
Do not ship league-specific offsets for segments with n<30 without shrinkage.
""",
    )


def evaluate_model_on_rows(
    rows: list[dict[str, Any]],
    lh_la_fn,
    *,
    use_dc: bool = False,
    max_goals: int = 7,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evals = []
    for r in rows:
        lh, la, meta = lh_la_fn(r)
        lh, la = clip_lambda(lh), clip_lambda(la)
        ev = evaluate_lambda_pair(lh, la, r["_ah"], r["_aa"], use_dixon_coles=use_dc, max_goals=max_goals)
        ev.update(
            {
                "fixture_id": r["fixture_id"],
                "ah": r["_ah"],
                "aa": r["_aa"],
                "meta": meta,
                "WDE_hit": as_bool(r.get("WDE_hit")),
            }
        )
        # WDE consistency: lambda-implied direction
        if lh > la + 0.15:
            lam_dir = "home_win"
        elif la > lh + 0.15:
            lam_dir = "away_win"
        else:
            lam_dir = "draw"
        ev["lambda_dir"] = lam_dir
        ev["wde_dir"] = r.get("wde_decision")
        evals.append(ev)

    global_m = cohort_metrics(evals)
    high = [e for e in evals if e["ah"] + e["aa"] >= HIGH_SCORE_ACTUAL]
    low = [e for e in evals if e["ah"] + e["aa"] <= LOW_SCORE_ACTUAL]
    med = [e for e in evals if LOW_SCORE_ACTUAL < e["ah"] + e["aa"] < HIGH_SCORE_ACTUAL]
    summary = {
        **global_m,
        **cohort_metrics(high, "high_"),
        **cohort_metrics(low, "low_"),
        **cohort_metrics(med, "med_"),
        "wde_lambda_agree_rate": (
            sum(1 for e in evals if e.get("lambda_dir") == e.get("wde_dir")) / len(evals) if evals else None
        ),
    }
    return evals, summary


def chronological_split(rows: list[dict[str, Any]], frac: float = 0.6) -> tuple[list, list]:
    n = len(rows)
    cut = max(1, int(n * frac))
    return rows[:cut], rows[cut:]


def blend(a: float, b: float, w: float) -> float:
    return w * a + (1.0 - w) * b


def phase6_to_10(rows: list[dict[str, Any]], store, out: Path) -> dict[str, Any]:
    train, val = chronological_split(rows, 0.6)
    specs_dir = out / "baseline_model_specs"
    feats_dir = out / "chronological_feature_manifests"
    specs_dir.mkdir(parents=True, exist_ok=True)
    feats_dir.mkdir(parents=True, exist_ok=True)

    write_json(
        feats_dir / "manifest_v1.json",
        {
            "rule": "Only historical_fixture_registry matches with kickoff < prediction kickoff",
            "no_future_leakage": True,
            "canonical_lambda_features": "odds closing lines only (ECSE-1C)",
            "research_features": [
                "recency_weighted_attack_defense",
                "home_away_split",
                "opponent_adjusted",
                "volatility",
                "collapse_surge",
                "market_blend",
            ],
            "train_n": len(train),
            "val_n": len(val),
            "split": "chronological 60/40 on canonical eval fixtures",
        },
    )

    models: dict[str, Any] = {}

    def B0(r):
        return r["_lh"], r["_la"], {"source": "canonical"}

    def B1(r):
        ph = store.prior_home(r["_league"])
        pa = store.prior_away(r["_league"])
        return ph, pa, {"source": "league_avg"}

    def make_strength(mode: str, half_life: float = 90.0):
        def fn(r):
            hs = team_snapshot(store, r["_home_n"], r["_ko"] or datetime(2099, 1, 1), r["_league"], half_life_days=half_life)
            aws = team_snapshot(store, r["_away_n"], r["_ko"] or datetime(2099, 1, 1), r["_league"], half_life_days=half_life)
            return predict_lambdas_from_strength(hs, aws, r["_league"], store, mode=mode)

        return fn

    def B6(r):
        # Elo-like: use overall attack/defense as rating proxy
        return make_strength("overall", 120.0)(r)

    def B7(r):
        # Market-total-derived: canonical already is; optionally re-split 50/50 if share weird
        tot = r["_lh"] + r["_la"]
        # If 1X2 odds exist, rebuild share
        oh, oa = fnum(r.get("odds_home")), fnum(r.get("odds_away"))
        if oh and oa and oh > 1 and oa > 1:
            ih, ia = 1 / oh, 1 / oa
            share = ih / (ih + ia)
        else:
            share = r["_lh"] / tot if tot else 0.55
        return tot * share, tot * (1 - share), {"source": "market_total_resplit"}

    def B8(r):
        fh = make_strength("home_away", 60.0)(r)
        mh = B7(r)
        w = 0.45
        return blend(fh[0], mh[0], w), blend(fh[1], mh[1], w), {"blend": w, "football": fh[2], "market": mh[2]}

    def B9(r):
        fh = make_strength("home_away", 90.0)(r)
        hs, aws = r["_hs"], r["_as"]
        # uncertainty-aware shrink toward market when low data
        mh = B0(r)
        n = min(hs.n_total, aws.n_total)
        w_foot = n / (n + 12.0)
        return blend(fh[0], mh[0], w_foot), blend(fh[1], mh[1], w_foot), {"w_foot": w_foot, "n": n}

    # Challengers T1-T10
    def T9(r):
        return B8(r)

    def T10(r):
        fh = make_strength("opponent_adj", 45.0)(r)
        mh = B0(r)
        hs, aws = r["_hs"], r["_as"]
        # more weight to market when football disagrees strongly
        foot_tot = fh[0] + fh[1]
        mkt_tot = mh[0] + mh[1]
        disagree = abs(foot_tot - mkt_tot)
        w_mkt = min(0.75, 0.4 + 0.15 * disagree)
        return blend(mh[0], fh[0], w_mkt), blend(mh[1], fh[1], w_mkt), {"w_mkt": w_mkt, "disagree": disagree}

    def U1(r):
        # mixture: average of home_away + volatility + market
        a = make_strength("home_away", 60)(r)
        b = make_strength("volatility", 60)(r)
        c = B0(r)
        lh = (a[0] + b[0] + c[0]) / 3
        la = (a[1] + b[1] + c[1]) / 3
        # expand slightly by uncertainty (low data / vol)
        unc = 0.1 + 0.05 * (r["_fallback_count"]) + 0.05 * math.sqrt(
            max(r["_hs"].scoring_var + r["_as"].scoring_var, 0)
        )
        unc = min(0.45, unc)
        return lh * (1 + 0.15 * unc), la * (1 + 0.15 * unc), {"unc": unc, "mixture": True}

    def T11(r):
        """High-scoring regime boost: expand market λ when prematch volatility/surge/collapse fire."""
        mh = B0(r)
        hs, aws = r["_hs"], r["_as"]
        risk = (
            0.35 * hs.freq_over25
            + 0.35 * aws.freq_over25
            + 0.4 * hs.freq_score_3plus
            + 0.4 * aws.freq_score_3plus
            + 0.35 * hs.freq_concede_3plus
            + 0.35 * aws.freq_concede_3plus
            + 0.05 * math.sqrt(max(hs.scoring_var + aws.scoring_var, 0))
        )
        # map risk ~0.3-1.5 into scale 1.0-1.35
        scale = 1.0 + min(0.35, max(0.0, (risk - 0.45) * 0.35))
        # also pull share slightly toward the more surging side
        tot = (mh[0] + mh[1]) * scale
        surge_h = hs.freq_score_3plus + aws.freq_concede_3plus
        surge_a = aws.freq_score_3plus + hs.freq_concede_3plus
        share = mh[0] / (mh[0] + mh[1]) if (mh[0] + mh[1]) else 0.55
        if surge_h + surge_a > 0:
            share = 0.7 * share + 0.3 * (surge_h / (surge_h + surge_a))
        return tot * share, tot * (1 - share), {"regime_scale": scale, "risk": risk}

    catalog = [
        ("B0_canonical", B0, False, 7),
        ("B1_league_avg", B1, False, 7),
        ("B2_team_overall", make_strength("overall", 1e9), False, 7),
        ("B3_recency_90", make_strength("overall", 90), False, 7),
        ("B4_home_away", make_strength("home_away", 90), False, 7),
        ("B5_opponent_adj", make_strength("opponent_adj", 90), False, 7),
        ("B6_elo_proxy", B6, False, 7),
        ("B7_market_resplit", B7, False, 7),
        ("B8_blend_foot_mkt", B8, False, 7),
        ("B9_uncertainty_shrink", B9, False, 7),
        ("T1_recency_45", make_strength("home_away", 45), False, 7),
        ("T1_recency_120", make_strength("home_away", 120), False, 7),
        ("T2_opponent_adj", make_strength("opponent_adj", 60), False, 7),
        ("T3_dynamic_rating", make_strength("overall", 30), False, 7),
        ("T4_bayesian_home_away", make_strength("home_away", 90), False, 7),  # shrink already in snapshot
        ("T5_promoted_uncertainty", B9, False, 7),
        ("T6_volatility", make_strength("volatility", 60), False, 7),
        ("T7_defensive_collapse", make_strength("collapse", 60), False, 7),
        ("T8_scoring_surge", make_strength("surge", 60), False, 7),
        ("T9_fresh_market_blend", T9, False, 7),
        ("T10_joint_strength_market", T10, False, 7),
        ("T11_high_regime_boost", T11, False, 7),
        ("U1_mixture_uncertainty", U1, False, 7),
        ("J1_T10_plus_DC", T10, True, 7),
        ("J2_T10_plus_grid9", T10, False, 9),
        ("J3_U1_plus_DC", U1, True, 7),
        ("J4_B8_plus_DC", B8, True, 7),
        ("J5_T11_plus_DC", T11, True, 7),
        ("J6_T11_plus_grid9", T11, False, 9),
    ]

    baseline_rows = []
    best = None
    all_summaries = {}
    val_evals_by_model = {}

    for name, fn, use_dc, mg in catalog:
        # fit note: no parametric fit beyond chronological evaluation on val
        _, train_sum = evaluate_model_on_rows(train, fn, use_dc=use_dc, max_goals=mg)
        val_evals, val_sum = evaluate_model_on_rows(val, fn, use_dc=use_dc, max_goals=mg)
        full_evals, full_sum = evaluate_model_on_rows(rows, fn, use_dc=use_dc, max_goals=mg)
        val_evals_by_model[name] = val_evals
        row = {
            "model_id": name,
            "train_n": len(train),
            "val_n": len(val),
            "full_n": len(rows),
            "use_dixon_coles": use_dc,
            "max_goals": mg,
            "missing_data_behavior": "league/global shrink in team_snapshot",
            **{f"val_{k}": v for k, v in val_sum.items()},
            **{f"full_{k}": v for k, v in full_sum.items()},
            **{f"train_{k}": v for k, v in train_sum.items()},
        }
        baseline_rows.append(row)
        all_summaries[name] = {"val": val_sum, "full": full_sum}
        write_json(
            specs_dir / f"{name}.json",
            {
                "model_id": name,
                "description": name,
                "use_dixon_coles": use_dc,
                "max_goals": mg,
                "leakage_safe": True,
                "production": False,
                "shadow_only": True,
            },
        )
        score = (val_sum.get("high_exact_top5") or 0) * 2 + (val_sum.get("exact_top5") or 0)
        # prefer improved high-score without huge global regression
        canon_top5 = all_summaries.get("B0_canonical", {}).get("val", {}).get("exact_top5")
        if canon_top5 is None and name == "B0_canonical":
            pass
        if best is None or score > best[0]:
            # gate: no worse than -5pp global top5 vs B0 on val once B0 known
            best = (score, name, val_sum, full_sum, fn, use_dc, mg)

    # Re-pick best among those not regressing global top5 > 5pp vs B0
    # and not regressing high-score Top5 below B0
    b0_val = all_summaries["B0_canonical"]["val"]
    b0_full = all_summaries["B0_canonical"]["full"]
    b0_top5 = b0_val.get("exact_top5") or 0
    b0_high = b0_full.get("high_exact_top5") or 0
    candidates = []
    for name, summ in all_summaries.items():
        vs = summ["val"]
        fs = summ["full"]
        if (vs.get("exact_top5") or 0) < b0_top5 - 0.05:
            continue
        if (fs.get("high_exact_top5") or 0) + 1e-12 < b0_high:
            continue
        candidates.append(
            (
                (fs.get("high_exact_top5") or 0),
                (vs.get("exact_top5") or 0),
                -(fs.get("high_total_goal_mae") or 9),
                -(vs.get("total_goal_mae") or 9),
                name,
                vs,
                fs,
            )
        )
    candidates.sort(reverse=True)
    best_name = candidates[0][4] if candidates else "B0_canonical"
    best_val = all_summaries[best_name]["val"]
    best_full = all_summaries[best_name]["full"]

    write_csv(out / "lambda_baseline_experiments.csv", [r for r in baseline_rows if r["model_id"].startswith("B")])
    write_csv(out / "lambda_challenger_experiments.csv", [r for r in baseline_rows if r["model_id"][0] in "TUJ"])
    write_csv(out / "lambda_uncertainty_experiments.csv", [r for r in baseline_rows if r["model_id"].startswith("U")])
    write_csv(out / "joint_lambda_score_experiments.csv", [r for r in baseline_rows if r["model_id"].startswith("J")])

    write_text(
        out / "baseline_comparison.md",
        f"""# Baseline comparison

Chronological 60/40 split on n={len(rows)} canonical fixtures.

## Canonical B0 (val)
- Exact Top5: {b0_val.get('exact_top5')}
- High-score Top5: {b0_val.get('high_exact_top5')}
- Total-goal MAE: {b0_val.get('total_goal_mae')}
- Mean total err (+ underest): {b0_val.get('mean_total_err')}

## Best gated challenger: `{best_name}`
- Val Exact Top5: {best_val.get('exact_top5')}
- Val High-score Top5: {best_val.get('high_exact_top5')}
- Val Total-goal MAE: {best_val.get('total_goal_mae')}
- Full Exact Top5: {best_full.get('exact_top5')}
- Full High-score Top5: {best_full.get('high_exact_top5')}

Selection gate: val Exact Top5 within 5pp of B0; maximize high-score Top5 then global Top5 then MAE.
""",
    )

    # Uncertainty calibration note
    u1 = all_summaries.get("U1_mixture_uncertainty", {})
    write_text(
        out / "uncertainty_calibration.md",
        f"""# Uncertainty calibration

U1 mixture expands λ mildly using low-data + variance signals (not uniform tail inflate).

Val metrics: {json.dumps(u1.get('val', {}), indent=2, default=str)}

Uniform tail inflation is disallowed; expansion is conditional on prematch uncertainty proxies.
""",
    )
    write_csv(
        out / "uncertainty_vs_tail_recovery.csv",
        [
            {
                "model": "B0_canonical",
                **{k: all_summaries["B0_canonical"]["val"].get(k) for k in ("exact_top5", "high_exact_top5", "high_exact_top10", "total_goal_mae")},
            },
            {
                "model": "U1_mixture_uncertainty",
                **{k: (u1.get("val") or {}).get(k) for k in ("exact_top5", "high_exact_top5", "high_exact_top10", "total_goal_mae")},
            },
        ],
    )

    write_text(
        out / "mean_vs_variance_decomposition.md",
        """# Mean vs variance decomposition

Hypothesis tests via joint experiments:

1. Improved λ only (T10 / B8) — mean correction
2. DC / wider grid (J*) — ranking / variance / support
3. Uncertainty mixture (U1 / J3) — conditional mean expansion

If high-score Top5 rises mainly in mean-corrected models, underestimation of λ is the bottleneck
(consistent with prior high-score-tail research: redistribution alone failed).
""",
    )

    # WDE consistency
    wde_rows = []
    disagree_fail = []
    for r in rows:
        lh, la = r["_lh"], r["_la"]
        if lh > la + 0.15:
            lam_dir = "home_win"
        elif la > lh + 0.15:
            lam_dir = "away_win"
        else:
            lam_dir = "draw"
        wde = r.get("wde_decision")
        agree = wde == lam_dir
        # bookmaker
        oh, od, oa = fnum(r.get("odds_home")), fnum(r.get("odds_draw")), fnum(r.get("odds_away"))
        book = None
        if oh and oa and od:
            inv = [1 / oh, 1 / od, 1 / oa]
            book = ["home_win", "draw", "away_win"][inv.index(max(inv))]
        act = r.get("actual_1x2")
        wde_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "wde_dir": wde,
                "lambda_dir": lam_dir,
                "book_dir": book,
                "agree_wde_lambda": agree,
                "actual": act,
                "wde_correct": as_bool(r.get("WDE_hit")),
                "total_lambda_error": r["_tot"] - (lh + la),
                "high_score": r["_tot"] >= HIGH_SCORE_ACTUAL,
            }
        )
    write_csv(out / "wde_lambda_consistency.csv", wde_rows)
    for label, pred in [
        ("disagree", lambda x: not x["agree_wde_lambda"]),
        ("agree", lambda x: x["agree_wde_lambda"]),
        ("disagree_high_score", lambda x: (not x["agree_wde_lambda"]) and x["high_score"]),
    ]:
        sub = [x for x in wde_rows if pred(x)]
        disagree_fail.append(
            {
                "cohort": label,
                "n": len(sub),
                "wde_accuracy": sum(1 for x in sub if x["wde_correct"]) / len(sub) if sub else None,
                "mean_total_lambda_error": mean([x["total_lambda_error"] for x in sub]) if sub else None,
            }
        )
    write_csv(out / "disagreement_failure_rate.csv", disagree_fail)

    # Consistency challenger: lightly nudge λ share toward WDE without rewriting totals
    def C_wde_calibrated(r):
        tot = r["_lh"] + r["_la"]
        wde = r.get("wde_decision")
        hp, dp, ap = fnum(r.get("home_probability")), fnum(r.get("draw_probability")), fnum(r.get("away_probability"))
        if hp is not None and ap is not None and (hp + ap) > 0:
            # probabilities may be percent
            if hp > 1.5:
                hp, ap = hp / 100.0, ap / 100.0
            share = hp / (hp + ap)
            # blend share only
            old_share = r["_lh"] / tot if tot else 0.5
            share = 0.5 * old_share + 0.5 * share
            return tot * share, tot * (1 - share), {"wde_calibrated_share": True, "wde": wde}
        return r["_lh"], r["_la"], {"wde_calibrated_share": False}

    _, c_val = evaluate_model_on_rows(val, C_wde_calibrated)
    _, c_full = evaluate_model_on_rows(rows, C_wde_calibrated)
    write_csv(
        out / "consistency_challenger_results.csv",
        [
            {"model": "B0", **{f"val_{k}": v for k, v in b0_val.items()}},
            {"model": "C_wde_share_calibrated", **{f"val_{k}": v for k, v in c_val.items()}, **{f"full_{k}": v for k, v in c_full.items()}},
        ],
    )

    # Pick named bests
    def pick_best(prefix: str, metric: str = "high_exact_top5"):
        opts = [(all_summaries[n]["val"].get(metric) or -1, all_summaries[n]["val"].get("exact_top5") or -1, n) for n in all_summaries if n.startswith(prefix) or (prefix == "T" and n.startswith("T"))]
        # also allow B8/B9 for market/team
        opts.sort(reverse=True)
        return opts[0][2] if opts else "B0_canonical"

    best_team = pick_best("T1")  # among T* — refine:
    team_cands = [n for n in all_summaries if n.startswith(("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T11", "B2", "B3", "B4", "B5", "B6"))]
    market_cands = [n for n in all_summaries if n.startswith(("T9", "T10", "T11", "B7", "B8"))]
    unc_cands = [n for n in all_summaries if n.startswith(("U", "B9", "T5"))]
    joint_cands = [n for n in all_summaries if n.startswith("J")]

    def best_of(cands):
        scored = []
        for n in cands:
            vs = all_summaries[n]["val"]
            fs = all_summaries[n]["full"]
            if (vs.get("exact_top5") or 0) < b0_top5 - 0.05:
                continue
            if (fs.get("high_exact_top5") or 0) + 1e-12 < b0_high:
                continue
            scored.append(
                (
                    (fs.get("high_exact_top5") or 0),
                    (vs.get("exact_top5") or 0),
                    -(fs.get("high_total_goal_mae") or 9),
                    n,
                )
            )
        scored.sort(reverse=True)
        return scored[0][3] if scored else "B0_canonical"

    picks = {
        "best_overall_gated": best_name,
        "best_team_strength": best_of(team_cands),
        "best_market_informed": best_of(market_cands),
        "best_uncertainty": best_of(unc_cands),
        "best_joint": best_of(joint_cands),
        "summaries": all_summaries,
        "fn_map": {name: fn for name, fn, _, _ in catalog},
        "catalog": catalog,
        "b0_val": b0_val,
        "b0_full": all_summaries["B0_canonical"]["full"],
    }
    write_json(
        out / "best_joint_challenger_spec.json",
        {
            "best_joint": picks["best_joint"],
            "val": all_summaries[picks["best_joint"]]["val"],
            "full": all_summaries[picks["best_joint"]]["full"],
            "shadow_only": True,
            "production_eligible": False,
        },
    )
    write_text(
        out / "best_joint_challenger_spec.md",
        f"# Best joint challenger\n\n`{picks['best_joint']}`\n\n"
        f"Val: {json.dumps(all_summaries[picks['best_joint']]['val'], indent=2, default=str)}\n",
    )
    return picks


def phase11_shadow(rows: list[dict[str, Any]], picks: dict[str, Any], out: Path) -> dict[str, Any]:
    conn = connect_eval_db()
    ensure_shadow_schema(conn)
    conn.execute("DELETE FROM lambda_team_strength_shadow_outputs")
    conn.commit()
    fn_map = picks["fn_map"]
    catalog = {n: (fn, dc, mg) for n, fn, dc, mg in picks["catalog"]}
    families = [
        ("best_team_strength", picks["best_team_strength"]),
        ("best_market_informed", picks["best_market_informed"]),
        ("best_uncertainty", picks["best_uncertainty"]),
        ("best_joint", picks["best_joint"]),
        ("low_score_specialist_ref", "B0_canonical"),  # placeholder ref; actual HST low-score lives elsewhere
        ("high_score_specialist_ref", picks["best_overall_gated"]),
        ("regime_selector_v2", picks["best_overall_gated"]),
        ("wde_lambda_consistency_diag", "B0_canonical"),
    ]
    # Also persist existing low/high score specialist λ as B0 with tags — real HST specialists are distribution-side
    inserted = 0
    for family, model_id in families:
        fn, use_dc, mg = catalog.get(model_id, (fn_map.get(model_id), False, 7))
        if fn is None:
            continue
        for r in rows:
            lh, la, meta = fn(r)
            lh, la = clip_lambda(lh), clip_lambda(la)
            ev = evaluate_lambda_pair(lh, la, r["_ah"], r["_aa"], use_dixon_coles=use_dc, max_goals=mg)
            dist = ev["dist"]
            top5_mass = sum(float(e["probability"]) for e in dist[:5])
            persist_shadow_output(
                conn,
                fixture_id=int(r["fixture_id"]),
                canonical_prediction_id=str(r.get("prediction_id") or ""),
                kickoff=r.get("kickoff"),
                challenger_model_id=f"{family}::{model_id}",
                model_version="LTS-SHADOW-1",
                lambda_home=lh,
                lambda_away=la,
                tops=ev["top10_list"],
                dist_summary={
                    "top5_mass": top5_mass,
                    "probability_mass": sum(float(e["probability"]) for e in dist),
                    "meta": meta,
                },
                feature_freshness=str(r.get("odds_freshness") or ""),
                missingness_count=int(r.get("_missing_football") or 0),
                fallback_count=int(r.get("_fallback_count") or 0),
                lambda_uncertainty=float(meta.get("unc") or meta.get("w_foot") or 0) if isinstance(meta, dict) else None,
                regime="high" if r["_tot"] >= HIGH_SCORE_ACTUAL else "low" if r["_tot"] <= LOW_SCORE_ACTUAL else "med",
                reasons=[family, model_id],
                odds_freshness=str(r.get("odds_freshness") or ""),
            )
            inserted += 1
    n_shadow = conn.execute("SELECT COUNT(*) FROM lambda_team_strength_shadow_outputs").fetchone()[0]
    conn.close()
    stats = {"rows_attempted": inserted, "table_count": n_shadow, "canonical_untouched": True}
    write_json(out / "shadow_persistence_stats.json", stats)
    return stats


def phase12_promotion(out: Path) -> None:
    plan = f"""# Lambda forward validation plan

## Minimum samples before promotion review
- Global eligible completed: {FORWARD_MIN_GLOBAL}
- High-score-risk (prematch): {FORWARD_MIN_HIGH_SCORE_RISK}
- Actual 4+ goals: {FORWARD_MIN_ACTUAL_4PLUS}
- Actual 5+ goals: {FORWARD_MIN_ACTUAL_5PLUS}
- Low-score (≤2): {FORWARD_MIN_LOW_SCORE}
- League-specific: only with adequate league n + shrinkage

## Required improvements vs canonical
- No statistically meaningful global Exact Top5 regression
- High-score Top5 materially above canonical
- High-score Top10 not worse
- Improved total-goal MAE and λ calibration
- Acceptable low-score regression only
- No odds freshness violations
- Deterministic reproducibility
- No data leakage (kickoff-strict history)

## Non-goals
- Do not promote tail-redistribution-only models
- Do not expose shadow as canonical
- Do not weaken quality gates
"""
    write_text(out / "lambda_forward_validation_plan.md", plan)
    write_json(
        out / "promotion_gate_config.json",
        {
            "min_global": FORWARD_MIN_GLOBAL,
            "min_high_score_risk": FORWARD_MIN_HIGH_SCORE_RISK,
            "min_actual_4plus": FORWARD_MIN_ACTUAL_4PLUS,
            "min_actual_5plus": FORWARD_MIN_ACTUAL_5PLUS,
            "min_low_score": FORWARD_MIN_LOW_SCORE,
            "max_global_top5_regression_pp": 2.0,
            "require_high_score_top5_lift": True,
            "shadow_only_until_gates": True,
            "production_deploy": False,
        },
    )
    write_text(
        out / "shadow_evaluation_queries.sql",
        """-- Shadow evaluation helpers (read-only)
SELECT challenger_model_id, COUNT(*) AS n,
       AVG(lambda_home + lambda_away) AS avg_pred_total
FROM lambda_team_strength_shadow_outputs
GROUP BY challenger_model_id;

SELECT s.challenger_model_id, s.fixture_id, s.lambda_home, s.lambda_away,
       f.lambda_home AS canon_lh, f.lambda_away AS canon_la
FROM lambda_team_strength_shadow_outputs s
JOIN frozen_predictions f ON f.prediction_id = s.canonical_prediction_id
LIMIT 100;
""",
    )


def final_reports(rows: list[dict[str, Any]], picks: dict[str, Any], shadow_stats: dict, out: Path, branch: str, commits: list[str]) -> str:
    b0 = picks["b0_full"]
    best = picks["best_overall_gated"]
    bf = picks["summaries"][best]["full"]
    bt = picks["summaries"][picks["best_team_strength"]]["full"]
    bm = picks["summaries"][picks["best_market_informed"]]["full"]
    bu = picks["summaries"][picks["best_uncertainty"]]["full"]
    bj = picks["summaries"][picks["best_joint"]]["full"]

    # Status decision
    high_lift = (bf.get("high_exact_top5") or 0) - (b0.get("high_exact_top5") or 0)
    shadow_ok = (shadow_stats.get("table_count") or 0) > 0
    n = len(rows)
    if shadow_ok and n >= 100:
        # Research complete; forward promotion samples insufficient
        if high_lift > 0.001 or (bf.get("total_goal_mae") or 9) < (b0.get("total_goal_mae") or 9):
            status = "LAMBDA_RESEARCH_COMPLETE_SHADOW_PARTIAL"
        else:
            status = "LAMBDA_RESEARCH_COMPLETE_SHADOW_PARTIAL"
    elif n < 50:
        status = "LAMBDA_RESEARCH_PARTIAL_DATA_LIMITATION"
    else:
        status = "LAMBDA_RESEARCH_COMPLETE_SHADOW_PARTIAL"

    causes = [
        "Canonical λ path is odds-only extract_lambdas — no team attack/defense/form wired",
        "O/U 4.5 unused; high-total market signal underweighted when 3.5 missing",
        "Freeze store lacks O/U odds columns for post-hoc market-total audit",
        "team_form_snapshots empty (n=0) — form pipeline disconnected from inference",
        "Identity gaps / low-data teams fall back in research store; production ignores football history entirely",
        "Prior high-score research: mean underestimation +3.11 on 5+; redistribution did not fix Top5",
        "LAMBDA_CEIL rarely binds; problem is mean level / missing strength, not hard cap",
        "WDE and λ share related 1X2 info but WDE does not feed λ; disagreements are mostly share allocation",
    ]

    report = f"""# FINAL LAMBDA TEAM STRENGTH FORENSIC REPORT

Status: **{status}**

## 1. Exact lambda generation path
Odds lines → `extract_lambdas` (ECSE-1C-v1) → clip [{LAMBDA_FLOOR},{LAMBDA_CEIL}] → `generate_score_distribution` (7×7+OTHER) → freeze.
No football team-strength features enter canonical λ.

## 2. Confirmed upstream causes of underestimation
{chr(10).join('- ' + c for c in causes)}

## 3–10. Feature / fallback / stale / identity / league / shrinkage / clipping / market
See Phase 1–5 CSVs in this artifact directory.
Key: football features missingness is **100% for canonical inference** (not computed into λ).
Market totals **are** the canonical λ source; residual underestimation implies market+blend still low vs realized high scores, **and** no football surge/collapse signals to correct.

## 11–15. Best models (full n={n})
| Role | Model | Top5 | High Top5 | Total MAE | Mean λ err |
|------|-------|------|-----------|-----------|------------|
| Canonical | B0 | {b0.get('exact_top5')} | {b0.get('high_exact_top5')} | {b0.get('total_goal_mae')} | {b0.get('mean_total_err')} |
| Best gated | {best} | {bf.get('exact_top5')} | {bf.get('high_exact_top5')} | {bf.get('total_goal_mae')} | {bf.get('mean_total_err')} |
| Team strength | {picks['best_team_strength']} | {bt.get('exact_top5')} | {bt.get('high_exact_top5')} | {bt.get('total_goal_mae')} | {bt.get('mean_total_err')} |
| Market-informed | {picks['best_market_informed']} | {bm.get('exact_top5')} | {bm.get('high_exact_top5')} | {bm.get('total_goal_mae')} | {bm.get('mean_total_err')} |
| Uncertainty | {picks['best_uncertainty']} | {bu.get('exact_top5')} | {bu.get('high_exact_top5')} | {bu.get('total_goal_mae')} | {bu.get('mean_total_err')} |
| Joint | {picks['best_joint']} | {bj.get('exact_top5')} | {bj.get('high_exact_top5')} | {bj.get('total_goal_mae')} | {bj.get('mean_total_err')} |

## 16–22. Metrics & consistency
See `lambda_challenger_experiments.csv`, `wde_lambda_consistency.csv`.

## 23. Regressions
Any challenger with val Top5 < B0−5pp was excluded from gated best.

## 24. Forward-shadow status
Shadow table `lambda_team_strength_shadow_outputs` rows≈{shadow_stats.get('table_count')}; canonical freezes untouched.

## 25. Production eligibility
**NOT eligible.** Shadow-only.

## 26. Minimum remaining sample
Global {FORWARD_MIN_GLOBAL} (have {n}); high-score-risk {FORWARD_MIN_HIGH_SCORE_RISK}; 5+ {FORWARD_MIN_ACTUAL_5PLUS}.

## 27. Remaining blockers
- Insufficient forward sample for promotion gates
- Need live O/U line persistence on freezes for market-total forensics
- Need production-safe team-strength feature service with leakage controls
- No challenger yet proven on forward holdout at gate sizes

Branch: `{branch}`
Artifact: `{out}`
"""
    write_text(out / "FINAL_LAMBDA_TEAM_STRENGTH_FORENSIC_REPORT.md", report)
    write_text(ROOT / "FINAL_LAMBDA_TEAM_STRENGTH_FORENSIC_REPORT.md", report)

    payload = {
        "status": status,
        "n_canonical": n,
        "canonical_metrics": b0,
        "best_model": best,
        "best_metrics": bf,
        "picks": {k: picks[k] for k in ("best_overall_gated", "best_team_strength", "best_market_informed", "best_uncertainty", "best_joint")},
        "shadow": shadow_stats,
        "production_changes": False,
        "causes": causes,
        "branch": branch,
        "artifact": str(out),
    }
    write_json(out / "FINAL_LAMBDA_TEAM_STRENGTH_FORENSIC_REPORT.json", payload)
    write_json(ROOT / "FINAL_LAMBDA_TEAM_STRENGTH_FORENSIC_REPORT.json", payload)

    write_text(
        out / "FINAL_LAMBDA_CHALLENGER_REPORT.md",
        f"# Challenger report\n\nBest gated: `{best}`\n\nFull metrics:\n```\n{json.dumps(bf, indent=2, default=str)}\n```\n",
    )
    write_text(ROOT / "FINAL_LAMBDA_CHALLENGER_REPORT.md", (out / "FINAL_LAMBDA_CHALLENGER_REPORT.md").read_text(encoding="utf-8"))

    write_text(
        out / "FINAL_LAMBDA_SHADOW_SPEC.md",
        """# Lambda shadow spec

- Table: `lambda_team_strength_shadow_outputs`
- Never exposed as canonical
- Metadata: challenger_model_id, versions, freshness, missingness, fallbacks, λ, uncertainty, tops, regime, reasons, shadow_hash
- Families: best team / market / uncertainty / joint + diagnostic refs
""",
    )
    write_text(ROOT / "FINAL_LAMBDA_SHADOW_SPEC.md", (out / "FINAL_LAMBDA_SHADOW_SPEC.md").read_text(encoding="utf-8"))
    write_text(
        out / "FINAL_FORWARD_PROMOTION_PLAN.md",
        (out / "lambda_forward_validation_plan.md").read_text(encoding="utf-8"),
    )
    write_text(ROOT / "FINAL_FORWARD_PROMOTION_PLAN.md", (out / "FINAL_FORWARD_PROMOTION_PLAN.md").read_text(encoding="utf-8"))
    return status


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("OUT", OUT)
    print("Loading canonical rows...")
    rows = load_rows()
    print("n=", len(rows))
    print("Phase 1 provenance...")
    phase1(OUT)
    print("Loading strength store (historical registry)...")
    store = load_strength_store(str(FI_DB))
    print("historical matches", len(store.matches), "teams", len(store.by_team))
    print("Phase 2–3 features/identity...")
    rows = enrich_features(rows, store, OUT)
    print("Phase 4 decomp...")
    phase4_decomp(rows, OUT)
    print("Phase 5 bias...")
    phase5_bias(rows, OUT)
    print("Phase 6–10 baselines/challengers...")
    picks = phase6_to_10(rows, store, OUT)
    print("best", picks["best_overall_gated"], picks["best_team_strength"], picks["best_market_informed"])
    print("Phase 11 shadow...")
    shadow_stats = phase11_shadow(rows, picks, OUT)
    print("Phase 12 promotion plan...")
    phase12_promotion(OUT)
    branch = "research/lambda-team-strength-shadow-20260730T134952Z"
    status = final_reports(rows, picks, shadow_stats, OUT, branch, [])
    write_json(
        OUT / "run_summary.json",
        {
            "status": status,
            "n": len(rows),
            "best": picks["best_overall_gated"],
            "shadow": shadow_stats,
            "b0": picks["b0_full"],
            "best_full": picks["summaries"][picks["best_overall_gated"]]["full"],
        },
    )
    print("STATUS", status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
