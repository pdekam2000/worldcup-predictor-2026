"""Forward aligned fixture scan — research-only constants."""

from __future__ import annotations

from pathlib import Path

STUDY_VERSION = "forward-aligned-scan-v1"
TZ_NAME = "Europe/Vienna"
CALLER = "forward_aligned_scan"

ARTIFACT_ROOT = Path("artifacts") / "research" / "forward_aligned_fixture_scan"
REPORT_ROOT = Path("reports") / "research"
DOCS_PATH = Path("docs") / "research" / "forward_aligned_fixture_scan.md"

MIN_DAYS = 3
MAX_DAYS = 6
DEFAULT_DAYS = 6

STATUS_COMPLETE = "FORWARD_ALIGNED_SCAN_COMPLETE"
STATUS_NO_FULL = "FORWARD_ALIGNED_SCAN_NO_FULL_ALIGNMENT"
STATUS_PARTIAL = "FORWARD_ALIGNED_SCAN_PARTIAL"
STATUS_BLOCKED = "FORWARD_ALIGNED_SCAN_BLOCKED"
STATUS_FAILED = "FORWARD_ALIGNED_SCAN_VALIDATION_FAILED"

TIER_S = "S_FULL_ALIGNMENT"
TIER_A = "A_STRONG_ALIGNMENT"
TIER_B = "B_DIRECTIONAL_ALIGNMENT"
TIER_REJECTED = "REJECTED"

MAX_TIER_S = 3
MAX_TIER_A = 5
MAX_TIER_B = 10

TOP5_MASS_TIER_S_MIN = 0.52

TIMING_BUCKETS = (
    ("LATE", 1.0, 3.0),
    ("MID", 3.0, 12.0),
    ("MATCHDAY", 6.0, 24.0),
    ("EARLY", 24.0, 72.0),
    ("VERY_EARLY", 72.0, None),
)

PROMOTION_MIN_CONFIRMED = 200
