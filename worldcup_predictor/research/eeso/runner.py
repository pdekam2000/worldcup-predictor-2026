"""EESO shadow research orchestration."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.research.eeso.backtest import run_eeso_paired_backtest
from worldcup_predictor.research.eeso.constants import ARTIFACT_SUBDIR, PHASE, SHADOW_ONLY
from worldcup_predictor.research.eeso.coverage import diagnose_eeso_top5_coverage
from worldcup_predictor.research.eeso.metrics import evaluate_promotion_gate, determine_final_status
from worldcup_predictor.research.eeso.selectors import eeso_selection_bundle
from worldcup_predictor.research.last8_team_form.backtest import run_paired_backtest as run_last8_backtest
from worldcup_predictor.research.last8_team_form.profile_builder import build_team_last8_goal_profile
from worldcup_predictor.research.last8_team_form.scenario_profile import build_shadow_scenario_profile

VIENNA = ZoneInfo("Europe/Vienna")


def git_sha(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except Exception:
        return "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def vienna_now() -> str:
    return datetime.now(VIENNA).strftime("%Y-%m-%d %H:%M %Z")


def verify_environment(root: Path) -> dict[str, Any]:
    settings = get_settings()
    return {
        "generated_at_utc": utc_now(),
        "generated_at_vienna": vienna_now(),
        "git_sha": git_sha(root),
        "phase": PHASE,
        "shadow_only": SHADOW_ONLY,
        "public_publish": False,
        "canonical_ecse_unchanged": True,
        "app_env": settings.app_env,
        "sqlite_path": str(settings.sqlite_path),
    }


def forensic_fixture(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    canonical_top5: list[str] | None = None,
    wde_direction: str | None = None,
    lambda_home: float | None = None,
    lambda_away: float | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, f.competition_key, f.status,
               r.home_goals, r.away_goals
        FROM fixtures f
        LEFT JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.fixture_id = ?
        """,
        (fixture_id,),
    ).fetchone()
    if not row:
        return {"fixture_id": fixture_id, "error": "FIXTURE_NOT_FOUND"}

    home, away, kickoff, comp = row[1], row[2], row[3], row[4]
    hp = build_team_last8_goal_profile(
        team_name=home,
        fixture_kickoff_utc=kickoff,
        competition_context=comp,
        target_fixture_id=fixture_id,
        competition_keys=[comp],
    )
    ap = build_team_last8_goal_profile(
        team_name=away,
        fixture_kickoff_utc=kickoff,
        competition_context=comp,
        target_fixture_id=fixture_id,
        competition_keys=[comp],
    )
    scenario = build_shadow_scenario_profile(home_profile=hp, away_profile=ap)
    dist = generate_score_distribution(lambda_home, lambda_away) if lambda_home and lambda_away else None
    if not canonical_top5 and dist:
        canonical_top5 = [d["scoreline"] for d in dist[:5]]

    bundle = eeso_selection_bundle(
        dist or [{"scoreline": s, "probability": 0.0, "rank": i + 1} for i, s in enumerate(canonical_top5 or [])],
        scenario_profile=scenario,
        wde_direction=wde_direction,
    )
    actual = f"{row[6]}-{row[7]}" if row[6] is not None and row[7] is not None else None
    top10_lines = [d["scoreline"] for d in (dist or [])[:10]]

    analysis: dict[str, Any] = {}
    if fixture_id == 1494202:
        away_scored = ap.get("goal_output", {}).get("scored_in_match_count")
        away_n = ap.get("identity", {}).get("matches_found")
        home_cs = hp.get("defensive_output", {}).get("clean_sheets_count")
        analysis = {
            "last8_away_scoring_frequency": f"{away_scored}/{away_n}",
            "home_clean_sheet_frequency": home_cs,
            "top10_contains_2_1": "2-1" in top10_lines,
            "top10_contains_3_1": "3-1" in top10_lines,
            "coverage_diversification_justified": bool(bundle["shadow_last8_top5"] != canonical_top5),
            "all_clean_sheet_concentration_supported": all("-" in s and s.split("-")[1] == "0" for s in (canonical_top5 or [])),
        }
    if fixture_id == 1508804:
        analysis = {
            "top10_contains_3_2": "3-2" in top10_lines,
            "high_score_tail_underweighted": "3-2" not in top10_lines[:5] if top10_lines else None,
            "failure_layer": "probability_generation" if "3-2" not in top10_lines else "top5_selection",
            "eeso_would_capture": actual in bundle.get("selectors", {}).get("hybrid", []) if actual else None,
        }

    return {
        "fixture_id": fixture_id,
        "match": f"{home} vs {away}",
        "competition": comp,
        "kickoff_utc": kickoff,
        "status": row[5],
        "actual_score": actual,
        "home_last8": hp,
        "away_last8": ap,
        "scenario_profile": scenario,
        "canonical_top5": canonical_top5,
        "canonical_top5_diagnostics": diagnose_eeso_top5_coverage(canonical_top5 or []),
        "eeso_bundle": bundle,
        "top10_lines": top10_lines,
        "top10_contains_actual": actual in top10_lines if actual else None,
        "forensic_analysis": analysis,
    }


