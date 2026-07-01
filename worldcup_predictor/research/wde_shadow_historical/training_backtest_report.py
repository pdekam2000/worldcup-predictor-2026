"""Part F — WDE shadow training + backtest markdown report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.wde_shadow_historical.constants import PHASE, TRAINING_BACKTEST_REPORT


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_acc(v: Any) -> str:
    return f"{v:.4f}" if isinstance(v, (int, float)) and v is not None else "n/a"


def _market_table(cmp: dict[str, Any]) -> str:
    lines = ["| Market | Shadow | Bookmaker | Historical | Current WDE |", "|--------|--------|-----------|------------|-------------|"]
    for m, label in [("1x2", "1X2"), ("ou25", "O/U2.5"), ("btts", "BTTS")]:
        row = cmp.get(m) or {}
        lines.append(
            f"| {label} | {_fmt_acc(row.get('shadow'))} | {_fmt_acc(row.get('bookmaker'))} | "
            f"{_fmt_acc(row.get('historical'))} | {_fmt_acc(row.get('current_wde'))} |"
        )
    return "\n".join(lines)


def _best_worst_segments(segments: dict[str, Any], key: str = "by_competition") -> tuple[str, str]:
    block = segments.get(key) or {}
    ranked = [
        (name, data.get("shadow_1x2_accuracy"))
        for name, data in block.items()
        if isinstance(data, dict) and data.get("n", 0) >= 50 and data.get("shadow_1x2_accuracy") is not None
    ]
    if not ranked:
        return "n/a", "n/a"
    ranked.sort(key=lambda x: x[1])
    return f"{ranked[-1][0]} ({ranked[-1][1]:.4f})", f"{ranked[0][0]} ({ranked[0][1]:.4f})"


def write_training_backtest_report(
    *,
    split: dict[str, Any],
    metrics: dict[str, Any],
    backtest: dict[str, Any],
    validation: dict[str, Any],
    dataset_summary: dict[str, Any] | None = None,
) -> None:
    rec = validation.get("final_recommendation", "DO_NOT_PROMOTE_MODEL")
    test_cmp = (backtest.get("comparison") or {}).get("test") or {}
    val_cmp = (backtest.get("comparison") or {}).get("validation") or {}
    test_segments = (backtest.get("test") or {}).get("segments") or {}
    wde_cov = (backtest.get("test") or {}).get("current_wde_coverage") or {}

    best_comp, worst_comp = _best_worst_segments(test_segments, "by_competition")
    best_country, worst_country = _best_worst_segments(test_segments, "by_country")

    fg = metrics.get("feature_groups") or {}
    feature_lines = "\n".join(f"- {k}: `{v}`" for k, v in fg.items())

    calibration_note = "See backtest artifact for per-market calibration buckets."
    test_1x2 = ((backtest.get("test") or {}).get("markets") or {}).get("1x2", {}).get("shadow", {})
    buckets = test_1x2.get("calibration_buckets") or []
    if buckets:
        calibration_note = "; ".join(
            f"{b['bin']}: conf={b['mean_confidence']}, acc={b['accuracy']} (n={b['count']})" for b in buckets[:5]
        )

    md = f"""# WDE Shadow Training & Backtest Report

**Phase:** {PHASE}  
**Mode:** Owner/internal research only — shadow model, no production replacement  
**Generated:** {_utc_now()}

## Split summary

| Split | Rows | Date range |
|-------|------|------------|
| Train | {(split.get('train') or {}).get('count', 0):,} | {(split.get('train') or {}).get('date_min', 'n/a')} → {(split.get('train') or {}).get('date_max', 'n/a')} |
| Validation | {(split.get('validation') or {}).get('count', 0):,} | {(split.get('validation') or {}).get('date_min', 'n/a')} → {(split.get('validation') or {}).get('date_max', 'n/a')} |
| Test | {(split.get('test') or {}).get('count', 0):,} | {(split.get('test') or {}).get('date_min', 'n/a')} → {(split.get('test') or {}).get('date_max', 'n/a')} |

- Strict time order: **{split.get('leakage_check', {}).get('strict_time_order')}**
- No duplicate row_hash: **{(split.get('verification') or {}).get('no_duplicate_row_hash')}**
- Dataset total (prep): **{(dataset_summary or {}).get('row_count', 'n/a'):,}**

## Model

- **Type:** `{metrics.get('model_type', 'n/a')}`
- **Directory:** `{metrics.get('model_dir', 'n/a')}`
- **Train rows:** {metrics.get('train_rows', 'n/a'):,}
- **Validation rows:** {metrics.get('val_rows', 'n/a'):,}

### Feature groups

{feature_lines}

## Validation metrics (during training)

| Market | Val accuracy | Bookmaker val accuracy | Beats bookmaker |
|--------|--------------|------------------------|-----------------|
| 1X2 | {_fmt_acc((metrics.get('markets') or {}).get('1x2', {}).get('val_accuracy'))} | {_fmt_acc((metrics.get('markets') or {}).get('1x2', {}).get('bookmaker_baseline_val_accuracy'))} | {(metrics.get('markets') or {}).get('1x2', {}).get('beats_bookmaker_on_val')} |
| O/U2.5 | {_fmt_acc((metrics.get('markets') or {}).get('ou25', {}).get('val_accuracy'))} | {_fmt_acc((metrics.get('markets') or {}).get('ou25', {}).get('bookmaker_baseline_val_accuracy'))} | {(metrics.get('markets') or {}).get('ou25', {}).get('beats_bookmaker_on_val')} |
| BTTS | {_fmt_acc((metrics.get('markets') or {}).get('btts', {}).get('val_accuracy'))} | {_fmt_acc((metrics.get('markets') or {}).get('btts', {}).get('bookmaker_baseline_val_accuracy'))} | {(metrics.get('markets') or {}).get('btts', {}).get('beats_bookmaker_on_val')} |

## Backtest — validation split

{_market_table(val_cmp)}

## Backtest — test split

{_market_table(test_cmp)}

### Current WDE comparison coverage (test)

- Matched predictions: **{wde_cov.get('matched_predictions', 0)}** / {wde_cov.get('total_rows', 0)}
- Coverage rate: **{wde_cov.get('coverage_rate', 0)}**
- Note: {wde_cov.get('note', 'Small coverage expected')}

## Best / worst (test, 1X2 accuracy, n≥50)

| Segment | Best | Worst |
|---------|------|-------|
| Competition | {best_comp} | {worst_comp} |
| Country | {best_country} | {worst_country} |

## Calibration (test 1X2)

{calibration_note}

## Risks

- Historical CSV teams may not align with production fixture crosswalk → low WDE comparison coverage.
- Bookmaker implied baseline is strong; beating it on held-out test is difficult.
- O/U2.5 has fewer usable rows than 1X2/BTTS.
- Time-based split may under-represent recent leagues/seasons in test.

## Validation gate

- Checks passed: **{validation.get('passed')}** / {validation.get('passed', 0) + validation.get('failed', 0)}
- Promotion allowed: **{validation.get('promotion_allowed')}**

## Final recommendation

### `{rec}`

**No production model replacement. No public changes. No writes to worldcup_stored_predictions or odds_snapshots.**
"""
    TRAINING_BACKTEST_REPORT.write_text(md, encoding="utf-8")
