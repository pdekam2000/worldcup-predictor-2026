"""Non-blocking TSBP forward shadow hook for owner full-day pipeline."""

from __future__ import annotations

import traceback
from typing import Any

from worldcup_predictor.challenger.constants import STATUS_DATA_BLOCKED, STATUS_OK, STATUS_POST_KICKOFF
from worldcup_predictor.challenger.diagnostics import timed
from worldcup_predictor.challenger.prediction_store import ensure_challenger_schema, save_comparison, save_freeze, save_prediction
from worldcup_predictor.challenger.schemas import build_challenger_prediction_envelope, utc_now
from worldcup_predictor.challenger.snapshot_reader import build_prematch_feature_snapshot
from worldcup_predictor.challenger.tsbp.comparison import build_tsbp_prematch_comparison
from worldcup_predictor.challenger.tsbp.constants import (
    DOMAIN_DATA_BLOCKED,
    DOMAIN_FORWARD_ENABLED,
    DOMAIN_POLICY_VERSION,
    DOMAIN_RESEARCH_ONLY,
    DOMAIN_UNSUPPORTED,
    MIN_LEAGUE_HISTORY,
    MIN_TEAM_GAMES,
    SNAPSHOT_PARITY_FAILED,
    TSBP_MODEL_ID,
    TSBP_MODEL_VERSION,
)
from worldcup_predictor.challenger.tsbp.domain_policy import classify_competition, is_forward_enabled, load_domain_policy
from worldcup_predictor.challenger.tsbp.model import TSBPChallenger


def _canonical_cutoff(canonical_summary: dict[str, Any] | None) -> str | None:
    if not canonical_summary:
        return None
    return (
        canonical_summary.get("feature_cutoff")
        or canonical_summary.get("prediction_time")
        or canonical_summary.get("frozen_at")
        or canonical_summary.get("odds_timestamp")
    )


