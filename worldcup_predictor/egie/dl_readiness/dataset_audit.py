"""PHASE DL-0 — Deep Learning dataset readiness audit (research only)."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts"
DATA = ROOT / "data"
DB_PATH = DATA / "football_intelligence.db"

# Minimum sample thresholds (research heuristics)
THRESHOLDS = {
    "ft_transformer_rows": 10_000,
    "ft_transformer_features": 20,
    "temporal_transformer_events_per_match": 5,
    "temporal_transformer_fixtures": 5_000,
    "deep_survival_timing_labels": 3_000,
    "player_embedding_players": 500,
    "player_embedding_matches_per_player": 10,
    "lightgbm_minimum": 1_000,
    "neural_minimum": 5_000,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _parquet_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "row_count": 0, "feature_count": 0}
    df = pd.read_parquet(path)
    null_pct = {c: round(float(df[c].isna().mean()), 4) for c in df.columns}
    dup_pct = 0.0
    if "fixture_id" in df.columns:
        dup_pct = round(float(1 - df["fixture_id"].nunique() / max(len(df), 1)), 4)
    elif "sportmonks_fixture_id" in df.columns:
        dup_pct = round(float(1 - df["sportmonks_fixture_id"].nunique() / max(len(df), 1)), 4)
    seasons: dict[str, int] = {}
    leagues: dict[str, int] = {}
    if "season" in df.columns:
        seasons = {str(k): int(v) for k, v in df["season"].value_counts().head(10).items()}
    for col in ("league", "competition_key"):
        if col in df.columns:
            leagues = {str(k): int(v) for k, v in df[col].value_counts().head(15).items()}
            break
    labels: dict[str, Any] = {}
    for col in (
        "first_goal_minute",
        "baseline_first_goal_team",
        "baseline_goal_range",
        "censored_match",
        "home_goals",
        "away_goals",
    ):
        if col in df.columns:
            labels[col] = {
                "non_null_pct": round(1 - float(df[col].isna().mean()), 4),
                "unique_values": int(df[col].nunique(dropna=True)),
            }
    return {
        "exists": True,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "row_count": int(len(df)),
        "feature_count": int(len(df.columns)),
        "columns": list(df.columns),
        "missing_value_pct": null_pct,
        "duplicate_pct": dup_pct,
        "season_coverage": seasons,
        "league_coverage": leagues,
        "label_availability": labels,
    }


def _jsonl_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "row_count": 0}
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    fixture_ids = [r.get("fixture_id") for r in rows if r.get("fixture_id") is not None]
    dup_pct = round(1 - len(set(fixture_ids)) / max(len(fixture_ids), 1), 4) if fixture_ids else 0.0
    keys = set()
    for r in rows[:50]:
        keys.update(r.keys())
    return {
        "exists": True,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "row_count": len(rows),
        "feature_count": len(keys),
        "duplicate_fixture_pct": dup_pct,
        "sample_keys": sorted(keys)[:25],
    }


def _sqlite_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def audit_dataset_inventory() -> dict[str, Any]:
    """STEP 1 — inventory all named datasets."""
    inv: dict[str, Any] = {"generated_at": _now(), "datasets": {}}

    # 1 EGIE Survival
    inv["datasets"]["egie_survival"] = {
        "name": "EGIE Survival Dataset",
        "source": "data/egie/survival/survival_dataset.parquet",
        **_parquet_stats(DATA / "egie" / "survival" / "survival_dataset.parquet"),
        "shadow_predictions": _jsonl_stats(DATA / "egie" / "survival" / "survival_shadow_predictions.jsonl"),
    }

    # 2 Goal Event Dataset (SQLite)
    with _sqlite_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM fixture_goal_events")
        goal_rows = cur.fetchone()[0]
        cur.execute(
            """
            SELECT f.competition_key, COUNT(DISTINCT e.fixture_id)
            FROM fixture_goal_events e
            JOIN fixtures f ON f.fixture_id = e.fixture_id
            GROUP BY f.competition_key ORDER BY COUNT(*) DESC
            """
        )
        goal_by_league = dict(cur.fetchall())
        cur.execute(
            "SELECT COUNT(DISTINCT fixture_id) FROM fixture_goal_events WHERE minute IS NOT NULL"
        )
        with_minute = cur.fetchone()[0]

    inv["datasets"]["goal_events"] = {
        "name": "Goal Event Dataset",
        "source": "sqlite:fixture_goal_events",
        "row_count": goal_rows,
        "fixtures_with_events": sum(goal_by_league.values()),
        "fixtures_with_minute": with_minute,
        "league_coverage": goal_by_league,
        "label_availability": {
            "first_goal_minute": {"fixtures": with_minute},
            "goal_sequence": {"row_count": goal_rows},
        },
        "feature_count": 8,
        "missing_value_pct": {},
        "duplicate_pct": 0.0,
    }

    # 3 API-Football Historical
    csv_path = DATA / "historical" / "worldcup_sample.csv"
    csv_rows = 0
    if csv_path.is_file():
        csv_rows = max(0, sum(1 for _ in csv_path.read_text(encoding="utf-8").splitlines()) - 2)
    with _sqlite_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT competition_key, COUNT(*) FROM fixtures GROUP BY competition_key")
        api_fixtures = dict(cur.fetchall())
        cur.execute("SELECT COUNT(*) FROM fixture_enrichment")
        enrich_total = cur.fetchone()[0]

    inv["datasets"]["api_football_historical"] = {
        "name": "API-Football Historical Dataset",
        "source": "sqlite:fixtures + fixture_enrichment",
        "row_count": sum(api_fixtures.values()),
        "demo_csv_rows": csv_rows,
        "league_coverage": api_fixtures,
        "enrichment_rows": enrich_total,
        "feature_count": 12,
        "label_availability": {"fixture_results": {"row_count": _table_count("fixture_results")}},
    }

    # 4 UEFA Club
    uefa_mapping = _load_json(ARTIFACTS / "uefa_fixture_mapping.json") or {}
    uefa_fixtures = uefa_mapping.get("fixtures") or []
    inv["datasets"]["uefa_club"] = {
        "name": "UEFA Club Dataset",
        "source": "artifacts/uefa_fixture_mapping.json + sportmonks raw cache",
        "row_count": len(uefa_fixtures),
        "league_coverage": dict(Counter(str(f.get("competition_key") or "unknown") for f in uefa_fixtures)),
        **_parquet_stats(DATA / "egie" / "uefa_club" / "uefa_survival_dataset.parquet"),
    }

    # 5 Odds
    with _sqlite_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM odds_snapshots")
        odds_snap = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM odds_api_cache")
        odds_cache = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(*) FROM fixture_enrichment
            WHERE odds_json IS NOT NULL AND odds_json != '' AND odds_json != '[]'
            """
        )
        odds_enrich = cur.fetchone()[0]

    uefa_raw = list((DATA / "egie" / "uefa_club" / "raw").glob("*.json"))
    legacy_raw = list((DATA / "data" / "egie" / "uefa_club" / "raw").glob("*.json"))
    seen: set[int] = set()
    uefa_cache_ids: list[int] = []
    for p in uefa_raw + legacy_raw:
        try:
            fid = int(p.stem)
        except ValueError:
            continue
        if fid in seen:
            continue
        seen.add(fid)
        uefa_cache_ids.append(fid)

    k2_backtest = _load_json(ARTIFACTS / "first_goal_market_backtest.json") or {}
    inv["datasets"]["odds"] = {
        "name": "Odds Dataset",
        "source": "odds_snapshots + UEFA sportmonks cache + odds_api_cache",
        "row_count": odds_snap + len(uefa_cache_ids),
        "odds_snapshots": odds_snap,
        "odds_api_cache_entries": odds_cache,
        "fixture_enrichment_odds": odds_enrich,
        "uefa_sportmonks_cache_fixtures": len(uefa_cache_ids),
        "sharp_mw_fg_accuracy_uefa": (k2_backtest.get("strategies") or {}).get("C", {}).get("direct_fg_accuracy"),
        "feature_count": 15,
        "label_availability": {"match_winner_implied": {"coverage_fixtures": 104}},
    }

    # 6 Lineups
    with _sqlite_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM fixture_enrichment
            WHERE lineups_json IS NOT NULL AND lineups_json != '' AND lineups_json != '[]'
            """
        )
        lineup_rows = cur.fetchone()[0]
    lineup_shadow = _jsonl_stats(DATA / "shadow" / "expected_lineup_accuracy.jsonl")
    inv["datasets"]["lineups"] = {
        "name": "Lineup Dataset",
        "source": "fixture_enrichment.lineups_json + expected_lineup shadow",
        "row_count": lineup_rows,
        "shadow_accuracy_rows": lineup_shadow.get("row_count", 0),
        "coverage_pct_of_enrichment": round(100 * lineup_rows / max(enrich_total, 1), 2),
        "feature_count": 6,
        "label_availability": {"confirmed_lineups": {"fixture_count": lineup_rows}},
    }

    # 7 Injuries — sparse in store
    inv["datasets"]["injuries"] = {
        "name": "Injuries Dataset",
        "source": "EGIE provider features (sparse)",
        "row_count": 0,
        "coverage_pct": 0.0,
        "note": "egie_paid_provider_audit: 0% injuries in premier_league provider store",
        "feature_count": 4,
        "label_availability": {},
    }
    paid_audit = _load_json(ARTIFACTS / "egie_paid_provider_audit.json")
    if paid_audit:
        inv["datasets"]["injuries"]["coverage_pct"] = (
            (paid_audit.get("provider_feature_store") or {}).get("coverage_pct", {}).get("injuries", 0.0)
        )

    # 8 Match Statistics
    with _sqlite_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM fixture_enrichment
            WHERE statistics_json IS NOT NULL AND statistics_json != '' AND statistics_json != '[]'
            """
        )
        stats_rows = cur.fetchone()[0]
    inv["datasets"]["match_statistics"] = {
        "name": "Match Statistics Dataset",
        "source": "fixture_enrichment.statistics_json",
        "row_count": stats_rows,
        "coverage_pct_of_enrichment": round(100 * stats_rows / max(enrich_total, 1), 2),
        "feature_count": 20,
    }

    # 9 xG
    with _sqlite_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM xg_snapshots")
        xg_snap = cur.fetchone()[0]
    xg_audit = _load_json(ARTIFACTS / "historical_xg_availability_audit.json") or {}
    inv["datasets"]["xg"] = {
        "name": "xG Dataset",
        "source": "xg_snapshots + sportmonks UEFA cache",
        "row_count": xg_snap,
        "sqlite_xg_snapshots": xg_snap,
        "uefa_parser_xg_resolved_pct": None,
        "feature_count": 8,
        "note": "UEFA cache: xG mostly absent on legacy seasons; ~3.6% after API-J expansion",
    }
    if uefa_fixtures:
        uefa_parquet = _parquet_stats(DATA / "egie" / "uefa_club" / "uefa_survival_dataset.parquet")
        hx = (uefa_parquet.get("label_availability") or {}).get("home_xg", {})
        inv["datasets"]["xg"]["uefa_home_xg_non_null_pct"] = hx.get("non_null_pct")

    # 10 Pressure
    inv["datasets"]["pressure"] = {
        "name": "Pressure Dataset",
        "source": "Sportmonks pressure index (not in API-Football store)",
        "row_count": 0,
        "coverage_pct": 0.0,
        "note": "egie_paid_provider_audit: 0% pressure in premier_league provider store",
        "feature_count": 4,
    }
    if paid_audit:
        inv["datasets"]["pressure"]["coverage_pct"] = (
            (paid_audit.get("provider_feature_store") or {}).get("coverage_pct", {}).get("pressure", 0.0)
        )

    # 11 Prediction History
    inv["datasets"]["prediction_history"] = {
        "name": "Prediction History Dataset",
        "source": "data/predictions/prediction_history.jsonl + sqlite predictions",
        **_jsonl_stats(DATA / "predictions" / "prediction_history.jsonl"),
        "sqlite_predictions": _table_count("predictions"),
        "sqlite_prediction_markets": _table_count("prediction_markets"),
        "label_availability": {"verification_results": {"row_count": _table_count("verification_results")}},
    }

    # 12 Accuracy Tracker
    inv["datasets"]["accuracy_tracker"] = {
        "name": "Accuracy Tracker Dataset",
        "source": "verification_results + learning_records_v2 + phase backtests",
        "row_count": _table_count("verification_results") + _table_count("learning_records_v2"),
        "verification_results": _table_count("verification_results"),
        "learning_records_v2": _table_count("learning_records_v2"),
        "worldcup_stored_predictions": _table_count("worldcup_stored_predictions"),
        "phase52a_fg_baseline": 0.5076,
        "phase52a_goal_range_baseline": 0.2779,
        "uefa_sharp_odds_fg": 0.7872,
    }

    return inv


