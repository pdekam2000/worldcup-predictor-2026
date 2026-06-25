"""Phase 48A — production accuracy snapshots, Rule A impact, agent contribution."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.api.global_prediction_archive import _parse_payload
from worldcup_predictor.api.performance_center import _MARKET_DEFS, reliability_level
from worldcup_predictor.automation.worldcup_background.accuracy_summary import rebuild_accuracy_summary
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

_AGENT_GROUPS: dict[str, tuple[str, ...]] = {
    "weather": ("weather_agent",),
    "odds_cluster": (
        "odds_market_agent",
        "market_consensus_agent",
        "sharp_money_intelligence_agent",
        "odds_control_agent",
    ),
    "odds_movement": ("odds_movement_agent",),
    "advanced_match_intelligence": (),
    "player_intelligence": (),
    "provider_fusion": (),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _parse_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _harmonization_fields(payload: dict[str, Any]) -> dict[str, str]:
    md = payload.get("metadata") or {}
    if not isinstance(md, dict):
        md = {}
    out: dict[str, str] = {}
    for key in (
        "harmonization_used",
        "harmonization_reason",
        "harmonization_source",
        "rule_a_active",
        "odds_available",
    ):
        val = payload.get(key) or md.get(key)
        if val is not None:
            out[key] = str(val).lower()
    return out


def _scoreline_implied_1x2(payload: dict[str, Any]) -> str | None:
    sl = payload.get("scoreline") or payload.get("predicted_scoreline")
    if isinstance(sl, dict):
        try:
            h = int(round(float(sl.get("home_goals") or sl.get("home") or 0)))
            a = int(round(float(sl.get("away_goals") or sl.get("away") or 0)))
        except (TypeError, ValueError):
            return None
    elif isinstance(sl, str) and "-" in sl:
        parts = sl.split("-", 1)
        try:
            h, a = int(parts[0].strip()), int(parts[1].strip())
        except ValueError:
            return None
    else:
        return None
    if h > a:
        return "home_win"
    if h < a:
        return "away_win"
    return "draw"


def _final_1x2_selection(payload: dict[str, Any]) -> str | None:
    sel = payload.get("selection") or payload.get("predicted_1x2")
    if not sel and isinstance(payload.get("one_x_two"), dict):
        sel = payload["one_x_two"].get("selection")
    if not sel:
        return None
    mapping = {
        "home": "home_win",
        "away": "away_win",
        "draw": "draw",
        "home_win": "home_win",
        "away_win": "away_win",
    }
    return mapping.get(str(sel).lower(), str(sel).lower())


def _actual_1x2_from_eval(row: dict[str, Any]) -> str | None:
    actual = row.get("actual_result")
    if not actual:
        score = row.get("final_score")
        if score and "-" in str(score):
            parts = str(score).split("-", 1)
            try:
                h, a = int(parts[0]), int(parts[1])
                if h > a:
                    return "home_win"
                if h < a:
                    return "away_win"
                return "draw"
            except ValueError:
                pass
        return None
    mapping = {
        "home": "home_win",
        "away": "away_win",
        "draw": "draw",
        "home_win": "home_win",
        "away_win": "away_win",
    }
    return mapping.get(str(actual).lower())


def _market_blocks_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    key_map = {
        "1X2": "market_1x2",
        "Over/Under 2.5": "market_over_under_2_5",
        "BTTS": "market_btts",
        "Double Chance": "market_double_chance",
        "HT Result": "market_ht_result",
        "Correct Score": "market_correct_score",
        "First Goal Team": "market_first_goal_team",
        "Goalscorer": "market_goalscorer",
        "Goal Minute": "market_goal_minute",
    }
    blocks: list[dict[str, Any]] = []
    for label, key in key_map.items():
        raw = summary.get(key) or {}
        total = int(raw.get("total") or 0)
        correct = int(raw.get("correct") or 0)
        wrong = max(0, total - correct)
        winrate = raw.get("winrate")
        if winrate is None and total > 0:
            winrate = round(correct / total, 4)
        blocks.append(
            {
                "market_name": label,
                "winrate": winrate,
                "sample_size": total,
                "correct": correct,
                "wrong": wrong,
                "reliability": reliability_level(total),
            }
        )
    return blocks


def compute_rule_a_impact(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    """Measure Rule A telemetry on settled 1X2 evaluations (production only)."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    try:
        eval_rows = repo.list_worldcup_prediction_evaluations(competition_key=competition_key)
        counters = {
            "wde_preserved": 0,
            "scoreline_override": 0,
            "beneficial_override": 0,
            "harmful_override": 0,
            "neutral_override": 0,
            "no_telemetry": 0,
            "settled_1x2": 0,
        }
        reason_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}

        for ev in eval_rows:
            status = str(ev.get("market_1x2_status") or "").lower()
            if status not in {"correct", "wrong"}:
                continue
            counters["settled_1x2"] += 1
            stored = repo.get_worldcup_stored_prediction(int(ev["fixture_id"]))
            payload = _parse_payload(stored) if stored else {}
            if str(payload.get("generated_by") or "").lower() in {"test", "phase35_test", "phase33_test"}:
                continue

            harm = _harmonization_fields(payload)
            if not harm:
                counters["no_telemetry"] += 1
                continue

            source = harm.get("harmonization_source", "unknown")
            reason = harm.get("harmonization_reason", "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

            used = harm.get("harmonization_used") == "true"
            if source == "wde" or not used:
                counters["wde_preserved"] += 1
            else:
                counters["scoreline_override"] += 1

            actual = _actual_1x2_from_eval(ev)
            final_pick = _final_1x2_selection(payload)
            scoreline_pick = _scoreline_implied_1x2(payload)
            if actual is None or final_pick is None:
                continue

            if source == "scoreline" and used and scoreline_pick and scoreline_pick != final_pick:
                scoreline_pick = final_pick

            if source == "wde" or not used:
                wde_pick = final_pick
                sl_pick = scoreline_pick or final_pick
            else:
                wde_pick = scoreline_pick if scoreline_pick == final_pick else final_pick
                sl_pick = final_pick

            if wde_pick == sl_pick:
                continue

            wde_ok = wde_pick == actual
            sl_ok = sl_pick == actual
            if not wde_ok and sl_ok:
                counters["beneficial_override"] += 1
            elif wde_ok and not sl_ok:
                counters["harmful_override"] += 1
            elif not wde_ok and not sl_ok:
                counters["neutral_override"] += 1

        total_tracked = counters["wde_preserved"] + counters["scoreline_override"]
        override_rate = (
            round(counters["scoreline_override"] / total_tracked, 4) if total_tracked else None
        )
        return {
            "updated_at": _utc_now_iso(),
            "settled_1x2": counters["settled_1x2"],
            "wde_preserved": counters["wde_preserved"],
            "scoreline_override": counters["scoreline_override"],
            "override_rate": override_rate,
            "beneficial_override": counters["beneficial_override"],
            "harmful_override": counters["harmful_override"],
            "neutral_override": counters["neutral_override"],
            "no_telemetry": counters["no_telemetry"],
            "harmonization_reason_counts": reason_counts,
            "harmonization_source_counts": source_counts,
            "rule_a_gate_mode": settings.rule_a_gate_mode,
        }
    finally:
        repo.close()


def compute_agent_contribution(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    """Track-only specialist influence vs winning 1X2 (does not modify WDE)."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    try:
        eval_rows = repo.list_worldcup_prediction_evaluations(competition_key=competition_key)
        groups: dict[str, dict[str, Any]] = {
            key: {
                "layer": key,
                "recommendation_count": 0,
                "available_count": 0,
                "alignment_with_winner": 0,
                "influence_score_sum": 0.0,
            }
            for key in _AGENT_GROUPS
        }
        groups["advanced_match_intelligence"] = {
            "layer": "advanced_match_intelligence",
            "recommendation_count": 0,
            "available_count": 0,
            "alignment_with_winner": 0,
            "influence_score_sum": 0.0,
        }
        groups["player_intelligence"] = {
            "layer": "player_intelligence",
            "recommendation_count": 0,
            "available_count": 0,
            "alignment_with_winner": 0,
            "influence_score_sum": 0.0,
        }
        groups["provider_fusion"] = {
            "layer": "provider_fusion",
            "recommendation_count": 0,
            "available_count": 0,
            "alignment_with_winner": 0,
            "influence_score_sum": 0.0,
        }

        for ev in eval_rows:
            if str(ev.get("market_1x2_status") or "").lower() not in {"correct", "wrong"}:
                continue
            won = str(ev.get("market_1x2_status")).lower() == "correct"
            stored = repo.get_worldcup_stored_prediction(int(ev["fixture_id"]))
            payload = _parse_payload(stored) if stored else {}
            agents = (payload.get("specialist_summary") or {}).get("agents") or {}
            if not isinstance(agents, dict):
                agents = {}

            pu = (payload.get("provider_utilization_v1") or payload.get("supplemental_sources") or {})
            if isinstance(pu, dict) and pu.get("provider_utilization_v1"):
                pu = pu.get("provider_utilization_v1") or pu

            for layer, agent_names in _AGENT_GROUPS.items():
                g = groups[layer]
                for name in agent_names:
                    row = agents.get(name)
                    if not isinstance(row, dict):
                        continue
                    status = str(row.get("status") or "").lower()
                    if status not in {"available", "partial"}:
                        continue
                    g["available_count"] += 1
                    g["recommendation_count"] += 1
                    impact = float(row.get("impact_score") or 0)
                    g["influence_score_sum"] += impact
                    if won and impact >= 50:
                        g["alignment_with_winner"] += 1

            if isinstance(pu, dict):
                for layer_key, block_key in (
                    ("advanced_match_intelligence", "advanced_match_intelligence"),
                    ("player_intelligence", "player_intelligence"),
                    ("provider_fusion", "provider_utilization_v1"),
                ):
                    block = pu.get(block_key) if block_key != "provider_utilization_v1" else pu
                    if not isinstance(block, dict) or not block:
                        continue
                    g = groups[layer_key if layer_key != "provider_fusion" else "provider_fusion"]
                    g["available_count"] += 1
                    g["recommendation_count"] += 1
                    score = float(block.get("attacking_edge") or block.get("odds_movement_score") or 50)
                    g["influence_score_sum"] += score
                    if won:
                        g["alignment_with_winner"] += 1

        out_layers: list[dict[str, Any]] = []
        for g in groups.values():
            n = int(g["recommendation_count"] or 0)
            avg_influence = round(g["influence_score_sum"] / n, 2) if n else 0.0
            align_rate = round(g["alignment_with_winner"] / n, 4) if n else None
            out_layers.append(
                {
                    **g,
                    "avg_influence_score": avg_influence,
                    "alignment_rate": align_rate,
                }
            )
        return {"updated_at": _utc_now_iso(), "layers": out_layers}
    finally:
        repo.close()


def _trend_from_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    days: int | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if days is not None:
        cutoff = now - timedelta(days=days)
        filtered = [
            s
            for s in snapshots
            if s.get("snapshot_at") and datetime.fromisoformat(str(s["snapshot_at"])[:19]) >= cutoff
        ]
    else:
        filtered = list(snapshots)

    if not filtered:
        return {"period_days": days, "sample_snapshots": 0, "winrate": None, "evaluated_count": 0}

    latest = filtered[-1]
    earliest = filtered[0]
    return {
        "period_days": days,
        "sample_snapshots": len(filtered),
        "winrate": latest.get("overall_winrate"),
        "evaluated_count": latest.get("evaluated_count"),
        "correct_count": latest.get("correct_count"),
        "wrong_count": latest.get("wrong_count"),
        "delta_winrate": (
            round(float(latest.get("overall_winrate") or 0) - float(earliest.get("overall_winrate") or 0), 4)
            if latest.get("overall_winrate") is not None and earliest.get("overall_winrate") is not None
            else None
        ),
        "from": earliest.get("snapshot_at"),
        "to": latest.get("snapshot_at"),
    }


def build_market_leaderboard(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = [m for m in markets if m.get("winrate") is not None and int(m.get("sample_size") or 0) > 0]
    ranked.sort(
        key=lambda m: (float(m["winrate"]), int(m.get("sample_size") or 0)),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for rank, m in enumerate(ranked, start=1):
        rel = m.get("reliability") or m.get("reliability_level") or reliability_level(int(m.get("sample_size") or 0))
        out.append({**m, "rank": rank, "reliability": rel})
    return out


def capture_performance_snapshot(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a point-in-time production accuracy snapshot."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    try:
        if summary is None:
            summary = rebuild_accuracy_summary(settings=settings, competition_key=competition_key)

        evaluated = int(summary.get("evaluated_predictions") or 0)
        correct = int(summary.get("correct") or 0)
        wrong = int(summary.get("wrong") or 0)
        pending = int(summary.get("pending") or 0)
        stored_preds = repo.count_worldcup_stored_predictions(competition_key=competition_key)

        markets = _market_blocks_from_summary(summary)
        rule_a = compute_rule_a_impact(settings=settings, competition_key=competition_key)
        agents = compute_agent_contribution(settings=settings, competition_key=competition_key)

        overall = summary.get("winrate")
        if overall is None and evaluated > 0:
            overall = round(correct / evaluated, 4)

        snapshot = {
            "competition_key": competition_key,
            "snapshot_at": _utc_now_iso(),
            "evaluated_count": evaluated,
            "correct_count": correct,
            "wrong_count": wrong,
            "pending_count": pending,
            "stored_predictions": stored_preds,
            "overall_winrate": overall,
            "markets": markets,
            "rule_a": rule_a,
            "agent_contribution": agents,
        }

        repo.insert_performance_snapshot(
            competition_key=competition_key,
            snapshot_at=snapshot["snapshot_at"],
            evaluated_count=evaluated,
            correct_count=correct,
            wrong_count=wrong,
            pending_count=pending,
            overall_winrate=overall,
            markets_json=json.dumps(markets, ensure_ascii=False),
            rule_a_json=json.dumps(rule_a, ensure_ascii=False),
            agent_contribution_json=json.dumps(agents, ensure_ascii=False),
        )
        return snapshot
    finally:
        repo.close()


def build_monitoring_bundle(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    """Aggregate trends, leaderboard, Rule A, and agent stats for Performance Center V2."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    try:
        snapshots = repo.list_performance_snapshots(competition_key=competition_key, limit=500)
        latest_rule_a = compute_rule_a_impact(settings=settings, competition_key=competition_key)
        latest_agents = compute_agent_contribution(settings=settings, competition_key=competition_key)

        if snapshots:
            try:
                markets = json.loads(snapshots[-1].get("markets_json") or "[]")
            except json.JSONDecodeError:
                markets = []

        if not markets:
            summary = repo.get_worldcup_accuracy_summary(competition_key=competition_key)
            if summary:
                markets = _market_blocks_from_summary(summary)

        leaderboard = build_market_leaderboard(markets)
        return {
            "accuracy_trends": {
                "last_7_days": _trend_from_snapshots(snapshots, days=7),
                "last_30_days": _trend_from_snapshots(snapshots, days=30),
                "all_time": _trend_from_snapshots(snapshots, days=None),
            },
            "market_leaderboard": leaderboard,
            "rule_a_monitoring": latest_rule_a,
            "agent_contribution": latest_agents,
            "snapshot_count": len(snapshots),
        }
    finally:
        repo.close()
