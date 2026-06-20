"""Phase 26 — intelligence coverage analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

from worldcup_predictor.validation.models import RealWorldValidationRecord


@dataclass
class CoverageReport:
    total_records: int = 0
    lineup_coverage: float = 0.0
    expected_lineup_coverage: float = 0.0
    context_coverage: float = 0.0
    xg_coverage: float = 0.0
    sportmonks_coverage: float = 0.0
    missing_rates: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_records": self.total_records,
            "lineup_coverage": self.lineup_coverage,
            "expected_lineup_coverage": self.expected_lineup_coverage,
            "context_coverage": self.context_coverage,
            "xg_coverage": self.xg_coverage,
            "sportmonks_coverage": self.sportmonks_coverage,
            "missing_rates": self.missing_rates,
        }


def _has_snapshot(block: dict) -> bool:
    if not block:
        return False
    if block.get("data_sources"):
        return True
    if block.get("available") is True:
        return True
    if block.get("status") not in (None, "unavailable", ""):
        return True
    return bool(block.get("home_xg") or block.get("motivation_score_home") or block.get("lineup_confidence"))


def compute_coverage(records: list[RealWorldValidationRecord]) -> CoverageReport:
    n = len(records)
    if n == 0:
        return CoverageReport()

    lineup = sum(1 for r in records if _has_snapshot(r.snapshots.lineup_snapshot))
    expected = sum(1 for r in records if _has_snapshot(r.snapshots.expected_lineup_snapshot))
    context = sum(1 for r in records if _has_snapshot(r.snapshots.tournament_context_snapshot))
    xg = sum(1 for r in records if _has_snapshot(r.snapshots.xg_snapshot))
    sm = sum(1 for r in records if _has_snapshot(r.snapshots.sportmonks_prediction_snapshot))

    report = CoverageReport(
        total_records=n,
        lineup_coverage=round(lineup / n, 4),
        expected_lineup_coverage=round(expected / n, 4),
        context_coverage=round(context / n, 4),
        xg_coverage=round(xg / n, 4),
        sportmonks_coverage=round(sm / n, 4),
    )
    report.missing_rates = {
        "lineup": round(1 - report.lineup_coverage, 4),
        "expected_lineup": round(1 - report.expected_lineup_coverage, 4),
        "context": round(1 - report.context_coverage, 4),
        "xg": round(1 - report.xg_coverage, 4),
        "sportmonks": round(1 - report.sportmonks_coverage, 4),
    }
    return report