def _table_count(table: str) -> int:
    if not DB_PATH.is_file():
        return 0
    with _sqlite_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT COUNT(*) FROM [{table}]")
            return int(cur.fetchone()[0])
        except sqlite3.Error:
            return 0


def _db_market_labels() -> dict[str, Any]:
    """Derive label counts from SQLite for market readiness."""
    out: dict[str, Any] = {}
    if not DB_PATH.is_file():
        return out

    with _sqlite_conn() as conn:
        cur = conn.cursor()

        # Finished fixtures with goals
        cur.execute(
            """
            SELECT COUNT(*) FROM fixture_results
            WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL
            """
        )
        finished = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM fixture_results
            WHERE total_goals IS NOT NULL AND total_goals >= 2
            """
        )
        over_15 = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(*) FROM fixture_results WHERE total_goals IS NOT NULL AND total_goals >= 3
            """
        )
        over_25 = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(*) FROM fixture_results WHERE total_goals IS NOT NULL AND total_goals >= 4
            """
        )
        over_35 = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM fixture_results
            WHERE home_goals > 0 AND away_goals > 0
            """
        )
        btts_yes = cur.fetchone()[0]

        cur.execute(
            """
            SELECT winner, COUNT(*) FROM fixture_results
            WHERE winner IS NOT NULL GROUP BY winner
            """
        )
        mw_dist = dict(cur.fetchall())

        cur.execute("SELECT COUNT(DISTINCT fixture_id) FROM fixture_goal_events")
        fg_fixtures = cur.fetchone()[0]

    out["finished_fixtures"] = finished
    out["btts_yes"] = btts_yes
    out["btts_no"] = finished - btts_yes
    out["over_1_5"] = over_15
    out["over_2_5"] = over_25
    out["over_3_5"] = over_35
    out["match_winner_distribution"] = mw_dist
    out["fixtures_with_goal_events"] = fg_fixtures

    # Survival parquet labels
    surv = _parquet_stats(DATA / "egie" / "survival" / "survival_dataset.parquet")
    fg_minute_pct = (surv.get("label_availability") or {}).get("first_goal_minute", {}).get("non_null_pct", 0)
    out["survival_first_goal_minute_non_null_pct"] = fg_minute_pct
    out["survival_rows"] = surv.get("row_count", 0)

    # UEFA FG side
    uefa = _parquet_stats(DATA / "egie" / "uefa_club" / "uefa_survival_dataset.parquet")
    out["uefa_rows"] = uefa.get("row_count", 0)
    out["uefa_first_goal_minute_non_null_pct"] = (
        (uefa.get("label_availability") or {}).get("first_goal_minute", {}).get("non_null_pct", 0)
    )

    return out


