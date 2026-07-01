"""Provider call audit log with per-run quota guards."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.owner_daily.constants import LOGS_DIR


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ProviderQuotaGuard:
    max_api_football: int = 100
    max_sportmonks: int = 100
    max_oddalerts: int = 100
    api_football_used: int = 0
    sportmonks_used: int = 0
    oddalerts_used: int = 0
    no_provider_calls: bool = False

    def can_call(self, provider: str) -> bool:
        if self.no_provider_calls:
            return False
        key = provider.lower().replace("-", "_")
        if key in ("api_football", "api-football", "apifootball"):
            return self.api_football_used < self.max_api_football
        if key == "sportmonks":
            return self.sportmonks_used < self.max_sportmonks
        if key in ("oddalerts", "odd_alerts"):
            return self.oddalerts_used < self.max_oddalerts
        return True

    def increment(self, provider: str) -> int:
        key = provider.lower().replace("-", "_")
        if key in ("api_football", "api-football", "apifootball"):
            self.api_football_used += 1
            return self.api_football_used
        if key == "sportmonks":
            self.sportmonks_used += 1
            return self.sportmonks_used
        if key in ("oddalerts", "odd_alerts"):
            self.oddalerts_used += 1
            return self.oddalerts_used
        return 0

    def to_dict(self) -> dict[str, int]:
        return {
            "api_football": self.api_football_used,
            "sportmonks": self.sportmonks_used,
            "oddalerts": self.oddalerts_used,
        }


@dataclass
class DailyProviderCallLog:
    run_date: str
    quota: ProviderQuotaGuard = field(default_factory=ProviderQuotaGuard)
    entries: list[dict[str, Any]] = field(default_factory=list)
    _log_path: Path | None = None

    @property
    def log_path(self) -> Path:
        if self._log_path is None:
            ymd = self.run_date.replace("-", "")
            self._log_path = LOGS_DIR / f"daily_provider_calls_{ymd}.jsonl"
        return self._log_path

    def record(
        self,
        *,
        provider: str,
        endpoint: str,
        action: str,
        fixture_id: int | None = None,
        provider_fixture_id: int | None = None,
        competition_key: str | None = None,
        market: str | None = None,
        request_reason: str = "",
        cache_hit: bool = False,
        call_made: bool = False,
        success: bool = False,
        error: str | None = None,
    ) -> dict[str, Any]:
        quota_counter = 0
        if call_made and not cache_hit:
            quota_counter = self.quota.increment(provider)
        row = {
            "timestamp": _utc_now_iso(),
            "provider": provider,
            "endpoint": endpoint,
            "action": action,
            "fixture_id": fixture_id,
            "provider_fixture_id": provider_fixture_id,
            "competition_key": competition_key,
            "market": market,
            "request_reason": request_reason,
            "cache_hit": cache_hit,
            "call_made": call_made,
            "success": success,
            "error": error,
            "quota_counter": quota_counter,
        }
        self.entries.append(row)
        return row

    def flush(self) -> Path:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            for row in self.entries:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        written = self.log_path
        self.entries.clear()
        return written