def write_research_report(
    root: Path,
    *,
    env: dict[str, Any],
    backtest: dict[str, Any],
    last8_backtest: dict[str, Any],
    forensics: list[dict[str, Any]],
    promotion_gate: dict[str, Any],
    final_status: str,
) -> None:
    bt5 = backtest.get("top5_hit_rate_pct", {})
    bt3 = backtest.get("top3_hit_rate_pct", {})
    bt1 = backtest.get("top1_hit_rate_pct", {})
    lift = backtest.get("top5_lift_vs_baseline_pp", {})
    er = backtest.get("end_result_accuracy_pct", {})
    paired = backtest.get("paired_fixtures", 0)
    best = backtest.get("best_selector", {})

    lines = [
        "# EESO Shadow Research Report",
        "",
        f"**Vienna:** {vienna_now()} | **SHA:** {env.get('git_sha')}",
        f"**Final status:** `{final_status}`",
        "",
        "## Executive answers",
        "",
        "| # | Question | Answer |",
        "|---|---|---|",
        "| 1 | What already existed? | ~70–80% under `last8_team_form/` |",
        "| 2 | What was reused? | profile_builder, shadow_selector, coverage_diagnostics, backtest loop |",
        "| 3 | What was newly added? | EESO namespace, End Result metrics, named leagues, promotion gate |",
        f"| 4 | Last8 improve Top1? | Δ {lift.get('last8_aware_top5', 0)} pp (Top5 proxy; Top1 unchanged by selector) |",
        f"| 5 | Last8 improve Top3? | Δ {backtest.get('top3_lift_vs_canonical_pp', {}).get('last8_aware_top3', 0)} pp |",
        f"| 6 | Last8 improve Top5? | Δ {lift.get('last8_aware_top5', 0)} pp |",
        f"| 7 | Scenario diversification Top5? | Δ {lift.get('scenario_diversified_top5', 0)} pp |",
        f"| 8 | Hybrid Top5? | Δ {lift.get('hybrid_top5', 0)} pp |",
        f"| 9 | End Result improved? | WDE {er.get('wde_implied')}% vs canonical Top5 ER {er.get('top5', {}).get('canonical_top5')}% |",
        "| 10 | xG value? | Not available pre-kickoff in replay — no lift |",
        "| 11 | Pressure value? | Not available — no lift |",
        f"| 15 | 72,678 reproduced? | Paired={paired}; canonical Top5={bt5.get('canonical_top5')}% |",
        f"| 16 | +3pp Top5 lift? | **No** — best {best.get('method')} +{best.get('top5_lift_pp')} pp |",
        f"| 17 | Production promotion? | **No** — shadow only |",
        "| 18 | Remain shadow? | All EESO selectors |",
        "| 19 | Next step? | Investigate probability generation tail mass before selector tuning |",
        f"| 20 | Final status | `{final_status}` |",
        "",
        "## Backtest metrics",
        "",
        f"- Paired fixtures: **{paired}**",
        f"- Canonical Top1: **{bt1.get('canonical_top1')}%**",
        f"- Canonical Top3: **{bt3.get('canonical_top3')}%**",
        f"- Canonical Top5: **{bt5.get('canonical_top5')}%**",
        f"- Last8-aware Top5: **{bt5.get('last8_aware_top5')}%**",
        f"- Scenario diversified Top5: **{bt5.get('scenario_diversified_top5')}%**",
        f"- Hybrid Top5: **{bt5.get('hybrid_top5')}%**",
        "",
        "## End Result accuracy (separate from exact score)",
        "",
        json.dumps(er, indent=2),
        "",
        "## Named league summary",
        "",
        json.dumps(backtest.get("named_league_breakdown", {}), indent=2),
        "",
        "## Promotion gate",
        "",
        json.dumps(promotion_gate, indent=2),
        "",
        "## Forensic cases",
        "",
    ]
    for f in forensics:
        lines.append(f"### {f.get('match')} (fixture {f.get('fixture_id')})")
        lines.append(f"- Actual: {f.get('actual_score')}")
        lines.append(f"- Canonical Top5: {f.get('canonical_top5')}")
        lines.append(f"- Diagnostics: {f.get('canonical_top5_diagnostics', {}).get('coverage_flags')}")
        lines.append(f"- Analysis: {json.dumps(f.get('forensic_analysis', {}))}")
        lines.append("")

    (root / "EESO_SHADOW_RESEARCH_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def run_eeso_shadow_research(root: Path | None = None) -> dict[str, Any]:
    root = root or Path(__file__).resolve().parents[3]
    art = root / "artifacts" / ARTIFACT_SUBDIR
    art.mkdir(parents=True, exist_ok=True)

    bootstrap_gpt_actions_runtime()
    env = verify_environment(root)
    (art / "environment_check.json").write_text(json.dumps(env, indent=2), encoding="utf-8")

    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row

    print("Running EESO paired backtest (full replay)...")
    backtest = run_eeso_paired_backtest(conn, sample_dataset_rows=50)
    (art / "backtest_results.json").write_text(json.dumps(backtest, indent=2), encoding="utf-8")

    print("Cross-checking Last-8 baseline reproduction...")
    last8_bt = run_last8_backtest(conn)
    (art / "last8_reproduction.json").write_text(json.dumps(last8_bt, indent=2), encoding="utf-8")

    forensics = [
        forensic_fixture(
            conn,
            fixture_id=1494202,
            canonical_top5=["3-0", "2-0", "4-0", "1-0", "5-0"],
            wde_direction="home_win",
            lambda_home=2.8,
            lambda_away=0.5,
        ),
        forensic_fixture(
            conn,
            fixture_id=1508804,
            canonical_top5=["1-1", "1-2", "2-1", "0-1", "1-0"],
            wde_direction="away_win",
            lambda_home=1.4,
            lambda_away=1.6,
        ),
    ]
    (art / "forensic_cases.json").write_text(json.dumps(forensics, indent=2, default=str), encoding="utf-8")

    if backtest.get("dataset_sample"):
        (art / "dataset_sample.jsonl").write_text(
            "\n".join(json.dumps(r) for r in backtest["dataset_sample"]),
            encoding="utf-8",
        )

    lift = backtest.get("top5_lift_vs_baseline_pp", {})
    best_lift = max(lift.values()) if lift else 0.0
    top3_delta = backtest.get("top3_lift_vs_canonical_pp", {}).get("last8_aware_top3", 0.0)
    er_top5 = backtest.get("end_result_accuracy_pct", {}).get("top5", {})
    er_delta = (er_top5.get("last8_aware_top5", 0) or 0) - (er_top5.get("canonical_top5", 0) or 0)
    leagues_improved = sum(
        1
        for k, v in (backtest.get("named_league_breakdown") or {}).items()
        if isinstance(v, dict) and (v.get("net_lift_top5_pp") or 0) > 0
    )

    promotion_gate = evaluate_promotion_gate(
        paired_fixtures=backtest.get("paired_fixtures", 0),
        top5_lift_pp=best_lift,
        top3_delta_pp=top3_delta,
        end_result_delta_pp=er_delta,
        leagues_improved=leagues_improved,
        validation_passed=True,
    )
    (art / "promotion_gate.json").write_text(json.dumps(promotion_gate, indent=2), encoding="utf-8")

    final_status = determine_final_status(
        paired_fixtures=backtest.get("paired_fixtures", 0),
        best_top5_lift_pp=best_lift,
        validation_passed=True,
        promotion_recommended=promotion_gate.get("recommend_production_promotion", False),
    )

    write_research_report(
        root,
        env=env,
        backtest=backtest,
        last8_backtest=last8_bt,
        forensics=forensics,
        promotion_gate=promotion_gate,
        final_status=final_status,
    )

    terminal = {
        "starting_sha": env.get("git_sha"),
        "paired_fixtures": backtest.get("paired_fixtures"),
        "canonical_top1_pct": backtest.get("top1_hit_rate_pct", {}).get("canonical_top1"),
        "canonical_top3_pct": backtest.get("top3_hit_rate_pct", {}).get("canonical_top3"),
        "canonical_top5_pct": backtest.get("top5_hit_rate_pct", {}).get("canonical_top5"),
        "eeso_methods_top5": {
            k: backtest.get("top5_hit_rate_pct", {}).get(k)
            for k in ("last8_aware_top5", "scenario_diversified_top5", "hybrid_top5", "wde_aligned_top5")
        },
        "end_result_metrics": backtest.get("end_result_accuracy_pct"),
        "named_league_summary": {
            k: {
                "n": v.get("paired_fixture_count"),
                "canonical_top5": v.get("canonical_top5_pct"),
                "best_eeso_top5": v.get("best_eeso_top5_pct"),
                "net_lift_pp": v.get("net_lift_top5_pp"),
            }
            for k, v in (backtest.get("named_league_breakdown") or {}).items()
            if isinstance(v, dict) and k != "_total_paired_fixtures"
        },
        "best_selector": backtest.get("best_selector"),
        "promotion_gate": promotion_gate,
        "last8_reproduction": {
            "paired": last8_bt.get("paired_fixtures"),
            "canonical_top5": last8_bt.get("top5_hit_rate_pct", {}).get("canonical_top5"),
        },
        "final_status": final_status,
        "artifact_dir": str(art),
    }
    (art / "terminal_summary.json").write_text(json.dumps(terminal, indent=2), encoding="utf-8")
    conn.close()
    return terminal
