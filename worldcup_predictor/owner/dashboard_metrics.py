"""Owner dashboard metrics — Hotfix Pack 7/8 (read-only aggregation, no engine changes)."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.autonomous.performance_certification import THRESHOLDS
from worldcup_predictor.config.competitions import get_competition

CERT_THRESHOLDS = THRESHOLDS

PROMOTION_GATES = {
    "paper": 100,
    "micro": 300,
    "prod": 1000,
}


def resolve_market_metrics(
    markets: dict[str, Any],
    *,
    market: str,
    engine: str,
) -> dict[str, Any]:
    """Fix nested cert report shape: markets['1x2']['production']."""
    bucket = markets.get(market)
    if isinstance(bucket, dict):
        inner = bucket.get(engine)
        if isinstance(inner, dict) and ("evaluated" in inner or "pending" in inner):
            return inner
        if "evaluated" in bucket or "pending" in bucket:
            return bucket
    flat = markets.get(f"{engine}:{market}")
    if isinstance(flat, dict):
        return flat
    return {}


def snapshot_count(conn: Any, *, engine: str, market_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(1) AS c FROM autonomous_prediction_snapshots WHERE engine = ? AND market_id = ?",
        (engine, market_id),
    ).fetchone()
    return int(row["c"]) if row else 0


def load_shadow_jsonl_stats() -> dict[str, Any]:
    """Read elite orchestrator shadow JSONL for model-center truth."""
    try:
        from worldcup_predictor.admin.elite_shadow_preview import (
            EVALUATIONS_PATH,
            PREDICTIONS_PATH,
            load_jsonl,
        )

        preds, pred_meta = load_jsonl(PREDICTIONS_PATH)
        evals, eval_meta = load_jsonl(EVALUATIONS_PATH)
    except Exception as exc:
        return {"error": str(exc), "predictions_by_market": {}, "prediction_total": 0, "evaluation_total": 0}

    by_market = Counter(str(r.get("market_id") or "unknown") for r in preds)
    eval_by_market = Counter(str(r.get("market_id") or "unknown") for r in evals)
    evaluated = sum(1 for r in evals if str(r.get("outcome") or "") in ("correct", "incorrect", "partial", "wrong"))
    pending = len(evals) - evaluated if evals else 0
    return {
        "predictions_path": str(PREDICTIONS_PATH),
        "evaluations_path": str(EVALUATIONS_PATH),
        "prediction_total": len(preds),
        "evaluation_total": len(evals),
        "evaluated": evaluated,
        "pending": pending,
        "predictions_by_market": dict(by_market),
        "evaluations_by_market": dict(eval_by_market),
        "pred_meta": pred_meta,
        "eval_meta": eval_meta,
    }


def load_store_totals(conn: Any) -> dict[str, Any]:
    def _count(sql: str, params: tuple = ()) -> int:
        row = conn.execute(sql, params).fetchone()
        return int(row["c"]) if row else 0

    return {
        "autonomous_snapshots": _count("SELECT COUNT(1) AS c FROM autonomous_prediction_snapshots"),
        "autonomous_evaluations": _count("SELECT COUNT(1) AS c FROM autonomous_snapshot_evaluations"),
        "predops_snapshots": _count("SELECT COUNT(1) AS c FROM predops_snapshots WHERE is_latest = 1"),
        "worldcup_stored_predictions": _count("SELECT COUNT(1) AS c FROM worldcup_stored_predictions"),
    }


def _safe_pct(value: Any) -> str | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(n):
        return None
    if n <= 1:
        n *= 100
    return f"{n:.1f}%"


def format_first_goal_timing_ui(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Convert research timing artifact to owner UI cards (no NaN / raw JSON)."""
    if not raw:
        return {"status": "pending", "label": "Pending", "cards": [], "ranges": []}

    overall = raw.get("overall") or raw.get("main_answer") or {}
    if isinstance(overall, dict) and "among_fixtures_with_at_least_one_goal" in overall:
        overall = overall.get("among_all_reliable_completed_fixtures") or overall.get("among_fixtures_with_at_least_one_goal") or {}

    cards: list[dict[str, Any]] = []
    mapping = (
        ("first_goal_1_30_pct", "Goals 1–30 min", "pct_A_with_goal_first_1_30", "pct_B_all_reliable_first_1_30"),
        ("first_goal_31_plus_pct", "Goals 31+ min", "pct_A_with_goal_first_31_plus", "pct_B_all_reliable_first_31_plus"),
        ("no_goal_pct", "No goal", "pct_B_no_goal", "pct_B_no_goal"),
    )
    flat = raw.get("overall") if isinstance(raw.get("overall"), dict) else {}
    for label_key, title, key_a, key_b in mapping:
        val = overall.get(label_key) or flat.get(key_a) or flat.get(key_b)
        pct = _safe_pct(val)
        cards.append(
            {
                "id": label_key,
                "title": title,
                "value": pct or "N/A",
                "status": "ok" if pct else "unknown",
                "sample": overall.get("sample_size") or flat.get("with_at_least_one_goal") or flat.get("total_reliable_fixtures"),
            }
        )

    ranges: list[dict[str, Any]] = []
    bucket_pct = flat.get("bucket_pct_of_reliable") or {}
    if isinstance(bucket_pct, dict):
        for bucket, pct in bucket_pct.items():
            label = format_goal_timing_token(bucket)
            ranges.append({"bucket": label, "pct": _safe_pct(pct) or "N/A"})

    status = "ok" if any(c.get("value") not in (None, "N/A") for c in cards) else "pending"
    return {
        "status": status,
        "label": "Available" if status == "ok" else "Pending",
        "cards": cards,
        "ranges": ranges,
        "recommendation": raw.get("recommendation"),
        "sample_reliable": flat.get("total_reliable_fixtures"),
    }


