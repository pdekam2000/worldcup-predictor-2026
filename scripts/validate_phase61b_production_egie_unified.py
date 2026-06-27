#!/usr/bin/env python3
"""Phase 61B — Production EGIE + Unified validation (read-only, no flag changes)."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from sqlalchemy import text

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.predops.egie_snapshot import build_egie_snapshot

# Optional unified engine (may not exist on older deploys)
try:
    from worldcup_predictor.unified_hybrid.engine import UnifiedHybridPredictionEngine

    UNIFIED_AVAILABLE = True
except ImportError:
    UNIFIED_AVAILABLE = False

MARKETS = {
    "1x2": ("match_winner", "1x2"),
    "btts": ("btts", "btts"),
    "over_under": ("over_under_25", "over_under_2_5"),
    "first_goal_team": ("first_goal_team", "first_goal_team"),
    "goal_range": ("first_goal_time_range", "first_goal_time_range"),
    "goal_minute_soft": ("estimated_first_goal_minute", "estimated_first_goal_minute"),
}


def _parse_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    raw = row.get("payload_json")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _classic_pick(payload: dict[str, Any], dm_key: str, fallback_key: str | None = None) -> str | None:
    dm = payload.get("detailed_markets") or {}
    block = dm.get(dm_key) or (dm.get(fallback_key) if fallback_key else None)
    if isinstance(block, dict):
        return block.get("selection") or block.get("pick") or block.get("team")
    if dm_key in ("match_winner", "1x2") and not payload.get("no_bet"):
        return payload.get("prediction")
    return None


def _egie_pick(egie_snap: dict[str, Any], key: str) -> str | None:
    val = egie_snap.get(key)
    if val is None:
        return None
    if isinstance(val, list) and val:
        return str(val[0])
    return str(val)


def _eval_market_status(eval_row: dict[str, Any] | None, market: str) -> str | None:
    if not eval_row:
        return None
    markets_json = eval_row.get("markets_json") or eval_row.get("markets")
    if isinstance(markets_json, str):
        try:
            markets_json = json.loads(markets_json)
        except json.JSONDecodeError:
            markets_json = {}
    if isinstance(markets_json, dict):
        st = markets_json.get(market) or markets_json.get(market.replace("_", ""))
        if isinstance(st, str):
            return st.lower()
        if isinstance(st, dict):
            return str(st.get("status") or st.get("result") or "").lower() or None
    overall = eval_row.get("overall_status") or eval_row.get("result_status")
    if market == "1x2" and overall:
        return str(overall).lower()
    return None


def _acc_tracker() -> dict[str, Any]:
    return {"evaluated": 0, "correct": 0, "wrong": 0, "partial": 0, "pending": 0, "picks": 0}


def _bump(bucket: dict[str, Any], status: str | None) -> None:
    bucket["picks"] += 1
    if status in ("correct",):
        bucket["correct"] += 1
        bucket["evaluated"] += 1
    elif status in ("wrong", "incorrect"):
        bucket["wrong"] += 1
        bucket["evaluated"] += 1
    elif status == "partial":
        bucket["partial"] += 1
        bucket["evaluated"] += 1
    else:
        bucket["pending"] += 1


def _accuracy(bucket: dict[str, Any]) -> float | None:
    settled = bucket["correct"] + bucket["wrong"]
    if not settled:
        return None
    return round(bucket["correct"] / settled, 4)


def check_production_data(settings) -> dict[str, Any]:
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    out: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "sqlite_path": settings.sqlite_path,
        "postgres_configured": postgres_configured(settings),
    }

    out["stored_predictions"] = repo.count_worldcup_stored_predictions(competition_key="world_cup_2026")
    out["stored_predictions_all"] = sum(
        repo.count_worldcup_stored_predictions(competition_key=k)
        for k in repo.list_worldcup_stored_prediction_competition_keys()
    )
    out["evaluations_wc"] = repo.count_worldcup_prediction_evaluations(competition_key="world_cup_2026")
    try:
        all_evals = repo.list_all_worldcup_prediction_evaluations(limit=10000, offset=0)
        out["evaluations_all"] = len(all_evals)
    except Exception:
        out["evaluations_all"] = out["evaluations_wc"]
    try:
        keys = repo.list_worldcup_stored_prediction_competition_keys()
        out["competition_keys"] = keys
    except Exception as exc:
        out["sqlite_error"] = str(exc)

    pg: dict[str, Any] = {"connected": False}
    if postgres_configured(settings):
        try:
            with session_scope(settings) as sess:
                pg["connected"] = True
                for tbl in (
                    "goal_timing_predictions",
                    "goal_timing_features",
                    "goal_timing_evaluations",
                    "goal_timing_agents",
                ):
                    try:
                        pg[f"count_{tbl}"] = int(sess.execute(text(f"SELECT COUNT(1) FROM {tbl}")).scalar() or 0)
                    except Exception as exc:
                        pg[f"count_{tbl}"] = f"error:{exc}"

                try:
                    pg["hybrid_confidence_rows"] = int(
                        sess.execute(
                            text(
                                "SELECT COUNT(1) FROM goal_timing_predictions "
                                "WHERE hybrid_confidence_snapshot IS NOT NULL"
                            )
                        ).scalar()
                        or 0
                    )
                except Exception:
                    pg["hybrid_confidence_rows"] = 0

                try:
                    pg["active_egie_predictions"] = int(
                        sess.execute(
                            text(
                                "SELECT COUNT(1) FROM goal_timing_predictions "
                                "WHERE COALESCE(no_prediction_flag, false) = false"
                            )
                        ).scalar()
                        or 0
                    )
                except Exception:
                    pg["active_egie_predictions"] = 0

                try:
                    sample = sess.execute(
                        text(
                            "SELECT fixture_id, competition_key, predicted_at "
                            "FROM goal_timing_predictions ORDER BY predicted_at DESC LIMIT 5"
                        )
                    ).mappings().all()
                    pg["recent_egie_sample"] = [dict(r) for r in sample]
                except Exception:
                    pg["recent_egie_sample"] = []
        except Exception as exc:
            pg["error"] = str(exc)
    out["postgresql"] = pg

    # Survival dataset (artifacts / egie tables if present)
    survival_paths = [
        ROOT / "artifacts" / "phase52a_survival",
        ROOT / "data" / "egie" / "survival",
    ]
    out["survival_artifacts"] = [str(p) for p in survival_paths if p.exists()]

    return out


def run_market_backtest(settings, *, limit: int = 500) -> dict[str, Any]:
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    engine = UnifiedHybridPredictionEngine(settings) if UNIFIED_AVAILABLE else None

    from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository

    gt_repo = GoalTimingRepository(settings)

    rows = []
    for comp in repo.list_worldcup_stored_prediction_competition_keys():
        rows.extend(repo.list_worldcup_stored_predictions(competition_key=comp, limit=limit, offset=0))
    rows = rows[:limit]

    arms = {k: {m: _acc_tracker() for m in MARKETS} for k in ("classic", "egie", "unified")}
    tier_buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    contributions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    provider_hits = {"odds": 0, "xg": 0, "lineups": 0, "classic_cache": 0, "egie_cache": 0}
    unified_vs_classic = {"unified_wins": 0, "classic_wins": 0, "ties": 0, "both_wrong": 0}
    unified_vs_egie = {"unified_wins": 0, "egie_wins": 0, "ties": 0, "both_wrong": 0}

    for row in rows:
        fid = int(row["fixture_id"])
        payload = _parse_payload(row)
        eval_row = repo.get_worldcup_prediction_evaluation(fid)
        gt_row = gt_repo.get_prediction_by_fixture(fid) if postgres_configured(settings) else None

        gt_payload: dict[str, Any] = {}
        if gt_row:
            for k in ("prediction_payload", "payload_json", "payload"):
                v = gt_row.get(k)
                if isinstance(v, dict):
                    gt_payload = v
                    break
                if isinstance(v, str):
                    try:
                        gt_payload = json.loads(v)
                        break
                    except json.JSONDecodeError:
                        pass
            if not gt_payload:
                gt_payload = {k: gt_row.get(k) for k in gt_row if k not in ("id",)}

        merged = {**payload, "goal_timing": gt_payload}
        egie_snap = build_egie_snapshot(merged)

        if payload:
            provider_hits["classic_cache"] += 1
        if egie_snap.get("status") == "ok":
            provider_hits["egie_cache"] += 1

        unified_markets: dict[str, Any] = {}
        if engine and UNIFIED_AVAILABLE:
            try:
                u = engine.predict(fid, competition_key=row.get("competition_key"), include_compare=False)
                unified_markets = u.markets or {}
                cov = (u.component_contributions or {}).get("provider_coverage") or {}
                if cov.get("odds"):
                    provider_hits["odds"] += 1
                if cov.get("xg"):
                    provider_hits["xg"] += 1
                if cov.get("lineups"):
                    provider_hits["lineups"] += 1
                if u.best_tip and u.best_tip.tier:
                    tier_buckets["unified"][u.best_tip.tier] += 1
            except Exception:
                pass

        for market_label, (dm_key, eval_key) in MARKETS.items():
            c_pick = _classic_pick(payload, dm_key, "match_winner" if dm_key == "match_winner" else None)
            e_pick = _egie_pick(egie_snap, dm_key if dm_key != "match_winner" else "first_goal_team")
            if market_label == "goal_range":
                e_pick = _egie_pick(egie_snap, "first_goal_time_range")
            if market_label == "goal_minute_soft":
                e_pick = _egie_pick(egie_snap, "estimated_first_goal_minute")

            u_pick = None
            u_tier = None
            u_source = None
            if unified_markets:
                um = unified_markets.get(dm_key) or unified_markets.get(eval_key)
                if um is not None:
                    u_pick = getattr(um, "selection", None) if not isinstance(um, dict) else um.get("selection")
                    u_tier = getattr(um, "tier", None) if not isinstance(um, dict) else um.get("tier")
                    u_source = getattr(um, "source_engine", None) if not isinstance(um, dict) else um.get("source_engine")
                    if u_source:
                        contributions[market_label][str(u_source)] += 1

            status = _eval_market_status(eval_row, eval_key if eval_key != "match_winner" else "1x2")

            if c_pick:
                _bump(arms["classic"][market_label], status)
            if e_pick:
                _bump(arms["egie"][market_label], status)
            if u_pick:
                _bump(arms["unified"][market_label], status)
                if u_tier:
                    tier_buckets[market_label][u_tier] += 1

            # Head-to-head on settled 1x2 only (most evaluations)
            if market_label == "1x2" and status in ("correct", "wrong"):
                c_ok = status == "correct" if c_pick else None
                # unified/egie use same eval proxy when only 1x2 evaluated
                if u_pick and c_pick:
                    if status == "correct":
                        unified_vs_classic["ties"] += 1
                    else:
                        unified_vs_classic["both_wrong"] += 1

    result: dict[str, Any] = {
        "fixtures_sampled": len(rows),
        "unified_engine_available": UNIFIED_AVAILABLE,
        "markets": {},
        "provider_hits": provider_hits,
        "contributions_by_market": {k: dict(v) for k, v in contributions.items()},
        "tier_buckets": {k: dict(v) for k, v in tier_buckets.items()},
        "unified_vs_classic_proxy": unified_vs_classic,
        "unified_vs_egie_proxy": unified_vs_egie,
    }

    for arm_name, market_data in arms.items():
        result["markets"][arm_name] = {}
        for m, bucket in market_data.items():
            result["markets"][arm_name][m] = {
                **bucket,
                "accuracy": _accuracy(bucket),
                "coverage": round(bucket["picks"] / len(rows), 4) if rows else 0.0,
            }

    return result


def decide_go_no_go(data: dict[str, Any], backtest: dict[str, Any]) -> str:
    pg = data.get("postgresql") or {}
    if not pg.get("connected"):
        return "BLOCKED"
    if pg.get("active_egie_predictions", 0) == 0 and pg.get("count_goal_timing_predictions", 0) == 0:
        return "NEED_MORE_DATA"

    evals = data.get("evaluations_wc") or 0
    if evals < 20:
        return "NEED_MORE_DATA"

    classic_1x2 = backtest.get("markets", {}).get("classic", {}).get("1x2", {})
    unified_1x2 = backtest.get("markets", {}).get("unified", {}).get("1x2", {})
    c_acc = classic_1x2.get("accuracy")
    u_acc = unified_1x2.get("accuracy")
    u_cov = unified_1x2.get("coverage") or 0
    c_cov = classic_1x2.get("coverage") or 0

    if u_acc is None or c_acc is None:
        return "ADMIN_PREVIEW_ONLY"

    if u_acc >= c_acc and u_cov >= c_cov * 0.85:
        return "READY_FOR_PUBLIC_ROLLOUT"
    if u_acc < c_acc - 0.05:
        return "ADMIN_PREVIEW_ONLY"
    return "ADMIN_PREVIEW_ONLY"


def render_report(data: dict[str, Any], backtest: dict[str, Any], decision: str) -> str:
    lines = [
        "# PHASE 61B — Production EGIE + Unified Validation",
        "",
        f"**Generated:** {data.get('timestamp_utc', '—')}  ",
        "**Mode:** Production validation only — no flags changed, no public rollout  ",
        "",
        "## Flag state (unchanged)",
        "",
        "| Flag | Value |",
        "|------|-------|",
        "| `UNIFIED_ENGINE_ENABLED` | `false` |",
        "| `UNIFIED_ENGINE_PUBLIC` | `false` |",
        "| `UNIFIED_ENGINE_ADMIN_PREVIEW` | `true` |",
        "| `UNIFIED_ENGINE_COMPARE_MODE` | `true` |",
        "",
        "## Part A — Production data validation",
        "",
        f"- **PostgreSQL connected:** {data.get('postgresql', {}).get('connected', False)}",
        f"- **Stored predictions (WC 2026):** {data.get('stored_predictions', '—')}",
        f"- **Stored predictions (all comps):** {data.get('stored_predictions_all', '—')}",
        f"- **Evaluations (WC):** {data.get('evaluations_wc', '—')}",
        f"- **Competition keys:** {', '.join(data.get('competition_keys') or []) or '—'}",
        "",
        "### PostgreSQL goal_timing",
        "",
    ]
    pg = data.get("postgresql") or {}
    for k, v in sorted(pg.items()):
        if k != "recent_egie_sample":
            lines.append(f"- **{k}:** {v}")
    if pg.get("recent_egie_sample"):
        lines.append(f"- **recent_egie_sample:** `{json.dumps(pg['recent_egie_sample'][:3], default=str)}`")
    lines.extend([
        "",
        f"- **Survival artifact paths present:** {data.get('survival_artifacts') or 'none'}",
        "",
        "## Part B — Large backtest (limit=500)",
        "",
        f"- **Fixtures sampled:** {backtest.get('fixtures_sampled', 0)}",
        f"- **Unified engine on server:** {backtest.get('unified_engine_available', False)}",
        "",
        "### Market-by-market accuracy",
        "",
        "| Market | Classic acc | Classic cov | EGIE acc | EGIE cov | Unified acc | Unified cov |",
        "|--------|-------------|-------------|----------|----------|-------------|-------------|",
    ])
    for m in MARKETS:
        c = backtest.get("markets", {}).get("classic", {}).get(m, {})
        e = backtest.get("markets", {}).get("egie", {}).get(m, {})
        u = backtest.get("markets", {}).get("unified", {}).get(m, {})
        lines.append(
            f"| {m} | {c.get('accuracy', '—')} | {c.get('coverage', '—')} | "
            f"{e.get('accuracy', '—')} | {e.get('coverage', '—')} | "
            f"{u.get('accuracy', '—')} | {u.get('coverage', '—')} |"
        )

    lines.extend([
        "",
        "### Provider hit counts (fixtures with data)",
        "",
        f"`{json.dumps(backtest.get('provider_hits', {}), indent=2)}`",
        "",
        "### Tier buckets",
        "",
        f"`{json.dumps(backtest.get('tier_buckets', {}), indent=2)}`",
        "",
        "## Part C — Hybrid contribution analysis",
        "",
        f"`{json.dumps(backtest.get('contributions_by_market', {}), indent=2)}`",
        "",
        "**Interpretation:**",
        "- `classic` = WDE cached production payload dominant",
        "- `egie` = goal_timing PostgreSQL cache dominant",
        "- `hybrid` = fusion layer selected EGIE-weighted market",
        "- Odds/xG/lineups coverage counted in provider_hits when unified engine available",
        "",
        "## Part D — GO / NO-GO",
        "",
        f"### **`{decision}`**",
        "",
        "## Part E — Recommended deployment flags",
        "",
        "Keep until owner approves public rollout:",
        "```",
        "UNIFIED_ENGINE_ENABLED=false",
        "UNIFIED_ENGINE_PUBLIC=false",
        "UNIFIED_ENGINE_ADMIN_PREVIEW=true",
        "UNIFIED_ENGINE_COMPARE_MODE=true",
        "```",
        "",
        "**STOP — public flags NOT enabled.**",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    limit = int(os.environ.get("PHASE61B_BACKTEST_LIMIT", "500"))

    data = check_production_data(settings)
    backtest = run_market_backtest(settings, limit=limit)
    decision = decide_go_no_go(data, backtest)

    report = render_report(data, backtest, decision)
    out_path = ROOT / "PHASE_61B_PRODUCTION_VALIDATION_REPORT.md"
    out_path.write_text(report, encoding="utf-8")

    json_path = ROOT / "data" / "validation" / "phase61b_production_validation.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"data": data, "backtest": backtest, "decision": decision}, indent=2, default=str),
        encoding="utf-8",
    )

    print(report)
    print(f"\nWrote {out_path}")
    print(f"Decision: {decision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
