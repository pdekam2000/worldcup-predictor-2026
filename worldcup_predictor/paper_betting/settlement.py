"""Paper bet settlement from archive evaluations — Phase A18."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.api.archive_evaluation_join import is_quarantined_evaluation, normalize_eval_status
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.paper_betting.constants import (
    BET_STATUS_LOST,
    BET_STATUS_PARTIAL,
    BET_STATUS_PENDING,
    BET_STATUS_VOID,
    BET_STATUS_WON,
    MARKET_EVAL_COLUMN,
)
from worldcup_predictor.paper_betting.store import PaperBettingStore


def _eval_status_for_market(evaluation: dict[str, Any] | None, market: str) -> str:
    if not evaluation or is_quarantined_evaluation(evaluation):
        return "pending"
    col = MARKET_EVAL_COLUMN.get(str(market or "").lower().replace("-", "_"))
    if not col:
        for key, c in MARKET_EVAL_COLUMN.items():
            if key in str(market or "").lower():
                col = c
                break
    if not col:
        col = "market_1x2_status"
    return normalize_eval_status(evaluation.get(col))


def _map_eval_to_bet_status(eval_status: str) -> str:
    if eval_status == "correct":
        return BET_STATUS_WON
    if eval_status == "wrong":
        return BET_STATUS_LOST
    if eval_status == "partial":
        return BET_STATUS_PARTIAL
    return BET_STATUS_PENDING


def compute_profit_loss(
    *,
    bet_status: str,
    stake: float,
    odds_decimal: float | None,
) -> tuple[float | None, float | None, str]:
    """Returns (profit_loss, payout, reason)."""
    stake = float(stake)
    if bet_status == BET_STATUS_WON:
        if odds_decimal and float(odds_decimal) > 1:
            payout = round(stake * float(odds_decimal), 2)
            profit = round(payout - stake, 2)
            return profit, payout, "won_with_odds"
        return None, stake, "won_profit_unavailable_no_odds"
    if bet_status == BET_STATUS_LOST:
        return round(-stake, 2), 0.0, "lost"
    if bet_status == BET_STATUS_PARTIAL:
        if odds_decimal and float(odds_decimal) > 1:
            half_profit = round(stake * 0.5 * (float(odds_decimal) - 1), 2)
            return half_profit, round(stake + half_profit, 2), "partial_half_stake"
        return 0.0, stake, "partial_no_odds"
    if bet_status == BET_STATUS_VOID:
        return 0.0, stake, "void"
    return None, None, "still_pending"


def settle_pending_bets(
    store: PaperBettingStore | None = None,
    *,
    user_id: str | None = None,
    repo: FootballIntelligenceRepository | None = None,
) -> dict[str, Any]:
    store = store or PaperBettingStore()
    repo = repo or FootballIntelligenceRepository(store.settings.sqlite_path or None)
    pending = store.list_pending_bets(user_id=user_id)
    settled = 0
    still_pending = 0
    errors = 0

    eval_cache: dict[int, dict[str, Any] | None] = {}

    for bet in pending:
        fid = int(bet["fixture_id"])
        if fid not in eval_cache:
            row = repo._conn.execute(  # noqa: SLF001
                "SELECT * FROM worldcup_prediction_evaluations WHERE fixture_id = ?",
                (fid,),
            ).fetchone()
            eval_cache[fid] = dict(row) if row else None

        evaluation = eval_cache[fid]
        eval_st = _eval_status_for_market(evaluation, bet.get("market") or "")
        bet_status = _map_eval_to_bet_status(eval_st)
        if bet_status == BET_STATUS_PENDING:
            still_pending += 1
            continue

        stake = float(bet.get("stake") or 0)
        odds = float(bet["odds_decimal"]) if bet.get("odds_decimal") else None
        profit, payout, reason = compute_profit_loss(
            bet_status=bet_status,
            stake=stake,
            odds_decimal=odds,
        )

        account = store.get_account(bet["user_id"])
        if account:
            balance = float(account["current_bankroll"])
            if bet_status == BET_STATUS_WON and payout is not None:
                balance = round(balance + payout, 2)
            elif bet_status == BET_STATUS_PARTIAL and payout is not None:
                balance = round(balance + payout, 2)
            elif bet_status == BET_STATUS_VOID:
                balance = round(balance + stake, 2)
            store.update_bankroll(int(account["id"]), balance)

        store.settle_bet(
            int(bet["id"]),
            user_id=bet["user_id"],
            status=bet_status,
            profit_loss=profit,
            payout=payout,
            odds_used=odds,
            evaluation_source="worldcup_prediction_evaluations",
            reason=reason,
        )
        settled += 1

    return {
        "status": "ok",
        "settled": settled,
        "still_pending": still_pending,
        "errors": errors,
        "scanned": len(pending),
    }
