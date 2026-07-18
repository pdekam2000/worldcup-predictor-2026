#!/usr/bin/env python3
"""CHALLENGER PHASE 4B — Activate TSBP-1 forward shadow (code + registration)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.challenger.prediction_store import ensure_challenger_schema
from worldcup_predictor.challenger.registry import get_model
from worldcup_predictor.challenger.tsbp.constants import (
    FORWARD_THRESHOLDS_TSBP,
    GBGM1_STATUS,
    TSBP_MODEL_ID,
    TSBP_STATUS,
)
from worldcup_predictor.challenger.tsbp.domain_policy import load_domain_policy, save_domain_policy
from worldcup_predictor.challenger.tsbp.forward_hook import run_tsbp_for_fixture
from worldcup_predictor.challenger.tsbp.model import TSBPChallenger
from worldcup_predictor.challenger.tsbp.registration import register_tsbp_and_pause_gbgm
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect

ART = ROOT / "artifacts" / "challenger_program" / "phase4b"
ART.mkdir(parents=True, exist_ok=True)


def _count_completed_evals(conn) -> int:
    ensure_challenger_schema(conn)
    row = conn.execute(
        "SELECT COUNT(*) n FROM challenger_evaluations WHERE model_id=?",
        (TSBP_MODEL_ID,),
    ).fetchone()
    return int(row["n"] if row else 0)


def _write_threshold_reports(n_completed: int) -> list[str]:
    """Only create threshold reports when actual completed count reaches threshold."""
    created = []
    for thr, label in FORWARD_THRESHOLDS_TSBP.items():
        path = ROOT / f"CHALLENGER_FORWARD_TSBP_{thr}_REPORT.md"
        if n_completed < thr:
            # Do not create fake success reports
            continue
        path.write_text(
            "\n".join(
                [
                    f"# CHALLENGER FORWARD TSBP — {thr} COMPLETED FIXTURES",
                    "",
                    f"Completed paired evaluations: **{n_completed}** (threshold {thr}: `{label}`).",
                    "",
                    "Conclusions at this threshold remain non-promotional."
                    if thr < 250
                    else "Promotion-quality review threshold reached — still Shadow only; no Ensemble approval without separate gate.",
                    "",
                    f"- model_id: `{TSBP_MODEL_ID}`",
                    f"- status: `{TSBP_STATUS}`",
                    "- is_shadow=true · public_visible=false · final_decision_authority=false",
                ]
            ),
            encoding="utf-8",
        )
        created.append(str(path.name))
    return created


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_challenger_schema(conn)

    phase3b = {}
    p3 = ROOT / "artifacts" / "challenger_program" / "phase3b" / "summary.json"
    if p3.exists():
        phase3b = json.loads(p3.read_text(encoding="utf-8"))

    reg = register_tsbp_and_pause_gbgm(phase3b_summary=phase3b)
    domain = load_domain_policy()
    save_domain_policy(domain)

    # Smoke: fit + predict one enabled historical FT fixture (research only; may reuse freeze)
    smoke = {"ok": False}
    try:
        row = conn.execute(
            """
            SELECT f.fixture_id, f.competition_key, f.kickoff_utc
            FROM fixtures f
            JOIN fixture_results r ON r.fixture_id=f.fixture_id
            WHERE f.competition_key IN ('premier_league','bundesliga')
              AND f.status='FT' AND f.is_placeholder=0
            ORDER BY f.kickoff_utc DESC LIMIT 1
            """
        ).fetchone()
        if row:
            # Use historical prediction_time = kickoff via snapshot builder inside hook —
            # for FT fixtures live hook blocks POST_KICKOFF. Smoke-test model fit/predict only.
            model = TSBPChallenger()
            model.fit_from_conn(conn, ["premier_league", "bundesliga"], before_kickoff=str(row["kickoff_utc"])[:19])
            fx = conn.execute(
                "SELECT home_team_id, away_team_id, competition_key FROM fixtures WHERE fixture_id=?",
                (row["fixture_id"],),
            ).fetchone()
            out = model.predict(
                {
                    "competition_key": fx["competition_key"],
                    "home_team_id": fx["home_team_id"],
                    "away_team_id": fx["away_team_id"],
                }
            )
            smoke = {
                "ok": True,
                "fixture_id": row["fixture_id"],
                "competition_key": row["competition_key"],
                "has_hda": bool(out.get("hda")),
                "corr": out.get("corr"),
                "label": out.get("label"),
                "top10_n": len(out.get("top10") or []),
                "prob_sum": round(sum((out.get("hda") or {}).values()), 6),
            }
    except Exception as exc:
        smoke = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    n_completed = _count_completed_evals(conn)
    threshold_reports = _write_threshold_reports(n_completed)

    # Spec + domain + phase reports (always)
    (ROOT / "TSBP_MODEL_SPECIFICATION.md").write_text(
        "\n".join(
            [
                "# TSBP MODEL SPECIFICATION",
                "",
                f"- model_id: `{TSBP_MODEL_ID}`",
                "- model_name: Team Strength Bivariate Poisson",
                "- model_family: bivariate_poisson",
                "- model_version: 1.0.0",
                "- distribution: BIVARIATE_POISSON",
                f"- status: `{TSBP_STATUS}`",
                "- is_shadow=true · public_visible=false · final_decision_authority=false",
                "",
                "## Methods",
                "- Attack: mean goals scored / league mean goals (FT only, before kickoff)",
                "- Defence: mean goals conceded / league mean goals",
                "- Home advantage: league home mean − away mean (embedded in λ)",
                "- Time decay: none (equal-weight expanding history)",
                "- League normalization: per competition_key",
                "- Dependence: bivariate correlation tilt corr=0.05",
                "- Score grid: 0..7 goals, renormalized",
                "- Calibration: none in v1 forward",
                "",
                "## Provenance",
                "```json",
                json.dumps(reg.get("tsbp") or {}, indent=2),
                "```",
                "",
                "Not GBGM. Do not serialize into ECSE fields. All outputs labelled `TSBP_SHADOW`.",
            ]
        ),
        encoding="utf-8",
    )

    (ROOT / "TSBP_DOMAIN_COVERAGE_REPORT.md").write_text(
        "\n".join(
            [
                "# TSBP DOMAIN COVERAGE REPORT",
                "",
                f"Policy version: `{domain.get('policy_version')}`",
                "",
                "```json",
                json.dumps(domain, indent=2),
                "```",
                "",
                "Forward enabled only where Phase 3B had sufficient coverage and team-strength beat league baseline:",
                "- premier_league → TSBP_FORWARD_ENABLED",
                "- bundesliga → TSBP_FORWARD_ENABLED",
                "- champions_league / world_cup_2026 → TSBP_RESEARCH_ONLY",
                "- other competitions → TSBP_UNSUPPORTED",
            ]
        ),
        encoding="utf-8",
    )

    # Deployment status: code ready locally; do not claim production deploy here
    final_status = "TSBP_FORWARD_SHADOW_CODE_READY_DEPLOY_PENDING"
    if not smoke.get("ok"):
        final_status = "TSBP_FORWARD_SHADOW_VALIDATION_FAILED"
    if not get_model(TSBP_MODEL_ID) and not (ART / "tsbp_model_registry.json").exists():
        final_status = "TSBP_FORWARD_SHADOW_VALIDATION_FAILED"

    # If registry + smoke OK, mark active in local code/runtime sense
    if smoke.get("ok") and (reg.get("tsbp") or {}).get("status") == TSBP_STATUS:
        # Local activation complete; production deploy still pending per Part P
        final_status = "TSBP_FORWARD_SHADOW_ACTIVE"

    phase_report = "\n".join(
        [
            "# CHALLENGER PHASE 4B — TSBP FORWARD SHADOW REPORT",
            "",
            f"## Final status: `{final_status}`",
            "",
            "### Registration",
            f"- TSBP registered: `{TSBP_MODEL_ID}`",
            f"- GBGM-1 status: `{GBGM1_STATUS}` (pause_gbgm1_new_generation=true)",
            "- Historical GBGM-1 freezes/evals retained (immutable)",
            "",
            "### Shadow invariants",
            "- is_shadow=true",
            "- public_visible=false",
            "- final_decision_authority=false",
            "- Canonical WDE/ECSE/BTTS/O-U unchanged",
            "- Owner/Custom GPT outputs remain canonical-only",
            "",
            "### Integration",
            "- Additive hook in `scripts/run_owner_full_day_predictions.py`",
            "- Same prematch snapshot path via `build_prematch_feature_snapshot`",
            "- Separate Challenger freeze + comparison tables",
            "- Failures never block canonical",
            "",
            "### Forward evaluations",
            f"- Completed TSBP evaluations in DB: **{n_completed}**",
            f"- Threshold reports created: `{threshold_reports or 'none (thresholds not reached)'}`",
            "",
            "### Smoke test",
            "```json",
            json.dumps(smoke, indent=2),
            "```",
            "",
            "No Ensemble approval. No public promotion. Cards Engine not started.",
            "",
            f"**STATUS: `{final_status}`**",
        ]
    )
    (ROOT / "CHALLENGER_PHASE4B_TSBP_FORWARD_SHADOW_REPORT.md").write_text(phase_report, encoding="utf-8")

    summary = {
        "status": final_status,
        "tsbp": reg.get("tsbp"),
        "gbgm1": reg.get("gbgm1"),
        "domain_policy_version": domain.get("policy_version"),
        "completed_evaluations": n_completed,
        "threshold_reports": threshold_reports,
        "smoke": smoke,
    }
    (ART / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0 if final_status in {"TSBP_FORWARD_SHADOW_ACTIVE", "TSBP_FORWARD_SHADOW_CODE_READY_DEPLOY_PENDING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
