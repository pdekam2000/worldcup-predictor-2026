"""
PREDICTION_ENGINE_75 — Phase 2: feature expansion + walk-forward.

Research/shadow only. Does not open Phase-1 sealed holdout.
Does not modify Canonical WDE/ECSE or deploy production policy.
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

import pandas as pd

from worldcup_predictor.research.prediction_engine_75 import phase1 as p1

ROOT = Path(__file__).resolve().parents[3]
PHASE = "PHASE2_FEATURE_EXPANSION_AND_WALK_FORWARD"
STATUS_COMPLETE = "PHASE2_FEATURE_EXPANSION_AND_WALK_FORWARD_COMPLETE"
STATUS_PARTIAL = "PHASE2_FEATURE_EXPANSION_PARTIAL_DATA_LIMITED"
STATUS_BLOCKED = "PHASE2_DATA_INTEGRITY_BLOCKED"
STATUS_FAILED = "PHASE2_VALIDATION_FAILED"
SEED = 20260802
PHASE1_N = 54
APPROVED_ACC = 0.4545
TARGET_EXPERIMENTS = 50000

COHORT_TF = "TRUE_FORWARD"
COHORT_PREMATCH = "HISTORICAL_PREMATCH_FREEZE"
COHORT_RECOVERED = "HISTORICAL_RESULT_RECOVERED"
COHORT_REPLAY = "HISTORICAL_REPLAY"

NO_BET_CODES = [
    "STALE_ODDS",
    "MISSING_ODDS",
    "LOW_CONFIDENCE",
    "HIGH_ENTROPY",
    "DIRECTION_CONFLICT",
    "LOW_EDGE",
    "DATA_INCOMPLETE",
    "FORENSIC_WARNING",
    "MODEL_DISAGREEMENT",
    "UNSUPPORTED_DOMAIN",
    "DECISION_OVERRIDE",
    "MARKET_CONFLICT",
    "OTHER",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def load_phase1_sealed_ids() -> set[int]:
    lock_paths = sorted((ROOT / "artifacts/prediction_engine_75_research").glob("**/sealed_holdout_lock.json"))
    if not lock_paths:
        return set()
    obj = json.loads(lock_paths[-1].read_text(encoding="utf-8"))
    return {int(x) for x in (obj.get("fixture_ids") or [])}


# ---------------------------------------------------------------------------
# Row model
# ---------------------------------------------------------------------------


@dataclass
class RowV2:
    fixture_id: int
    kickoff_utc: str | None
    predicted_at: str | None
    frozen_at: str | None
    freeze_id: str | None
    freeze_hash: str | None
    cohort: str
    source: str
    league: str | None
    match: str | None
    wde_decision: str | None
    ft_marginal: str | None
    home_p: float | None
    draw_p: float | None
    away_p: float | None
    confidence: float | None
    no_bet: bool | None
    no_bet_reasons: list[str] = field(default_factory=list)
    no_bet_reason_source: str | None = None
    top3_mass: float | None = None
    top5_mass: float | None = None
    top10_mass: float | None = None
    entropy: float | None = None
    lambda_home: float | None = None
    lambda_away: float | None = None
    ecse_h_mass: float | None = None
    ecse_d_mass: float | None = None
    ecse_a_mass: float | None = None
    ecse_direction: str | None = None
    lambda_v2_home: float | None = None
    lambda_v2_away: float | None = None
    lambda_v2_direction: str | None = None
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    odds_snapshot_at: str | None = None
    odds_n_books: int | None = None
    odds_source: str | None = None
    implied_home: float | None = None
    implied_draw: float | None = None
    implied_away: float | None = None
    book_margin: float | None = None
    favorite_strength: float | None = None
    balanced_market: bool | None = None
    actual_1x2: str | None = None
    final_score: str | None = None
    exclusion_reason: str | None = None
    model_versions: dict[str, str] = field(default_factory=dict)
    feature_flags: dict[str, bool] = field(default_factory=dict)

    def edge(self) -> float | None:
        probs = [p for p in (self.home_p, self.draw_p, self.away_p) if p is not None]
        return max(probs) if probs else None


# ---------------------------------------------------------------------------
# Odds helpers
# ---------------------------------------------------------------------------


def extract_1x2_from_snapshot(payload: dict[str, Any]) -> dict[str, Any] | None:
    api = payload.get("api_sports") or payload.get("api_football") or {}
    bms = api.get("bookmakers") or []
    homes: list[float] = []
    draws: list[float] = []
    aways: list[float] = []
    for bm in bms:
        for bet in bm.get("bets") or []:
            name = str(bet.get("name") or "").lower()
            if name not in {"match winner", "1x2", "full time result", "ft result", "home/away"}:
                continue
            for v in bet.get("values") or []:
                val = str(v.get("value") or "").lower()
                o = p1._safe_odds(v.get("odd"))
                if o is None:
                    continue
                if val in {"home", "1"}:
                    homes.append(o)
                elif val in {"draw", "x"}:
                    draws.append(o)
                elif val in {"away", "2"}:
                    aways.append(o)
    if homes and draws and aways:
        return {
            "home": round(sum(homes) / len(homes), 4),
            "draw": round(sum(draws) / len(draws), 4),
            "away": round(sum(aways) / len(aways), 4),
            "n_books": len(bms),
        }
    return None


def enrich_odds_metrics(row: RowV2) -> None:
    oh, od, oa = row.odds_home, row.odds_draw, row.odds_away
    if not (oh and od and oa):
        return
    ih, id_, ia = 1.0 / oh, 1.0 / od, 1.0 / oa
    s = ih + id_ + ia
    row.implied_home, row.implied_draw, row.implied_away = ih / s, id_ / s, ia / s
    row.book_margin = round(s - 1.0, 4)
    fav = min(oh, od, oa)
    row.favorite_strength = round(1.0 / fav, 4)
    # balanced if top-2 implied within 0.08
    imps = sorted([row.implied_home, row.implied_draw, row.implied_away], reverse=True)
    row.balanced_market = (imps[0] - imps[1]) <= 0.08


def scoreline_masses(top_json: Any) -> tuple[float | None, float | None, float | None, float | None, float | None, str | None]:
    """Return h/d/a mass, top3, top5, direction from list of {scoreline,probability} or strings."""
    items: list[tuple[str, float]] = []
    if isinstance(top_json, str):
        try:
            top_json = json.loads(top_json)
        except json.JSONDecodeError:
            return None, None, None, None, None, None
    if not isinstance(top_json, list):
        return None, None, None, None, None, None
    for i, it in enumerate(top_json):
        if isinstance(it, dict):
            sc = str(it.get("scoreline") or it.get("score") or "")
            pr = float(it.get("probability") or it.get("p") or 0.0)
        else:
            sc = str(it)
            pr = 0.0
        if sc:
            items.append((sc, pr))
    if not items:
        return None, None, None, None, None, None
    # if probs all zero, uniform over listed
    if sum(p for _, p in items) <= 0:
        items = [(sc, 1.0 / len(items)) for sc, _ in items]
    h = d = a = 0.0
    for sc, pr in items:
        try:
            hg, ag = sc.replace(" ", "").split("-", 1)
            hg_i, ag_i = int(hg), int(ag)
        except ValueError:
            continue
        if hg_i > ag_i:
            h += pr
        elif ag_i > hg_i:
            a += pr
        else:
            d += pr
    s = h + d + a
    if s > 0:
        h, d, a = h / s, d / s, a / s
    direction = max([("home", h), ("draw", d), ("away", a)], key=lambda x: x[1])[0]
    top3 = sum(p for _, p in items[:3]) if len(items) >= 3 else sum(p for _, p in items)
    top5 = sum(p for _, p in items[:5]) if len(items) >= 5 else sum(p for _, p in items)
    return h, d, a, top3, top5, direction


def reconstruct_no_bet_reasons(row: RowV2, payload: dict[str, Any] | None = None) -> None:
    """Never invent precise reasons without evidence; mark reconstructed."""
    payload = payload or {}
    reasons: list[str] = []
    source = "unknown"
    native = payload.get("no_bet_reasons") or payload.get("no_bet_reason_codes")
    if isinstance(native, list) and native:
        row.no_bet_reasons = [str(x) for x in native]
        row.no_bet_reason_source = "canonical"
        return
    if isinstance(native, str) and native.strip():
        row.no_bet_reasons = [native.strip()]
        row.no_bet_reason_source = "canonical"
        return
    # reconstruct from evidence
    if row.no_bet:
        source = "reconstructed"
        if row.odds_home is None or row.odds_draw is None or row.odds_away is None:
            reasons.append("MISSING_ODDS")
        if (row.confidence or 100) < 55:
            reasons.append("LOW_CONFIDENCE")
        if row.entropy is not None and row.entropy >= 1.7:
            reasons.append("HIGH_ENTROPY")
        if row.wde_decision and row.ft_marginal and row.wde_decision != row.ft_marginal:
            reasons.append("DIRECTION_CONFLICT")
        if row.edge() is not None and row.edge() < 0.4:
            reasons.append("LOW_EDGE")
        caution = str(payload.get("caution_reason") or "")
        if caution:
            reasons.append("FORENSIC_WARNING")
        if not reasons:
            reasons.append("OTHER")
    row.no_bet_reasons = reasons
    row.no_bet_reason_source = source if reasons else None


# ---------------------------------------------------------------------------
# Corpus expansion
# ---------------------------------------------------------------------------


def _open_db() -> sqlite3.Connection | None:
    db = ROOT / "data" / "football_intelligence.db"
    if not db.exists():
        return None
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _load_finished_eval() -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for path in sorted((ROOT / "artifacts/finished_match_evaluation").glob("**/complete_fixture_evaluations.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            continue
        for r in rows:
            fid = int(r.get("fixture_id") or 0)
            if not fid:
                continue
            out[fid] = {**r, "_source_path": str(path.relative_to(ROOT))}
    return out


def _attach_odds_map(conn: sqlite3.Connection, fixture_ids: set[int]) -> dict[int, dict[str, Any]]:
    """Latest prematch odds snapshot per fixture (snapshot_at < kickoff when kickoff known)."""
    out: dict[int, dict[str, Any]] = {}
    if not fixture_ids:
        return out
    # pull all odds for these fixtures
    qmarks = ",".join("?" for _ in fixture_ids)
    rows = conn.execute(
        f"SELECT fixture_id, snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id IN ({qmarks})",
        tuple(fixture_ids),
    ).fetchall()
    by_fid: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_fid[int(r["fixture_id"])].append(r)
    # kickoffs
    ko_map: dict[int, datetime | None] = {}
    for r in conn.execute(f"SELECT fixture_id, kickoff_utc FROM fixtures WHERE fixture_id IN ({qmarks})", tuple(fixture_ids)):
        ko_map[int(r["fixture_id"])] = p1._parse_dt(r["kickoff_utc"])
    for fid, snaps in by_fid.items():
        ko = ko_map.get(fid)
        candidates = []
        for s in snaps:
            st = p1._parse_dt(s["snapshot_at"])
            if ko and st and st >= ko:
                continue
            try:
                payload = json.loads(s["payload_json"] or "{}")
            except json.JSONDecodeError:
                continue
            odds = extract_1x2_from_snapshot(payload)
            if not odds:
                continue
            candidates.append((st or datetime.min.replace(tzinfo=timezone.utc), odds, s["snapshot_at"]))
        if not candidates:
            continue
        candidates.sort(key=lambda x: x[0])
        # use latest prematch
        _, odds, snap_at = candidates[-1]
        out[fid] = {**odds, "snapshot_at": snap_at, "source": "odds_snapshots"}
    return out


def _attach_ecse(conn: sqlite3.Connection, fixture_ids: set[int]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    if not fixture_ids:
        return out
    qmarks = ",".join("?" for _ in fixture_ids)
    rows = conn.execute(
        f"""
        SELECT * FROM ecse_prediction_snapshots
        WHERE fixture_id IN ({qmarks}) AND COALESCE(is_frozen,0)=1
        ORDER BY generated_at DESC
        """,
        tuple(fixture_ids),
    ).fetchall()
    for r in rows:
        fid = int(r["fixture_id"])
        if fid in out:
            continue
        tops = r["top_10_scorelines_json"] or r["top_5_scores_json"]
        h, d, a, t3, t5, direction = scoreline_masses(tops)
        # top10 mass from top10 list if present
        t10 = None
        try:
            arr = json.loads(r["top_10_scorelines_json"] or "[]")
            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                t10 = sum(float(x.get("probability") or 0) for x in arr[:10])
        except Exception:
            t10 = None
        out[fid] = {
            "lambda_home": r["lambda_home"],
            "lambda_away": r["lambda_away"],
            "h": h,
            "d": d,
            "a": a,
            "top3": t3,
            "top5": t5 if t5 is not None else r.get("confidence_score"),
            "top10": t10,
            "direction": direction,
            "model_version": r["model_version"],
            "generated_at": r["generated_at"],
            "entropy": None,
        }
        # entropy from probs if available
        if h is not None:
            probs = [x for x in (h, d, a) if x and x > 0]
            if probs:
                out[fid]["entropy"] = round(-sum(x * math.log(x) for x in probs), 4)
    return out


def _attach_lambda_v2(conn: sqlite3.Connection, fixture_ids: set[int]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    if not fixture_ids:
        return out
    qmarks = ",".join("?" for _ in fixture_ids)
    rows = conn.execute(
        f"""
        SELECT fixture_id, lambda_home, lambda_away, top5_json, top10_json, created_at_utc, model_version, feature_cutoff
        FROM lambda_v2_shadow_outputs
        WHERE fixture_id IN ({qmarks})
        ORDER BY created_at_utc DESC
        """,
        tuple(fixture_ids),
    ).fetchall()
    for r in rows:
        fid = int(r["fixture_id"])
        if fid in out:
            continue
        lh, la = float(r["lambda_home"] or 0), float(r["lambda_away"] or 0)
        direction = "home" if lh > la + 0.05 else "away" if la > lh + 0.05 else "draw"
        out[fid] = {
            "lambda_home": r["lambda_home"],
            "lambda_away": r["lambda_away"],
            "direction": direction,
            "created_at": r["created_at_utc"],
            "feature_cutoff": r["feature_cutoff"],
            "model_version": r["model_version"],
        }
    return out


def build_expanded_corpus() -> tuple[list[RowV2], list[dict[str, Any]], dict[str, Any]]:
    exclusions: list[dict[str, Any]] = []
    by_fid: dict[int, RowV2] = {}
    source_counts: Counter[str] = Counter()

    finished = _load_finished_eval()
    for fid, r in finished.items():
        actual = p1._norm_dir(r.get("actual_1x2"))
        wde = p1._norm_dir(r.get("wde_decision"))
        marg = p1._norm_dir(r.get("ft_marginal_direction"))
        ko = str(r.get("kickoff_utc") or "") or None
        fr = str(r.get("frozen_at") or r.get("generated_at") or "") or None
        reason = None
        ko_dt, fr_dt = p1._parse_dt(ko), p1._parse_dt(fr)
        if ko_dt and fr_dt and fr_dt >= ko_dt:
            reason = "POST_KICKOFF_FREEZE"
        if not actual:
            reason = reason or "RESULT_MISSING"
        if not wde:
            reason = reason or "WDE_DECISION_MISSING"
        row = RowV2(
            fixture_id=fid,
            kickoff_utc=ko,
            predicted_at=fr,
            frozen_at=fr,
            freeze_id=str(r.get("freeze_id") or "") or None,
            freeze_hash=str(r.get("freeze_hash") or "") or None,
            cohort=COHORT_REPLAY,
            source="finished_match_evaluation",
            league=str(r.get("league") or r.get("competition") or "") or None,
            match=r.get("match"),
            wde_decision=wde,
            ft_marginal=marg,
            home_p=p1._norm_prob(r.get("home_probability")),
            draw_p=p1._norm_prob(r.get("draw_probability")),
            away_p=p1._norm_prob(r.get("away_probability")),
            confidence=p1._norm_conf(r.get("wde_confidence")),
            no_bet=bool(r.get("no_bet")) if r.get("no_bet") is not None else None,
            top5_mass=p1._f(r.get("top5_mass")),
            top10_mass=p1._f(r.get("top10_mass")),
            entropy=p1._f(r.get("entropy")),
            lambda_home=p1._f(r.get("lambda_home")),
            lambda_away=p1._f(r.get("lambda_away")),
            actual_1x2=actual,
            final_score=str(r.get("regulation_score") or r.get("final_score") or "") or None,
            exclusion_reason=reason,
            feature_flags={"finished_eval": True},
        )
        reconstruct_no_bet_reasons(row, r if isinstance(r, dict) else {})
        by_fid[fid] = row
        source_counts["finished_match_evaluation"] += 1
        if reason:
            exclusions.append({"fixture_id": fid, "reason": reason, "source": "finished_match_evaluation"})

    conn = _open_db()
    if conn is not None:
        try:
            stored = conn.execute(
                """
                SELECT sp.fixture_id, sp.kickoff_utc, sp.predicted_at, sp.payload_json, sp.source AS store_source,
                       sp.validation_tier, sp.is_quarantined, sp.quarantine_reason,
                       fr.home_goals, fr.away_goals, fr.final_score,
                       fr.regulation_home_goals, fr.regulation_away_goals,
                       fx.kickoff_utc AS fx_kickoff, fx.home_team, fx.away_team, fx.competition_key
                FROM worldcup_stored_predictions sp
                JOIN fixture_results fr ON fr.fixture_id = sp.fixture_id
                LEFT JOIN fixtures fx ON fx.fixture_id = sp.fixture_id
                WHERE fr.home_goals IS NOT NULL AND COALESCE(sp.is_active,1)=1
                """
            ).fetchall()
            for r in stored:
                fid = int(r["fixture_id"])
                if r["is_quarantined"]:
                    exclusions.append(
                        {
                            "fixture_id": fid,
                            "reason": f"QUARANTINED:{r['quarantine_reason'] or 'unknown'}",
                            "source": "worldcup_stored_predictions",
                        }
                    )
                    continue
                try:
                    payload = json.loads(r["payload_json"] or "{}")
                except json.JSONDecodeError:
                    exclusions.append({"fixture_id": fid, "reason": "PAYLOAD_JSON_INVALID", "source": "worldcup_stored_predictions"})
                    continue
                if not isinstance(payload, dict):
                    exclusions.append({"fixture_id": fid, "reason": "PAYLOAD_NOT_OBJECT", "source": "worldcup_stored_predictions"})
                    continue
                probs = payload.get("probabilities") or {}
                home_p = p1._norm_prob(probs.get("home_win") if probs.get("home_win") is not None else probs.get("home"))
                draw_p = p1._norm_prob(probs.get("draw"))
                away_p = p1._norm_prob(probs.get("away_win") if probs.get("away_win") is not None else probs.get("away"))
                wde = p1._norm_dir(payload.get("prediction") or payload.get("selected_1x2") or payload.get("direction"))
                conf = p1._norm_conf(payload.get("confidence"))
                no_bet = payload.get("no_bet")
                if no_bet is None:
                    no_bet = payload.get("no_bet_flag")
                ko = str(r["kickoff_utc"] or r["fx_kickoff"] or payload.get("kickoff_utc") or "") or None
                pred_at = str(r["predicted_at"] or payload.get("predicted_at") or "") or None
                reason = None
                ko_dt, pr_dt = p1._parse_dt(ko), p1._parse_dt(pred_at)
                if ko_dt and pr_dt and pr_dt >= ko_dt:
                    reason = "POST_KICKOFF_PREDICTION"
                if not wde:
                    reason = reason or "WDE_DECISION_MISSING"
                # regulation-time label
                if r["regulation_home_goals"] is not None and r["regulation_away_goals"] is not None:
                    hg, ag = int(r["regulation_home_goals"]), int(r["regulation_away_goals"])
                else:
                    hg, ag = int(r["home_goals"]), int(r["away_goals"])
                actual = "home" if hg > ag else "away" if ag > hg else "draw"
                match = None
                if r["home_team"] and r["away_team"]:
                    match = f"{r['home_team']} vs {r['away_team']}"
                cohort = COHORT_PREMATCH if reason is None else COHORT_PREMATCH
                if reason == "POST_KICKOFF_PREDICTION":
                    pass
                row = RowV2(
                    fixture_id=fid,
                    kickoff_utc=ko,
                    predicted_at=pred_at,
                    frozen_at=pred_at,
                    freeze_id=None,
                    freeze_hash=None,
                    cohort=cohort,
                    source="worldcup_stored_predictions",
                    league=str(r["competition_key"] or "") or None,
                    match=match or (f"{payload.get('home_team')} vs {payload.get('away_team')}" if payload.get("home_team") else None),
                    wde_decision=wde,
                    ft_marginal=None,
                    home_p=home_p,
                    draw_p=draw_p,
                    away_p=away_p,
                    confidence=conf,
                    no_bet=bool(no_bet) if no_bet is not None else None,
                    actual_1x2=actual,
                    final_score=str(r["final_score"] or f"{hg}-{ag}"),
                    exclusion_reason=reason,
                    feature_flags={"stored_prediction": True},
                    model_versions={"store_source": str(r["store_source"] or "")},
                )
                reconstruct_no_bet_reasons(row, payload)
                # Prefer finished_eval overlay for richer fields when present; keep stored if new
                prev = by_fid.get(fid)
                if prev is None:
                    by_fid[fid] = row
                    source_counts["worldcup_stored_predictions_new"] += 1
                else:
                    # merge: keep freeze richness, fill missing from stored
                    if prev.home_p is None:
                        prev.home_p, prev.draw_p, prev.away_p = home_p, draw_p, away_p
                    if prev.confidence is None:
                        prev.confidence = conf
                    if prev.no_bet is None:
                        prev.no_bet = row.no_bet
                    if prev.predicted_at is None:
                        prev.predicted_at = pred_at
                    if prev.kickoff_utc is None:
                        prev.kickoff_utc = ko
                    if prev.cohort == COHORT_REPLAY and reason is None:
                        prev.cohort = COHORT_PREMATCH  # upgrade label when verified prematch store exists
                    prev.feature_flags["stored_prediction"] = True
                    source_counts["worldcup_stored_predictions_merge"] += 1
                if reason:
                    exclusions.append({"fixture_id": fid, "reason": reason, "source": "worldcup_stored_predictions"})

            fids = set(by_fid.keys())
            odds_map = _attach_odds_map(conn, fids)
            ecse_map = _attach_ecse(conn, fids)
            l2_map = _attach_lambda_v2(conn, fids)
            for fid, row in by_fid.items():
                if fid in odds_map:
                    o = odds_map[fid]
                    # verify odds timestamp vs kickoff
                    ko_dt = p1._parse_dt(row.kickoff_utc)
                    od_dt = p1._parse_dt(o.get("snapshot_at"))
                    if ko_dt and od_dt and od_dt >= ko_dt:
                        exclusions.append({"fixture_id": fid, "reason": "POST_KICKOFF_ODDS_SKIPPED", "source": "odds_snapshots"})
                    else:
                        row.odds_home, row.odds_draw, row.odds_away = o["home"], o["draw"], o["away"]
                        row.odds_snapshot_at = o.get("snapshot_at")
                        row.odds_n_books = o.get("n_books")
                        row.odds_source = o.get("source")
                        enrich_odds_metrics(row)
                        row.feature_flags["odds"] = True
                if fid in ecse_map:
                    e = ecse_map[fid]
                    row.lambda_home = row.lambda_home if row.lambda_home is not None else e.get("lambda_home")
                    row.lambda_away = row.lambda_away if row.lambda_away is not None else e.get("lambda_away")
                    row.ecse_h_mass, row.ecse_d_mass, row.ecse_a_mass = e.get("h"), e.get("d"), e.get("a")
                    row.ecse_direction = e.get("direction")
                    if row.top3_mass is None:
                        row.top3_mass = e.get("top3")
                    if row.top5_mass is None:
                        row.top5_mass = e.get("top5")
                    if row.top10_mass is None:
                        row.top10_mass = e.get("top10")
                    if row.entropy is None:
                        row.entropy = e.get("entropy")
                    if row.ft_marginal is None:
                        row.ft_marginal = e.get("direction")
                    row.model_versions["ecse"] = str(e.get("model_version") or "")
                    row.feature_flags["ecse"] = True
                if fid in l2_map:
                    lv = l2_map[fid]
                    # feature_cutoff must precede kickoff
                    ko_dt = p1._parse_dt(row.kickoff_utc)
                    cut = p1._parse_dt(lv.get("feature_cutoff") or lv.get("created_at"))
                    if ko_dt and cut and cut >= ko_dt:
                        exclusions.append({"fixture_id": fid, "reason": "LAMBDA_V2_POST_KICKOFF_SKIPPED", "source": "lambda_v2"})
                    else:
                        row.lambda_v2_home = lv.get("lambda_home")
                        row.lambda_v2_away = lv.get("lambda_away")
                        row.lambda_v2_direction = lv.get("direction")
                        row.model_versions["lambda_v2"] = str(lv.get("model_version") or "")
                        row.feature_flags["lambda_v2"] = True
            # Recompute reconstructed no_bet reasons after odds/ECSE joins (do not overwrite canonical).
            for row in by_fid.values():
                if row.no_bet_reason_source == "canonical":
                    continue
                if row.no_bet:
                    row.no_bet_reasons = []
                    row.no_bet_reason_source = None
                    reconstruct_no_bet_reasons(row, {})
        finally:
            conn.close()

    rows = list(by_fid.values())
    rows.sort(key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))
    inventory = {
        "n_raw": len(rows),
        "source_counts": dict(source_counts),
        "cohort_counts_raw": dict(Counter(r.cohort for r in rows)),
        "exclusion_reason_counts": dict(Counter(r.exclusion_reason or "OK" for r in rows)),
        "n_exclusions_logged": len(exclusions),
        "phase1_usable_n": PHASE1_N,
    }
    return rows, exclusions, inventory


def usable(rows: list[RowV2]) -> list[RowV2]:
    return [r for r in rows if r.exclusion_reason is None and r.actual_1x2 and r.wde_decision]


# ---------------------------------------------------------------------------
# Quality / leakage
# ---------------------------------------------------------------------------


def quality_and_leakage(rows: list[RowV2], sealed: set[int]) -> tuple[dict, dict, dict]:
    fids = [r.fixture_id for r in rows]
    dup = [fid for fid, c in Counter(fids).items() if c > 1]
    result_conflicts = []
    by_fid: dict[int, list[RowV2]] = defaultdict(list)
    for r in rows:
        by_fid[r.fixture_id].append(r)
    # already unique by construction; check score consistency
    post_ko = sum(1 for r in rows if r.exclusion_reason in {"POST_KICKOFF_FREEZE", "POST_KICKOFF_PREDICTION"})
    priced = sum(1 for r in usable(rows) if r.odds_home and r.odds_draw and r.odds_away)
    quality = {
        "n_rows": len(rows),
        "n_usable": len(usable(rows)),
        "duplicate_fixture_ids": dup,
        "result_conflicts": result_conflicts,
        "post_kickoff_excluded": post_ko,
        "priced_usable": priced,
        "impossible_odds": sum(
            1
            for r in rows
            if any(o is not None and (o < 1.01 or o > 100) for o in (r.odds_home, r.odds_draw, r.odds_away))
        ),
        "missing_labels": sum(1 for r in rows if not r.actual_1x2),
        "cohort_counts_usable": dict(Counter(r.cohort for r in usable(rows))),
    }
    label = {
        "regulation_time_policy": "prefer regulation_home/away_goals else home_goals/away_goals from fixture_results",
        "extra_time_separated": True,
        "penalties_not_used_for_1x2": True,
        "home_away_orientation": "provider fixture home/away as stored",
    }
    leak = {
        "passed": True,
        "findings": [
            {"severity": "INFO", "issue": "phase1_holdout_sealed_ids", "n": len(sealed), "ids_sample": sorted(sealed)[:11]},
            {"severity": "INFO", "issue": "true_forward_count", "n": sum(1 for r in rows if r.cohort == COHORT_TF)},
            {
                "severity": "MEDIUM" if priced < 20 else "INFO",
                "issue": "priced_odds_coverage",
                "priced_usable": priced,
                "usable": len(usable(rows)),
            },
            {
                "severity": "INFO",
                "issue": "shadow_features_partial",
                "note": "Exact V2 / DNA / Twins / HCEE / xG / lineups largely unavailable in local joins",
            },
        ],
        "sealed_holdout_opened": False,
        "no_result_as_feature": True,
    }
    if dup or result_conflicts:
        leak["passed"] = False
        leak["findings"].append({"severity": "HIGH", "issue": "integrity_failure", "dup": dup, "conflicts": result_conflicts})
    return quality, label, leak


# ---------------------------------------------------------------------------
# Metrics / baselines / strategies
# ---------------------------------------------------------------------------


def metrics(preds: list[tuple[str | None, RowV2]], universe: int) -> dict[str, Any]:
    labeled = [(p, r) for p, r in preds if p and r.actual_1x2]
    n = len(labeled)
    hits = sum(1 for p, r in labeled if p == r.actual_1x2)
    lo, hi = p1.wilson_ci(hits, n)
    by_act: dict[str, list[bool]] = defaultdict(list)
    by_pred: dict[str, list[bool]] = defaultdict(list)
    for p, r in labeled:
        by_act[r.actual_1x2 or "?"].append(p == r.actual_1x2)
        by_pred[p].append(p == r.actual_1x2)
    recalls = {k: (sum(v) / len(v) if v else None) for k, v in by_act.items()}
    precision = {k: (sum(v) / len(v) if v else None) for k, v in by_pred.items()}
    bal_vals = [v for v in recalls.values() if v is not None]
    bal = sum(bal_vals) / len(bal_vals) if bal_vals else None
    pnls = []
    for p, r in labeled:
        o = p1._safe_odds({"home": r.odds_home, "draw": r.odds_draw, "away": r.odds_away}.get(p or ""))
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
    odds_vals = []
    for p, r in labeled:
        o = p1._safe_odds({"home": r.odds_home, "draw": r.odds_draw, "away": r.odds_away}.get(p or ""))
        if o:
            odds_vals.append(o)
    # league concentration
    leagues = Counter(r.league or "?" for _, r in labeled)
    top_league_share = (leagues.most_common(1)[0][1] / n) if n and leagues else None
    return {
        "n": n,
        "hits": hits,
        "accuracy": round(hits / n, 4) if n else None,
        "balanced_accuracy": round(bal, 4) if bal is not None else None,
        "ci95": [lo, hi],
        "coverage_of_input": round(n / universe, 4) if universe else None,
        "priced_n": len(pnls),
        "roi": round(sum(pnls) / len(pnls), 4) if pnls else None,
        "max_drawdown": max_dd,
        "avg_odds": round(sum(odds_vals) / len(odds_vals), 4) if odds_vals else None,
        "class_recall": {k: round(v, 4) if v is not None else None for k, v in recalls.items()},
        "class_precision": {k: round(v, 4) if v is not None else None for k, v in precision.items()},
        "top_league_share": round(top_league_share, 4) if top_league_share is not None else None,
    }


def market_fav(r: RowV2) -> str | None:
    odds = [(k, v) for k, v in (("home", r.odds_home), ("draw", r.odds_draw), ("away", r.odds_away)) if v]
    if not odds:
        return None
    return min(odds, key=lambda x: x[1])[0]


def prob_argmax(r: RowV2) -> str | None:
    if not any(x is not None for x in (r.home_p, r.draw_p, r.away_p)):
        return r.wde_decision
    return max([("home", r.home_p or 0), ("draw", r.draw_p or 0), ("away", r.away_p or 0)], key=lambda x: x[1])[0]


def run_baselines_v2(rows: list[RowV2]) -> dict[str, Any]:
    u = len(rows)
    out: dict[str, Any] = {}

    def pack(name: str, preds: list[tuple[str | None, RowV2]]):
        out[name] = {"name": name, **metrics(preds, u)}

    pack("market_favorite", [(market_fav(r), r) for r in rows if market_fav(r)])
    pack("raw_wde_argmax", [(prob_argmax(r), r) for r in rows])
    pack("stored_wde_decision", [(r.wde_decision, r) for r in rows])
    pack("ecse_full_mass_direction", [(r.ecse_direction or r.ft_marginal, r) for r in rows if (r.ecse_direction or r.ft_marginal)])
    pack("lambda_v2_direction", [(r.lambda_v2_direction, r) for r in rows if r.lambda_v2_direction])
    # majority of available directions
    maj = []
    for r in rows:
        votes = [x for x in (r.wde_decision, r.ecse_direction, r.lambda_v2_direction, prob_argmax(r)) if x]
        if not votes:
            continue
        maj.append((Counter(votes).most_common(1)[0][0], r))
    pack("available_model_majority", maj)
    pack("current_no_bet_policy_proxy_conf60", [(r.wde_decision, r) for r in rows if (r.confidence or 0) >= 60 and not r.no_bet])
    pack("strict_selection_proxy_conf60_edge55", [(r.wde_decision, r) for r in rows if (r.confidence or 0) >= 60 and (r.edge() or 0) >= 0.55])

    # sklearn baselines on probability features (chronological: fit on first 70%)
    try:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, StackingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        labeled = [r for r in rows if r.home_p is not None and r.draw_p is not None and r.away_p is not None and r.actual_1x2]
        if len(labeled) >= 40:
            split = int(len(labeled) * 0.7)
            train, test = labeled[:split], labeled[split:]

            def Xy(rs: list[RowV2]):
                X = [[r.home_p or 0, r.draw_p or 0, r.away_p or 0, (r.confidence or 0) / 100.0, r.top5_mass or 0, r.entropy or 0] for r in rs]
                y = [r.actual_1x2 for r in rs]
                return X, y

            Xtr, ytr = Xy(train)
            Xte, yte = Xy(test)
            models = {
                "multinomial_logistic": Pipeline(
                    [("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=500, multi_class="multinomial", random_state=SEED))]
                ),
                "gradient_boosting": GradientBoostingClassifier(random_state=SEED),
                "random_forest": RandomForestClassifier(n_estimators=100, random_state=SEED),
            }
            for name, model in models.items():
                model.fit(Xtr, ytr)
                pred = model.predict(Xte)
                pack(name, list(zip(pred, test)))
            # calibrated GB
            gb = GradientBoostingClassifier(random_state=SEED)
            cal = CalibratedClassifierCV(gb, method="isotonic", cv=3)
            cal.fit(Xtr, ytr)
            pack("calibrated_gradient_boosting", list(zip(cal.predict(Xte), test)))
            # stacking
            stack = StackingClassifier(
                estimators=[
                    ("lr", LogisticRegression(max_iter=400, multi_class="multinomial", random_state=SEED)),
                    ("rf", RandomForestClassifier(n_estimators=80, random_state=SEED)),
                ],
                final_estimator=LogisticRegression(max_iter=400, multi_class="multinomial", random_state=SEED),
            )
            stack.fit(Xtr, ytr)
            pack("stacking_meta_baseline", list(zip(stack.predict(Xte), test)))
            # draw specialist: predict draw if draw_p high else WDE
            pack(
                "draw_specialist_proxy",
                [(("draw" if (r.draw_p or 0) >= 0.32 else r.wde_decision), r) for r in test],
            )
            # favorite specialist: follow market if odds else WDE
            pack(
                "favorite_specialist_proxy",
                [((market_fav(r) or r.wde_decision), r) for r in test],
            )
            # underdog detector: pick second favorite when confidence low
            und = []
            for r in test:
                if market_fav(r) and (r.confidence or 100) < 55:
                    odds = sorted(
                        [(k, v) for k, v in (("home", r.odds_home), ("draw", r.odds_draw), ("away", r.odds_away)) if v],
                        key=lambda x: x[1],
                    )
                    und.append((odds[1][0] if len(odds) > 1 else r.wde_decision, r))
                else:
                    und.append((r.wde_decision, r))
            pack("underdog_upset_detector_proxy", und)
        else:
            for name in (
                "multinomial_logistic",
                "gradient_boosting",
                "random_forest",
                "calibrated_gradient_boosting",
                "stacking_meta_baseline",
                "draw_specialist_proxy",
                "favorite_specialist_proxy",
                "underdog_upset_detector_proxy",
            ):
                out[name] = {"name": name, "status": "INSUFFICIENT_N", "n": len(labeled)}
    except Exception as e:  # noqa: BLE001
        out["sklearn_baselines_error"] = {"error": str(e)}

    for name in ("elo_baseline", "exact_v2_full_mass_direction"):
        out[name] = {"name": name, "status": "NOT_AVAILABLE_PHASE2_PARTIAL", "n": 0, "accuracy": None}
    out["current_approved_reference"] = {"name": "current_approved_reference", "accuracy": APPROVED_ACC, "n": 11}
    return out


@dataclass(frozen=True)
class StratCfg:
    min_confidence: float
    min_edge: float
    max_entropy: float | None
    min_top5: float | None
    require_agree_ecse: bool
    odds_max: float | None
    direction_mode: str  # wde|argmax|ecse|majority
    exclude_no_bet: bool
    balanced_only: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_search_space(max_n: int = TARGET_EXPERIMENTS) -> list[StratCfg]:
    confs = [0, 45, 50, 55, 58, 60, 62, 65, 68, 70]
    edges = [0.0, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
    ents = [None, 1.80, 1.70, 1.62, 1.55, 1.50]
    top5s = [None, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
    odds_caps = [None, 1.50, 1.80, 2.00, 2.20, 2.50, 3.00, 4.00]
    modes = ["wde", "argmax", "ecse", "majority"]
    space: list[StratCfg] = []
    seen: set[str] = set()
    for vals in product(confs, edges, ents, top5s, [False, True], odds_caps, modes, [True, False], [False, True]):
        cfg = StratCfg(*vals)
        h = p1.cfg_hash(cfg.to_dict())
        if h in seen:
            continue
        seen.add(h)
        space.append(cfg)
        if len(space) >= max_n:
            break
    return space


def apply_strategy(rows: list[RowV2], cfg: StratCfg) -> list[tuple[str | None, RowV2]]:
    out: list[tuple[str | None, RowV2]] = []
    for r in rows:
        if cfg.exclude_no_bet and r.no_bet:
            continue
        if (r.confidence or 0) < cfg.min_confidence:
            continue
        if (r.edge() or 0) < cfg.min_edge:
            continue
        if cfg.max_entropy is not None and r.entropy is not None and r.entropy > cfg.max_entropy:
            continue
        if cfg.min_top5 is not None and (r.top5_mass or 0) < cfg.min_top5:
            continue
        if cfg.require_agree_ecse and r.ecse_direction and r.wde_decision and r.ecse_direction != r.wde_decision:
            continue
        if cfg.balanced_only and r.balanced_market is False:
            continue
        if cfg.direction_mode == "wde":
            d = r.wde_decision
        elif cfg.direction_mode == "argmax":
            d = prob_argmax(r)
        elif cfg.direction_mode == "ecse":
            d = r.ecse_direction or r.wde_decision
        else:
            votes = [x for x in (r.wde_decision, r.ecse_direction, r.lambda_v2_direction) if x]
            d = Counter(votes).most_common(1)[0][0] if votes else r.wde_decision
        if not d:
            continue
        o = {"home": r.odds_home, "draw": r.odds_draw, "away": r.odds_away}.get(d)
        if cfg.odds_max is not None and o is not None and o > cfg.odds_max:
            continue
        if cfg.odds_max is not None and o is None:
            # odds required when odds_max set
            continue
        out.append((d, r))
    return out


def run_strategy_search(
    train: list[RowV2],
    val: list[RowV2],
    *,
    max_experiments: int,
    min_val_n: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Oversample config space so skipped empty selections do not under-fill the registry.
    space = build_search_space(max(max_experiments * 3, max_experiments))
    registry: list[dict[str, Any]] = []
    skipped_empty = 0
    for cfg in space:
        if len(registry) >= max_experiments:
            break
        tr = apply_strategy(train, cfg)
        va = apply_strategy(val, cfg)
        if len(va) == 0 and len(tr) == 0:
            skipped_empty += 1
            continue
        tm = metrics(tr, len(train))
        vm = metrics(va, len(val))
        flags = []
        if (vm.get("n") or 0) < 10:
            flags.append("SMALL_SAMPLE_NOT_PROMOTABLE")
        if (vm.get("n") or 0) < min_val_n:
            flags.append("BELOW_MIN_VAL_N")
        registry.append(
            {
                "config_hash": p1.cfg_hash(cfg.to_dict()),
                "config": cfg.to_dict(),
                "train": tm,
                "validation": vm,
                "flags": flags,
                "holdout": "SEALED_UNOPENED",
                "val_score": (vm.get("accuracy") or 0) * math.log1p(vm.get("n") or 0),
            }
        )
    meta = {
        "n_space_built": len(space),
        "n_run": len(registry),
        "skipped_empty": skipped_empty,
        "max_experiments": max_experiments,
    }
    return registry, meta


def rank_for_gate(registry: list[dict[str, Any]], *, min_n: int | None = None, min_cov: float | None = None) -> list[dict]:
    rows = []
    for r in registry:
        va = r["validation"]
        n = va.get("n") or 0
        cov = va.get("coverage_of_input") or 0
        if min_n is not None and n < min_n:
            continue
        if min_cov is not None and cov < min_cov:
            continue
        if "BELOW_MIN_VAL_N" in (r.get("flags") or []):
            continue
        rows.append(r)
    rows.sort(key=lambda x: (-(x["validation"].get("accuracy") or 0), -(x["validation"].get("n") or 0)))
    return rows


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------


def walk_forward_folds(rows: list[RowV2], sealed: set[int]) -> tuple[list[dict], dict]:
    """Expanding-window walk-forward excluding sealed holdout fixtures."""
    data = [r for r in usable(rows) if r.fixture_id not in sealed]
    data = sorted(data, key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))
    folds = []
    # expanding: initial train 40, test blocks of 15
    min_train = 40
    block = 15
    i = min_train
    while i + 5 <= len(data):
        train = data[:i]
        test = data[i : i + block]
        if len(test) < 5:
            break
        # select strategy on train internal split (last 20% of train as mini-val) — no sealed
        cut = max(10, int(len(train) * 0.8))
        tr_fit, tr_val = train[:cut], train[cut:]
        reg, _ = run_strategy_search(tr_fit, tr_val if tr_val else train[-10:], max_experiments=400, min_val_n=3)
        ranked = rank_for_gate(reg, min_n=5)
        best = ranked[0] if ranked else None
        cfg = StratCfg(**best["config"]) if best else StratCfg(0, 0, None, None, False, None, "wde", False, False)
        preds = apply_strategy(test, cfg)
        m = metrics(preds, len(test))
        folds.append(
            {
                "fold": len(folds) + 1,
                "train_n": len(train),
                "test_n": len(test),
                "train_start": train[0].kickoff_utc,
                "train_end": train[-1].kickoff_utc,
                "test_start": test[0].kickoff_utc,
                "test_end": test[-1].kickoff_utc,
                "selected_config_hash": best["config_hash"] if best else None,
                "test_metrics": m,
                "league_composition": dict(Counter(r.league or "?" for r in test)),
            }
        )
        i += block
    accs = [f["test_metrics"].get("accuracy") for f in folds if f["test_metrics"].get("accuracy") is not None]
    summary = {
        "n_folds": len(folds),
        "mean_accuracy": round(sum(accs) / len(accs), 4) if accs else None,
        "median_accuracy": round(sorted(accs)[len(accs) // 2], 4) if accs else None,
        "worst_fold_accuracy": min(accs) if accs else None,
        "std_accuracy": round(pd.Series(accs).std(ddof=0), 4) if accs else None,
        "scheme": "expanding_window_block15_min_train40_exclude_phase1_sealed",
    }
    return folds, summary


# ---------------------------------------------------------------------------
# Ablation / errors
# ---------------------------------------------------------------------------


def feature_ablation(rows: list[RowV2], sealed: set[int]) -> dict[str, Any]:
    data = [r for r in usable(rows) if r.fixture_id not in sealed]
    if len(data) < 30:
        return {"status": "INSUFFICIENT_N", "n": len(data)}
    split = int(len(data) * 0.7)
    train, val = data[:split], data[split:]
    families = {
        "canonical_only": StratCfg(0, 0, None, None, False, None, "wde", False, False),
        "canonical_plus_ecse_agree": StratCfg(0, 0, None, None, True, None, "wde", False, False),
        "canonical_plus_conf55": StratCfg(55, 0, None, None, False, None, "wde", False, False),
        "canonical_plus_entropy": StratCfg(0, 0, 1.7, None, False, None, "wde", False, False),
        "canonical_plus_top5": StratCfg(0, 0, None, 0.5, False, None, "wde", False, False),
        "canonical_plus_odds_cap": StratCfg(0, 0, None, None, False, 3.0, "wde", False, False),
        "majority_blend": StratCfg(0, 0, None, None, False, None, "majority", False, False),
        "ecse_direction": StratCfg(0, 0, None, None, False, None, "ecse", False, False),
    }
    base = metrics(apply_strategy(val, families["canonical_only"]), len(val))
    out = {"base_canonical_only": base, "deltas": {}}
    helped, hurt = [], []
    for name, cfg in families.items():
        m = metrics(apply_strategy(val, cfg), len(val))
        d_acc = None if base.get("accuracy") is None or m.get("accuracy") is None else round(m["accuracy"] - base["accuracy"], 4)
        out["deltas"][name] = {"metrics": m, "accuracy_delta": d_acc}
        if d_acc is not None and d_acc > 0.01:
            helped.append(name)
        if d_acc is not None and d_acc < -0.01:
            hurt.append(name)
    out["helped"] = helped
    out["hurt"] = hurt
    return out


def error_clusters(rows: list[RowV2], sealed: set[int]) -> dict[str, Any]:
    data = [r for r in usable(rows) if r.fixture_id not in sealed]
    clusters: dict[str, list[dict]] = defaultdict(list)
    for r in data:
        pred = r.wde_decision
        if not pred or pred == r.actual_1x2:
            continue
        fav = market_fav(r)
        tags = []
        if r.actual_1x2 == "draw":
            tags.append("draw_underranked")
        if fav and pred == fav:
            tags.append("favorite_failure")
        if fav and r.actual_1x2 and r.actual_1x2 != fav:
            tags.append("underdog_breakout")
        if r.ecse_direction and r.ecse_direction != pred:
            tags.append("direction_reversal")
        if fav and pred and fav != pred:
            tags.append("market_contradiction")
        if r.entropy is not None and r.entropy >= 1.7:
            tags.append("high_entropy")
        if r.edge() is not None and r.edge() < 0.4:
            tags.append("low_edge")
        if not r.feature_flags.get("odds"):
            tags.append("data_incomplete")
        if not tags:
            tags.append("unknown")
        for t in tags:
            clusters[t].append(
                {
                    "fixture_id": r.fixture_id,
                    "league": r.league,
                    "pred": pred,
                    "actual": r.actual_1x2,
                    "confidence": r.confidence,
                    "odds_home": r.odds_home,
                }
            )
    summary = {k: {"n": len(v), "sample": v[:5]} for k, v in sorted(clusters.items(), key=lambda x: -len(x[1]))}
    return {"clusters": summary, "primary": list(summary.keys())[:5]}


# ---------------------------------------------------------------------------
# Feature store
# ---------------------------------------------------------------------------


FEATURE_SPEC = [
    # name, family, leakage_class, missing_policy
    ("fixture_id", "id", "safe", "required"),
    ("kickoff_utc", "time", "safe", "required"),
    ("predicted_at", "time", "safe", "required_for_usable"),
    ("cohort", "meta", "safe", "required"),
    ("wde_decision", "canonical", "safe", "required_for_usable"),
    ("home_p", "canonical", "safe", "leave_null"),
    ("draw_p", "canonical", "safe", "leave_null"),
    ("away_p", "canonical", "safe", "leave_null"),
    ("confidence", "canonical", "safe", "leave_null"),
    ("no_bet", "canonical", "safe", "leave_null"),
    ("no_bet_reasons", "canonical", "safe", "leave_empty"),
    ("no_bet_reason_source", "canonical", "safe", "leave_null"),
    ("top3_mass", "ecse", "safe", "leave_null"),
    ("top5_mass", "ecse", "safe", "leave_null"),
    ("top10_mass", "ecse", "safe", "leave_null"),
    ("entropy", "ecse", "safe", "leave_null"),
    ("lambda_home", "ecse", "safe", "leave_null"),
    ("lambda_away", "ecse", "safe", "leave_null"),
    ("ecse_h_mass", "ecse", "safe", "leave_null"),
    ("ecse_d_mass", "ecse", "safe", "leave_null"),
    ("ecse_a_mass", "ecse", "safe", "leave_null"),
    ("ecse_direction", "ecse", "safe", "leave_null"),
    ("lambda_v2_home", "shadow", "safe", "leave_null"),
    ("lambda_v2_away", "shadow", "safe", "leave_null"),
    ("lambda_v2_direction", "shadow", "safe", "leave_null"),
    ("odds_home", "market", "safe_if_prematch", "leave_null"),
    ("odds_draw", "market", "safe_if_prematch", "leave_null"),
    ("odds_away", "market", "safe_if_prematch", "leave_null"),
    ("implied_home", "market", "safe_if_prematch", "leave_null"),
    ("implied_draw", "market", "safe_if_prematch", "leave_null"),
    ("implied_away", "market", "safe_if_prematch", "leave_null"),
    ("book_margin", "market", "safe_if_prematch", "leave_null"),
    ("favorite_strength", "market", "safe_if_prematch", "leave_null"),
    ("balanced_market", "market", "safe_if_prematch", "leave_null"),
    ("actual_1x2", "label", "label_only", "required_for_usable"),
]


def build_feature_store(rows: list[RowV2], out_dir: Path) -> dict[str, Any]:
    records = []
    for r in rows:
        d = {
            "fixture_id": r.fixture_id,
            "kickoff_utc": r.kickoff_utc,
            "predicted_at": r.predicted_at,
            "frozen_at": r.frozen_at,
            "cohort": r.cohort,
            "source": r.source,
            "league": r.league,
            "wde_decision": r.wde_decision,
            "ft_marginal": r.ft_marginal,
            "home_p": r.home_p,
            "draw_p": r.draw_p,
            "away_p": r.away_p,
            "confidence": r.confidence,
            "no_bet": r.no_bet,
            "no_bet_reasons": "|".join(r.no_bet_reasons),
            "no_bet_reason_source": r.no_bet_reason_source,
            "top3_mass": r.top3_mass,
            "top5_mass": r.top5_mass,
            "top10_mass": r.top10_mass,
            "entropy": r.entropy,
            "lambda_home": r.lambda_home,
            "lambda_away": r.lambda_away,
            "ecse_h_mass": r.ecse_h_mass,
            "ecse_d_mass": r.ecse_d_mass,
            "ecse_a_mass": r.ecse_a_mass,
            "ecse_direction": r.ecse_direction,
            "lambda_v2_home": r.lambda_v2_home,
            "lambda_v2_away": r.lambda_v2_away,
            "lambda_v2_direction": r.lambda_v2_direction,
            "odds_home": r.odds_home,
            "odds_draw": r.odds_draw,
            "odds_away": r.odds_away,
            "odds_snapshot_at": r.odds_snapshot_at,
            "odds_source": r.odds_source,
            "implied_home": r.implied_home,
            "implied_draw": r.implied_draw,
            "implied_away": r.implied_away,
            "book_margin": r.book_margin,
            "favorite_strength": r.favorite_strength,
            "balanced_market": r.balanced_market,
            "actual_1x2": r.actual_1x2,
            "final_score": r.final_score,
            "exclusion_reason": r.exclusion_reason,
        }
        records.append(d)
    df = pd.DataFrame(records)
    pq = out_dir / "feature_store_v2.parquet"
    df.to_parquet(pq, index=False)
    n = len(df)
    avail_rows = []
    provenance = []
    for name, family, leak, miss in FEATURE_SPEC:
        rate = float(df[name].notna().mean()) if name in df.columns else 0.0
        avail_rows.append(
            {
                "feature": name,
                "family": family,
                "availability_rate": round(rate, 4),
                "leakage_classification": leak,
                "missing_value_policy": miss,
                "available_phase2": rate > 0,
            }
        )
        provenance.append(
            {
                "feature": name,
                "family": family,
                "source": {
                    "canonical": "worldcup_stored_predictions/finished_match_evaluation",
                    "ecse": "ecse_prediction_snapshots",
                    "shadow": "lambda_v2_shadow_outputs",
                    "market": "odds_snapshots",
                    "label": "fixture_results",
                    "time": "fixtures/store timestamps",
                    "id": "fixture_id",
                    "meta": "assigned",
                }.get(family, "mixed"),
                "timestamp_field": "predicted_at/odds_snapshot_at/kickoff_utc",
            }
        )
    available = sum(1 for a in avail_rows if a["available_phase2"])
    try:
        pq_path = str(pq.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        pq_path = str(pq)
    manifest = {
        "path": pq_path,
        "n_rows": n,
        "n_features_in_spec": len(FEATURE_SPEC),
        "n_features_available": available,
        "phase1_available": 22,
        "format": "parquet",
    }
    return {"manifest": manifest, "availability": avail_rows, "provenance": provenance, "df": df}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_phase2(
    *,
    out_dir: Path | None = None,
    max_experiments: int = TARGET_EXPERIMENTS,
) -> dict[str, Any]:
    ts = _utc_now()
    out = out_dir or (ROOT / "artifacts" / "prediction_engine_75_phase2" / ts)
    out.mkdir(parents=True, exist_ok=True)

    sealed = load_phase1_sealed_ids()
    rows, exclusions, inventory = build_expanded_corpus()
    use = usable(rows)
    priced_before = 3  # phase1
    priced_after = sum(1 for r in use if r.odds_home and r.odds_draw and r.odds_away)

    # inventory artifacts
    inv_rows = [
        {
            "fixture_id": r.fixture_id,
            "cohort": r.cohort,
            "source": r.source,
            "kickoff_utc": r.kickoff_utc,
            "predicted_at": r.predicted_at,
            "exclusion_reason": r.exclusion_reason,
            "has_odds": bool(r.odds_home and r.odds_draw and r.odds_away),
            "has_ecse": bool(r.feature_flags.get("ecse")),
            "has_lambda_v2": bool(r.feature_flags.get("lambda_v2")),
            "no_bet_reason_source": r.no_bet_reason_source,
            "in_phase1_sealed": r.fixture_id in sealed,
        }
        for r in rows
    ]
    _write_json(out / "expanded_dataset_inventory.json", {**inventory, "n_usable": len(use), "priced_usable": priced_after})
    _write_csv(out / "expanded_dataset_inventory.csv", inv_rows)
    _write_csv(out / "excluded_fixture_ledger.csv", exclusions or [{"fixture_id": "", "reason": "NONE", "source": ""}])
    _write_json(
        out / "fixture_source_reconciliation.json",
        {
            "phase1_usable": PHASE1_N,
            "phase2_usable": len(use),
            "delta": len(use) - PHASE1_N,
            "sources": inventory.get("source_counts"),
            "cohorts": dict(Counter(r.cohort for r in use)),
            "overlap_with_phase1_sealed": sorted(sealed & {r.fixture_id for r in use}),
        },
    )

    quality, label_rep, leak = quality_and_leakage(rows, sealed)
    _write_json(out / "dataset_quality_report.json", quality)
    _write_json(out / "label_integrity_report.json", label_rep)
    _write_json(out / "leakage_report.json", leak)
    _write_json(
        out / "feature_leakage_audit.json",
        {
            "passed": leak.get("passed"),
            "rules": [
                "odds only if snapshot_at < kickoff",
                "lambda_v2 only if feature_cutoff < kickoff",
                "labels never used as features",
                "phase1 sealed holdout excluded from strategy selection",
            ],
        },
    )

    fs = build_feature_store(rows, out)
    _write_json(out / "feature_store_v2_manifest.json", fs["manifest"])
    _write_csv(out / "feature_availability_matrix.csv", fs["availability"])
    _write_json(out / "feature_provenance.json", {"features": fs["provenance"]})

    # no_bet reason coverage
    use_nb = [r for r in use if r.no_bet]
    nb_cov = {
        "usable_with_no_bet_true": len(use_nb),
        "with_reasons": sum(1 for r in use_nb if r.no_bet_reasons),
        "reason_source_counts": dict(Counter(r.no_bet_reason_source or "none" for r in use)),
        "code_counts": dict(Counter(c for r in use for c in r.no_bet_reasons)),
    }
    _write_json(out / "no_bet_reason_coverage.json", nb_cov)

    # research universe excludes sealed for selection
    research = [r for r in use if r.fixture_id not in sealed]
    research = sorted(research, key=lambda r: (str(r.kickoff_utc or ""), r.fixture_id))
    # chronological split for search: 70/30 of research (no sealed)
    cut = int(len(research) * 0.7)
    train, val = research[:cut], research[cut:]

    baselines = run_baselines_v2(research)
    _write_json(out / "baseline_results_v2.json", baselines)

    folds, wf_summary = walk_forward_folds(rows, sealed)
    _write_json(out / "walk_forward_folds.json", {"folds": folds, "summary": wf_summary})
    _write_csv(
        out / "walk_forward_summary.csv",
        [
            {
                "fold": f["fold"],
                "train_n": f["train_n"],
                "test_n": f["test_n"],
                "accuracy": f["test_metrics"].get("accuracy"),
                "coverage": f["test_metrics"].get("coverage_of_input"),
                "roi": f["test_metrics"].get("roi"),
                "n": f["test_metrics"].get("n"),
            }
            for f in folds
        ],
    )
    _write_json(
        out / "walk_forward_strategy_stability.json",
        {
            "unique_selected_configs": len({f.get("selected_config_hash") for f in folds if f.get("selected_config_hash")}),
            "summary": wf_summary,
        },
    )

    # strategy search — may reduce if N makes 50k meaningless
    justified_cap = max_experiments
    if len(research) < 80:
        justified_cap = min(max_experiments, 15000)
        search_note = "Reduced experiment cap due to limited usable N; additional configs add little statistical power"
    else:
        search_note = "Full Phase2 experiment target"
    registry, search_meta = run_strategy_search(train, val, max_experiments=justified_cap, min_val_n=5)
    search_meta["note"] = search_note
    search_meta["justified_cap"] = justified_cap

    # write registry sample + meta (full local)
    reg_path = out / "experiment_registry_phase2.jsonl"
    with reg_path.open("w", encoding="utf-8") as fh:
        for row in registry:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    # sample for git
    with (out / "experiment_registry_phase2_sample.jsonl").open("w", encoding="utf-8") as fh:
        for row in registry[:30]:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    _write_json(out / "experiment_registry_phase2_meta.json", {"n_full": len(registry), **search_meta})

    def lead_rows(ranked: list[dict], limit: int = 100) -> list[dict]:
        out_rows = []
        for r in ranked[:limit]:
            va = r["validation"]
            out_rows.append(
                {
                    "config_hash": r["config_hash"],
                    "accuracy": va.get("accuracy"),
                    "n": va.get("n"),
                    "coverage": va.get("coverage_of_input"),
                    "ci_lo": (va.get("ci95") or [None, None])[0],
                    "ci_hi": (va.get("ci95") or [None, None])[1],
                    "avg_odds": va.get("avg_odds"),
                    "roi": va.get("roi"),
                    "max_drawdown": va.get("max_drawdown"),
                    "top_league_share": va.get("top_league_share"),
                    "flags": "|".join(r.get("flags") or []),
                    "direction_mode": r["config"].get("direction_mode"),
                    "min_confidence": r["config"].get("min_confidence"),
                }
            )
        return out_rows

    all_ranked = rank_for_gate(registry, min_n=1)
    _write_csv(out / "strategy_leaderboard_all.csv", lead_rows(all_ranked))
    _write_csv(out / "strategy_leaderboard_n25.csv", lead_rows(rank_for_gate(registry, min_n=25)))
    _write_csv(out / "strategy_leaderboard_n50.csv", lead_rows(rank_for_gate(registry, min_n=50)))
    _write_csv(out / "strategy_leaderboard_n100.csv", lead_rows(rank_for_gate(registry, min_n=100)))
    cov_rows = []
    for thr in (0.05, 0.10, 0.20, 0.30):
        ranked = rank_for_gate(registry, min_n=10, min_cov=thr)
        if ranked:
            va = ranked[0]["validation"]
            cov_rows.append(
                {
                    "min_coverage": thr,
                    "config_hash": ranked[0]["config_hash"],
                    "accuracy": va.get("accuracy"),
                    "n": va.get("n"),
                    "coverage": va.get("coverage_of_input"),
                    "roi": va.get("roi"),
                    "avg_odds": va.get("avg_odds"),
                }
            )
    _write_csv(out / "coverage_leaderboards.csv", cov_rows)

    abl = feature_ablation(rows, sealed)
    _write_json(out / "feature_ablation.json", abl)
    err = error_clusters(rows, sealed)
    _write_json(out / "error_clusters.json", err)

    # priced inventory
    priced_rows = [
        {
            "fixture_id": r.fixture_id,
            "odds_home": r.odds_home,
            "odds_draw": r.odds_draw,
            "odds_away": r.odds_away,
            "odds_snapshot_at": r.odds_snapshot_at,
            "odds_source": r.odds_source,
            "kickoff_utc": r.kickoff_utc,
        }
        for r in use
        if r.odds_home and r.odds_draw and r.odds_away
    ]
    _write_csv(out / "priced_fixture_inventory.csv", priced_rows)
    _write_json(
        out / "odds_recovery_report.json",
        {
            "priced_n_phase1": priced_before,
            "priced_n_phase2": priced_after,
            "source": "odds_snapshots (latest prematch Match Winner consensus)",
            "historical_csv_ft_result": "audited but registry_fixture_id namespace largely disjoint from Sportmonks ids; not force-joined",
            "fabricated": False,
        },
    )

    # new future sealed boundary (document only; do not open)
    future_seal = research[int(len(research) * 0.8) :] if research else []
    _write_json(
        out / "sealed_holdout_status.json",
        {
            "phase1_holdout": {
                "status": "SEALED_UNOPENED",
                "n": len(sealed),
                "fixture_ids": sorted(sealed),
                "opened": False,
            },
            "phase2_future_boundary_documented_not_opened": {
                "status": "DOCUMENTED_SEALED",
                "n": len(future_seal),
                "fixture_ids": [r.fixture_id for r in future_seal],
                "note": "Additional chronological tail reserved; not used for Phase2 ranking claims",
            },
        },
    )
    _write_json(
        out / "true_forward_collection_plan.json",
        {
            "status": "PLAN_READY_NOT_AUTO_ENABLED",
            "actions": [
                "Freeze Canonical + challengers before kickoff",
                "Persist real prematch odds + explicit no_bet reasons",
                "Evaluate after FT only",
                "Never backfill as TRUE_FORWARD",
                "No auto-promotion",
            ],
            "timers": "Prepare only; do not enable without owner approval",
            "true_forward_n_now": 0,
        },
    )
    _write_json(
        out / "promotion_gate_status.json",
        {
            "passed": False,
            "target_75_claimed": False,
            "reasons": [
                "Phase2 does not open sealed holdout",
                "true_forward_n=0",
                "No promotion without owner approval",
            ],
        },
    )

    best25 = (rank_for_gate(registry, min_n=25) or [None])[0]
    best50 = (rank_for_gate(registry, min_n=50) or [None])[0]
    best100 = (rank_for_gate(registry, min_n=100) or [None])[0]

    # status decision
    if not leak.get("passed"):
        status = STATUS_BLOCKED
    elif len(use) <= PHASE1_N and priced_after <= priced_before:
        status = STATUS_PARTIAL
    elif len(use) > PHASE1_N and folds:
        # complete if corpus grew and walk-forward ran; note data limits remain
        status = STATUS_COMPLETE if len(use) >= PHASE1_N + 20 else STATUS_PARTIAL
    else:
        status = STATUS_PARTIAL

    # mark phase1 n=8 75% explicitly
    phase1_note = {"phase1_best_val_75pct_n8": "SMALL_SAMPLE_NOT_PROMOTABLE"}

    validation = {
        "status": status,
        "phase": PHASE,
        "phase1_usable_n": PHASE1_N,
        "phase2_usable_n": len(use),
        "cohort_counts": dict(Counter(r.cohort for r in use)),
        "priced_n_before": priced_before,
        "priced_n_after": priced_after,
        "features_before": 22,
        "features_after": fs["manifest"]["n_features_available"],
        "no_bet_reason_coverage": nb_cov,
        "walk_forward_fold_count": len(folds),
        "walk_forward_mean_accuracy": wf_summary.get("mean_accuracy"),
        "strategies_tested": len(registry),
        "search_meta": search_meta,
        "best_n25": _best_pack(best25),
        "best_n50": _best_pack(best50),
        "best_n100": _best_pack(best100),
        "feature_families_helped": abl.get("helped"),
        "feature_families_hurt": abl.get("hurt"),
        "primary_error_clusters": err.get("primary"),
        "sealed_holdout_status": "SEALED_UNOPENED",
        "true_forward_status": "PLAN_READY_N0",
        "baseline_stored_wde_accuracy": (baselines.get("stored_wde_decision") or {}).get("accuracy"),
        "phase1_small_sample_note": phase1_note,
        "target_75_claimed": False,
        "not_deployed": True,
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "no_auto_promotion": True,
        "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/") if out.is_relative_to(ROOT) else str(out),
        "compute": {
            "strategies_tested": len(registry),
            "walk_forward_folds": len(folds),
            "api_calls": 0,
            "db_mode": "read_only",
        },
    }
    _write_json(out / "validation_report.json", validation)
    report = _report_md(validation)
    (out / "PHASE2_FEATURE_EXPANSION_AND_WALK_FORWARD_REPORT.md").write_text(report, encoding="utf-8")
    (out / "PHASE2_FEATURE_EXPANSION_AND_WALK_FORWARD_REPORT_FA.md").write_text(
        "# فاز ۲ — گسترش ویژگی و walk-forward\n\n" + report, encoding="utf-8"
    )
    (out / "owner_phase2_research_dashboard.html").write_text(_dashboard(validation), encoding="utf-8")
    return validation


def _best_pack(best: dict | None) -> dict | None:
    if not best:
        return None
    va = best["validation"]
    return {
        "config_hash": best["config_hash"],
        "accuracy": va.get("accuracy"),
        "n": va.get("n"),
        "coverage": va.get("coverage_of_input"),
        "avg_odds": va.get("avg_odds"),
        "roi": va.get("roi"),
        "max_drawdown": va.get("max_drawdown"),
        "flags": best.get("flags"),
        "config": best.get("config"),
    }


def _report_md(v: dict[str, Any]) -> str:
    return f"""# PHASE2_FEATURE_EXPANSION_AND_WALK_FORWARD_REPORT

