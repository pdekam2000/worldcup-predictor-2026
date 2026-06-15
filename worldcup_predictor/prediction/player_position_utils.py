"""Shared player position helpers for first-goal and API-Sports normalization."""

from __future__ import annotations

GOALKEEPER_POSITIONS = frozenset({"G", "GK", "GOALKEEPER"})
FORWARD_POSITIONS = frozenset({"F", "FW", "ST", "CF", "LW", "RW", "WF", "SS"})
ATTACK_MID_POSITIONS = frozenset({"AM", "CAM", "LAM", "RAM", "OM", "ACM"})
CENTRAL_MID_POSITIONS = frozenset({"M", "MF", "CM", "MC", "DM", "CDM"})
DEFENDER_POSITIONS = frozenset({"D", "DF", "CB", "LB", "RB", "WB", "LWB", "RWB"})


def normalize_position(pos: str | None) -> str:
    return str(pos or "").strip().upper()


def is_goalkeeper(pos: str | None) -> bool:
    p = normalize_position(pos)
    if not p:
        return False
    if p in GOALKEEPER_POSITIONS:
        return True
    return len(p) <= 2 and p.startswith("G")


def position_score_multiplier(pos: str | None) -> float | None:
    p = normalize_position(pos)
    if is_goalkeeper(p):
        return None
    if not p:
        return 0.55
    if p in FORWARD_POSITIONS:
        return 1.0
    if p in ATTACK_MID_POSITIONS:
        return 0.88
    if p in CENTRAL_MID_POSITIONS:
        return 0.62
    if p in DEFENDER_POSITIONS:
        return 0.32
    return 0.48


def apply_position_score(base: float, pos: str | None, *, penalty_gk_goals: float | None = None) -> float | None:
    if is_goalkeeper(pos):
        if penalty_gk_goals and penalty_gk_goals > 0:
            return round(base * 0.22 + min(penalty_gk_goals, 3) * 4, 2)
        return None
    mult = position_score_multiplier(pos)
    if mult is None:
        return None
    return round(base * mult, 2)
