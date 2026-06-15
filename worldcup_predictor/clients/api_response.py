from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

SourceKind = Literal["live", "cache", "placeholder"]


@dataclass
class ApiCallResult:
    """Normalized API call envelope — never raises to callers."""

    data: Any
    source: SourceKind
    endpoint: str
    error: str | None = None
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and self.data is not None

    @property
    def response_count(self) -> int:
        if isinstance(self.data, list):
            return len(self.data)
        if self.data is not None:
            return 1
        return 0

    @property
    def unavailable_reason(self) -> str | None:
        if self.error:
            return self.error
        if self.data is None:
            return "empty response"
        return None
