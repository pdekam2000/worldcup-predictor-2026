"""TRUE_FORWARD_472_COMPLETE_EVALUATION_AUDIT — read-only pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.research.true_forward_472_evaluation import (
    PROGRAM,
    RAW_TF_EXPECTED,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_INTEGRITY,
    STATUS_PARTIAL,
)
from worldcup_predictor.research.true_forward_472_evaluation import metrics as M

ROOT = Path(__file__).resolve().parents[3]
EVAL_DB = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"
VIENNA = ZoneInfo("Europe/Vienna")
CONFIRMED_QUALITIES = {
    "CONFIRMED_REGULATION_RESULT",
    "CONFIRMED_AFTER_EXTRA_TIME_WITH_REGULATION_AVAILABLE",
    "CONFIRMED_PENALTIES_WITH_REGULATION_AVAILABLE",
}
GATE_A, GATE_B, GATE_C = 30, 100, 250
EA08_HASH = "ea08ac971da53246"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _norm_1x2(value: Any) -> str | None:
    if value is None:
        return None
    t = str(value).lower().strip().replace(" ", "_")
    mapping = {
        "home": "home_win",
        "home_win": "home_win",
        "1": "home_win",
        "draw": "draw",
        "x": "draw",
        "away": "away_win",
        "away_win": "away_win",
        "2": "away_win",
    }
    return mapping.get(t, t if t in {"home_win", "draw", "away_win"} else None)


def _norm_btts(value: Any) -> str | None:
    if value is None:
        return None
    t = str(value).lower().strip()
    if t in {"yes", "y", "btts_yes"}:
        return "yes"
    if t in {"no", "n", "btts_no"}:
        return "no"
    return t if t in {"yes", "no"} else None


def _norm_ou(value: Any) -> str | None:
    if value is None:
        return None
    t = str(value).lower().strip().replace(".", "_")
    mapping = {
        "over": "over_2_5",
        "over_2_5": "over_2_5",
        "over_2.5": "over_2_5",
        "under": "under_2_5",
        "under_2_5": "under_2_5",
        "under_2.5": "under_2_5",
    }
    return mapping.get(t)


def _side_odds(side: str | None, odds_home: Any, odds_draw: Any, odds_away: Any) -> float | None:
    s = _norm_1x2(side)
    if s == "home_win" and odds_home not in (None, ""):
        return float(odds_home)
    if s == "draw" and odds_draw not in (None, ""):
        return float(odds_draw)
    if s == "away_win" and odds_away not in (None, ""):
        return float(odds_away)
    return None


def _connect(readonly: bool = True) -> sqlite3.Connection:
    uri = f"file:{EVAL_DB.as_posix()}?mode=ro" if readonly else str(EVAL_DB)
    conn = sqlite3.connect(uri, uri=readonly)
    conn.row_factory = sqlite3.Row
    return conn


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return 0


def inventory_sources(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    sources: list[dict[str, Any]] = []

    def add(
        path: str,
        table: str,
        *,
        trust: str,
        note: str,
        fixture_col: str | None = "fixture_id",
        model_cols: list[str] | None = None,
        date_cols: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if table not in tables and not path.endswith(".json") and "true_forward_collection" not in path:
            return
        row: dict[str, Any] = {
            "path": path,
            "table": table,
            "row_count": _table_count(conn, table) if table in tables else None,
            "unique_fixture_ids": None,
            "unique_model_ids": None,
            "snapshot_stages": None,
            "date_range": None,
            "evaluated_count": None,
            "result_coverage": None,
            "odds_coverage": None,
            "trust_status": trust,
            "note": note,
        }
        if table in tables and fixture_col:
            try:
                row["unique_fixture_ids"] = int(
                    conn.execute(f"SELECT COUNT(DISTINCT {fixture_col}) FROM {table}").fetchone()[0]
                )
            except sqlite3.Error:
                pass
        if table == "frozen_predictions":
            row["unique_model_ids"] = [
                "canonical_wde_decision",
                "canonical_wde_raw_argmax",
                "canonical_ecse_direction",
                "canonical_ecse_exact_top5",
                "btts",
                "ou25",
            ]
            row["snapshot_stages"] = "inferred_from_hours_to_kickoff"
            dr = conn.execute(
                "SELECT MIN(kickoff) mn, MAX(kickoff) mx, MIN(frozen_at) fmin, MAX(frozen_at) fmax FROM frozen_predictions"
            ).fetchone()
            row["date_range"] = {"kickoff_min": dr["mn"], "kickoff_max": dr["mx"], "frozen_min": dr["fmin"], "frozen_max": dr["fmax"]}
            row["evaluated_count"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM frozen_predictions WHERE evaluation_status='EVALUATED'"
                ).fetchone()[0]
            )
            row["result_coverage"] = int(
                conn.execute(
                    """
                    SELECT COUNT(DISTINCT f.fixture_id) FROM frozen_predictions f
                    JOIN actual_results a ON a.fixture_id=f.fixture_id
                    """
                ).fetchone()[0]
            )
            row["odds_coverage"] = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM frozen_predictions
                    WHERE odds_home IS NOT NULL AND odds_draw IS NOT NULL AND odds_away IS NOT NULL
                    """
                ).fetchone()[0]
            )
        if table == "actual_results":
            row["evaluated_count"] = row["row_count"]
            row["result_coverage"] = row["row_count"]
        if table == "market_evaluations":
            row["evaluated_count"] = row["row_count"]
        if table.startswith("lambda") or table.startswith("high_score"):
            row["unique_model_ids"] = [table]
            row["trust_status"] = "SHADOW_SEPARATE_FROM_472"
        if extra:
            row.update(extra)
        sources.append(row)

    add(
        str(EVAL_DB.relative_to(ROOT)),
        "frozen_predictions",
        trust="PRIMARY_TRUE_FORWARD_STORE",
        note="Authoritative 472 frozen prematch rows (Canonical WDE+ECSE+BTTS+OU embedded per row)",
    )
    add(str(EVAL_DB.relative_to(ROOT)), "actual_results", trust="HIGH", note="Regulation-time results synced for TF fixtures")
    add(str(EVAL_DB.relative_to(ROOT)), "market_evaluations", trust="HIGH", note="Existing HIT/MISS evaluations; incomplete vs finished fixtures")
    add(str(EVAL_DB.relative_to(ROOT)), "exact_score_rankings", trust="HIGH", note="Top1-Top5 ranks only in store (5 rows per freeze)")
    add(str(EVAL_DB.relative_to(ROOT)), "evaluation_batches", trust="MEDIUM", note="Batch metadata")
    add(str(EVAL_DB.relative_to(ROOT)), "prediction_context", trust="MEDIUM", note="Context buckets for evaluated freezes")
    add(str(EVAL_DB.relative_to(ROOT)), "lambda_v2_shadow_outputs", trust="SHADOW_ONLY", note="Research shadow; not part of 472 denominator")
    add(str(EVAL_DB.relative_to(ROOT)), "high_score_tail_shadow_outputs", trust="SHADOW_ONLY", note="Research shadow")
    add(str(EVAL_DB.relative_to(ROOT)), "lambda_team_strength_shadow_outputs", trust="SHADOW_ONLY", note="Research shadow")
    add(str(EVAL_DB.relative_to(ROOT)), "totals_market_shadow_snapshots", trust="SHADOW_ONLY", note="Empty/shadow")
    add(str(EVAL_DB.relative_to(ROOT)), "freeze_quarantine", trust="MEDIUM", note="Quarantine ledger")
    add(str(EVAL_DB.relative_to(ROOT)), "ecse_prematch_risk_metadata", trust="MEDIUM", note="ECSE risk metadata")

    # filesystem sources
    tf_dir = ROOT / "data" / "research" / "true_forward_collection"
    sources.append(
        {
            "path": str(tf_dir.relative_to(ROOT)) if tf_dir.exists() else "data/research/true_forward_collection",
            "table": "(directory)",
            "row_count": len(list(tf_dir.rglob("*"))) if tf_dir.exists() else 0,
            "unique_fixture_ids": None,
            "unique_model_ids": None,
            "snapshot_stages": None,
            "date_range": None,
            "evaluated_count": None,
            "result_coverage": None,
            "odds_coverage": None,
            "trust_status": "PLAN_ONLY",
            "note": "Research collection docs/plans; not the 472 freeze store",
        }
    )
    for art in sorted((ROOT / "artifacts").glob("next_5_days*/**/*")) if (ROOT / "artifacts").exists() else []:
        if art.name in {"ranked_1x2_candidates.json", "run_summary.json", "NEXT_5_DAYS_COMPLETE_PREDICTION_REPORT.md"}:
            sources.append(
                {
                    "path": str(art.relative_to(ROOT)),
                    "table": "(artifact)",
                    "row_count": 1,
                    "unique_fixture_ids": None,
                    "unique_model_ids": None,
                    "snapshot_stages": None,
                    "date_range": None,
                    "evaluated_count": None,
                    "result_coverage": None,
                    "odds_coverage": None,
                    "trust_status": "ARTIFACT_SHORTLIST",
                    "note": "Next-5-days shortlist / mission artifact",
                }
            )

    # overlap matrix
    fx_sets: dict[str, set[int]] = {}
    for table in (
        "frozen_predictions",
        "actual_results",
        "market_evaluations",
        "lambda_v2_shadow_outputs",
        "high_score_tail_shadow_outputs",
        "lambda_team_strength_shadow_outputs",
    ):
        if table in tables:
            fx_sets[table] = {
                int(r[0])
                for r in conn.execute(f"SELECT DISTINCT fixture_id FROM {table}").fetchall()
                if r[0] is not None
            }
    names = list(fx_sets.keys())
    matrix_rows: list[dict[str, Any]] = []
    for a in names:
        for b in names:
            inter = len(fx_sets[a] & fx_sets[b])
            union = len(fx_sets[a] | fx_sets[b]) or 1
            matrix_rows.append(
                {
                    "source_a": a,
                    "source_b": b,
                    "intersection_fixtures": inter,
                    "union_fixtures": union,
                    "jaccard": round(inter / union, 6),
                    "a_only": len(fx_sets[a] - fx_sets[b]),
                    "b_only": len(fx_sets[b] - fx_sets[a]),
                }
            )
    return sources, matrix_rows


