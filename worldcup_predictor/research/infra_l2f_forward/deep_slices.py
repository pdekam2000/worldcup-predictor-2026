"""Deep-slice analysis for L2-F vs canonical (research-only; no routing)."""

from __future__ import annotations

import json
import math
import random
import sqlite3
from collections import defaultdict
from typing import Any

from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE
from worldcup_predictor.research.infra_l2f_forward.historical_replay import EVAL_TABLE, ensure_replay_schema


def _wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom))


def _bootstrap_diff(
    a_hits: list[int],
    b_hits: list[int],
    *,
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Return mean(a-b), 2.5%, 97.5% bootstrap percentiles of mean diff."""
    n = min(len(a_hits), len(b_hits))
    if n == 0:
        return (0.0, 0.0, 0.0)
    a = a_hits[:n]
    b = b_hits[:n]
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(a[i] - b[i] for i in idx) / n)
    diffs.sort()
    mean = sum(a[i] - b[i] for i in range(n)) / n
    lo = diffs[int(0.025 * (n_boot - 1))]
    hi = diffs[int(0.975 * (n_boot - 1))]
    return (mean, lo, hi)


def _safe_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {}


def _fetch_freeze(eval_conn: sqlite3.Connection, freeze_id: str | None, fixture_id: int) -> dict[str, Any]:
    cols = {r[1] for r in eval_conn.execute("PRAGMA table_info(frozen_predictions)").fetchall()}
    wanted = [
        "competition",
        "kickoff",
        "frozen_at",
        "lambda_home",
        "lambda_away",
        "odds_home",
        "odds_draw",
        "odds_away",
        "complete_payload_json",
        "ecse_payload_json",
        "wde_payload_json",
        "ou_payload_json",
        "btts_payload_json",
    ]
    select_cols = [c for c in wanted if c in cols]
    if not select_cols:
        return {}
    sql_cols = ", ".join(select_cols)
    row = None
    if freeze_id:
        row = eval_conn.execute(
            f"SELECT {sql_cols} FROM frozen_predictions WHERE prediction_id=?",
            (freeze_id,),
        ).fetchone()
    if row is None:
        row = eval_conn.execute(
            f"SELECT {sql_cols} FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1",
            (fixture_id,),
        ).fetchone()
    return dict(row) if row is not None else {}


def _load_eval_join(
    eval_conn: sqlite3.Connection,
    fi_conn: sqlite3.Connection,
    *,
    cohort_types: list[str],
    model_id: str = "EXACT_V2_SELECTED",
) -> list[dict[str, Any]]:
    ensure_replay_schema(fi_conn)
    placeholders = ",".join("?" for _ in cohort_types)
    rows = fi_conn.execute(
        f"""
        SELECT e.fixture_id, e.freeze_id, e.cohort_type, e.top1, e.top3, e.top5, e.top10,
               e.canonical_top5, e.lambda_home, e.lambda_away, e.actual_home, e.actual_away,
               e.log_loss, e.actual_rank, e.p_actual
        FROM {EVAL_TABLE} e
        WHERE e.cohort_type IN ({placeholders}) AND e.model_id=?
        """,
        (*cohort_types, model_id),
    ).fetchall()
    out = []
    for r in rows:
        fid = int(r[0] if not isinstance(r, sqlite3.Row) else r["fixture_id"])
        freeze_id = r[1] if not isinstance(r, sqlite3.Row) else r["freeze_id"]
        frd = _fetch_freeze(eval_conn, freeze_id, fid)
        shadow = fi_conn.execute(
            f"""
            SELECT top5_mass, entropy, payload_json, lambda_home, lambda_away
            FROM {SHADOW_TABLE}
            WHERE fixture_id=? AND model_id=?
            ORDER BY created_at_utc DESC LIMIT 1
            """,
            (fid, model_id),
        ).fetchone()
        ctx = None
        try:
            ctx = eval_conn.execute(
                "SELECT * FROM prediction_context WHERE prediction_id=?",
                (freeze_id,),
            ).fetchone()
        except Exception:
            ctx = None

        ah = int(r[10] if not isinstance(r, sqlite3.Row) else r["actual_home"])
        aa = int(r[11] if not isinstance(r, sqlite3.Row) else r["actual_away"])
        tg = ah + aa
        lh = float(r[8] if not isinstance(r, sqlite3.Row) else r["lambda_home"] or 0)
        la = float(r[9] if not isinstance(r, sqlite3.Row) else r["lambda_away"] or 0)
        et = lh + la

        complete = _safe_json(frd.get("complete_payload_json"))
        ecse = _safe_json(frd.get("ecse_payload_json"))
        ou = _safe_json(frd.get("ou_payload_json"))
        btts = _safe_json(frd.get("btts_payload_json"))

        oh = frd.get("odds_home")
        od = frd.get("odds_draw")
        oa = frd.get("odds_away")
        try:
            oh_f, oa_f = float(oh), float(oa)
            balanced = abs(oh_f - oa_f) <= 0.40
            favorite = "home" if oh_f < oa_f else "away" if oa_f < oh_f else "even"
            fav_strength = abs(oh_f - oa_f)
        except (TypeError, ValueError):
            balanced = None
            favorite = "unknown"
            fav_strength = None

        # Prematch expected total buckets
        if et < 2.0:
            et_bucket = "lt_2.0"
        elif et < 2.5:
            et_bucket = "2.0_2.5"
        elif et < 3.0:
            et_bucket = "2.5_3.0"
        else:
            et_bucket = "gte_3.0"

        if tg <= 1:
            tg_bucket = "0-1"
        elif tg <= 3:
            tg_bucket = "2-3"
        else:
            tg_bucket = "4+"

        top5_mass = None
        entropy = None
        if shadow:
            top5_mass = shadow[0] if not isinstance(shadow, sqlite3.Row) else shadow["top5_mass"]
            entropy = shadow[1] if not isinstance(shadow, sqlite3.Row) else shadow["entropy"]

        # OU direction from payload if present
        ou_dir = None
        for key in ("pick", "direction", "prediction", "selected"):
            if key in ou and ou[key] is not None:
                ou_dir = str(ou[key])
                break
        if ou_dir is None and "over_2_5" in str(ou).lower():
            ou_dir = "over_hint"
        if ou_dir is None and "under_2_5" in str(ou).lower():
            ou_dir = "under_hint"

        # Timing to kickoff
        timing_bucket = "unknown"
        try:
            from worldcup_predictor.research.infra_l2f_forward.historical_cohort import _parse_dt

            fr_t = _parse_dt(frd.get("frozen_at"))
            ko_t = _parse_dt(frd.get("kickoff"))
            if fr_t and ko_t:
                hours = (ko_t - fr_t).total_seconds() / 3600.0
                if hours < 6:
                    timing_bucket = "lt_6h"
                elif hours < 24:
                    timing_bucket = "6_24h"
                else:
                    timing_bucket = "gte_24h"
        except Exception:
            pass

        ctxd = dict(ctx) if ctx is not None and isinstance(ctx, sqlite3.Row) else {}
        no_bet = None
        consensus = None
        if complete:
            no_bet = complete.get("no_bet") or complete.get("no_bet_status")
            consensus = complete.get("consensus") or complete.get("consensus_class")
        if ctxd:
            consensus = consensus or ctxd.get("market_agreement_class") or ctxd.get("conflict_class")

        # ECSE tail mass above 3 goals if present in payload
        tail_mass = None
        tops = ecse.get("top10") or ecse.get("top_scores") or complete.get("ecse_top10")
        if isinstance(tops, list):
            mass = 0.0
            for item in tops:
                if isinstance(item, dict):
                    score = str(item.get("score") or item.get("label") or "")
                    p = item.get("probability") or item.get("p") or 0
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    score, p = str(item[0]), item[1]
                else:
                    continue
                try:
                    h, a = score.replace(":", "-").split("-")[:2]
                    if int(h) + int(a) >= 4:
                        mass += float(p)
                except Exception:
                    continue
            tail_mass = mass

        out.append(
            {
                "fixture_id": fid,
                "freeze_id": freeze_id,
                "cohort_type": r[2] if not isinstance(r, sqlite3.Row) else r["cohort_type"],
                "competition": frd.get("competition") or "unknown",
                "top1": int(r[3] if not isinstance(r, sqlite3.Row) else r["top1"] or 0),
                "top3": int(r[4] if not isinstance(r, sqlite3.Row) else r["top3"] or 0),
                "top5": int(r[5] if not isinstance(r, sqlite3.Row) else r["top5"] or 0),
                "top10": int(r[6] if not isinstance(r, sqlite3.Row) else r["top10"] or 0),
                "canonical_top5": (
                    int(r[7])
                    if (r[7] if not isinstance(r, sqlite3.Row) else r["canonical_top5"]) is not None
                    else None
                ),
                "actual_total_goals": tg,
                "tg_bucket_outcome": tg_bucket,
                "expected_total_lambda": et,
                "et_bucket_prematch": et_bucket,
                "balanced_prematch": balanced,
                "favorite_prematch": favorite,
                "fav_strength_prematch": fav_strength,
                "top5_mass": float(top5_mass) if top5_mass is not None else None,
                "entropy": float(entropy) if entropy is not None else None,
                "ou_direction_prematch": ou_dir,
                "timing_to_kickoff_prematch": timing_bucket,
                "no_bet": no_bet,
                "consensus": consensus,
                "btts_payload_present": bool(btts),
                "ecse_tail_mass_ge4_prematch": tail_mass,
                "uses_only_prematch_for_slice_keys": True,  # except tg_bucket_outcome
            }
        )
    return out


def summarize_slice(rows: list[dict[str, Any]], *, key: str, prematch_only: bool) -> list[dict[str, Any]]:
    buckets: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        buckets[r.get(key)].append(r)
    out = []
    for label, rs in sorted(buckets.items(), key=lambda x: (-len(x[1]), str(x[0]))):
        n = len(rs)
        c_hits = [int(x["canonical_top5"]) for x in rs if x.get("canonical_top5") is not None]
        e1 = [int(x["top1"]) for x in rs]
        e3 = [int(x["top3"]) for x in rs]
        e5 = [int(x["top5"]) for x in rs]
        c_n = len(c_hits)
        c_top5 = sum(c_hits) / c_n if c_n else None
        e_top5 = sum(e5) / n
        mean_diff, lo, hi = _bootstrap_diff(e5, c_hits if c_n == n else e5)
        out.append(
            {
                "slice_key": key,
                "slice_value": label,
                "n": n,
                "canonical_top5": c_top5,
                "exact_v2_top1": sum(e1) / n,
                "exact_v2_top3": sum(e3) / n,
                "exact_v2_top5": e_top5,
                "abs_diff_top5": (e_top5 - c_top5) if c_top5 is not None else None,
                "exact_v2_top5_wilson_95": _wilson_interval(sum(e5), n),
                "canonical_top5_wilson_95": _wilson_interval(sum(c_hits), c_n) if c_n else None,
                "bootstrap_diff_exact_minus_canonical_95": {"mean": mean_diff, "lo": lo, "hi": hi},
                "prematch_observable_slice": prematch_only and key != "tg_bucket_outcome",
                "warning": (
                    "OUTCOME_DEFINED_SLICE_NOT_FOR_ROUTING"
                    if key == "tg_bucket_outcome"
                    else None
                ),
            }
        )
    return out


def run_deep_slice_report(
    eval_conn: sqlite3.Connection,
    fi_conn: sqlite3.Connection,
    *,
    cohort_types: list[str] | None = None,
) -> dict[str, Any]:
    cohort_types = cohort_types or ["historical_replay", "historical_replay_result_recovered"]
    rows = _load_eval_join(eval_conn, fi_conn, cohort_types=cohort_types)
    slices = {
        "tg_bucket_outcome": summarize_slice(rows, key="tg_bucket_outcome", prematch_only=False),
        "et_bucket_prematch": summarize_slice(rows, key="et_bucket_prematch", prematch_only=True),
        "competition": summarize_slice(rows, key="competition", prematch_only=True),
        "balanced_prematch": summarize_slice(rows, key="balanced_prematch", prematch_only=True),
        "favorite_prematch": summarize_slice(rows, key="favorite_prematch", prematch_only=True),
        "timing_to_kickoff_prematch": summarize_slice(
            rows, key="timing_to_kickoff_prematch", prematch_only=True
        ),
        "ou_direction_prematch": summarize_slice(rows, key="ou_direction_prematch", prematch_only=True),
    }
    # Entropy / top5 mass quantiles (prematch shadow outputs — still prediction-time)
    for metric, edges, name in (
        ("entropy", [None, 2.5, 3.0, 3.5, None], "entropy_bucket_prematch"),
        ("top5_mass", [None, 0.35, 0.45, 0.55, None], "top5_mass_bucket_prematch"),
    ):
        for r in rows:
            v = r.get(metric)
            if v is None:
                r[name] = "unknown"
                continue
            if edges[1] is not None and v < edges[1]:
                r[name] = f"lt_{edges[1]}"
            elif edges[2] is not None and v < edges[2]:
                r[name] = f"{edges[1]}_{edges[2]}"
            elif edges[3] is not None and v < edges[3]:
                r[name] = f"{edges[2]}_{edges[3]}"
            else:
                r[name] = f"gte_{edges[3]}"
        slices[name] = summarize_slice(rows, key=name, prematch_only=True)

    return {
        "n_rows": len(rows),
        "cohort_types": cohort_types,
        "slices": slices,
        "note": (
            "tg_bucket_outcome uses final goals and must not drive live routing. "
            "Prematch slices are candidates for research gates only."
        ),
    }