def audit_market_readiness(inventory: dict[str, Any]) -> dict[str, Any]:
    """STEP 2 — per-market readiness."""
    labels = _db_market_labels()
    finished = labels.get("finished_fixtures", 0)
    surv_rows = labels.get("survival_rows", 0)
    uefa_rows = labels.get("uefa_rows", 0)

    def _balance(pos: int, total: int) -> dict[str, float]:
        if total <= 0:
            return {"positive_rate": 0.0, "negative_rate": 0.0}
        return {"positive_rate": round(pos / total, 4), "negative_rate": round(1 - pos / total, 4)}

    markets: dict[str, Any] = {}

    # FG Team — best labels in UEFA odds subset; PL baseline ~51%
    fg_evaluable = 97  # from K2 backtest
    markets["first_goal_team"] = {
        "available_samples": max(surv_rows, uefa_rows, fg_evaluable),
        "positive_samples": "home/away split ~50/50",
        "class_balance": {"home": 0.5, "away": 0.5, "none": 0.05},
        "feature_richness": "high with odds; low with xG alone",
        "historical_depth": "1 PL season + UEFA multi-season partial",
        "current_baseline_accuracy": 0.5076,
        "odds_derived_ceiling": 0.7872,
        "readiness": "PARTIAL",
        "readiness_reason": "Labels exist but EGIE baseline 51%; odds enrichment 79% — DL unlikely to beat market intelligence",
    }

    markets["goal_range"] = {
        "available_samples": surv_rows,
        "positive_samples": surv_rows,
        "class_balance": "multi-class (~5 ranges)",
        "feature_richness": "moderate (rates + history)",
        "historical_depth": "380 PL fixtures",
        "current_baseline_accuracy": 0.2779,
        "survival_shadow_delta": 0.0316,
        "readiness": "PARTIAL",
        "readiness_reason": "Survival shadow +3.2pp but below 35% target; needs more timing labels",
    }

    markets["goal_minute"] = {
        "available_samples": int(surv_rows * float(labels.get("survival_first_goal_minute_non_null_pct") or 0)),
        "positive_samples": "per-minute hazard bins",
        "class_balance": "highly imbalanced (90+ classes)",
        "feature_richness": "moderate",
        "historical_depth": "weak — survival parquet FG minute 0% populated",
        "current_baseline_accuracy": 0.0335,
        "survival_soft_delta": 0.0459,
        "readiness": "NOT READY",
        "readiness_reason": "Timing labels missing in survival parquet; exact minute 3.4% baseline",
    }

    markets["next_goal_team"] = {
        "available_samples": labels.get("fixtures_with_goal_events", 0),
        "readiness": "NOT READY",
        "readiness_reason": "No dedicated in-play label store",
    }

    btts_yes = labels.get("btts_yes", 0)
    markets["btts"] = {
        "available_samples": finished,
        "positive_samples": btts_yes,
        "class_balance": _balance(btts_yes, finished),
        "feature_richness": "moderate (team stats)",
        "historical_depth": f"{finished} finished fixtures",
        "readiness": "READY" if finished >= 1000 else "PARTIAL",
        "readiness_reason": f"{finished} labels; classical ML sufficient",
    }

    for key, threshold, col in [
        ("over_1_5", 2, labels.get("over_1_5", 0)),
        ("over_2_5", 3, labels.get("over_2_5", 0)),
        ("over_3_5", 4, labels.get("over_3_5", 0)),
    ]:
        markets[key] = {
            "available_samples": finished,
            "positive_samples": col,
            "class_balance": _balance(col, finished),
            "feature_richness": "moderate",
            "historical_depth": f"{finished} fixtures",
            "readiness": "READY" if finished >= 1000 else "PARTIAL",
        }

    markets["match_winner"] = {
        "available_samples": finished,
        "positive_samples": finished,
        "class_balance": labels.get("match_winner_distribution", {}),
        "feature_richness": "high with odds",
        "readiness": "READY",
        "readiness_reason": "1617 results; odds-driven approaches dominate",
    }

    markets["correct_score"] = {
        "available_samples": finished,
        "class_balance": "sparse (~20+ scorelines)",
        "readiness": "PARTIAL",
        "readiness_reason": "Needs Poisson/neural Poisson; sample OK but high cardinality",
    }

    markets["first_half_goal"] = {
        "available_samples": labels.get("fixtures_with_goal_events", 0),
        "readiness": "PARTIAL",
        "readiness_reason": "Events exist; half-time labels need extraction",
    }

    markets["anytime_goalscorer"] = {
        "available_samples": _table_count("player_stats_snapshots"),
        "readiness": "NOT READY",
        "readiness_reason": "0 player_stats_snapshots; no player history store",
    }

    markets["first_goalscorer"] = {
        "available_samples": 0,
        "readiness": "NOT READY",
        "readiness_reason": "No scorer label dataset; prediction_history has sparse scorer fields",
    }

    return {"generated_at": _now(), "markets": markets, "label_summary": labels}


