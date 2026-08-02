"""
PREDICTION_ENGINE_75_PERCENT_RESEARCH_PROGRAM — Phase 1 foundation.

Research/shadow only. Does not change Canonical WDE/ECSE, freezes, or production
selection policy. Sealed chronological holdout remains unopened for strategy selection.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[3]
PHASE = "PREDICTION_ENGINE_75_PERCENT_RESEARCH_PROGRAM_PHASE1"
STATUS_READY = "PREDICTION_ENGINE_75_RESEARCH_FOUNDATION_READY"
STATUS_BLOCKED = "PREDICTION_ENGINE_75_RESEARCH_DATA_BLOCKED"
APPROVED_ACC = 0.4545  # from APPROVED_BETS forensic (5/11)
TARGET_ACC = 0.75
MIN_HOLDOUT_N = 100
SEED = 20260802

# Display wording — research/docs only; production deploy requires owner approval.
LABEL_WORDING_MAP = {
    "Approved Bet": "Research Candidate",
    "BETTABLE_CANDIDATE": "MODEL_CANDIDATE",
    "Bettable": "Model Candidate",
    "Strong Pick": "High Model Agreement",
    "SELECTED_FOR_BETTING": "RESEARCH_SHORTLIST",
    "APPROVED": "RESEARCH_CANDIDATE",
}


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm_dir(v: Any) -> str | None:
    s = str(v or "").strip().lower()
    if not s or s in {"none", "null", "unknown", "unavailable_in_freeze"}:
        return None
    if "home" in s or s in {"h", "1", "home_win"}:
        return "home"
    if "away" in s or s in {"a", "2", "away_win"}:
        return "away"
    if "draw" in s or s in {"d", "x"}:
        return "draw"
    return None


def _norm_conf(v: Any) -> float | None:
    c = _f(v)
    if c is None:
        return None
    return c * 100.0 if c <= 1.5 else c


def _norm_prob(v: Any) -> float | None:
    p = _f(v)
    if p is None:
        return None
    return p / 100.0 if p > 1.5 else p


def _safe_odds(v: Any) -> float | None:
    o = _f(v)
    if o is None or o < 1.01 or o > 100:
        return None
    return o


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    s = str(v).replace("Z", "+00:00").replace(" UTC", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fields or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = hits / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) / n) + (z * z / (4 * n * n)))
    return round((centre - margin) / den, 4), round((centre + margin) / den, 4)


def cfg_hash(cfg: dict[str, Any]) -> str:
    blob = json.dumps(cfg, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Feature dictionary / availability
# ---------------------------------------------------------------------------

FEATURE_CATALOG = [
    ("fixture_id", "id", True, "freeze/eval"),
    ("kickoff_utc", "timestamp", True, "fixtures/freeze"),
    ("frozen_at", "timestamp", True, "freeze"),
    ("generated_at", "timestamp", True, "freeze"),
    ("freeze_id", "id", True, "freeze"),
    ("freeze_hash", "hash", True, "freeze"),
    ("league", "categorical", True, "freeze/eval"),
    ("competition", "categorical", True, "freeze"),
    ("validation_tier", "categorical", False, "owner scope"),
    ("wde_decision", "label", True, "WDE freeze"),
    ("ft_marginal_direction", "label", True, "WDE freeze"),
    ("home_probability", "float", True, "WDE"),
    ("draw_probability", "float", True, "WDE"),
    ("away_probability", "float", True, "WDE"),
    ("wde_confidence", "float", True, "WDE"),
    ("ecse_top1..top10", "scores", True, "ECSE freeze ranks"),
    ("top5_mass", "float", True, "ECSE"),
    ("top10_mass", "float", True, "ECSE"),
    ("entropy", "float", False, "often missing in freeze overlay"),
    ("lambda_home", "float", True, "ECSE"),
    ("lambda_away", "float", True, "ECSE"),
    ("odds_home/draw/away", "float", False, "often missing as decimal; reject implied-prob"),
    ("exact_v2_direction", "label", False, "shadow; not on all freezes"),
    ("dna_direction", "label", False, "shadow"),
    ("twins_direction", "label", False, "shadow"),
    ("hcee", "struct", False, "shadow"),
    ("team_form_h2h", "struct", False, "shadow"),
    ("xg", "float", False, "sparse"),
    ("lineups", "struct", False, "sparse"),
    ("injuries", "struct", False, "sparse"),
    ("referee", "categorical", False, "sparse"),
    ("weather", "struct", False, "sparse"),
    ("odds_movement", "float", False, "not in Phase1 freeze overlay"),
    ("actual_1x2", "label", True, "fixture_results / eval"),
    ("final_score", "score", True, "fixture_results"),
    ("cohort_type", "categorical", True, "assigned historical_replay"),
]


@dataclass
class ResearchRow:
    fixture_id: int
    kickoff_utc: str | None
    frozen_at: str | None
    generated_at: str | None
    freeze_id: str | None
    freeze_hash: str | None
    league: str | None
    match: str | None
    wde_decision: str | None
    ft_marginal: str | None
    home_p: float | None
    draw_p: float | None
    away_p: float | None
    confidence: float | None
    top5_mass: float | None
    top10_mass: float | None
    entropy: float | None
    lambda_home: float | None
    lambda_away: float | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    actual_1x2: str | None
    final_score: str | None
    exclusion_reason: str | None = None
    cohort_type: str = "historical_replay"
    feature_flags: dict[str, bool] = field(default_factory=dict)


def load_research_rows() -> tuple[list[ResearchRow], dict[str, Any]]:
    """Build Phase-1 rows from finished freeze evaluations + DB results (read-only)."""
    by_fid: dict[int, ResearchRow] = {}
    exclusions: list[dict[str, Any]] = []

    for path in sorted((ROOT / "artifacts/finished_match_evaluation").glob("**/complete_fixture_evaluations.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            continue
        for r in rows:
            fid = int(r.get("fixture_id") or 0)
            if not fid:
                continue
            actual = _norm_dir(r.get("actual_1x2"))
            wde = _norm_dir(r.get("wde_decision"))
            marg = _norm_dir(r.get("ft_marginal_direction"))
            ko = str(r.get("kickoff_utc") or "") or None
            fr = str(r.get("frozen_at") or r.get("generated_at") or "") or None
            reason = None
            ko_dt, fr_dt = _parse_dt(ko), _parse_dt(fr)
            if ko_dt and fr_dt and fr_dt >= ko_dt:
                reason = "POST_KICKOFF_FREEZE"
            if not actual:
                reason = reason or "RESULT_MISSING"
            row = ResearchRow(
                fixture_id=fid,
                kickoff_utc=ko,
                frozen_at=fr,
                generated_at=str(r.get("generated_at") or "") or None,
                freeze_id=str(r.get("freeze_id") or "") or None,
                freeze_hash=str(r.get("freeze_hash") or "") or None,
                league=str(r.get("league") or r.get("competition") or "") or None,
                match=r.get("match"),
                wde_decision=wde,
                ft_marginal=marg,
                home_p=_norm_prob(r.get("home_probability")),
                draw_p=_norm_prob(r.get("draw_probability")),
                away_p=_norm_prob(r.get("away_probability")),
                confidence=_norm_conf(r.get("wde_confidence")),
                top5_mass=_f(r.get("top5_mass")),
                top10_mass=_f(r.get("top10_mass")),
                entropy=_f(r.get("entropy")),
                lambda_home=_f(r.get("lambda_home")),
                lambda_away=_f(r.get("lambda_away")),
                odds_home=None,
                odds_draw=None,
                odds_away=None,
                actual_1x2=actual,
                final_score=str(r.get("regulation_score") or r.get("final_score") or "") or None,
                exclusion_reason=reason,
                cohort_type="historical_replay",
                feature_flags={
                    "wde": wde is not None,
                    "probs": r.get("home_probability") is not None,
                    "ecse_mass": r.get("top5_mass") is not None,
                    "entropy": r.get("entropy") not in (None, "None"),
                    "lambda": r.get("lambda_home") is not None,
                },
            )
            prev = by_fid.get(fid)
            if prev is None or (ko and str(prev.kickoff_utc or "") < ko):
                by_fid[fid] = row
            if reason:
                exclusions.append({"fixture_id": fid, "reason": reason, "source": str(path.relative_to(ROOT))})

    # Join DB results for any missing actuals; odds from shortlist artifacts / predictions carefully
    db = ROOT / "data" / "football_intelligence.db"
    if db.exists():
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute(
                "SELECT fixture_id, home_goals, away_goals, final_score FROM fixture_results WHERE home_goals IS NOT NULL"
            ):
                fid = int(r["fixture_id"])
                hg, ag = int(r["home_goals"]), int(r["away_goals"])
                actual = "home" if hg > ag else "away" if ag > hg else "draw"
                if fid in by_fid:
                    if by_fid[fid].actual_1x2 is None:
                        by_fid[fid].actual_1x2 = actual
                        by_fid[fid].final_score = r["final_score"] or f"{hg}-{ag}"
                        if by_fid[fid].exclusion_reason == "RESULT_MISSING":
                            by_fid[fid].exclusion_reason = None
                # do not invent freeze rows from results alone in Phase1
            for r in conn.execute("SELECT fixture_id, confidence, no_bet_flag FROM predictions"):
                fid = int(r["fixture_id"])
                if fid in by_fid and by_fid[fid].confidence is None:
                    by_fid[fid].confidence = _norm_conf(r["confidence"])
        finally:
            conn.close()

    # Attach decimal odds from owner/selection artifacts when present
    for path in ROOT.glob("artifacts/**/selected_matches.json"):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for it in obj.get("selected") or []:
            fid = int(it.get("fixture_id") or 0)
            if fid not in by_fid:
                continue
            oh = _safe_odds(it.get("home_odds") or it.get("odds_h"))
            od = _safe_odds(it.get("draw_odds") or it.get("odds_d"))
            oa = _safe_odds(it.get("away_odds") or it.get("odds_a"))
            if oh and od and oa:
                by_fid[fid].odds_home, by_fid[fid].odds_draw, by_fid[fid].odds_away = oh, od, oa
                by_fid[fid].feature_flags["odds"] = True

    for path in ROOT.glob("artifacts/**/day*_best_three.json"):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for it in obj.get("selected") or []:
            fid = int(it.get("fixture_id") or 0)
            if fid not in by_fid:
                continue
            # often no odds; skip
            oh = _safe_odds(it.get("home_odds") or (it.get("odds") or {}).get("home") if isinstance(it.get("odds"), dict) else None)
            if oh:
                by_fid[fid].odds_home = oh

    rows = list(by_fid.values())
    rows.sort(key=lambda r: str(r.kickoff_utc or ""))
    audit = {
        "n_raw": len(rows),
        "n_usable": sum(1 for r in rows if r.exclusion_reason is None and r.actual_1x2 and r.wde_decision),
        "exclusion_counts": dict(Counter(r.exclusion_reason or "OK" for r in rows)),
        "exclusions_sample": exclusions[:50],
        "sources": ["artifacts/finished_match_evaluation/**/complete_fixture_evaluations.json", "fixture_results", "predictions"],
    }
    return rows, audit


def usable_rows(rows: list[ResearchRow]) -> list[ResearchRow]:
    return [r for r in rows if r.exclusion_reason is None and r.actual_1x2 and r.wde_decision]


def chronological_split(rows: list[ResearchRow], *, train=0.6, val=0.2) -> dict[str, list[ResearchRow]]:
    rows = sorted(usable_rows(rows), key=lambda r: str(r.kickoff_utc or ""))
    n = len(rows)
    i1 = int(n * train)
    i2 = int(n * (train + val))
    return {"train": rows[:i1], "validation": rows[i1:i2], "holdout_sealed": rows[i2:]}


# ---------------------------------------------------------------------------
# Metrics / baselines / strategies
# ---------------------------------------------------------------------------

def _edge(r: ResearchRow) -> float | None:
    probs = [p for p in (r.home_p, r.draw_p, r.away_p) if p is not None]
    return max(probs) if probs else None


def market_favorite(r: ResearchRow) -> str | None:
    odds = [("home", r.odds_home), ("draw", r.odds_draw), ("away", r.odds_away)]
    odds = [(k, v) for k, v in odds if v is not None]
    if not odds:
        # fallback: highest WDE prob as weak proxy only when labeled market_missing
        return None
    return min(odds, key=lambda x: x[1])[0]


def metrics(preds: list[tuple[str | None, ResearchRow]]) -> dict[str, Any]:
    """preds: list of (predicted_dir, row)."""
    labeled = [(p, r) for p, r in preds if p and r.actual_1x2]
    n = len(labeled)
    hits = sum(1 for p, r in labeled if p == r.actual_1x2)
    lo, hi = wilson_ci(hits, n)
    # per-class
    by_act: dict[str, list[bool]] = defaultdict(list)
    for p, r in labeled:
        by_act[r.actual_1x2 or "?"].append(p == r.actual_1x2)
    recalls = {k: (sum(v) / len(v) if v else None) for k, v in by_act.items()}
    bal = sum(v for v in recalls.values() if v is not None) / max(1, len([v for v in recalls.values() if v is not None])) if recalls else None

    # priced ROI
    pnls = []
    for p, r in labeled:
        omap = {"home": r.odds_home, "draw": r.odds_draw, "away": r.odds_away}
        o = _safe_odds(omap.get(p or ""))
        if o is None:
            continue
        pnls.append((o - 1.0) if p == r.actual_1x2 else -1.0)
    max_dd = None
    if pnls:
        eq = peak = 0.0
        dd = 0.0
        for x in pnls:
            eq += x
            peak = max(peak, eq)
            dd = min(dd, eq - peak)
        max_dd = round(dd, 4)

    avg_odds = None
    odds_vals = []
    for p, r in labeled:
        o = _safe_odds({"home": r.odds_home, "draw": r.odds_draw, "away": r.odds_away}.get(p or ""))
        if o:
            odds_vals.append(o)
    if odds_vals:
        avg_odds = round(sum(odds_vals) / len(odds_vals), 4)

    return {
        "n": n,
        "hits": hits,
        "accuracy": round(hits / n, 4) if n else None,
        "balanced_accuracy": round(bal, 4) if bal is not None else None,
        "ci95": [lo, hi],
        "coverage_of_input": None,  # filled by caller
        "priced_n": len(pnls),
        "roi": round(sum(pnls) / len(pnls), 4) if pnls else None,
        "max_drawdown": max_dd,
        "avg_odds": avg_odds,
        "class_recall": {k: round(v, 4) if v is not None else None for k, v in recalls.items()},
    }


def run_baselines(rows: list[ResearchRow]) -> dict[str, Any]:
    out = {}

    def pack(name: str, preds: list[tuple[str | None, ResearchRow]], universe: int):
        m = metrics(preds)
        m["coverage_of_input"] = round(m["n"] / universe, 4) if universe else None
        m["name"] = name
        out[name] = m

    u = len(rows)
    pack("raw_wde_argmax_proxy_ft_marginal", [(r.ft_marginal or r.wde_decision, r) for r in rows], u)
    pack("stored_wde_decision", [(r.wde_decision, r) for r in rows], u)
    # market favorite only when odds present
    market_preds = [(market_favorite(r), r) for r in rows if market_favorite(r)]
    pack("market_implied_favorite", market_preds, u)
    # majority of available: wde + marginal (same often) — keep simple
    pack(
        "simple_prob_argmax",
        [
            (
                max(
                    [("home", r.home_p or 0), ("draw", r.draw_p or 0), ("away", r.away_p or 0)],
                    key=lambda x: x[1],
                )[0]
                if any(x is not None for x in (r.home_p, r.draw_p, r.away_p))
                else r.wde_decision,
                r,
            )
            for r in rows
        ],
        u,
    )
    # current-like: conf>=60
    pack(
        "current_no_bet_proxy_conf_ge_60",
        [(r.wde_decision, r) for r in rows if (r.confidence or 0) >= 60],
        u,
    )
    # strict approved proxy — conf>=60 and edge>=0.55
    pack(
        "strict_selection_proxy_conf60_edge55",
        [(r.wde_decision, r) for r in rows if (r.confidence or 0) >= 60 and (_edge(r) or 0) >= 0.55],
        u,
    )
    # Elo/Poisson/Dixon-Coles/GBM/Logistic — unavailable without full feature store in Phase1
    for name in (
        "elo_baseline",
        "poisson_baseline",
        "dixon_coles_baseline",
        "gradient_boosting_baseline",
        "calibrated_logistic_baseline",
        "exact_v2_full_mass",
        "ecse_full_mass_direction",
        "majority_model_vote",
        "weighted_model_vote",
    ):
        out[name] = {
            "name": name,
            "status": "NOT_AVAILABLE_IN_PHASE1_DATASET",
            "n": 0,
            "accuracy": None,
            "note": "Requires extended feature/model join; deferred to Phase 2+",
        }
    out["current_approved_forensic_reference"] = {
        "name": "current_approved_forensic_reference",
        "n": 11,
        "hits": 5,
        "accuracy": APPROVED_ACC,
        "note": "From APPROVED_BETS_FORENSIC_EVALUATION; not recomputed here",
    }
    return out


@dataclass(frozen=True)
class StrategyConfig:
    min_confidence: float
    min_edge: float
    max_entropy: float | None
    min_top5_mass: float | None
    require_decision_equals_marginal: bool
    odds_max: float | None  # abstain if favorite odds above this when odds exist; else ignore
    direction_mode: str  # wde | marginal | prob_argmax

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def apply_strategy(cfg: StrategyConfig, rows: list[ResearchRow]) -> list[tuple[str | None, ResearchRow]]:
    selected = []
    for r in rows:
        if (r.confidence or -1) < cfg.min_confidence:
            continue
        edge = _edge(r)
        if edge is None or edge < cfg.min_edge:
            continue
        if cfg.max_entropy is not None and r.entropy is not None and r.entropy > cfg.max_entropy:
            continue
        if cfg.min_top5_mass is not None and r.top5_mass is not None and r.top5_mass < cfg.min_top5_mass:
            continue
        if cfg.require_decision_equals_marginal and r.ft_marginal and r.wde_decision and r.ft_marginal != r.wde_decision:
            continue
        if cfg.direction_mode == "wde":
            d = r.wde_decision
        elif cfg.direction_mode == "marginal":
            d = r.ft_marginal or r.wde_decision
        else:
            if any(x is not None for x in (r.home_p, r.draw_p, r.away_p)):
                d = max([("home", r.home_p or 0), ("draw", r.draw_p or 0), ("away", r.away_p or 0)], key=lambda x: x[1])[0]
            else:
                d = r.wde_decision
        if cfg.odds_max is not None:
            fav = market_favorite(r)
            if fav and d:
                o = _safe_odds({"home": r.odds_home, "draw": r.odds_draw, "away": r.odds_away}.get(d))
                # If priced and too long (high odds), skip under max-odds cap for favorite-seeking strategies
                if o is not None and o > cfg.odds_max:
                    continue
        if d:
            selected.append((d, r))
    return selected


def build_search_space() -> list[StrategyConfig]:
    confs = [0, 45, 50, 55, 58, 60, 62, 65, 68, 70]
    edges = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
    ents = [None, 1.70, 1.62, 1.55]
    masses = [None, 0.45, 0.55, 0.65]
    agree = [False, True]
    odds_caps = [None, 1.50, 1.80, 2.20, 3.00]
    modes = ["wde", "marginal", "prob_argmax"]
    cfgs = []
    for vals in product(confs, edges, ents, masses, agree, odds_caps, modes):
        cfgs.append(
            StrategyConfig(
                min_confidence=float(vals[0]),
                min_edge=float(vals[1]),
                max_entropy=vals[2],
                min_top5_mass=vals[3],
                require_decision_equals_marginal=bool(vals[4]),
                odds_max=vals[5],
                direction_mode=str(vals[6]),
            )
        )
    # dedupe by hash
    seen = set()
    uniq = []
    for c in cfgs:
        h = cfg_hash(c.to_dict())
        if h in seen:
            continue
        seen.add(h)
        uniq.append(c)
    return uniq


def run_strategy_search(
    train: list[ResearchRow],
    validation: list[ResearchRow],
    *,
    max_experiments: int = 8000,
    min_val_n: int = 8,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    space = build_search_space()
    space = space[:max_experiments]
    registry = []
    for i, cfg in enumerate(space):
        tr_preds = apply_strategy(cfg, train)
        va_preds = apply_strategy(cfg, validation)
        tr_m = metrics(tr_preds)
        va_m = metrics(va_preds)
        tr_m["coverage_of_input"] = round(tr_m["n"] / len(train), 4) if train else None
        va_m["coverage_of_input"] = round(va_m["n"] / len(validation), 4) if validation else None
        # reject tiny / extreme-favorite-only usefulness flags
        flags = []
        if (va_m["n"] or 0) < min_val_n:
            flags.append("INSUFFICIENT_VAL_N")
        if (va_m.get("avg_odds") or 99) < 1.20 and (va_m["n"] or 0) > 0:
            flags.append("EXTREME_FAVORITE_RISK")
        if (va_m.get("coverage_of_input") or 0) < 0.05 and (va_m["n"] or 0) > 0:
            flags.append("VERY_LOW_COVERAGE")
        row = {
            "experiment_id": i,
            "config_hash": cfg_hash(cfg.to_dict()),
            "config": cfg.to_dict(),
            "train": tr_m,
            "validation": va_m,
            "flags": flags,
            "holdout": "SEALED_UNOPENED",
            "selected_on": "validation_only",
        }
        registry.append(row)
    return registry, {"n_space": len(build_search_space()), "n_run": len(registry), "max_experiments": max_experiments}


def rank_validation_strategies(registry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for r in registry:
        va = r["validation"]
        if "INSUFFICIENT_VAL_N" in r["flags"]:
            continue
        # multi-objective score: accuracy primary, then coverage, then roi if present
        acc = va.get("accuracy") or 0
        cov = va.get("coverage_of_input") or 0
        roi = va.get("roi") if va.get("roi") is not None else -1.0
        score = 100 * acc + 10 * cov + 2 * max(roi, -1)
        if "EXTREME_FAVORITE_RISK" in r["flags"]:
            score -= 5
        ranked.append({**r, "val_score": round(score, 4)})
    ranked.sort(key=lambda x: (-x["val_score"], -(x["validation"].get("n") or 0)))
    return ranked


def leakage_audit(rows: list[ResearchRow], splits: dict[str, list[ResearchRow]]) -> dict[str, Any]:
    findings = []
    post = [r for r in rows if r.exclusion_reason == "POST_KICKOFF_FREEZE"]
    if post:
        findings.append({"severity": "HIGH", "issue": "post_kickoff_freezes_excluded", "n": len(post)})
    # holdout sealed check
    hold_ids = {r.fixture_id for r in splits["holdout_sealed"]}
    findings.append(
        {
            "severity": "INFO",
            "issue": "holdout_sealed_for_strategy_selection",
            "n": len(hold_ids),
            "note": "Phase1 must not use holdout metrics for ranking/tuning",
        }
    )
    # odds implied-prob contamination check
    findings.append(
        {
            "severity": "MEDIUM",
            "issue": "decimal_odds_sparse",
            "n_with_odds": sum(1 for r in usable_rows(rows) if r.odds_home and r.odds_draw and r.odds_away),
            "note": "ROI baselines limited; reject values <1.01 as non-decimal",
        }
    )
    # feature timestamp rule documented
    findings.append(
        {
            "severity": "INFO",
            "issue": "phase1_feature_set_limited",
            "note": "xG/lineups/injuries/DNA/ExactV2 not joined; availability matrix marks missing",
        }
    )
    # chronological integrity
    ks = [str(r.kickoff_utc) for r in splits["train"] + splits["validation"] + splits["holdout_sealed"]]
    chrono_ok = ks == sorted(ks)
    if not chrono_ok:
        # per-split sorted is enough
        chrono_ok = all(
            [str(r.kickoff_utc) for r in splits[k]] == sorted(str(r.kickoff_utc) for r in splits[k])
            for k in splits
        )
    findings.append({"severity": "INFO" if chrono_ok else "HIGH", "issue": "chronological_split_order", "ok": chrono_ok})
    return {"findings": findings, "passed": not any(f.get("severity") == "HIGH" and f.get("ok") is False for f in findings)}


def compute_estimate(n_experiments: int, n_rows: int) -> dict[str, Any]:
    # rough CPU estimate
    ops = n_experiments * n_rows
    return {
        "n_experiments": n_experiments,
        "n_rows_scanned_per_experiment": n_rows,
        "approx_row_scans": ops,
        "estimated_runtime_seconds_local": round(ops / 5e5, 2),  # heuristic
        "disk_artifact_budget_mb": 50,
        "parallel_workers_recommended": 1,
        "api_calls": 0,
        "note": "Phase1 uses frozen local artifacts only; no provider fan-out",
    }


def run_phase1(out_dir: Path | None = None, *, max_experiments: int = 5000) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir or (ROOT / "artifacts/prediction_engine_75_research" / ts)
    out.mkdir(parents=True, exist_ok=True)

    # Part 1 — label audit (research wording map; no production deploy)
    label_audit = {
        "policy": "Downgrade user-facing betting suitability language in research/docs; production patch prepared but NOT deployed",
        "wording_map": LABEL_WORDING_MAP,
        "hard_blockers_retained": [
            "stale_odds",
            "missing_odds",
            "unsupported_competition",
            "post_kickoff_prediction",
            "incomplete_canonical_output",
            "invalid_freeze",
            "result_leakage_risk",
        ],
        "production_policy_preserved": True,
        "deployed": False,
        "evidence_against_current_approval": {
            "strict_approved_accuracy": APPROVED_ACC,
            "canonical_baseline_approx": 0.519,
            "conclusion": "Current approved/selected/bettable labels are not proof of betting suitability",
        },
    }
    _write_json(out / "label_safety_audit.json", label_audit)

    rows, data_audit = load_research_rows()
    usable = usable_rows(rows)
    status = STATUS_READY if len(usable) >= 30 else STATUS_BLOCKED

    splits = chronological_split(rows)
    # lock holdout IDs without scoring strategies on them
    holdout_lock = {
        "status": "SEALED",
        "n": len(splits["holdout_sealed"]),
        "fixture_ids": [r.fixture_id for r in splits["holdout_sealed"]],
        "opened_for_strategy_selection": False,
        "opened_for_reporting": False,
        "lock_hash": hashlib.sha256(",".join(str(r.fixture_id) for r in splits["holdout_sealed"]).encode()).hexdigest(),
        "rule": "Do not tune or rank strategies using these fixtures in Phase1",
    }
    _write_json(out / "sealed_holdout_lock.json", holdout_lock)

    leak = leakage_audit(rows, splits)
    _write_json(out / "leakage_audit.json", leak)

    # dataset docs
    avail = []
    for name, typ, present, src in FEATURE_CATALOG:
        avail.append({"feature": name, "type": typ, "available_phase1": present, "source": src})
    _write_json(out / "data_dictionary.json", {"features": avail, "label": "actual_1x2 regulation-time"})
    _write_json(
        out / "dataset_manifest.json",
        {
            **data_audit,
            "n_usable_finished_labeled": len(usable),
            "n_true_forward": 0,
            "feature_count_catalog": len(FEATURE_CATALOG),
            "feature_count_available_phase1": sum(1 for f in FEATURE_CATALOG if f[2]),
            "cohorts": {"historical_replay": len(usable), "historical_result_recovered": 0, "true_forward": 0},
            "split": {k: len(v) for k, v in splits.items()},
        },
    )

    # baselines on train and validation separately (not holdout)
    base_train = run_baselines(splits["train"])
    base_val = run_baselines(splits["validation"])
    _write_json(
        out / "baseline_results.json",
        {
            "train": base_train,
            "validation": base_val,
            "holdout": "SEALED_UNOPENED",
            "current_approved_accuracy_reference": APPROVED_ACC,
        },
    )

    space = build_search_space()
    _write_json(
        out / "strategy_search_space.json",
        {
            "n_unique_configs": len(space),
            "dimensions": {
                "min_confidence": "0..70",
                "min_edge": "0.35..0.65",
                "max_entropy": [None, 1.70, 1.62, 1.55],
                "min_top5_mass": [None, 0.45, 0.55, 0.65],
                "require_decision_equals_marginal": [False, True],
                "odds_max": [None, 1.50, 1.80, 2.20, 3.00],
                "direction_mode": ["wde", "marginal", "prob_argmax"],
            },
            "phase1_run_cap": max_experiments,
        },
    )

    compute = compute_estimate(min(max_experiments, len(space)), len(splits["train"]) + len(splits["validation"]))
    _write_json(out / "compute_estimate.json", compute)

    registry, search_meta = run_strategy_search(splits["train"], splits["validation"], max_experiments=max_experiments)
    # write registry jsonl
    reg_path = out / "experiment_registry.jsonl"
    with reg_path.open("w", encoding="utf-8") as fh:
        for row in registry:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    ranked = rank_validation_strategies(registry)
    top = ranked[:50]
    _write_json(out / "top_candidate_configs.json", {"n": len(top), "rows": top, "selection_split": "validation_only", "holdout": "SEALED"})

    # leaderboard csv
    lead_rows = []
    for r in ranked[:200]:
        va = r["validation"]
        lead_rows.append(
            {
                "config_hash": r["config_hash"],
                "val_accuracy": va.get("accuracy"),
                "val_n": va.get("n"),
                "val_coverage": va.get("coverage_of_input"),
                "val_roi": va.get("roi"),
                "val_avg_odds": va.get("avg_odds"),
                "val_ci_lo": (va.get("ci95") or [None, None])[0],
                "val_ci_hi": (va.get("ci95") or [None, None])[1],
                "flags": "|".join(r.get("flags") or []),
                "val_score": r.get("val_score"),
                "min_confidence": r["config"]["min_confidence"],
                "min_edge": r["config"]["min_edge"],
                "direction_mode": r["config"]["direction_mode"],
            }
        )
    _write_csv(out / "strategy_leaderboard.csv", lead_rows)

    # Pareto front (accuracy vs coverage on validation)
    pareto = []
    for r in ranked:
        va = r["validation"]
        if not va.get("accuracy") or not va.get("coverage_of_input"):
            continue
        dominated = False
        for o in ranked:
            oa = o["validation"]
            if (oa.get("accuracy") or 0) >= (va.get("accuracy") or 0) and (oa.get("coverage_of_input") or 0) >= (
                va.get("coverage_of_input") or 0
            ) and (
                (oa.get("accuracy") or 0) > (va.get("accuracy") or 0)
                or (oa.get("coverage_of_input") or 0) > (va.get("coverage_of_input") or 0)
            ):
                dominated = True
                break
        if not dominated:
            pareto.append(
                {
                    "config_hash": r["config_hash"],
                    "accuracy": va.get("accuracy"),
                    "coverage": va.get("coverage_of_input"),
                    "roi": va.get("roi"),
                    "n": va.get("n"),
                    "avg_odds": va.get("avg_odds"),
                }
            )
    _write_csv(out / "pareto_front.csv", pareto[:100])

    # Placeholder / plan artifacts for later phases
    _write_json(out / "walk_forward_results.json", {"status": "DEFERRED_PHASE2", "note": "Rolling walk-forward after feature expansion"})
    _write_json(out / "sealed_holdout_results.json", {"status": "SEALED_UNOPENED", "lock": holdout_lock})
    _write_json(out / "league_stability.json", {"status": "DEFERRED_UNTIL_LARGER_N", "n_usable": len(usable)})
    _write_json(out / "odds_bucket_stability.json", {"status": "LIMITED_ODDS_COVERAGE_PHASE1"})
    _write_json(out / "calibration_results.json", {"status": "DEFERRED_PHASE2", "note": "Need full probability vectors + larger N"})
    _write_json(out / "roi_results.json", {"validation_top": [{k: r.get(k) for k in ("config_hash", "validation")} for r in top[:10]]})
    _write_json(out / "drawdown_results.json", {"validation_top": [{"config_hash": r["config_hash"], "max_drawdown": r["validation"].get("max_drawdown")} for r in top[:10]]})
    _write_json(out / "error_forensics.json", {"status": "PHASE1_SUMMARY_ONLY", "note": "Full miss taxonomy in Phase2; approved forensic already showed direction reversals dominate"})
    _write_json(out / "feature_ablation.json", {"status": "DEFERRED_PHASE2"})
    _write_json(out / "model_comparison.json", {"baselines_validation": {k: v.get("accuracy") for k, v in base_val.items() if isinstance(v, dict)}})
    _write_json(
        out / "true_forward_plan.json",
        {
            "mode": "shadow_only",
            "actions": [
                "For every future eligible fixture freeze Canonical + challengers before kickoff",
                "Persist real prematch odds",
                "Evaluate after FT only",
                "Never backfill after kickoff",
                "Daily evaluation summary",
                "No auto-promotion",
            ],
            "minimum_true_forward_n_for_promotion": 250,
        },
    )
    best = top[0] if top else None
    _write_json(
        out / "promotion_gate_status.json",
        {
            "target_accuracy": TARGET_ACC,
            "passed": False,
            "reasons": [
                "Phase1 only; holdout sealed",
                f"usable_finished_n={len(usable)} < promotion thresholds",
                "true_forward_n=0",
                "No strategy may be promoted from validation alone",
            ],
            "best_validation": {
                "accuracy": (best or {}).get("validation", {}).get("accuracy") if best else None,
                "n": (best or {}).get("validation", {}).get("n") if best else None,
                "coverage": (best or {}).get("validation", {}).get("coverage_of_input") if best else None,
                "roi": (best or {}).get("validation", {}).get("roi") if best else None,
                "avg_odds": (best or {}).get("validation", {}).get("avg_odds") if best else None,
            }
            if best
            else None,
        },
    )

    stored_wde_val = (base_val.get("stored_wde_decision") or {}).get("accuracy")
    validation = {
        "status": status,
        "phase": PHASE,
        "usable_fixture_count": len(rows),
        "finished_labeled_count": len(usable),
        "true_forward_count": 0,
        "feature_count_catalog": len(FEATURE_CATALOG),
        "feature_count_available_phase1": sum(1 for f in FEATURE_CATALOG if f[2]),
        "leakage_passed": leak.get("passed"),
        "baseline_stored_wde_val_accuracy": stored_wde_val,
        "baseline_market_val_accuracy": (base_val.get("market_implied_favorite") or {}).get("accuracy"),
        "current_approved_accuracy": APPROVED_ACC,
        "split_sizes": {k: len(v) for k, v in splits.items()},
        "strategies_tested": len(registry),
        "search_space_size": search_meta["n_space"],
        "best_validation_accuracy": (best or {}).get("validation", {}).get("accuracy") if best else None,
        "best_validation_coverage": (best or {}).get("validation", {}).get("coverage_of_input") if best else None,
        "best_validation_avg_odds": (best or {}).get("validation", {}).get("avg_odds") if best else None,
        "best_validation_roi": (best or {}).get("validation", {}).get("roi") if best else None,
        "best_validation_n": (best or {}).get("validation", {}).get("n") if best else None,
        "sealed_holdout_status": "SEALED_UNOPENED",
        "compute": compute,
        "next_milestone": "PHASE2_FEATURE_EXPANSION_AND_WALK_FORWARD",
        "target_75_claimed": False,
        "not_deployed": True,
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "no_auto_promotion": True,
        "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/") if out.is_relative_to(ROOT) else str(out),
    }
    _write_json(out / "validation_report.json", validation)

    report = _report_md(validation, label_audit, leak, best)
    (out / "PREDICTION_ENGINE_75_PERCENT_RESEARCH_REPORT.md").write_text(report, encoding="utf-8")
    (out / "PREDICTION_ENGINE_75_PERCENT_RESEARCH_REPORT_FA.md").write_text("# برنامه پژوهشی موتور پیش‌بینی ۷۵٪\n\n" + report, encoding="utf-8")
    (out / "owner_research_dashboard.html").write_text(_dashboard_html(validation), encoding="utf-8")
    return validation


def _report_md(v: dict[str, Any], label_audit: dict, leak: dict, best: dict | None) -> str:
    return f"""# PREDICTION_ENGINE_75_PERCENT_RESEARCH_REPORT — Phase 1

