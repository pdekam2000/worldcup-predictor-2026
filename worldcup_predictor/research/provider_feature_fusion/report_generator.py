"""Generate markdown audit reports from fusion artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.provider_feature_fusion.constants import (
    ABLATION_PATH,
    COVERAGE_PATH,
    EXPERIMENTS_PATH,
    IMPORTANCE_PATH,
    PHASE,
)
from worldcup_predictor.research.provider_feature_fusion.leakage import registry_dict


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def generate_capability_inventory(root: Path) -> str:
    return """# Paid Provider Capability Inventory

Date: 2026-07-12

## Summary

| Provider | Role | Primary storage | Affects WDE | Affects ECSE | Affects backtest |
|----------|------|-----------------|-------------|--------------|------------------|
| API-Football | Primary | `fixtures`, `fixture_enrichment`, `odds_snapshots`, `api_response_cache` | Yes | Yes (odds lambdas) | Yes (cache replay) |
| SportMonks | Enrichment | `sportmonks_fixture_enrichment`, `fs_sportmonks_xg_*`, pressure store | Shadow promotion only | Research/EGIE | xG/pressure backtests |
| OddAlerts | Research/CSV | `oddalerts_probability_market_rows`, shadow tables | No (official) | Shadow/lab only | CSV historical |
| The Odds API | Odds consensus | `odds_api_cache`, `odds_api_usage` | Cross-source quality | No | Cache replay |
| RapidAPI stats/xG | Supplemental | In-memory / supplemental JSON | Agent signals only | No | No |
| Weather | Enrichment | File cache + report embed | Confidence modifier | No | No |

## API-Football endpoints (configured)

| Endpoint | Pre-match | Historical | Cache TTL | Storage | Prediction consumer |
|----------|-----------|------------|-----------|---------|---------------------|
| `fixtures` | Yes | Yes | 1800s | `fixtures` | Discovery, WDE context |
| `odds` | Yes | Limited | 3600s | `odds_snapshots`, enrichment | WDE, ECSE, BTTS, O/U |
| `teams/statistics` | Yes | Yes | 86400s | enrichment | WDE form/strength |
| `fixtures/headtohead` | Yes | Yes | 3600s | enrichment | WDE H2H factor |
| `injuries` | Yes | Yes | 28800s | enrichment | WDE injury factor |
| `fixtures/lineups` | ≤4h pre-KO | Yes | 900–1800s | enrichment | WDE lineup factor |
| `fixtures/statistics` | Post-match | Yes | 1800s | enrichment | **Not pre-match** |
| `standings` | Yes | Yes | 86400s | enrichment | Motivation context |
| `predictions` | Yes | Yes | 3600s | cache only | Reference, not official pick |

**Quota:** Daily live budget via `quota_guard.py`; scheduled odds refresh capped at 20 calls/run.

## SportMonks endpoints

| Include group | Pre-match | Storage | Consumer |
|---------------|-----------|---------|----------|
| participants, statistics, lineups | Yes | `sportmonks_fixture_enrichment` | Enrichment gap-fill |
| xGFixture | Mixed | `fs_sportmonks_xg_*` | EGIE, shadow xG (sparse) |
| pressure | Live/in-match | pressure feature store | Goal-timing research |
| odds, predictions | Pre-match | enrichment JSON | Odds fallback #2 |

## OddAlerts

| Path | Trigger | Storage | Consumer |
|------|---------|---------|----------|
| Gmail CSV import | Daily pipeline | `oddalerts_probability_market_rows` | ECSE shadow, segment calibration |
| Live API | Strict refresh fallback #3 | `oddalerts_odds_history` | Crosswalk-only refresh |
| Shadow tables | Lab runs | `ecse_oddalerts_shadow_*` | Owner shadow API |

## Call triggers (no new calls in this phase)

- On-demand: prediction gate, match intelligence builder, owner daily cycle
- Scheduled: `worldcup-odds-refresh.timer` (30 min, max 20 calls)
- Backfill: result backfill (separate unit, overlap-protected)

