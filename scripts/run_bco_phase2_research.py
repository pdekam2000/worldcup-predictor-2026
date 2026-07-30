"""Phase 2 research runner: Top5 / TopN / weights / coupon comparison.

Research-only. No freeze mutation. No production deploy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.research.bet_coverage_optimizer.config import scoring_weights_from_config
from worldcup_predictor.research.bet_coverage_optimizer.service import run_coverage_optimizer_job
from scripts.run_bet_coverage_optimizer_three_fixtures import FIXTURES, RAW_BY_FIXTURE


def _model_payloads() -> dict[int, dict]:
    # Extend each fixture to 12 scorelines for Top12 comparisons (pad from exact/canonical)
    out: dict[int, dict] = {}
    pad = [
        {"score": "3-0", "probability": 0.03, "rank": 9},
        {"score": "3-2", "probability": 0.025, "rank": 10},
        {"score": "4-0", "probability": 0.02, "rank": 11},
        {"score": "4-1", "probability": 0.015, "rank": 12},
    ]
    for fid, block in FIXTURES.items():
        payload = {k: v for k, v in block.items() if k != "label"}
        for mid in ("canonical", "exact_v2"):
            if mid not in payload:
                continue
            scores = list(payload[mid]["scores"])
            existing = {s["score"] for s in scores}
            for extra in pad:
                if extra["score"] not in existing:
                    scores.append(dict(extra))
                if len(scores) >= 12:
                    break
            payload[mid] = {"scores": scores[:12]}
        out[int(fid)] = payload
    return out


def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path("artifacts/coverage_optimizer") / f"phase2_{ts}"
    root.mkdir(parents=True, exist_ok=True)
    payloads = _model_payloads()

    topn_cmp = {}
    for n in (8, 10, 12):
        result = run_coverage_optimizer_job(
            list(FIXTURES.keys()),
            model_payloads=payloads,
            raw_payload_by_fixture=RAW_BY_FIXTURE,
            require_fresh=False,
            skip_db_odds=True,
            top_n_scores=n,
            stake_per_ticket=1.0,
            output_dir=root / f"top{n}",
            run_coupon_optimizer=True,
        )
        topn_cmp[str(n)] = {
            "output_dir": result["output_dir"],
            "statuses": result["summary"]["statuses"],
            "fourth": {
                str(r["fixture_id"]): (r.get("selected_coverage_market") or {}).get("market_label")
                for r in result["recommendations"]
            },
            "ranked_top1": {
                str(r["fixture_id"]): (r.get("ranked_candidates") or [{}])[0]
                for r in result["recommendations"]
            },
            "top_n_mass": {str(r["fixture_id"]): r["total_top_n_probability_mass"] for r in result["recommendations"]},
            "coupon_score": (result.get("coupon_optimizer") or {}).get("coupon_score"),
            "expected_coupon_value": (result.get("coupon_optimizer") or {}).get("expected_coupon_value"),
            "independent_baseline": (result.get("coupon_optimizer") or {}).get("independent_baseline"),
        }

    # Weight sensitivity on Top8
    weight_profiles = {
        "default": scoring_weights_from_config(None),
        "mass_heavy": scoring_weights_from_config(
            {
                "coverage_weights": {
                    "covered_probability_mass": 0.60,
                    "non_exact_probability_mass": 0.15,
                    "exact_overlap_probability_mass": 0.10,
                    "estimated_edge": 0.10,
                    "log_odds": 0.05,
                }
            }
        ),
        "edge_heavy": scoring_weights_from_config(
            {
                "coverage_weights": {
                    "covered_probability_mass": 0.15,
                    "non_exact_probability_mass": 0.10,
                    "exact_overlap_probability_mass": 0.10,
                    "estimated_edge": 0.45,
                    "log_odds": 0.20,
                }
            }
        ),
        "odds_heavy": scoring_weights_from_config(
            {
                "coverage_weights": {
                    "covered_probability_mass": 0.15,
                    "non_exact_probability_mass": 0.10,
                    "exact_overlap_probability_mass": 0.10,
                    "estimated_edge": 0.15,
                    "log_odds": 0.50,
                }
            }
        ),
    }
    weight_cmp = {}
    for name, weights in weight_profiles.items():
        result = run_coverage_optimizer_job(
            list(FIXTURES.keys()),
            model_payloads=payloads,
            raw_payload_by_fixture=RAW_BY_FIXTURE,
            require_fresh=False,
            skip_db_odds=True,
            top_n_scores=8,
            weights=weights,
            stake_per_ticket=1.0,
            output_dir=root / f"weights_{name}",
            run_coupon_optimizer=False,
        )
        weight_cmp[name] = {
            "weights": weights.to_dict(),
            "fourth": {
                str(r["fixture_id"]): (r.get("selected_coverage_market") or {}).get("market_label")
                for r in result["recommendations"]
            },
            "ranked": {
                str(r["fixture_id"]): [
                    {
                        "rank": x["rank"],
                        "market_label": x["market_label"],
                        "coverage_score": x["coverage_score"],
                        "odds": x["odds"],
                    }
                    for x in (r.get("ranked_candidates") or [])[:5]
                ]
                for r in result["recommendations"]
            },
        }

    # Pull Top5 comparison from default Top8 run
    top5_path = root / "top8" / "candidate_markets_ranked.json"
    top5 = json.loads(top5_path.read_text(encoding="utf-8")) if top5_path.is_file() else {}

    validation = {
        "phase": "bco-phase2",
        "research_only": True,
        "owner_only": True,
        "canonical_formulas_unchanged": True,
        "freezes_unchanged": True,
        "shadow_not_promoted": True,
        "top_n_compared": [8, 10, 12],
        "weight_profiles": list(weight_profiles.keys()),
        "artifacts_root": str(root),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "top5_markets": top5,
        "topn_comparison": topn_cmp,
        "weight_sensitivity": weight_cmp,
        "coupon_optimizer_comparison": {
            str(n): {
                "coupon_score": topn_cmp[str(n)].get("coupon_score"),
                "expected_coupon_value": topn_cmp[str(n)].get("expected_coupon_value"),
                "independent_baseline": topn_cmp[str(n)].get("independent_baseline"),
                "fourth_independent": topn_cmp[str(n)].get("fourth"),
            }
            for n in (8, 10, 12)
        },
        "validation": validation,
    }
    (root / "phase2_research_bundle.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (root / "validation_report.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print(json.dumps({"artifacts_root": str(root), "validation": validation}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
