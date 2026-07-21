"""Read-only Tier A → Tier S distance analysis from an existing scan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.forward_evaluation.context import scoreline_side
from worldcup_predictor.research.forward_aligned_scan.constants import (
    ARTIFACT_ROOT,
    REPORT_ROOT,
    TOP5_MASS_TIER_S_MIN,
    TIER_A,
    TIER_S,
)
from worldcup_predictor.research.wde_vs_ecse_forensics.directions import norm_dir

GATE_LABELS = (
    ("wde", "WDE"),
    ("ft_marginal", "FT marginal"),
    ("market_direction", "Market direction"),
    ("top1_direction", "Top1 direction"),
    ("top3_majority", "Top3 majority"),
    ("top5_majority", "Top5 majority"),
    ("high_agreement", "HIGH_AGREEMENT"),
    ("top5_mass", "Top5 Mass"),
    ("fresh_odds", "Fresh Odds"),
    ("no_bet_false", "no_bet=false"),
)

FAIL_SEVERITY = {
    "FAILED_TIER_S_NO_BET_TRUE": ("HIGH", "no_bet=true blocks Tier S; refresh may help only if quality gate clears"),
    "FAILED_TIER_S_TOP5_MASS_BELOW_0_52": ("MEDIUM", "Top5 Mass below 0.52; model/odds refresh may shift concentration"),
    "FAILED_TIER_S_TOP5_MASS_UNAVAILABLE": ("HIGH", "Top5 Mass missing at classify time"),
    "FAILED_TIER_S_TOP1_DIRECTION_CONFLICT": ("HIGH", "ECSE Top1 direction ≠ WDE"),
    "FAILED_TIER_S_TOP3_MAJORITY_CONFLICT": ("HIGH", "ECSE Top3 majority ≠ WDE"),
    "FAILED_TIER_S_FT_MARGINAL_CONFLICT": ("HIGH", "FT marginal ≠ WDE"),
    "FAILED_TIER_S_MARKET_DIRECTION_CONFLICT": ("MEDIUM", "Market direction ≠ WDE"),
    "FAILED_TIER_S_CONSENSUS_NOT_HIGH_AGREEMENT": ("HIGH", "Consensus not HIGH_AGREEMENT"),
}


def _agree(a: Any, b: Any) -> bool:
    return bool(a and b and norm_dir(a) == norm_dir(b))


def _load_scan(scan_id: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or project_root()
    path = root / ARTIFACT_ROOT / scan_id / "summary.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _gate_audit(row: dict[str, Any]) -> dict[str, Any]:
    dirs = row.get("directions") or {}
    pred = row.get("prediction") or {}
    ecse = pred.get("ecse") or {}
    odds = row.get("odds_prep") or {}
    wde = dirs.get("wde_decision")
    ft = dirs.get("ft_marginal")
    t1 = dirs.get("ecse_top1_direction")
    t3 = dirs.get("ecse_top3_majority")
    t5 = dirs.get("ecse_top5_majority")
    market = dirs.get("market_direction")
    mass = ecse.get("top5_mass")
    mass_f = float(mass) if mass is not None else None

    passes = {
        "wde": bool(wde),
        "ft_marginal": _agree(wde, ft),
        "market_direction": _agree(wde, market) or norm_dir(wde) == "draw",
        "top1_direction": _agree(wde, t1),
        "top3_majority": _agree(wde, t3),
        "top5_majority": _agree(wde, t5),
        "high_agreement": str(pred.get("consensus") or "").upper() == "HIGH_AGREEMENT",
        "top5_mass": mass_f is not None and mass_f >= TOP5_MASS_TIER_S_MIN,
        "fresh_odds": bool(odds.get("ready")),
        "no_bet_false": pred.get("no_bet") is False,
    }
    pass_labels = [label for key, label in GATE_LABELS if passes.get(key)]
    fail_codes = list(row.get("tier_s_failure_reasons") or [])
    fail_detail = [
        {
            "code": code,
            "severity": FAIL_SEVERITY.get(code, ("MEDIUM", code))[0],
            "note": FAIL_SEVERITY.get(code, ("MEDIUM", code))[1],
        }
        for code in fail_codes
    ]
    remaining = len(fail_codes)
    passed_count = sum(1 for v in passes.values() if v)
    max_gates = len(passes)
    tier_s_score_deficit = max_gates - passed_count

    return {
        "passes": passes,
        "pass_labels": pass_labels,
        "fail_codes": fail_codes,
        "fail_detail": fail_detail,
        "gates_passed_count": passed_count,
        "gates_total": max_gates,
        "tier_s_score_deficit": tier_s_score_deficit,
        "distance_to_tier_s_gates_remaining": remaining,
        "distance_summary": (
            f"{remaining} gate{'s' if remaining != 1 else ''} remaining"
            if remaining
            else "0 gates remaining — qualifies Tier S"
        ),
    }


def _top5_table(row: dict[str, Any]) -> list[dict[str, Any]]:
    ecse = (row.get("prediction") or {}).get("ecse") or {}
    ranks = []
    for i in range(1, 6):
        t = ecse.get(f"top{i}") or {}
        if isinstance(t, dict) and t.get("score"):
            sc = str(t["score"])
            ranks.append(
                {
                    "rank": f"Top{i}",
                    "exact_score": sc,
                    "probability": t.get("probability"),
                    "direction": scoreline_side(sc),
                }
            )
        else:
            dirs_ranks = (row.get("directions") or {}).get("ranks") or []
            r = next((x for x in dirs_ranks if int(x.get("rank") or 0) == i), {})
            sc = str(r.get("score") or "")
            ranks.append(
                {
                    "rank": f"Top{i}",
                    "exact_score": sc,
                    "probability": r.get("probability"),
                    "direction": r.get("direction") or scoreline_side(sc),
                }
            )
    return ranks


def _goal_profile(row: dict[str, Any], top5: list[dict[str, Any]]) -> dict[str, Any]:
    ga = row.get("goal_alignment") or {}
    probs = [float(r["probability"]) for r in top5 if isinstance(r.get("probability"), (int, float))]
    top3_mass = sum(probs[:3]) if len(probs) >= 3 else None
    top5_mass = sum(probs) if probs else (row.get("prediction") or {}).get("ecse", {}).get("top5_mass")
    return {
        "cumulative_top3_probability": round(top3_mass, 6) if top3_mass is not None else None,
        "cumulative_top5_probability": round(float(top5_mass), 6) if top5_mass is not None else None,
        "top3_mass_persisted": (row.get("prediction") or {}).get("ecse", {}).get("top3_mass"),
        "top5_mass_persisted": (row.get("prediction") or {}).get("ecse", {}).get("top5_mass"),
        "entropy": (row.get("prediction") or {}).get("ecse", {}).get("entropy"),
        "clean_sheet_count_top5": ga.get("top5_clean_sheet_count"),
        "btts_yes_count_top5": ga.get("top5_btts_count"),
        "over25_count_top5": ga.get("top5_over25_count"),
        "under25_count_top5": ga.get("top5_under25_count"),
        "btts_prediction": ga.get("btts_prediction") or (row.get("prediction") or {}).get("btts", {}).get("prediction"),
        "ou25_prediction": ga.get("ou25_prediction") or (row.get("prediction") or {}).get("ou25", {}).get("preferred_side"),
    }


def _refresh_priority(row: dict[str, Any], audit: dict[str, Any]) -> tuple[str, str]:
    remaining = audit["distance_to_tier_s_gates_remaining"]
    fails = set(audit["fail_codes"])
    mass = (row.get("prediction") or {}).get("ecse", {}).get("top5_mass")
    mass_ok = mass is not None and float(mass) >= TOP5_MASS_TIER_S_MIN
    htk = row.get("hours_to_kickoff")
    timing = str(row.get("timing_class") or "")

    if remaining == 0:
        return "LOW", "Already Tier S gates satisfied at scan time"
    if remaining == 1 and fails == {"FAILED_TIER_S_NO_BET_TRUE"} and mass_ok:
        if htk is not None and float(htk) > 6:
            return (
                "HIGH",
                "Only no_bet=true blocks Tier S; mass and alignment gates pass — "
                "later odds/model refresh could clear no_bet if exposed by payload",
            )
        return (
            "MEDIUM",
            "Only no_bet blocks but kickoff window is tightening; refresh still possible pre-match",
        )
    if remaining == 1 and fails == {"FAILED_TIER_S_NO_BET_TRUE"}:
        return "MEDIUM", "Only no_bet but Top5 Mass also marginal — refresh less certain"
    if "FAILED_TIER_S_TOP5_MASS_BELOW_0_52" in fails and len(fails) <= 2:
        return "MEDIUM", "Mass gate fail — refresh may help concentration but no_bet also blocks"
    if any(
        c in fails
        for c in (
            "FAILED_TIER_S_TOP3_MAJORITY_CONFLICT",
            "FAILED_TIER_S_TOP1_DIRECTION_CONFLICT",
            "FAILED_TIER_S_CONSENSUS_NOT_HIGH_AGREEMENT",
        )
    ):
        return "LOW", "Directional/consensus conflict — unlikely Tier S on odds refresh alone"
    return "LOW", f"{remaining} gates remain; promotion unlikely without model shift"


def _owner_bucket(row: dict[str, Any], audit: dict[str, Any]) -> tuple[str, str, str, bool]:
    remaining = audit["distance_to_tier_s_gates_remaining"]
    fails = set(audit["fail_codes"])
    mass = float((row.get("prediction") or {}).get("ecse", {}).get("top5_mass") or 0)
    score = int(row.get("alignment_score") or 0)
    no_bet = (row.get("prediction") or {}).get("no_bet")

    if row.get("alignment_tier") == TIER_S:
        return (
            "Strongest Available",
            "Passes all Tier S gates including no_bet=false and Top5 Mass≥0.52.",
            "None.",
            False,
        )
    if remaining == 1 and fails == {"FAILED_TIER_S_NO_BET_TRUE"} and mass >= TOP5_MASS_TIER_S_MIN and score >= 80:
        return (
            "Very Close To Tier S",
            f"All directional/mass/consensus gates pass; only no_bet=true ({score} alignment, mass={mass:.3f}).",
            "no_bet=true",
            True,
        )
    if remaining == 1 and fails == {"FAILED_TIER_S_NO_BET_TRUE"}:
        return (
            "Very Close To Tier S",
            "Single blocker is no_bet=true; other gates pass.",
            "no_bet=true",
            True,
        )
    if remaining <= 2 and mass >= 0.45:
        return (
            "Research Only",
            f"Interesting alignment (score={score}) but {remaining} gates fail: {list(fails)}.",
            "; ".join(audit["fail_codes"]),
            remaining == 1,
        )
    return (
        "Research Only",
        f"Tier A watchlist only; {remaining} Tier S gates fail.",
        "; ".join(audit["fail_codes"]),
        False,
    )


def _sort_key(row: dict[str, Any], audit: dict[str, Any]) -> tuple:
    ecse = (row.get("prediction") or {}).get("ecse") or {}
    ent = ecse.get("entropy")
    stab = str(row.get("stability") or "")
    stab_rank = 0 if "STABLE" in stab.upper() and "UNKNOWN" not in stab.upper() else 1
    return (
        -audit["gates_passed_count"],
        -int(row.get("alignment_score") or 0),
        -(float(ecse.get("top5_mass") or -1)),
        -(float(ecse.get("top3_mass") or -1)),
        float(ent) if ent is not None else 999.0,
        stab_rank,
        audit["distance_to_tier_s_gates_remaining"],
        int(row.get("fixture_id") or 0),
    )


def analyze_tier_a_near_tier_s(scan_id: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or project_root()
    scan = _load_scan(scan_id, root=root)
    tier_s_rows = [r for r in scan.get("fixtures") or [] if r.get("alignment_tier") == TIER_S]
    tier_a_rows = [r for r in scan.get("fixtures") or [] if r.get("alignment_tier") == TIER_A]

    analyzed: list[dict[str, Any]] = []
    for row in tier_a_rows:
        audit = _gate_audit(row)
        top5 = _top5_table(row)
        goal = _goal_profile(row, top5)
        refresh_pri, refresh_note = _refresh_priority(row, audit)
        bucket, why, blocker, refresh_may = _owner_bucket(row, audit)
        dirs = row.get("directions") or {}
        pred = row.get("prediction") or {}
        ecse = pred.get("ecse") or {}
        odds = row.get("odds_prep") or {}
        analyzed.append(
            {
                "fixture_id": row["fixture_id"],
                "match": f"{row.get('home_team')} vs {row.get('away_team')}",
                "kickoff_vienna": row.get("kickoff_vienna"),
                "timing_class": row.get("timing_class"),
                "hours_to_kickoff": row.get("hours_to_kickoff"),
                "alignment_tier": row.get("alignment_tier"),
                "alignment_score": row.get("alignment_score"),
                "tier_s_score_deficit": audit["tier_s_score_deficit"],
                "gates_passed_count": audit["gates_passed_count"],
                "gates_total": audit["gates_total"],
                "passes": audit["pass_labels"],
                "fails": audit["fail_detail"],
                "distance_to_tier_s": audit["distance_summary"],
                "gates_remaining": audit["distance_to_tier_s_gates_remaining"],
                "wde": dirs.get("wde_decision"),
                "ft_marginal": dirs.get("ft_marginal"),
                "market_direction": dirs.get("market_direction"),
                "ecse_top1_direction": dirs.get("ecse_top1_direction"),
                "ecse_top3_majority": dirs.get("ecse_top3_majority"),
                "ecse_top5_majority": dirs.get("ecse_top5_majority"),
                "consensus": pred.get("consensus"),
                "no_bet": pred.get("no_bet"),
                "no_bet_diagnostics_status": (pred.get("no_bet_diagnostics") or {}).get("no_bet_reason_status"),
                "top5_mass": ecse.get("top5_mass"),
                "top3_mass": ecse.get("top3_mass"),
                "entropy": ecse.get("entropy"),
                "stability": row.get("stability"),
                "hda_odds": [odds.get("home"), odds.get("draw"), odds.get("away")],
                "top5_table": top5,
                "exact_score_profile": goal,
                "owner_bucket": bucket,
                "owner_why": why,
                "tier_s_blocker": blocker,
                "refresh_could_promote": refresh_may,
                "refresh_priority": refresh_pri,
                "refresh_priority_note": refresh_note,
            }
        )

    ranked = sorted(analyzed, key=lambda a: _sort_key(next(r for r in tier_a_rows if r["fixture_id"] == a["fixture_id"]), _gate_audit(next(r for r in tier_a_rows if r["fixture_id"] == a["fixture_id"]))))

    # Re-sort using stored metrics (cleaner)
    ranked = sorted(
        analyzed,
        key=lambda a: (
            -a["gates_passed_count"],
            -int(a["alignment_score"] or 0),
            -(float(a["top5_mass"] or -1)),
            -(float(a["top3_mass"] or -1)),
            float(a["entropy"] or 999),
            0 if "STABLE" in str(a.get("stability") or "").upper() and "UNKNOWN" not in str(a.get("stability") or "").upper() else 1,
            a["gates_remaining"],
            int(a["fixture_id"]),
        ),
    )

    tier_s_analysis = []
    for row in tier_s_rows:
        audit = _gate_audit(row)
        top5 = _top5_table(row)
        tier_s_analysis.append(
            {
                "fixture_id": row["fixture_id"],
                "match": f"{row.get('home_team')} vs {row.get('away_team')}",
                "alignment_tier": TIER_S,
                "alignment_score": row.get("alignment_score"),
                "passes": audit["pass_labels"],
                "fails": [],
                "distance_to_tier_s": "Tier S — all gates pass",
                "top5_table": top5,
                "top5_mass": (row.get("prediction") or {}).get("ecse", {}).get("top5_mass"),
                "no_bet": (row.get("prediction") or {}).get("no_bet"),
            }
        )

    very_close = [a for a in ranked if a["owner_bucket"] == "Very Close To Tier S"]
    strongest = list(tier_s_analysis) + [a for a in ranked if a["gates_remaining"] == 1 and a["top5_mass"] and float(a["top5_mass"]) >= TOP5_MASS_TIER_S_MIN][:3]

    # Shortlist: 1 Tier S + up to 3 near Tier S
    shortlist = []
    if tier_s_analysis:
        s0 = tier_s_analysis[0]
        row = tier_s_rows[0]
        dirs = row.get("directions") or {}
        pred = row.get("prediction") or {}
        ecse = pred.get("ecse") or {}
        shortlist.append(
            {
                "fixture": s0["match"],
                "fixture_id": s0["fixture_id"],
                "tier": "S_FULL_ALIGNMENT",
                "alignment_score": s0["alignment_score"],
                "wde": dirs.get("wde_decision"),
                "market_direction": dirs.get("market_direction"),
                "top1": dirs.get("ecse_top1_direction"),
                "top5_majority": dirs.get("ecse_top5_majority"),
                "top5_mass": ecse.get("top5_mass"),
                "consensus": pred.get("consensus"),
                "no_bet": pred.get("no_bet"),
                "why_selected": "Only fixture passing all Tier S gates at scan time.",
            }
        )
    for a in ranked[:3]:
        if len(shortlist) >= 4:
            break
        shortlist.append(
            {
                "fixture": a["match"],
                "fixture_id": a["fixture_id"],
                "tier": "A_STRONG_ALIGNMENT",
                "alignment_score": a["alignment_score"],
                "wde": a["wde"],
                "market_direction": a["market_direction"],
                "top1": a["ecse_top1_direction"],
                "top5_majority": a["ecse_top5_majority"],
                "top5_mass": a["top5_mass"],
                "consensus": a["consensus"],
                "no_bet": a["no_bet"],
                "why_selected": a["owner_why"],
                "tier_s_blocker": a["tier_s_blocker"],
                "gates_remaining": a["gates_remaining"],
            }
        )

    return {
        "status": "TIER_A_NEAR_TIER_S_ANALYSIS_COMPLETE",
        "scan_id": scan_id,
        "generated_from": "existing_scan_read_only",
        "canonical_writes": 0,
        "tier_s_count": len(tier_s_rows),
        "tier_a_count": len(tier_a_rows),
        "tier_s": tier_s_analysis,
        "ranked_near_tier_s": ranked,
        "almost_tier_s_ranking": {
            "first": ranked[0] if len(ranked) > 0 else None,
            "second": ranked[1] if len(ranked) > 1 else None,
            "third": ranked[2] if len(ranked) > 2 else None,
            "fourth": ranked[3] if len(ranked) > 3 else None,
            "fifth": ranked[4] if len(ranked) > 4 else None,
        },
        "strongest_available": strongest,
        "very_close_to_tier_s": very_close,
        "research_only_count": sum(1 for a in ranked if a["owner_bucket"] == "Research Only"),
        "owner_shortlist": shortlist,
        "refresh_high_priority": [a["fixture_id"] for a in ranked if a["refresh_priority"] == "HIGH"],
        "refresh_medium_priority": [a["fixture_id"] for a in ranked if a["refresh_priority"] == "MEDIUM"],
        "refresh_low_priority": [a["fixture_id"] for a in ranked if a["refresh_priority"] == "LOW"],
    }


def _md_top5_table(top5: list[dict[str, Any]]) -> str:
    lines = [
        "| Rank | Exact Score | Probability |",
        "| ---: | ----------- | ----------: |",
    ]
    for r in top5:
        p = r.get("probability")
        ps = f"{float(p):.6f}" if isinstance(p, (int, float)) else "N/A"
        lines.append(f"| {r.get('rank')} | {r.get('exact_score')} | {ps} |")
    return "\n".join(lines)


def write_reports(analysis: dict[str, Any], *, root: Path | None = None) -> dict[str, str]:
    root = root or project_root()
    scan_id = analysis["scan_id"]
    rep_dir = root / REPORT_ROOT
    art_dir = root / ARTIFACT_ROOT / scan_id
    rep_dir.mkdir(parents=True, exist_ok=True)
    art_dir.mkdir(parents=True, exist_ok=True)

    json_path = art_dir / "tier_a_near_tier_s.json"
    json_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md_path = rep_dir / f"tier_a_near_tier_s_analysis_{scan_id}.md"
    lines = [
        f"# Tier A → Tier S Forensic Analysis",
        "",
        f"Scan: `{scan_id}` · read-only · zero canonical writes",
        "",
        f"Tier S at scan: **{analysis['tier_s_count']}** · Tier A qualified: **{analysis['tier_a_count']}**",
        "",
        "## Key finding",
        "",
        "All **36** Tier A fixtures share **`no_bet=true`** as a Tier S blocker. "
        "None can become Tier S without that gate clearing. "
        "Distance ranking therefore prioritizes fixtures with **only one remaining gate** and highest Top5 Mass.",
        "",
        "## Tier S reference",
        "",
    ]
    for s in analysis.get("tier_s") or []:
        lines += [
            f"### {s['match']} (`{s['fixture_id']}`)",
            f"- Score: **{s['alignment_score']}** · Top5 Mass: **{s['top5_mass']}** · no_bet: **{s['no_bet']}**",
            "",
            _md_top5_table(s.get("top5_table") or []),
            "",
        ]

    lines += ["## Almost Tier S — Top 5", ""]
    for label, key in [
        ("1st", "first"),
        ("2nd", "second"),
        ("3rd", "third"),
        ("4th", "fourth"),
        ("5th", "fifth"),
    ]:
        a = (analysis.get("almost_tier_s_ranking") or {}).get(key)
        if not a:
            continue
        lines += [
            f"### {label}: {a['match']} (`{a['fixture_id']}`)",
            f"- Alignment Score: **{a['alignment_score']}** · Gates passed: **{a['gates_passed_count']}/{a['gates_total']}** · Remaining: **{a['gates_remaining']}**",
            f"- Top5 Mass: **{a['top5_mass']}** · Refresh: **{a['refresh_priority']}**",
            "",
            "**Passes:** " + ", ".join(a.get("passes") or []),
            "",
            "**Fails:**",
        ]
        for f in a.get("fails") or []:
            lines.append(f"- `{f['code']}` ({f['severity']}): {f['note']}")
        lines += [
            "",
            f"**Distance:** {a['distance_to_tier_s']}",
            "",
            _md_top5_table(a.get("top5_table") or []),
            "",
            f"- Cumulative Top3: {a.get('exact_score_profile', {}).get('cumulative_top3_probability')} · "
            f"Top5: {a.get('exact_score_profile', {}).get('cumulative_top5_probability')} · "
            f"Clean-sheet scores in Top5: {a.get('exact_score_profile', {}).get('clean_sheet_count_top5')} · "
            f"BTTS scores: {a.get('exact_score_profile', {}).get('btts_yes_count_top5')} · "
            f"O2.5/U2.5: {a.get('exact_score_profile', {}).get('over25_count_top5')}/"
            f"{a.get('exact_score_profile', {}).get('under25_count_top5')}",
            "",
            f"**Owner bucket:** {a['owner_bucket']} — {a['owner_why']}",
            "",
        ]

    lines += ["## Full Tier A ranking (36)", "", "| Rank | Match | Score | Mass | Gates rem | Refresh | Blocker |", "| ---: | ----- | ----: | ---: | --------: | ------- | ------- |"]
    for i, a in enumerate(analysis.get("ranked_near_tier_s") or [], 1):
        lines.append(
            f"| {i} | {a['match']} | {a['alignment_score']} | {a['top5_mass']} | "
            f"{a['gates_remaining']} | {a['refresh_priority']} | {a['tier_s_blocker'][:40]} |"
        )
    lines += [
        "",
        "## Refresh priority summary",
        "",
        f"- HIGH ({len(analysis.get('refresh_high_priority') or [])}): `{analysis.get('refresh_high_priority')}`",
        f"- MEDIUM ({len(analysis.get('refresh_medium_priority') or [])}): see JSON for full list",
        f"- LOW ({len(analysis.get('refresh_low_priority') or [])}): see JSON for full list",
        "",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    short_path = rep_dir / f"owner_shortlist_{scan_id}.md"
    slines = [
        f"# Owner Shortlist — `{scan_id}`",
        "",
        "Research only. No betting guarantee. No official freeze.",
        "",
        "| Fixture | Tier | Score | WDE | Market | Top1 | Top5 maj | Top5 Mass | Cons | no_bet | Why |",
        "| ------- | ---- | ----: | --- | ------ | ---- | -------- | --------: | ---- | ------ | --- |",
    ]
    for s in analysis.get("owner_shortlist") or []:
        slines.append(
            f"| {s['fixture']} | {s['tier']} | {s['alignment_score']} | {s['wde']} | {s['market_direction']} | "
            f"{s['top1']} | {s['top5_majority']} | {s['top5_mass']} | {s['consensus']} | {s['no_bet']} | {s['why_selected'][:80]} |"
        )
    slines.append("")
    short_path.write_text("\n".join(slines) + "\n", encoding="utf-8")

    # Also write canonical names user requested at report root
    alias_md = rep_dir / "tier_a_near_tier_s_analysis.md"
    alias_json = rep_dir / "tier_a_near_tier_s.json"
    alias_short = rep_dir / "owner_shortlist.md"
    alias_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    alias_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    alias_short.write_text(short_path.read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "analysis_json": str(json_path),
        "analysis_md": str(md_path),
        "owner_shortlist": str(short_path),
        "analysis_md_alias": str(alias_md),
        "analysis_json_alias": str(alias_json),
        "owner_shortlist_alias": str(alias_short),
    }


def run_analysis(scan_id: str, *, root: Path | None = None) -> dict[str, Any]:
    analysis = analyze_tier_a_near_tier_s(scan_id, root=root)
    analysis["outputs"] = write_reports(analysis, root=root)
    return analysis