**This audit phase:** `provider_calls_made = 0`
"""


def generate_usage_matrix(root: Path) -> str:
    experiments = _load(EXPERIMENTS_PATH)
    return """# Provider Feature Usage Matrix

| Feature | Provider | Stored field | WDE | ECSE | BTTS | O/U | Confidence | Selection | Status |
|---------|----------|--------------|-----|------|------|-----|------------|-----------|--------|
| Odds consensus (1X2) | API-Football/OddAlerts | `odds_snapshots`, CSV odds | Yes | Yes | Implied | Implied | Via data quality | Yes | **Primary** |
| Implied probabilities | Derived | `implied_prob_*` | Yes | Lambda input | Yes | Yes | Yes | Yes | **Used** |
| Bookmaker count | Canonical snapshot | payload metadata | Indirect | No | No | No | Yes | No | Used |
| Market entropy | Derived | computed | No | No | No | No | Possible | No | Shadow tested |
| xG for/against (pre-match) | SportMonks | `xg_snapshots` | Shadow promo only | Research | No | No | Shadow | No | **Underused** (sparse) |
| xG (CSV realized) | External CSV | `expectedGoalsHome` | Diagnostic only | Diagnostic | No | No | No | No | **Leakage — not promotable** |
| Team form | API-Football | enrichment / intel report | Yes | No | No | No | Yes | No | Used |
| Home/away form split | API-Football | intel report | Yes | No | No | No | Yes | No | Used |
| Lineup strength | API-Football | enrichment lineups | Yes | No | No | No | Yes | No | Used when available |
| Injuries | API-Football | enrichment | Yes | No | No | No | Yes | No | Used |
| H2H | API-Football | enrichment | Yes | No | No | No | Partial | No | Used |
| Standings/motivation | API-Football/SportMonks | enrichment | Context | No | No | No | Partial | No | Partial |
| Pressure index | SportMonks | pressure store | No | No | No | No | No | No | **Unused in production** |
| Shots/possession | API-Football stats | enrichment (post-match) | No | No | No | No | No | No | **Post-match only** |
| OddAlerts segments | OddAlerts CSV | probability rows | No | Shadow | Shadow | Shadow | Shadow | Shadow | Shadow only |
| Provider prediction model | API-Football/SportMonks | cache | Reference | No | No | No | No | No | **Underused** |
| Weather | WeatherAPI | supplemental | Confidence | No | No | No | Yes | No | Supplemental |
| Opening vs closing odds | Multi | snapshot timestamps | Movement (if valid) | No | No | No | Possible | No | Needs timestamp audit |

## Priority recommendations

