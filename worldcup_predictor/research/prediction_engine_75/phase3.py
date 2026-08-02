"""
PREDICTION_ENGINE_75 — Phase 3: Specialist models + Meta ensemble.

Research/shadow only. Mixture-of-experts over failure regimes.
Does not open Phase-1 sealed holdout. Does not modify Canonical/WDE/ECSE.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from worldcup_predictor.research.prediction_engine_75 import phase1 as p1
from worldcup_predictor.research.prediction_engine_75 import phase2 as p2

ROOT = Path(__file__).resolve().parents[3]
PHASE = "PHASE3_SPECIALIST_MODELS_META_ENSEMBLE"
STATUS_COMPLETE = "PHASE3_SPECIALIST_MODELS_COMPLETE"
STATUS_LIMITED = "PHASE3_DATA_LIMITED"
STATUS_FAILED = "PHASE3_VALIDATION_FAILED"
SEED = 20260802

REGIMES = [
    "Favorite_Failure",
    "Underdog_Breakout",
    "Draw_Underranked",
    "Direction_Reversal",
    "Market_Contradiction",
    "Low_Goal_Surprise",
    "High_Goal_Explosion",
    "Late_Goal_Pattern",
    "League_Specific_Drift",
    "Unknown",
]

SPECIALISTS = [
    "Favorite_Specialist",
    "Draw_Specialist",
    "Underdog_Specialist",
    "Balanced_Odds_Specialist",
    "Heavy_Favorite_Specialist",
    "Low_Goal_Specialist",
    "High_Goal_Specialist",
    "League_Specialist",
    "Market_Contradiction_Detector",
    "Upset_Risk_Detector",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    p2._write_csv(path, rows, fields)


# ---------------------------------------------------------------------------
# Feature vectors / helpers
# ---------------------------------------------------------------------------


def _goals(r: p2.RowV2) -> tuple[int | None, int | None]:
    sc = str(r.final_score or "")
    if "-" not in sc:
        return None, None
    try:
        a, b = sc.replace(" ", "").split("-", 1)
        return int(a), int(b)
    except ValueError:
        return None, None


def feature_vector(r: p2.RowV2) -> list[float]:
    fav_odds = None
    if r.odds_home and r.odds_draw and r.odds_away:
        fav_odds = min(r.odds_home, r.odds_draw, r.odds_away)
    return [
        float(r.home_p or 0.0),
        float(r.draw_p or 0.0),
        float(r.away_p or 0.0),
        float((r.confidence or 0.0) / 100.0),
        float(r.top5_mass or 0.0),
        float(r.top10_mass or 0.0),
        float(r.entropy or 0.0),
        float(r.lambda_home or 0.0),
        float(r.lambda_away or 0.0),
        float(r.ecse_h_mass or 0.0),
        float(r.ecse_d_mass or 0.0),
        float(r.ecse_a_mass or 0.0),
        float(r.implied_home or 0.0),
        float(r.implied_draw or 0.0),
        float(r.implied_away or 0.0),
        float(r.book_margin or 0.0),
        float(r.favorite_strength or 0.0),
        1.0 if r.balanced_market else 0.0,
        float(fav_odds or 0.0),
        float((r.lambda_home or 0.0) + (r.lambda_away or 0.0)),
        abs(float(r.lambda_home or 0.0) - float(r.lambda_away or 0.0)),
        1.0 if r.wde_decision and r.ecse_direction and r.wde_decision != r.ecse_direction else 0.0,
        1.0 if r.no_bet else 0.0,
    ]


FEATURE_NAMES = [
    "home_p",
    "draw_p",
    "away_p",
    "confidence_norm",
    "top5_mass",
    "top10_mass",
    "entropy",
    "lambda_home",
    "lambda_away",
    "ecse_h_mass",
    "ecse_d_mass",
    "ecse_a_mass",
    "implied_home",
    "implied_draw",
    "implied_away",
    "book_margin",
    "favorite_strength",
    "balanced_market",
    "fav_odds",
    "lambda_total",
    "lambda_diff",
    "wde_ecse_conflict",
    "no_bet",
]


def label_idx(y: str) -> int:
    return {"home": 0, "draw": 1, "away": 2}[y]


def idx_label(i: int) -> str:
    return ["home", "draw", "away"][int(i)]


# ---------------------------------------------------------------------------
# Error regimes
# ---------------------------------------------------------------------------


def tag_regimes(r: p2.RowV2) -> list[str]:
    """Tag miss regimes for a fixture using WDE decision vs actual (prematch features only for patterns)."""
    pred = r.wde_decision
    if not pred or not r.actual_1x2 or pred == r.actual_1x2:
        return []
    tags: list[str] = []
    fav = p2.market_fav(r)
    hg, ag = _goals(r)
    total = (hg + ag) if hg is not None and ag is not None else None
    if r.actual_1x2 == "draw":
        tags.append("Draw_Underranked")
    if fav and pred == fav:
        tags.append("Favorite_Failure")
    if fav and r.actual_1x2 != fav:
        tags.append("Underdog_Breakout")
    if r.ecse_direction and r.ecse_direction != pred:
        tags.append("Direction_Reversal")
    if fav and pred != fav:
        tags.append("Market_Contradiction")
    if total is not None and total <= 1 and (r.lambda_home or 0) + (r.lambda_away or 0) >= 2.2:
        tags.append("Low_Goal_Surprise")
    if total is not None and total >= 4 and (r.lambda_home or 0) + (r.lambda_away or 0) <= 2.4:
        tags.append("High_Goal_Explosion")
    # Late-goal pattern not available prematch — mark only if HT score present later; else unavailable
    # Without HT data we do not invent Late_Goal_Pattern
    if not tags:
        tags.append("Unknown")
    return tags


def discover_error_regimes(rows: list[p2.RowV2]) -> dict[str, Any]:
    buckets: dict[str, list[p2.RowV2]] = {k: [] for k in REGIMES}
    league_miss: dict[str, list[p2.RowV2]] = defaultdict(list)
    for r in rows:
        tags = tag_regimes(r)
        for t in tags:
            if t in buckets:
                buckets[t].append(r)
        if tags and r.league:
            league_miss[r.league or "?"].append(r)

    # League-specific drift: leagues with miss rate >> overall
    overall_miss = sum(1 for r in rows if r.wde_decision and r.actual_1x2 and r.wde_decision != r.actual_1x2)
    overall_rate = overall_miss / len(rows) if rows else 0
    for lg, miss_rows in league_miss.items():
        lg_n = sum(1 for r in rows if r.league == lg)
        if lg_n >= 8 and (len(miss_rows) / lg_n) >= overall_rate + 0.15:
            buckets["League_Specific_Drift"].extend(miss_rows)

    regimes_out = {}
    for name, rs in buckets.items():
        # unique by fixture
        uniq: dict[int, p2.RowV2] = {r.fixture_id: r for r in rs}
        rs = list(uniq.values())
        n = len(rs)
        # within regime, "accuracy" of WDE is 0 by construction for miss buckets; report baseline-on-regime after flip diagnostics
        confs = [r.confidence for r in rs if r.confidence is not None]
        odds = []
        pnls = []
        for r in rs:
            d = r.wde_decision
            o = p1._safe_odds({"home": r.odds_home, "draw": r.odds_draw, "away": r.odds_away}.get(d or ""))
            if o:
                odds.append(o)
                pnls.append(-1.0)  # all misses
        lamb_h = [r.lambda_home for r in rs if r.lambda_home is not None]
        lamb_a = [r.lambda_away for r in rs if r.lambda_away is not None]
        regimes_out[name] = {
            "n": n,
            "wde_accuracy_on_regime": 0.0 if n and name != "Late_Goal_Pattern" else None,
            "mean_confidence": round(sum(confs) / len(confs), 3) if confs else None,
            "avg_odds": round(sum(odds) / len(odds), 4) if odds else None,
            "roi_if_bet_wde": round(sum(pnls) / len(pnls), 4) if pnls else None,
            "common_leagues": [x for x, _ in Counter(r.league or "?" for r in rs).most_common(5)],
            "common_lambda_home_mean": round(sum(lamb_h) / len(lamb_h), 4) if lamb_h else None,
            "common_lambda_away_mean": round(sum(lamb_a) / len(lamb_a), 4) if lamb_a else None,
            "common_ecse_pattern": dict(Counter(r.ecse_direction or "?" for r in rs).most_common(3)),
            "common_wde_pattern": dict(Counter(r.wde_decision or "?" for r in rs).most_common(3)),
            "common_features": {
                "mean_draw_p": round(sum(r.draw_p or 0 for r in rs) / n, 4) if n else None,
                "mean_top5_mass": round(sum(r.top5_mass or 0 for r in rs) / n, 4) if n else None,
                "mean_entropy": round(sum(r.entropy or 0 for r in rs) / n, 4) if n else None,
                "balanced_share": round(sum(1 for r in rs if r.balanced_market) / n, 4) if n else None,
            },
            "note": (
                "Late_Goal_Pattern unavailable without prematch HT/event features"
                if name == "Late_Goal_Pattern"
                else None
            ),
        }
    regimes_out["Late_Goal_Pattern"]["n"] = 0
    regimes_out["Late_Goal_Pattern"]["status"] = "UNAVAILABLE_NO_PREMATCH_EVENT_FEATURES"
    return {"regimes": regimes_out, "overall_miss_rate": round(overall_rate, 4), "n_rows": len(rows)}


# ---------------------------------------------------------------------------
# Specialists
# ---------------------------------------------------------------------------


@dataclass
class SpecialistSpec:
    name: str
    eligibility: str
    min_train_n: int = 20


def eligible(name: str, r: p2.RowV2) -> bool:
    fav = p2.market_fav(r)
    fav_odds = min([o for o in (r.odds_home, r.odds_draw, r.odds_away) if o], default=None)
    lam_tot = (r.lambda_home or 0) + (r.lambda_away or 0)
    if name == "Favorite_Specialist":
        return fav is not None and fav_odds is not None and fav_odds <= 2.2
    if name == "Heavy_Favorite_Specialist":
        return fav_odds is not None and fav_odds <= 1.45
    if name == "Draw_Specialist":
        return bool(r.balanced_market) or ((r.draw_p or 0) >= 0.28) or (
            fav_odds is not None and 1.9 <= fav_odds <= 2.6
        )
    if name == "Underdog_Specialist":
        return fav_odds is not None and fav_odds <= 1.9 and (r.confidence or 100) < 62
    if name == "Balanced_Odds_Specialist":
        return bool(r.balanced_market)
    if name == "Low_Goal_Specialist":
        return lam_tot > 0 and lam_tot <= 2.2
    if name == "High_Goal_Specialist":
        return lam_tot >= 2.8
    if name == "League_Specialist":
        return True  # hierarchical prior via league one-hot proxy = league miss rate features already in vector? use all
    if name == "Market_Contradiction_Detector":
        return fav is not None and r.wde_decision is not None and fav != r.wde_decision
    if name == "Upset_Risk_Detector":
        return fav_odds is not None and fav_odds <= 1.7
    return False


def specialist_target_direction(name: str, r: p2.RowV2) -> str | None:
    """Default prediction direction prior used when model abstains / for routing baselines."""
    fav = p2.market_fav(r)
    if name in {"Favorite_Specialist", "Heavy_Favorite_Specialist"}:
        return fav or r.wde_decision
    if name == "Draw_Specialist":
        return "draw"
    if name in {"Underdog_Specialist", "Upset_Risk_Detector"}:
        if not fav:
            return r.wde_decision
        odds = sorted(
            [(k, v) for k, v in (("home", r.odds_home), ("draw", r.odds_draw), ("away", r.odds_away)) if v],
            key=lambda x: x[1],
        )
        return odds[1][0] if len(odds) > 1 else r.wde_decision
    if name == "Balanced_Odds_Specialist":
        return "draw" if (r.draw_p or 0) >= max(r.home_p or 0, r.away_p or 0) else (r.wde_decision)
    if name == "Low_Goal_Specialist":
        # lean toward draw / low-score side = WDE but boost draw if lambdas close
        if abs((r.lambda_home or 0) - (r.lambda_away or 0)) < 0.25:
            return "draw"
        return r.wde_decision
    if name == "High_Goal_Specialist":
        return p2.prob_argmax(r) or r.wde_decision
    if name == "Market_Contradiction_Detector":
        return fav  # trust market when contradiction
    if name == "League_Specialist":
        return r.wde_decision
    return r.wde_decision


@dataclass
class FittedSpecialist:
    name: str
    model: Any
    train_n: int
    classes: list[str]
    feature_importance: dict[str, float]
    status: str
    note: str = ""


def fit_specialist(name: str, train: list[p2.RowV2]) -> FittedSpecialist:
    elig = [r for r in train if eligible(name, r) and r.actual_1x2 in {"home", "draw", "away"}]
    if len(elig) < 15:
        return FittedSpecialist(
            name=name,
            model=None,
            train_n=len(elig),
            classes=[],
            feature_importance={},
            status="DATA_LIMITED",
            note=f"eligible_train_n={len(elig)} < 15",
        )
    X = np.array([feature_vector(r) for r in elig], dtype=float)
    y = np.array([r.actual_1x2 for r in elig])
    # Need at least 2 classes
    if len(set(y)) < 2:
        return FittedSpecialist(name, None, len(elig), [], {}, "DATA_LIMITED", "single_class")
    base = LogisticRegression(max_iter=400, random_state=SEED)
    pipe = Pipeline([("scaler", StandardScaler()), ("clf", base)])
    try:
        if len(elig) >= 40 and min(Counter(y).values()) >= 3:
            model: Any = CalibratedClassifierCV(pipe, method="sigmoid", cv=3)
        else:
            model = pipe
        model.fit(X, y)
        # importance from linear coef if available
        imp: dict[str, float] = {}
        clf = None
        if hasattr(model, "calibrated_classifiers_"):
            pass
        else:
            clf = model.named_steps.get("clf")
        if clf is not None and hasattr(clf, "coef_"):
            coef = np.mean(np.abs(clf.coef_), axis=0)
            for i, n in enumerate(FEATURE_NAMES):
                imp[n] = round(float(coef[i]), 5)
        return FittedSpecialist(
            name=name,
            model=model,
            train_n=len(elig),
            classes=sorted(set(y)),
            feature_importance=imp,
            status="FITTED",
        )
    except Exception as e:  # noqa: BLE001
        return FittedSpecialist(name, None, len(elig), [], {}, "FIT_FAILED", str(e))


@dataclass
class SpecialistPrediction:
    name: str
    eligible: bool
    direction: str | None
    p_home: float | None
    p_draw: float | None
    p_away: float | None
    confidence: float | None
    abstain_probability: float | None
    reason: str
    top_features: list[str] = field(default_factory=list)


def predict_specialist(spec: FittedSpecialist, r: p2.RowV2) -> SpecialistPrediction:
    if not eligible(spec.name, r):
        return SpecialistPrediction(
            name=spec.name,
            eligible=False,
            direction=None,
            p_home=None,
            p_draw=None,
            p_away=None,
            confidence=None,
            abstain_probability=1.0,
            reason="not_eligible_for_regime",
        )
    prior = specialist_target_direction(spec.name, r)
    if spec.model is None or spec.status != "FITTED":
        # heuristic fallback — still research-only
        conf = float(r.confidence or 50) / 100.0
        abstain = 0.55 if conf < 0.55 else 0.25
        # crude probs from prior
        probs = {"home": 0.33, "draw": 0.34, "away": 0.33}
        if prior:
            probs = {"home": 0.2, "draw": 0.2, "away": 0.2}
            probs[prior] = 0.6
        return SpecialistPrediction(
            name=spec.name,
            eligible=True,
            direction=prior,
            p_home=probs["home"],
            p_draw=probs["draw"],
            p_away=probs["away"],
            confidence=round(max(probs.values()), 4),
            abstain_probability=abstain,
            reason=f"heuristic_fallback:{spec.status}",
            top_features=["confidence", "market", "lambda_diff"],
        )
    X = np.array([feature_vector(r)], dtype=float)
    proba = spec.model.predict_proba(X)[0]
    classes = list(spec.model.classes_)
    pmap = {c: float(proba[i]) for i, c in enumerate(classes)}
    for k in ("home", "draw", "away"):
        pmap.setdefault(k, 0.0)
    s = pmap["home"] + pmap["draw"] + pmap["away"]
    if s > 0:
        pmap = {k: v / s for k, v in pmap.items()}
    direction = max(pmap, key=lambda k: pmap[k])
    conf = pmap[direction]
    # abstain if flat or low conf
    entropy = -sum(v * math.log(v) for v in pmap.values() if v > 0)
    abstain = float(min(0.95, max(0.05, (entropy / math.log(3)) * (1.0 - conf))))
    top_feats = sorted(spec.feature_importance.items(), key=lambda x: -x[1])[:5]
    return SpecialistPrediction(
        name=spec.name,
        eligible=True,
        direction=direction,
        p_home=round(pmap["home"], 4),
        p_draw=round(pmap["draw"], 4),
        p_away=round(pmap["away"], 4),
        confidence=round(conf, 4),
        abstain_probability=round(abstain, 4),
        reason="calibrated_specialist" if "Calibrated" in type(spec.model).__name__ else "fitted_specialist",
        top_features=[k for k, _ in top_feats] or FEATURE_NAMES[:5],
    )


# ---------------------------------------------------------------------------
# Meta router
# ---------------------------------------------------------------------------


@dataclass
class MetaDecision:
    fixture_id: int
    p_home: float
    p_draw: float
    p_away: float
    direction: str
    expected_correctness: float
    abstain_probability: float
    chosen_specialist: str
    reason: str
    rejected: list[dict[str, str]]
    explain: dict[str, Any]
    routing_log: dict[str, Any]


def route_specialist(r: p2.RowV2, preds: dict[str, SpecialistPrediction]) -> tuple[str, str, list[dict[str, str]]]:
    """Deterministic routing rules + specialist abstain gates."""
    rejected: list[dict[str, str]] = []
    fav_odds = min([o for o in (r.odds_home, r.odds_draw, r.odds_away) if o], default=None)
    entropy = r.entropy

    def reject(name: str, why: str) -> None:
        rejected.append({"specialist": name, "reason": why})

    # High entropy → abstain preference
    if entropy is not None and entropy >= 1.75:
        for n, p in preds.items():
            if n != "Draw_Specialist":
                reject(n, "high_entropy_prefer_abstain")
        return "ABSTAIN", "high_entropy>=1.75", rejected

    # Balanced → Draw
    if r.balanced_market and preds.get("Draw_Specialist") and preds["Draw_Specialist"].eligible:
        for n in preds:
            if n != "Draw_Specialist":
                reject(n, "balanced_market_routes_to_draw_specialist")
        return "Draw_Specialist", "balanced_market", rejected

    # Heavy favorite
    if fav_odds is not None and fav_odds <= 1.45 and preds.get("Heavy_Favorite_Specialist") and preds["Heavy_Favorite_Specialist"].eligible:
        for n in preds:
            if n != "Heavy_Favorite_Specialist":
                reject(n, "heavy_favorite_route")
        return "Heavy_Favorite_Specialist", "heavy_favorite_odds<=1.45", rejected

    # Market contradiction
    fav = p2.market_fav(r)
    if fav and r.wde_decision and fav != r.wde_decision:
        if preds.get("Market_Contradiction_Detector") and preds["Market_Contradiction_Detector"].eligible:
            for n in preds:
                if n != "Market_Contradiction_Detector":
                    reject(n, "market_contradiction_route")
            return "Market_Contradiction_Detector", "wde_vs_market_conflict", rejected

    # Upset risk
    if fav_odds is not None and fav_odds <= 1.7 and (r.confidence or 100) < 58:
        if preds.get("Upset_Risk_Detector") and preds["Upset_Risk_Detector"].eligible:
            for n in preds:
                if n != "Upset_Risk_Detector":
                    reject(n, "upset_risk_route")
            return "Upset_Risk_Detector", "short_favorite_low_confidence", rejected

    # Low / high goal regimes
    lam_tot = (r.lambda_home or 0) + (r.lambda_away or 0)
    if lam_tot and lam_tot <= 2.2 and preds.get("Low_Goal_Specialist") and preds["Low_Goal_Specialist"].eligible:
        for n in preds:
            if n != "Low_Goal_Specialist":
                reject(n, "low_goal_route")
        return "Low_Goal_Specialist", "lambda_total<=2.2", rejected
    if lam_tot and lam_tot >= 2.8 and preds.get("High_Goal_Specialist") and preds["High_Goal_Specialist"].eligible:
        for n in preds:
            if n != "High_Goal_Specialist":
                reject(n, "high_goal_route")
        return "High_Goal_Specialist", "lambda_total>=2.8", rejected

    # Favorite default
    if preds.get("Favorite_Specialist") and preds["Favorite_Specialist"].eligible:
        for n in preds:
            if n != "Favorite_Specialist":
                reject(n, "default_favorite_route")
        return "Favorite_Specialist", "default_favorite_eligible", rejected

    # League / WDE fallback via League specialist
    if preds.get("League_Specialist") and preds["League_Specialist"].eligible:
        for n in preds:
            if n != "League_Specialist":
                reject(n, "league_fallback")
        return "League_Specialist", "league_fallback", rejected

    return "CANONICAL_WDE", "no_specialist_eligible", rejected


def meta_decide(r: p2.RowV2, fitted: dict[str, FittedSpecialist]) -> MetaDecision:
    preds = {n: predict_specialist(fitted[n], r) for n in SPECIALISTS if n in fitted}
    chosen, reason, rejected = route_specialist(r, preds)

    if chosen == "ABSTAIN":
        # blend WDE probs but high abstain
        ph, pd_, pa = float(r.home_p or 0.33), float(r.draw_p or 0.34), float(r.away_p or 0.33)
        s = ph + pd_ + pa or 1.0
        ph, pd_, pa = ph / s, pd_ / s, pa / s
        direction = max([("home", ph), ("draw", pd_), ("away", pa)], key=lambda x: x[1])[0]
        return MetaDecision(
            fixture_id=r.fixture_id,
            p_home=round(ph, 4),
            p_draw=round(pd_, 4),
            p_away=round(pa, 4),
            direction=direction,
            expected_correctness=round(max(ph, pd_, pa) * 0.7, 4),
            abstain_probability=0.85,
            chosen_specialist="ABSTAIN",
            reason=reason,
            rejected=rejected,
            explain={
                "why_selected": reason,
                "expected_accuracy": round(max(ph, pd_, pa) * 0.7, 4),
                "expected_calibration": "deferred_small_n",
                "expected_uncertainty": "high",
                "top_features": ["entropy", "confidence", "top5_mass"],
            },
            routing_log={"rule": reason, "chosen": "ABSTAIN"},
        )

    if chosen == "CANONICAL_WDE":
        ph, pd_, pa = float(r.home_p or 0.33), float(r.draw_p or 0.34), float(r.away_p or 0.33)
        s = ph + pd_ + pa or 1.0
        ph, pd_, pa = ph / s, pd_ / s, pa / s
        direction = r.wde_decision or max([("home", ph), ("draw", pd_), ("away", pa)], key=lambda x: x[1])[0]
        return MetaDecision(
            fixture_id=r.fixture_id,
            p_home=round(ph, 4),
            p_draw=round(pd_, 4),
            p_away=round(pa, 4),
            direction=direction,
            expected_correctness=round(max(ph, pd_, pa), 4),
            abstain_probability=0.2,
            chosen_specialist="CANONICAL_WDE",
            reason=reason,
            rejected=rejected,
            explain={
                "why_selected": reason,
                "expected_accuracy": round(max(ph, pd_, pa), 4),
                "expected_calibration": "wde_native",
                "expected_uncertainty": "moderate",
                "top_features": ["home_p", "draw_p", "away_p", "confidence"],
            },
            routing_log={"rule": reason, "chosen": "CANONICAL_WDE"},
        )

    sp = preds[chosen]
    # Blend specialist with WDE (70/30) for stability
    wh, wd, wa = float(r.home_p or 0), float(r.draw_p or 0), float(r.away_p or 0)
    ws = wh + wd + wa
    if ws > 0:
        wh, wd, wa = wh / ws, wd / ws, wa / ws
    else:
        wh, wd, wa = 0.34, 0.33, 0.33
    sh, sd, sa = sp.p_home or wh, sp.p_draw or wd, sp.p_away or wa
    ph = 0.7 * sh + 0.3 * wh
    pd_ = 0.7 * sd + 0.3 * wd
    pa = 0.7 * sa + 0.3 * wa
    s = ph + pd_ + pa
    ph, pd_, pa = ph / s, pd_ / s, pa / s
    direction = max([("home", ph), ("draw", pd_), ("away", pa)], key=lambda x: x[1])[0]
    abstain = sp.abstain_probability if sp.abstain_probability is not None else 0.3
    # escalate abstain if specialist itself wants abstain
    if abstain >= 0.7:
        direction = r.wde_decision or direction
    return MetaDecision(
        fixture_id=r.fixture_id,
        p_home=round(ph, 4),
        p_draw=round(pd_, 4),
        p_away=round(pa, 4),
        direction=direction,
        expected_correctness=round(max(ph, pd_, pa) * (1.0 - 0.3 * abstain), 4),
        abstain_probability=round(float(abstain), 4),
        chosen_specialist=chosen,
        reason=reason,
        rejected=rejected,
        explain={
            "why_selected": reason,
            "why_others_rejected": rejected[:8],
            "expected_accuracy": round(max(ph, pd_, pa) * (1.0 - 0.3 * abstain), 4),
            "expected_calibration": sp.reason,
            "expected_uncertainty": "high" if abstain >= 0.6 else "moderate" if abstain >= 0.35 else "low",
            "top_features": sp.top_features,
            "specialist_direction": sp.direction,
            "specialist_confidence": sp.confidence,
        },
        routing_log={"rule": reason, "chosen": chosen, "specialist_abstain": abstain},
    )


# ---------------------------------------------------------------------------
# Evaluation / walk-forward
# ---------------------------------------------------------------------------


def eval_predictions(rows: list[p2.RowV2], preds: list[tuple[str | None, p2.RowV2]], *, abstain_flags: list[bool] | None = None) -> dict[str, Any]:
    if abstain_flags is None:
        labeled = [(p, r) for p, r in preds if p]
    else:
        labeled = [(p, r) for (p, r), ab in zip(preds, abstain_flags) if p and not ab]
    return p2.metrics(labeled, len(rows))


def walk_forward_specialists(rows: list[p2.RowV2], sealed: set[int]) -> tuple[list[dict], dict, dict]:
    data = [r for r in p2.usable(rows) if r.fixture_id not in sealed]
    data = sorted(data, key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))
    folds = []
    routing_events: list[dict] = []
    min_train, block = 50, 20
    i = min_train
    while i + 8 <= len(data):
        train, test = data[:i], data[i : i + block]
        if len(test) < 8:
            break
        fitted = {n: fit_specialist(n, train) for n in SPECIALISTS}
        # evaluate each specialist + meta + canonical + phase2 best proxy (ecse top5)
        fold_metrics: dict[str, Any] = {}
        # canonical
        fold_metrics["canonical_wde"] = p2.metrics([(r.wde_decision, r) for r in test], len(test))
        fold_metrics["ecse_direction"] = p2.metrics([(r.ecse_direction or r.wde_decision, r) for r in test], len(test))
        # phase2-like best strategy proxy
        cfg = p2.StratCfg(0, 0.0, None, 0.65, False, None, "ecse", False, False)
        fold_metrics["phase2_best_proxy_ecse_top5"] = p2.metrics(p2.apply_strategy(test, cfg), len(test))

        for n, sp in fitted.items():
            preds = []
            for r in test:
                pr = predict_specialist(sp, r)
                if not pr.eligible or (pr.abstain_probability or 0) >= 0.75:
                    continue
                preds.append((pr.direction, r))
            fold_metrics[n] = p2.metrics(preds, len(test))

        meta_preds = []
        meta_abs = []
        for r in test:
            md = meta_decide(r, fitted)
            routing_events.append(
                {
                    "fold": len(folds) + 1,
                    "fixture_id": r.fixture_id,
                    "chosen": md.chosen_specialist,
                    "reason": md.reason,
                    "abstain": md.abstain_probability,
                    "direction": md.direction,
                    "actual": r.actual_1x2,
                    "correct": md.direction == r.actual_1x2 if md.abstain_probability < 0.75 else None,
                }
            )
            meta_preds.append((md.direction, r))
            meta_abs.append(md.abstain_probability >= 0.75)
        fold_metrics["meta_model"] = eval_predictions(test, meta_preds, abstain_flags=meta_abs)
        fold_metrics["meta_model_no_abstain"] = p2.metrics(meta_preds, len(test))

        folds.append(
            {
                "fold": len(folds) + 1,
                "train_n": len(train),
                "test_n": len(test),
                "train_end": train[-1].kickoff_utc,
                "test_start": test[0].kickoff_utc,
                "test_end": test[-1].kickoff_utc,
                "metrics": fold_metrics,
                "specialist_fit_status": {n: fitted[n].status for n in SPECIALISTS},
            }
        )
        i += block

    # aggregate
    def agg(key: str) -> dict[str, Any]:
        accs = []
        ns = []
        for f in folds:
            m = f["metrics"].get(key) or {}
            if m.get("accuracy") is not None:
                accs.append(m["accuracy"])
                ns.append(m.get("n") or 0)
        return {
            "mean_accuracy": round(sum(accs) / len(accs), 4) if accs else None,
            "median_accuracy": round(sorted(accs)[len(accs) // 2], 4) if accs else None,
            "worst_accuracy": min(accs) if accs else None,
            "mean_n": round(sum(ns) / len(ns), 2) if ns else None,
            "folds_with_metric": len(accs),
        }

    summary = {
        "n_folds": len(folds),
        "models": {k: agg(k) for k in (["canonical_wde", "ecse_direction", "phase2_best_proxy_ecse_top5", "meta_model", "meta_model_no_abstain"] + SPECIALISTS)},
    }
    routing = {
        "n_events": len(routing_events),
        "chosen_counts": dict(Counter(e["chosen"] for e in routing_events)),
        "sample": routing_events[:40],
        "events_path_note": "full events embedded in walk_forward folds routing sample",
    }
    return folds, summary, routing


def calibration_report(rows: list[p2.RowV2], fitted: dict[str, FittedSpecialist]) -> dict[str, Any]:
    """Simple reliability bins for meta expected correctness vs outcome."""
    bins = defaultdict(list)
    for r in rows:
        md = meta_decide(r, fitted)
        if md.abstain_probability >= 0.75:
            continue
        b = int(md.expected_correctness * 5) / 5.0
        bins[b].append(1.0 if md.direction == r.actual_1x2 else 0.0)
    out = []
    for b in sorted(bins):
        vals = bins[b]
        out.append({"expected_bin": b, "n": len(vals), "empirical_accuracy": round(sum(vals) / len(vals), 4)})
    return {"bins": out, "note": "research calibration on non-holdout rows; not production"}


def lock_candidates(wf_summary: dict[str, Any], regimes: dict[str, Any]) -> dict[str, Any]:
    """Lock top candidates after walk-forward — no further tuning."""
    models = wf_summary.get("models") or {}
    ranked = []
    for name, m in models.items():
        if m.get("mean_accuracy") is None:
            continue
        ranked.append(
            {
                "model": name,
                "mean_accuracy": m["mean_accuracy"],
                "median_accuracy": m.get("median_accuracy"),
                "worst_accuracy": m.get("worst_accuracy"),
                "mean_n": m.get("mean_n"),
                "folds": m.get("folds_with_metric"),
                "score": (m["mean_accuracy"] or 0) * math.log1p(m.get("mean_n") or 0),
            }
        )
    ranked.sort(key=lambda x: (-(x["score"] or 0), -(x["mean_accuracy"] or 0)))
    locked = []
    for row in ranked[:5]:
        locked.append({**row, "locked": True, "tuning_allowed_after_lock": False})
    return {
        "locked_at": _utc_now(),
        "rule": "Top 5 by walk-forward score; NO MORE TUNING; holdout remains sealed",
        "locked_candidates": locked,
        "leaderboard": ranked,
        "phase1_holdout_opened": False,
        "promotion": False,
        "deployment": False,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_phase3(*, out_dir: Path | None = None) -> dict[str, Any]:
    ts = _utc_now()
    out = out_dir or (ROOT / "artifacts" / "prediction_engine_75_phase3" / ts)
    out.mkdir(parents=True, exist_ok=True)

    sealed = p2.load_phase1_sealed_ids()
    rows, _ex, _inv = p2.build_expanded_corpus()
    use = [r for r in p2.usable(rows) if r.fixture_id not in sealed]
    use = sorted(use, key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))

    if len(use) < 40:
        status = STATUS_FAILED
        validation = {
            "status": status,
            "reason": "insufficient_usable_rows",
            "n": len(use),
            "sealed_holdout_status": "SEALED_UNOPENED",
            "not_deployed": True,
            "canonical_unchanged": True,
            "wde_unchanged": True,
            "ecse_unchanged": True,
            "no_auto_promotion": True,
        }
        _write_json(out / "validation_report.json", validation)
        return validation

    # Part 1 regimes on research set
    regimes = discover_error_regimes(use)
    _write_json(out / "error_regimes.json", regimes)

    # Fit specialists on first 70% for artifact snapshot (walk-forward refits per fold)
    cut = int(len(use) * 0.7)
    train_snap, val_snap = use[:cut], use[cut:]
    fitted = {n: fit_specialist(n, train_snap) for n in SPECIALISTS}
    specialist_doc = {
        "specialists": [
            {
                "name": n,
                "status": fitted[n].status,
                "train_n": fitted[n].train_n,
                "classes": fitted[n].classes,
                "note": fitted[n].note,
                "feature_importance_top": dict(
                    sorted(fitted[n].feature_importance.items(), key=lambda x: -x[1])[:8]
                ),
                "research_only": True,
            }
            for n in SPECIALISTS
        ],
        "shadow_inputs_unavailable": ["Exact_V2", "DNA", "Twins", "HCEE"],
        "available_inputs": ["WDE", "ECSE", "Lambda_V2", "Market", "Odds", "Top5", "Entropy", "League", "Confidence"],
    }
    _write_json(out / "specialist_models.json", specialist_doc)

    # Meta model doc + routing analysis on validation snapshot
    meta_rows = []
    routing_sample = []
    for r in val_snap:
        md = meta_decide(r, fitted)
        meta_rows.append(asdict(md))
        routing_sample.append(md.routing_log | {"fixture_id": r.fixture_id, "chosen": md.chosen_specialist, "reason": md.reason})
    _write_json(
        out / "meta_model.json",
        {
            "type": "rule_router_plus_specialist_probability_blend",
            "blend": "0.7*specialist + 0.3*WDE",
            "outputs": ["p_home", "p_draw", "p_away", "expected_correctness", "abstain_probability", "chosen_specialist", "reason"],
            "n_validation_decisions": len(meta_rows),
            "sample_decisions": meta_rows[:20],
            "research_only": True,
            "canonical_unchanged": True,
        },
    )
    _write_json(
        out / "routing_analysis.json",
        {
            "chosen_counts": dict(Counter(x["chosen"] for x in routing_sample)),
            "sample": routing_sample[:50],
            "rules": [
                "high_entropy -> ABSTAIN",
                "balanced_market -> Draw_Specialist",
                "fav_odds<=1.45 -> Heavy_Favorite_Specialist",
                "wde!=market -> Market_Contradiction_Detector",
                "short fav + low conf -> Upset_Risk_Detector",
                "lambda_total<=2.2 -> Low_Goal_Specialist",
                "lambda_total>=2.8 -> High_Goal_Specialist",
                "else Favorite_Specialist / League / Canonical_WDE",
            ],
        },
    )

    # Walk-forward
    folds, wf_summary, routing = walk_forward_specialists(rows, sealed)
    _write_json(out / "walk_forward_specialists.json", {"folds": folds, "summary": wf_summary, "routing": routing})

    lock = lock_candidates(wf_summary, regimes)
    _write_json(out / "candidate_lock.json", lock)
    _write_csv(out / "candidate_leaderboard.csv", lock["leaderboard"])

    # Feature importance aggregate
    imp_agg: dict[str, list[float]] = defaultdict(list)
    for n, sp in fitted.items():
        for k, v in sp.feature_importance.items():
            imp_agg[k].append(v)
    feat_imp = {
        k: {"mean_abs_coef": round(sum(v) / len(v), 5), "specialists_with_signal": len(v)}
        for k, v in sorted(imp_agg.items(), key=lambda x: -sum(x[1]) / max(1, len(x[1])))
    }
    _write_json(out / "feature_importance.json", feat_imp)

    cal = calibration_report(val_snap, fitted)
    _write_json(out / "calibration_report.json", cal)

    _write_json(
        out / "sealed_holdout_status.json",
        {
            "phase1_holdout": {"status": "SEALED_UNOPENED", "n": len(sealed), "opened": False, "fixture_ids": sorted(sealed)},
            "phase3_tuning_after_lock": False,
        },
    )
    _write_json(
        out / "promotion_gate_status.json",
        {
            "passed": False,
            "promotion": False,
            "deployment": False,
            "auto_promotion": False,
            "holdout_opened": False,
            "ready_for_later_holdout_eval": True,
            "locked_candidates": [c["model"] for c in lock["locked_candidates"]],
        },
    )

    fitted_n = sum(1 for s in fitted.values() if s.status == "FITTED")
    meta_wf = (wf_summary.get("models") or {}).get("meta_model") or {}
    canon_wf = (wf_summary.get("models") or {}).get("canonical_wde") or {}
    # Status: COMPLETE if architecture delivered with folds; DATA_LIMITED if few specialists fitted
    if not folds:
        status = STATUS_FAILED
    elif fitted_n < 3 or len(use) < 100:
        status = STATUS_LIMITED
    else:
        status = STATUS_COMPLETE

    validation = {
        "status": status,
        "phase": PHASE,
        "usable_n_excl_sealed": len(use),
        "priced_n": sum(1 for r in use if r.odds_home and r.odds_draw and r.odds_away),
        "specialists_fitted": fitted_n,
        "specialists_total": len(SPECIALISTS),
        "walk_forward_folds": len(folds),
        "meta_walk_forward_mean_accuracy": meta_wf.get("mean_accuracy"),
        "canonical_walk_forward_mean_accuracy": canon_wf.get("mean_accuracy"),
        "locked_candidates": lock["locked_candidates"],
        "primary_error_regimes": sorted(
            ((k, v.get("n") or 0) for k, v in (regimes.get("regimes") or {}).items()),
            key=lambda x: -x[1],
        )[:5],
        "sealed_holdout_status": "SEALED_UNOPENED",
        "target_75_claimed": False,
        "not_deployed": True,
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "no_auto_promotion": True,
        "no_more_tuning_after_lock": True,
        "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/") if out.is_relative_to(ROOT) else str(out),
    }
    _write_json(out / "validation_report.json", validation)

    report = _report_md(validation, regimes, wf_summary, lock)
    (out / "PHASE3_SPECIALIST_MODELS_REPORT.md").write_text(report, encoding="utf-8")
    (out / "PHASE3_SPECIALIST_MODELS_REPORT_FA.md").write_text(
        "# فاز ۳ — مدل‌های متخصص و متا-انسمبل\n\n" + report, encoding="utf-8"
    )
    (out / "owner_dashboard.html").write_text(_dashboard(validation), encoding="utf-8")
    return validation


def _report_md(v: dict, regimes: dict, wf: dict, lock: dict) -> str:
    return f"""# PHASE3_SPECIALIST_MODELS_REPORT