def format_goal_timing_token(value: Any) -> str:
    if value is None:
        return "Pending"
    text = str(value).strip()
    if not text or text.lower() == "nan" or "nan" in text.lower():
        return "Unknown"
    if text.lower() in {"pending", "tbd", "null"}:
        return "Pending"
    if "%" in text and "nan" in text.lower():
        return "N/A"
    return text


def certification_display(
    metrics: dict[str, Any],
    *,
    engine: str,
    level_key: str,
    levels: dict[str, str],
) -> dict[str, Any]:
    evaluated = int(metrics.get("evaluated") or 0)
    pending = int(metrics.get("pending") or 0)
    predictions = int(metrics.get("predictions") or 0)
    winrate = metrics.get("winrate")
    legacy = levels.get(level_key) or levels.get(level_key.split(":", 1)[-1]) or "BLOCKED"

    if engine == "elite_shadow" and predictions == 0 and evaluated == 0:
        return {
            "code": "SHADOW_ONLY",
            "label": "SHADOW_RESEARCH_ONLY",
            "legacy": legacy,
            "evaluated": evaluated,
            "required": CERT_THRESHOLDS["RESEARCH_ONLY"]["min_evaluated"],
        }

    min_research = CERT_THRESHOLDS["RESEARCH_ONLY"]["min_evaluated"]
    min_paper = CERT_THRESHOLDS["PAPER_READY"]["min_evaluated"]
    min_prod = CERT_THRESHOLDS["PRODUCTION_READY"]["min_evaluated"]
    min_wr_paper = CERT_THRESHOLDS["PAPER_READY"]["min_winrate"]
    min_wr_prod = CERT_THRESHOLDS["PRODUCTION_READY"]["min_winrate"]

    if evaluated < min_research:
        return {
            "code": "WAITING_DATA",
            "label": f"WAITING_DATA ({evaluated}/{min_research})",
            "legacy": legacy,
            "evaluated": evaluated,
            "pending": pending,
            "required": min_research,
        }

    if legacy == "PRODUCTION_READY" or (
        evaluated >= min_prod and winrate is not None and winrate >= min_wr_prod
    ):
        return {"code": "CERTIFIED", "label": "CERTIFIED", "legacy": legacy, "evaluated": evaluated}

    if legacy == "PAPER_READY":
        return {"code": "PROMOTED", "label": "PAPER_READY", "legacy": legacy, "evaluated": evaluated}

    if evaluated < min_paper:
        return {
            "code": "LOW_SAMPLE",
            "label": f"LOW_SAMPLE ({evaluated}/{min_paper})",
            "legacy": legacy,
            "evaluated": evaluated,
            "required": min_paper,
        }

    if winrate is not None and winrate < min_wr_paper:
        return {
            "code": "LOW_WINRATE",
            "label": f"LOW_WINRATE ({winrate * 100:.1f}%)",
            "legacy": legacy,
            "evaluated": evaluated,
            "winrate": winrate,
        }

    if legacy == "RESEARCH_ONLY":
        return {"code": "RESEARCH_ONLY", "label": "RESEARCH_ONLY", "legacy": legacy, "evaluated": evaluated}

    return {"code": "BLOCKED", "label": legacy, "legacy": legacy, "evaluated": evaluated}


