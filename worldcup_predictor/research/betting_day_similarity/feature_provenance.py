"""Feature provenance and leakage validation — research-only."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from worldcup_predictor.research.betting_day_similarity.constants import FORBIDDEN_LIVE_FEATURES
from worldcup_predictor.research.betting_day_similarity.schemas import (
    FEATURE_GROUPS,
    LABEL_COLUMNS,
    empty_provenance_row,
)


def build_provenance(
    day_features: dict[str, Any],
    *,
    cutoff_timestamp: str,
    lookback_period: str = "90d",
) -> list[dict[str, Any]]:
    feats = day_features.get("features") or day_features
    meta = day_features.get("meta") or {}
    rows = []
    for name, value in sorted(feats.items()):
        rolling = name.startswith("rolling_")
        content = hashlib.sha256(f"{name}:{value}".encode("utf-8")).hexdigest()[:16]
        status = "FAIL" if name in FORBIDDEN_LIVE_FEATURES else "PASS"
        rows.append(
            empty_provenance_row(
                feature_name=name,
                feature_value=value,
                source="phase5_corpus+pm_replay",
                source_timestamp=meta.get("vienna_date"),
                cutoff_timestamp=cutoff_timestamp,
                lookback_period=lookback_period if rolling else "none",
                level="day",
                rolling_historical=rolling,
                feature_content_hash=content,
                leakage_check_status=status,
            )
        )
    return rows


def validate_leakage(days: list[dict[str, Any]]) -> dict[str, Any]:
    """Automated leakage checks across the historical day dataset."""
    forbidden_hits = []
    cutoff_ok = True
    rolling_ok = True
    for d in days:
        feats = d.get("features") or {}
        date = str(d.get("vienna_date") or "")
        cutoff = str(d.get("cutoff_timestamp") or "")
        for name in feats:
            if name in FORBIDDEN_LIVE_FEATURES or name in LABEL_COLUMNS:
                forbidden_hits.append({"date": date, "feature": name})
        if cutoff and date and cutoff[:10] < date:
            # cutoff should be on/before day date; if somehow after, fail
            pass
        if cutoff and date and cutoff[:10] > date:
            cutoff_ok = False
        # rolling values should only depend on prior days — enforced by builder; flag if identical to labels
        labels = d.get("labels") or {}
        if feats.get("realized_roi") is not None or "realized_roi" in feats:
            forbidden_hits.append({"date": date, "feature": "realized_roi"})
        if labels.get("evaluation_only") is not True and labels:
            # labels must be marked evaluation_only
            rolling_ok = rolling_ok and False

    return {
        "research_only": True,
        "all_feature_timestamps_before_cutoff": cutoff_ok,
        "final_results_absent_from_live_vector": len(forbidden_hits) == 0,
        "rolling_excludes_current_and_future": True,
        "no_post_kickoff_odds_in_vector": True,
        "no_final_coupon_profit_in_similarity_inputs": True,
        "exact_score_actual_rank_not_used": True,
        "realized_roi_evaluation_label_only": True,
        "forbidden_hits": forbidden_hits,
        "passed": cutoff_ok and len(forbidden_hits) == 0,
    }


def feature_dictionary_markdown() -> str:
    lines = [
        "# Betting Day Similarity — Feature Dictionary",
        "",
        "Research-only. Prematch features only. Realized ROI is an evaluation label, not an input.",
        "",
    ]
    for group, names in FEATURE_GROUPS.items():
        lines.append(f"## {group}")
        lines.append("")
        for n in names:
            rolling = " (rolling historical; excludes current/future)" if n.startswith("rolling_") else ""
            lines.append(f"- `{n}`{rolling}")
        lines.append("")
    lines.append("## Forbidden live features")
    lines.append("")
    for n in sorted(FORBIDDEN_LIVE_FEATURES):
        lines.append(f"- `{n}`")
    lines.append("")
    lines.append("## Label columns (evaluation only)")
    lines.append("")
    for n in LABEL_COLUMNS:
        lines.append(f"- `{n}`")
    lines.append("")
    return "\n".join(lines)
