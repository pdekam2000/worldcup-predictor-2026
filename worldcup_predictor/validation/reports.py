"""Phase 26 — automated validation reports."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from worldcup_predictor.validation.contribution import update_contribution_stats
from worldcup_predictor.validation.coverage import compute_coverage
from worldcup_predictor.validation.models import PromotionContributionStats
from worldcup_predictor.validation.readiness import compute_readiness_score
from worldcup_predictor.validation.store import PromotionContributionStore, RealWorldValidationStore

REPORTS_DIR = Path("data/validation/reports")


def _accuracy(records: list) -> float:
    settled = [r for r in records if r.settled and r.one_x_two_correct is not None]
    if not settled:
        return 0.0
    return sum(1 for r in settled if r.one_x_two_correct) / len(settled)


def _calibration_rate(records: list) -> float:
    settled = [r for r in records if r.settled and r.confidence_calibration_ok is not None]
    if not settled:
        return 0.0
    return sum(1 for r in settled if r.confidence_calibration_ok) / len(settled)


def _disagreement_success(records: list) -> float:
    relevant = [
        r
        for r in records
        if r.settled
        for p in r.promotions
        if p.promotion_key == "24c_sportmonks" and p.disagreement is not None and p.disagreement >= 0.25
    ]
    if not relevant:
        return 0.0
    helped = sum(1 for r in records if r.signal_usefulness.get("24c_sportmonks") == "helped")
    return helped / max(1, len([r for r in records if r.settled]))


def generate_weekly_summary(
    *,
    store: RealWorldValidationStore | None = None,
    output_path: Path | str | None = None,
) -> Path:
    store = store or RealWorldValidationStore()
    records = store.load_all()
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent = [
        r
        for r in records
        if datetime.fromisoformat(r.prediction_timestamp[:19]) >= cutoff.replace(tzinfo=None)
    ]
    coverage = compute_coverage(recent or records)
    readiness = compute_readiness_score(records)
    settled_recent = [r for r in recent if r.settled]

    lines = [
        "# Weekly Validation Summary",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"- Records (7d): **{len(recent)}**",
        f"- Settled (7d): **{len(settled_recent)}**",
        f"- 1X2 accuracy (7d): **{_accuracy(recent):.1%}**",
        f"- Confidence calibration (7d): **{_calibration_rate(recent):.1%}**",
        "",
        "## Coverage",
        "",
        f"- Lineup: {coverage.lineup_coverage:.1%}",
        f"- Expected lineup: {coverage.expected_lineup_coverage:.1%}",
        f"- Tournament context: {coverage.context_coverage:.1%}",
        f"- xG: {coverage.xg_coverage:.1%}",
        f"- Sportmonks: {coverage.sportmonks_coverage:.1%}",
        "",
        f"## WorldCupReadinessScore: **{readiness.score:.1f}/100**",
        "",
    ]
    for note in readiness.notes:
        lines.append(f"- {note}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    target = Path(output_path or REPORTS_DIR / "weekly_validation_summary.md")
    target.write_text("\n".join(lines) + "\n",encoding="utf-8")
    return target


def generate_monthly_impact_report(
    *,
    store: RealWorldValidationStore | None = None,
    stats_store: PromotionContributionStore | None = None,
    output_path: Path | str | None = None,
) -> Path:
    store = store or RealWorldValidationStore()
    stats_store = stats_store or PromotionContributionStore()
    records = store.load_all()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent = [
        r
        for r in records
        if datetime.fromisoformat(r.prediction_timestamp[:19]) >= cutoff.replace(tzinfo=None)
    ]
    stats = update_contribution_stats(None, recent or records)
    stats_store.save(stats)
    coverage = compute_coverage(recent or records)

    lines = [
        "# Monthly Promotion Impact Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Metrics",
        "",
        f"- 1X2 accuracy (30d): **{_accuracy(recent):.1%}**",
        f"- Confidence calibration (30d): **{_calibration_rate(recent):.1%}**",
        f"- Disagreement success rate: **{_disagreement_success(recent):.1%}**",
        "",
        "## Promotion Contribution",
        "",
        "| Promotion | Total | Helped | Neutral | Harmful | Signal Avail | Avg Δ |",
        "|-----------|-------|--------|---------|---------|--------------|-------|",
    ]
    for key in ("24a_lineup", "24b_context", "24c_xg", "24c_sportmonks"):
        s: PromotionContributionStats = stats.get(key) or PromotionContributionStats(promotion_key=key)
        lines.append(
            f"| {key} | {s.total} | {s.helped} | {s.neutral} | {s.harmful} | "
            f"{s.signal_available_rate:.1%} | {s.avg_delta:+.2f} |"
        )

    lines.extend(
        [
            "",
            "## Coverage (30d)",
            "",
            f"- Lineup missing rate: {coverage.missing_rates.get('lineup', 0):.1%}",
            f"- Context missing rate: {coverage.missing_rates.get('context', 0):.1%}",
            f"- xG missing rate: {coverage.missing_rates.get('xg', 0):.1%}",
            f"- Sportmonks missing rate: {coverage.missing_rates.get('sportmonks', 0):.1%}",
            "",
            "**All promotion flags remain shadow — no gated rollout.**",
        ]
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    target = Path(output_path or REPORTS_DIR / "monthly_promotion_impact_report.md")
    target.write_text("\n".join(lines) + "\n",encoding="utf-8")
    return target
