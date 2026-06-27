"""Alert detectors from PredOps, Betting Plan, Paper Betting — Phase A19 (read-only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.ai_assistant.rules import (
    build_dedup_key,
    is_meaningful_odds_movement,
    is_meaningful_quality_change,
    passes_quality_threshold,
    should_notify_user,
)
from worldcup_predictor.ai_assistant.store import AssistantStore
from worldcup_predictor.predops.store import PredOpsStore
from worldcup_predictor.publication.bet_quality_overlay import build_publication_overlay


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _best_quality_from_snapshot(snapshot: dict[str, Any]) -> tuple[float | None, str | None]:
    payload = snapshot.get("payload") or {}
    if isinstance(payload, str):
        import json

        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    overlay = build_publication_overlay(payload)
    markets = overlay.get("markets") or []
    best_score = None
    best_market = None
    for m in markets:
        q = m.get("bet_quality_score")
        if q is None:
            continue
        try:
            score = float(q)
        except (TypeError, ValueError):
            continue
        if best_score is None or score > best_score:
            best_score = score
            best_market = m.get("market")
    return best_score, best_market


def _match_watchlist(
    watchlist: list[dict[str, Any]],
    *,
    fixture_id: int,
    competition_key: str | None,
    home_team: str | None,
    away_team: str | None,
) -> bool:
    if not watchlist:
        return False
    for item in watchlist:
        itype = item.get("item_type")
        iid = str(item.get("item_id", "")).lower()
        if itype == "fixture" and iid == str(fixture_id):
            return True
        if itype == "competition" and competition_key and iid == competition_key.lower():
            return True
        if itype == "team":
            ht = (home_team or "").lower()
            at = (away_team or "").lower()
            if iid in (ht, at):
                return True
    return False


def detect_snapshot_alerts(
    store: AssistantStore,
    user_id: str,
    *,
    fixture_id: int,
    snapshot: dict[str, Any],
    prefs: dict[str, Any],
    watchlist: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _match_watchlist(
        watchlist,
        fixture_id=fixture_id,
        competition_key=snapshot.get("competition_key"),
        home_team=(snapshot.get("payload") or {}).get("home_team") if isinstance(snapshot.get("payload"), dict) else None,
        away_team=(snapshot.get("payload") or {}).get("away_team") if isinstance(snapshot.get("payload"), dict) else None,
    ):
        return []

    created: list[dict[str, Any]] = []
    snap_id = snapshot.get("snapshot_id")
    scope = f"fixture:{fixture_id}"
    prev_state = store.get_alert_state(scope)
    prev_snap_id = prev_state.get("last_snapshot_id") if prev_state else None

    if prev_snap_id == snap_id:
        return []

    new_score, new_market = _best_quality_from_snapshot(snapshot)
    old_score = None
    old_market = None
    if prev_state and prev_state.get("last_value"):
        parts = str(prev_state["last_value"]).split("|")
        if parts:
            try:
                old_score = float(parts[0])
            except ValueError:
                pass
        if len(parts) > 1:
            old_market = parts[1]

    if not passes_quality_threshold(prefs, new_score):
        store.set_alert_state(scope, last_value=f"{new_score or 0}|{new_market or ''}", last_snapshot_id=snap_id)
        return []

    # Prediction ready
    coverage = snapshot.get("coverage_state")
    if coverage == "completed" and prev_state is None:
        if should_notify_user(prefs, alert_type="prediction_ready"):
            n = store.create_notification(
                user_id,
                category="prediction",
                alert_type="prediction_ready",
                fixture_id=fixture_id,
                title="Fixture prediction ready",
                message=f"Fixture {fixture_id} is now prediction ready.",
                new_value=str(fixture_id),
                reason="coverage_completed",
                link=f"/matches/{fixture_id}",
                dedup_key=build_dedup_key("prediction_ready", fixture_id),
            )
            if n:
                created.append(n)

    # Quality changes
    if is_meaningful_quality_change(old_score, new_score) and new_score is not None:
        alert_type = "quality_increase" if (old_score is None or new_score > old_score) else "quality_decrease"
        if should_notify_user(prefs, alert_type=alert_type):
            n = store.create_notification(
                user_id,
                category="quality",
                alert_type=alert_type,
                fixture_id=fixture_id,
                title=f"Bet quality {'increased' if alert_type == 'quality_increase' else 'decreased'}",
                message=f"Quality moved from {old_score or 'n/a'} to {new_score:.0f} on {new_market or 'market'}.",
                old_value=str(old_score) if old_score is not None else None,
                new_value=str(new_score),
                reason="predops_snapshot_delta",
                link=f"/matches/{fixture_id}",
                dedup_key=build_dedup_key(alert_type, fixture_id, f"{int(new_score)}"),
            )
            if n:
                created.append(n)

    # Best pick change
    if old_market and new_market and old_market != new_market:
        if should_notify_user(prefs, alert_type="best_pick_change"):
            n = store.create_notification(
                user_id,
                category="prediction",
                alert_type="best_pick_change",
                fixture_id=fixture_id,
                title="Best pick changed",
                message=f"Top market shifted from {old_market} to {new_market}.",
                old_value=old_market,
                new_value=new_market,
                reason="market_rank_change",
                link=f"/matches/{fixture_id}",
                dedup_key=build_dedup_key("best_pick_change", fixture_id, new_market),
            )
            if n:
                created.append(n)

    # EGIE / deltas from snapshot
    deltas = snapshot.get("deltas")
    if isinstance(deltas, str):
        import json

        try:
            deltas = json.loads(deltas)
        except json.JSONDecodeError:
            deltas = {}
    if isinstance(deltas, dict):
        changed = deltas.get("changed_markets") or []
        if changed and should_notify_user(prefs, alert_type="egie_prediction_change"):
            n = store.create_notification(
                user_id,
                category="prediction",
                alert_type="egie_prediction_change",
                fixture_id=fixture_id,
                title="Prediction update",
                message=f"Markets updated: {', '.join(changed[:5])}.",
                new_value=",".join(changed[:10]),
                reason="snapshot_delta",
                link=f"/matches/{fixture_id}",
                dedup_key=build_dedup_key("egie_prediction_change", fixture_id, snap_id or ""),
            )
            if n:
                created.append(n)

        lineup_delta = deltas.get("lineup_delta")
        if lineup_delta and should_notify_user(prefs, alert_type="lineup_published"):
            n = store.create_notification(
                user_id,
                category="prediction",
                alert_type="lineup_published",
                fixture_id=fixture_id,
                title="Lineups published",
                message=f"Lineup data available for fixture {fixture_id}.",
                reason="lineup_delta",
                link=f"/matches/{fixture_id}",
                dedup_key=build_dedup_key("lineup_published", fixture_id),
            )
            if n:
                created.append(n)

    # Final 3 hours
    kickoff = _parse_dt(snapshot.get("kickoff_utc"))
    if kickoff:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        hours_left = (kickoff - now).total_seconds() / 3600
        if 0 < hours_left <= 3:
            if should_notify_user(prefs, alert_type="match_final_hours"):
                n = store.create_notification(
                    user_id,
                    category="system",
                    alert_type="match_final_hours",
                    fixture_id=fixture_id,
                    title="Match starts soon",
                    message=f"Fixture {fixture_id} kicks off in under 3 hours.",
                    reason="kickoff_window",
                    link=f"/matches/{fixture_id}",
                    dedup_key=build_dedup_key("match_final_hours", fixture_id),
                )
                if n:
                    created.append(n)

    store.set_alert_state(
        scope,
        last_value=f"{new_score or 0}|{new_market or ''}",
        last_snapshot_id=snap_id,
    )
    return created


def detect_combo_alerts(
    store: AssistantStore,
    user_id: str,
    *,
    combos: list[dict[str, Any]],
    prefs: dict[str, Any],
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    min_combo = (prefs.get("min_combo_type") or "balanced").lower()
    rank = {"safe": 3, "balanced": 2, "value": 1, "aggressive": 0}
    min_rank = rank.get(min_combo, 2)

    for combo in combos:
        ctype = (combo.get("combo_type") or combo.get("type") or "").lower()
        if rank.get(ctype, 0) < min_rank:
            continue
        if ctype != "safe":
            continue
        combo_id = combo.get("combo_id") or combo.get("id") or ctype
        if should_notify_user(prefs, alert_type="safe_combo_available"):
            n = store.create_notification(
                user_id,
                category="combo",
                alert_type="safe_combo_available",
                fixture_id=None,
                title="New safe combo available",
                message=combo.get("label") or f"Safe combo ready ({len(combo.get('legs') or [])} legs).",
                new_value=str(combo_id),
                reason="betting_plan_combo",
                link="/combo-tips",
                dedup_key=build_dedup_key("safe_combo_available", None, str(combo_id)),
            )
            if n:
                created.append(n)
    return created


def detect_paper_betting_alerts(
    store: AssistantStore,
    user_id: str,
    *,
    settlement_result: dict[str, Any],
    prefs: dict[str, Any],
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    settled = settlement_result.get("settled") or 0
    if settled <= 0:
        return []

    from worldcup_predictor.ai_assistant.constants import DRAWDOWN_WARNING_PCT, ROI_MILESTONE_STEPS
    from worldcup_predictor.paper_betting.analytics import build_summary
    from worldcup_predictor.paper_betting.store import PaperBettingStore

    pb_store = PaperBettingStore()
    summary = build_summary(pb_store, user_id, period="month")
    roi = float(summary.get("roi_pct") or 0)
    profit = float(summary.get("profit_loss") or 0)

    if should_notify_user(prefs, alert_type="paper_bet_settled"):
        n = store.create_notification(
            user_id,
            category="paper_betting",
            alert_type="paper_bet_settled",
            fixture_id=None,
            title="Virtual bet settled",
            message=f"{settled} paper bet(s) settled. Month P/L: {profit:+.2f}.",
            new_value=str(settled),
            reason="paper_settlement",
            link="/paper-betting",
            dedup_key=build_dedup_key("paper_bet_settled", None, _today_key()),
        )
        if n:
            created.append(n)

    for step in ROI_MILESTONE_STEPS:
        if roi >= step:
            dk = build_dedup_key("roi_milestone", None, f"{step}")
            n = store.create_notification(
                user_id,
                category="paper_betting",
                alert_type="roi_milestone",
                fixture_id=None,
                title=f"ROI milestone: {step}%",
                message=f"Virtual portfolio reached {roi:.1f}% ROI this month.",
                new_value=str(roi),
                reason="roi_milestone",
                link="/paper-betting",
                dedup_key=dk,
            )
            if n:
                created.append(n)
                break

    starting = float(summary.get("starting_bankroll") or 0)
    current = float(summary.get("current_bankroll") or 0)
    if starting > 0:
        drawdown = (starting - current) / starting * 100
        if drawdown >= DRAWDOWN_WARNING_PCT and profit < 0:
            n = store.create_notification(
                user_id,
                category="paper_betting",
                alert_type="drawdown_warning",
                fixture_id=None,
                title="Drawdown warning",
                message=f"Virtual bankroll down {drawdown:.1f}% from starting balance.",
                new_value=str(round(drawdown, 1)),
                reason="drawdown_threshold",
                link="/paper-betting",
                dedup_key=build_dedup_key("drawdown_warning", None, _today_key()),
            )
            if n:
                created.append(n)

    return created


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def scan_user_fixtures(
    store: AssistantStore,
    predops: PredOpsStore,
    user_id: str,
    watchlist: list[dict[str, Any]],
    prefs: dict[str, Any],
) -> list[dict[str, Any]]:
    fixture_ids: set[int] = set()
    for item in watchlist:
        if item.get("item_type") == "fixture":
            try:
                fixture_ids.add(int(item["item_id"]))
            except (TypeError, ValueError):
                pass

    # Also scan today's fixtures for watched competitions/teams via recent snapshots
    rows = predops._conn.execute(  # noqa: SLF001
        """
        SELECT DISTINCT fixture_id FROM predops_snapshots
        WHERE is_latest = 1 AND kickoff_utc >= date('now')
        ORDER BY kickoff_utc LIMIT 50
        """,
    ).fetchall()
    for row in rows:
        fixture_ids.add(int(row[0]))

    created: list[dict[str, Any]] = []
    for fid in fixture_ids:
        snap = predops.get_latest_snapshot(fid)
        if not snap:
            continue
        created.extend(
            detect_snapshot_alerts(store, user_id, fixture_id=fid, snapshot=snap, prefs=prefs, watchlist=watchlist)
        )
    return created
