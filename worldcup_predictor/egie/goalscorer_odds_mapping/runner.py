"""Phase 54M goalscorer odds mapping orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_ml_shadow.features import load_dataset, prepare_features, split_data
from worldcup_predictor.egie.goalscorer_ml_shadow.trainer import predict_logistic, train_logistic
from worldcup_predictor.egie.goalscorer_odds_mapping.audit import audit_report, scan_cache_odds
from worldcup_predictor.egie.goalscorer_odds_mapping.calibration_study import run_calibration_study
from worldcup_predictor.egie.goalscorer_odds_mapping.comparison import build_comparison_frame, run_comparison
from worldcup_predictor.egie.goalscorer_odds_mapping.mapper import map_all_selections
from worldcup_predictor.egie.goalscorer_odds_mapping.models import VALID_RECOMMENDATIONS

ARTIFACT_DIR = Path("artifacts/phase54m_goalscorer_odds_mapping")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _score_ml_probabilities(dataset: pd.DataFrame) -> pd.DataFrame:
    df = prepare_features(dataset)
    train, val, _test = split_data(df)
    model, scaler = train_logistic(train, "target_anytime")
    scored = df.copy()
    scored["ml_probability"] = predict_logistic(model, scaler, df)
    return scored


def _recommend(
    audit_summary: dict[str, Any],
    mapping_summary: dict[str, Any],
    comparison: dict[str, Any],
    calibration: dict[str, Any],
) -> str:
    fixtures = int(audit_summary.get("fixtures_with_goalscorer_odds") or 0)
    rate = float(mapping_summary.get("mapping_rate") or 0)
    mapped = int(mapping_summary.get("mapped_count") or 0)

    if fixtures < 30:
        return "NEED_MORE_GOALSCORER_ODDS"
    if rate < 0.5 or mapped < 500:
        return "NEED_BETTER_PLAYER_MAPPING"

    metrics = (comparison.get("metrics") or {})
    ml_top3 = (metrics.get("ml_probability") or {}).get("top3_hit", 0)
    odds_top3 = (metrics.get("implied_probability") or {}).get("top3_hit", 0)
    blend_top3 = (metrics.get("ml_odds_blend") or {}).get("top3_hit", 0)

    if odds_top3 < 0.15 and ml_top3 < 0.2:
        return "GOALSCORER_ODDS_NOT_USEFUL"
    if rate >= 0.75 and mapped >= 1500 and (blend_top3 >= ml_top3 or calibration.get("status") == "ok"):
        return "GOALSCORER_ODDS_READY"
    if rate >= 0.6:
        return "GOALSCORER_ODDS_READY" if blend_top3 > ml_top3 else "NEED_BETTER_PLAYER_MAPPING"
    return "NEED_BETTER_PLAYER_MAPPING"


def run_phase54m(artifact_dir: Path | str | None = None) -> dict[str, Any]:
    out = Path(artifact_dir or ARTIFACT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    raw_rows, audit_summary = scan_cache_odds()
    audit = audit_report(raw_rows, audit_summary)

    raw_df = pd.DataFrame([r.to_dict() for r in raw_rows])
    raw_df.to_csv(out / "goalscorer_odds_raw.csv", index=False)

    dataset = load_dataset()
    lineup_df = dataset[["sportmonks_fixture_id", "player_id", "player_name", "team_id", "starter", "target_anytime"]].copy()

    mapped, unmapped, map_summary = map_all_selections(raw_rows, lineup_df)

    mapped_records = []
    raw_lookup = {(r.sportmonks_fixture_id, r.selection_name, r.bookmaker, r.market): r for r in raw_rows}
    for m in mapped:
        d = m.to_dict()
        raw = raw_lookup.get((m.sportmonks_fixture_id, m.selection_name, m.bookmaker, m.market))
        if raw:
            d["label"] = raw.label
            d["timestamp"] = raw.timestamp
            d["finished"] = raw.finished
        mapped_records.append(d)
    mapped_df = pd.DataFrame(mapped_records)
    mapped_df.to_csv(out / "goalscorer_odds_mapped.csv", index=False)
    unmapped_df = pd.DataFrame(unmapped)
    unmapped_df.to_csv(out / "goalscorer_odds_unmapped.csv", index=False)

    full_summary = audit_summary.to_dict()
    full_summary.update({
        "mapped_count": map_summary.mapped_count,
        "unmapped_count": map_summary.unmapped_count,
        "mapping_rate": map_summary.mapping_rate,
        "confidence_high": map_summary.confidence_high,
        "confidence_medium": map_summary.confidence_medium,
        "confidence_low": map_summary.confidence_low,
        "audit": audit,
    })
    (out / "mapping_summary.json").write_text(json.dumps(full_summary, indent=2, default=str), encoding="utf-8")

    ml_scores = _score_ml_probabilities(dataset)
    finished_ids = set(raw_df[raw_df["finished"] == True]["sportmonks_fixture_id"].astype(int).tolist())  # noqa: E712

    comparison_df = build_comparison_frame(
        mapped_df if not mapped_df.empty else pd.DataFrame(),
        dataset,
        ml_scores,
        market_label="Anytime",
    )
    if not comparison_df.empty:
        comparison_df = comparison_df[comparison_df["sportmonks_fixture_id"].isin(finished_ids)]

    comparison = run_comparison(comparison_df)

    val_comparison = pd.DataFrame()
    if not comparison_df.empty:
        val_ids = set(dataset[dataset["split"] == "val"]["sportmonks_fixture_id"].astype(int).tolist())
        val_comparison = comparison_df[comparison_df["sportmonks_fixture_id"].isin(val_ids)]

    calibration = run_calibration_study(comparison_df, val_comparison if not val_comparison.empty else None)

    recommendation = _recommend(
        audit_summary.to_dict(),
        map_summary.to_dict(),
        comparison,
        calibration,
    )

    report = {
        "generated_at": _utc_now(),
        "audit": audit,
        "mapping_summary": full_summary,
        "comparison": comparison,
        "calibration": calibration,
        "recommendation": recommendation,
    }
    (out / "phase54m_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    if recommendation not in VALID_RECOMMENDATIONS:
        report["recommendation"] = "NEED_BETTER_PLAYER_MAPPING"

    return report
