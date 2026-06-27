"""Market-level prediction evaluation — read-only display & scoring helpers (Hotfix)."""

from __future__ import annotations

import json
from typing import Any, Literal

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome

EvalStatus = Literal["correct", "wrong", "pending", "unavailable", "unknown", "void"]

# Canonical keys exposed to UI filters.
PUBLIC_MARKET_FILTERS: tuple[str, ...] = (
    "best_bets",
    "1x2",
    "btts",
    "over_under_2_5",
    "over_2_5",
    "under_2_5",
    "double_chance",
    "correct_score",
    "first_goal_team",
    "goal_minute",
    "goalscorer",
    "ht_result",
)

MARKET_LABELS: dict[str, str] = {
    "1x2": "1X2",
    "btts": "BTTS",
    "over_under_0_5": "Over/Under 0.5",
    "over_under_1_5": "Over/Under 1.5",
    "over_under_2_5": "Over/Under 2.5",
    "over_2_5": "Over/Under 2.5",
    "under_2_5": "Under 2.5",
    "over_under_3_5": "Over/Under 3.5",
    "double_chance": "Double Chance",
    "correct_score": "Correct Score",
    "first_goal_team": "First Goal Team",
    "goal_minute": "Goal Time Range",
    "goalscorer": "Goalscorer",
    "ht_result": "Half Time Result",
}


def canonical_1x2_selection(payload: dict[str, Any]) -> str | None:
    """Single source for 1X2 — matches archive display (_main_prediction)."""
    pred = payload.get("prediction") or payload.get("one_x_two")
    if pred:
        return str(pred)
    dm = payload.get("detailed_markets") if isinstance(payload.get("detailed_markets"), dict) else {}
    mw = dm.get("match_winner") if isinstance(dm.get("match_winner"), dict) else {}
    if mw.get("selection"):
        return str(mw["selection"])
    return None


def _dm_block(payload: dict[str, Any], key: str) -> dict[str, Any]:
    dm = payload.get("detailed_markets") if isinstance(payload.get("detailed_markets"), dict) else {}
    block = dm.get(key)
    return block if isinstance(block, dict) else {}


def _prob_block(payload: dict[str, Any], key: str) -> dict[str, Any]:
    probs = payload.get("probabilities") if isinstance(payload.get("probabilities"), dict) else {}
    block = probs.get(key)
    return block if isinstance(block, dict) else {}


def _selection_from_blocks(*blocks: dict[str, Any] | None) -> str | None:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        sel = block.get("selection") or block.get("pick") or block.get("team") or block.get("player")
        if sel is not None and str(sel).strip():
            return str(sel)
    return None


def ou_selection_from_payload(payload: dict[str, Any], *, line: str = "2_5") -> str | None:
    key = f"over_under_{line}"
    dm_key = key if line != "2_5" else "over_under_25"
    return _selection_from_blocks(_dm_block(payload, dm_key), _prob_block(payload, key))


def btts_selection_from_payload(payload: dict[str, Any]) -> str | None:
    return _selection_from_blocks(_dm_block(payload, "btts"), _prob_block(payload, "btts"))


def double_chance_selection_from_payload(payload: dict[str, Any]) -> str | None:
    dc = _dm_block(payload, "double_chance")
    if not dc:
        return None
    if dc.get("selection"):
        return str(dc["selection"])
    best = max(
        [
            ("home_or_draw", dc.get("home_or_draw")),
            ("draw_or_away", dc.get("draw_or_away")),
            ("home_or_away", dc.get("home_or_away")),
        ],
        key=lambda x: float(x[1] or 0),
    )
    return best[0] if float(best[1] or 0) > 0 else None


def _normalize_market_key(raw: str | None) -> str | None:
    if not raw:
        return None
    key = str(raw).lower().strip().replace("-", "_").replace(" ", "_")
    aliases = {
        "match_winner": "1x2",
        "1x2": "1x2",
        "over_under_25": "over_under_2_5",
        "over_under_2_5": "over_under_2_5",
        "over_2_5": "over_under_2_5",
        "under_2_5": "over_under_2_5",
        "both_teams_to_score": "btts",
        "first_team_to_score": "first_goal_team",
        "goal_timing": "goal_minute",
        "half_time": "ht_result",
        "halftime": "ht_result",
    }
    return aliases.get(key, key)


def market_key_from_pick(pick: dict[str, Any] | None) -> str | None:
    if not isinstance(pick, dict):
        return None
    mk = pick.get("market_key") or pick.get("market")
    resolved = _normalize_market_key(str(mk) if mk else None)
    if resolved:
        return resolved
    sel = str(pick.get("selection") or pick.get("pick") or "").lower()
    if "double chance" in sel or sel in {"1x", "x2", "12", "home_or_draw", "draw_or_away", "home_or_away"}:
        return "double_chance"
    if "btts" in sel or sel in {"yes", "no", "btts_yes", "btts_no"}:
        return "btts"
    if "over" in sel or "under" in sel:
        return "over_under_2_5"
    if sel in {"home", "draw", "away", "home_win", "away_win"}:
        return "1x2"
    return None