def build_market_row(
    *,
    markets: dict[str, Any],
    levels: dict[str, str],
    engine: str,
    market: str,
    conn: Any,
    shadow_by_market: dict[str, int] | None = None,
) -> dict[str, Any]:
    metrics = dict(resolve_market_metrics(markets, market=market, engine=engine))
    preds = snapshot_count(conn, engine=engine, market_id=market)
    shadow_n = int((shadow_by_market or {}).get(market) or 0)
    if engine == "elite_shadow" and shadow_n > preds:
        preds = shadow_n
    evaluated = int(metrics.get("evaluated") or 0)
    pending = int(metrics.get("pending") or 0)
    metrics["predictions"] = preds or (evaluated + pending)
    metrics["autonomous_predictions"] = snapshot_count(conn, engine=engine, market_id=market)
    if engine == "elite_shadow":
        metrics["shadow_jsonl_predictions"] = shadow_n
    level_key = f"{engine}:{market}"
    cert = certification_display(metrics, engine=engine, level_key=level_key, levels=levels)
    return {
        "market": market,
        "predictions": metrics["predictions"],
        "evaluated": evaluated,
        "pending": pending,
        "winrate": metrics.get("winrate"),
        "roi": metrics.get("roi"),
        "certification": cert["label"],
        "certification_code": cert["code"],
        "certification_detail": cert,
    }


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def aggregate_wc_engine_metrics(
    repo: Any,
    *,
    rolling_days: int | None = None,
) -> dict[str, Any]:
    rows = repo.list_all_worldcup_prediction_evaluations(include_quarantined=True)
    cutoff = None
    if rolling_days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=rolling_days)).replace(tzinfo=None)

    correct = wrong = pending = 0
    for row in rows:
        if cutoff:
            ev_at = _parse_dt(row.get("evaluated_at"))
            if ev_at is None or ev_at < cutoff:
                continue
        st = str(row.get("market_1x2_status") or row.get("overall_status") or "pending").lower()
        if st == "correct":
            correct += 1
        elif st == "wrong":
            wrong += 1
        else:
            pending += 1
    evaluated = correct + wrong
    return {
        "source": "worldcup_prediction_evaluations",
        "evaluated": evaluated,
        "correct": correct,
        "wrong": wrong,
        "pending": pending,
        "winrate": (correct / evaluated) if evaluated else None,
        "total_rows": len(rows),
    }


def build_performance_center_payload(
    *,
    store: Any,
    repo: Any,
    cert_summary: dict[str, Any],
) -> dict[str, Any]:
    prod_auto = dict(cert_summary.get("engines", {}).get("production") or {})
    elite_auto = dict(cert_summary.get("engines", {}).get("elite_shadow") or {})
    prod_wc = aggregate_wc_engine_metrics(repo)
    correct = int(prod_wc.get("correct") or 0)
    wrong = int(prod_wc.get("wrong") or 0)
    evaluated = correct + wrong
    if evaluated == 0:
        evaluated = int(prod_auto.get("evaluated") or 0)
        correct = int(prod_auto.get("correct") or 0)
        wrong = int(prod_auto.get("wrong") or 0)
    prod_merged = {
        **prod_auto,
        "autonomous": prod_auto,
        "worldcup_evaluations": prod_wc,
        "evaluated": evaluated,
        "correct": correct,
        "wrong": wrong,
        "winrate": (correct / evaluated) if evaluated else None,
    }

    rolling: dict[str, Any] = {}
    for days in (7, 30, 90):
        rolling[f"{days}d"] = {
            "production": {
                **store.aggregate_performance(engine="production", rolling_days=days),
                "worldcup": aggregate_wc_engine_metrics(repo, rolling_days=days),
            },
            "elite_shadow": store.aggregate_performance(engine="elite_shadow", rolling_days=days),
        }

    return {
        "production": prod_merged,
        "elite_shadow": elite_auto,
        "rolling": rolling,
        "overall": cert_summary.get("overall") or {},
        "certification_levels": cert_summary.get("certification_levels") or {},
    }


def promotion_progress_block(evaluated: int) -> dict[str, Any]:
    ev = int(evaluated or 0)
    return {
        "paper": {"current": ev, "required": PROMOTION_GATES["paper"], "label": f"{ev} / {PROMOTION_GATES['paper']}"},
        "micro": {"current": ev, "required": PROMOTION_GATES["micro"], "label": f"{ev} / {PROMOTION_GATES['micro']}"},
        "prod": {"current": ev, "required": PROMOTION_GATES["prod"], "label": f"{ev} / {PROMOTION_GATES['prod']}"},
    }


def _health_level(ok: bool | None, *, warn: bool = False) -> str:
    if ok is True:
        return "green"
    if warn:
        return "yellow"
    return "red"