Status: **{v['status']}**

## Scope

Mixture-of-experts research over failure regimes. Canonical / WDE / ECSE unchanged. Holdout sealed. No deployment.

## Error regimes (top)

{v['primary_error_regimes']}

Overall miss rate: {(regimes or {}).get('overall_miss_rate')}

## Specialists

Fitted: **{v['specialists_fitted']}** / {v['specialists_total']}

Unavailable shadow inputs in local joins: Exact V2, DNA, Twins, HCEE (documented; not fabricated).

## Walk-forward

Folds: **{v['walk_forward_folds']}**

- Meta mean accuracy: {v['meta_walk_forward_mean_accuracy']}
- Canonical WDE mean accuracy: {v['canonical_walk_forward_mean_accuracy']}

## Locked candidates (NO MORE TUNING)

{[c.get('model') for c in v.get('locked_candidates') or []]}

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- SEALED HOLDOUT UNOPENED
- NO AUTO-PROMOTION
- 75% target **not claimed**
"""


def _dashboard(v: dict[str, Any]) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Phase3 Specialists</title>
<style>body{{font-family:Georgia,serif;margin:2rem;background:#10151c;color:#e8eef5}}
h1{{color:#9ad0b8}}.card{{background:#1a222d;padding:1rem;margin:1rem 0;border-radius:8px}}</style></head><body>
<h1>Phase 3 — Specialist Models + Meta</h1>
<div class="card"><b>{v['status']}</b><br/>
usable={v['usable_n_excl_sealed']} · specialists fitted={v['specialists_fitted']}/{v['specialists_total']}<br/>
WF folds={v['walk_forward_folds']} · meta acc={v['meta_walk_forward_mean_accuracy']} · WDE acc={v['canonical_walk_forward_mean_accuracy']}<br/>
holdout={v['sealed_holdout_status']}</div>
<p>NOT DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · SEALED HOLDOUT UNOPENED · NO AUTO-PROMOTION</p>
</body></html>"""