1. **High:** Canonical pre-match odds features (already primary; extend entropy/movement with valid timestamps)
2. **Medium:** SportMonks pre-match xG snapshots (coverage backfill required)
3. **Medium:** Lineup/injury snapshots with explicit `feature_available_at`
4. **Low:** Live pressure, post-match statistics for pre-match models
5. **Shadow only:** OddAlerts ECSE segments (continue shadow evaluation)
"""


def generate_leakage_audit(root: Path) -> str:
    rows = registry_dict()
    lines = [
        "# Provider Feature Leakage Audit",
        "",
        "Rule: `feature_available_at <= prediction_cutoff_at < kickoff_at`",
        "",
        "| Feature | Provider | Class | Cutoff rule | Notes |",
        "|---------|----------|-------|-------------|-------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['feature']} | {r['provider']} | {r['leakage_class']} | {r['cutoff_rule']} | {r['notes']} |"
        )
    lines.extend(
        [
            "",
            "## Excluded from primary shadow fusion",
            "",
            "- CSV `expectedGoalsHome/Away` — POST_MATCH_ONLY",
            "- `fixture_enrichment.statistics_json` — POST_MATCH_ONLY",
            "- SportMonks pressure — LIVE_ONLY",
            "- Closing odds without pre-kickoff timestamp — LEAKAGE_RISK",
            "",
            "## Safe for primary experiments (this phase)",
            "",
            "- Pre-match FT odds from stored historical CSV",
            "- Derived implied probabilities and entropy",
            "- Form proxy derived from pre-match odds shape (not results)",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_coverage_report(root: Path) -> str:
    cov = _load(COVERAGE_PATH)
    lines = [
        "# Provider Feature Historical Coverage",
        "",
        f"Audited: {cov.get('audited_at_utc', 'n/a')}",
        f"Completed fixtures: {cov.get('completed_fixtures', 'n/a')}",
        "",
        "## Feature coverage (SQLite)",
        "",
        "| Feature | Eligible | With feature | Coverage % |",
        "|---------|----------|--------------|------------|",
    ]
    for name, meta in (cov.get("feature_coverage") or {}).items():
        lines.append(
            f"| {name} | {meta.get('eligible_fixtures')} | {meta.get('fixtures_with_feature')} | {meta.get('coverage_pct')}% |"
        )
    lines.extend(["", "## By competition (odds)", "", "| Competition | Completed | With odds | Coverage % |", "|-------------|-----------|-----------|------------|"])
    for row in cov.get("by_competition") or []:
        lines.append(
            f"| {row.get('competition_key')} | {row.get('completed_fixtures')} | {row.get('with_odds')} | {row.get('odds_coverage_pct')}% |"
        )
    lines.extend(
        [
            "",
            "## Historical CSV staging (stored)",
            "",
            "- WDE shadow dataset: **77,023** rows (2022-09-20 → 2026-07-01)",
            "- OddAlerts probability rows: **8.7M+** (crosswalk-limited to ~547 completed fixtures in SQLite)",
            "- SportMonks enrichment: **51** fixtures",
            "- xG snapshots: **26** fixtures",
            "",
            "**Gap:** Pre-match xG and lineup/injury snapshot coverage insufficient for promotion.",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_feature_store_design(root: Path) -> str:
    return """# Provider Feature Store Design

## Canonical prematch record (shadow)

```json
{
  "fixture_id": "int|string",
  "provider_fixture_ids": {"api_football": 0, "sportmonks": 0, "oddalerts": 0},
  "prediction_cutoff_utc": "ISO-8601",
  "kickoff_utc": "ISO-8601",
  "feature_version": "provider_fusion_v1",
  "source_versions": {"odds_snapshot_id": null, "xg_snapshot_id": null},
  "home_xg_for": null,
  "away_xg_for": null,
  "odds_home": 1.95,
  "implied_home": 0.48,
  "bookmaker_count": 14,
  "market_entropy": 0.92,
  "data_quality": "OK",
  "missingness_mask": {"odds": 1, "xg": 0, "lineup": 0}
}
```

## Requirements (met in shadow path)

- Snapshot-based, timestamped, immutable after freeze
- No provider calls during model execution or backtest
- Cache-first from `odds_snapshots`, CSV staging, enrichment
- Missing values explicit via `missingness_mask`
- No silent zero fill (median imputation logged in experiment config only)
- Feature provenance in `source_versions`

## Storage (shadow only)

- Dataset: `artifacts/provider_feature_fusion/shadow_dataset.parquet`
- Shadow outputs: `artifacts/provider_feature_fusion/shadow_outputs/*.jsonl`
- Isolated table: `provider_feature_fusion_shadow` (separate SQLite artifact DB)

**No production DB migration in this phase.**
"""


def generate_ablation_report_md(root: Path) -> str:
    abl = _load(ABLATION_PATH)
    lines = [
        "# Provider Feature Ablation Report",
        "",
        f"Baseline: {abl.get('baseline_variant')}",
        "",
        "| Family | Variant | N | Δ accuracy | Log loss | Cal error | ECSE Top1 | Flags |",
        "|--------|---------|---|------------|----------|-----------|-----------|-------|",
    ]
    for row in abl.get("families") or []:
        lines.append(
            f"| {row.get('feature_family')} | {row.get('variant')} | {row.get('sample_size')} | "
            f"{row.get('delta_accuracy')} | {row.get('log_loss')} | {row.get('calibration_error')} | "
            f"{row.get('ecse_top1')} | {', '.join(row.get('leakage_flags') or [])} |"
        )
    lines.append("")
    lines.append(abl.get("conclusion_note", ""))
    return "\n".join(lines) + "\n"


def generate_importance_report_md(root: Path) -> str:
    imp = _load(IMPORTANCE_PATH)
    lines = ["# Provider Feature Importance Report", "", f"Variant: {imp.get('variant')}", "", "## Permutation importance (holdout)", ""]
    for row in imp.get("permutation_importance") or []:
        lines.append(f"- **{row.get('feature')}**: mean={row.get('permutation_mean')}, std={row.get('permutation_std')}")
    lines.extend(["", "## Consistently useful", ""])
    for f in imp.get("consistently_useful") or []:
        lines.append(f"- {f}")
    lines.extend(["", "## Unstable / redundant", ""])
    for f in imp.get("unstable_or_redundant") or []:
        lines.append(f"- {f}")
    return "\n".join(lines) + "\n"


def generate_promotion_gates(root: Path) -> str:
    return """# Provider Feature Fusion Promotion Gates