def build_health_cards(
    *,
    overview: dict[str, Any],
    monitoring: dict[str, Any],
    autonomous: dict[str, Any],
) -> list[dict[str, Any]]:
    health = overview.get("health") or {}
    pg = health.get("postgres") == "operational"
    api_ok = health.get("api") == "operational"
    sched = monitoring.get("scheduler") or {}
    quota = monitoring.get("api_quota") or {}
    sysm = monitoring.get("system") or {}
    ram = sysm.get("ram") or {}
    disk = sysm.get("disk") or {}

    predops_depth = 0
    try:
        from worldcup_predictor.predops.store import PredOpsStore

        predops_depth = int(PredOpsStore().queue_stats().get("queued") or 0)
    except Exception:
        predops_depth = 0

    return [
        {"id": "api", "title": "API", "status": _health_level(api_ok), "detail": "operational" if api_ok else "degraded"},
        {"id": "postgres", "title": "Postgres", "status": _health_level(pg), "detail": "reachable" if pg else "down"},
        {"id": "redis", "title": "Redis", "status": "yellow", "detail": "not configured (SQLite cache)"},
        {
            "id": "scheduler",
            "title": "Scheduler",
            "status": _health_level(bool(sched.get("active")), warn=not sched.get("enabled")),
            "detail": f"timer {'active' if sched.get('active') else 'inactive'}",
            "last_run": autonomous.get("last_run"),
        },
        {
            "id": "predops",
            "title": "PredOps",
            "status": _health_level(predops_depth < 50, warn=predops_depth >= 20),
            "detail": f"queue depth {predops_depth}",
        },
        {
            "id": "shadow_runtime",
            "title": "Shadow Runtime",
            "status": _health_level(autonomous.get("platform_enabled", True)),
            "detail": f"predictions today {overview.get('autonomous', {}).get('predictions_today', 0)}",
        },
        {
            "id": "assistant_timer",
            "title": "Assistant Timer",
            "status": _health_level(bool(sched.get("enabled"))),
            "detail": sched.get("timer_unit") or "worldcup-autonomous.timer",
        },
        {
            "id": "disk",
            "title": "Disk",
            "status": _health_level((disk.get("percent") or 0) < 85, warn=(disk.get("percent") or 0) >= 70),
            "detail": f"{disk.get('percent', '—')}% used",
        },
        {
            "id": "ram",
            "title": "RAM",
            "status": _health_level((ram.get("percent") or 0) < 90, warn=(ram.get("percent") or 0) >= 75),
            "detail": f"{ram.get('percent', '—')}% used",
        },
        {
            "id": "cpu",
            "title": "CPU",
            "status": _health_level((sysm.get("cpu_percent") or 0) < 85, warn=(sysm.get("cpu_percent") or 0) >= 70),
            "detail": f"{sysm.get('cpu_percent', '—')}%",
        },
        {
            "id": "api_usage",
            "title": "API Usage",
            "status": _health_level(quota.get("quota_risk") not in ("high", "critical")),
            "detail": f"calls today {quota.get('live_requests', 0)} · risk {quota.get('quota_risk', '—')}",
        },
    ]


def upcoming_fixture_count(conn: Any, competition_key: str, *, days: int = 90) -> int:
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days)).replace(tzinfo=None).isoformat()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    row = conn.execute(
        """
        SELECT COUNT(1) AS c FROM fixtures
        WHERE competition_key = ?
          AND status IN ('NS', 'TBD', 'PST')
          AND kickoff_utc IS NOT NULL
          AND kickoff_utc >= ?
          AND kickoff_utc <= ?
        """,
        (competition_key, now, cutoff),
    ).fetchone()
    return int(row["c"]) if row else 0


def enrich_prefetch_competition(
    block: dict[str, Any],
    *,
    conn: Any,
    window_days: int,
) -> dict[str, Any]:
    ck = block["competition_key"]
    if int(block.get("fixtures") or 0) > 0:
        block["season_status"] = "IN_SEASON"
        return block
    upcoming_90 = upcoming_fixture_count(conn, ck, days=90)
    upcoming_window = upcoming_fixture_count(conn, ck, days=window_days)
    if upcoming_window > 0 or upcoming_90 > 0:
        block["season_status"] = "OUT_OF_WINDOW"
        block["fixtures_upcoming_90d"] = upcoming_90
    else:
        block["season_status"] = "OFF_SEASON"
        try:
            block["competition_name"] = get_competition(ck).display_name
        except KeyError:
            block["competition_name"] = ck
        block["coverage_label"] = "OFF_SEASON"
    return block