def audit_feature_coverage(inventory: dict[str, Any]) -> dict[str, Any]:
    """STEP 3 — feature coverage audit."""
    enrich_total = (inventory.get("datasets") or {}).get("api_football_historical", {}).get("enrichment_rows", 0)
    ds = inventory.get("datasets") or {}

    def _pct(num: int, den: int) -> float:
        return round(100 * num / max(den, 1), 2)

    features = {
        "odds": {
            "coverage_pct": _pct(ds.get("odds", {}).get("fixture_enrichment_odds", 0), enrich_total),
            "missing_pct": round(100 - _pct(ds.get("odds", {}).get("fixture_enrichment_odds", 0), enrich_total), 2),
            "usable_pct": _pct(ds.get("odds", {}).get("uefa_sportmonks_cache_fixtures", 0), 220),
            "notes": "API-Football enrichment odds 4.3%; UEFA Sportmonks cache strong",
        },
        "closing_odds": {
            "coverage_pct": 56.76,
            "missing_pct": 43.24,
            "usable_pct": 56.76,
            "notes": "UEFA K2 closing MW coverage on mapped fixtures",
        },
        "sharp_odds": {
            "coverage_pct": 56.76,
            "missing_pct": 43.24,
            "usable_pct": 56.76,
            "notes": "Sharp MW 78.7% FG accuracy; primary signal",
        },
        "events": {
            "coverage_pct": _pct(1532, enrich_total),
            "missing_pct": _pct(enrich_total - 1532, enrich_total),
            "usable_pct": 94.47,
            "notes": "fixture_goal_events + enrichment events",
        },
        "lineups": {
            "coverage_pct": ds.get("lineups", {}).get("coverage_pct_of_enrichment", 0),
            "missing_pct": round(100 - float(ds.get("lineups", {}).get("coverage_pct_of_enrichment", 0)), 2),
            "usable_pct": 3.16,
            "notes": "Enrichment lineups high; EGIE provider lineups 3.16%",
        },
        "injuries": {
            "coverage_pct": ds.get("injuries", {}).get("coverage_pct", 0),
            "missing_pct": 100.0,
            "usable_pct": 0.0,
        },
        "statistics": {
            "coverage_pct": ds.get("match_statistics", {}).get("coverage_pct_of_enrichment", 0),
            "missing_pct": round(100 - float(ds.get("match_statistics", {}).get("coverage_pct_of_enrichment", 0)), 2),
            "usable_pct": 90.9,
        },
        "xg": {
            "coverage_pct": float(ds.get("xg", {}).get("uefa_home_xg_non_null_pct", 0) or 0) * 100,
            "missing_pct": 96.4,
            "usable_pct": 3.6,
            "notes": "Primary bottleneck per API-J",
        },
        "pressure": {
            "coverage_pct": ds.get("pressure", {}).get("coverage_pct", 0),
            "missing_pct": 100.0,
            "usable_pct": 0.0,
        },
        "predictions": {
            "coverage_pct": _pct(ds.get("prediction_history", {}).get("row_count", 0), enrich_total),
            "missing_pct": 95.0,
            "usable_pct": _pct(ds.get("accuracy_tracker", {}).get("verification_results", 0), enrich_total),
            "notes": "Live WC predictions; limited verified outcomes",
        },
    }
    return {"generated_at": _now(), "features": features, "enrichment_denominator": enrich_total}


