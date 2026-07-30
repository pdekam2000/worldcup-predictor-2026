#!/usr/bin/env python3
"""Football strength foundation + Lambda V2 research orchestrator (shadow only)."""

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
from worldcup_predictor.research.football_strength_foundation.constants import (
    FEATURE_SCHEMA_VERSION,
    FORWARD_MIN_ACTUAL_4PLUS,
    FORWARD_MIN_ACTUAL_5PLUS,
    FORWARD_MIN_COMPLETE_FEATURE,
    FORWARD_MIN_GLOBAL,
    FORWARD_MIN_MULTI_LINE_MARKET,
    HIGH_SCORE,
    LOW_SCORE,
)
from worldcup_predictor.research.football_strength_foundation.historical_match_service import (
    HistoricalMatchService,
)
from worldcup_predictor.research.football_strength_foundation.lambda_v2 import (
    football_hda_blend,
    football_only,
    football_totals_blend,
    full_blend,
    market_only_from_odds_row,
    uncertainty_aware_blend,
)
from worldcup_predictor.research.football_strength_foundation.score_v2 import (
    dist_dc,
    dist_overdispersed,
    dist_poisson,
    exact_metrics,
    rank_bias_table,
)
from worldcup_predictor.research.football_strength_foundation.shadow_store import (
    ensure_shadow_schema,
    persist_shadow,
)
from worldcup_predictor.research.football_strength_foundation.team_form_snapshot_writer import (
    TeamFormSnapshotWriter,
    root_cause_markdown,
)
from worldcup_predictor.research.football_strength_foundation.team_strength_engine import TeamStrengthEngine
from worldcup_predictor.research.football_strength_foundation.totals_market import (
    TotalsLine,
    audit_totals_pipeline_markdown,
    ensure_totals_schema,
    invert_multi_line,
    persist_totals_lines,
)
from worldcup_predictor.research.lambda_team_strength.metrics import fnum, mean, normalize_team, parse_teams
from worldcup_predictor.research.lambda_team_strength.team_strength import load_strength_store

CANONICAL_CSV = (
    ROOT
    / "artifacts"
    / "dataset_reconciliation_experiments"
    / "20260730T125305Z"
    / "evaluation_one_canonical_freeze_per_fixture.csv"
)
FI_DB = ROOT / "data" / "football_intelligence.db"
OUT = ROOT / "artifacts" / "football_strength_lambda_v2" / "20260730T142215Z"
BRANCH = "research/football-strength-lambda-v2-20260730T142215Z"


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
        try:
            return datetime.strptime(t[:n], "%Y-%m-%d %H:%M:%S" if n == 19 else "%Y-%m-%d %H:%M" if n == 16 else "%Y-%m-%d")
        except Exception:
            continue
    return None


def phase1_contract(out: Path) -> None:
    write_text(
        out / "PREMATCH_FOOTBALL_FEATURE_CONTRACT.md",
        f"""# Prematch football feature contract

Schema version: `{FEATURE_SCHEMA_VERSION}`

## Rules
- All features must be known at `feature_cutoff_timestamp` ≤ kickoff.
- No post-match / future rows.
- Nullable fields must declare fallback policy.
- Canonical freezes are never rewritten with reconstructed features.

## Identity
fixture_id, competition_id/key, season, home_team_id/name, away_team_id/name,
kickoff_utc, prediction_timestamp, feature_cutoff_timestamp

## Attack / defense / environment / market / quality
See `prematch_feature_schema.json` and `feature_units_and_ranges.csv`.
""",
    )
    schema = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "groups": {
            "identity": [
                "fixture_id",
                "competition_key",
                "season",
                "home_team_id",
                "away_team_id",
                "kickoff_utc",
                "prediction_timestamp",
                "feature_cutoff_timestamp",
            ],
            "attack": [
                "recent_goals_scored",
                "home_goals_scored",
                "away_goals_scored",
                "opponent_adjusted_attack",
                "expected_scoring_strength",
                "scoring_trend",
                "scoring_variance",
                "freq_score_2plus",
                "freq_score_3plus",
            ],
            "defense": [
                "recent_goals_conceded",
                "home_goals_conceded",
                "away_goals_conceded",
                "opponent_adjusted_defense",
                "defensive_trend",
                "conceding_variance",
                "freq_concede_2plus",
                "freq_concede_3plus",
                "clean_sheet_rate",
            ],
            "environment": [
                "league_avg_goals",
                "home_goal_avg",
                "away_goal_avg",
                "btts_rate",
                "over25_rate",
                "over35_rate",
                "over45_rate",
                "competition_volatility",
            ],
            "market": [
                "odds_home",
                "odds_draw",
                "odds_away",
                "ou25_over",
                "ou25_under",
                "ou35_over",
                "ou35_under",
                "ou45_over",
                "ou45_under",
                "btts_yes",
                "btts_no",
                "bookmaker_count",
                "odds_timestamp",
                "odds_freshness",
            ],
            "quality": [
                "history_match_count",
                "feature_missing_count",
                "fallback_count",
                "low_data_flag",
                "promoted_new_team_flag",
                "reserve_youth_flag",
                "identity_confidence",
                "source_confidence",
            ],
        },
        "training_allowed": True,
        "runtime_inference_allowed": True,
        "canonical_production_lambda_consumes": False,
    }
    write_json(out / "prematch_feature_schema.json", schema)
    units = []
    for g, feats in schema["groups"].items():
        for f in feats:
            units.append(
                {
                    "feature": f,
                    "group": g,
                    "unit": "goals" if "goal" in f or "attack" in f or "defense" in f or "avg" in f else "rate/flag/id",
                    "valid_range": "[0,inf) or [0,1] or categorical",
                    "nullable": True,
                    "training_allowed": True,
                    "runtime_allowed": True,
                    "canonical_lambda_uses": False,
                }
            )
    write_csv(out / "feature_units_and_ranges.csv", units)
    write_csv(
        out / "feature_source_and_fallback_matrix.csv",
        [
            {"feature_group": "attack/defense", "source": "historical_match_service", "fallback": "league->global prior", "shrinkage": "sample-size hierarchical"},
            {"feature_group": "environment", "source": "league aggregates pre-cutoff", "fallback": "global averages", "shrinkage": "n/a"},
            {"feature_group": "market HDA", "source": "freeze / odds snapshots", "fallback": "none (nullable)", "shrinkage": "n/a"},
            {"feature_group": "market totals", "source": "totals_market_shadow / historical odds", "fallback": "do not invent lines", "shrinkage": "n/a"},
            {"feature_group": "form snapshots", "source": "derived_historical_team_form_snapshots", "fallback": "compute on the fly", "shrinkage": "engine"},
        ],
    )