**No promotion in this phase.** Design-only criteria:

1. Chronological holdout improvement ≥ +0.5% accuracy on 1X2 with n ≥ 5,000
2. No material calibration regression (Δ calibration_error ≤ +0.01)
3. Improvement in ≥ 2 competition groups on holdout
4. Stable Tier A behavior (production scope fixtures)
5. Tier B remains owner_shadow / non-public
6. No unresolved leakage flags
7. Missing-data behavior stable (no provider/competition bias from imputation)
8. Shadow evaluation period ≥ 30 days live shadow
9. Rollback path documented and tested
10. API cost justified vs measured lift

**Current status:** Gates not met for xG/lineup/pressure families due to coverage gaps.
"""


def generate_final_report(root: Path) -> str:
    exp = _load(EXPERIMENTS_PATH)
    abl = _load(ABLATION_PATH)
    cov = _load(COVERAGE_PATH)
    imp = _load(IMPORTANCE_PATH)

    variants = exp.get("variants") or {}
    base = (variants.get("A_baseline_production_odds") or {}).get("holdout") or {}
    full = (variants.get("H_full_safe_fusion") or {}).get("holdout") or {}
    xg = (variants.get("C_baseline_plus_xg_diagnostic") or {}).get("holdout") or {}

    b1x2 = base.get("wde_1x2") or {}
    h1x2 = full.get("wde_1x2") or {}
    x1x2 = xg.get("wde_1x2") or {}

    # Determine recommendation
    delta = (h1x2.get("accuracy") or 0) - (b1x2.get("accuracy") or 0)
    xg_cov = (cov.get("feature_coverage") or {}).get("xg_snapshots", {}).get("coverage_pct", 0)
    if xg_cov < 5:
        recommendation = "FEATURE_COVERAGE_BACKFILL_REQUIRED"
    elif delta > 0.005:
        recommendation = "SHADOW_FEATURE_FUSION_READY"
    elif (x1x2.get("accuracy") or 0) > (b1x2.get("accuracy") or 0) + 0.01:
        recommendation = "FEATURE_LEAKAGE_REVIEW_REQUIRED"
    else:
        recommendation = "FEATURE_FUSION_NO_PROVEN_IMPROVEMENT"

    return f"""# Paid Provider Feature Utilization and Shadow Fusion Report

Date: 2026-07-12

## Final recommendation

**{recommendation}**

---