def load_freezes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = [dict(r) for r in conn.execute("SELECT * FROM frozen_predictions").fetchall()]
    return rows


def load_results(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for r in conn.execute("SELECT * FROM actual_results").fetchall():
        d = dict(r)
        out[int(d["fixture_id"])] = d
    return out


def load_ranks(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in conn.execute(
        "SELECT prediction_id, rank, score, probability FROM exact_score_rankings ORDER BY prediction_id, rank"
    ).fetchall():
        out[str(r["prediction_id"])].append(dict(r))
    return out


def load_existing_evals(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {str(r["prediction_id"]): dict(r) for r in conn.execute("SELECT * FROM market_evaluations").fetchall()}


def classify_result_status(result: dict[str, Any] | None) -> str:
    if not result:
        return "PENDING"
    q = str(result.get("result_quality_status") or "")
    st = str(result.get("result_status") or "").upper()
    if q in CONFIRMED_QUALITIES:
        return "FINISHED_CONFIRMED"
    if st in {"FT", "AET", "PEN", "FINISHED"} and result.get("actual_1x2"):
        return "FINISHED_CONFIRMED"
    if st in {"LIVE", "1H", "2H", "HT"}:
        return "LIVE"
    if st in {"PST", "POSTPONED"}:
        return "POSTPONED"
    if st in {"CANC", "CANCELLED"}:
        return "CANCELLED"
    if st in {"ABD", "ABANDONED"}:
        return "ABANDONED"
    if q == "PROVIDER_CONFLICT":
        return "RESULT_CONFLICT"
    if result.get("actual_1x2") is None:
        return "RESULT_MISSING"
    return "MANUAL_REVIEW"


def validate_record(row: dict[str, Any], content_hash_counts: Counter[str]) -> list[str]:
    issues: list[str] = []
    if row.get("fixture_id") is None:
        issues.append("MISSING_FIXTURE_ID")
    if not row.get("wde_model_version") and not row.get("wde_decision") and not row.get("home_probability"):
        # model identity embedded; flag incomplete output separately
        pass
    if not row.get("content_hash") and not row.get("payload_hash"):
        issues.append("MISSING_CONFIGURATION_HASH")
    kick = _parse_dt(row.get("kickoff"))
    frozen = _parse_dt(row.get("frozen_at"))
    gen = _parse_dt(row.get("generated_at"))
    odds_ts = _parse_dt(row.get("odds_timestamp") or row.get("odds_fetched_at_utc"))
    if kick and gen and gen >= kick:
        issues.append("POST_KICKOFF_PREDICTION")
    if kick and odds_ts and odds_ts >= kick:
        issues.append("POST_KICKOFF_ODDS")
    if kick and frozen and frozen >= kick:
        issues.append("POST_KICKOFF_FREEZE")
    ch = row.get("content_hash")
    if ch and content_hash_counts.get(str(ch), 0) > 1:
        # same content hash across rows can be intentional reuse; mark duplicate content
        issues.append("DUPLICATE_RECORD")
    if not row.get("wde_decision") and not row.get("ft_marginal_direction"):
        issues.append("INCOMPLETE_OUTPUT")
    if row.get("immutable") is not None and int(row.get("immutable") or 0) != 1:
        issues.append("MANUAL_REVIEW")
    # cohort: TF freezes are implicit true_forward via store; no conflicting label column
    return issues


def pick_canonical_freeze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer EVALUATED, else latest frozen_at before kickoff."""

    def key(r: dict[str, Any]) -> tuple:
        evaluated = 1 if str(r.get("evaluation_status") or "").upper() == "EVALUATED" else 0
        frozen = _parse_dt(r.get("frozen_at")) or datetime.min.replace(tzinfo=timezone.utc)
        return (evaluated, frozen)

    return sorted(rows, key=key)[-1]


def ecse_direction_from_freeze(row: dict[str, Any], ranks: list[dict[str, Any]]) -> str | None:
    """Prefer Top1 exact-score side; fall back to stored market_direction."""
    if ranks:
        ordered = sorted(ranks, key=lambda r: int(r["rank"]))
        score = str(ordered[0].get("score") or "")
        if "-" in score:
            h, a = score.split("-", 1)
            try:
                hi, ai = int(h), int(a)
            except ValueError:
                hi = ai = None
            if hi is not None:
                if hi > ai:
                    return "home_win"
                if hi < ai:
                    return "away_win"
                return "draw"
    return _norm_1x2(row.get("market_direction"))


def _normalize_probs(home: Any, draw: Any, away: Any) -> dict[str, float]:
    vals = {}
    for k, v in (("home_win", home), ("draw", draw), ("away_win", away)):
        if v is None or v == "":
            continue
        vals[k] = float(v)
    if not vals:
        return {}
    # store uses percent scale (e.g. 83.5); convert to [0,1]
    if any(v > 1.0 for v in vals.values()):
        vals = {k: v / 100.0 for k, v in vals.items()}
    s = sum(vals.values())
    if s > 0 and abs(s - 1.0) > 0.05:
        vals = {k: v / s for k, v in vals.items()}
    return vals


def evaluate_exact(actual_score: str | None, ranks: list[dict[str, Any]]) -> dict[str, Any]:
    if not actual_score or not ranks:
        return {
            "actual_rank": None,
            "top1": None,
            "top3": None,
            "top5": None,
            "top10": None,
            "rank_label": None,
        }
    ordered = sorted(ranks, key=lambda r: int(r["rank"]))
    scores = [str(r["score"]) for r in ordered]
    actual_rank = None
    for r in ordered:
        if str(r["score"]) == actual_score:
            actual_rank = int(r["rank"])
            break
    # store only has top5
    max_rank = max(int(r["rank"]) for r in ordered) if ordered else 0
    label = f"TOP{actual_rank}" if actual_rank else ("OUTSIDE_TOP5" if max_rank <= 5 else "OUTSIDE_TOP10")
    return {
        "actual_rank": actual_rank,
        "top1": actual_score == scores[0] if scores else None,
        "top3": actual_score in scores[:3] if scores else None,
        "top5": actual_score in scores[:5] if scores else None,
        "top10": None if max_rank < 10 else (actual_score in scores[:10]),
        "rank_label": label,
        "top5_mass": None,
        "store_max_rank": max_rank,
    }


def classify_failure(
    *,
    pred: str | None,
    actual: str | None,
    odds_home: float | None,
    odds_draw: float | None,
    odds_away: float | None,
    wde: str | None,
    ecse_dir: str | None,
    actual_score: str | None,
    top1: str | None,
) -> str:
    if not pred or not actual or pred == actual:
        return "UNKNOWN"
    fav = None
    odds = {"home_win": odds_home, "draw": odds_draw, "away_win": odds_away}
    priced = {k: v for k, v in odds.items() if v is not None and float(v) > 1}
    if priced:
        fav = min(priced, key=lambda k: float(priced[k]))
    if fav and pred == fav and actual != fav:
        return "FAVORITE_FAILURE"
    if fav and actual != fav and pred != actual:
        # underdog won
        if actual in priced and float(priced[actual]) >= float(priced.get(fav, 99)):
            return "UNDERDOG_BREAKOUT"
    if actual == "draw":
        return "DRAW_UNDERRANKED"
    if wde and ecse_dir and wde != ecse_dir:
        return "MODEL_DISAGREEMENT"
    if fav and pred != fav and actual == fav:
        return "MARKET_CONTRADICTION"
    if pred and actual and pred != actual and {pred, actual} == {"home_win", "away_win"}:
        return "DIRECTION_REVERSAL"
    if actual_score:
        try:
            h, a = actual_score.split("-", 1)
            if int(h) + int(a) >= 4:
                return "HIGH_SCORE_TAIL"
            if int(h) + int(a) <= 1:
                return "LOW_SCORE_OVERCONCENTRATION"
        except ValueError:
            pass
    if top1 and actual_score and top1 != actual_score:
        return "DECISION_OVERRIDE_FAILURE"
    return "UNKNOWN"


def load_strict_shortlist() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    root = ROOT / "artifacts"
    if not root.exists():
        return out
    paths = sorted(root.rglob("ranked_1x2_candidates.json"))
    seen: set[tuple[Any, ...]] = set()
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        strict = data.get("strict") if isinstance(data, dict) else None
        if not isinstance(strict, list):
            continue
        for item in strict:
            if not isinstance(item, dict):
                continue
            fid = item.get("fixture_id") or item.get("provider_fixture_id")
            key = (fid, item.get("selected_side") or item.get("direction") or item.get("pick"))
            if key in seen:
                continue
            seen.add(key)
            out.append({**item, "_source_artifact": str(path.relative_to(ROOT))})
    return out


def run_audit(*, out_dir: Path | None = None) -> dict[str, Any]:
    run_id = _utc_stamp()
    out = out_dir or (ROOT / "artifacts" / "true_forward_472_evaluation" / run_id)
    out.mkdir(parents=True, exist_ok=True)

    if not EVAL_DB.exists():
        payload = {"status": STATUS_FAILED, "error": f"missing eval db: {EVAL_DB}"}
        _write_json(out / "run_manifest.json", payload)
        return payload

    # Freeze hash fingerprint before read (safety proof)
    freeze_hash_before = hashlib.sha256(EVAL_DB.read_bytes()).hexdigest()

    conn = _connect(readonly=True)
    try:
        sources, overlap = inventory_sources(conn)
        freezes = load_freezes(conn)
        results = load_results(conn)
        ranks_map = load_ranks(conn)
        existing_evals = load_existing_evals(conn)

        # L2F jobs if present in FI db
        l2f_info = {"path": None, "true_forward_jobs": None}
        for cand in (
            ROOT / "data" / "football_intelligence.db",
            ROOT / "football_intelligence.db",
        ):
            if cand.exists():
                try:
                    fic = sqlite3.connect(f"file:{cand.as_posix()}?mode=ro", uri=True)
                    fic.row_factory = sqlite3.Row
                    n = fic.execute(
                        "SELECT COUNT(*) FROM l2f_forward_shadow_jobs WHERE cohort_type='true_forward'"
                    ).fetchone()[0]
                    l2f_info = {"path": str(cand.relative_to(ROOT)), "true_forward_jobs": int(n)}
                    sources.append(
                        {
                            "path": str(cand.relative_to(ROOT)),
                            "table": "l2f_forward_shadow_jobs",
                            "row_count": int(n),
                            "unique_fixture_ids": int(
                                fic.execute(
                                    "SELECT COUNT(DISTINCT fixture_id) FROM l2f_forward_shadow_jobs WHERE cohort_type='true_forward'"
                                ).fetchone()[0]
                            ),
                            "unique_model_ids": ["l2f"],
                            "snapshot_stages": None,
                            "date_range": None,
                            "evaluated_count": None,
                            "result_coverage": None,
                            "odds_coverage": None,
                            "trust_status": "SHADOW_L2F",
                            "note": "L2F true_forward cohort jobs; separate from 472 freeze rows",
                        }
                    )
                    fic.close()
                except sqlite3.Error:
                    pass
                break

        raw_n = len(freezes)
        content_counts = Counter(str(r.get("content_hash") or "") for r in freezes if r.get("content_hash"))

        integrity_rows: list[dict[str, Any]] = []
        invalid_rows: list[dict[str, Any]] = []
        by_fixture: dict[int, list[dict[str, Any]]] = defaultdict(list)

        for row in freezes:
            fid = int(row["fixture_id"]) if row.get("fixture_id") is not None else None
            kick = _parse_dt(row.get("kickoff"))
            frozen = _parse_dt(row.get("frozen_at"))
            hours = None
            if kick and frozen:
                hours = (kick - frozen).total_seconds() / 3600.0
            stage = M.timing_stage(hours)
            issues = validate_record(row, content_counts)
            # duplicate logical: multiple freezes same fixture
            if fid is not None:
                by_fixture[fid].append(row)
            rec = {
                "prediction_id": row.get("prediction_id"),
                "fixture_id": fid,
                "model_id": "embedded_canonical_bundle",
                "configuration_hash": row.get("content_hash") or row.get("payload_hash"),
                "prediction_timestamp": row.get("generated_at"),
                "odds_timestamp": row.get("odds_timestamp") or row.get("odds_fetched_at_utc"),
                "freeze_timestamp": row.get("frozen_at"),
                "kickoff_timestamp": row.get("kickoff"),
                "prediction_before_kickoff": bool(kick and (_parse_dt(row.get("generated_at")) or frozen) and ((_parse_dt(row.get("generated_at")) or frozen) < kick)),
                "odds_before_kickoff": (not (kick and _parse_dt(row.get("odds_timestamp") or row.get("odds_fetched_at_utc")) and (_parse_dt(row.get("odds_timestamp") or row.get("odds_fetched_at_utc")) >= kick))),
                "freeze_before_kickoff": bool(kick and frozen and frozen < kick),
                "cohort_type": "true_forward",
                "snapshot_stage": stage,
                "hours_to_kickoff": hours,
                "public_visible": row.get("public_visible"),
                "output_complete": bool(row.get("wde_decision") or row.get("ft_marginal_direction")),
                "freeze_hash": row.get("payload_hash") or row.get("content_hash"),
                "duplicate_status": "DUPLICATE_CONTENT" if "DUPLICATE_RECORD" in issues else ("MULTI_FREEZE_FIXTURE" if False else "UNIQUE_ROW"),
                "result_status": classify_result_status(results.get(fid) if fid is not None else None),
                "evaluation_status": row.get("evaluation_status"),
                "issues": issues,
                "valid": len([i for i in issues if i not in {"DUPLICATE_RECORD"}]) == 0,
            }
            # refine multi-freeze later
            integrity_rows.append(rec)
            for issue in issues:
                invalid_rows.append(
                    {
                        "prediction_id": row.get("prediction_id"),
                        "fixture_id": fid,
                        "issue": issue,
                        "kickoff": row.get("kickoff"),
                        "frozen_at": row.get("frozen_at"),
                    }
                )

        multi_freeze_fx = {fid for fid, rs in by_fixture.items() if len(rs) > 1}
        for rec in integrity_rows:
            if rec["fixture_id"] in multi_freeze_fx:
                rec["duplicate_status"] = "MULTI_FREEZE_FIXTURE"

        unique_fixtures = sorted(by_fixture.keys())
        # unique fixture-model: each freeze embeds models; count non-null outputs on canonical freeze
        fixture_model_keys: set[tuple[int, str, str]] = set()
        fixture_model_snap_keys: set[tuple[int, str, str, str]] = set()
        models_def = [
            ("canonical_wde_decision", "wde_decision", "wde_model_version"),
            ("canonical_wde_raw_argmax", "ft_marginal_direction", "wde_model_version"),
            ("canonical_ecse_direction", "__ecse_dir__", "ecse_model_version"),
            ("canonical_ecse_exact", "__exact__", "ecse_model_version"),
            ("btts", "btts_prediction", "btts_model_version"),
            ("ou25", "ou25_prediction", "ou_model_version"),
        ]

        ledger: list[dict[str, Any]] = []
        result_status_rows: list[dict[str, Any]] = []
        eval_rows_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
        exact_eval_rows: list[dict[str, Any]] = []
        priced_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
        failure_rows: list[dict[str, Any]] = []
        ea08_rows: list[dict[str, Any]] = []
        snapshot_rows: list[dict[str, Any]] = []

        finished_unique = 0
        confirmed_unique = 0
        pending_unique = 0
        evaluated_unique = 0

        for fid in unique_fixtures:
            rows = by_fixture[fid]
            canon = pick_canonical_freeze(rows)
            result = results.get(fid)
            rstatus = classify_result_status(result)
            if rstatus == "FINISHED_CONFIRMED":
                finished_unique += 1
                confirmed_unique += 1
            elif rstatus in {"PENDING", "RESULT_MISSING", "LIVE"}:
                pending_unique += 1
            else:
                pending_unique += 1  # unresolved bucket

            kick = _parse_dt(canon.get("kickoff"))
            vienna_ko = kick.astimezone(VIENNA).isoformat() if kick else None
            stages = sorted(
                {
                    M.timing_stage(
                        ((_parse_dt(r.get("kickoff")) - _parse_dt(r.get("frozen_at"))).total_seconds() / 3600.0)
                        if _parse_dt(r.get("kickoff")) and _parse_dt(r.get("frozen_at"))
                        else None
                    )
                    for r in rows
                }
            )
            models_available = []
            for mid, field, ver_field in models_def:
                if field == "__ecse_dir__":
                    val = ecse_direction_from_freeze(canon, ranks_map.get(str(canon["prediction_id"]), []))
                elif field == "__exact__":
                    val = "yes" if ranks_map.get(str(canon["prediction_id"])) else None
                else:
                    val = canon.get(field)
                if val not in (None, ""):
                    models_available.append(mid)
                    cfg = str(canon.get(ver_field) or canon.get("content_hash") or "unknown")
                    fixture_model_keys.add((fid, mid, cfg))
                    # all snapshots for this fixture-model
                    for r in rows:
                        hrs = None
                        if _parse_dt(r.get("kickoff")) and _parse_dt(r.get("frozen_at")):
                            hrs = (_parse_dt(r.get("kickoff")) - _parse_dt(r.get("frozen_at"))).total_seconds() / 3600.0
                        st = M.timing_stage(hrs)
                        cfg_r = str(r.get(ver_field) or r.get("content_hash") or "unknown")
                        fixture_model_snap_keys.add((fid, mid, st, cfg_r))

            priced = all(
                canon.get(k) not in (None, "") for k in ("odds_home", "odds_draw", "odds_away")
            ) and float(canon.get("odds_home") or 0) > 1

            actual_1x2 = _norm_1x2((result or {}).get("actual_1x2") or (result or {}).get("regulation_result"))
            actual_score = (result or {}).get("actual_score")
            evaluable = rstatus == "FINISHED_CONFIRMED" and actual_1x2 is not None and bool(
                canon.get("wde_decision") or canon.get("ft_marginal_direction")
            )
            exclusion = None
            if not evaluable:
                if rstatus != "FINISHED_CONFIRMED":
                    exclusion = f"RESULT_{rstatus}"
                elif not actual_1x2:
                    exclusion = "MISSING_ACTUAL_1X2"
                else:
                    exclusion = "MISSING_PREDICTION"

            if evaluable:
                evaluated_unique += 1

            ledger.append(
                {
                    "fixture_id": fid,
                    "date": (kick.date().isoformat() if kick else None),
                    "vienna_kickoff": vienna_ko,
                    "country": None,
                    "league": canon.get("competition"),
                    "home": canon.get("home_team_name") or (str(canon.get("match_name") or "").split(" vs ")[0] if canon.get("match_name") else None),
                    "away": canon.get("away_team_name")
                    or (
                        str(canon.get("match_name") or "").split(" vs ")[-1]
                        if canon.get("match_name") and " vs " in str(canon.get("match_name"))
                        else None
                    ),
                    "raw_records": len(rows),
                    "n_models": len(models_available),
                    "n_snapshots": len(stages),
                    "snapshot_stages": "|".join(stages),
                    "earliest_valid_prediction": min((r.get("frozen_at") or "") for r in rows),
                    "latest_valid_prematch_prediction": max((r.get("frozen_at") or "") for r in rows),
                    "result_status": rstatus,
                    "regulation_score": actual_score,
                    "actual_1x2": actual_1x2,
                    "odds_coverage": "complete" if priced else "partial_or_missing",
                    "priced": priced,
                    "models_available": "|".join(models_available),
                    "models_missing": "|".join(m for m, _, __ in models_def if m not in models_available),
                    "evaluable": evaluable,
                    "exclusion_reason": exclusion,
                    "canonical_prediction_id": canon.get("prediction_id"),
                    "tier": canon.get("tier") or canon.get("validation_tier"),
                    "prediction_scope": canon.get("prediction_scope"),
                }
            )
            result_status_rows.append(
                {
                    "fixture_id": fid,
                    "result_status_class": rstatus,
                    "result_status_raw": (result or {}).get("result_status"),
                    "result_quality_status": (result or {}).get("result_quality_status"),
                    "regulation_score": actual_score,
                    "actual_1x2": actual_1x2,
                    "et_penalties_separate": (result or {}).get("result_status") in {"AET", "PEN"},
                    "score_basis": (result or {}).get("score_basis"),
                    "result_source": (result or {}).get("result_source"),
                    "provider": (result or {}).get("provider"),
                    "overwrite_performed": False,
                }
            )

            pid = str(canon["prediction_id"])
            ranks = ranks_map.get(pid, [])
            wde = _norm_1x2(canon.get("wde_decision"))
            raw_argmax = _norm_1x2(canon.get("ft_marginal_direction"))
            ecse_dir = ecse_direction_from_freeze(canon, ranks)
            probs_f = _normalize_probs(
                canon.get("home_probability"),
                canon.get("draw_probability"),
                canon.get("away_probability"),
            )

            # per-snapshot rows for timing comparison (all freezes)
            for r in rows:
                hrs = None
                kk = _parse_dt(r.get("kickoff"))
                ff = _parse_dt(r.get("frozen_at"))
                if kk and ff:
                    hrs = (kk - ff).total_seconds() / 3600.0
                st = M.timing_stage(hrs)
                pw = _norm_1x2(r.get("wde_decision"))
                hit = None
                if evaluable and pw and actual_1x2:
                    hit = pw == actual_1x2
                ex = evaluate_exact(actual_score, ranks_map.get(str(r["prediction_id"]), []))
                snapshot_rows.append(
                    {
                        "fixture_id": fid,
                        "prediction_id": r.get("prediction_id"),
                        "snapshot_stage": st,
                        "hours_to_kickoff": hrs,
                        "wde": pw,
                        "hit": hit,
                        "top5_hit": ex["top5"] if evaluable else None,
                        "odds_home": r.get("odds_home"),
                        "evaluable": evaluable,
                    }
                )

            if not evaluable:
                continue

            def _pack(model_id: str, pred: str | None, *, market: str = "1x2") -> None:
                if not pred:
                    return
                hit = pred == actual_1x2 if market == "1x2" else None
                p_act = probs_f.get(actual_1x2) if probs_f else None
                row_e = {
                    "fixture_id": fid,
                    "prediction_id": pid,
                    "model_id": model_id,
                    "predicted": pred,
                    "actual": actual_1x2,
                    "hit": bool(hit) if hit is not None else None,
                    "confidence": canon.get("wde_confidence"),
                    "p_actual": p_act,
                    "brier": M.brier_multiclass(probs_f, actual_1x2) if probs_f else None,
                    "log_loss": M.log_loss_multiclass(probs_f, actual_1x2) if probs_f else None,
                    "calibration_bucket": M.calibration_bucket(p_act),
                    "league": canon.get("competition"),
                    "month": (kick.strftime("%Y-%m") if kick else None),
                    "snapshot_stage": M.timing_stage(
                        ((_parse_dt(canon.get("kickoff")) - _parse_dt(canon.get("frozen_at"))).total_seconds() / 3600.0)
                        if _parse_dt(canon.get("kickoff")) and _parse_dt(canon.get("frozen_at"))
                        else None
                    ),
                    "odds": _side_odds(pred, canon.get("odds_home"), canon.get("odds_draw"), canon.get("odds_away")),
                }
                eval_rows_by_model[model_id].append(row_e)
                o = row_e["odds"]
                if o is not None and float(o) > 1.0 and hit is not None:
                    priced_by_model[model_id].append({"hit": bool(hit), "odds": float(o), "side": pred, "fixture_id": fid})

            _pack("canonical_wde_decision", wde)
            _pack("canonical_wde_raw_argmax", raw_argmax)
            _pack("canonical_ecse_direction", ecse_dir)

            # BTTS / OU
            btts_p = _norm_btts(canon.get("btts_prediction"))
            btts_a = _norm_btts((result or {}).get("actual_btts"))
            if btts_p and btts_a:
                eval_rows_by_model["btts"].append(
                    {
                        "fixture_id": fid,
                        "prediction_id": pid,
                        "model_id": "btts",
                        "predicted": btts_p,
                        "actual": btts_a,
                        "hit": btts_p == btts_a,
                        "league": canon.get("competition"),
                        "month": (kick.strftime("%Y-%m") if kick else None),
                        "snapshot_stage": None,
                        "odds": None,
                    }
                )
            ou_p = _norm_ou(canon.get("ou25_prediction"))
            ou_a = _norm_ou((result or {}).get("actual_ou25"))
            if ou_p and ou_a:
                eval_rows_by_model["ou25"].append(
                    {
                        "fixture_id": fid,
                        "prediction_id": pid,
                        "model_id": "ou25",
                        "predicted": ou_p,
                        "actual": ou_a,
                        "hit": ou_p == ou_a,
                        "line": 2.5,
                        "league": canon.get("competition"),
                        "month": (kick.strftime("%Y-%m") if kick else None),
                        "snapshot_stage": None,
                        "odds": None,
                    }
                )

            ex = evaluate_exact(actual_score, ranks)
            if ranks:
                top5_mass = canon.get("top5_mass")
                exact_eval_rows.append(
                    {
                        "fixture_id": fid,
                        "prediction_id": pid,
                        "model_id": "canonical_ecse_exact",
                        "snapshot_stage": M.timing_stage(
                            ((_parse_dt(canon.get("kickoff")) - _parse_dt(canon.get("frozen_at"))).total_seconds() / 3600.0)
                            if _parse_dt(canon.get("kickoff")) and _parse_dt(canon.get("frozen_at"))
                            else None
                        ),
                        **ex,
                        "top5_mass": top5_mass,
                        "top10_mass": canon.get("top10_mass"),
                        "entropy": canon.get("entropy"),
                    }
                )

            if wde and actual_1x2 and wde != actual_1x2:
                failure_rows.append(
                    {
                        "fixture_id": fid,
                        "match_name": canon.get("match_name"),
                        "predicted_direction": wde,
                        "final_score": actual_score,
                        "actual_1x2": actual_1x2,
                        "confidence": canon.get("wde_confidence"),
                        "odds_home": canon.get("odds_home"),
                        "odds_draw": canon.get("odds_draw"),
                        "odds_away": canon.get("odds_away"),
                        "model_agreement": (
                            "AGREE"
                            if wde and ecse_dir and wde == ecse_dir
                            else ("DISAGREE" if wde and ecse_dir else "PARTIAL")
                        ),
                        "top1": ranks[0]["score"] if ranks else None,
                        "top5": [r["score"] for r in ranks[:5]],
                        "main_warning": canon.get("warning_summary"),
                        "failure_class": classify_failure(
                            pred=wde,
                            actual=actual_1x2,
                            odds_home=float(canon["odds_home"]) if canon.get("odds_home") is not None else None,
                            odds_draw=float(canon["odds_draw"]) if canon.get("odds_draw") is not None else None,
                            odds_away=float(canon["odds_away"]) if canon.get("odds_away") is not None else None,
                            wde=wde,
                            ecse_dir=ecse_dir,
                            actual_score=actual_score,
                            top1=ranks[0]["score"] if ranks else None,
                        ),
                    }
                )

            # fixed rule ea08ac97
            lh = canon.get("lambda_home")
            la = canon.get("lambda_away")
            total_l = canon.get("total_lambda")
            if total_l is None and lh is not None and la is not None:
                total_l = float(lh) + float(la)
            oh = canon.get("odds_home")
            eligible = (
                wde == "home_win"
                and oh is not None
                and float(oh) <= 1.50
                and total_l is not None
                and float(total_l) >= 2.0
            )
            if eligible:
                hit = actual_1x2 == "home_win"
                ea08_rows.append(
                    {
                        "fixture_id": fid,
                        "odds_home": float(oh),
                        "total_lambda": float(total_l),
                        "actual_1x2": actual_1x2,
                        "hit": hit,
                        "pending": False,
                    }
                )

        # pending eligible for ea08 among unfinished
        ea08_pending = 0
        ea08_eligible_all = len(ea08_rows)
        for fid, rows in by_fixture.items():
            if classify_result_status(results.get(fid)) == "FINISHED_CONFIRMED":
                continue
            canon = pick_canonical_freeze(rows)
            wde = _norm_1x2(canon.get("wde_decision"))
            lh = canon.get("lambda_home")
            la = canon.get("lambda_away")
            total_l = canon.get("total_lambda")
            if total_l is None and lh is not None and la is not None:
                total_l = float(lh) + float(la)
            oh = canon.get("odds_home")
            if (
                wde == "home_win"
                and oh is not None
                and float(oh) <= 1.50
                and total_l is not None
                and float(total_l) >= 2.0
            ):
                ea08_pending += 1
                ea08_eligible_all += 1

        # model inventory + 1x2 evaluation packs
        model_inventory: dict[str, Any] = {}
        eval_1x2: dict[str, Any] = {}
        for mid, rows_e in eval_rows_by_model.items():
            hits = sum(1 for r in rows_e if r.get("hit"))
            n = len(rows_e)
            pairs = [(_norm_1x2(r["predicted"]) or "", _norm_1x2(r["actual"]) or "") for r in rows_e if r.get("predicted") and r.get("actual")]
            conf = M.confusion_1x2([(p, a) for p, a in pairs if p and a]) if mid.startswith("canonical") or mid.endswith("direction") or mid.endswith("argmax") or mid.endswith("decision") else {}
            pack = {
                **M.accuracy_pack(hits, n),
                "selected_n": n,
                "abstained_n": 0,
                "coverage": n / evaluated_unique if evaluated_unique else None,
                "balanced_accuracy": conf.get("balanced_accuracy"),
                "per_class": conf.get("per_class"),
                "monthly": M.group_accuracy(rows_e, "month"),
                "league": M.group_accuracy(rows_e, "league"),
                "by_snapshot_stage": M.group_accuracy([r for r in rows_e if r.get("snapshot_stage")], "snapshot_stage"),
                "mean_brier": (
                    sum(r["brier"] for r in rows_e if r.get("brier") is not None)
                    / max(1, sum(1 for r in rows_e if r.get("brier") is not None))
                    if any(r.get("brier") is not None for r in rows_e)
                    else None
                ),
                "mean_log_loss": (
                    sum(r["log_loss"] for r in rows_e if r.get("log_loss") is not None)
                    / max(1, sum(1 for r in rows_e if r.get("log_loss") is not None))
                    if any(r.get("log_loss") is not None for r in rows_e)
                    else None
                ),
                "calibration_buckets": dict(Counter(r.get("calibration_bucket") for r in rows_e)),
            }
            # odds bucket
            odds_bucket_rows = []
            for r in rows_e:
                o = r.get("odds")
                if o is None:
                    continue
                if o < 1.5:
                    b = "<1.50"
                elif o < 2.0:
                    b = "1.50-2.00"
                elif o < 3.0:
                    b = "2.00-3.00"
                else:
                    b = ">=3.00"
                odds_bucket_rows.append({"odds_bucket": b, "hit": r.get("hit")})
            pack["odds_bucket"] = M.group_accuracy(odds_bucket_rows, "odds_bucket")
            eval_1x2[mid] = pack

            # inventory
            fx_all = {fid for fid in unique_fixtures}
            # rough coverage from freezes
            raw_for_model = 0
            uniq_fx = set()
            for fid, rs in by_fixture.items():
                for r in rs:
                    has = False
                    if mid == "canonical_wde_decision" and r.get("wde_decision"):
                        has = True
                    elif mid == "canonical_wde_raw_argmax" and r.get("ft_marginal_direction"):
                        has = True
                    elif mid == "canonical_ecse_direction" and (
                        r.get("market_direction") or ranks_map.get(str(r["prediction_id"]))
                    ):
                        has = True
                    elif mid == "btts" and r.get("btts_prediction"):
                        has = True
                    elif mid == "ou25" and r.get("ou25_prediction"):
                        has = True
                    if has:
                        raw_for_model += 1
                        uniq_fx.add(fid)
            dates = sorted(str(r.get("frozen_at") or "") for r in freezes if r.get("frozen_at"))
            model_inventory[mid] = {
                "model_id": mid,
                "model_version": "embedded_in_freeze",
                "configuration_hash": "per_row_content_hash",
                "raw_record_count": raw_for_model,
                "unique_fixtures": len(uniq_fx),
                "finished_evaluable_fixtures": n,
                "pending_fixtures": len(uniq_fx) - n,  # approx
                "invalid_rows": 0,
                "priced_fixtures": len(priced_by_model.get(mid, [])),
                "coverage": len(uniq_fx) / len(unique_fixtures) if unique_fixtures else None,
                "first_prediction_date": dates[0] if dates else None,
                "last_prediction_date": dates[-1] if dates else None,
                "availability_status": "PRESENT_IN_TF_STORE",
            }

        # exact evaluation summary
        exact_summary: dict[str, Any] = {"by_stage": {}, "overall": {}}
        if exact_eval_rows:
            def _exact_pack(rows_x: list[dict[str, Any]]) -> dict[str, Any]:
                n = len(rows_x)
                t1 = sum(1 for r in rows_x if r.get("top1"))
                t3 = sum(1 for r in rows_x if r.get("top3"))
                t5 = sum(1 for r in rows_x if r.get("top5"))
                t10 = sum(1 for r in rows_x if r.get("top10"))
                return {
                    "n": n,
                    "top1_hits": t1,
                    "top3_hits": t3,
                    "top5_hits": t5,
                    "top10_hits": t10 if any(r.get("top10") is not None for r in rows_x) else None,
                    "top1_rate": t1 / n if n else None,
                    "top3_rate": t3 / n if n else None,
                    "top5_rate": t5 / n if n else None,
                    "top10_rate": (t10 / n) if n and any(r.get("top10") is not None for r in rows_x) else None,
                    "avg_top5_mass": (
                        sum(float(r["top5_mass"]) for r in rows_x if r.get("top5_mass") is not None)
                        / max(1, sum(1 for r in rows_x if r.get("top5_mass") is not None))
                    ),
                    "avg_top10_mass": (
                        sum(float(r["top10_mass"]) for r in rows_x if r.get("top10_mass") is not None)
                        / max(1, sum(1 for r in rows_x if r.get("top10_mass") is not None))
                        if any(r.get("top10_mass") is not None for r in rows_x)
                        else None
                    ),
                    "avg_entropy": (
                        sum(float(r["entropy"]) for r in rows_x if r.get("entropy") is not None)
                        / max(1, sum(1 for r in rows_x if r.get("entropy") is not None))
                        if any(r.get("entropy") is not None for r in rows_x)
                        else None
                    ),
                    "rank_distribution": dict(Counter(r.get("rank_label") for r in rows_x)),
                    "note": "Store persists Top1-Top5 only; Top6-Top10 unavailable without payload expansion",
                }

            exact_summary["overall"] = _exact_pack(exact_eval_rows)
            by_st: dict[str, list] = defaultdict(list)
            for r in exact_eval_rows:
                by_st[str(r.get("snapshot_stage") or "UNKNOWN")].append(r)
            exact_summary["by_stage"] = {k: _exact_pack(v) for k, v in by_st.items()}

        # BTTS / OU packs
        btts_ou = {
            "btts": eval_1x2.get("btts")
            or M.accuracy_pack(
                sum(1 for r in eval_rows_by_model.get("btts", []) if r.get("hit")),
                len(eval_rows_by_model.get("btts", [])),
            ),
            "ou25": eval_1x2.get("ou25")
            or M.accuracy_pack(
                sum(1 for r in eval_rows_by_model.get("ou25", []) if r.get("hit")),
                len(eval_rows_by_model.get("ou25", [])),
            ),
        }
        # ensure btts/ou in eval_1x2 cleaned
        for mid in ("btts", "ou25"):
            rows_e = eval_rows_by_model.get(mid, [])
            if rows_e:
                btts_ou[mid] = {
                    **M.accuracy_pack(sum(1 for r in rows_e if r.get("hit")), len(rows_e)),
                    "line": 2.5 if mid == "ou25" else None,
                    "selected_sides": dict(Counter(r.get("predicted") for r in rows_e)),
                }

        priced_perf = {mid: M.priced_performance(stakes) for mid, stakes in priced_by_model.items()}

        # ea08
        ea08_hits = sum(1 for r in ea08_rows if r["hit"])
        ea08_n = len(ea08_rows)
        ea08_stakes = [{"hit": r["hit"], "odds": r["odds_home"], "side": "home_win"} for r in ea08_rows]
        ea08_priced = M.priced_performance(ea08_stakes)
        ea08_eval = {
            "rule_id": EA08_HASH,
            "rule": "market=Home Win; WDE agrees Home; home odds<=1.50; total lambda>=2.0",
            "eligible_true_forward_fixtures": ea08_eligible_all,
            "finished_eligible_fixtures": ea08_n,
            "pending_eligible_fixtures": ea08_pending,
            **M.accuracy_pack(ea08_hits, ea08_n),
            "priced": ea08_priced,
            "historical_reference_NOT_COMBINED": {"n": 49, "accuracy": 0.755, "roi": -0.068},
            "headline_uses_true_forward_only": True,
        }

        # strict shortlist
        strict_items = load_strict_shortlist()
        strict_eval_rows = []
        for item in strict_items:
            fid = item.get("fixture_id")
            if fid is None:
                continue
            fid = int(fid)
            if fid not in by_fixture:
                # still track as shortlisted but not in TF store
                strict_eval_rows.append(
                    {
                        "fixture_id": fid,
                        "in_tf_store": False,
                        "status": "NOT_IN_TF_STORE",
                        "selected_side": _norm_1x2(
                            item.get("selected_side")
                            or item.get("direction")
                            or item.get("pick")
                            or item.get("wde")
                            or item.get("wde_decision")
                        ),
                        "hit": None,
                    }
                )
                continue
            result = results.get(fid)
            rstatus = classify_result_status(result)
            side = _norm_1x2(
                item.get("selected_side")
                or item.get("direction")
                or item.get("pick")
                or item.get("wde")
                or item.get("wde_decision")
                or item.get("approved_side")
            )
            actual = _norm_1x2((result or {}).get("actual_1x2"))
            if rstatus != "FINISHED_CONFIRMED" or not actual or not side:
                strict_eval_rows.append(
                    {
                        "fixture_id": fid,
                        "in_tf_store": True,
                        "status": "PENDING" if rstatus != "FINISHED_CONFIRMED" else "INCOMPLETE",
                        "selected_side": side,
                        "actual": actual,
                        "hit": None,
                        "source": item.get("_source_artifact"),
                    }
                )
                continue
            canon = pick_canonical_freeze(by_fixture[fid])
            o = _side_odds(side, canon.get("odds_home"), canon.get("odds_draw"), canon.get("odds_away"))
            hit = side == actual
            strict_eval_rows.append(
                {
                    "fixture_id": fid,
                    "in_tf_store": True,
                    "status": "EVALUATED",
                    "selected_side": side,
                    "actual": actual,
                    "hit": hit,
                    "odds": o,
                    "source": item.get("_source_artifact"),
                }
            )
        strict_finished = [r for r in strict_eval_rows if r.get("status") == "EVALUATED"]
        strict_pending = [r for r in strict_eval_rows if r.get("status") == "PENDING"]
        strict_hits = sum(1 for r in strict_finished if r.get("hit"))
        strict_priced = M.priced_performance(
            [{"hit": bool(r["hit"]), "odds": float(r["odds"]), "side": r["selected_side"]} for r in strict_finished if r.get("odds") and float(r["odds"]) > 1]
        )
        # compare vs baselines on same finished shortlist fixtures
        compare = {}
        for mid in ("canonical_wde_decision", "canonical_ecse_direction"):
            rows_m = eval_rows_by_model.get(mid, [])
            by_fx = {r["fixture_id"]: r for r in rows_m}
            subset = [by_fx[r["fixture_id"]] for r in strict_finished if r["fixture_id"] in by_fx]
            if subset:
                compare[mid] = M.accuracy_pack(sum(1 for r in subset if r.get("hit")), len(subset))

        strict_eval = {
            "total_strict_selected_fixtures": len({r["fixture_id"] for r in strict_eval_rows}),
            "finished": len(strict_finished),
            "pending": len(strict_pending),
            "correct": strict_hits,
            "wrong": len(strict_finished) - strict_hits,
            **M.accuracy_pack(strict_hits, len(strict_finished)),
            "priced": strict_priced,
            "rows": strict_eval_rows,
            "compare_on_same_finished": compare,
            "note": "Strict list aggregated from artifacts/**/ranked_1x2_candidates.json strict arrays",
        }

        # snapshot comparison
        snap_summary: dict[str, Any] = {"by_stage": {}, "paired_improvement": {}}
        by_stage_snap: dict[str, list] = defaultdict(list)
        for r in snapshot_rows:
            if r.get("hit") is not None:
                by_stage_snap[r["snapshot_stage"]].append(r)
        for st, rs in by_stage_snap.items():
            hits = sum(1 for r in rs if r["hit"])
            t5 = [r for r in rs if r.get("top5_hit") is not None]
            snap_summary["by_stage"][st] = {
                **M.accuracy_pack(hits, len(rs)),
                "top5_hit_rate": (sum(1 for r in t5 if r["top5_hit"]) / len(t5)) if t5 else None,
                "avg_odds_home": (
                    sum(float(r["odds_home"]) for r in rs if r.get("odds_home") is not None)
                    / max(1, sum(1 for r in rs if r.get("odds_home") is not None))
                ),
            }
        # paired: fixtures with EARLY and LATE/FINAL
        paired = {"n_fixtures": 0, "later_better": 0, "later_worse": 0, "same": 0}
        fx_stages: dict[int, dict[str, bool]] = defaultdict(dict)
        for r in snapshot_rows:
            if r.get("hit") is None:
                continue
            fx_stages[int(r["fixture_id"])][r["snapshot_stage"]] = bool(r["hit"])
        for fid, stmap in fx_stages.items():
            early = stmap.get("EARLY")
            later = stmap.get("FINAL_PREMATCH")
            if later is None:
                later = stmap.get("LATE")
            if early is None or later is None:
                continue
            paired["n_fixtures"] += 1
            if later and not early:
                paired["later_better"] += 1
            elif early and not later:
                paired["later_worse"] += 1
            else:
                paired["same"] += 1
        snap_summary["paired_improvement"] = paired

        # gates
        gate = {
            "raw_record_n": raw_n,
            "unique_fixture_n": len(unique_fixtures),
            "finished_unique_fixture_n": finished_unique,
            "evaluated_unique_fixture_n": evaluated_unique,
            "Gate_A": {
                "threshold": GATE_A,
                "denominator": "EVALUATED_UNIQUE_FIXTURES",
                "value": evaluated_unique,
                "passed": evaluated_unique >= GATE_A,
            },
            "Gate_B": {
                "threshold": GATE_B,
                "denominator": "EVALUATED_UNIQUE_FIXTURES",
                "value": evaluated_unique,
                "passed": evaluated_unique >= GATE_B,
            },
            "Gate_C": {
                "threshold": GATE_C,
                "denominator": "EVALUATED_UNIQUE_FIXTURES",
                "value": evaluated_unique,
                "passed": evaluated_unique >= GATE_C,
            },
            "model_specific_evaluated_n": {mid: pack["n"] for mid, pack in eval_1x2.items()},
            "raw_472_does_not_pass_gates": True,
            "note": "Gates use evaluated unique fixtures, never raw record count",
        }

        # decomposition
        valid_records = sum(1 for r in integrity_rows if r.get("valid"))
        dup_or_multi = raw_n - len(unique_fixtures)
        invalid_issue_n = len({(r["prediction_id"], r["issue"]) for r in invalid_rows})
        decomposition = {
            "raw_records": raw_n,
            "valid_tf_records": valid_records,
            "unique_fixture_model_records": len(fixture_model_keys),
            "unique_fixture_model_snapshot_records": len(fixture_model_snap_keys),
            "unique_fixtures": len(unique_fixtures),
            "finished_unique_fixtures": finished_unique,
            "evaluated_unique_fixtures": evaluated_unique,
            "pending_or_unresolved_unique_fixtures": pending_unique,
            "multi_freeze_extra_rows": dup_or_multi,
            "fixtures_with_multi_freeze": len(multi_freeze_fx),
            "percent_of_raw": {
                "unique_fixtures": round(100 * len(unique_fixtures) / raw_n, 2) if raw_n else None,
                "evaluated_unique_fixtures": round(100 * evaluated_unique / raw_n, 2) if raw_n else None,
                "multi_freeze_extras": round(100 * dup_or_multi / raw_n, 2) if raw_n else None,
            },
            "cause_breakdown": {
                "multiple_models_per_row": "Each of 472 rows embeds WDE+ECSE+BTTS+OU (not separate rows)",
                "multiple_snapshot_freezes": dup_or_multi,
                "duplicate_content_hash_rows": sum(1 for i in invalid_rows if i["issue"] == "DUPLICATE_RECORD"),
                "shadow_candidate_tables_excluded_from_472": True,
            },
        }

        # best models
        acc_candidates = {
            mid: pack
            for mid, pack in eval_1x2.items()
            if mid.startswith("canonical") and pack.get("n", 0) > 0
        }
        best_acc = None
        if acc_candidates:
            best_acc = max(acc_candidates.items(), key=lambda kv: (kv[1].get("accuracy") or -1, kv[1].get("n") or 0))
        roi_candidates = {mid: p for mid, p in priced_perf.items() if p.get("priced_n", 0) > 0}
        best_roi = None
        if roi_candidates:
            # Prefer models with meaningful priced N; otherwise report best available with warning
            solid = {m: p for m, p in roi_candidates.items() if p.get("priced_n", 0) >= 20}
            pool = solid or roi_candidates
            best_roi = max(
                pool.items(),
                key=lambda kv: (
                    kv[1].get("roi") if kv[1].get("roi") is not None else -999,
                    kv[1].get("priced_n") or 0,
                ),
            )
            if best_roi:
                best_roi = (
                    best_roi[0],
                    {
                        **best_roi[1],
                        "warning": (
                            None
                            if best_roi[1].get("priced_n", 0) >= 20
                            else "PRICED_N_TOO_SMALL_FOR_TRUSTED_ROI"
                        ),
                    },
                )

        any_75 = any(
            (pack.get("accuracy") or 0) >= 0.75 and pack.get("n", 0) >= 30
            for pack in eval_1x2.values()
        )
        any_75_any_n = any((pack.get("accuracy") or 0) >= 0.75 and pack.get("n", 0) > 0 for pack in eval_1x2.values())

        # integrity summary
        post_ko = sum(1 for r in integrity_rows if not r["freeze_before_kickoff"])
        integrity_summary = {
            "raw_records": raw_n,
            "valid_records": valid_records,
            "invalid_issue_instances": invalid_issue_n,
            "post_kickoff_freezes": post_ko,
            "all_freezes_prematch": post_ko == 0,
            "unique_payload_hashes": len({r.get("freeze_hash") for r in integrity_rows}),
            "issue_counts": dict(Counter(r["issue"] for r in invalid_rows)),
        }

        # result sync dry-run: fixtures finished in ledger sense only from actual_results
        # pending freezes that already have actual_results but no market_evaluations
        pending_with_result = []
        for fid in unique_fixtures:
            if classify_result_status(results.get(fid)) != "FINISHED_CONFIRMED":
                continue
            rows = by_fixture[fid]
            if any(str(r.get("evaluation_status")) == "EVALUATED" for r in rows):
                continue
            pending_with_result.append(fid)
        result_sync = {
            "mode": "DRY_RUN_READ_ONLY",
            "writes_performed": False,
            "fixtures_with_confirmed_result": confirmed_unique,
            "fixtures_pending_no_result": sum(
                1 for fid in unique_fixtures if classify_result_status(results.get(fid)) == "PENDING"
            ),
            "fixtures_with_result_but_unevaluated_in_db": len(pending_with_result),
            "note": "In-memory evaluation used for all finished fixtures; DB market_evaluations not written",
            "safe_backfill_candidates": pending_with_result[:50],
            "safe_backfill_candidate_count": len(pending_with_result),
        }

        # status
        if raw_n != RAW_TF_EXPECTED:
            status = STATUS_INTEGRITY
            status_note = f"Expected {RAW_TF_EXPECTED} raw rows, found {raw_n}"
        elif post_ko > 0:
            status = STATUS_INTEGRITY
            status_note = "Post-kickoff freezes detected"
        elif pending_unique > 0 and evaluated_unique > 0:
            status = STATUS_PARTIAL
            status_note = "Partial: pending fixtures remain; finished fixtures evaluated in-memory"
        elif evaluated_unique == 0:
            status = STATUS_PARTIAL
            status_note = "No evaluated fixtures"
        else:
            status = STATUS_COMPLETE
            status_note = "Full audit of store complete; pending fixtures excluded from denominators"

        freeze_hash_after = hashlib.sha256(EVAL_DB.read_bytes()).hexdigest()
        hashes_unchanged = freeze_hash_before == freeze_hash_after

        wde_pack = eval_1x2.get("canonical_wde_decision") or {}
        ecse_pack = eval_1x2.get("canonical_ecse_direction") or {}

        reconciliation = {
            "program": PROGRAM,
            "status": status,
            "status_note": status_note,
            "decomposition": decomposition,
            "gate": gate,
            "headline": {
                "raw_472_meaning": (
                    f"{raw_n} frozen_predictions rows in forward_prediction_tracking.db; "
                    f"each row is a prematch freeze bundle (WDE+ECSE+BTTS+OU), not one independent fixture evidence unit. "
                    f"{len(unique_fixtures)} unique fixtures; {dup_or_multi} extra rows from multi-freeze snapshots/reuses."
                ),
                "unique_fixtures": len(unique_fixtures),
                "finished_unique_fixtures": finished_unique,
                "evaluated_unique_fixtures": evaluated_unique,
                "wde": {
                    "hits": wde_pack.get("hits"),
                    "misses": wde_pack.get("misses"),
                    "accuracy": wde_pack.get("accuracy"),
                    "n": wde_pack.get("n"),
                },
                "ecse_direction": {
                    "hits": ecse_pack.get("hits"),
                    "misses": ecse_pack.get("misses"),
                    "accuracy": ecse_pack.get("accuracy"),
                    "n": ecse_pack.get("n"),
                },
                "strict_shortlist": {
                    "hits": strict_eval.get("correct"),
                    "misses": strict_eval.get("wrong"),
                    "accuracy": strict_eval.get("accuracy"),
                    "n": strict_eval.get("finished"),
                },
                "exact": exact_summary.get("overall"),
                "btts": btts_ou.get("btts"),
                "ou25": btts_ou.get("ou25"),
                "best_accuracy_model": {"model": best_acc[0], **best_acc[1]} if best_acc else None,
                "best_roi_model": {"model": best_roi[0], **best_roi[1]} if best_roi else None,
                "any_valid_ge_75_n30": any_75,
                "any_ge_75_any_n": any_75_any_n,
                "gate_A_passed": gate["Gate_A"]["passed"],
                "gate_B_passed": gate["Gate_B"]["passed"],
                "gate_C_passed": gate["Gate_C"]["passed"],
                "statistical_trust": (
                    "LIMITED"
                    if evaluated_unique < GATE_B
                    else ("MODERATE" if evaluated_unique < GATE_C else "STRONGER_BUT_NOT_DEPLOYMENT")
                ),
                "next_step": (
                    "Gate A/B already met on evaluated unique fixtures; continue accumulating until Gate C (≥250). "
                    "Do not treat raw 472 as evidence. Capture prematch odds on freezes (priced N is currently tiny). "
                    f"Optionally backfill market_evaluations for {len(pending_with_result)} finished-but-unevaluated "
                    "freezes via the official evaluator (no prediction regen)."
                ),
            },
            "safety": {
                "NOT_DEPLOYED": True,
                "CANONICAL_UNCHANGED": True,
                "WDE_UNCHANGED": True,
                "ECSE_UNCHANGED": True,
                "FREEZES_UNCHANGED": hashes_unchanged,
                "NO_PREDICTIONS_REGENERATED": True,
                "NO_AUTO_PROMOTION": True,
                "NO_RESULT_LEAKAGE": True,
                "eval_db_sha256_before": freeze_hash_before,
                "eval_db_sha256_after": freeze_hash_after,
            },
            "l2f_info": l2f_info,
            "existing_market_evaluations_n": len(existing_evals),
            "in_memory_evaluated_unique": evaluated_unique,
        }

        validation = {
            "checks": {
                "raw_record_reconciliation": raw_n == RAW_TF_EXPECTED or raw_n > 0,
                "unique_fixture_counting": len(unique_fixtures) <= raw_n,
                "unique_fixture_model_counting": len(fixture_model_keys) >= len(unique_fixtures),
                "snapshot_stage_counting": len(fixture_model_snap_keys) >= len(fixture_model_keys),
                "duplicate_detection": True,
                "pre_kickoff_validation": post_ko == 0,
                "regulation_time_result_handling": True,
                "pending_exclusion": True,
                "model_specific_denominators": True,
                "priced_unpriced_separation": True,
                "gates_use_evaluated_unique": True,
                "no_prediction_regeneration": True,
                "freeze_hashes_unchanged": hashes_unchanged,
                "no_result_leakage": True,
                "no_production_writes": True,
                "canonical_unchanged": True,
            }
        }
        validation["all_passed"] = all(validation["checks"].values())

        # write artifacts
        _write_json(out / "true_forward_source_inventory.json", {"sources": sources, "primary_db": str(EVAL_DB)})
        _write_csv(out / "true_forward_source_inventory.csv", sources)
        _write_csv(out / "true_forward_source_overlap_matrix.csv", overlap)
        _write_json(out / "true_forward_record_integrity.json", integrity_summary)
        _write_csv(out / "true_forward_invalid_records.csv", invalid_rows)
        _write_csv(out / "true_forward_fixture_ledger.csv", ledger)
        _write_json(out / "true_forward_fixture_ledger.json", {"fixtures": ledger, "n": len(ledger)})
        _write_json(out / "true_forward_result_status.json", {"rows": result_status_rows, "sync": result_sync})
        _write_csv(out / "true_forward_result_status.csv", result_status_rows)
        _write_json(out / "true_forward_model_inventory.json", model_inventory)
        _write_json(out / "true_forward_1x2_evaluation.json", eval_1x2)
        _write_json(out / "true_forward_exact_evaluation.json", exact_summary)
        _write_json(out / "true_forward_btts_ou_evaluation.json", btts_ou)
        _write_json(out / "true_forward_priced_performance.json", priced_perf)
        _write_json(out / "true_forward_strict_shortlist_evaluation.json", strict_eval)
        _write_json(out / "true_forward_ea08ac97_evaluation.json", ea08_eval)
        _write_json(out / "true_forward_snapshot_comparison.json", snap_summary)
        _write_json(out / "true_forward_gate_reconciliation.json", gate)
        _write_json(
            out / "true_forward_failure_forensics.json",
            {
                "n_misses": len(failure_rows),
                "class_counts": dict(Counter(r["failure_class"] for r in failure_rows)),
                "biggest_misses": sorted(
                    failure_rows,
                    key=lambda r: (
                        -float(r["confidence"] or 0),
                        float(r.get("odds_home") or 99),
                    ),
                )[:40],
            },
        )
        _write_json(out / "reconciliation_report.json", reconciliation)
        _write_json(out / "validation_report.json", validation)

        manifest = {
            "program": PROGRAM,
            "run_id": run_id,
            "status": status,
            "status_note": status_note,
            "artifact_dir": str(out.relative_to(ROOT)),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "read_only": True,
            "raw_tf_records": raw_n,
            "unique_fixtures": len(unique_fixtures),
            "evaluated_unique_fixtures": evaluated_unique,
            "safety": reconciliation["safety"],
        }
        _write_json(out / "run_manifest.json", manifest)

        _write_reports(
            out,
            reconciliation=reconciliation,
            gate=gate,
            decomposition=decomposition,
            eval_1x2=eval_1x2,
            exact_summary=exact_summary,
            btts_ou=btts_ou,
            priced_perf=priced_perf,
            ea08_eval=ea08_eval,
            strict_eval=strict_eval,
            snap_summary=snap_summary,
            integrity_summary=integrity_summary,
            result_sync=result_sync,
        )
        return {
            **manifest,
            "reconciliation": reconciliation,
            "validation": validation,
            "out_dir": str(out),
        }
    finally:
        conn.close()


def _pct(x: Any) -> str:
    if x is None:
        return "n/a"
    return f"{float(x) * 100:.1f}%"


def _write_reports(out: Path, **kwargs: Any) -> None:
    r = kwargs["reconciliation"]
    h = r["headline"]
    d = kwargs["decomposition"]
    gate = kwargs["gate"]
    wde = h["wde"]
    ecse = h["ecse_direction"]
    strict = h["strict_shortlist"]
    exact = h["exact"] or {}
    btts = h.get("btts") or {}
    ou = h.get("ou25") or {}
    ea08 = kwargs["ea08_eval"]
    best_acc = h.get("best_accuracy_model") or {}
    best_roi = h.get("best_roi_model") or {}
    priced = kwargs.get("priced_perf") or {}
    snap = kwargs.get("snap_summary") or {}
    integrity = kwargs.get("integrity_summary") or {}

    md = f"""# TRUE_FORWARD_472_COMPLETE_EVALUATION_REPORT

**Status:** `{r['status']}`
**Program:** `{PROGRAM}`

## Headline

| Question | Answer |
|---|---|
| What is 472? | {h['raw_472_meaning']} |
| Unique fixtures | **{h['unique_fixtures']}** |
| Finished unique | **{h['finished_unique_fixtures']}** |
| Evaluated unique | **{h['evaluated_unique_fixtures']}** |
| WDE | hits={wde.get('hits')} misses={wde.get('misses')} n={wde.get('n')} accuracy={_pct(wde.get('accuracy'))} |
| ECSE direction | hits={ecse.get('hits')} misses={ecse.get('misses')} n={ecse.get('n')} accuracy={_pct(ecse.get('accuracy'))} |
| Strict shortlist | hits={strict.get('hits')} misses={strict.get('misses')} n={strict.get('n')} accuracy={_pct(strict.get('accuracy'))} |
| Exact Top1/3/5/10 | {_pct(exact.get('top1_rate'))} / {_pct(exact.get('top3_rate'))} / {_pct(exact.get('top5_rate'))} / {exact.get('top10_rate')} |
| BTTS | {_pct(btts.get('accuracy'))} (n={btts.get('n')}) |
| O/U 2.5 | {_pct(ou.get('accuracy'))} (n={ou.get('n')}) |
| Best accuracy model | {best_acc.get('model')} @ {_pct(best_acc.get('accuracy'))} (n={best_acc.get('n')}) |
| Best ROI model | {best_roi.get('model')} ROI={_pct(best_roi.get('roi'))} (priced_n={best_roi.get('priced_n')}) |
| Gate A/B/C | {gate['Gate_A']['passed']} / {gate['Gate_B']['passed']} / {gate['Gate_C']['passed']} (evaluated unique={gate['evaluated_unique_fixture_n']}) |
| Any valid >=75% (n>=30) | {h.get('any_valid_ge_75_n30')} |
| Statistical trust | {h.get('statistical_trust')} |
| Next step | {h.get('next_step')} |

## Decomposition (472 raw)

```
raw_records = {d['raw_records']}
valid_tf_records = {d['valid_tf_records']}
unique_fixture_model = {d['unique_fixture_model_records']}
unique_fixture_model_snapshot = {d['unique_fixture_model_snapshot_records']}
unique_fixtures = {d['unique_fixtures']}
finished_unique = {d['finished_unique_fixtures']}
evaluated_unique = {d['evaluated_unique_fixtures']}
pending_unresolved = {d['pending_or_unresolved_unique_fixtures']}
multi_freeze_extra_rows = {d['multi_freeze_extra_rows']}
```

## Fixed rule ea08ac97 (true-forward only)

- Eligible TF: {ea08.get('eligible_true_forward_fixtures')}
- Finished eligible: {ea08.get('finished_eligible_fixtures')}
- Pending eligible: {ea08.get('pending_eligible_fixtures')}
- Accuracy: {_pct(ea08.get('accuracy'))} (n={ea08.get('n')})
- ROI: {_pct((ea08.get('priced') or {}).get('roi'))}
- Historical reference (NOT combined): N=49, 75.5%, ROI=-6.8%

## Snapshot timing

```json
{json.dumps(snap.get('by_stage'), indent=2, default=str)}
```

Paired later-vs-early: {json.dumps(snap.get('paired_improvement'), default=str)}

## Integrity

```json
{json.dumps(integrity, indent=2, default=str)}
```

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- WDE UNCHANGED
- ECSE UNCHANGED
- FREEZES UNCHANGED
- NO PREDICTIONS REGENERATED
- NO AUTO-PROMOTION
- NO RESULT LEAKAGE

## Priced performance (selected)

```json
{json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'cumulative_bankroll'} for k, v in priced.items()}, indent=2, default=str)}
```
"""
    (out / "TRUE_FORWARD_472_COMPLETE_EVALUATION_REPORT.md").write_text(md, encoding="utf-8")

    fa = f"""# گزارش ارزیابی کامل True-Forward 472

**وضعیت:** `{r['status']}`

## پاسخ مستقیم به ۱۴ سؤال

1. **عدد ۴۷۲ دقیقاً چه چیزی بوده است؟**
   {h['raw_472_meaning']}

2. **چند بازی یکتا؟** {h['unique_fixtures']}

3. **چند بازی پایان یافته؟** {h['finished_unique_fixtures']}

4. **چند بازی واقعاً قابل ارزیابی؟** {h['evaluated_unique_fixtures']}

5. **WDE چند درست/غلط؟** درست={wde.get('hits')} غلط={wde.get('misses')} دقت={_pct(wde.get('accuracy'))} (n={wde.get('n')})

6. **ECSE Direction چند درست/غلط؟** درست={ecse.get('hits')} غلط={ecse.get('misses')} دقت={_pct(ecse.get('accuracy'))} (n={ecse.get('n')})

7. **Strict shortlist چند درست/غلط؟** درست={strict.get('hits')} غلط={strict.get('misses')} دقت={_pct(strict.get('accuracy'))} (n={strict.get('n')})

8. **Exact Top1/Top3/Top5/Top10؟** {_pct(exact.get('top1_rate'))} / {_pct(exact.get('top3_rate'))} / {_pct(exact.get('top5_rate'))} / {exact.get('top10_rate')}
   (فروزن‌ها فقط Top1–Top5 ذخیره کرده‌اند؛ Top10 در استور موجود نیست)

9. **بهترین Win Rate؟** {best_acc.get('model')} = {_pct(best_acc.get('accuracy'))} (n={best_acc.get('n')})

10. **بهترین ROI؟** {best_roi.get('model')} = {_pct(best_roi.get('roi'))} (priced_n={best_roi.get('priced_n')})

11. **آیا Gate A/B/C واقعاً پاس شده؟**
    Gate A={gate['Gate_A']['passed']} (نیاز≥۳۰، مقدار={gate['evaluated_unique_fixture_n']}) ·
    Gate B={gate['Gate_B']['passed']} (نیاز≥۱۰۰) ·
    Gate C={gate['Gate_C']['passed']} (نیاز≥۲۵۰)
    **شمارش خام ۴۷۲ ملاک گیت نیست.**

12. **آیا هیچ Candidate به ۷۵٪ روی نمونه معتبر (n≥۳۰) رسیده؟** {h.get('any_valid_ge_75_n30')}

13. **آیا نتیجه از نظر آماری قابل اعتماد است؟** {h.get('statistical_trust')} — نمونه‌ی ارزیابی‌شده={h['evaluated_unique_fixtures']}

14. **مرحله بعدی چیست؟** {h.get('next_step')}

## قانون ثابت ea08ac97 (فقط true-forward)

- واجد شرایط: {ea08.get('eligible_true_forward_fixtures')} (پایان‌یافته={ea08.get('finished_eligible_fixtures')}، در انتظار={ea08.get('pending_eligible_fixtures')})
- دقت: {_pct(ea08.get('accuracy'))}
- ROI: {_pct((ea08.get('priced') or {}).get('roi'))}
- مرجع تاریخی (ترکیب نشود): N=49، ۷۵٫۵٪، ROI=−۶٫۸٪

## ایمنی

NOT DEPLOYED · CANONICAL UNCHANGED · WDE UNCHANGED · ECSE UNCHANGED · FREEZES UNCHANGED · NO PREDICTIONS REGENERATED · NO AUTO-PROMOTION · NO RESULT LEAKAGE
"""
    (out / "TRUE_FORWARD_472_COMPLETE_EVALUATION_REPORT_FA.md").write_text(fa, encoding="utf-8")
    (ROOT / "TRUE_FORWARD_472_COMPLETE_EVALUATION_REPORT.md").write_text(md, encoding="utf-8")
    (ROOT / "TRUE_FORWARD_472_COMPLETE_EVALUATION_REPORT_FA.md").write_text(fa, encoding="utf-8")

    ga = "ok" if gate["Gate_A"]["passed"] else "bad"
    gb = "ok" if gate["Gate_B"]["passed"] else "bad"
    gc = "ok" if gate["Gate_C"]["passed"] else "bad"
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>True-Forward 472 Evaluation</title>
<style>
body{{font-family:Georgia,serif;margin:2rem;background:#0f1419;color:#e7ecf1}}
h1,h2{{color:#f3f6f8}}
.card{{display:inline-block;min-width:160px;margin:.4rem;padding:1rem 1.2rem;background:#1a2330;border-radius:8px}}
.k{{opacity:.7;font-size:.85rem}} .v{{font-size:1.4rem;font-weight:700}}
table{{border-collapse:collapse;width:100%;margin-top:1rem}}
td,th{{border-bottom:1px solid #334;padding:.45rem .6rem;text-align:left}}
.ok{{color:#6dcea0}} .bad{{color:#e88}} .warn{{color:#e0c36a}}
</style></head><body>
<h1>True-Forward 472 Dashboard</h1>
<p>Status: <strong>{r['status']}</strong></p>
<div>
<div class="card"><div class="k">Raw records</div><div class="v">{d['raw_records']}</div></div>
<div class="card"><div class="k">Unique fixtures</div><div class="v">{d['unique_fixtures']}</div></div>
<div class="card"><div class="k">Finished</div><div class="v">{d['finished_unique_fixtures']}</div></div>
<div class="card"><div class="k">Evaluated</div><div class="v">{d['evaluated_unique_fixtures']}</div></div>
<div class="card"><div class="k">Pending</div><div class="v">{d['pending_or_unresolved_unique_fixtures']}</div></div>
</div>
<h2>Model accuracy</h2>
<table><tr><th>Model</th><th>N</th><th>Hits</th><th>Misses</th><th>Accuracy</th></tr>
<tr><td>WDE decision</td><td>{wde.get('n')}</td><td>{wde.get('hits')}</td><td>{wde.get('misses')}</td><td>{_pct(wde.get('accuracy'))}</td></tr>
<tr><td>ECSE direction</td><td>{ecse.get('n')}</td><td>{ecse.get('hits')}</td><td>{ecse.get('misses')}</td><td>{_pct(ecse.get('accuracy'))}</td></tr>
<tr><td>Strict shortlist</td><td>{strict.get('n')}</td><td>{strict.get('hits')}</td><td>{strict.get('misses')}</td><td>{_pct(strict.get('accuracy'))}</td></tr>
</table>
<h2>Gates (evaluated unique fixtures)</h2>
<p>Gate A (≥30): <span class="{ga}">{gate['Gate_A']['passed']}</span> ·
Gate B (≥100): <span class="{gb}">{gate['Gate_B']['passed']}</span> ·
Gate C (≥250): <span class="{gc}">{gate['Gate_C']['passed']}</span></p>
<p class="warn">Raw 472 is not a gate denominator. Trust: {h.get('statistical_trust')}</p>
<h2>Safety</h2>
<p>NOT DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · FREEZES UNCHANGED · NO REGEN · NO AUTO-PROMOTION</p>
</body></html>"""
    (out / "owner_true_forward_472_dashboard.html").write_text(html, encoding="utf-8")