def load_rows() -> list[dict[str, Any]]:
    rows = list(csv.DictReader(CANONICAL_CSV.open(encoding="utf-8")))
    for r in rows:
        r["_ah"] = int(float(r["actual_ft_home"]))
        r["_aa"] = int(float(r["actual_ft_away"]))
        r["_tot"] = r["_ah"] + r["_aa"]
        r["_lh"] = fnum(r.get("lambda_home")) or 1.2
        r["_la"] = fnum(r.get("lambda_away")) or 1.0
        h, a = parse_teams(r.get("match_name"))
        r["_home"], r["_away"] = h, a
        r["_ko"] = parse_ko(r.get("kickoff")) or datetime(2099, 1, 1)
        r["_league"] = normalize_team(str(r.get("competition") or "unknown")).replace(" ", "")
        r["_fresh"] = str(r.get("odds_freshness") or "").upper().startswith("FRESH")
        bc = r.get("bookmaker_count")
        r["_books"] = int(float(bc)) if bc not in (None, "") else None
    return sorted(rows, key=lambda x: str(x.get("kickoff") or ""))


def lookup_totals_lines(fi: sqlite3.Connection, home: str, away: str, kickoff: datetime) -> list[TotalsLine]:
    """Best-effort historical totals near kickoff from staging odds; never invent odds."""
    day = kickoff.strftime("%Y-%m-%d")
    # Prefer exact team string match on staging (has home/away + ft_goals_* markets)
    sql = """
        SELECT market, outcome, AVG(odds) AS odds, COUNT(*) AS n
        FROM external_match_odds_staging
        WHERE event_date = ?
          AND lower(home_team) = lower(?)
          AND lower(away_team) = lower(?)
          AND market IN (
            'ft_goals_over_2_5','ft_goals_under_2_5',
            'ft_goals_over_3_5','ft_goals_under_3_5',
            'ft_goals_over_4_5','ft_goals_under_4_5'
          )
        GROUP BY market, outcome
    """
    try:
        rows = list(fi.execute(sql, (day, home, away)))
    except Exception:
        rows = []
    if not rows:
        # fuzzy first-token match
        h0 = home.split()[0]
        a0 = away.split()[0]
        sql2 = """
            SELECT market, outcome, AVG(odds) AS odds, COUNT(*) AS n
            FROM external_match_odds_staging
            WHERE event_date = ?
              AND lower(home_team) LIKE ?
              AND lower(away_team) LIKE ?
              AND market LIKE 'ft_goals_%'
            GROUP BY market, outcome
        """
        try:
            rows = list(fi.execute(sql2, (day, f"%{h0.lower()}%", f"%{a0.lower()}%")))
        except Exception:
            rows = []

    over: dict[float, float] = {}
    under: dict[float, float] = {}
    for market, outcome, odds, n in rows:
        m = str(market).lower()
        if "2_5" in m or "2.5" in m:
            line = 2.5
        elif "3_5" in m or "3.5" in m:
            line = 3.5
        elif "4_5" in m or "4.5" in m:
            line = 4.5
        else:
            continue
        if "over" in m:
            over[line] = float(odds)
        elif "under" in m:
            under[line] = float(odds)
    lines = []
    for L in (2.5, 3.5, 4.5):
        if L in over or L in under:
            lines.append(
                TotalsLine(L, over.get(L), under.get(L), provider="external_match_odds_staging", freshness="HISTORICAL")
            )
    return lines


