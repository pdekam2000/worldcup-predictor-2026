"""Budget allocation for main + insurance coupons (research-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.constants import DEFAULT_BUDGET


def _round_step(value: float, step: float) -> float:
    if step <= 0:
        return round(value, 2)
    return round(round(value / step) * step, 2)


def allocate_budget(
    *,
    n_main_tickets: int,
    n_insurance_tickets: int,
    insurance_scores: list[float] | None = None,
    budget_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Allocate total budget across main + insurance tickets.

    Modes:
      - equal
      - score_weighted (insurance only; main equal)
      - kelly_research (DISABLED by default; labeled research-only)
    Never presents profit as guaranteed.
    """
    cfg = {**DEFAULT_BUDGET, **(budget_cfg or {})}
    total = float(cfg["total_budget_eur"])
    main_ratio = float(cfg["main_budget_ratio"])
    ins_ratio = float(cfg["insurance_budget_ratio"])
    # Normalize ratios
    s = main_ratio + ins_ratio
    if s <= 0:
        main_ratio, ins_ratio = 0.8, 0.2
        s = 1.0
    main_ratio, ins_ratio = main_ratio / s, ins_ratio / s

    main_budget = round(total * main_ratio, 4)
    ins_budget = round(total * ins_ratio, 4)
    min_s = float(cfg["min_stake_per_ticket_eur"])
    max_s = float(cfg["max_stake_per_ticket_eur"])
    step = float(cfg["rounding_step_eur"])
    mode = str(cfg.get("stake_mode") or "equal").lower()
    kelly_enabled = bool(cfg.get("kelly_enabled", False)) and mode == "kelly_research"

    warning = (
        "Research-only budget allocation. Modeled EV/coverage is not guaranteed profit. "
        "Kelly mode is research-labeled and disabled by default."
    )

    n_main = max(0, int(n_main_tickets))
    n_ins = max(0, int(n_insurance_tickets))

    stake_main = 0.0
    if n_main > 0:
        stake_main = _round_step(main_budget / n_main, step)
        stake_main = min(max_s, max(min_s, stake_main))

    stakes_ins: list[float] = []
    if n_ins > 0:
        if mode == "score_weighted" and insurance_scores and len(insurance_scores) == n_ins:
            scores = [max(0.0, float(x)) for x in insurance_scores]
            total_score = sum(scores) or float(n_ins)
            raw = [(ins_budget * (sc / total_score)) for sc in scores]
            stakes_ins = [min(max_s, max(min_s, _round_step(v, step))) for v in raw]
        elif kelly_enabled:
            # Conservative research stub: equal stakes with kelly label (no bankroll edge required)
            eq = min(max_s, max(min_s, _round_step(ins_budget / n_ins, step)))
            stakes_ins = [eq] * n_ins
            warning += " kelly_research used equal fallback without fabricating edges."
        else:
            eq = min(max_s, max(min_s, _round_step(ins_budget / n_ins, step)))
            stakes_ins = [eq] * n_ins

    main_allocated = round(stake_main * n_main, 4)
    ins_allocated = round(sum(stakes_ins), 4)
    allocated = round(main_allocated + ins_allocated, 4)
    remainder = round(total - allocated, 4)

    return {
        "research_only": True,
        "owner_only": True,
        "warning": warning,
        "stake_mode": "kelly_research" if kelly_enabled else mode,
        "kelly_enabled": kelly_enabled,
        "total_budget_eur": total,
        "main_budget_eur": main_budget,
        "insurance_budget_eur": ins_budget,
        "main_budget_ratio": main_ratio,
        "insurance_budget_ratio": ins_ratio,
        "n_main_tickets": n_main,
        "n_insurance_tickets": n_ins,
        "stake_per_main_ticket_eur": stake_main,
        "stake_per_insurance_ticket_eur": stakes_ins,
        "equal_insurance_stake_eur": (stakes_ins[0] if stakes_ins else 0.0),
        "total_allocated_eur": allocated,
        "unallocated_remainder_eur": remainder,
        "maximum_theoretical_loss_eur": allocated,
        "min_stake_per_ticket_eur": min_s,
        "max_stake_per_ticket_eur": max_s,
        "rounding_step_eur": step,
        "gross_return_scenarios": {
            "note": "Only computable when all ticket combined odds exist; not guaranteed profit.",
            "all_main_lose_insurance_none": -allocated,
        },
    }