def resolve_best_bet_market_keys(payload: dict[str, Any]) -> set[str]:
    if bool(payload.get("no_bet")):
        return set()
    pick = payload.get("best_available_pick") or payload.get("user_visible_pick")
    if not isinstance(pick, dict):
        return set()
    mk = market_key_from_pick(pick)
    return {mk} if mk else set()


def is_user_visible_prediction(payload: dict[str, Any]) -> bool:
    if bool(payload.get("no_bet")):
        return False
    tracking = payload.get("accuracy_tracking") if isinstance(payload.get("accuracy_tracking"), dict) else {}
    if tracking.get("shadow") or tracking.get("admin_only") or tracking.get("research_only"):
        return False
    source = str(payload.get("source") or payload.get("generated_by") or "").lower()
    if "shadow" in source or source == "research":
        return False
    return True


def extract_predicted_markets(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Markets explicitly present in stored payload (no fabrication)."""
    out: dict[str, dict[str, Any]] = {}
    dm = payload.get("detailed_markets") if isinstance(payload.get("detailed_markets"), dict) else {}

    def _add(key: str, selection: str | None, *, prob: Any = None, conf: Any = None, extra: dict | None = None) -> None:
        if not selection:
            return
        block = {"predicted_pick": selection, "probability": prob, "confidence": conf}
        if extra:
            block.update(extra)
        out[key] = block

    if canonical_1x2_selection(payload):
        mw = _dm_block(payload, "match_winner")
        _add("1x2", canonical_1x2_selection(payload), prob=mw.get("probability"), conf=payload.get("confidence"))

    btts_sel = btts_selection_from_payload(payload)
    if btts_sel:
        b = _dm_block(payload, "btts")
        _add("btts", btts_sel, prob=b.get("probability"))

    for line, dm_key in (
        ("0_5", "over_under_05"),
        ("1_5", "over_under_15"),
        ("2_5", "over_under_25"),
        ("3_5", "over_under_35"),
    ):
        sel = ou_selection_from_payload(payload, line=line)
        if sel:
            b = _dm_block(payload, dm_key)
            _add(f"over_under_{line}", sel, prob=b.get("probability"))

    dc_sel = double_chance_selection_from_payload(payload)
    if dc_sel:
        _add("double_chance", dc_sel)

    cs = dm.get("correct_scores")
    if isinstance(cs, dict) and (cs.get("selection") or cs.get("label")):
        _add("correct_score", str(cs.get("selection") or cs.get("label")))
    elif isinstance(cs, list) and cs:
        top = cs[0] if isinstance(cs[0], dict) else None
        if top and (top.get("label") or top.get("scoreline")):
            _add("correct_score", str(top.get("label") or top.get("scoreline")))

    fg = dm.get("first_goal") if isinstance(dm.get("first_goal"), dict) else {}
    if fg.get("team"):
        _add("first_goal_team", str(fg["team"]), conf=fg.get("confidence"))
    if fg.get("minute_range") or fg.get("expected_minute"):
        _add(
            "goal_minute",
            str(fg.get("minute_range") or fg.get("expected_minute")),
            conf=fg.get("confidence"),
        )

    ht = dm.get("halftime") if isinstance(dm.get("halftime"), dict) else {}
    if ht.get("selection"):
        _add("ht_result", str(ht["selection"]), prob=ht.get("probability"))

    gs = dm.get("goalscorer") if isinstance(dm.get("goalscorer"), dict) else {}
    if gs.get("player"):
        _add("goalscorer", str(gs["player"]), conf=gs.get("confidence"))

    return out


def _status_from_eval(raw: str | None) -> EvalStatus:
    value = str(raw or "").lower().strip()
    if value in {"correct", "wrong", "pending", "unavailable"}:
        return value  # type: ignore[return-value]
    if value in {"unknown", "void", ""}:
        return "unavailable"
    return "pending"


def _display_pick(market_key: str, pick: str | None) -> str:
    if not pick:
        return "—"
    p = str(pick).lower()
    if market_key == "1x2":
        if p in {"home", "home_win"}:
            return "Home Win"
        if p == "draw":
            return "Draw"
        if p in {"away", "away_win"}:
            return "Away Win"
    if market_key == "btts":
        return "Yes" if p in {"yes", "btts_yes"} else "No" if p in {"no", "btts_no"} else pick
    if market_key.startswith("over_under"):
        return pick.replace("_", " ").title()
    return pick


def build_market_evaluation_rows(
    payload: dict[str, Any],
    outcome: FixtureOutcome,
    *,
    market_statuses: dict[str, str],
    advanced_markets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build per-market evaluation rows for API/UI (no payload mutation)."""
    predicted = extract_predicted_markets(payload)
    best_bet_keys = resolve_best_bet_market_keys(payload)
    user_visible = is_user_visible_prediction(payload)
    finished = bool(outcome.is_finished)
    actual = outcome.actual_result
    rows: list[dict[str, Any]] = []

    status_map = dict(market_statuses)
    adv = advanced_markets or {}
    for adv_key, block in adv.items():
        if isinstance(block, dict) and block.get("status"):
            canon = _normalize_market_key(adv_key) or adv_key
            status_map[canon] = str(block["status"])

    for market_key, pred in predicted.items():
        raw_status = status_map.get(market_key, "pending" if not finished else "unavailable")
        status = _status_from_eval(raw_status)
        if not finished:
            status = "pending"
            reason = "fixture_not_finished"
        elif status == "unavailable":
            reason = "not_evaluated"
        elif status in {"correct", "wrong"}:
            reason = "match_finished"
        else:
            reason = "pending_evaluation"

        is_correct: bool | None = True if status == "correct" else False if status == "wrong" else None
        pick = pred.get("predicted_pick")
        rows.append(
            {
                "market_key": market_key,
                "market_label": MARKET_LABELS.get(market_key, market_key.replace("_", " ").title()),
                "predicted_pick": pick,
                "display_pick": _display_pick(market_key, pick),
                "actual_result": actual,
                "is_correct": is_correct,
                "status": status,
                "confidence": pred.get("confidence"),
                "probability": pred.get("probability"),
                "tier": payload.get("pick_tier") or (
                    (payload.get("accuracy_tracking") or {}).get("pick_tier")
                ),
                "was_best_bet": market_key in best_bet_keys,
                "was_user_visible": user_visible,
                "evaluation_reason": reason,
                "odds": pred.get("odds"),
            }
        )

    return rows


def market_rows_from_evaluation(
    eval_row: dict[str, Any] | None,
    payload: dict[str, Any],
    outcome: FixtureOutcome,
) -> list[dict[str, Any]]:
    """Load market rows from detail_json or rebuild from stored columns."""
    if not eval_row:
        return []
    detail: dict[str, Any] = {}
    raw = eval_row.get("detail_json")
    if raw:
        try:
            detail = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError):
            detail = {}
    if isinstance(detail.get("market_evaluations"), list) and detail["market_evaluations"]:
        return detail["market_evaluations"]

    from worldcup_predictor.api.archive_evaluation_join import market_statuses_from_evaluation_row

    statuses = market_statuses_from_evaluation_row(eval_row)
    adv = detail.get("advanced_markets") if isinstance(detail.get("advanced_markets"), dict) else {}
    return build_market_evaluation_rows(
        payload,
        outcome,
        market_statuses=statuses,
        advanced_markets=adv,
    )


