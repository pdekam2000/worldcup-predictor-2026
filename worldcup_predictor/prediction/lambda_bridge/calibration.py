"""Temporary bridge parameter overrides for Phase 12B-R simulation sweeps."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from worldcup_predictor.prediction.lambda_bridge import config as cfg


@dataclass(frozen=True)
class BridgeSweepParams:
    """Simulation-only parameter set — does not change production defaults."""

    name: str
    global_cap: float = 0.22
    market_cap: float = 0.10
    injury_cap: float = 0.12
    lineup_cap: float = 0.10
    tournament_cap: float = 0.06
    dq_disable_below: float = 45.0
    active_agents: frozenset[str] | None = None

    def label(self) -> str:
        if self.active_agents is not None:
            agents = ",".join(sorted(self.active_agents))
            return f"{self.name} [{agents}]"
        return self.name


@dataclass
class _ConfigBackup:
    global_cap: float
    specialist_caps: dict[str, float]
    group_caps: dict[str, float]
    dq_disable_below: float


@contextmanager
def apply_sweep(params: BridgeSweepParams) -> Iterator[BridgeSweepParams]:
    """Patch config module for one sweep iteration; always restored."""
    backup = _ConfigBackup(
        global_cap=cfg.GLOBAL_LAMBDA_CAP,
        specialist_caps=dict(cfg.SPECIALIST_CAPS),
        group_caps=dict(cfg.GROUP_CAPS),
        dq_disable_below=cfg.DQ_DISABLE_BELOW,
    )
    try:
        cfg.GLOBAL_LAMBDA_CAP = params.global_cap
        cfg.DQ_DISABLE_BELOW = params.dq_disable_below
        cfg.SPECIALIST_CAPS = {
            **cfg.SPECIALIST_CAPS,
            "market_consensus_agent": params.market_cap,
            "injury_suspension_intelligence_agent": params.injury_cap,
            "lineup_intelligence_agent": params.lineup_cap,
            "tournament_intelligence_agent": params.tournament_cap,
        }
        sharp_cap = min(0.05, params.market_cap)
        cfg.SPECIALIST_CAPS["sharp_money_intelligence_agent"] = sharp_cap
        cfg.GROUP_CAPS = {
            "odds": max(params.market_cap, sharp_cap),
            "squad_health": params.injury_cap + params.lineup_cap,
            "context": max(params.tournament_cap, 0.0),
        }
        yield params
    finally:
        cfg.GLOBAL_LAMBDA_CAP = backup.global_cap
        cfg.SPECIALIST_CAPS = backup.specialist_caps
        cfg.GROUP_CAPS = backup.group_caps
        cfg.DQ_DISABLE_BELOW = backup.dq_disable_below


ABLATION_SCENARIOS: dict[str, frozenset[str]] = {
    "A_market_only": frozenset({"market_consensus_agent"}),
    "B_injury_only": frozenset({"injury_suspension_intelligence_agent"}),
    "C_lineup_only": frozenset({"lineup_intelligence_agent"}),
    "D_market_injury": frozenset({"market_consensus_agent", "injury_suspension_intelligence_agent"}),
    "E_market_lineup": frozenset({"market_consensus_agent", "lineup_intelligence_agent"}),
    "F_injury_lineup": frozenset(
        {"injury_suspension_intelligence_agent", "lineup_intelligence_agent"}
    ),
    "G_market_injury_lineup": frozenset(
        {
            "market_consensus_agent",
            "injury_suspension_intelligence_agent",
            "lineup_intelligence_agent",
        }
    ),
    "H_no_tournament": frozenset(
        {
            "market_consensus_agent",
            "injury_suspension_intelligence_agent",
            "lineup_intelligence_agent",
            "sharp_money_intelligence_agent",
        }
    ),
}

SWEEP_GLOBAL_CAPS = (0.08, 0.12, 0.16, 0.20, 0.22)
SWEEP_MARKET_CAPS = (0.04, 0.06, 0.08, 0.10)
SWEEP_INJURY_CAPS = (0.02, 0.04, 0.06, 0.08)
SWEEP_LINEUP_CAPS = (0.02, 0.04, 0.06, 0.08)
SWEEP_TOURNAMENT_CAPS = (0.00, 0.02, 0.03)
SWEEP_DQ_CUTOFFS = (45.0, 55.0, 65.0)
