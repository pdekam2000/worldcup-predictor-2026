"""Phase 54H-7 expanded pressure shadow backtest on 150+ fixture dataset."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.pressure_backtest.minute_proxy_audit import run_minute_proxy_audit
from worldcup_predictor.egie.pressure_backtest.pressure_dataset_builder import ARTIFACT_DIR_H7, PressureDatasetBuilder
from worldcup_predictor.egie.pressure_backtest.pressure_feature_builder import PRESSURE_FEATURE_NAMES
from worldcup_predictor.egie.pressure_backtest.pressure_revalidation_runner import PressureRevalidationRunner

ARTIFACT_DIR = ARTIFACT_DIR_H7

_FEATURE_GROUPS = (
    ("pressure_spike_count", ("pressure_spike_count_home", "pressure_spike_count_away")),
    ("pressure_before_first_goal", ("pressure_before_first_goal_home", "pressure_before_first_goal_away")),
    ("pressure_momentum", ("pressure_momentum",)),
    ("pressure_first_15", ("pressure_first_15_home", "pressure_first_15_away")),
    ("pressure_first_30", ("pressure_first_30_home", "pressure_first_30_away")),
    ("pressure_dominance", ("pressure_dominance",)),
    ("pressure_swing", ("pressure_swing",)),
    ("pressure_last_5", ("pressure_last_5_home", "pressure_last_5_away")),
    ("pressure_last_10", ("pressure_last_10_home", "pressure_last_10_away")),
)


def _temporal_split_3way(df: pd.DataFrame, train_frac: float = 0.6, val_frac: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from worldcup_predictor.egie.pressure_backtest.pressure_backtest_runner import _temporal_split

    train, rest = _temporal_split(df, train_frac=train_frac / (train_frac + val_frac + (1 - train_frac - val_frac)))
    if len(rest) < 2:
        return train, rest.iloc[:0], rest
    val_cut = max(1, int(len(rest) * (val_frac / (val_frac + (1 - train_frac - val_frac)))))
    val = rest.iloc[:val_cut]
    test = rest.iloc[val_cut:]
    return train, val, test


def _split_report(df: pd.DataFrame, label_col: str) -> dict[str, Any]:
    train, val, test = _temporal_split_3way(df)
    labeled = df[df[label_col].notna()] if label_col in df.columns else df
    pressure_pct = round(100.0 * float(labeled["pressure_available"].sum()) / max(1, len(labeled)), 2)
    return {
        "train": int(len(train)),
        "validation": int(len(val)),
        "test": int(len(test)),
        "total_labeled": int(labeled[label_col].notna().sum()) if label_col in labeled.columns else len(labeled),
        "pressure_coverage_pct": pressure_pct,
    }


def _classify_feature_groups(pooled: dict[str, float]) -> list[dict[str, Any]]:
    if not pooled:
        return []
    group_scores: dict[str, float] = {}
    for label, members in _FEATURE_GROUPS:
        group_scores[label] = sum(float(pooled.get(m, 0.0)) for m in members)
    max_score = max(group_scores.values()) if group_scores else 1.0
    ranked = sorted(group_scores.items(), key=lambda x: x[1], reverse=True)
    out: list[dict[str, Any]] = []
    for label, score in ranked:
        if score >= max_score * 0.55:
            bucket = "STRONG_POSITIVE"
        elif score >= max_score * 0.25:
            bucket = "WEAK_POSITIVE"
        elif score >= max_score * 0.08:
            bucket = "NEUTRAL"
        else:
            bucket = "HARMFUL"
        out.append({"feature_group": label, "importance_sum": round(score, 6), "classification": bucket})
    return out


def _recommend_h7(
    proxy_audit: dict[str, Any],
    markets: dict[str, dict[str, Any]],
    coverage: dict[str, Any],
) -> str:
    fixtures = int(coverage.get("fixtures_with_pressure") or 0)
    if fixtures < 100:
        return "PRESSURE_NO_VALUE"

    proxy_risk = proxy_audit.get("proxy_risk_verdict")
    comp = proxy_audit.get("comparison") or {}
    true_lift = float(comp.get("true_pressure_lift_after_controlling_minute") or 0.0)

    deltas: list[float] = []
    for section in markets.values():
        for market in section.values():
            d = (market.get("delta_b_vs_a") or {}).get("accuracy")
            if d is not None:
                deltas.append(float(d))
    avg_delta = sum(deltas) / len(deltas) if deltas else 0.0

    inplay_ng = ((markets.get("inplay") or {}).get("next_goal_team") or {}).get("delta_b_vs_a") or {}
    ng_lift = float(inplay_ng.get("accuracy") or 0.0)

    if proxy_risk == "MINUTE_PROXY_RISK_HIGH" and true_lift < 0:
        if avg_delta >= 0.03 and ng_lift >= 0.02:
            return "PRESSURE_MEDIUM_VALUE"
        if avg_delta > 0.01:
            return "PRESSURE_LOW_VALUE"
        return "PRESSURE_NO_VALUE"

    if avg_delta >= 0.05 and true_lift >= 0.02:
        return "PRESSURE_HIGH_VALUE"
    if avg_delta >= 0.02 or ng_lift >= 0.015 or true_lift >= 0.02:
        return "PRESSURE_MEDIUM_VALUE"
    if avg_delta > 0 or ng_lift > 0:
        return "PRESSURE_LOW_VALUE"
    return "PRESSURE_NO_VALUE"


class PressureExpandedRunner:
    """Run full 54H-7 expanded backtest pipeline."""

    def __init__(self) -> None:
        self.dataset_builder = PressureDatasetBuilder()
        self.revalidation = PressureRevalidationRunner()

    def run(self) -> dict[str, Any]:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

        summary = self.dataset_builder.save(ARTIFACT_DIR, phase="54H-7")
        prematch_df = pd.read_parquet(ARTIFACT_DIR / "pressure_prematch_dataset.parquet")
        inplay_df = pd.read_parquet(ARTIFACT_DIR / "pressure_inplay_dataset.parquet")

        from worldcup_predictor.egie.pressure_backtest.pressure_leakage_audit import run_pressure_leakage_audit

        leakage = run_pressure_leakage_audit(ARTIFACT_DIR)
        proxy = run_minute_proxy_audit(inplay_df, output_dir=ARTIFACT_DIR, phase="54H-7")
        backtest = self.revalidation.run(prematch_df, inplay_df, proxy_audit=proxy)
        backtest["phase"] = "54H-7"
        backtest["leakage_audit_status"] = leakage.get("status")

        split_report = {
            "prematch_first_goal_team": _split_report(
                prematch_df[prematch_df["label_first_goal_team"].isin(["home", "away"])],
                "label_first_goal_team",
            ),
            "prematch_goal_range": _split_report(prematch_df, "label_goal_range"),
            "inplay_next_goal_team": _split_report(
                inplay_df[inplay_df["label_next_goal_team"].isin(["home", "away"])],
                "label_next_goal_team",
            ),
            "inplay_goal_minute_bucket": _split_report(inplay_df, "label_goal_minute_bucket"),
        }

        pooled: dict[str, float] = {}
        for section in (backtest.get("markets") or {}).values():
            for market in section.values():
                arm_b = market.get("arm_b_pressure_full") or market.get("arm_b_baseline_plus_pressure") or {}
                for feat, imp in (arm_b.get("feature_importance") or {}).items():
                    if feat in PRESSURE_FEATURE_NAMES:
                        pooled[feat] = pooled.get(feat, 0.0) + float(imp)

        feature_groups = _classify_feature_groups(pooled)
        recommendation = _recommend_h7(proxy, backtest.get("markets") or {}, summary)

        from worldcup_predictor.egie.pressure_backtest.pressure_vs_xg_compare import run_pressure_vs_xg_compare

        xg_compare = run_pressure_vs_xg_compare(prematch_df, inplay_df, output_dir=ARTIFACT_DIR)

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": "54H-7",
            "backtest_only": True,
            "production_changes": False,
            "wde_changes": False,
            "saas_changes": False,
            "dataset_summary": summary,
            "split_report": split_report,
            "leakage_audit": {"status": leakage.get("status"), "all_pass": leakage.get("all_pass")},
            "minute_proxy_audit": {
                "proxy_risk_verdict": proxy.get("proxy_risk_verdict"),
                "comparison": proxy.get("comparison"),
            },
            "markets": backtest.get("markets"),
            "prematch_train_size": backtest.get("prematch_train_size"),
            "prematch_test_size": backtest.get("prematch_test_size"),
            "inplay_train_size": backtest.get("inplay_train_size"),
            "inplay_test_size": backtest.get("inplay_test_size"),
            "feature_importance_groups": feature_groups,
            "feature_importance_raw": backtest.get("feature_importance"),
            "pressure_vs_xg": xg_compare,
            "threshold_fixtures": int(summary.get("fixtures_with_pressure") or 0),
            "recommendation": recommendation,
            "shadow_integration_ready": recommendation in ("PRESSURE_HIGH_VALUE", "PRESSURE_MEDIUM_VALUE"),
        }

        (ARTIFACT_DIR / "expanded_backtest_results.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        (ARTIFACT_DIR / "feature_importance_groups.json").write_text(
            json.dumps(feature_groups, indent=2, default=str), encoding="utf-8"
        )
        (ARTIFACT_DIR / "split_report.json").write_text(
            json.dumps(split_report, indent=2, default=str), encoding="utf-8"
        )
        return result
