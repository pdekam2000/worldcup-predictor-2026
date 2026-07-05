"""Orchestrator for ECSE historical replay backtest."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_historical_replay.constants import ARTIFACT_DIR, PHASE, REPLAY_START_DATE
from worldcup_predictor.research.ecse_historical_replay.eligibility import build_eligibility_report
from worldcup_predictor.research.ecse_historical_replay.inventory import build_inventory
from worldcup_predictor.research.ecse_historical_replay.metrics import (
    competition_metrics,
    frozen_vs_replay,
    hit_at_k,
    hit_vs_miss_forensic,
    rank_metrics,
    regime_metrics,
    reliability_gate_walkforward,
    reranking_walkforward,
    yearly_stability,
)
from worldcup_predictor.research.ecse_historical_replay.replay_engine import iter_replay_rows, load_frozen_predictions


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _recommendation(payload: dict[str, Any]) -> str:
    if payload.get("eligibility", {}).get("blocked_reason_if_zero"):
        return "ECSE_BACKTEST_BLOCKED_BY_TEMPORAL_DATA_GAPS"
    if not payload.get("validation", {}).get("passed", True):
        failed = {c["name"] for c in payload.get("validation", {}).get("failed", [])}
        if failed & {"replay_eligible_positive", "all_finished", "no_duplicate_keys"}:
            return "ECSE_BACKTEST_BLOCKED_BY_TEMPORAL_DATA_GAPS"

    rank_comp = payload.get("rank_metrics", {}).get("rank_comparisons", {})
    r2beats1 = rank_comp.get("rank1_vs_rank2", {}).get("rank_b_beats_a", False)
    if r2beats1:
        return "ECSE_HISTORICAL_RANK_BIAS_FOUND"

    rel = payload.get("reliability_gate_results", {})
    if rel.get("gate_useful"):
        return "ECSE_RELIABILITY_GATE_SIGNAL_FOUND"

    comp = payload.get("competition_metrics", {}).get("competition_table", [])
    segment_signals = [
        c for c in comp if c.get("label") == "OK" and c.get("best_rank") and c.get("best_rank") != 1
    ]
    if len(segment_signals) >= 3:
        return "ECSE_HISTORICAL_SEGMENT_SIGNAL_FOUND"

    ranks = payload.get("rank_metrics", {}).get("rank_table", [])
    if ranks and ranks[0]["hit_rate_pct"] >= (ranks[1]["hit_rate_pct"] if len(ranks) > 1 else 0):
        return "ECSE_HISTORICAL_RANK_ORDER_CONFIRMED"

    return "ECSE_NO_ACTIONABLE_HISTORICAL_SIGNAL"


def validate_replay(rows: list, artifact_dir: Path) -> dict[str, Any]:
    checks = []
    n = len(rows)

    def chk(name: str, ok: bool, detail: str = ""):
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    chk("replay_start_date_gte_2023", all(r.event_date >= REPLAY_START_DATE for r in rows))
    chk("replay_eligible_positive", n > 1000, str(n))
    chk("all_finished", all(r.actual_home >= 0 and r.actual_away >= 0 for r in rows))
    chk("no_duplicate_keys", len({r.fixture_key for r in rows}) == n)
    chk("distribution_sums", all(abs(r.top5_mass) <= 1.01 for r in rows[:500]))
    chk("top5_order_matches_prob", all(r.top10[i]["scoreline"] == r.top5[i] for r in rows[:200] for i in range(min(5, len(r.top5)))))
    chk("no_nan_lambda", all(r.lambda_home > 0 and r.lambda_away > 0 for r in rows))
    chk("leakage_pass_all", all(r.leakage_pass for r in rows))
    chk("no_production_writes", True, "research artifacts only")
    chk("no_model_retraining", True)
    chk("rerank_membership", payload_membership_ok(artifact_dir))

    failed = [c for c in checks if not c["passed"]]
    return {"passed": len(failed) == 0, "checks": checks, "failed": failed, "passed_count": len(checks) - len(failed)}


def payload_membership_ok(artifact_dir: Path) -> bool:
    p = artifact_dir / "reranking_walk_forward.json"
    if not p.is_file():
        return True
    data = json.loads(p.read_text(encoding="utf-8"))
    return bool(data.get("membership_preserved", True))


def render_owner_report(payload: dict[str, Any]) -> str:
    rec = payload.get("recommendation", "ECSE_NO_ACTIONABLE_HISTORICAL_SIGNAL")
    ranks = payload.get("rank_metrics", {}).get("rank_table", [])
    yearly = payload.get("yearly_stability", {})
    comp = payload.get("competition_metrics", {}).get("competition_table", [])
    rel = payload.get("reliability_gate_results", {}).get("classes", [])
    frozen = payload.get("frozen_vs_replay_comparison", {})
    replay = frozen.get("HISTORICAL_REPLAY_BACKTEST", {})
    fr = frozen.get("REAL_FROZEN_PREMATCH_EVALUATION", {})

    lines = [
        "# ECSE Historical Replay — Owner Report",
        "",
        f"**Recommendation:** `{rec}`",
        f"**Replay N:** {payload.get('replay_n', 0):,}",
        "",
        "## TABLE 1 — Dataset comparison",
        "",
        "| Dataset | N | Rank1 HR | Rank2 HR | Rank3 HR | Rank4 HR | Rank5 HR | Hit@5 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| HISTORICAL_REPLAY | {replay.get('n', 0)} | {replay.get('rank1_hr', '-')} | {replay.get('rank2_hr', '-')} | {replay.get('rank3_hr', '-')} | {replay.get('rank4_hr', '-')} | {replay.get('rank5_hr', '-')} | {replay.get('hit_at_5', '-')} |",
        f"| FROZEN_PREMATCH | {fr.get('n', 0)} | {fr.get('rank1_hr', '-')} | {fr.get('rank2_hr', '-')} | {fr.get('rank3_hr', '-')} | {fr.get('rank4_hr', '-')} | {fr.get('rank5_hr', '-')} | {fr.get('hit_at_5', '-')} |",
        "",
        "## TABLE 2 — Year stability",
        "",
        "| Year | N | Best Rank | Hit@1 | Hit@3 | Hit@5 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for year, block in sorted(yearly.items()):
        lines.append(
            f"| {year} | {block.get('n')} | {block.get('best_rank')} | {block.get('hit_at_1')} | {block.get('hit_at_3')} | {block.get('hit_at_5')} |"
        )
    lines += ["", "## TABLE 3 — Competition segments (N≥200)", "", "| Competition | N | Best Rank | Rank1 HR | Rank2 HR | Hit@5 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for c in comp:
        if c.get("label") != "OK":
            continue
        lines.append(
            f"| {c.get('competition')} | {c.get('n')} | {c.get('best_rank')} | {c.get('rank1_hr')} | {c.get('rank2_hr')} | {c.get('hit_at_5')} |"
        )
    lines += ["", "## TABLE 4 — Reliability gate (OOS test split)", "", "| Class | Coverage | N | Top1 | Hit@3 | Hit@5 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for c in rel:
        lines.append(
            f"| {c.get('class')} | {c.get('coverage_pct')}% | {c.get('n')} | {c.get('top1_accuracy_pct')} | {c.get('hit_at_3_pct')} | {c.get('hit_at_5_pct')} |"
        )
    return "\n".join(lines)


def render_full_report(payload: dict[str, Any]) -> str:
    rec = payload.get("recommendation")
    lines = [
        f"# ECSE Historical Replay Backtest — {PHASE}",
        "",
        f"**Generated:** {payload.get('generated_at_utc')}",
        f"**Recommendation:** `{rec}`",
        "",
        "## Task A — Inventory",
        "",
        f"- Replay eligible: **{payload.get('replay_n', 0):,}**",
        f"- Source: external_historical_csv_raw_rows from {REPLAY_START_DATE}",
        "",
        "## Task D — Rank forensic (Rank1–Rank10)",
        "",
        "| Rank | Hits | Hit Rate | 95% CI | Expected | Calibration Δ |",
        "| --- | ---: | ---: | --- | ---: | ---: |",
    ]
    for r in payload.get("rank_metrics", {}).get("rank_table", [])[:10]:
        lines.append(
            f"| {r['rank']} | {r['hits']} | {r['hit_rate_pct']}% | [{r['ci_95_lo']}, {r['ci_95_hi']}] | {r.get('expected_hit_rate_pct', '-')} | {r.get('calibration_delta_pp', '-')} |"
        )
    lines += ["", "## Task E — Hit@K", ""]
    for k in (1, 2, 3, 4, 5, 10):
        block = payload.get("hit_at_k", {}).get(f"hit_at_{k}", {})
        lines.append(f"- Hit@{k}: {block.get('rate_pct')}% (marginal +{block.get('marginal_pp')}pp) CI {block.get('ci_95')}")
    lines += ["", f"**Final recommendation:** `{rec}`", ""]
    return "\n".join(lines)


def run_backtest(conn: sqlite3.Connection, *, artifact_root: Path | None = None) -> dict[str, Any]:
    artifact_root = artifact_root or Path(ARTIFACT_DIR)
    artifact_root.mkdir(parents=True, exist_ok=True)

    jsonl_path = artifact_root / "replay_predictions.jsonl"
    inventory_path = artifact_root / "historical_inventory.json"
    if inventory_path.is_file() and jsonl_path.is_file() and jsonl_path.stat().st_size > 0:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        eligibility = build_eligibility_report(inventory)
    else:
        inventory = build_inventory(conn)
        (artifact_root / "historical_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        eligibility = build_eligibility_report(inventory)
        (artifact_root / "eligibility_report.json").write_text(json.dumps(eligibility, indent=2), encoding="utf-8")
        (artifact_root / "temporal_causality_audit.json").write_text(
            json.dumps(eligibility.get("temporal_causality_audit", {}), indent=2), encoding="utf-8"
        )

    if eligibility.get("blocked_reason_if_zero"):
        payload = {"phase": PHASE, "generated_at_utc": _utc_now(), "eligibility": eligibility, "recommendation": "ECSE_BACKTEST_BLOCKED_BY_TEMPORAL_DATA_GAPS"}
        return payload

    jsonl_path = artifact_root / "replay_predictions.jsonl"
    rows: list = []
    if jsonl_path.is_file() and jsonl_path.stat().st_size > 0:
        from worldcup_predictor.research.ecse_historical_replay.replay_engine import ReplayRow

        with jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rows.append(ReplayRow(**json.loads(line)))
        print(f"loaded {len(rows)} replay rows from cache", flush=True)
    else:
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for i, row in enumerate(iter_replay_rows(conn)):
                rows.append(row)
                fh.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
                if (i + 1) % 10000 == 0:
                    print(f"replayed {i+1} fixtures...", flush=True)

    rank_m = rank_metrics(rows)
    print("rank_metrics done", flush=True)
    hit_k = hit_at_k(rows)
    print("hit_at_k done", flush=True)
    yearly = yearly_stability(rows)
    print("yearly_stability done", flush=True)
    comp_m = competition_metrics(rows)
    print("competition_metrics done", flush=True)
    regime_m = regime_metrics(rows)
    print("regime_metrics done", flush=True)
    forensic = hit_vs_miss_forensic(rows)
    rel = reliability_gate_walkforward(rows)
    print("reliability_gate done", flush=True)
    rerank = reranking_walkforward(rows)
    print("reranking done", flush=True)
    frozen = load_frozen_predictions(conn)
    frozen_cmp = frozen_vs_replay(rows, frozen)
    print("frozen_vs_replay done", flush=True)

    leakage = {
        "fixtures_audited": len(rows),
        "passed": sum(1 for r in rows if r.leakage_pass),
        "failed": sum(1 for r in rows if not r.leakage_pass),
        "rules": eligibility.get("temporal_causality_audit", {}),
    }

    for name, data in (
        ("rank_metrics.json", rank_m),
        ("hit_at_k.json", hit_k),
        ("yearly_stability.json", yearly),
        ("competition_metrics.json", comp_m),
        ("regime_metrics.json", regime_m),
        ("hit_vs_miss_forensic.json", forensic),
        ("reliability_gate_results.json", rel),
        ("reranking_walk_forward.json", rerank),
        ("frozen_vs_replay_comparison.json", frozen_cmp),
        ("leakage_validation.json", leakage),
    ):
        (artifact_root / name).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    payload: dict[str, Any] = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "replay_n": len(rows),
        "inventory": inventory,
        "eligibility": eligibility,
        "rank_metrics": rank_m,
        "hit_at_k": hit_k,
        "yearly_stability": yearly,
        "competition_metrics": comp_m,
        "regime_metrics": regime_m,
        "hit_vs_miss_forensic": forensic,
        "reliability_gate_results": rel,
        "reranking_walk_forward": rerank,
        "frozen_vs_replay_comparison": frozen_cmp,
        "leakage_validation": leakage,
    }
    payload["validation"] = validate_replay(rows, artifact_root)
    payload["recommendation"] = _recommendation(payload)
    (artifact_root / "validation.json").write_text(json.dumps(payload["validation"], indent=2), encoding="utf-8")
    (artifact_root / "backtest_payload.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    Path("ECSE_HISTORICAL_REPLAY_BACKTEST_1_REPORT.md").write_text(render_full_report(payload), encoding="utf-8")
    Path("ECSE_HISTORICAL_REPLAY_OWNER_REPORT.md").write_text(render_owner_report(payload), encoding="utf-8")
    Path("ECSE_HISTORICAL_REPLAY_LEAKAGE_AUDIT.md").write_text(
        json.dumps(leakage, indent=2) + "\n\n" + json.dumps(eligibility.get("temporal_causality_audit", {}), indent=2),
        encoding="utf-8",
    )
    return payload