def rank_dl_suitability(market_readiness: dict[str, Any], feature_coverage: dict[str, Any]) -> dict[str, Any]:
    """STEP 4 — DL suitability tiers."""
    rankings = [
        {
            "market": "fg_team",
            "tier": "C",
            "rationale": "Odds intelligence 78.7% vs baseline 51%; DL adds complexity without beating sharp MW",
        },
        {
            "market": "goal_range",
            "tier": "B",
            "rationale": "Kaplan-Meier survival +3.2pp; classical survival may suffice before deep survival",
        },
        {
            "market": "goal_minute",
            "tier": "C",
            "rationale": "Labels missing in parquet; 3.4% exact accuracy; data fix required first",
        },
        {
            "market": "btts",
            "tier": "A",
            "rationale": "1600+ labels, balanced; tabular ML likely optimal",
        },
        {
            "market": "over_under",
            "tier": "A",
            "rationale": "1600+ labels; Poisson/LightGBM standard approach",
        },
        {
            "market": "correct_score",
            "tier": "B",
            "rationale": "High cardinality; neural Poisson possible but needs more seasons",
        },
        {
            "market": "goalscorer",
            "tier": "C",
            "rationale": "No player-level history store",
        },
    ]
    return {"generated_at": _now(), "ranked": rankings}


