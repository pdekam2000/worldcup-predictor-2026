"""Phase 54O goalscorer bridge orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_bridge.audit import audit_fixture_bridges, merge_player_mapping_audit
from worldcup_predictor.egie.goalscorer_bridge.dataset_v2 import ARTIFACT_DIR, build_dataset_v2
from worldcup_predictor.egie.goalscorer_bridge.edge_analysis import run_edge_analysis
from worldcup_predictor.egie.goalscorer_bridge.fixture_mapper import build_fixture_bridges
from worldcup_predictor.egie.goalscorer_bridge.models import VALID_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_bridge.odds_loader import load_all_bridged_odds
from worldcup_predictor.egie.goalscorer_bridge.player_mapper import load_lineup_df_for_fixtures, map_bridged_odds
from worldcup_predictor.egie.goalscorer_bridge.revalidation import run_revalidation
from worldcup_predictor.egie.goalscorer_ml_shadow.features import load_dataset
from worldcup_predictor.egie.goalscorer_odds_mapping.comparison import build_comparison_frame
from worldcup_predictor.egie.goalscorer_odds_mapping.models import MappedOddsSelection

REPORT_PATH = Path("PHASE_54O_GOALSCORER_BRIDGE_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _attach_labels(mapped: list[MappedOddsSelection], raw_rows: list[Any]) -> pd.DataFrame:
    raw_lookup = {
        (r.sportmonks_fixture_id, r.selection_name, r.bookmaker, r.market): r
        for r in raw_rows
    }
    rows = []
    for m in mapped:
        d = m.to_dict()
        raw = raw_lookup.get((m.sportmonks_fixture_id, m.selection_name, m.bookmaker, m.market))
        d["label"] = raw.label if raw else "Anytime"
        rows.append(d)
    return pd.DataFrame(rows)


def _choose_recommendation(
    fixture_audit: dict[str, Any],
    mapping_rate: float,
    reval: dict[str, Any],
    edge: dict[str, Any],
) -> str:
    mapped = int(fixture_audit.get("mapped") or 0)
    if mapped < 20 or mapping_rate < 0.25:
        return "GOALSCORER_ODDS_BLOCKED"
    if reval.get("status") != "ok":
        return "GOALSCORER_NOT_READY"

    anytime = (reval.get("markets") or {}).get("anytime") or {}
    ranking = anytime.get("ranking") or {}
    ml_top3 = float((ranking.get("ml_only") or {}).get("top3_hit") or 0)
    blend_top3 = float((ranking.get("ml_odds_blend") or {}).get("top3_hit") or 0)
    odds_top3 = float((ranking.get("odds_only") or {}).get("top3_hit") or 0)

    cal = anytime.get("calibration") or {}
    ml_brier = float((cal.get("raw") or {}).get("ml_only", {}).get("brier") or 1.0)
    odds_brier = float((cal.get("raw") or {}).get("odds_only", {}).get("brier") or 1.0)
    blend_brier = float((cal.get("raw") or {}).get("ml_odds_blend", {}).get("brier") or 1.0)

    edge_val = edge.get("edge_value", "LOW")
    ml_wins_ranking = blend_top3 > ml_top3 + 0.02
    odds_calibrates = odds_brier < ml_brier
    blend_calibrates = blend_brier < ml_brier

    if mapped >= 40 and mapping_rate >= 0.45 and (ml_wins_ranking or odds_top3 > 0.4) and blend_calibrates:
        return "GOALSCORER_HIGH_VALUE"
    if mapped >= 25 and mapping_rate >= 0.30 and (ml_wins_ranking or odds_calibrates or edge_val in ("MEDIUM", "HIGH")):
        return "GOALSCORER_MEDIUM_VALUE"
    if mapping_rate < 0.30:
        return "GOALSCORER_ODDS_BLOCKED"
    return "GOALSCORER_NOT_READY"


def run_phase54o() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    bridges = build_fixture_bridges()
    bridge_payload = [b.to_dict() for b in bridges]
    (ARTIFACT_DIR / "fixture_bridge.json").write_text(json.dumps(bridge_payload, indent=2), encoding="utf-8")

    fixture_audit = audit_fixture_bridges(bridges)

    raw_odds = load_all_bridged_odds(bridges)
    sm_ids = sorted({int(b.sportmonks_fixture_id) for b in bridges if b.sportmonks_fixture_id})
    lineup_df = load_lineup_df_for_fixtures(sm_ids)

    mapped, unmapped, mapping_summary, diagnostics = map_bridged_odds(raw_odds, lineup_df, bridges)
    mapped_df = _attach_labels(mapped, raw_odds)

    pd.DataFrame([m.to_dict() for m in mapped]).to_csv(ARTIFACT_DIR / "goalscorer_odds_mapped_bridged.csv", index=False)
    pd.DataFrame(unmapped).to_csv(ARTIFACT_DIR / "goalscorer_odds_unmapped_bridged.csv", index=False)

    audit_payload = merge_player_mapping_audit(fixture_audit, mapping_summary, diagnostics)
    (ARTIFACT_DIR / "bridge_audit.json").write_text(json.dumps(audit_payload, indent=2), encoding="utf-8")

    full_dataset = load_dataset()
    dataset_v2, ds_meta = build_dataset_v2(bridges, mapped)
    if not dataset_v2.empty:
        dataset_v2.to_parquet(ARTIFACT_DIR / "goalscorer_dataset_v2.parquet", index=False)
        dataset_v2.head(5000).to_csv(ARTIFACT_DIR / "goalscorer_dataset_v2.csv", index=False)
    (ARTIFACT_DIR / "dataset_v2_summary.json").write_text(json.dumps(ds_meta, indent=2), encoding="utf-8")

    reval = run_revalidation(dataset_v2, mapped_df, full_dataset=full_dataset)
    (ARTIFACT_DIR / "revalidation.json").write_text(json.dumps(reval, indent=2, default=str), encoding="utf-8")

    # edge analysis on anytime comparison
    edge = {"status": "no_data", "edge_value": "LOW"}
    anytime_comp = pd.DataFrame()
    if not mapped_df.empty and not dataset_v2.empty:
        from worldcup_predictor.egie.goalscorer_bridge.revalidation import _comparison_for_market
        from worldcup_predictor.egie.goalscorer_ml_shadow.features import prepare_features, split_data
        from worldcup_predictor.egie.goalscorer_ml_shadow.trainer import predict_logistic, train_logistic

        train, _, _ = split_data(full_dataset)
        train_f = prepare_features(train)
        test_ids = set(dataset_v2["sportmonks_fixture_id"].astype(int).unique())
        test_f = prepare_features(full_dataset[full_dataset["sportmonks_fixture_id"].isin(test_ids)])
        model, scaler = train_logistic(train_f, "target_anytime")
        ml_scores = test_f[["sportmonks_fixture_id", "player_id"]].copy()
        ml_scores["ml_probability"] = predict_logistic(model, scaler, test_f)
        outcomes = dataset_v2.drop_duplicates(["sportmonks_fixture_id", "player_id"])
        anytime_comp = _comparison_for_market(mapped_df, outcomes, ml_scores, market_label="Anytime", target_col="target_anytime")
        if not anytime_comp.empty:
            edge = run_edge_analysis(anytime_comp)

    (ARTIFACT_DIR / "edge_analysis.json").write_text(json.dumps(edge, indent=2), encoding="utf-8")

    recommendation = _choose_recommendation(
        audit_payload["fixture_bridge"],
        mapping_summary.mapping_rate,
        reval,
        edge,
    )

    report = {
        "generated_at": _utc_now(),
        "phase": "54O",
        "fixture_bridge": audit_payload["fixture_bridge"],
        "player_mapping": audit_payload["player_mapping"],
        "dataset_v2": ds_meta,
        "revalidation": reval,
        "edge_analysis": edge,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase54o_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_report(report, audit_payload, mapping_summary, reval, edge, ds_meta, recommendation)
    return report


def _write_report(
    report: dict[str, Any],
    audit: dict[str, Any],
    mapping_summary: Any,
    reval: dict[str, Any],
    edge: dict[str, Any],
    ds_meta: dict[str, Any],
    recommendation: str,
) -> None:
    fb = audit.get("fixture_bridge") or {}
    anytime = (reval.get("markets") or {}).get("anytime") or {}
    ranking = anytime.get("ranking") or {}
    cal = anytime.get("calibration") or {}
    cal_raw = cal.get("raw") or {}

    def _metric(track: str, key: str) -> str:
        return str((ranking.get(track) or {}).get(key, "n/a"))

    lines = [
        "# PHASE 54O — API-Football Goalscorer Odds Bridge",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}  ",
        "**Mode:** Data Bridge → Mapping Expansion → Revalidation → Report  ",
        "**Status:** Complete — research only  ",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{recommendation}`**",
        "",
        "---",
        "",
        "## Part A — Fixture bridge",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| API-Football GS fixtures | **{fb.get('total_api_gs_fixtures')}** |",
        f"| Mapped (HIGH) | **{fb.get('mapped')}** |",
        f"| Partial (MEDIUM/LOW) | {fb.get('partial')} |",
        f"| Unmapped | {fb.get('unmapped')} |",
        f"| With Sportmonks lineups | {fb.get('with_sportmonks_lineups')} |",
        "",
        "Artifact: `artifacts/phase54o_goalscorer_bridge/fixture_bridge.json`",
        "",
        "## Part B — Team resolution",
        "",
        "Home/away teams resolved via Sportmonks WC cache + `team_names_match` aliases.",
        "",
        "## Part C — Player mapping expansion",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Selections processed | {mapping_summary.selection_count} |",
        f"| **Mapping rate** | **{mapping_summary.mapping_rate:.1%}** |",
        f"| HIGH confidence | {mapping_summary.confidence_high} |",
        f"| MEDIUM confidence | {mapping_summary.confidence_medium} |",
        f"| Unmapped | {mapping_summary.unmapped_count} |",
        "",
        "## Part D — Goalscorer dataset v2",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Rows | {ds_meta.get('rows', 0)} |",
        f"| Fixtures | {ds_meta.get('fixtures', 0)} |",
        f"| Rows with anytime odds | {ds_meta.get('rows_with_anytime_odds', 0)} |",
        "",
        "Artifact: `artifacts/phase54o_goalscorer_bridge/goalscorer_dataset_v2.parquet`",
        "",
        "## Part E — Revalidation (Anytime)",
        "",
        f"| Signal | Top-1 | Top-3 | Top-5 |",
        f"|--------|-------|-------|-------|",
        f"| ML only | {_metric('ml_only', 'top1_hit')} | {_metric('ml_only', 'top3_hit')} | {_metric('ml_only', 'top5_hit')} |",
        f"| Odds only | {_metric('odds_only', 'top1_hit')} | {_metric('odds_only', 'top3_hit')} | {_metric('odds_only', 'top5_hit')} |",
        f"| ML + Odds blend | {_metric('ml_odds_blend', 'top1_hit')} | {_metric('ml_odds_blend', 'top3_hit')} | {_metric('ml_odds_blend', 'top5_hit')} |",
        "",
        "### Calibration",
        "",
        f"| Track | Brier | ECE |",
        f"|-------|-------|-----|",
    ]
    for track in ("ml_only", "odds_only", "ml_odds_blend"):
        t = cal_raw.get(track) or {}
        lines.append(f"| {track} | {t.get('brier', 'n/a')} | {t.get('ece', 'n/a')} |")

    lines.extend(
        [
            "",
            "## Part F — Edge analysis",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Agreement % | {edge.get('agreement_pct', 'n/a')} |",
            f"| Disagreement % | {edge.get('disagreement_pct', 'n/a')} |",
            f"| Disagree-group hit rate | {edge.get('disagree_group_hit_rate', 'n/a')} |",
            f"| **Edge value** | **{edge.get('edge_value', 'LOW')}** |",
            "",
            "## Part G — Decision questions",
            "",
            f"1. **WC fixtures bridged:** {int(fb.get('mapped', 0)) + int(fb.get('partial', 0))} of {fb.get('total_api_gs_fixtures')} (HIGH={fb.get('mapped')})",
            f"2. **Mapping rate:** {mapping_summary.mapping_rate:.1%}",
            f"3. **ML+Odds beats ML alone (top-3):** {float(_metric('ml_odds_blend', 'top3_hit') if _metric('ml_odds_blend', 'top3_hit') != 'n/a' else 0) > float(_metric('ml_only', 'top3_hit') if _metric('ml_only', 'top3_hit') != 'n/a' else 0)}",
            f"4. **Bookmaker adds value:** odds top-3={_metric('odds_only', 'top3_hit')}",
            f"5. **Calibration improved by blend:** blend Brier {cal_raw.get('ml_odds_blend', {}).get('brier', 'n/a')} vs ML {cal_raw.get('ml_only', {}).get('brier', 'n/a')}",
            f"6. **Goalscorer HIGH_VALUE:** {recommendation == 'GOALSCORER_HIGH_VALUE'}",
            "7. **Build next:** fixture-lineup bridge for unmapped 29 fixtures; expand beyond WC; production shadow capture",
            "",
            f"### Final recommendation: **`{recommendation}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No production integration",
            "- No WDE / SaaS / deploy changes",
            "- No live prediction changes",
            "- No EGIE scoring changes",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
