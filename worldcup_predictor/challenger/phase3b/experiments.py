"""Controlled Phase 3B experiment matrix (validation selects; holdout once)."""

from __future__ import annotations

from typing import Any

import numpy as np

from worldcup_predictor.challenger.backtest.splits import chronological_split
from worldcup_predictor.challenger.phase3b.baselines import (
    fit_team_strength,
    league_avg_predict,
    team_strength_predict,
)
from worldcup_predictor.challenger.phase3b.calibration import apply_temperature, fit_temperature
from worldcup_predictor.challenger.phase3b.distributions import goals_to_markets
from worldcup_predictor.challenger.phase3b.enrichment import (
    V1_FEATURE_COLS_MC,
    V1_FEATURE_COLS_NM,
    V2_FEATURE_COLS_MC,
    V2_FEATURE_COLS_NM,
    enrich_rows_chronological,
)
from worldcup_predictor.challenger.phase3b.metrics_ext import evaluate_full


def _matrix(rows: list[dict], cols: list[str]) -> np.ndarray:
    mat = []
    for r in rows:
        f = r["features"]
        mat.append([float(f[c]) if f.get(c) is not None else np.nan for c in cols])
    return np.asarray(mat, dtype=float)


def _impute(X: np.ndarray, med: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    X = X.copy()
    if med is None:
        med = np.nanmedian(X, axis=0)
        med = np.where(np.isnan(med), 0.0, med)
    inds = np.where(np.isnan(X))
    X[inds] = np.take(med, inds[1])
    return X, med


def _fit_gbm(train: list[dict], cols: list[str], backend: str = "lightgbm"):
    X, med = _impute(_matrix(train, cols))
    yh = np.asarray([r["home_goals"] for r in train], dtype=float)
    ya = np.asarray([r["away_goals"] for r in train], dtype=float)
    if backend == "lightgbm":
        try:
            import lightgbm as lgb

            mh = lgb.LGBMRegressor(
                n_estimators=80,
                learning_rate=0.05,
                num_leaves=15,
                min_child_samples=20,
                subsample=0.85,
                colsample_bytree=0.85,
                reg_lambda=1.0,
                random_state=42,
                verbosity=-1,
            )
            ma = lgb.LGBMRegressor(
                n_estimators=80,
                learning_rate=0.05,
                num_leaves=15,
                min_child_samples=20,
                subsample=0.85,
                colsample_bytree=0.85,
                reg_lambda=1.0,
                random_state=42,
                verbosity=-1,
            )
            mh.fit(X, yh)
            ma.fit(X, ya)
            return {"backend": "lightgbm", "mh": mh, "ma": ma, "med": med, "cols": cols}
        except Exception:
            backend = "sklearn_hist"
    from sklearn.ensemble import HistGradientBoostingRegressor

    mh = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=80, min_samples_leaf=20, random_state=42)
    ma = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=80, min_samples_leaf=20, random_state=42)
    mh.fit(X, yh)
    ma.fit(X, ya)
    return {"backend": "sklearn_hist", "mh": mh, "ma": ma, "med": med, "cols": cols}


def _predict_gbm(model: dict, rows: list[dict], *, family: str = "independent_poisson") -> list[dict]:
    X, _ = _impute(_matrix(rows, model["cols"]), model["med"])
    yh = np.clip(model["mh"].predict(X), 0.05, 6.0)
    ya = np.clip(model["ma"].predict(X), 0.05, 6.0)
    return [goals_to_markets(float(h), float(a), family=family) for h, a in zip(yh, ya)]


def _split_sets(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict], Any]:
    split = chronological_split(rows)
    by_id = {r["fixture_id"]: r for r in rows}
    train = [by_id[i] for i in split.train_ids if i in by_id]
    val = [by_id[i] for i in split.validation_ids if i in by_id]
    hold = [by_id[i] for i in split.holdout_ids if i in by_id]
    return train, val, hold, split


