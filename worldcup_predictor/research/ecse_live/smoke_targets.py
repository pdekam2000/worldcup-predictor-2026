"""PHASE ECSE-LIVE-1 — Win2Day smoke-test fixture targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PHASE = "ECSE-LIVE-1"


@dataclass(frozen=True)
class EcseSmokeTarget:
    home_team: str
    away_team: str
    label: str | None = None

    @property
    def display(self) -> str:
        return self.label or f"{self.home_team} vs {self.away_team}"


WIN2DAY_SMOKE_TARGETS: tuple[EcseSmokeTarget, ...] = (
    EcseSmokeTarget("Brazil", "Japan"),
    EcseSmokeTarget("Germany", "Paraguay"),
    EcseSmokeTarget("Netherlands", "Morocco"),
    EcseSmokeTarget("Ivory Coast", "Norway"),
    EcseSmokeTarget("France", "Sweden"),
    EcseSmokeTarget("Mexico", "Ecuador"),
    EcseSmokeTarget("England", "DR Congo"),
    EcseSmokeTarget("Belgium", "Senegal"),
)

# Known API-Football naming variants for resolver hints.
TEAM_ALIASES: dict[str, tuple[str, ...]] = {
    "dr congo": ("congo dr", "congo", "democratic republic of the congo", "drc"),
    "ivory coast": ("cote d'ivoire", "côte d'ivoire", "cote divoire"),
    "usa": ("united states", "united states of america"),
}


def targets_as_dicts() -> list[dict[str, Any]]:
    return [
        {"home_team": t.home_team, "away_team": t.away_team, "label": t.display}
        for t in WIN2DAY_SMOKE_TARGETS
    ]
