"""ODDS-TIMESTAMP-NORMALIZATION-1 — Safe UTC timestamp parsing for odds freshness."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

PHASE = "ODDS-TIMESTAMP-NORMALIZATION-1"

# Naive timestamps without timezone are treated as UTC (project storage convention).
NAIVE_TIMESTAMP_ASSUMPTION = "UTC"

_UNIX_SECONDS_MAX = 4_102_444_800  # ~2100-01-01
_UNIX_MS_THRESHOLD = 1_000_000_000_000

_SPACE_UTC_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d+))?\s*UTC$",
    re.IGNORECASE,
)
_SPACE_OFFSET_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:\s*([+-]\d{2}:\d{2}))?$"
)


def format_timestamp_utc(dt: datetime | None = None) -> str:
    """Canonical write format: YYYY-MM-DDTHH:MM:SS+00:00."""
    value = dt or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def normalize_timestamp(value: Any) -> datetime | None:
    """Return timezone-aware UTC datetime or None. Never raises."""
    return parse_timestamp_utc(value)


def parse_timestamp_utc(value: Any) -> datetime | None:
    """Parse odds snapshot timestamps from DB/provider values into UTC."""
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, (int, float)):
        return _parse_unix_number(float(value))

    text = str(value).strip()
    if not text:
        return None

    if text.isdigit():
        try:
            return _parse_unix_number(float(text))
        except (ValueError, OverflowError):
            return None

    parsed = _parse_iso_like(text)
    if parsed is not None:
        return parsed

    parsed = _parse_space_utc(text)
    if parsed is not None:
        return parsed

    return None


def _parse_unix_number(raw: float) -> datetime | None:
    if raw != raw or raw in (float("inf"), float("-inf")):  # NaN / inf
        return None
    if raw >= _UNIX_MS_THRESHOLD or raw <= -_UNIX_MS_THRESHOLD:
        raw = raw / 1000.0
    if abs(raw) > _UNIX_SECONDS_MAX:
        return None
    try:
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _parse_iso_like(text: str) -> datetime | None:
    candidate = text
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    candidate = candidate.replace(" UTC", "+00:00").replace(" utc", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_space_utc(text: str) -> datetime | None:
    match = _SPACE_UTC_RE.match(text)
    if match:
        date_part, time_part, micro = match.group(1), match.group(2), match.group(3)
        frac = f".{micro}" if micro else ""
        try:
            dt = datetime.fromisoformat(f"{date_part}T{time_part}{frac}+00:00")
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    match = _SPACE_OFFSET_RE.match(text)
    if match:
        date_part, time_part, micro, offset = match.groups()
        frac = f".{micro}" if micro else ""
        tz_suffix = offset or "+00:00"
        try:
            dt = datetime.fromisoformat(f"{date_part}T{time_part}{frac}{tz_suffix}")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def timestamp_age_hours(
    value: Any,
    *,
    now_utc: datetime | None = None,
) -> float | None:
    snap = parse_timestamp_utc(value)
    if snap is None:
        return None
    ref = now_utc or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    ref = ref.astimezone(timezone.utc)
    return round(max(0.0, (ref - snap).total_seconds() / 3600.0), 2)


def classify_timestamp_format(value: Any) -> str:
    """Best-effort format family label for audit reporting."""
    if value is None:
        return "null"
    if isinstance(value, datetime):
        return "datetime_object"
    if isinstance(value, (int, float)):
        return "unix_milliseconds" if abs(float(value)) >= _UNIX_MS_THRESHOLD else "unix_seconds"
    text = str(value).strip()
    if not text:
        return "empty"
    if text.isdigit():
        return classify_timestamp_format(int(text))
    if text.endswith("Z"):
        return "iso8601_z"
    if "+00:00" in text or re.search(r"[+-]\d{2}:\d{2}$", text):
        return "iso8601_offset"
    if _SPACE_UTC_RE.match(text):
        return "space_separated_utc_suffix"
    if "T" in text:
        return "iso8601_naive" if "+" not in text[10:] and not text.endswith("Z") else "iso8601_offset"
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text):
        return "space_separated_naive"
    return "other"


def explain_timestamp_parse(value: Any) -> str:
    family = classify_timestamp_format(value)
    parsed = parse_timestamp_utc(value)
    if parsed is None:
        return f"family={family}; parsed=None; assumption={NAIVE_TIMESTAMP_ASSUMPTION} for naive values"
    return (
        f"family={family}; parsed={parsed.isoformat()}; "
        f"assumption={NAIVE_TIMESTAMP_ASSUMPTION} for naive values"
    )