def run_experiment_matrix(rows_nm: list[dict], rows_mc: list[dict] | None = None) -> dict[str, Any]:
    """
    Experiments A–H. Selection uses validation LogLoss; holdout evaluated once per candidate.
    """
    rows_nm = enrich_rows_chronological(rows_nm)
    rows_mc = enrich_rows_chronological(rows_mc) if rows_mc else rows_nm

    train, val, hold, split = _split_sets(rows_nm)
    train_mc, val_mc, hold_mc, _ = _split_sets(rows_mc)

    results: dict[str, Any] = {
        "split": {
            "method": split.method,
            "train_n": len(train),
            "validation_n": len(val),
            "holdout_n": len(hold),
            "train_end": split.train_end,
            "validation_end": split.validation_end,
            "holdout_end": split.holdout_end,
        },
        "experiments": {},
    }

    # A — League baseline
    a_val = [league_avg_predict(train, r) for r in val]
    a_hold = [league_avg_predict(train, r) for r in hold]
    results["experiments"]["A"] = {
        "name": "League baseline",
        "features": "league only",
        "market": False,
        "distribution": "independent_poisson",
        "validation": evaluate_full(val, a_val),
        "holdout": evaluate_full(hold, a_hold),
    }

    # B — Team strength
    strength = fit_team_strength(train)
    b_val = [team_strength_predict(strength, r) for r in val]
    b_hold = [team_strength_predict(strength, r) for r in hold]
    results["experiments"]["B"] = {
        "name": "Team strength baseline",
        "features": "attack/defence",
        "market": False,
        "distribution": "independent_poisson",
        "validation": evaluate_full(val, b_val),
        "holdout": evaluate_full(hold, b_hold),
    }

    # C — GBGM-NM-v1 (current features, regularized)
    m_c = _fit_gbm(train, V1_FEATURE_COLS_NM)
    c_val = _predict_gbm(m_c, val)
    c_hold = _predict_gbm(m_c, hold)
    results["experiments"]["C"] = {
        "name": "GBGM-NM-v1",
        "features": "current",
        "market": False,
        "distribution": "independent_poisson",
        "backend": m_c["backend"],
        "validation": evaluate_full(val, c_val),
        "holdout": evaluate_full(hold, c_hold),
    }

    # D — GBGM-NM-v2 improved features
    m_d = _fit_gbm(train, V2_FEATURE_COLS_NM)
    d_val = _predict_gbm(m_d, val)
    d_hold = _predict_gbm(m_d, hold)
    results["experiments"]["D"] = {
        "name": "GBGM-NM-v2",
        "features": "improved",
        "market": False,
        "distribution": "independent_poisson",
        "backend": m_d["backend"],
        "validation": evaluate_full(val, d_val),
        "holdout": evaluate_full(hold, d_hold),
    }

    # E — GBGM-MC-v1
    m_e = _fit_gbm(train_mc, V1_FEATURE_COLS_MC)
    e_val = _predict_gbm(m_e, val_mc)
    e_hold = _predict_gbm(m_e, hold_mc)
    results["experiments"]["E"] = {
        "name": "GBGM-MC-v1",
        "features": "current",
        "market": True,
        "distribution": "independent_poisson",
        "backend": m_e["backend"],
        "validation": evaluate_full(val_mc, e_val),
        "holdout": evaluate_full(hold_mc, e_hold),
    }

    # F — GBGM-MC-v2
    m_f = _fit_gbm(train_mc, V2_FEATURE_COLS_MC)
    f_val = _predict_gbm(m_f, val_mc)
    f_hold = _predict_gbm(m_f, hold_mc)
    results["experiments"]["F"] = {
        "name": "GBGM-MC-v2",
        "features": "improved",
        "market": True,
        "distribution": "independent_poisson",
        "backend": m_f["backend"],
        "validation": evaluate_full(val_mc, f_val),
        "holdout": evaluate_full(hold_mc, f_hold),
    }

    # Pick best NM/MC by validation logloss among C/D/E/F (+B as candidate)
    candidates = []
    for key in ("B", "C", "D", "E", "F"):
        exp = results["experiments"][key]
        ll = exp["validation"].get("logloss_1x2")
        if ll is not None:
            candidates.append((ll, key, exp))
    candidates.sort(key=lambda t: t[0])
    best_key = candidates[0][1] if candidates else "B"
    best_exp = results["experiments"][best_key]

    # Rebuild best preds for G/H distributions
    if best_key == "B":
        base_val = b_val
        base_hold = b_hold
        base_rows_val, base_rows_hold = val, hold
    elif best_key == "C":
        base_val, base_hold = c_val, c_hold
        base_rows_val, base_rows_hold = val, hold
    elif best_key == "D":
        base_val, base_hold = d_val, d_hold
        base_rows_val, base_rows_hold = val, hold
    elif best_key == "E":
        base_val, base_hold = e_val, e_hold
        base_rows_val, base_rows_hold = val_mc, hold_mc
    else:
        base_val, base_hold = f_val, f_hold
        base_rows_val, base_rows_hold = val_mc, hold_mc

    def _regrid(preds: list[dict], family: str) -> list[dict]:
        return [
            goals_to_markets(p["expected_home_goals"], p["expected_away_goals"], family=family)
            for p in preds
        ]

    g_val = _regrid(base_val, "dixon_coles")
    g_hold = _regrid(base_hold, "dixon_coles")
    results["experiments"]["G"] = {
        "name": f"Best ({best_key}) + Dixon–Coles",
        "features": "best",
        "market": best_exp.get("market"),
        "distribution": "dixon_coles",
        "base_experiment": best_key,
        "validation": evaluate_full(base_rows_val, g_val),
        "holdout": evaluate_full(base_rows_hold, g_hold),
    }

    h_val = _regrid(base_val, "bivariate_poisson")
    h_hold = _regrid(base_hold, "bivariate_poisson")
    results["experiments"]["H"] = {
        "name": f"Best ({best_key}) + Bivariate Poisson",
        "features": "best",
        "market": best_exp.get("market"),
        "distribution": "bivariate_poisson",
        "base_experiment": best_key,
        "validation": evaluate_full(base_rows_val, h_val),
        "holdout": evaluate_full(base_rows_hold, h_hold),
    }

    # Calibration on best Poisson candidate (validation-only T)
    t = fit_temperature(base_rows_val, base_val)
    cal_val = [apply_temperature(p, t) for p in base_val]
    cal_hold = [apply_temperature(p, t) for p in base_hold]
    results["calibration"] = {
        "method": "temperature",
        "T": t,
        "base_experiment": best_key,
        "validation_pre": evaluate_full(base_rows_val, base_val),
        "validation_post": evaluate_full(base_rows_val, cal_val),
        "holdout_pre": evaluate_full(base_rows_hold, base_hold),
        "holdout_post": evaluate_full(base_rows_hold, cal_hold),
        "note": "Temperature fitted on validation only; holdout reported once for transparency",
    }

    # Final selection among A–H + calibrated by validation logloss (calibrated uses post)
    selection_pool = []
    for key, exp in results["experiments"].items():
        ll = exp["validation"].get("logloss_1x2")
        if ll is not None:
            selection_pool.append((ll, key, False))
    ll_cal = results["calibration"]["validation_post"].get("logloss_1x2")
    if ll_cal is not None:
        selection_pool.append((ll_cal, f"{best_key}+temp", True))
    selection_pool.sort(key=lambda t: t[0])
    chosen_ll, chosen_id, is_cal = selection_pool[0]
    if is_cal:
        chosen_hold = results["calibration"]["holdout_post"]
        chosen_val = results["calibration"]["validation_post"]
        chosen_name = f"{best_key} temperature-calibrated"
    else:
        chosen_hold = results["experiments"][chosen_id]["holdout"]
        chosen_val = results["experiments"][chosen_id]["validation"]
        chosen_name = results["experiments"][chosen_id]["name"]

    league_hold_ll = results["experiments"]["A"]["holdout"]["logloss_1x2"]
    league_hold_brier = results["experiments"]["A"]["holdout"]["brier_1x2"]
    gbgm_v1_hold_ll = results["experiments"]["C"]["holdout"]["logloss_1x2"]

    beats_league = (chosen_hold.get("logloss_1x2") is not None and chosen_hold["logloss_1x2"] < league_hold_ll) or (
        chosen_hold.get("brier_1x2") is not None and chosen_hold["brier_1x2"] < league_hold_brier
    )
    beats_gbgm1 = chosen_hold.get("logloss_1x2") is not None and chosen_hold["logloss_1x2"] < gbgm_v1_hold_ll

    results["selection"] = {
        "chosen_by_validation": chosen_id,
        "chosen_name": chosen_name,
        "validation_logloss": chosen_ll,
        "holdout_metrics": chosen_hold,
        "validation_metrics": chosen_val,
        "beats_league_baseline_holdout": beats_league,
        "beats_gbgm_v1_holdout": beats_gbgm1,
        "league_holdout_logloss": league_hold_ll,
        "gbgm_v1_holdout_logloss": gbgm_v1_hold_ll,
    }
    results["_models"] = {"D": m_d, "F": m_f, "strength": strength, "best_key": best_key}
    return results


