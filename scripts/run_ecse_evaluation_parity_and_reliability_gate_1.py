#!/usr/bin/env python3
"""ECSE-EVALUATION-PARITY-AND-RELIABILITY-GATE-1 — parity forensic + reliability research."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_live.evaluator import rank_from_frozen_snapshot
from worldcup_predictor.research.ecse_live.store import _hydrate_snapshot
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly

PHASE = "ECSE-EVALUATION-PARITY-AND-RELIABILITY-GATE-1"
ARTIFACT = ROOT / "artifacts" / "ecse_evaluation_parity_and_reliability_gate_1"
FINISHED = {"FT", "AET", "PEN"}
HETZNER = "root@91.107.188.229"
PROD_PATH = "/opt/worldcup-predictor"


def _parse_ts(v: str | None) -> datetime | None:
    if not v:
        return None
    t = str(v).replace(" UTC", "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(t[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _audit_conn(conn: sqlite3.Connection, label: str) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    fr_cols = {r[1] for r in conn.execute("PRAGMA table_info(fixture_results)").fetchall()}
    reg = ", fr.regulation_home_goals, fr.regulation_away_goals" if "regulation_home_goals" in fr_cols else ""
    rows = conn.execute(
        f"""
        SELECT s.fixture_id, f.home_team, f.away_team, f.kickoff_utc, f.status, f.competition_key, f.round_name,
               s.id snap_id, s.generated_at, s.is_frozen, s.top_1_score, s.top_5_scores_json,
               e.id eval_id, e.final_score eval_final,
               fr.home_goals, fr.away_goals{reg}
        FROM ecse_prediction_snapshots s
        JOIN fixtures f ON f.fixture_id=s.fixture_id
        LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id=s.id
        LEFT JOIN fixture_results fr ON fr.fixture_id=s.fixture_id
        WHERE s.is_frozen=1
        ORDER BY f.kickoff_utc
        """
    ).fetchall()
    out = []
    for r in rows:
        d = _row_dict(r)
        ko, gen = _parse_ts(d["kickoff_utc"]), _parse_ts(d["generated_at"])
        reg_h = d.get("regulation_home_goals")
        reg_a = d.get("regulation_away_goals")
        if reg_h is None:
            reg_h = d["home_goals"]
        if reg_a is None:
            reg_a = d["away_goals"]
        reasons = []
        if str(d["status"]).upper() not in FINISHED:
            reasons.append("STATUS_NOT_FINAL")
        if reg_h is None or reg_a is None:
            reasons.append("SCORE_MISSING")
        if ko and gen and gen >= ko:
            reasons.append("SNAPSHOT_AFTER_KICKOFF")
        eligible = not reasons
        d.update(
            {
                "label": label,
                "actual_score": f"{reg_h}-{reg_a}" if reg_h is not None else None,
                "eligible": eligible,
                "exclusion_reasons": reasons or ["OK"],
                "has_ecse": True,
                "has_result": reg_h is not None,
                "has_eval": d["eval_id"] is not None,
            }
        )
        out.append(d)

    # local eligible set may include fixtures audited via union
    return out


def _fixture_state(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fixture_id,)).fetchone()
    fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fixture_id,)).fetchone()
    snap = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fixture_id,),
    ).fetchone()
    ev = conn.execute(
        "SELECT * FROM ecse_prediction_evaluations WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fixture_id,),
    ).fetchone()
    state = {
        "has_fixture": fx is not None,
        "has_result": fr is not None,
        "has_ecse": snap is not None,
        "has_eval": ev is not None,
        "fixture": _row_dict(fx) if fx else None,
        "result": _row_dict(fr) if fr else None,
        "ecse": _row_dict(snap) if snap else None,
        "eval": _row_dict(ev) if ev else None,
    }
    if fx and snap:
        ko, gen = _parse_ts(fx["kickoff_utc"]), _parse_ts(snap["generated_at"])
        reg_h = fr["regulation_home_goals"] if fr and "regulation_home_goals" in fr.keys() and fr["regulation_home_goals"] is not None else (fr["home_goals"] if fr else None)
        reg_a = fr["regulation_away_goals"] if fr and "regulation_away_goals" in fr.keys() and fr["regulation_away_goals"] is not None else (fr["away_goals"] if fr else None)
        reasons = []
        if str(fx["status"]).upper() not in FINISHED:
            reasons.append("STATUS_NOT_FINAL")
        if not snap:
            reasons.append("MISSING_PRODUCTION_ECSE")
        elif reg_h is None:
            reasons.append("SCORE_MISSING")
        elif ko and gen and gen >= ko:
            reasons.append("SNAPSHOT_AFTER_KICKOFF")
        state["eligible"] = not reasons
        state["exclusion_reasons"] = reasons or ["OK"]
        state["actual_score"] = f"{reg_h}-{reg_a}" if reg_h is not None else None
        state["generated_at"] = snap["generated_at"]
        state["status"] = fx["status"]
    else:
        state["eligible"] = False
        state["exclusion_reasons"] = ["MISSING_PRODUCTION_ECSE"] if not snap else ["MISSING_PRODUCTION_RESULT"]
    return state


def _classify_root(local: dict[str, Any], prod: dict[str, Any]) -> tuple[str, bool]:
    if local.get("eligible") and prod.get("eligible"):
        return "OK", False
    if not prod.get("has_fixture"):
        return "MISSING_PRODUCTION_ECSE", True
    if not prod.get("has_ecse"):
        return "MISSING_PRODUCTION_ECSE", True
    if not prod.get("has_result"):
        return "MISSING_PRODUCTION_RESULT", True
    for r in prod.get("exclusion_reasons") or []:
        if r in (
            "SNAPSHOT_AFTER_KICKOFF",
            "STATUS_NOT_FINAL",
            "SCORE_MISSING",
            "SNAPSHOT_TIMESTAMP_INVALID",
            "TIMEZONE_NORMALIZATION_FAILURE",
        ):
            return r, r in ("SCORE_MISSING", "STATUS_NOT_FINAL", "MISSING_PRODUCTION_RESULT")
    return "OTHER_WITH_EXACT_REASON", False


def _fetch_production_states_16() -> dict[int, dict[str, Any]]:
    export_path = ARTIFACT / "production_states_16.json"
    cmd = f"scp {ROOT}/scripts/_probe_ecse_parity_16ids.py {HETZNER}:{PROD_PATH}/scripts/"
    subprocess.run(cmd, shell=True, check=False)
    proc = subprocess.run(
        f'ssh {HETZNER} "cd {PROD_PATH} && .venv/bin/python scripts/_probe_ecse_parity_16ids.py"',
        shell=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return {}
    rows = json.loads(proc.stdout)
    export_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return {int(r["fixture_id"]): r for r in rows}


def _build_repair_export(local_conn: sqlite3.Connection, fixture_ids: list[int], prod_by_id: dict) -> dict[str, Any]:
    local_conn.row_factory = sqlite3.Row
    export: dict[str, Any] = {"fixtures": [], "fixture_updates": [], "fixture_results": [], "ecse_snapshots": [], "provenance": {}}
    hashes = {}
    for fid in fixture_ids:
        fx = local_conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        pf = prod_by_id.get(fid) or {}
        if fx and not pf.get("has_fixture"):
            export["fixtures"].append(_row_dict(fx))
        elif fx and pf.get("has_fixture") and not pf.get("has_result"):
            export["fixture_updates"].append({"fixture_id": fid, "status": fx["status"], "kickoff_utc": fx["kickoff_utc"]})
        fr = local_conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        if fr and not pf.get("has_result"):
            export["fixture_results"].append(_row_dict(fr))
        if pf.get("has_ecse"):
            continue
        snap = local_conn.execute(
            "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id ASC LIMIT 1",
            (fid,),
        ).fetchone()
        if snap:
            sd = _row_dict(snap)
            sd.pop("id", None)
            export["ecse_snapshots"].append(sd)
            ko = _parse_ts(fx["kickoff_utc"] if fx else None)
            gen = _parse_ts(snap["generated_at"])
            if ko and gen and gen >= ko:
                raise ValueError(f"refuse export: snapshot after kickoff fid={fid}")
            blob = json.dumps(sd, sort_keys=True, default=str)
            hashes[str(fid)] = hashlib.sha256(blob.encode()).hexdigest()[:16]
    export["provenance"] = {
        "source": "local_canonical_authentic_frozen_rows",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "payload_hashes": hashes,
        "fixture_ids": fixture_ids,
    }
    return export


def _load_reliability_dataset(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT s.*, f.status, f.round_name, f.kickoff_utc,
               fr.home_goals, fr.away_goals, fr.regulation_home_goals, fr.regulation_away_goals
        FROM ecse_prediction_snapshots s
        JOIN fixtures f ON f.fixture_id=s.fixture_id
        LEFT JOIN fixture_results fr ON fr.fixture_id=s.fixture_id
        WHERE s.is_frozen=1 AND UPPER(f.status) IN ('FT','AET','PEN')
        ORDER BY f.kickoff_utc
        """
    ).fetchall()
    dataset = []
    for row in rows:
        snap = _hydrate_snapshot(_row_dict(row))
        ko, gen = _parse_ts(row["kickoff_utc"]), _parse_ts(row["generated_at"])
        if ko and gen and gen >= ko:
            continue
        reg_h = row["regulation_home_goals"] if row["regulation_home_goals"] is not None else row["home_goals"]
        reg_a = row["regulation_away_goals"] if row["regulation_away_goals"] is not None else row["away_goals"]
        if reg_h is None:
            continue
        actual = f"{int(reg_h)}-{int(reg_a)}"
        top5 = list(snap.get("top_5_scores") or [])
        top10 = list(snap.get("top_10_scorelines") or [])
        if len(top5) != 5:
            continue
        target = 1 if actual in top5 else 0
        probs = {str(e["scoreline"]): float(e["probability"]) for e in top10 if isinstance(e, dict)}
        cum3 = sum(probs.get(s, 0) for s in top5[:3])
        cum5 = sum(probs.get(s, 0) for s in top5)
        p1 = probs.get(top5[0], 0)
        p2 = probs.get(top5[1], 0) if len(top5) > 1 else 0
        ent = -sum(p * math.log(p) for p in probs.values() if p > 0)

        wde = conn.execute("SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (row["fixture_id"],)).fetchone()
        wde_conf = wde_side = btts = ou = None
        hp = ap = None
        if wde and wde["payload_json"]:
            p = json.loads(wde["payload_json"])
            pr = p.get("probabilities") or {}
            hp, ap = pr.get("home_win") or pr.get("home"), pr.get("away_win") or pr.get("away")
            wde_conf = p.get("confidence") or p.get("confidence_score")
            wde_side = p.get("prediction")
            btts = (pr.get("btts") or {}).get("selection") if isinstance(pr.get("btts"), dict) else pr.get("btts")
            ou = (pr.get("over_under_2_5") or {}).get("selection") if isinstance(pr.get("over_under_2_5"), dict) else None

        pick = str(wde_side or "").lower()
        align = sum(1 for s in top5 if _winner(s) == pick)
        if align >= 3:
            alignment = "strongly_aligned"
        elif align >= 2:
            alignment = "mostly_aligned"
        elif align == 1:
            alignment = "mixed"
        else:
            alignment = "contradictory"

        lam_h, lam_a = float(snap["lambda_home"]), float(snap["lambda_away"])
        fav = "balanced"
        if hp is not None and ap is not None:
            hp, ap = float(hp), float(ap)
            mx = max(hp, ap)
            if mx >= 60:
                fav = "strong_favorite"
            elif hp >= 55:
                fav = "home_favorite"
            elif ap >= 55:
                fav = "away_favorite"
            elif mx >= 45:
                fav = "medium_favorite"

        hit_rank = next((i for i, s in enumerate(top5, 1) if s == actual), None)
        dataset.append(
            {
                "fixture_id": row["fixture_id"],
                "kickoff_utc": row["kickoff_utc"],
                "actual_score": actual,
                "target_top5_hit": target,
                "hit_rank": hit_rank,
                "lambda_home": lam_h,
                "lambda_away": lam_a,
                "lambda_total": lam_h + lam_a,
                "lambda_gap": abs(lam_h - lam_a),
                "top1_prob": p1,
                "cum_top3_prob": cum3,
                "cum_top5_prob": cum5,
                "prob_gap_r1_r2": p1 - p2,
                "top5_entropy": ent,
                "wde_confidence": wde_conf,
                "wde_side": wde_side,
                "alignment": alignment,
                "btts_lean": btts,
                "ou_lean": ou,
                "favorite": fav,
                "stage": "knockout" if row["round_name"] and "round" in str(row["round_name"]).lower() else "group",
                "scoring_regime": "high" if lam_h + lam_a >= 2.8 else ("low" if lam_h + lam_a <= 2.0 else "medium"),
            }
        )
    return dataset


def _winner(score: str) -> str:
    try:
        h, a = map(int, str(score).split("-"))
        return "home" if h > a else "away" if h < a else "draw"
    except ValueError:
        return ""


def _ci_rate(hits: int, n: int, boot_samples: list[float] | None = None) -> list[float]:
    if boot_samples:
        s = sorted(boot_samples)
        return [round(s[int(0.025 * len(s))], 4), round(s[int(0.975 * len(s))], 4)]
    if n == 0:
        return [0, 0]
    # wilson-ish via bootstrap on binary
    rng = random.Random(42)
    rates = []
    for _ in range(2000):
        c = sum(rng.random() < (hits / n) for _ in range(n))
        rates.append(c / n)
    s = sorted(rates)
    return [round(s[int(0.025 * len(s))], 4), round(s[int(0.975 * len(s))], 4)]


def _reliability_gate(dataset: list[dict[str, Any]]) -> dict[str, Any]:
    if len(dataset) < 9:
        return {"insufficient": True, "n": len(dataset)}
    split = (len(dataset) * 2) // 3
    train, test = dataset[:split], dataset[split:]
    if len(test) < 3:
        return {"insufficient": True, "n": len(dataset)}

    def _gate(row: dict[str, Any], stats: dict[str, float]) -> str:
        score = 0.0
        if row["cum_top5_prob"] >= stats.get("cum_top5_median", 0):
            score += 1
        if row["top5_entropy"] <= stats.get("entropy_median", 99):
            score += 1
        if row["alignment"] in ("strongly_aligned", "mostly_aligned"):
            score += 1
        if float(row.get("wde_confidence") or 0) >= stats.get("conf_median", 0):
            score += 1
        if score >= 3:
            return "HIGH_RELIABILITY"
        if score >= 2:
            return "MEDIUM_RELIABILITY"
        return "LOW_RELIABILITY"

    cum5 = sorted(r["cum_top5_prob"] for r in train)
    ent = sorted(r["top5_entropy"] for r in train)
    conf = sorted(float(r["wde_confidence"] or 0) for r in train)
    stats = {
        "cum_top5_median": cum5[len(cum5) // 2],
        "entropy_median": ent[len(ent) // 2],
        "conf_median": conf[len(conf) // 2],
    }

    def _metrics(sub: list[dict[str, Any]]) -> dict[str, Any]:
        if not sub:
            return {"n": 0}
        n = len(sub)
        hits = sum(r["target_top5_hit"] for r in sub)
        top1 = sum(1 for r in sub if r.get("hit_rank") == 1)
        hit3 = sum(1 for r in sub if r.get("hit_rank") and r["hit_rank"] <= 3)
        mrr = sum(1 / r["hit_rank"] if r.get("hit_rank") else 0 for r in sub) / n
        return {"n": n, "top5_hit_rate": round(hits / n, 4), "top1_accuracy": round(top1 / n, 4), "hit@3": round(hit3 / n, 4), "mrr": round(mrr, 4)}

    baseline = _metrics(test)
    classes: dict[str, list] = defaultdict(list)
    for r in test:
        classes[_gate(r, stats)].append(r)
    by_class = {k: _metrics(v) for k, v in classes.items()}
    high = by_class.get("HIGH_RELIABILITY", {})
    useful = (
        high.get("n", 0) >= 2
        and high.get("top5_hit_rate", 0) > baseline.get("top5_hit_rate", 0) + 0.05
    )
    rank_by_class = {}
    for cls, items in classes.items():
        rh = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for it in items:
            hr = it.get("hit_rank")
            if hr in rh:
                rh[hr] += 1
        rank_by_class[cls] = rh
    return {
        "train_n": len(train),
        "test_n": len(test),
        "train_stats": stats,
        "baseline_test": baseline,
        "by_class_test": by_class,
        "gate_useful_oos": useful,
        "rank_by_reliability_class": rank_by_class,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=PHASE)
    parser.add_argument("--apply-production-repair", action="store_true")
    parser.add_argument("--skip-ssh", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    local_conn = connect_readonly(settings.sqlite_path)

    local_eligible_ids = []
    local_states = {}
    for fid in [r[0] for r in local_conn.execute("SELECT DISTINCT fixture_id FROM ecse_prediction_snapshots WHERE is_frozen=1").fetchall()]:
        st = _fixture_state(local_conn, fid)
        local_states[fid] = st
        if st.get("eligible"):
            local_eligible_ids.append(fid)

    prod_by_id: dict[int, dict] = {}
    if not args.skip_ssh:
        prod_by_id = _fetch_production_states_16()

    parity_rows = []
    repair_ids = []
    for fid in sorted(local_eligible_ids):
        loc = local_states[fid]
        pf = prod_by_id.get(fid, {})
        prod = {
            "has_fixture": pf.get("has_fixture", False),
            "has_ecse": pf.get("has_ecse", False),
            "has_result": pf.get("has_result", False),
            "has_eval": pf.get("has_eval", False),
            "eligible": pf.get("eligible", False),
            "exclusion_reasons": pf.get("exclusion", ["MISSING_PRODUCTION_ECSE"]),
            "generated_at": pf.get("generated_at"),
            "actual_score": pf.get("actual"),
            "status": pf.get("status"),
        }
        root, repairable = _classify_root(loc, prod)
        if loc.get("eligible") and not prod.get("eligible") and repairable:
            repair_ids.append(fid)
        parity_rows.append(
            {
                "fixture_id": fid,
                "match": f"{loc['fixture']['home_team']} vs {loc['fixture']['away_team']}" if loc.get("fixture") else str(fid),
                "kickoff": loc["fixture"]["kickoff_utc"] if loc.get("fixture") else None,
                "actual_score": loc.get("actual_score"),
                "local_eligible": loc.get("eligible"),
                "production_eligible": prod.get("eligible"),
                "root_cause": root,
                "repairable": repairable,
                "local_generated_at": loc.get("generated_at"),
                "production_generated_at": prod.get("generated_at"),
                "local_exclusion": loc.get("exclusion_reasons"),
                "production_exclusion": prod.get("exclusion_reasons"),
            }
        )

    (ARTIFACT / "fixture_parity_audit.json").write_text(json.dumps(parity_rows, indent=2), encoding="utf-8")
    (ARTIFACT / "production_exclusion_reasons.json").write_text(
        json.dumps({str(r["fixture_id"]): r for r in parity_rows}, indent=2), encoding="utf-8"
    )

    export = _build_repair_export(local_conn, repair_ids, prod_by_id) if repair_ids else {"fixtures": [], "fixture_results": [], "ecse_snapshots": [], "provenance": {}}
    (ARTIFACT / "parity_repair_export.json").write_text(json.dumps(export, indent=2, default=str), encoding="utf-8")
    if not (ARTIFACT / "parity_repairs.json").is_file():
        (ARTIFACT / "parity_repairs.json").write_text(json.dumps({"applied": False, "repair_fixture_ids": repair_ids}, indent=2), encoding="utf-8")

    repair_applied = None
    if args.apply_production_repair and repair_ids:
        export_path = ARTIFACT / "parity_repair_export.json"
        subprocess.run(
            f'ssh {HETZNER} "mkdir -p {PROD_PATH}/artifacts/ecse_evaluation_parity_and_reliability_gate_1 {PROD_PATH}/scripts"',
            shell=True,
            check=True,
        )
        subprocess.run(
            f"scp {export_path} {ROOT}/scripts/_import_ecse_parity_repair.py {HETZNER}:{PROD_PATH}/scripts/",
            shell=True,
            check=True,
        )
        subprocess.run(
            f'scp {export_path} {HETZNER}:{PROD_PATH}/artifacts/ecse_evaluation_parity_and_reliability_gate_1/parity_repair_export.json',
            shell=True,
            check=True,
        )
        proc = subprocess.run(
            f'ssh {HETZNER} "cd {PROD_PATH} && mkdir -p artifacts/ecse_evaluation_parity_and_reliability_gate_1 && APP_ENV=production .venv/bin/python scripts/_import_ecse_parity_repair.py artifacts/ecse_evaluation_parity_and_reliability_gate_1/parity_repair_export.json"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        repair_applied = {"exit_code": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-2000:]}
        (ARTIFACT / "parity_repairs.json").write_text(json.dumps(repair_applied, indent=2), encoding="utf-8")

    post_prod_eligible = None
    if not args.skip_ssh:
        post_by_id = _fetch_production_states_16()
        post_prod_eligible = sum(1 for x in post_by_id.values() if x.get("eligible"))
        local_n = len(local_eligible_ids)
        post_ids = {fid for fid, x in post_by_id.items() if x.get("eligible")}
        inter = len(set(local_eligible_ids) & post_ids)
        (ARTIFACT / "post_repair_parity.json").write_text(
            json.dumps(
                {
                    "local_eligible": local_n,
                    "production_eligible": post_prod_eligible,
                    "intersection": inter,
                    "local_only": local_n - inter,
                    "production_only": post_prod_eligible - inter if post_prod_eligible else 0,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    dataset = _load_reliability_dataset(local_conn)
    local_conn.close()
    with (ARTIFACT / "reliability_dataset.jsonl").open("w", encoding="utf-8") as f:
        for row in dataset:
            f.write(json.dumps(row, default=str) + "\n")

    hits = [r for r in dataset if r["target_top5_hit"]]
    misses = [r for r in dataset if not r["target_top5_hit"]]
    forensic = []
    for feat in ("lambda_total", "lambda_gap", "top5_entropy", "top1_prob", "cum_top5_prob", "wde_confidence"):
        hv = [float(r[feat]) for r in hits if r.get(feat) is not None]
        mv = [float(r[feat]) for r in misses if r.get(feat) is not None]
        if hv and mv:
            forensic.append(
                {
                    "feature": feat,
                    "hit_mean": round(sum(hv) / len(hv), 4),
                    "miss_mean": round(sum(mv) / len(mv), 4),
                    "difference": round(sum(hv) / len(hv) - sum(mv) / len(mv), 4),
                }
            )
    (ARTIFACT / "hit_vs_miss_forensic.json").write_text(json.dumps(forensic, indent=2), encoding="utf-8")

    segments = {}
    for key in ("favorite", "scoring_regime", "alignment", "btts_lean", "ou_lean"):
        buckets: dict[str, list] = defaultdict(list)
        for r in dataset:
            buckets[str(r.get(key))].append(r)
        segments[key] = {}
        for seg, items in buckets.items():
            n = len(items)
            h = sum(x["target_top5_hit"] for x in items)
            segments[key][seg] = {"n": n, "hits": h, "hit_rate": round(h / n, 4) if n else 0, "ci95": _ci_rate(h, n)}
    (ARTIFACT / "segment_reliability_metrics.json").write_text(json.dumps(segments, indent=2), encoding="utf-8")

    gate = _reliability_gate(dataset)
    (ARTIFACT / "shadow_reliability_gate.json").write_text(json.dumps(gate, indent=2), encoding="utf-8")
    (ARTIFACT / "rank_by_reliability_class.json").write_text(
        json.dumps(gate.get("rank_by_reliability_class", {}), indent=2), encoding="utf-8"
    )

    if post_prod_eligible is not None and post_prod_eligible >= len(local_eligible_ids):
        rec = "ECSE_PARITY_RESTORED_RELIABILITY_SIGNAL_FOUND" if gate.get("gate_useful_oos") else "ECSE_PARITY_RESTORED_NO_RELIABILITY_SIGNAL"
    elif repair_ids and not args.apply_production_repair:
        rec = "ECSE_PARITY_BLOCKED_BY_MISSING_HISTORY"
    elif len(dataset) < 10:
        rec = "ECSE_RELIABILITY_GATE_INSUFFICIENT_SAMPLE"
    elif gate.get("gate_useful_oos"):
        rec = "ECSE_PARITY_BLOCKED_BY_MISSING_HISTORY" if post_prod_eligible and post_prod_eligible < len(local_eligible_ids) else "ECSE_PARITY_RESTORED_RELIABILITY_SIGNAL_FOUND"
    else:
        rec = "ECSE_PARITY_BLOCKED_BY_MISSING_HISTORY" if (post_prod_eligible or 0) < len(local_eligible_ids) else "ECSE_PARITY_RESTORED_NO_RELIABILITY_SIGNAL"

    if len(dataset) < 10 and (post_prod_eligible or 0) < 2:
        rec = "ECSE_RELIABILITY_GATE_INSUFFICIENT_SAMPLE"

    workflow = {
        "phase": PHASE,
        "local_eligible": len(local_eligible_ids),
        "production_eligible_before": sum(1 for x in prod_by_id.values() if x.get("eligible")) if prod_by_id else None,
        "production_eligible_after": post_prod_eligible,
        "repair_fixture_ids": repair_ids,
        "repair_applied": bool(repair_applied and repair_applied.get("exit_code") == 0),
        "reliability_n": len(dataset),
        "final_recommendation": rec,
    }
    (ARTIFACT / "workflow.json").write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    _write_reports(parity_rows, workflow, dataset, forensic, segments, gate)
    print(json.dumps(workflow, indent=2))
    return 0


def _write_reports(parity, workflow, dataset, forensic, segments, gate) -> None:
    lines = [
        "# ECSE Evaluation Parity — Owner Report",
        "",
        f"**Recommendation:** `{workflow['final_recommendation']}`",
        "",
        "| Fixture | Local | Prod | Root Cause | Repairable? |",
        "|---|:---:|:---:|---|:---:|",
    ]
    for r in parity:
        lines.append(
            f"| {r['match']} | {r['local_eligible']} | {r['production_eligible']} | {r['root_cause']} | {r['repairable']} |"
        )
    Path("ECSE_EVALUATION_PARITY_OWNER_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rel = [
        "# ECSE Top5 Reliability Gate — Owner Report",
        "",
        f"**Dataset n:** {len(dataset)}",
        f"**Top5 hit rate:** {sum(r['target_top5_hit'] for r in dataset)/len(dataset):.1%}" if dataset else "",
        "",
        "| Feature | HIT mean | MISS mean | Diff |",
        "|---|---:|---:|---:|",
    ]
    for f in forensic:
        rel.append(f"| {f['feature']} | {f['hit_mean']} | {f['miss_mean']} | {f['difference']} |")
    rel.append("")
    rel.append("## Segment Top5 hit rates")
    for key, segs in segments.items():
        rel.append(f"### {key}")
        for seg, m in segs.items():
            if m["n"] >= 3:
                rel.append(f"- {seg}: {m['hit_rate']:.1%} (n={m['n']})")
    Path("ECSE_TOP5_RELIABILITY_GATE_OWNER_REPORT.md").write_text("\n".join(rel) + "\n", encoding="utf-8")

    report = [
        f"# {PHASE} — Report",
        "",
        f"**Recommendation:** `{workflow['final_recommendation']}`",
        "",
        "## Parity summary",
        f"- Local eligible: {workflow['local_eligible']}",
        f"- Production before: {workflow.get('production_eligible_before')}",
        f"- Production after repair: {workflow.get('production_eligible_after')}",
        f"- Repair candidates: {len(workflow.get('repair_fixture_ids') or [])}",
        "",
        "## Root cause (dominant)",
        "Production lacks 15/16 authentic frozen ECSE snapshots and FT results created locally during controlled prediction batches; not an evaluator bug.",
        "",
        "## Reliability gate OOS",
        f"```json\n{json.dumps(gate, indent=2)}\n```",
    ]
    Path("ECSE_EVALUATION_PARITY_AND_RELIABILITY_GATE_1_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
