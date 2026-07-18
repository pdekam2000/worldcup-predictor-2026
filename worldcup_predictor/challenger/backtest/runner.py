"""Backtest runner for GBGM challengers vs baselines (leakage-safe)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.challenger.backtest.metrics import (
    accuracy,
    bootstrap_ci,
    brier_binary,
    log_loss_binary,
    multiclass_brier,
    multiclass_logloss,
    topk_hit,
)
from worldcup_predictor.challenger.backtest.splits import chronological_split
from worldcup_predictor.challenger.constants import FROZEN_CANONICAL, RECONSTRUCTED_RESEARCH_ONLY
from worldcup_predictor.challenger.models.gbgm import GBGMChallenger, available_backends, goals_to_markets
from worldcup_predictor.challenger.snapshot_reader import build_prematch_feature_snapshot


def _result_1x2(hg: int, ag: int) -> str:
    if hg > ag:
        return "home"
    if hg < ag:
        return "away"
    return "draw"


def build_dataset(conn, competition_keys: list[str], *, include_market: bool = False) -> dict[str, Any]:
    placeholders = ",".join("?" for _ in competition_keys)
    rows = conn.execute(
        f"""
        SELECT f.fixture_id, f.home_team_id, f.away_team_id, f.home_team, f.away_team, f.competition_key,
               f.kickoff_utc, r.home_goals, r.away_goals, f.status
        FROM fixtures f
        JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.is_placeholder=0 AND f.status IN ('FT','AET','PEN')
          AND r.home_goals IS NOT NULL AND r.away_goals IS NOT NULL
          AND f.competition_key IN ({placeholders})
        ORDER BY f.kickoff_utc ASC
        """,
        competition_keys,
    ).fetchall()
    dataset = []
    blocked = 0
    for r in rows:
        snap = build_prematch_feature_snapshot(
            conn,
            int(r["fixture_id"]),
            prediction_time=datetime.fromisoformat(str(r["kickoff_utc"]).replace("Z", "+00:00")[:19]).replace(tzinfo=timezone.utc)
            if r["kickoff_utc"]
            else None,
            include_market=include_market,
        )
        if snap.get("status") != "OK":
            blocked += 1
            continue
        feats = snap["features"]
        dataset.append(
            {
                "fixture_id": int(r["fixture_id"]),
                "kickoff_utc": r["kickoff_utc"],
                "competition_key": r["competition_key"],
                "home_goals": int(r["home_goals"]),
                "away_goals": int(r["away_goals"]),
                "actual_1x2": _result_1x2(int(r["home_goals"]), int(r["away_goals"])),
                "actual_btts": 1 if int(r["home_goals"]) >= 1 and int(r["away_goals"]) >= 1 else 0,
                "actual_over25": 1 if int(r["home_goals"]) + int(r["away_goals"]) >= 3 else 0,
                "actual_score": f"{int(r['home_goals'])}-{int(r['away_goals'])}",
                "features": feats,
                "feature_snapshot_hash": snap["feature_snapshot_hash"],
                "source_label": RECONSTRUCTED_RESEARCH_ONLY,
            }
        )
    raw = json.dumps(
        {"n": len(dataset), "blocked": blocked, "comps": competition_keys, "market": include_market},
        sort_keys=True,
    )
    manifest = {
        "dataset_version": "challenger-bt-v1",
        "creation_timestamp": datetime.now(timezone.utc).isoformat(),
        "competitions": competition_keys,
        "fixture_count": len(dataset),
        "blocked_snapshots": blocked,
        "include_market": include_market,
        "hash": hashlib.sha256(raw.encode()).hexdigest(),
        "leakage_checks": {
            "time_cutoff_kickoff": True,
            "target_fixture_excluded_from_form": True,
            "forbidden_postmatch_fields": True,
        },
        "note": "Canonical freezes not used as Challenger training labels; targets are FT scores only after kickoff.",
    }
    return {"manifest": manifest, "rows": dataset}


def _league_avg_pred(train_rows: list[dict], row: dict) -> dict[str, Any]:
    comp = row["competition_key"]
    same = [r for r in train_rows if r["competition_key"] == comp]
    if not same:
        same = train_rows
    ah = sum(r["home_goals"] for r in same) / len(same)
    aa = sum(r["away_goals"] for r in same) / len(same)
    return goals_to_markets(ah, aa)


def _eval_predictions(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    y1 = [r["actual_1x2"] for r in rows]
    p1 = [p["decision_1x2"] for p in preds]
    probs = [p["hda"] for p in preds]
    btts_y = [r["actual_btts"] for r in rows]
    btts_p = [p["btts_yes"] for p in preds]
    ou_y = [r["actual_over25"] for r in rows]
    ou_p = [p["ou25_over"] for p in preds]
    scores = [r["actual_score"] for r in rows]
    top5 = [[t["score"] for t in (p.get("top5") or [])] for p in preds]
    top10 = [[t["score"] for t in (p.get("top10") or [])] for p in preds]
    return {
        "n": len(rows),
        "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
        "acc_1x2": accuracy(y1, p1),
        "brier_1x2": multiclass_brier(y1, probs),
        "logloss_1x2": multiclass_logloss(y1, probs),
        "brier_btts": brier_binary(btts_y, btts_p),
        "logloss_btts": log_loss_binary(btts_y, btts_p),
        "acc_btts": accuracy(btts_y, [1 if p >= 0.5 else 0 for p in btts_p]),
        "brier_ou25": brier_binary(ou_y, ou_p),
        "logloss_ou25": log_loss_binary(ou_y, ou_p),
        "acc_ou25": accuracy(ou_y, [1 if p >= 0.5 else 0 for p in ou_p]),
        "top1_hit": topk_hit(scores, top5, 1),
        "top3_hit": topk_hit(scores, top5, 3),
        "top5_hit": topk_hit(scores, top5, 5),
        "top10_hit": topk_hit(scores, top10, 10),
        "bootstrap_acc_1x2": bootstrap_ci([1.0 if a == b else 0.0 for a, b in zip(y1, p1)]),
    }


def run_gbgm_backtest(conn, competition_keys: list[str]) -> dict[str, Any]:
    backends = available_backends()
    # Prefer lightgbm + sklearn_hist
    backends = [b for b in backends if b in {"lightgbm", "sklearn_hist", "xgboost", "catboost"}]
    results: dict[str, Any] = {"backends_available": backends, "variants": {}}

    for include_market, variant in ((False, "NM"), (True, "MC")):
        ds = build_dataset(conn, competition_keys, include_market=include_market)
        rows = ds["rows"]
        if len(rows) < 80:
            results["variants"][variant] = {"ok": False, "reason": "insufficient_rows", "n": len(rows), "manifest": ds["manifest"]}
            continue
        split = chronological_split(rows)
        by_id = {r["fixture_id"]: r for r in rows}
        train = [by_id[i] for i in split.train_ids if i in by_id]
        val = [by_id[i] for i in split.validation_ids if i in by_id]
        hold = [by_id[i] for i in split.holdout_ids if i in by_id]

        # baselines on holdout
        league_preds = [_league_avg_pred(train, r) for r in hold]
        baseline_metrics = _eval_predictions(hold, league_preds)

        backend_metrics = {}
        best_backend = None
        best_ll = 1e9
        for backend in backends:
            try:
                model = GBGMChallenger(variant=variant, backend=backend)
                model.fit(
                    [r["features"] for r in train],
                    [r["home_goals"] for r in train],
                    [r["away_goals"] for r in train],
                    sample_meta={"split": "train", "manifest_hash": ds["manifest"]["hash"]},
                )
                val_preds = [model.predict(r["features"]) for r in val]
                val_m = _eval_predictions(val, val_preds)
                hold_preds = [model.predict(r["features"]) for r in hold]
                hold_m = _eval_predictions(hold, hold_preds)
                backend_metrics[backend] = {
                    "validation": val_m,
                    "holdout": hold_m,
                    "model_id": model.model_id,
                    "model_version": model.model_version,
                    "metadata": model.serialize_metadata(),
                }
                ll = val_m.get("logloss_1x2")
                if ll is not None and ll < best_ll:
                    best_ll = ll
                    best_backend = backend
            except Exception as exc:
                backend_metrics[backend] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:240]}"}
                continue

        results["variants"][variant] = {
            "ok": bool(best_backend),
            "manifest": ds["manifest"],
            "split": {
                "method": split.method,
                "train_n": len(train),
                "validation_n": len(val),
                "holdout_n": len(hold),
                "train_end": split.train_end,
                "validation_end": split.validation_end,
                "holdout_end": split.holdout_end,
            },
            "league_avg_holdout": baseline_metrics,
            "backends": backend_metrics,
            "selected_backend_by_val_logloss": best_backend,
            "canonical_note": {
                "frozen_canonical": FROZEN_CANONICAL,
                "reconstructed_research_only": RECONSTRUCTED_RESEARCH_ONLY,
                "mixing_rule": "Do not mix reconstructed Challenger metrics with true forward freezes without separate reporting",
            },
        }
    return results