def run_ablation(train: list[dict], val: list[dict], hold: list[dict]) -> dict[str, Any]:
    """Feature-group ablation on NM-v2 using validation for ranking; holdout reported."""
    groups = {
        "full": V2_FEATURE_COLS_NM,
        "remove_elo": [c for c in V2_FEATURE_COLS_NM if not c.startswith("elo")],
        "remove_form": [
            c
            for c in V2_FEATURE_COLS_NM
            if c
            not in {
                "home_goals_for_avg_l5",
                "home_goals_against_avg_l5",
                "away_goals_for_avg_l5",
                "away_goals_against_avg_l5",
                "home_att_rel_l5",
                "home_def_rel_l5",
                "away_att_rel_l5",
                "away_def_rel_l5",
            }
        ],
        "remove_league": [c for c in V2_FEATURE_COLS_NM if not c.startswith("comp__") and not c.startswith("league_")],
        "remove_opponent_adj": [
            c
            for c in V2_FEATURE_COLS_NM
            if c
            not in {
                "home_att_expanding",
                "home_def_expanding",
                "away_att_expanding",
                "away_def_expanding",
                "lambda_proxy_home",
                "lambda_proxy_away",
            }
        ],
        "remove_home_away_split": [
            c
            for c in V2_FEATURE_COLS_NM
            if c
            not in {
                "home_goals_for_avg_l5",
                "home_goals_against_avg_l5",
                "away_goals_for_avg_l5",
                "away_goals_against_avg_l5",
            }
        ],
    }
    out = {}
    for name, cols in groups.items():
        if len(cols) < 4:
            out[name] = {"skipped": True, "reason": "too_few_cols", "n_cols": len(cols)}
            continue
        m = _fit_gbm(train, cols)
        vp = _predict_gbm(m, val)
        hp = _predict_gbm(m, hold)
        out[name] = {
            "n_cols": len(cols),
            "validation": evaluate_full(val, vp),
            "holdout": evaluate_full(hold, hp),
        }
    return out


