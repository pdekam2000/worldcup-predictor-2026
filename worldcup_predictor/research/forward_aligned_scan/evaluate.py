"""Post-match evaluation of a forward aligned scan (confirmed FT only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.context import scoreline_side
from worldcup_predictor.research.forward_aligned_scan.constants import ARTIFACT_ROOT, PROMOTION_MIN_CONFIRMED
from worldcup_predictor.research.forward_aligned_scan.directions import norm_dir
from worldcup_predictor.research.forward_aligned_scan.store import scan_dir, write_json


def evaluate_scan(scan_id: str, *, root: Path | None = None) -> dict[str, Any]:
    # Post-match loaders live in an optional forensics package; keep them lazy so
    # FAS unit tests collect from a clean checkout without that dependency.
    try:
        from worldcup_predictor.research.wde_vs_ecse_forensics.load import load_prod_fixture_results
        from worldcup_predictor.research.wde_vs_ecse_forensics.stats_ext import paired_mcnemar, rate_block
    except ImportError as exc:
        return {
            "status": "MISSING_OPTIONAL_FORENSICS_DEPS",
            "scan_id": scan_id,
            "error": str(exc),
            "hint": "Install/track wde_vs_ecse_forensics to run post-match evaluate_scan.",
        }

    root = root or project_root()
    d = scan_dir(scan_id, root)
    summary_path = d / "summary.json"
    if not summary_path.is_file():
        return {"status": "MISSING_SCAN", "scan_id": scan_id}

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    settings = get_settings()
    prod_results = load_prod_fixture_results(Path(settings.sqlite_path))

    rows = []
    pending = []
    for r in summary.get("fixtures") or []:
        if r.get("alignment_tier") not in {
            "S_FULL_ALIGNMENT",
            "A_STRONG_ALIGNMENT",
            "B_DIRECTIONAL_ALIGNMENT",
        }:
            continue
        fid = int(r["fixture_id"])
        res = prod_results.get(fid)
        if not res or not res.get("actual_score"):
            pending.append({"fixture_id": fid, "reason": "pending_or_missing_result"})
            continue
        actual = str(res["actual_score"])
        actual_dir = norm_dir(res.get("actual_1x2")) or scoreline_side(actual)
        dirs = r.get("directions") or {}
        pred = r.get("prediction") or {}
        ecse = pred.get("ecse") or {}
        scores = [str(x) for x in (ecse.get("scores") or [])]
        if len(scores) < 5:
            for i in range(1, 6):
                t = ecse.get(f"top{i}")
                sc = t.get("score") if isinstance(t, dict) else t
                if sc:
                    scores.append(str(sc))
        scores = scores[:5]
        rank = scores.index(actual) + 1 if actual in scores else None
        rows.append(
            {
                "fixture_id": fid,
                "alignment_tier": r.get("alignment_tier"),
                "actual_score": actual,
                "actual_1x2": actual_dir,
                "wde_hit": dirs.get("wde_decision") == actual_dir,
                "ecse_top1_dir_hit": dirs.get("ecse_top1_direction") == actual_dir,
                "ecse_top5_maj_hit": dirs.get("ecse_top5_majority") == actual_dir,
                "agree": dirs.get("wde_decision") == dirs.get("ecse_top5_majority"),
                "top1_hit": rank == 1,
                "top3_hit": rank is not None and rank <= 3,
                "top5_hit": rank is not None and rank <= 5,
            }
        )

    n = len(rows)
    by_tier: dict[str, Any] = {}
    for tier in ("S_FULL_ALIGNMENT", "A_STRONG_ALIGNMENT", "B_DIRECTIONAL_ALIGNMENT"):
        subset = [r for r in rows if r["alignment_tier"] == tier]
        by_tier[tier] = {
            "n": len(subset),
            "wde": rate_block(sum(1 for r in subset if r["wde_hit"]), len(subset)),
            "ecse_top5_maj": rate_block(sum(1 for r in subset if r["ecse_top5_maj_hit"]), len(subset)),
            "top5_exact": rate_block(sum(1 for r in subset if r["top5_hit"]), len(subset)),
        }

    out = {
        "scan_id": scan_id,
        "confirmed_n": n,
        "pending_n": len(pending),
        "pending": pending,
        "overall": {
            "wde": rate_block(sum(1 for r in rows if r["wde_hit"]), n),
            "ecse_top1_dir": rate_block(sum(1 for r in rows if r["ecse_top1_dir_hit"]), n),
            "ecse_top5_maj": rate_block(sum(1 for r in rows if r["ecse_top5_maj_hit"]), n),
            "agreement_rule": rate_block(
                sum(1 for r in rows if r["agree"] and r["wde_hit"]),
                sum(1 for r in rows if r["agree"]),
            ),
            "exact_top1": rate_block(sum(1 for r in rows if r["top1_hit"]), n),
            "exact_top3": rate_block(sum(1 for r in rows if r["top3_hit"]), n),
            "exact_top5": rate_block(sum(1 for r in rows if r["top5_hit"]), n),
            "mcnemar_wde_vs_top5_maj": paired_mcnemar(
                [r["wde_hit"] for r in rows],
                [r["ecse_top5_maj_hit"] for r in rows],
            ),
        },
        "by_tier": by_tier,
        "promotion_gate": {
            "min_confirmed_required": PROMOTION_MIN_CONFIRMED,
            "confirmed_n": n,
            "eligible_for_promotion_review": n >= PROMOTION_MIN_CONFIRMED,
            "auto_promote": False,
            "note": "Do not promote until n>=200, meaningful coverage, significant lift, owner approval.",
        },
        "rows": rows,
    }
    write_json(d / "evaluation.json", out)
    return out