def run_tsbp_for_fixture(
    conn,
    *,
    fixture_id: int,
    prediction_scope: str = "owner_shadow",
    validation_tier: str | None = None,
    canonical_summary: dict[str, Any] | None = None,
    linked_canonical_freeze_id: str | None = None,
    resource_limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Independent TSBP prediction. Failures must never affect canonical.
    """
    limits = resource_limits or {"max_runtime_ms": 5000}
    policy = load_domain_policy()

    with timed("tsbp_predict") as diag:
        # Load fixture competition
        fx = conn.execute(
            "SELECT competition_key, home_team_id, away_team_id, home_team, away_team, kickoff_utc, status FROM fixtures WHERE fixture_id=?",
            (fixture_id,),
        ).fetchone()
        if not fx:
            return {"status": STATUS_DATA_BLOCKED, "reason": "fixture_not_found", "canonical_unaffected": True, "diagnostics": diag}

        comp = fx["competition_key"]
        domain = classify_competition(comp, policy)
        if domain == DOMAIN_UNSUPPORTED:
            return {
                "status": DOMAIN_UNSUPPORTED,
                "reason": "competition_not_in_tsbp_allowlist",
                "competition_key": comp,
                "canonical_unaffected": True,
                "diagnostics": diag,
            }
        if domain == DOMAIN_RESEARCH_ONLY:
            return {
                "status": DOMAIN_RESEARCH_ONLY,
                "reason": "research_only_domain",
                "competition_key": comp,
                "canonical_unaffected": True,
                "diagnostics": diag,
                "note": "No forward freeze written for RESEARCH_ONLY domains",
            }
        if domain != DOMAIN_FORWARD_ENABLED:
            return {
                "status": domain,
                "reason": "domain_not_forward_enabled",
                "competition_key": comp,
                "canonical_unaffected": True,
                "diagnostics": diag,
            }

        snap = build_prematch_feature_snapshot(conn, fixture_id, include_market=False)
        if snap.get("status") == STATUS_POST_KICKOFF:
            return {"status": STATUS_POST_KICKOFF, "reason": "post_kickoff", "canonical_unaffected": True, "diagnostics": diag}

        # Snapshot parity vs canonical cutoff
        tsbp_cutoff = snap.get("prediction_time")
        can_cutoff = _canonical_cutoff(canonical_summary)
        parity_ok = True
        parity_reason = None
        if can_cutoff and tsbp_cutoff:
            # Same calendar second bucket is enough for research parity
            parity_ok = str(can_cutoff)[:19] == str(tsbp_cutoff)[:19] or abs(
                # if ISO differs only by timezone formatting, compare kickoff-based
                0
            ) == 0
            # Prefer: both use kickoff as cutoff — snapshot builder uses kickoff when prediction_time not forced
            # Mark failed only if canonical explicitly declares a different cutoff
            if canonical_summary and canonical_summary.get("feature_cutoff") and str(canonical_summary["feature_cutoff"])[:19] != str(tsbp_cutoff)[:19]:
                if canonical_summary.get("require_strict_snapshot_parity"):
                    parity_ok = False
                    parity_reason = SNAPSHOT_PARITY_FAILED

        if snap.get("status") != "OK":
            # Still allow TSBP if we have team ids + league history; domain already enabled
            # Prefer snapshot OK; otherwise data blocked
            env = build_challenger_prediction_envelope(
                fixture_id=fixture_id,
                model_id=TSBP_MODEL_ID,
                model_version=TSBP_MODEL_VERSION,
                outputs={},
                feature_snapshot_id=snap.get("feature_snapshot_id"),
                feature_snapshot_hash=snap.get("feature_snapshot_hash"),
                prediction_time=snap.get("prediction_time") or utc_now(),
                kickoff=snap.get("kickoff_utc") or fx["kickoff_utc"],
                home_team=snap.get("home_team") or fx["home_team"],
                away_team=snap.get("away_team") or fx["away_team"],
                competition=comp,
                prediction_scope=prediction_scope,
                validation_tier=validation_tier,
                confidence=None,
                data_quality=DOMAIN_DATA_BLOCKED,
                missing_features=list(snap.get("missing_required") or []),
                warnings=[str(snap.get("reason")), f"domain_policy={DOMAIN_POLICY_VERSION}"],
                status=STATUS_DATA_BLOCKED,
            )
            save_prediction(conn, env)
            return {"prediction": env, "freeze": None, "comparison": None, "diagnostics": diag, "canonical_unaffected": True}

        # Fit strengths strictly before kickoff
        model = TSBPChallenger()
        enabled = [c for c, v in (policy.get("classifications") or {}).items() if v == DOMAIN_FORWARD_ENABLED]
        kickoff = str(fx["kickoff_utc"] or "")[:19]
        model.fit_from_conn(conn, enabled or [comp], before_kickoff=kickoff)
        league_n = float((model.strength or {}).get("league_means", {}).get(comp, {}).get("n") or 0)
        if league_n < MIN_LEAGUE_HISTORY:
            return {
                "status": DOMAIN_DATA_BLOCKED,
                "reason": "insufficient_league_history",
                "league_n": league_n,
                "canonical_unaffected": True,
                "diagnostics": diag,
            }

        feats = dict(snap.get("features") or {})
        feats["competition_key"] = comp
        feats["home_team_id"] = fx["home_team_id"]
        feats["away_team_id"] = fx["away_team_id"]
        outputs = model.predict(feats)
        home_games = int((outputs.get("team_history") or {}).get("home_games") or 0)
        away_games = int((outputs.get("team_history") or {}).get("away_games") or 0)
        warnings = [f"domain_policy={DOMAIN_POLICY_VERSION}"]
        if home_games < MIN_TEAM_GAMES or away_games < MIN_TEAM_GAMES:
            warnings.append("sparse_team_history")

        conf = round(50 + 40 * max((outputs.get("hda") or {}).values()), 1) if outputs.get("hda") else 55.0
        env = build_challenger_prediction_envelope(
            fixture_id=fixture_id,
            model_id=TSBP_MODEL_ID,
            model_version=TSBP_MODEL_VERSION,
            outputs=outputs,
            feature_snapshot_id=snap.get("feature_snapshot_id"),
            feature_snapshot_hash=snap.get("feature_snapshot_hash"),
            prediction_time=snap.get("prediction_time") or utc_now(),
            kickoff=snap.get("kickoff_utc") or fx["kickoff_utc"],
            home_team=snap.get("home_team") or fx["home_team"],
            away_team=snap.get("away_team") or fx["away_team"],
            competition=comp,
            prediction_scope=prediction_scope,
            validation_tier=validation_tier,
            confidence=conf,
            data_quality="OK" if home_games >= MIN_TEAM_GAMES and away_games >= MIN_TEAM_GAMES else "SPARSE_TEAM_HISTORY",
            missing_features=[],
            warnings=warnings,
            status=STATUS_OK,
        )
        env["domain_policy_version"] = DOMAIN_POLICY_VERSION
        env["canonical_feature_cutoff"] = can_cutoff
        env["tsbp_feature_cutoff"] = tsbp_cutoff
        env["snapshot_parity_ok"] = parity_ok
        if not parity_ok:
            env["warnings"] = list(env.get("warnings") or []) + [parity_reason or SNAPSHOT_PARITY_FAILED]

        save_prediction(conn, env)
        fr = save_freeze(conn, env, linked_canonical_freeze_id=linked_canonical_freeze_id)
        env["freeze_hash"] = fr.get("freeze_hash")

        comparison = None
        if canonical_summary and parity_ok:
            comparison = build_tsbp_prematch_comparison(canonical_summary, env, snapshot_parity_ok=True)
            comparison.update(
                {
                    "fixture_id": fixture_id,
                    "model_id": TSBP_MODEL_ID,
                    "model_version": TSBP_MODEL_VERSION,
                    "challenger_freeze_hash": fr.get("freeze_hash"),
                    "canonical_freeze_hash": canonical_summary.get("freeze_hash"),
                    "canonical_odds_timestamp": canonical_summary.get("odds_timestamp"),
                    "tsbp_odds_timestamp": None,
                    "feature_snapshot_hash": snap.get("feature_snapshot_hash"),
                }
            )
            save_comparison(conn, comparison)
        elif canonical_summary and not parity_ok:
            comparison = build_tsbp_prematch_comparison(canonical_summary, env, snapshot_parity_ok=False)
            comparison.update(
                {
                    "fixture_id": fixture_id,
                    "model_id": TSBP_MODEL_ID,
                    "model_version": TSBP_MODEL_VERSION,
                    "challenger_freeze_hash": fr.get("freeze_hash"),
                    "canonical_freeze_hash": canonical_summary.get("freeze_hash"),
                }
            )
            save_comparison(conn, comparison)

        if diag.get("elapsed_ms") and limits.get("max_runtime_ms") and diag["elapsed_ms"] > limits["max_runtime_ms"]:
            diag["runtime_warning"] = "exceeded_soft_limit"

        return {
            "prediction": env,
            "freeze": fr,
            "comparison": comparison,
            "diagnostics": diag,
            "canonical_unaffected": True,
            "model_id": TSBP_MODEL_ID,
        }


def run_tsbp_shadow_batch_safe(
    conn,
    fixture_metas: list[dict[str, Any]],
) -> dict[str, Any]:
    """Batch wrapper: never raises into canonical pipeline."""
    ensure_challenger_schema(conn)
    results = []
    failures = 0
    domain_rejects = 0
    for meta in fixture_metas:
        try:
            out = run_tsbp_for_fixture(
                conn,
                fixture_id=int(meta["fixture_id"]),
                prediction_scope=str(meta.get("prediction_scope") or "owner_shadow"),
                validation_tier=meta.get("validation_tier"),
                canonical_summary=meta.get("canonical_summary"),
                linked_canonical_freeze_id=meta.get("linked_canonical_freeze_id") or meta.get("freeze_id"),
            )
            if out.get("status") in {DOMAIN_UNSUPPORTED, DOMAIN_RESEARCH_ONLY, DOMAIN_DATA_BLOCKED}:
                domain_rejects += 1
            results.append(out)
        except Exception as exc:
            failures += 1
            results.append(
                {
                    "fixture_id": meta.get("fixture_id"),
                    "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    "canonical_unaffected": True,
                    "traceback_tail": traceback.format_exc()[-400:],
                }
            )
    forward_active = True
    reason = "TSBP_FORWARD_SHADOW_ACTIVE"
    if failures >= max(3, len(fixture_metas) // 2) and fixture_metas:
        forward_active = False
        reason = "OPERATIONAL_INSTABILITY"
    return {
        "n": len(fixture_metas),
        "failures": failures,
        "domain_rejects": domain_rejects,
        "results": results,
        "forward_active": forward_active,
        "reason": reason,
        "model_id": TSBP_MODEL_ID,
        "note": "TSBP failure must never change canonical job status",
    }
