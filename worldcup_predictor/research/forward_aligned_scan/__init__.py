"""Forward aligned fixture scan package (research-only)."""

from worldcup_predictor.research.forward_aligned_scan.constants import (
    STATUS_BLOCKED,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_NO_FULL,
    STATUS_PARTIAL,
    STUDY_VERSION,
)
from worldcup_predictor.research.forward_aligned_scan.runner import run_forward_aligned_scan

__all__ = [
    "STUDY_VERSION",
    "STATUS_COMPLETE",
    "STATUS_NO_FULL",
    "STATUS_PARTIAL",
    "STATUS_BLOCKED",
    "STATUS_FAILED",
    "run_forward_aligned_scan",
]