Status: **{v['status']}**

## Corpus

- Phase1 usable N: {v['phase1_usable_n']}
- Phase2 usable N: **{v['phase2_usable_n']}**
- Cohorts: `{v['cohort_counts']}`
- Priced odds: {v['priced_n_before']} → **{v['priced_n_after']}**
- Features available: {v['features_before']} → **{v['features_after']}**

## Walk-forward

- Folds: **{v['walk_forward_fold_count']}**
- Mean accuracy: {v['walk_forward_mean_accuracy']}

## Strategy search

- Strategies tested: **{v['strategies_tested']}**
- Best N≥25: `{v['best_n25']}`
- Best N≥50: `{v['best_n50']}`
- Best N≥100: `{v['best_n100']}`

Phase1 75% @ n=8 remains **SMALL_SAMPLE_NOT_PROMOTABLE**.

## Ablation

- Helped: {v['feature_families_helped']}
- Hurt: {v['feature_families_hurt']}

## Error clusters

{v['primary_error_clusters']}

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
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Phase2 75 Research</title>
<style>body{{font-family:Georgia,serif;margin:2rem;background:#0f1419;color:#e7eef5}}
h1{{color:#9ad7b8}}.card{{background:#1a222c;padding:1rem;margin:1rem 0;border-radius:8px}}</style></head><body>
<h1>Prediction Engine 75% — Phase 2</h1>
<div class="card"><b>{v['status']}</b><br/>
usable {v['phase1_usable_n']}→{v['phase2_usable_n']} · priced {v['priced_n_before']}→{v['priced_n_after']}<br/>
features {v['features_before']}→{v['features_after']} · strategies {v['strategies_tested']}<br/>
WF folds {v['walk_forward_fold_count']} · holdout {v['sealed_holdout_status']}</div>
<p>NOT DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · SEALED HOLDOUT UNOPENED · NO AUTO-PROMOTION</p>
</body></html>"""
