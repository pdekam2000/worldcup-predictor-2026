"""Recalibration report from recent error audit — recommendations only, no weight auto-apply."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.accuracy.recent_error_audit import (
    MIN_SAMPLE_WARNING,
    RecentErrorAuditReport,
    build_recent_error_audit,
    fetch_fixtures_for_audit,
    write_recent_error_audit_markdown,
)

LIVE_CALIBRATION_JSON = Path("reports/calibration/recent_live_calibration.json")
RECALIBRATION_JSON = Path("reports/calibration/recent_recalibration_report.json")
RECALIBRATION_MD = Path("reports/calibration/recent_recalibration_report.md")
MIN_PARTIAL_SAMPLE = 10


@dataclass
class RecalibrationRecommendations:
    generated_at_utc: str
    competition_key: str
    verified_sample: int
    sample_adequate: bool
    warnings: list[str] = field(default_factory=list)
    confidence_correction_factor: float = 1.0
    max_confidence_cap: float | None = None
    draw_market_threshold: float = 0.28
    balanced_edge_max: float = 0.025
    ou_goal_threshold_adjustment: float = 0.0
    scoreline_probability_cap: float = 0.40
    fusion_low_diversity_extra_penalty: float = 0.0
    fixes_applied: list[str] = field(default_factory=list)
    before_distribution: dict[str, Any] = field(default_factory=dict)
    after_distribution: dict[str, Any] = field(default_factory=dict)
    apply_recommendations_after_user_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _distribution_from_audit(audit: RecentErrorAuditReport) -> dict[str, Any]:
    b = audit.bias
    w20 = next((w for w in audit.windows if w.window == 20), audit.windows[0] if audit.windows else None)
    return {
        "1x2_accuracy_last20": w20.one_x_two if w20 else None,
        "ou_accuracy_last20": w20.over_under if w20 else None,
        "avg_confidence_last20": w20.avg_confidence if w20 else None,
        "calibration_gap_last20": w20.calibration_gap if w20 else None,
        "home_pick_rate": b.home_pick_rate,
        "draw_pick_rate": b.draw_pick_rate,
        "draw_actual_rate": b.draw_actual_rate,
        "over_pick_share": round(b.over_predicted / max(audit.total_verified, 1), 4),
    }


def build_recalibration_from_audit(audit: RecentErrorAuditReport) -> RecalibrationRecommendations:
    rec = RecalibrationRecommendations(
        generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        competition_key=audit.competition_key,
        verified_sample=audit.total_verified,
        sample_adequate=audit.sample_adequate,
        warnings=list(audit.warnings),
        before_distribution=_distribution_from_audit(audit),
    )

    if audit.total_verified < MIN_PARTIAL_SAMPLE:
        rec.warnings.append(
            f"Fewer than {MIN_PARTIAL_SAMPLE} verified matches — no calibration factors applied."
        )
        rec.after_distribution = dict(rec.before_distribution)
        return rec

    w20 = next((w for w in audit.windows if w.window == 20), None)
    if w20 and w20.calibration_gap is not None and w20.calibration_gap < -0.08:
        gap = abs(w20.calibration_gap)
        factor = max(0.85, 1.0 - gap * 0.6)
        rec.confidence_correction_factor = round(factor, 3)
        rec.fixes_applied.append(
            f"Confidence correction factor {rec.confidence_correction_factor} "
            f"(high-band overconfidence gap {w20.calibration_gap:+.2f})."
        )
        if audit.sample_adequate and w20.avg_confidence > 72:
            rec.max_confidence_cap = 72.0
            rec.fixes_applied.append("Cap max confidence at 72 until sample stabilizes.")

    if audit.bias.draw_missed >= 2 and (audit.bias.draw_actual_rate or 0) > 0.15:
        rec.draw_market_threshold = 0.26
        rec.balanced_edge_max = 0.03
        rec.fixes_applied.append(
            "Draw protection: lower draw-market threshold and widen balanced edge band."
        )

    n = max(audit.total_verified, 1)
    ou_bias = (audit.bias.over_predicted / n) - (audit.bias.over_actual / n)
    if ou_bias > 0.12 and audit.sample_adequate:
        rec.ou_goal_threshold_adjustment = 0.08
        rec.fixes_applied.append(
            "O/U calibration: raise expected-goals threshold before confirming Over 2.5."
        )
    elif ou_bias < -0.12 and audit.sample_adequate:
        rec.ou_goal_threshold_adjustment = -0.08
        rec.fixes_applied.append(
            "O/U calibration: lower expected-goals threshold before confirming Under 2.5."
        )

    if audit.bias.favorite_wrong >= 2:
        rec.scoreline_probability_cap = 0.32
        rec.fixes_applied.append("Scoreline uncertainty: cap displayed scoreline probability at 32%.")
    elif audit.total_verified >= MIN_PARTIAL_SAMPLE:
        rec.scoreline_probability_cap = 0.38
        rec.fixes_applied.append("Scoreline uncertainty: conservative cap at 38%.")

    if any("Overconfidence" in p for p in audit.bias.repeated_patterns):
        rec.fusion_low_diversity_extra_penalty = 1.5
        rec.fixes_applied.append(
            "Fusion safety: extra penalty when correlated agents agree but diversity is low."
        )

    if not rec.fixes_applied:
        rec.fixes_applied.append("No structural fixes — monitoring only.")

    after = dict(rec.before_distribution)
    if rec.confidence_correction_factor < 1.0 and w20:
        after["adjusted_avg_confidence_estimate"] = round(
            w20.avg_confidence * rec.confidence_correction_factor, 1
        )
    rec.after_distribution = after

    if not audit.sample_adequate:
        rec.warnings.append(
            f"Sample below {MIN_SAMPLE_WARNING} — fixes are conservative and may be revised."
        )
    return rec


def run_full_recalibration_pipeline(
    *,
    competition_key: str = "world_cup_2026",
    write_audit: bool = True,
) -> tuple[RecentErrorAuditReport, RecalibrationRecommendations]:
    fixtures = fetch_fixtures_for_audit(competition_key=competition_key)
    audit = build_recent_error_audit(fixtures, competition_key=competition_key)
    if write_audit:
        write_recent_error_audit_markdown(audit)
    rec = build_recalibration_from_audit(audit)
    write_recalibration_reports(rec)
    return audit, rec


def write_recalibration_reports(rec: RecalibrationRecommendations) -> tuple[Path, Path]:
    RECALIBRATION_JSON.parent.mkdir(parents=True, exist_ok=True)
    RECALIBRATION_JSON.write_text(json.dumps(rec.to_dict(), indent=2), encoding="utf-8")

    live_payload = {
        "generated_at_utc": rec.generated_at_utc,
        "competition_key": rec.competition_key,
        "verified_sample": rec.verified_sample,
        "sample_adequate": rec.sample_adequate,
        "confidence_correction_factor": rec.confidence_correction_factor,
        "max_confidence_cap": rec.max_confidence_cap,
        "draw_market_threshold": rec.draw_market_threshold,
        "balanced_edge_max": rec.balanced_edge_max,
        "ou_goal_threshold_adjustment": rec.ou_goal_threshold_adjustment,
        "scoreline_probability_cap": rec.scoreline_probability_cap,
        "fusion_low_diversity_extra_penalty": rec.fusion_low_diversity_extra_penalty,
        "active": rec.verified_sample >= MIN_PARTIAL_SAMPLE,
    }
    LIVE_CALIBRATION_JSON.write_text(json.dumps(live_payload, indent=2), encoding="utf-8")

    lines = [
        "# Recent Recalibration Report",
        "",
        f"Generated: {rec.generated_at_utc}",
        f"**Verified sample:** {rec.verified_sample} · **Adequate:** {rec.sample_adequate}",
        "",
        "## Recommended live calibration (not auto-applied to factor weights)",
        "",
        f"- Confidence correction factor: **{rec.confidence_correction_factor}**",
        f"- Max confidence cap: **{rec.max_confidence_cap or 'none'}**",
        f"- Draw market threshold: **{rec.draw_market_threshold}**",
        f"- Balanced edge max: **{rec.balanced_edge_max}**",
        f"- O/U goal threshold adjustment: **{rec.ou_goal_threshold_adjustment:+.2f}**",
        f"- Scoreline probability cap: **{rec.scoreline_probability_cap}**",
        f"- Fusion low-diversity extra penalty: **{rec.fusion_low_diversity_extra_penalty}**",
        "",
        "## Fixes applied to live calibration config",
        "",
    ]
    for fix in rec.fixes_applied:
        lines.append(f"- {fix}")
    if rec.warnings:
        lines.extend(["", "## Warnings", ""])
        for w in rec.warnings:
            lines.append(f"- {w}")
    lines.extend(["", "## Before / after distribution", "", "```json", json.dumps({"before": rec.before_distribution, "after": rec.after_distribution}, indent=2), "```"])
    RECALIBRATION_MD.write_text("\n".join(lines), encoding="utf-8")
    return RECALIBRATION_JSON, RECALIBRATION_MD
