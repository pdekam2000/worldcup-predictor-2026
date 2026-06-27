"""Goal timing band helpers for TIMING_RANGE_CONSISTENCY (bugfix)."""

from __future__ import annotations

import re

# Matches extended_markets._BAND_MIDPOINT bands (minute inclusive ranges).
TIMING_MINUTE_BANDS: tuple[tuple[int, int, str], ...] = (
    (0, 15, "0-15"),
    (16, 30, "16-30"),
    (31, 45, "31-45"),
    (46, 60, "46-60"),
    (61, 75, "61-75"),
    (76, 120, "76-90+"),
)

RULE_TIMING_RANGE_CONSISTENCY = "TIMING_RANGE_CONSISTENCY"


def normalize_minute_band(band: str) -> str:
    text = str(band or "").strip().replace("_", "-")
    if text == "76-90":
        return "76-90+"
    return text


def parse_minute_band(band: str) -> tuple[int, int] | None:
    text = normalize_minute_band(band).replace("+", "").strip()
    if not text or text in {"—", "-", "no_goal"}:
        return None
    match = re.match(r"^(\d+)-(\d+)$", text)
    if not match:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    if start > end:
        return None
    return start, end


def expected_minute_in_band(expected_minute: int, band: str) -> bool:
    parsed = parse_minute_band(band)
    if parsed is None:
        return False
    start, end = parsed
    return start <= int(expected_minute) <= end


def band_for_expected_minute(expected_minute: int) -> str | None:
    minute = int(expected_minute)
    for start, end, label in TIMING_MINUTE_BANDS:
        if start <= minute <= end:
            return label
    return None