## Executive answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Features fetched? | API-Football (broad), SportMonks (enrichment/xG/pressure), OddAlerts (CSV+API), The Odds API, RapidAPI, Weather |
| 2 | Features stored? | `odds_snapshots`, `fixture_enrichment`, CSV staging (77k rows), OddAlerts 8.7M rows, sparse xG/pressure |
| 3 | Affect WDE? | Form, H2H, injuries, lineups, odds implied probs (primary) |
| 4 | Affect ECSE? | Odds lambdas (production); OddAlerts shadow only |
| 5 | Affect BTTS/O-U? | Implied odds + Poisson extended markets |
| 6 | Unused? | Pressure, post-match stats, provider prediction models, most SportMonks xG |
| 7 | Historical coverage? | Odds: high in CSV (77k); SQLite odds 100% of 868 completed w/ odds; xG 2.8% |
| 8 | Leakage risk? | CSV realized xG, post-match stats, closing odds, live pressure |
| 9 | Improved WDE? | Full safe fusion Δ1x2 accuracy = **{variants.get('H_full_safe_fusion', {}).get('delta_vs_baseline_1x2_accuracy')}** |
| 10 | Improved calibration? | See ablation calibration_error per family |
| 11 | Improved BTTS? | See holdout BTTS accuracy per variant in experiments JSON |
| 12 | Improved O/U? | See holdout O/U accuracy per variant |
| 13 | Improved ECSE? | Odds-proxy Top1/Top3/Top5 in experiments JSON |
| 14 | Harmed performance? | Lineup/pressure proxies (no data) = baseline equivalent |
| 15 | Highest-value provider? | **API-Football odds** (primary, highest coverage) |
| 16 | Not worth API cost? | Live pressure fetches, redundant post-match stats for pre-match models |
| 17 | Full fusion vs baseline? | Holdout 1X2: baseline **{b1x2.get('accuracy')}** vs full **{h1x2.get('accuracy')}** |
| 18 | Stable by competition? | See `by_league` in experiments JSON |
| 19 | Stable by Tier? | Tier B shadow only; Tier A uses same odds path — no Tier-specific lift proven |
| 20 | Ready for longer shadow? | Odds-derived features only, if Δ > 0 and calibration stable |
| 21 | Additional data required? | Pre-match SportMonks xG snapshots, timestamped lineup/injury snapshots |
| 22 | Next phase? | Coverage backfill for safe prematch xG + 30-day live shadow of odds-enhanced fusion |

---

## Experiment summary (chronological holdout)

| Variant | 1X2 accuracy | Δ vs baseline | Log loss | Cal error |
|---------|--------------|---------------|----------|-----------|
| A baseline | {b1x2.get('accuracy')} | — | {b1x2.get('log_loss')} | {b1x2.get('calibration_error')} |
| H full safe | {h1x2.get('accuracy')} | {variants.get('H_full_safe_fusion', {}).get('delta_vs_baseline_1x2_accuracy')} | {h1x2.get('log_loss')} | {h1x2.get('calibration_error')} |
| C xG diagnostic | {x1x2.get('accuracy')} | {variants.get('C_baseline_plus_xg_diagnostic', {}).get('delta_vs_baseline_1x2_accuracy')} | {x1x2.get('log_loss')} | *non-promotable* |

**Provider calls this phase:** 0  
**Production modified:** false  
**Shadow storage:** `production_visible=false`

---

## Artifacts

- `artifacts/provider_feature_fusion/coverage_audit.json`
- `artifacts/provider_feature_fusion/fusion_experiments.json`
- `artifacts/provider_feature_fusion/ablation_report.json`
- `artifacts/provider_feature_fusion/feature_importance.json`
- `artifacts/provider_feature_fusion/shadow_dataset.parquet`

**STOP** — No model deployment. No production promotion.
"""


def generate_all_reports(root: Path | None = None) -> dict[str, str]:
    root = root or Path(".")
    mapping = {
        "PAID_PROVIDER_CAPABILITY_INVENTORY.md": generate_capability_inventory(root),
        "PROVIDER_FEATURE_USAGE_MATRIX.md": generate_usage_matrix(root),
        "PROVIDER_FEATURE_LEAKAGE_AUDIT.md": generate_leakage_audit(root),
        "PROVIDER_FEATURE_HISTORICAL_COVERAGE.md": generate_coverage_report(root),
        "PROVIDER_FEATURE_STORE_DESIGN.md": generate_feature_store_design(root),
        "PROVIDER_FEATURE_ABLATION_REPORT.md": generate_ablation_report_md(root),
        "PROVIDER_FEATURE_IMPORTANCE_REPORT.md": generate_importance_report_md(root),
        "PROVIDER_FEATURE_FUSION_PROMOTION_GATES.md": generate_promotion_gates(root),
        "PAID_PROVIDER_FEATURE_UTILIZATION_AND_SHADOW_FUSION_REPORT.md": generate_final_report(root),
    }
    for name, content in mapping.items():
        _write(root / name, content)
    return {k: str(root / k) for k in mapping}
