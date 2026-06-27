"""Strip debug metadata from public PredOps responses — Phase A15 + A16."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.publication.bet_quality_overlay import apply_plan_gating, build_publication_overlay

_DEBUG_KEYS = frozenset(
    {
        "tier_a_prediction",
        "tier_b_prediction",
        "audit_trace",
        "agent_contributions",
        "data_sources_used",
        "calibration_version",
        "model_version",
        "deltas",
        "payload",
        "_predops_signals",
        "_prefetch_signals",
    }
)


def sanitize_public_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}
    overlay = apply_plan_gating(build_publication_overlay(payload, include_debug=False), "free")
    out: dict[str, Any] = {
        "snapshot_id": snapshot.get("snapshot_id"),
        "fixture_id": snapshot.get("fixture_id"),
        "competition_key": snapshot.get("competition_key"),
        "generated_at": snapshot.get("generated_at"),
        "coverage_state": snapshot.get("coverage_state"),
        "publication_overlay": overlay,
    }
    markets_doc = snapshot.get("markets") or {}
    public_markets: dict[str, Any] = {}
    mkt = markets_doc.get("markets") if isinstance(markets_doc, dict) else {}
    if isinstance(mkt, dict):
        mq = overlay.get("market_quality") or {}
        for mid, block in mkt.items():
            if not isinstance(block, dict):
                continue
            quality = mq.get(mid) or mq.get(mid.replace("match_winner", "1x2")) or {}
            public_markets[mid] = {
                "market_id": mid,
                "market_status": block.get("market_status"),
                "final_selected_prediction": block.get("final_selected_prediction"),
                "bet_quality_score": quality.get("bet_quality_score"),
                "bet_quality_tier": quality.get("bet_quality_tier"),
                "bet_quality_color": quality.get("bet_quality_color"),
                "quality_reason": quality.get("quality_reason"),
            }
    out["markets"] = public_markets
    return out


def sanitize_public_coverage(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "version": report.get("version"),
        "window_days": report.get("window_days"),
        "generated_at": report.get("generated_at"),
        "totals": report.get("totals"),
        "competitions": [
            {
                "competition_key": c.get("competition_key"),
                "fixtures": c.get("fixtures"),
                "latest_snapshots": c.get("latest_snapshots"),
                "coverage_pct": c.get("coverage_pct"),
                "fresh_pct": c.get("fresh_pct"),
                "missing": c.get("missing"),
                "stale": c.get("stale"),
            }
            for c in report.get("competitions") or []
        ],
    }
