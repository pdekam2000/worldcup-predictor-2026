"""Compare pressure vs xG feature families on shared EGIE shadow markets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.pressure_backtest.minute_proxy_audit import _eval_with_bootstrap
from worldcup_predictor.egie.pressure_backtest.pressure_backtest_runner import _delta, _temporal_split
from worldcup_predictor.egie.pressure_backtest.pressure_feature_builder import PRESSURE_FEATURE_NAMES
from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import BASELINE_COLS
from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XG_FEATURE_NAMES, XgFeatureBuilder


def _attach_xg_features(df: pd.DataFrame, xg_feats: dict[int, dict[str, Any]]) -> pd.DataFrame:
    out = df.copy()
    for col in XG_FEATURE_NAMES:
        out[col] = out["sportmonks_fixture_id"].map(lambda fid: xg_feats.get(int(fid), {}).get(col))
    out["xg_available"] = out["sportmonks_fixture_id"].map(
        lambda fid: bool(xg_feats.get(int(fid), {}).get("xg_available"))
    )
    return out


def _team_goals_bucket(row: pd.Series) -> str:
    total = int(row.get("label_total_goals") or 0)
    if total <= 1:
        return "0-1"
    if total <= 3:
        return "2-3"
    return "4+"


def run_pressure_vs_xg_compare(
    prematch_df: pd.DataFrame,
    inplay_df: pd.DataFrame,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    xg_builder = XgFeatureBuilder()
    summaries = xg_builder.load_ordered_summaries()
    xg_feats = xg_builder.build_chronological_features(summaries)

    pm = _attach_xg_features(prematch_df, xg_feats)
    ip = _attach_xg_features(inplay_df, xg_feats)

    pm_train, pm_test = _temporal_split(pm)
    ip_train, ip_test = _temporal_split(ip)

    baseline = [c for c in BASELINE_COLS if c in pm.columns]
    pressure_cols = [c for c in PRESSURE_FEATURE_NAMES if c in pm.columns]
    xg_cols = [c for c in XG_FEATURE_NAMES if c in pm.columns]

    fg_train = pm_train[pm_train["label_first_goal_team"].isin(["home", "away"])].copy()
    fg_test = pm_test[pm_test["label_first_goal_team"].isin(["home", "away"])].copy()
    fg_train["label_fg_binary"] = (fg_train["label_first_goal_team"] == "home").astype(int)
    fg_test["label_fg_binary"] = (fg_test["label_first_goal_team"] == "home").astype(int)

    ng_train = ip_train[ip_train["label_next_goal_team"].isin(["home", "away"])].copy()
    ng_test = ip_test[ip_test["label_next_goal_team"].isin(["home", "away"])].copy()
    ng_train["label_ng_binary"] = (ng_train["label_next_goal_team"] == "home").astype(int)
    ng_test["label_ng_binary"] = (ng_test["label_next_goal_team"] == "home").astype(int)

    tg_train = pm_train.copy()
    tg_test = pm_test.copy()
    tg_train["label_team_goals_bucket"] = tg_train.apply(_team_goals_bucket, axis=1)
    tg_test["label_team_goals_bucket"] = tg_test.apply(_team_goals_bucket, axis=1)

    def _compare_block(train: pd.DataFrame, test: pd.DataFrame, label_col: str, *, multiclass: bool, binary_col: str | None = None) -> dict[str, Any]:
        use_col = binary_col or label_col
        sub_train = train[train.get("xg_available", False) == True]  # noqa: E712
        sub_test = test[test.get("xg_available", False) == True]  # noqa: E712
        sub_train = sub_train[sub_train.get("pressure_available", False) == True]  # noqa: E712
        sub_test = sub_test[sub_test.get("pressure_available", False) == True]  # noqa: E712
        pressure_arm = _eval_with_bootstrap(
            sub_train, sub_test, baseline + pressure_cols, use_col, multiclass=multiclass, require_pressure=True
        )
        xg_arm = _eval_with_bootstrap(
            sub_train, sub_test, baseline + xg_cols, use_col, multiclass=multiclass, require_pressure=True
        )
        both_arm = _eval_with_bootstrap(
            sub_train,
            sub_test,
            baseline + pressure_cols + xg_cols,
            use_col,
            multiclass=multiclass,
            require_pressure=True,
        )
        return {
            "shared_samples_test": int((both_arm or {}).get("test_n") or 0),
            "pressure_baseline_plus_pressure": pressure_arm,
            "xg_baseline_plus_xg": xg_arm,
            "baseline_plus_both": both_arm,
            "delta_pressure_vs_xg_accuracy": _delta(xg_arm, pressure_arm).get("accuracy"),
            "stronger_family": (
                "pressure"
                if float((pressure_arm or {}).get("accuracy") or 0) > float((xg_arm or {}).get("accuracy") or 0)
                else "xg"
                if float((xg_arm or {}).get("accuracy") or 0) > float((pressure_arm or {}).get("accuracy") or 0)
                else "tie"
            ),
        }

    markets = {
        "first_goal_team": _compare_block(fg_train, fg_test, "label_first_goal_team", multiclass=False, binary_col="label_fg_binary"),
        "goal_range": _compare_block(pm_train, pm_test, "label_goal_range", multiclass=True),
        "team_goals": _compare_block(tg_train, tg_test, "label_team_goals_bucket", multiclass=True),
        "next_goal_team": _compare_block(ng_train, ng_test, "label_next_goal_team", multiclass=False, binary_col="label_ng_binary"),
    }

    wins = {"pressure": 0, "xg": 0, "tie": 0}
    for m in markets.values():
        fam = m.get("stronger_family")
        if fam in wins:
            wins[fam] += 1

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "54H-7",
        "markets": markets,
        "summary": {
            "pressure_wins": wins["pressure"],
            "xg_wins": wins["xg"],
            "ties": wins["tie"],
            "overall_stronger": max(wins, key=wins.get),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pressure_vs_xg_compare.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out
