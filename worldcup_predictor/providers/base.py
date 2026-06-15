"""Shared types for optional external data providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Literal

ProviderName = Literal[
    "api_sports",
    "sportmonks",
    "the_odds_api",
    "weatherapi",
    "openweather",
    "rapid_football_stats",
    "rapid_xg_statistics",
    "rapid_open_weather",
]


class ProviderTier(IntEnum):
    """Resolution order — lower runs first; primary must not be replaced by enrichment."""

    PRIMARY = 1
    ENRICHMENT = 2


@dataclass(frozen=True)
class ProviderCallResult:
    """Normalized provider response — never raises to callers."""

    data: Any
    provider: ProviderName
    tier: ProviderTier
    endpoint: str
    configured: bool = True
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.data is not None

    @property
    def available(self) -> bool:
        if not self.ok:
            return False
        if isinstance(self.data, list):
            return len(self.data) > 0
        if isinstance(self.data, dict):
            return bool(self.data)
        return self.data is not None


@dataclass
class ProviderStatus:
    provider: ProviderName
    tier: ProviderTier
    configured: bool
    label: str
    env_var: str
    note: str = ""


@dataclass
class EnrichmentOutcome:
    """Summary of optional provider merges applied to a report."""

    applied_providers: list[str] = field(default_factory=list)
    filled_fields: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