def run_domain_breakdown(rows: list[dict]) -> dict[str, Any]:
    rows = enrich_rows_chronological(rows)
    domains = {
        "global": rows,
        "premier_league": [r for r in rows if r["competition_key"] == "premier_league"],
        "bundesliga": [r for r in rows if r["competition_key"] == "bundesliga"],
        "tier_a_domestic": [r for r in rows if r["competition_key"] in {"premier_league", "bundesliga"}],
        "international": [r for r in rows if r["competition_key"] in {"world_cup_2026", "champions_league"}],
        "high_data": [r for r in rows if r["competition_key"] in {"premier_league", "bundesliga"}],
        "low_data": [r for r in rows if r["competition_key"] in {"world_cup_2026", "champions_league"}],
    }
    out = {}
    for name, subset in domains.items():
        if len(subset) < 80:
            out[name] = {"ok": False, "reason": "insufficient_rows", "n": len(subset)}
            continue
        train, val, hold, split = _split_sets(subset)
        strength = fit_team_strength(train)
        a_hold = [league_avg_predict(train, r) for r in hold]
        b_hold = [team_strength_predict(strength, r) for r in hold]
        m = _fit_gbm(train, V2_FEATURE_COLS_NM)
        d_hold = _predict_gbm(m, hold)
        out[name] = {
            "ok": True,
            "n": len(subset),
            "split": {"train_n": len(train), "validation_n": len(val), "holdout_n": len(hold)},
            "league_avg_holdout": evaluate_full(hold, a_hold),
            "team_strength_holdout": evaluate_full(hold, b_hold),
            "gbgm_v2_holdout": evaluate_full(hold, d_hold),
            "missingness": {
                "mean_form_missing_rate": sum(float(r["features"].get("form_missing_rate") or 0) for r in subset) / len(subset),
                "low_coverage_share": sum(1 for r in subset if r["features"].get("coverage_bucket") == "LOW_COVERAGE") / len(subset),
            },
        }
    return out