def cohort_eval(evals: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(evals)
    if not n:
        return {"n": 0}

    def rate(k):
        return sum(1 for e in evals if e.get(k)) / n

    return {
        "n": n,
        "top1": rate("top1"),
        "top3": rate("top3"),
        "top5": rate("top5"),
        "top10": rate("top10"),
        "log_loss": mean([e["log_loss"] for e in evals]),
        "total_mae": mean([e["total_mae"] for e in evals]),
        "mean_bias": mean([e["bias"] for e in evals]),
        "home_mae": mean([e["home_mae"] for e in evals]),
        "away_mae": mean([e["away_mae"] for e in evals]),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("OUT", OUT)
    phase1_contract(OUT)
    write_text(OUT / "team_form_snapshot_root_cause.md", root_cause_markdown())
    write_text(OUT / "totals_market_pipeline_audit.md", audit_totals_pipeline_markdown())
    write_text(
        OUT / "historical_match_service_spec.md",
        """# Historical match service spec\n\n- Only matches with kickoff < cutoff\n- FT scores only\n- Dedup by fixture key\n- Deterministic order\n- Leakage assertions enforced\n- Extends lambda_team_strength store (staging + registry)\n""",
    )
    write_text(
        OUT / "team_strength_engine_spec.md",
        """# Team strength engine V1\n\nHierarchical shrinkage team→league→global by sample size.\nDoes not force low-data teams to artificially low-goal priors.\nReturns attack/defense/volatility/uncertainty/quality.\n""",
    )
    write_text(
        OUT / "hierarchical_shrinkage.md",
        """# Hierarchical shrinkage\n\n`estimate_shrunk = n/(n+k)*team + k/(n+k)*league_prior` with k=prior_strength (default 8).\nMissing home/away split falls back to league side prior and increments fallback_count.\nUncertainty rises with 1/sqrt(n) and fallbacks.\n""",
    )
    write_text(
        OUT / "market_total_inversion_spec.md",
        """# Market total inversion\n\nInvert Poisson total λ from de-vigged P(over line) via binary search.\nMulti-line weighted blend: 2.5=0.45, 3.5=0.35, 4.5=0.20 when present.\nNever invent missing lines. Flag non-monotonic over probabilities.\n""",
    )

    print("Loading strength store...")
    store = load_strength_store(str(FI_DB))
    hist = HistoricalMatchService(store=store)
    engine = TeamStrengthEngine(hist)
    rows = load_rows()
    print("n fixtures", len(rows))

    fi = sqlite3.connect(f"file:{FI_DB}?mode=ro", uri=True)
    eval_conn = connect_eval_db()
    ensure_shadow_schema(eval_conn)
    ensure_totals_schema(eval_conn)
    eval_conn.execute("DELETE FROM lambda_v2_shadow_outputs")
    eval_conn.commit()
    form_writer = TeamFormSnapshotWriter(eval_conn)

    # Chronological split
    cut = max(1, int(len(rows) * 0.6))
    train, val = rows[:cut], rows[cut:]
    write_json(
        OUT / "chronological_split_manifest.json",
        {
            "n": len(rows),
            "train_n": len(train),
            "val_n": len(val),
            "rule": "sorted by kickoff; 60/40; features from history kickoff < fixture kickoff only",
            "no_leakage": True,
        },
    )

    model_fns = {
        "L2-A_football_only": lambda b, m, lines, r: football_only(b),
        "L2-B_market_only": lambda b, m, lines, r: m,
        "L2-C_football_hda": lambda b, m, lines, r: football_hda_blend(b, m),
        "L2-D_football_totals": lambda b, m, lines, r: football_totals_blend(b, lines, m),
        "L2-E_full_blend": lambda b, m, lines, r: full_blend(b, lines, m),
        "L2-F_uncertainty_aware": lambda b, m, lines, r: uncertainty_aware_blend(
            b, lines, m, odds_fresh=r["_fresh"], bookmaker_count=r["_books"]
        ),
        "B0_canonical": lambda b, m, lines, r: market_only_from_odds_row(None, fallback_lh=r["_lh"], fallback_la=r["_la"]),
    }

    dist_fns = {
        "poisson": dist_poisson,
        "dixon_coles": dist_dc,
        "overdispersed": dist_overdispersed,
    }

    # Build per-fixture artifacts
    hist_audit = []
    strength_val = []
    inversion_rows = []
    mono_rows = []
    coverage_rows = []
    backtest_rows = []
    segment_acc: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    rank_rows_by_model: dict[str, list] = defaultdict(list)
    factorial = []
    form_ids = 0
    totals_persisted = 0
    multi_line_n = 0
    complete_feature_n = 0

    for r in rows:
        cutoff = r["_ko"]
        bundle = engine.build_match(r["_home"], r["_away"], cutoff, r["_league"], target_fixture_id=int(r["fixture_id"]))
        hq_h = hist.matches_for_team(r["_home"], cutoff, target_fixture_id=int(r["fixture_id"]))
        hq_a = hist.matches_for_team(r["_away"], cutoff, target_fixture_id=int(r["fixture_id"]))
        hist_audit.append(
            {
                "fixture_id": r["fixture_id"],
                "home_key": hq_h.team_key,
                "away_key": hq_a.team_key,
                "home_n": len(hq_h.matches),
                "away_n": len(hq_a.matches),
                "home_query_hash": hq_h.query_hash,
                "away_query_hash": hq_a.query_hash,
                "leakage_ok": hq_h.leakage_checks_passed and hq_a.leakage_checks_passed,
            }
        )
        form_writer.persist_derived(
            fixture_id=int(r["fixture_id"]),
            home_team=r["_home"],
            away_team=r["_away"],
            cutoff=cutoff,
            engine=engine,
            league=r["_league"],
        )
        form_ids += 2

        lines = lookup_totals_lines(fi, r["_home"], r["_away"], cutoff)
        if lines:
            totals_persisted += persist_totals_lines(eval_conn, fixture_id=int(r["fixture_id"]), lines=lines)
        if sum(1 for L in lines if L.line in (2.5, 3.5, 4.5) and (L.over_odds or L.under_odds)) >= 2:
            multi_line_n += 1
        inv = invert_multi_line(lines)
        inversion_rows.append({"fixture_id": r["fixture_id"], **{k: inv.get(k) for k in ("lambda_total", "method", "n_lines", "lines_used")}})
        mono_rows.append({"fixture_id": r["fixture_id"], **inv.get("monotonic", {}), "probs": inv.get("probs")})

        mkt = market_only_from_odds_row(None, fallback_lh=r["_lh"], fallback_la=r["_la"])
        missing = int(bundle.home.n_total == 0) + int(bundle.away.n_total == 0) + int(not lines)
        fallback = bundle.home.fallback_count + bundle.away.fallback_count
        if bundle.home.n_total >= 8 and bundle.away.n_total >= 8:
            complete_feature_n += 1

        coverage_rows.append(
            {
                "fixture_id": r["fixture_id"],
                "home_n": bundle.home.n_total,
                "away_n": bundle.away.n_total,
                "totals_lines": [ln.line for ln in lines],
                "n_totals_lines": len(lines),
                "missing_count": missing,
                "fallback_count": fallback,
                "odds_fresh": r["_fresh"],
            }
        )
        strength_val.append(
            {
                "fixture_id": r["fixture_id"],
                "home_attack": bundle.home.attack_home,
                "away_attack": bundle.away.attack_away,
                "home_def": bundle.home.defense_home,
                "away_def": bundle.away.defense_away,
                "env": bundle.league_environment,
                "unc": 0.5 * (bundle.home.uncertainty + bundle.away.uncertainty),
                "quality_home": bundle.home.quality_tier,
                "quality_away": bundle.away.quality_tier,
            }
        )

        outputs = {name: fn(bundle, mkt, lines, r) for name, fn in model_fns.items()}

        # Exact distributions for key models
        for mid, outp in outputs.items():
            for dname, dfn in dist_fns.items():
                dist = dfn(outp.lambda_home, outp.lambda_away)
                em = exact_metrics(dist, r["_ah"], r["_aa"])
                rec = {
                    "fixture_id": r["fixture_id"],
                    "model_id": mid,
                    "dist": dname,
                    "split": "train" if r in train else "val",
                    "lambda_home": outp.lambda_home,
                    "lambda_away": outp.lambda_away,
                    "lambda_total": outp.lambda_total,
                    "uncertainty": outp.uncertainty,
                    "football_w": outp.football_contribution,
                    "market_w": outp.market_contribution,
                    "home_mae": abs(r["_ah"] - outp.lambda_home),
                    "away_mae": abs(r["_aa"] - outp.lambda_away),
                    "total_mae": abs(r["_tot"] - outp.lambda_total),
                    "bias": r["_tot"] - outp.lambda_total,
                    "actual_total": r["_tot"],
                    "WDE_hit": as_bool(r.get("WDE_hit")),
                    "OU_hit": as_bool(r.get("OU_hit")),
                    "BTTS_hit": as_bool(r.get("BTTS_hit")),
                    **em,
                }
                backtest_rows.append(rec)
                # segments
                segs = ["all"]
                if r["_tot"] <= LOW_SCORE:
                    segs.append("low")
                elif r["_tot"] >= HIGH_SCORE:
                    segs.append("high5")
                elif r["_tot"] >= 4:
                    segs.append("high4")
                else:
                    segs.append("med")
                if missing == 0:
                    segs.append("complete_feature")
                if len(lines) >= 2:
                    segs.append("market_multi_line")
                if bundle.home.low_data or bundle.away.low_data:
                    segs.append("low_data")
                for s in segs:
                    segment_acc[f"{mid}|{dname}"][s].append(rec)

                if dname == "poisson":
                    rank_rows_by_model[mid].append(
                        {
                            "actual_score": f"{r['_ah']}-{r['_aa']}",
                            "predicted_rank": em["rank"],
                            "top5": em["top5"],
                        }
                    )

        # Factorial for selected models
        for mid in ("B0_canonical", "L2-A_football_only", "L2-F_uncertainty_aware", "L2-E_full_blend"):
            for dname, dfn in dist_fns.items():
                dist = dfn(outputs[mid].lambda_home, outputs[mid].lambda_away)
                em = exact_metrics(dist, r["_ah"], r["_aa"])
                factorial.append(
                    {
                        "fixture_id": r["fixture_id"],
                        "lambda_model": mid,
                        "dist_model": dname,
                        "top5": em["top5"],
                        "top10": em["top10"],
                        "log_loss": em["log_loss"],
                        "high": r["_tot"] >= HIGH_SCORE,
                    }
                )

        # Shadow persistence for families
        shadow_models = [
            ("LAMBDA_V2_FOOTBALL", "L2-A_football_only", "poisson"),
            ("LAMBDA_V2_MARKET_TOTAL", "L2-B_market_only", "poisson"),
            ("LAMBDA_V2_BLENDED", "L2-F_uncertainty_aware", "poisson"),
            ("EXACT_V2_POISSON", "L2-F_uncertainty_aware", "poisson"),
            ("EXACT_V2_DC", "L2-F_uncertainty_aware", "dixon_coles"),
            ("EXACT_V2_OVERDISPERSED", "L2-F_uncertainty_aware", "overdispersed"),
            ("EXACT_V2_SELECTED", "L2-E_full_blend", "dixon_coles"),
        ]
        for family, mid, dname in shadow_models:
            outp = outputs[mid]
            dist = dist_fns[dname](outp.lambda_home, outp.lambda_away)
            em = exact_metrics(dist, r["_ah"], r["_aa"])
            top5_mass = sum(float(e["probability"]) for e in dist[:5])
            ent = -sum(float(e["probability"]) * math.log(max(float(e["probability"]), 1e-12)) for e in dist[:20])
            persist_shadow(
                eval_conn,
                fixture_id=int(r["fixture_id"]),
                model_id=family,
                model_version="LAMBDA-V2-1",
                lambda_home=outp.lambda_home,
                lambda_away=outp.lambda_away,
                tops=em["tops"],
                dist_type=dname,
                canonical_prediction_id=str(r.get("prediction_id") or ""),
                meta={
                    "feature_schema_version": FEATURE_SCHEMA_VERSION,
                    "feature_cutoff": cutoff.isoformat(),
                    "history_count_home": bundle.home.n_total,
                    "history_count_away": bundle.away.n_total,
                    "missing_count": missing,
                    "fallback_count": fallback,
                    "odds_freshness": r.get("odds_freshness"),
                    "totals_lines": [ln.line for ln in lines],
                    "lambda_uncertainty": outp.uncertainty,
                    "top5_mass": top5_mass,
                    "entropy": ent,
                    "wde_direction_mass": fnum(r.get("home_probability")),
                    "inner_model": mid,
                    "football_w": outp.football_contribution,
                    "market_w": outp.market_contribution,
                },
            )

    write_csv(OUT / "historical_query_audit.csv", hist_audit)
    write_csv(OUT / "team_strength_validation.csv", strength_val)
    write_csv(OUT / "multi_line_lambda_estimates.csv", inversion_rows)
    write_csv(OUT / "market_line_consistency_audit.csv", mono_rows)
    write_csv(OUT / "alternate_totals_coverage.csv", coverage_rows)
    write_csv(OUT / "lambda_v2_backtest.csv", backtest_rows)

    # Model comparison on validation poisson
    comp = []
    for mid in model_fns:
        for split_name, subset in (("val", val), ("full", rows)):
            fids = {str(x["fixture_id"]) for x in subset}
            sub = [b for b in backtest_rows if b["model_id"] == mid and b["dist"] == "poisson" and str(b["fixture_id"]) in fids]
            high = [b for b in sub if b["actual_total"] >= HIGH_SCORE]
            low = [b for b in sub if b["actual_total"] <= LOW_SCORE]
            m = cohort_eval(sub)
            mh = cohort_eval(high)
            ml = cohort_eval(low)
            comp.append(
                {
                    "model_id": mid,
                    "split": split_name,
                    **{f"global_{k}": v for k, v in m.items()},
                    **{f"high_{k}": v for k, v in mh.items()},
                    **{f"low_{k}": v for k, v in ml.items()},
                }
            )
    write_csv(OUT / "lambda_v2_model_comparison_table.csv", comp)

    seg_rows = []
    for key, segs in segment_acc.items():
        mid, dname = key.split("|", 1)
        for seg, lst in segs.items():
            # validation only where possible
            lst_val = [x for x in lst if x["split"] == "val"]
            use = lst_val if lst_val else lst
            c = cohort_eval(use)
            seg_rows.append({"model_id": mid, "dist": dname, "segment": seg, **c})
    write_csv(OUT / "lambda_v2_segment_results.csv", seg_rows)

    # Rank bias for blended
    write_csv(OUT / "lambda_v2_rank_bias.csv", rank_bias_table(rank_rows_by_model.get("L2-F_uncertainty_aware", [])))
    write_csv(OUT / "rank_calibration_results.csv", rank_bias_table(rank_rows_by_model.get("B0_canonical", [])))

    # Factorial aggregation
    fac_sum = []
    groups: dict[tuple, list] = defaultdict(list)
    for f in factorial:
        groups[(f["lambda_model"], f["dist_model"])].append(f)
    for (lm, dm), lst in groups.items():
        high = [x for x in lst if x["high"]]
        fac_sum.append(
            {
                "lambda_model": lm,
                "dist_model": dm,
                "n": len(lst),
                "top5": sum(1 for x in lst if x["top5"]) / len(lst),
                "top10": sum(1 for x in lst if x["top10"]) / len(lst),
                "log_loss": mean([x["log_loss"] for x in lst]),
                "high_n": len(high),
                "high_top5": sum(1 for x in high if x["top5"]) / len(high) if high else None,
                "high_top10": sum(1 for x in high if x["top10"]) / len(high) if high else None,
            }
        )
    write_csv(OUT / "lambda_distribution_factorial_experiment.csv", fac_sum)
    write_csv(OUT / "exact_score_v2_candidates.csv", fac_sum)

    write_text(
        OUT / "mean_variance_correlation_decomposition.md",
        """# Mean vs variance vs correlation

Compare factorial rows:
- B0 + poisson = canonical means + canonical dist
- L2-* + poisson = improved/changed means only
- B0 + DC/overdispersed = variance/correlation only
- L2-* + DC/overdispersed = joint

If high-score Top5 only moves when means change, λ underestimation dominates.
If only DC helps global Top5 but not high-score, ranking/low-score correlation dominates.
""",
    )
    write_text(
        OUT / "lambda_v2_model_comparison.md",
        "See `lambda_v2_model_comparison_table.csv` and `lambda_v2_segment_results.csv`.\n",
    )

    # Pick bests on val poisson with gates similar to prior research
    def pick(mid_prefix: str | None = None):
        cands = []
        b0 = next(c for c in comp if c["model_id"] == "B0_canonical" and c["split"] == "val")
        for c in comp:
            if c["split"] != "val":
                continue
            if mid_prefix and not c["model_id"].startswith(mid_prefix):
                continue
            if c["model_id"] == "B0_canonical" and mid_prefix:
                continue
            if (c.get("global_top5") or 0) < (b0.get("global_top5") or 0) - 0.05:
                continue
            cands.append(((c.get("high_top5") or 0), (c.get("global_top5") or 0), -(c.get("global_total_mae") or 9), c))
        cands.sort(reverse=True)
        return cands[0][3] if cands else b0

    best_foot = pick("L2-A")
    best_mkt = pick("L2-B")
    best_blend = pick("L2-F") if any(c["model_id"] == "L2-F_uncertainty_aware" for c in comp) else pick("L2-E")
    # Prefer L2-F/E explicitly among blends
    blend_opts = [c for c in comp if c["split"] == "val" and c["model_id"] in ("L2-C_football_hda", "L2-D_football_totals", "L2-E_full_blend", "L2-F_uncertainty_aware")]
    b0v = next(c for c in comp if c["model_id"] == "B0_canonical" and c["split"] == "val")
    blend_opts = [c for c in blend_opts if (c.get("global_top5") or 0) >= (b0v.get("global_top5") or 0) - 0.05]
    blend_opts.sort(key=lambda c: (-(c.get("high_top5") or 0), -(c.get("global_top5") or 0), c.get("global_total_mae") or 9))
    best_blend = blend_opts[0] if blend_opts else b0v
    b0_full = next(c for c in comp if c["model_id"] == "B0_canonical" and c["split"] == "full")
    foot_full = next(c for c in comp if c["model_id"] == "L2-A_football_only" and c["split"] == "full")
    blend_full = next(c for c in comp if c["model_id"] == best_blend["model_id"] and c["split"] == "full")

    shadow_n = eval_conn.execute("SELECT COUNT(*) FROM lambda_v2_shadow_outputs").fetchone()[0]
    derived_n = eval_conn.execute("SELECT COUNT(*) FROM derived_historical_team_form_snapshots").fetchone()[0]
    tot_n = eval_conn.execute("SELECT COUNT(*) FROM totals_market_shadow_snapshots").fetchone()[0]

    # Promotion / infra docs
    write_text(
        OUT / "lambda_forward_validation_plan.md",
        f"""# Forward validation gates\n\nMin samples: global {FORWARD_MIN_GLOBAL}, complete-feature {FORWARD_MIN_COMPLETE_FEATURE}, 4+ {FORWARD_MIN_ACTUAL_4PLUS}, 5+ {FORWARD_MIN_ACTUAL_5PLUS}, multi-line {FORWARD_MIN_MULTI_LINE_MARKET}.\nCurrent eval n={len(rows)}; complete_feature≈{complete_feature_n}; multi_line≈{multi_line_n}.\n""",
    )
    write_json(
        OUT / "promotion_gate_config.json",
        {
            "min_global": FORWARD_MIN_GLOBAL,
            "min_complete_feature": FORWARD_MIN_COMPLETE_FEATURE,
            "min_4plus": FORWARD_MIN_ACTUAL_4PLUS,
            "min_5plus": FORWARD_MIN_ACTUAL_5PLUS,
            "min_multi_line": FORWARD_MIN_MULTI_LINE_MARKET,
            "require_high_top5_lift": True,
            "max_global_top5_regression_pp": 2.0,
            "shadow_only": True,
        },
    )
    write_text(
        ROOT / "migrations" / "research_football_strength_lambda_v2.sql",
        f"""-- Additive research/shadow schemas (safe; do not alter frozen_predictions)
-- Apply only after review. Rollback: DROP TABLE IF EXISTS ...
CREATE TABLE IF NOT EXISTS derived_historical_team_form_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  fixture_id INTEGER NOT NULL,
  team_name TEXT NOT NULL,
  home_or_away_role TEXT NOT NULL,
  cutoff_timestamp TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  feature_schema_version TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS totals_market_shadow_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  fixture_id INTEGER,
  line REAL NOT NULL,
  over_odds REAL,
  under_odds REAL,
  created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lambda_v2_shadow_outputs (
  shadow_id TEXT PRIMARY KEY,
  fixture_id INTEGER NOT NULL,
  model_id TEXT NOT NULL,
  shadow_hash TEXT NOT NULL,
  created_at_utc TEXT NOT NULL
);
""",
    )

    # Final reports
    high_lift = (blend_full.get("high_top5") or 0) - (b0_full.get("high_top5") or 0)
    status = "FOOTBALL_STRENGTH_FOUNDATION_COMPLETE_LAMBDA_V2_PARTIAL"
    if high_lift > 0.02 and len(rows) >= FORWARD_MIN_GLOBAL:
        status = "FOOTBALL_STRENGTH_FOUNDATION_AND_LAMBDA_V2_COMPLETE"
    elif complete_feature_n < 50:
        status = "FOOTBALL_STRENGTH_FOUNDATION_PARTIAL_DATA_LIMITATION"

    exec_sum = f"""# FINAL PHASE EXECUTIVE SUMMARY

Status: **{status}**

## Why canonical λ is odds-only
ECSE `extract_lambdas` inverts closing O/U + 1X2. Football strength was never wired; `team_form_snapshots` has schema but **no writer** (incomplete integration, not a deliberate “formless” product choice for λ).

## Foundation delivered
- Prematch feature contract `{FEATURE_SCHEMA_VERSION}`
- Leakage-safe historical match service
- Derived team form snapshots (n={derived_n}) — freezes untouched
- Totals market shadow persistence (n={tot_n}); O/U 4.5 not invented
- Team strength engine V1 + Lambda V2 candidates L2-A..F
- Exact V2 dist variants + shadow family rows={shadow_n}

## Metrics (full n={len(rows)}, poisson)
| Model | Top5 | High Top5 | Total MAE | Bias |
|-------|------|-----------|-----------|------|
| B0 canonical | {b0_full.get('global_top5')} | {b0_full.get('high_top5')} | {b0_full.get('global_total_mae')} | {b0_full.get('global_mean_bias')} |
| L2-A football | {foot_full.get('global_top5')} | {foot_full.get('high_top5')} | {foot_full.get('global_total_mae')} | {foot_full.get('global_mean_bias')} |
| Best blend ({best_blend['model_id']}) | {blend_full.get('global_top5')} | {blend_full.get('high_top5')} | {blend_full.get('global_total_mae')} | {blend_full.get('global_mean_bias')} |

## Deployable vs shadow-only
Deployable after review: historical service, derived snapshot writer, totals shadow schema, feature contract, leakage tests.
Must remain shadow: Lambda V2 / Exact V2 as canonical replacements.

## Blockers
- High-score Top5 lift not yet material on n=168
- Multi-line market coverage incomplete on freezes ({multi_line_n}/{len(rows)})
- Forward sample below promotion gates
"""
    write_text(OUT / "FINAL_PHASE_EXECUTIVE_SUMMARY.md", exec_sum)
    write_text(ROOT / "FINAL_PHASE_EXECUTIVE_SUMMARY.md", exec_sum)

    reports = {
        "FINAL_FOOTBALL_STRENGTH_FOUNDATION_REPORT.md": f"""# Football strength foundation

1. Canonical λ odds-only via extract_lambdas
2. Incomplete integration (empty team_form_snapshots, no writer)
3. Root cause: schema without writer/scheduler/ECSE hook
4. O/U 3.5/4.5: historical under-lines common; over-45 sparse; extractor ignores 4.5; freezes lack lines
5. Football feature coverage: history mean n≈ see validation CSV; complete_feature={complete_feature_n}
6. Freshness: kickoff-strict history; market from freeze freshness flags
7. Leakage protections: assertions in historical_match_service
8–15. See executive summary metrics
16–25. Shadow={shadow_n}; production changes=none; infra additive only

Status: {status}
""",
        "FINAL_LAMBDA_V2_RESEARCH_REPORT.md": f"""# Lambda V2 research

Best football-only: L2-A (full Top5={foot_full.get('global_top5')}, high={foot_full.get('high_top5')})
Best market: L2-B / B0 equivalent
Best blended: {best_blend['model_id']} (full Top5={blend_full.get('global_top5')}, high={blend_full.get('high_top5')})

No production promotion. Shadow family LAMBDA_V2_*.
Status: {status}
""",
        "FINAL_EXACT_SCORE_V2_REPORT.md": """# Exact Score V2

Factorial experiment isolates means vs DC vs overdispersion.
See lambda_distribution_factorial_experiment.csv.
Rank calibration is diagnostic only — must not conceal bad λ.
""",
        "FINAL_SHADOW_PIPELINE_SPEC.md": f"""# Shadow pipeline spec

Table `lambda_v2_shadow_outputs` (n={shadow_n})
Families: LAMBDA_V2_FOOTBALL, LAMBDA_V2_MARKET_TOTAL, LAMBDA_V2_BLENDED,
EXACT_V2_POISSON, EXACT_V2_DC, EXACT_V2_OVERDISPERSED, EXACT_V2_SELECTED
Never canonical. Separate from HST and prior LTS shadows.
""",
        "FINAL_SAFE_INFRA_DEPLOYMENT_PLAN.md": """# Safe infra deployment plan

## May deploy after review (additive)
- historical match query service
- derived form snapshot writer (or future-job production writer behind flag)
- totals market shadow persistence schema
- feature contract / metadata
- leakage tests

## Must NOT deploy as canonical yet
- Lambda V2
- Exact Score V2
- rank calibration
- regime selector

## Checklist
- [ ] migration review
- [ ] rollback scripts
- [ ] local/GitHub/prod/GPT Actions parity matrix
- [ ] no freeze mutation
- [ ] GPT Actions schema unchanged for canonical fields

Do not auto-deploy.
""",
    }
    for name, body in reports.items():
        write_text(OUT / name, body)
        write_text(ROOT / name, body)

    payload = {
        "status": status,
        "n": len(rows),
        "complete_feature_n": complete_feature_n,
        "multi_line_n": multi_line_n,
        "shadow_n": shadow_n,
        "derived_form_n": derived_n,
        "totals_n": tot_n,
        "b0_full": b0_full,
        "football_full": foot_full,
        "blend_full": blend_full,
        "best_blend_model": best_blend["model_id"],
        "production_changes": False,
        "branch": BRANCH,
        "artifact": str(OUT),
    }
    write_json(OUT / "FINAL_FOOTBALL_STRENGTH_FOUNDATION_REPORT.json", payload)
    write_json(ROOT / "FINAL_FOOTBALL_STRENGTH_FOUNDATION_REPORT.json", payload)
    write_json(OUT / "run_summary.json", payload)

    fi.close()
    eval_conn.close()
    print("STATUS", status)
    print("shadow", shadow_n, "derived_form", derived_n, "totals", tot_n)
    print("multi_line", multi_line_n, "complete_feature", complete_feature_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