def count_evaluation_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    correct = wrong = pending = unavailable = 0
    for row in rows:
        st = str(row.get("status") or "pending").lower()
        if st == "correct":
            correct += 1
        elif st == "wrong":
            wrong += 1
        elif st == "unavailable":
            unavailable += 1
        else:
            pending += 1
    evaluated = correct + wrong
    return {
        "evaluated_markets_count": evaluated,
        "correct_markets_count": correct,
        "wrong_markets_count": wrong,
        "pending_markets_count": pending,
        "unavailable_markets_count": unavailable,
        "total_markets_tracked": len(rows),
    }


def compute_aggregate_card_status(
    rows: list[dict[str, Any]],
    *,
    scope: str = "visible",
) -> tuple[str, str]:
    """Card-level status — Partial when mixed; Unavailable when no predictions."""
    if not rows:
        return "unavailable", "no_predicted_markets"

    filtered = rows
    if scope == "visible":
        filtered = [r for r in rows if r.get("was_user_visible", True)]
    elif scope == "best_bet":
        filtered = [r for r in rows if r.get("was_best_bet")]

    if not filtered:
        return "unavailable", "no_markets_in_scope"

    settled = [r for r in filtered if r.get("status") in {"correct", "wrong"}]
    if not settled:
        if any(r.get("status") == "pending" for r in filtered):
            return "pending", "fixture_not_finished_or_unevaluated"
        return "unavailable", "no_evaluated_markets"

    correct = sum(1 for r in settled if r.get("status") == "correct")
    wrong = sum(1 for r in settled if r.get("status") == "wrong")
    if correct > 0 and wrong > 0:
        return "partial", "mixed_market_results"
    if wrong > 0 and correct == 0:
        return "wrong", "all_evaluated_markets_wrong"
    if correct > 0 and wrong == 0:
        return "correct", "all_evaluated_markets_correct"
    return "pending", "markets_unsettled"