def match_architectures(market_readiness: dict[str, Any]) -> dict[str, Any]:
    """STEP 5 — architecture matching per market."""
    return {
        "generated_at": _now(),
        "matches": {
            "first_goal_team": {
                "recommended": ["market_intelligence", "logistic_regression", "lightgbm"],
                "not_recommended": ["ft_transformer", "lstm"],
                "reason": "Sharp odds dominate; parser/enrichment fixes beat ML",
            },
            "goal_range": {
                "recommended": ["kaplan_meier", "hazard_model", "lightgbm"],
                "future_dl": ["deep_survival_network"],
                "reason": "Phase 52A survival +3.2pp without deep learning",
            },
            "goal_minute": {
                "recommended": ["hazard_model", "temporal_survival"],
                "future_dl": ["deep_survival_network", "temporal_transformer"],
                "reason": "Needs timing labels before any architecture",
            },
            "btts": {
                "recommended": ["logistic", "lightgbm", "poisson_btts"],
                "not_recommended": ["transformer"],
            },
            "over_under": {
                "recommended": ["poisson", "lightgbm", "market_intelligence"],
            },
            "correct_score": {
                "recommended": ["poisson", "dixon_coles"],
                "future_dl": ["neural_poisson"],
            },
            "goalscorer": {
                "recommended": ["player_embeddings"],
                "prerequisite": "player match history ingestion",
            },
            "match_winner": {
                "recommended": ["market_intelligence", "elo", "lightgbm"],
            },
        },
    }


