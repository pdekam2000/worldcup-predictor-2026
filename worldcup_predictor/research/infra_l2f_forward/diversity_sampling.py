"""Phase 6 — deterministic diversity sampling for high-volume true-forward.

Uses only prematch-observable metadata. Reproducible via policy version + seed.
Never cherry-picks on model output or outcomes.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

SAMPLING_POLICY_VERSION = "l2f-hv-tf-sampling-v1"
DEFAULT_SEED = "phase6-true-forward-2026"
DEFAULT_DAILY_CAP = 100
MAX_LEAGUE_SHARE = 0.20


def _stable_rank_key(fixture_id: int, *, seed: str, policy_version: str) -> str:
    material = f"{policy_version}|{seed}|{int(fixture_id)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _sorted_eligible(eligible: list[dict[str, Any]], *, seed: str, policy_version: str) -> list[dict[str, Any]]:
    return sorted(
        eligible,
        key=lambda r: (_stable_rank_key(int(r["fixture_id"]), seed=seed, policy_version=policy_version), int(r["fixture_id"])),
    )


def sample_eligible_fixtures(
    eligible: list[dict[str, Any]],
    *,
    daily_cap: int = DEFAULT_DAILY_CAP,
    seed: str = DEFAULT_SEED,
    policy_version: str = SAMPLING_POLICY_VERSION,
    max_league_share: float = MAX_LEAGUE_SHARE,
) -> dict[str, Any]:
    """Select up to daily_cap fixtures with league diversity soft constraints.

    When fewer than daily_cap are eligible, all are selected.
    When more exist, rank by stable hash and fill while preferring
    league share ≤ max_league_share when alternatives remain.
    """
    cap = max(0, int(daily_cap))
    ranked = _sorted_eligible(list(eligible), seed=seed, policy_version=policy_version)
    eligible_ids = [int(r["fixture_id"]) for r in ranked]

    if cap <= 0:
        return {
            "sampling_policy_version": policy_version,
            "seed": seed,
            "daily_cap": cap,
            "max_league_share": max_league_share,
            "eligible_count": len(ranked),
            "selected_count": 0,
            "selected_fixture_ids": [],
            "non_selected_eligible_fixture_ids": eligible_ids,
            "selected": [],
            "league_distribution": {},
            "odds_strength_distribution": {},
            "market_balance_distribution": {},
            "expected_total_distribution": {},
            "reproducibility": {
                "hash_algorithm": "sha256",
                "rank_material": f"{policy_version}|{seed}|<fixture_id>",
            },
            "notes": [
                "Selection uses only prematch-observable metadata.",
                "Model outputs and outcomes are never used.",
                "no_bet is not a selection filter (known only post-prediction).",
            ],
        }

    if len(ranked) <= cap:
        selected = list(ranked)
    else:
        soft_cap = max(1, int(cap * float(max_league_share)))
        selected: list[dict[str, Any]] = []
        deferred: list[dict[str, Any]] = []
        league_counts: Counter[str] = Counter()

        # Pass 1 — prefer league diversity under soft share cap
        for row in ranked:
            league = str(row.get("competition_key") or "unknown")
            if league_counts[league] < soft_cap and len(selected) < cap:
                selected.append(row)
                league_counts[league] += 1
            else:
                deferred.append(row)

        # Pass 2 — fill remaining slots in stable hash order (may exceed soft share)
        for row in deferred:
            if len(selected) >= cap:
                break
            selected.append(row)

        selected = _sorted_eligible(selected[:cap], seed=seed, policy_version=policy_version)

    selected_ids = [int(r["fixture_id"]) for r in selected]
    selected_set = set(selected_ids)
    non_selected = [i for i in eligible_ids if i not in selected_set]

    def _dist(key: str) -> dict[str, int]:
        return dict(Counter(str(r.get(key) or "unknown") for r in selected))

    return {
        "sampling_policy_version": policy_version,
        "seed": seed,
        "daily_cap": cap,
        "max_league_share": max_league_share,
        "eligible_count": len(ranked),
        "selected_count": len(selected),
        "selected_fixture_ids": selected_ids,
        "non_selected_eligible_fixture_ids": non_selected,
        "selected": selected,
        "league_distribution": _dist("competition_key"),
        "odds_strength_distribution": _dist("odds_strength_bucket"),
        "market_balance_distribution": _dist("market_balance_bucket"),
        "expected_total_distribution": _dist("expected_total_bucket"),
        "reproducibility": {
            "hash_algorithm": "sha256",
            "rank_material": f"{policy_version}|{seed}|<fixture_id>",
            "proof_digest": hashlib.sha256(
                json.dumps(
                    {"policy": policy_version, "seed": seed, "ids": selected_ids},
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        },
        "notes": [
            "Selection uses only prematch-observable metadata.",
            "Model outputs and outcomes are never used.",
            "no_bet is not a selection filter (known only post-prediction).",
            "League share soft-cap applied only when alternatives exist.",
        ],
    }


def assert_reproducible(
    eligible: list[dict[str, Any]],
    *,
    daily_cap: int,
    seed: str = DEFAULT_SEED,
    policy_version: str = SAMPLING_POLICY_VERSION,
) -> bool:
    a = sample_eligible_fixtures(eligible, daily_cap=daily_cap, seed=seed, policy_version=policy_version)
    b = sample_eligible_fixtures(eligible, daily_cap=daily_cap, seed=seed, policy_version=policy_version)
    return a["selected_fixture_ids"] == b["selected_fixture_ids"] and a["reproducibility"]["proof_digest"] == b[
        "reproducibility"
    ]["proof_digest"]