def limited_historical_payload(payload: dict[str, Any]) -> bool:
    keys = extract_predicted_markets(payload)
    return len(keys) <= 1 and "1x2" in keys


def compute_best_bet_winrate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Public winrate — best bets only, settled correct/wrong."""
    eligible = [
        r
        for r in rows
        if r.get("was_best_bet")
        and r.get("was_user_visible")
        and r.get("status") in {"correct", "wrong"}
        and not r.get("is_quarantined")
    ]
    correct = sum(1 for r in eligible if r.get("status") == "correct")
    total = len(eligible)
    accuracy = round((correct / total) * 100, 1) if total else 0.0
    return {"total": total, "correct": correct, "accuracy": accuracy}


def compute_archive_winrate_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate stats for archive header — separates best bet vs research."""
    best_rows: list[dict[str, Any]] = []
    research_rows: list[dict[str, Any]] = []
    card_counts = {"correct": 0, "wrong": 0, "partial": 0, "pending": 0, "unavailable": 0}

    for item in items:
        status = str(item.get("result_status") or "pending").lower()
        if status in card_counts:
            card_counts[status] += 1
        breakdown = item.get("market_breakdown") or []
        for row in breakdown:
            if row.get("was_best_bet") and row.get("was_user_visible"):
                best_rows.append({**row, "is_quarantined": item.get("is_quarantined")})
            elif row.get("was_user_visible"):
                research_rows.append(row)

    best = compute_best_bet_winrate(best_rows)
    research_settled = [r for r in research_rows if r.get("status") in {"correct", "wrong"}]
    research_correct = sum(1 for r in research_settled if r.get("status") == "correct")
    research_accuracy = (
        round((research_correct / len(research_settled)) * 100, 1) if research_settled else 0.0
    )

    return {
        "total": len(items),
        "correct": card_counts["correct"],
        "wrong": card_counts["wrong"],
        "partial": card_counts["partial"],
        "pending": card_counts["pending"],
        "unavailable": card_counts["unavailable"],
        "accuracy": best["accuracy"],
        "best_bet_winrate": best,
        "market_research_accuracy": {
            "total": len(research_settled),
            "correct": research_correct,
            "accuracy": research_accuracy,
        },
    }


def filter_market_key_for_api(market_filter: str | None) -> str | None:
    if not market_filter or market_filter in {"all", "*"}:
        return None
    return str(market_filter).lower().strip()


def row_matches_market_filter(item: dict[str, Any], market_filter: str | None) -> bool:
    mf = filter_market_key_for_api(market_filter)
    if not mf:
        return True
    if mf == "best_bets":
        breakdown = item.get("market_breakdown") or []
        return any(r.get("was_best_bet") and r.get("was_user_visible") for r in breakdown) or bool(
            item.get("has_best_bet")
        )
    breakdown = item.get("market_breakdown") or []
    keys = {str(r.get("market_key")) for r in breakdown}
    if mf in keys:
        return True
    if mf in {"over_2_5", "under_2_5"} and "over_under_2_5" in keys:
        return True
    return mf in set(item.get("predicted_market_keys") or [])


def market_view_for_row(item: dict[str, Any], market_filter: str | None) -> dict[str, Any] | None:
    """Primary market line for filtered list display."""
    mf = filter_market_key_for_api(market_filter)
    if not mf or mf == "best_bets":
        best = [r for r in (item.get("market_breakdown") or []) if r.get("was_best_bet")]
        return best[0] if best else None
    key = "over_under_2_5" if mf in {"over_2_5", "under_2_5"} else mf
    for row in item.get("market_breakdown") or []:
        if row.get("market_key") == key:
            if mf == "over_2_5" and "over" not in str(row.get("predicted_pick") or "").lower():
                continue
            if mf == "under_2_5" and "under" not in str(row.get("predicted_pick") or "").lower():
                continue
            return row
    return None


def attach_market_evaluations_to_result(
    evaluation: dict[str, Any],
    payload: dict[str, Any],
    outcome: FixtureOutcome,
) -> dict[str, Any]:
    """Add market_evaluations + card_status to evaluator output (stored in detail_json)."""
    markets = evaluation.get("markets") or {}
    rows = build_market_evaluation_rows(
        payload,
        outcome,
        market_statuses=markets,
        advanced_markets=evaluation.get("advanced_markets"),
    )
    card_status, card_reason = compute_aggregate_card_status(rows, scope="visible")
    evaluation = dict(evaluation)
    evaluation["market_evaluations"] = rows
    evaluation["card_status"] = card_status
    evaluation["card_status_reason"] = card_reason
    evaluation["limited_historical_payload"] = limited_historical_payload(payload)
    # Card status for lists — do not collapse to single failed secondary market.
    if card_status in {"correct", "wrong", "partial", "unavailable"}:
        evaluation["status"] = card_status
    return evaluation