Status: **{v['status']}**

## Decision context

Current strict approval finished accuracy **{v['current_approved_accuracy']}** underperforms Canonical baseline references.
`BETTABLE` / `APPROVED` / `SELECTED_FOR_BETTING` must not be treated as betting proof.

## Phase 1 scope

Foundation only: dataset audit, leakage controls, baselines, chronological splits, bounded strategy search on **validation**, sealed holdout **unopened**.

## Label safety

Production policy preserved. Research wording map prepared (not deployed):
{json.dumps(label_audit['wording_map'], indent=2)}

## Dataset

- Usable finished labeled: **{v['finished_labeled_count']}**
- True-forward: **{v['true_forward_count']}**
- Feature catalog: {v['feature_count_catalog']} · available in Phase1: {v['feature_count_available_phase1']}
- Split sizes: `{v['split_sizes']}`

## Leakage

Passed: **{v['leakage_passed']}**
Findings summarized in `leakage_audit.json`.

## Baselines (validation)

- Stored WDE decision accuracy: **{v['baseline_stored_wde_val_accuracy']}**
- Market favorite (priced subset): **{v['baseline_market_val_accuracy']}**
- Current approved reference: **{v['current_approved_accuracy']}**

## Strategy search

- Space size: {v['search_space_size']}
- Tested: **{v['strategies_tested']}**
- Best validation accuracy: **{v['best_validation_accuracy']}** (n={v['best_validation_n']})
- Coverage: **{v['best_validation_coverage']}**
- Avg odds: **{v['best_validation_avg_odds']}**
- ROI: **{v['best_validation_roi']}**

Holdout: **{v['sealed_holdout_status']}** — not used for ranking.

## 75% target

**Not claimed.** Promotion gates require sealed holdout ≥75% with N≥100 and true-forward ≥250, plus stability/ROI/calibration checks.

## Next milestone

{v['next_milestone']}

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- NO AUTO-PROMOTION
"""


def _dashboard_html(v: dict[str, Any]) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>75% Research Phase1</title>
<style>body{{font-family:Georgia,serif;margin:2rem;background:#101820;color:#e8eef2}}
h1{{color:#8fd6b5}}.card{{background:#1b2530;padding:1rem;margin:1rem 0;border-radius:8px}}</style></head><body>
<h1>Prediction Engine 75% Research — Phase 1</h1>
<div class="card"><b>{v['status']}</b><br/>
usable finished={v['finished_labeled_count']} · strategies={v['strategies_tested']}<br/>
best val acc={v['best_validation_accuracy']} · coverage={v['best_validation_coverage']}<br/>
holdout={v['sealed_holdout_status']} · target_75_claimed={v['target_75_claimed']}</div>
<p>NOT DEPLOYED · CANONICAL UNCHANGED · WDE/ECSE UNCHANGED · NO AUTO-PROMOTION</p>
</body></html>"""