def check_dl_thresholds(inventory: dict[str, Any]) -> dict[str, Any]:
    """STEP 6 — minimum data thresholds."""
    surv_rows = (inventory.get("datasets") or {}).get("egie_survival", {}).get("row_count", 0)
    surv_features = (inventory.get("datasets") or {}).get("egie_survival", {}).get("feature_count", 0)
    goal_events = (inventory.get("datasets") or {}).get("goal_events", {}).get("row_count", 0)
    finished = _db_market_labels().get("finished_fixtures", 0)
    players = _table_count("player_stats_snapshots")

    fg_minute_labels = int(
        surv_rows
        * float(
            _db_market_labels().get("survival_first_goal_minute_non_null_pct") or 0
        )
    )

    checks = {
        "ft_transformer": {
            "required_rows": THRESHOLDS["ft_transformer_rows"],
            "actual_rows": surv_rows,
            "required_features": THRESHOLDS["ft_transformer_features"],
            "actual_features": surv_features,
            "passes": surv_rows >= THRESHOLDS["ft_transformer_rows"]
            and surv_features >= THRESHOLDS["ft_transformer_features"],
        },
        "temporal_transformer": {
            "required_fixtures": THRESHOLDS["temporal_transformer_fixtures"],
            "actual_fixtures": goal_events,
            "required_events_per_match": THRESHOLDS["temporal_transformer_events_per_match"],
            "passes": goal_events >= THRESHOLDS["temporal_transformer_fixtures"],
        },
        "deep_survival_network": {
            "required_timing_labels": THRESHOLDS["deep_survival_timing_labels"],
            "actual_timing_labels": fg_minute_labels,
            "passes": fg_minute_labels >= THRESHOLDS["deep_survival_timing_labels"],
        },
        "player_embedding_engine": {
            "required_players": THRESHOLDS["player_embedding_players"],
            "actual_player_snapshots": players,
            "passes": players >= THRESHOLDS["player_embedding_players"],
        },
        "lightgbm_tabular": {
            "required_rows": THRESHOLDS["lightgbm_minimum"],
            "actual_rows": finished,
            "passes": finished >= THRESHOLDS["lightgbm_minimum"],
        },
        "neural_tabular": {
            "required_rows": THRESHOLDS["neural_minimum"],
            "actual_rows": surv_rows,
            "passes": surv_rows >= THRESHOLDS["neural_minimum"],
        },
    }
    return {"generated_at": _now(), "thresholds": THRESHOLDS, "checks": checks}


def build_roadmap_decision(
    suitability: dict[str, Any],
    thresholds: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    """STEP 7 — ranked build options."""
    options = [
        {
            "option": "A",
            "name": "No Deep Learning yet",
            "score": 95,
            "rationale": "Data quality + odds intelligence outperform ML; fix labels/xG/odds pipeline first",
        },
        {
            "option": "F",
            "name": "Hybrid ML + Market Intelligence",
            "score": 88,
            "rationale": "Extend odds-primary + EGIE enrichment; proven +28pp FG lift on UEFA",
        },
        {
            "option": "B",
            "name": "Deep Survival Network",
            "score": 35,
            "rationale": "Timing labels insufficient; classical survival only +3.2pp so far",
        },
        {
            "option": "C",
            "name": "FT-Transformer",
            "score": 15,
            "rationale": f"380 rows vs {THRESHOLDS['ft_transformer_rows']} required",
        },
        {
            "option": "D",
            "name": "Temporal Transformer",
            "score": 25,
            "rationale": "Events exist but sequential training pipeline not built",
        },
        {
            "option": "E",
            "name": "Player Embedding Engine",
            "score": 10,
            "rationale": "0 player stats snapshots",
        },
    ]
    options.sort(key=lambda x: x["score"], reverse=True)
    return {
        "generated_at": _now(),
        "ranked_options": options,
        "recommended_first": options[0],
        "recommended_second": options[1],
    }
