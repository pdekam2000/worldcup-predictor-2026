#!/usr/bin/env python3
"""TSBP Phase 4C — first eligible prematch forward freeze (local or via env DB).

Does NOT retroactively freeze completed matches.
Does NOT modify canonical engines.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.challenger.prediction_store import ensure_challenger_schema
from worldcup_predictor.challenger.tsbp.constants import TSBP_MODEL_ID
from worldcup_predictor.challenger.tsbp.domain_policy import classify_competition
from worldcup_predictor.challenger.tsbp.forward_hook import run_tsbp_for_fixture
from worldcup_predictor.challenger.tsbp.registration import register_tsbp_and_pause_gbgm
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect


def _parse(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_challenger_schema(conn)
    register_tsbp_and_pause_gbgm()

    now = datetime.now(timezone.utc)
    rows = conn.execute(
        """
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status
        FROM fixtures
        WHERE is_placeholder=0
          AND competition_key IN ('premier_league','bundesliga')
          AND status IN ('NS','TBD','SCH')
        ORDER BY kickoff_utc ASC
        LIMIT 50
        """
    ).fetchall()

    chosen = None
    for r in rows:
        ko = _parse(r["kickoff_utc"])
        if ko and ko > now and classify_competition(r["competition_key"]) == "TSBP_FORWARD_ENABLED":
            chosen = dict(r)
            break

    out_dir = ROOT / "artifacts" / "challenger_program" / "phase4c"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not chosen:
        payload = {
            "ok": False,
            "reason": "NO_ELIGIBLE_PREMATCH_PL_BL_FIXTURE",
            "forward_paired_frozen": 0,
            "forward_completed_evaluated": 0,
            "note": "Do not retroactively freeze completed matches",
        }
        (out_dir / "first_forward_freeze.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 0

    # Canonical summary uses kickoff as shared cutoff (parity soft)
    canonical_summary = {
        "freeze_hash": None,
        "feature_cutoff": chosen["kickoff_utc"],
        "prediction_time": chosen["kickoff_utc"],
        "require_strict_snapshot_parity": False,
        "wde_decision": None,
        "btts": None,
        "ou25": None,
        "ecse_top1": None,
    }
    result = run_tsbp_for_fixture(
        conn,
        fixture_id=int(chosen["fixture_id"]),
        prediction_scope="phase4c_first_forward",
        validation_tier="A",
        canonical_summary=canonical_summary,
        linked_canonical_freeze_id=None,
    )
    pred = result.get("prediction") or {}
    outputs = pred.get("output_probabilities") or {}
    freeze = result.get("freeze") or {}

    # Count freezes for TSBP
    n_frozen = conn.execute(
        "SELECT COUNT(*) n FROM challenger_freezes WHERE model_id=?",
        (TSBP_MODEL_ID,),
    ).fetchone()["n"]
    n_eval = conn.execute(
        "SELECT COUNT(*) n FROM challenger_evaluations WHERE model_id=?",
        (TSBP_MODEL_ID,),
    ).fetchone()["n"]

    payload = {
        "ok": bool(freeze.get("freeze_hash") or freeze.get("created") or freeze.get("reused")),
        "fixture_id": chosen["fixture_id"],
        "match": f"{chosen['home_team']} vs {chosen['away_team']}",
        "competition_key": chosen["competition_key"],
        "kickoff_utc": chosen["kickoff_utc"],
        "status": result.get("status") or pred.get("status"),
        "tsbp_freeze_hash": freeze.get("freeze_hash"),
        "tsbp_freeze_reused": freeze.get("reused"),
        "prediction_content_hash": pred.get("prediction_content_hash"),
        "feature_snapshot_hash": pred.get("feature_snapshot_hash"),
        "snapshot_parity_ok": pred.get("snapshot_parity_ok"),
        "domain_policy_version": pred.get("domain_policy_version"),
        "model_version": pred.get("model_version"),
        "required_fields": {
            "expected_home_goals": outputs.get("expected_home_goals"),
            "expected_away_goals": outputs.get("expected_away_goals"),
            "expected_total_goals": outputs.get("expected_total_goals"),
            "covariance_dependence_parameter": outputs.get("covariance_dependence_parameter"),
            "hda": outputs.get("hda"),
            "btts_yes": outputs.get("btts_yes"),
            "ou25_over": outputs.get("ou25_over"),
            "top1": outputs.get("top1_score"),
            "top10_n": len(outputs.get("top10") or []),
            "top3_mass": outputs.get("top3_mass"),
            "top5_mass": outputs.get("top5_mass"),
            "entropy": outputs.get("entropy"),
            "label": outputs.get("label"),
        },
        "forward_paired_frozen": int(n_frozen),
        "forward_completed_evaluated": int(n_eval),
        "public_visible": False,
        "canonical_unaffected": True,
        "diagnostics": result.get("diagnostics"),
    }
    (out_dir / "first_forward_freeze.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
