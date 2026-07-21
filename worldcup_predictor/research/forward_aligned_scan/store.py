"""Artifact persistence for forward aligned scan (research-only)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.research.forward_aligned_scan.constants import ARTIFACT_ROOT, REPORT_ROOT


def scan_dir(scan_id: str, root: Path | None = None) -> Path:
    return (root or project_root()) / ARTIFACT_ROOT / scan_id


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    cols = fields or sorted({k for r in rows for k in r.keys()})
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            flat = {}
            for k in cols:
                v = r.get(k)
                flat[k] = json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v
            w.writerow(flat)


def persist_scan(payload: dict[str, Any], *, root: Path | None = None) -> dict[str, str]:
    root = root or project_root()
    scan_id = payload["scan_id"]
    d = scan_dir(scan_id, root)
    d.mkdir(parents=True, exist_ok=True)

    write_json(d / "summary.json", payload)
    write_json(d / "scan.json", payload)
    write_json(d / "discovery.json", payload.get("discovery"))
    write_json(d / "exclusion_audit.json", {
        "excluded_discovery": (payload.get("discovery") or {}).get("excluded"),
        "rejected_alignment": (payload.get("selection") or {}).get("rejected"),
    })
    write_json(d / "zero_write_integrity.json", payload.get("zero_write_integrity"))
    write_json(d / "selection.json", payload.get("selection"))
    write_json(d / "fixtures.json", payload.get("fixtures"))
    write_json(d / "timing_classes.json", payload.get("timing_summary"))
    if payload.get("isolation_preflight") is not None:
        write_json(d / "isolation_preflight.json", payload.get("isolation_preflight"))
    write_json(
        d / "canonical_state.json",
        {
            "before": payload.get("canonical_state_before"),
            "after": payload.get("canonical_state_after"),
            "unchanged": payload.get("canonical_state_unchanged"),
        },
    )

    sel = payload.get("selection") or {}
    write_json(d / "selected_tier_s.json", sel.get("tier_s") or [])
    write_json(d / "selected_tier_a.json", sel.get("tier_a") or [])
    write_json(d / "tier_b_watchlist.json", sel.get("tier_b") or [])

    flat_rows = []
    for r in payload.get("fixtures") or []:
        pred = r.get("prediction") or {}
        ecse = pred.get("ecse") or {}
        dirs = r.get("directions") or {}
        flat_rows.append(
            {
                "fixture_id": r.get("fixture_id"),
                "match": f"{r.get('home_team')} vs {r.get('away_team')}",
                "vienna_date": r.get("vienna_date"),
                "kickoff_vienna": r.get("kickoff_vienna"),
                "league": r.get("league"),
                "country": r.get("country"),
                "alignment_tier": r.get("alignment_tier"),
                "alignment_score": r.get("alignment_score"),
                "wde": dirs.get("wde_decision"),
                "ft_marginal": dirs.get("ft_marginal"),
                "market": dirs.get("market_direction"),
                "ecse_top1_dir": dirs.get("ecse_top1_direction"),
                "ecse_top5_maj": dirs.get("ecse_top5_majority"),
                "top5_mass": ecse.get("top5_mass"),
                "top3_mass": ecse.get("top3_mass"),
                "entropy": ecse.get("entropy"),
                "top1_probability": ecse.get("top1_probability"),
                "probabilities_persisted": r.get("probabilities_persisted"),
                "consensus": pred.get("consensus"),
                "no_bet": pred.get("no_bet"),
                "timing_class": r.get("timing_class"),
                "odds_availability": (r.get("odds_prep") or {}).get("availability"),
                "selected_reason": r.get("selected_reason"),
                "tier_s_failure_reasons": r.get("tier_s_failure_reasons"),
                "reject_reasons": r.get("reject_reasons"),
            }
        )
    write_csv(d / "fixtures.csv", flat_rows)

    selected = []
    for bucket in ("tier_s", "tier_a", "tier_b"):
        for r in (sel.get(bucket) or []):
            selected.append(r)
    write_json(d / "selected.json", selected)

    cmp = payload.get("baseline_comparison")
    outs: dict[str, str] = {}
    if cmp:
        write_json(d / "baseline_comparison.json", cmp)
        cmp_rows = []
        odds_rows = []
        model_rows = []
        tier_rows = []
        for r in cmp.get("fixtures") or []:
            om = r.get("odds_movement") or {}
            wm = r.get("wde_movement") or {}
            em = r.get("ecse_movement") or {}
            am = r.get("alignment_movement") or {}
            cmp_rows.append(
                {
                    "fixture_id": r.get("fixture_id"),
                    "match": r.get("match"),
                    "labels": ",".join(r.get("movement_labels") or []),
                    "old_tier": am.get("old_tier") or r.get("old_tier"),
                    "new_tier": am.get("new_tier") or r.get("new_tier"),
                    "top5_jaccard": em.get("top5_jaccard"),
                    "top5_mass_delta": em.get("top5_mass_delta"),
                    "alignment_score_delta": am.get("alignment_score_delta"),
                }
            )
            odds_rows.append(
                {
                    "fixture_id": r.get("fixture_id"),
                    "match": r.get("match"),
                    "old_hda": om.get("old_hda"),
                    "new_hda": om.get("new_hda"),
                    "max_odds_movement": om.get("max_odds_movement"),
                    "bookmaker_count_old": om.get("bookmaker_count_old"),
                    "bookmaker_count_new": om.get("bookmaker_count_new"),
                }
            )
            model_rows.append(
                {
                    "fixture_id": r.get("fixture_id"),
                    "match": r.get("match"),
                    "wde_old": wm.get("old_wde"),
                    "wde_new": wm.get("new_wde"),
                    "top1_old": em.get("top1_old"),
                    "top1_new": em.get("top1_new"),
                    "top5_old": em.get("old_top5"),
                    "top5_new": em.get("new_top5"),
                    "top5_mass_old": em.get("top5_mass_old"),
                    "top5_mass_new": em.get("top5_mass_new"),
                    "entropy_old": em.get("entropy_old"),
                    "entropy_new": em.get("entropy_new"),
                }
            )
            tier_rows.append(
                {
                    "fixture_id": r.get("fixture_id"),
                    "match": r.get("match"),
                    "old_tier": am.get("old_tier"),
                    "new_tier": am.get("new_tier"),
                    "labels": ",".join(r.get("movement_labels") or []),
                    "old_no_bet": am.get("old_no_bet"),
                    "new_no_bet": am.get("new_no_bet"),
                    "old_consensus": am.get("old_consensus"),
                    "new_consensus": am.get("new_consensus"),
                }
            )
        write_csv(d / "baseline_comparison.csv", cmp_rows)
        write_csv(d / "odds_movements.csv", odds_rows)
        write_csv(d / "model_movements.csv", model_rows)
        write_csv(d / "tier_movements.csv", tier_rows)
        outs["baseline_comparison"] = str(d / "baseline_comparison.json")

    report_path = write_report_markdown(payload, root=root)
    fresh_paths = write_fresh_reports(payload, root=root)
    outs.update(
        {
            "artifact_dir": str(d),
            "summary": str(d / "summary.json"),
            "scan": str(d / "scan.json"),
            "report": report_path,
            **fresh_paths,
        }
    )
    return outs


def write_fresh_reports(payload: dict[str, Any], *, root: Path | None = None) -> dict[str, str]:
    """Owner-facing fresh / comparison / summary reports for a rescan."""
    root = root or project_root()
    scan_id = payload.get("scan_id") or "unknown"
    rep_dir = root / REPORT_ROOT
    rep_dir.mkdir(parents=True, exist_ok=True)
    sel = payload.get("selection") or {}
    cmp = payload.get("baseline_comparison") or {}
    zw = payload.get("zero_write_integrity") or {}

    def _top5(row: dict[str, Any]) -> str:
        lines = [
            "| Rank | Exact score | Probability | Direction |",
            "| ---: | ----------- | ----------: | --------- |",
        ]
        ranks = (row.get("directions") or {}).get("ranks") or []
        for i in range(1, 6):
            r = next((x for x in ranks if int(x.get("rank") or 0) == i), None) or {}
            if not r.get("score"):
                t = ((row.get("prediction") or {}).get("ecse") or {}).get(f"top{i}") or {}
                r = {"score": t.get("score"), "probability": t.get("probability"), "direction": r.get("direction")}
            from worldcup_predictor.forward_evaluation.context import scoreline_side

            sc = str(r.get("score") or "")
            p = r.get("probability")
            ps = f"{float(p):.6f}" if isinstance(p, (int, float)) else "N/A"
            lines.append(f"| Top{i} | {sc} | {ps} | {r.get('direction') or scoreline_side(sc)} |")
        return "\n".join(lines)

    # --- fresh.md ---
    fresh_lines = [
        f"# Forward Aligned Fresh Rescan — `{scan_id}`",
        "",
        f"- Status: `{payload.get('status')}` / fresh_status=`{payload.get('fresh_status')}`",
        f"- Generated Vienna: `{payload.get('generated_at_vienna')}`",
        f"- Probabilities persisted on all predicted: `{payload.get('probabilities_persisted_all_predicted')}`",
        f"- Canonical state unchanged: `{payload.get('canonical_state_unchanged')}`",
        f"- Baseline compare: `{payload.get('baseline_scan_id')}`",
        "",
        "## Zero-write",
        "",
        "```",
        zw.get("proof_text") or "",
        "```",
        "",
        "## Tier S",
        "",
    ]
    for r in sel.get("tier_s") or []:
        ecse = (r.get("prediction") or {}).get("ecse") or {}
        fresh_lines += [
            f"### {r.get('home_team')} vs {r.get('away_team')} (`{r.get('fixture_id')}`)",
            f"- score={r.get('alignment_score')} Top5Mass={ecse.get('top5_mass')} no_bet="
            f"`{(r.get('prediction') or {}).get('no_bet')}`",
            _top5(r),
            "",
        ]
    if not sel.get("tier_s"):
        fresh_lines.append("_None._\n")
    fresh_lines.append("## Tier A\n")
    for r in sel.get("tier_a") or []:
        ecse = (r.get("prediction") or {}).get("ecse") or {}
        fresh_lines += [
            f"### {r.get('home_team')} vs {r.get('away_team')} (`{r.get('fixture_id')}`)",
            f"- Tier S failures: `{r.get('tier_s_failure_reasons')}`",
            f"- Top5Mass={ecse.get('top5_mass')} no_bet=`{(r.get('prediction') or {}).get('no_bet')}`",
            _top5(r),
            "",
        ]
    if not sel.get("tier_a"):
        fresh_lines.append("_None._\n")
    fresh_lines.append("## Tier B watchlist\n")
    for r in sel.get("tier_b") or []:
        dirs = r.get("directions") or {}
        fresh_lines.append(
            f"- `{r.get('fixture_id')}` {r.get('home_team')} vs {r.get('away_team')} "
            f"WDE={dirs.get('wde_decision')} Top1={dirs.get('ecse_top1_direction')} "
            f"Top5maj={dirs.get('ecse_top5_majority')} cons={(r.get('prediction') or {}).get('consensus')}"
        )
    fresh_path = rep_dir / f"forward_aligned_fixture_scan_{scan_id}_fresh.md"
    fresh_path.write_text("\n".join(fresh_lines) + "\n", encoding="utf-8")

    # --- comparison.md ---
    cmp_lines = [
        f"# Baseline Comparison — `{scan_id}` vs `{payload.get('baseline_scan_id')}`",
        "",
        f"- Overlap: {cmp.get('overlap_count')}",
        f"- Label counts: `{json.dumps(cmp.get('summary_labels') or {}, ensure_ascii=False)}`",
        "",
        "## Promotions / demotions",
        "",
        f"- To Tier S: {[r.get('fixture_id') for r in (cmp.get('promotions_to_tier_s') or [])]}",
        f"- To Tier A: {[r.get('fixture_id') for r in (cmp.get('promotions_to_tier_a') or [])]}",
        f"- Demoted from A: {[r.get('fixture_id') for r in (cmp.get('demotions_from_tier_a') or [])]}",
        f"- Started excluded: {[r.get('fixture_id') for r in (cmp.get('started_excluded') or [])]}",
        "",
        "## Per-fixture movements (selected prior Tier A focus)",
        "",
    ]
    prior_a = {1494611, 1589419, 1589416, 1589417, 1595191}
    for r in cmp.get("fixtures") or []:
        if int(r.get("fixture_id") or 0) not in prior_a and "PROMOTED_TO_TIER_S" not in (
            r.get("movement_labels") or []
        ):
            continue
        am = r.get("alignment_movement") or {}
        em = r.get("ecse_movement") or {}
        om = r.get("odds_movement") or {}
        cmp_lines += [
            f"### {r.get('match')} (`{r.get('fixture_id')}`)",
            f"- Labels: `{r.get('movement_labels')}`",
            f"- Tier: {am.get('old_tier')} → {am.get('new_tier')}",
            f"- Odds H/D/A: {om.get('old_hda')} → {om.get('new_hda')} (maxΔ={om.get('max_odds_movement')})",
            f"- Top5: {em.get('old_top5')} → {em.get('new_top5')} (Jaccard={em.get('top5_jaccard')})",
            f"- Top5 Mass: {em.get('top5_mass_old')} → {em.get('top5_mass_new')}",
            "",
        ]
    cmp_path = rep_dir / f"forward_aligned_fixture_scan_{scan_id}_comparison.md"
    cmp_path.write_text("\n".join(cmp_lines) + "\n", encoding="utf-8")

    # --- owner_summary.md ---
    owner_lines = [
        f"# Owner Summary — Fresh Rescan `{scan_id}`",
        "",
        f"**Fresh status:** `{payload.get('fresh_status')}`",
        "",
        f"Tier S/A/B = {(sel.get('counts') or {}).get('tier_s_selected')}/"
        f"{(sel.get('counts') or {}).get('tier_a_selected')}/"
        f"{(sel.get('counts') or {}).get('tier_b_selected')}",
        "",
        "Research only. No betting guarantee. No official freeze.",
        "",
        "## Best available (Tier S then Tier A, no_bet=false preferred)",
        "",
    ]
    ranked = list(sel.get("tier_s") or []) + list(sel.get("tier_a") or [])
    for r in ranked:
        pred = r.get("prediction") or {}
        use = (
            "1X2 + Exact Score research"
            if r.get("alignment_tier") == "S_FULL_ALIGNMENT"
            else ("watchlist only" if pred.get("no_bet") else "1X2 research / Exact Score research")
        )
        owner_lines.append(
            f"- `{r.get('fixture_id')}` {r.get('home_team')} vs {r.get('away_team')} — {use} "
            f"(no_bet={pred.get('no_bet')}, mass={(pred.get('ecse') or {}).get('top5_mass')})"
        )
    owner_path = rep_dir / f"forward_aligned_fixture_scan_{scan_id}_owner_summary.md"
    owner_path.write_text("\n".join(owner_lines) + "\n", encoding="utf-8")

    return {
        "fresh_report": str(fresh_path),
        "comparison_report": str(cmp_path),
        "owner_summary": str(owner_path),
    }


def write_report_markdown(payload: dict[str, Any], *, root: Path | None = None) -> str:
    root = root or project_root()
    from_date = ((payload.get("discovery") or {}).get("range") or {}).get("from_date") or "unknown"
    rep_dir = root / REPORT_ROOT
    rep_dir.mkdir(parents=True, exist_ok=True)
    path = rep_dir / f"forward_aligned_fixture_scan_{from_date}.md"

    def top5_table(row: dict[str, Any]) -> list[str]:
        ranks = ((row.get("directions") or {}).get("ranks")) or []
        lines = [
            "",
            "| Rank | Exact score | Probability | Direction |",
            "| ---: | ----------- | ----------: | --------- |",
        ]
        for i in range(1, 6):
            r = next((x for x in ranks if int(x.get("rank") or 0) == i), None)
            if not r:
                # fallback from prediction.ecse
                t = ((row.get("prediction") or {}).get("ecse") or {}).get(f"top{i}") or {}
                if isinstance(t, dict):
                    r = {"score": t.get("score"), "probability": t.get("probability"), "direction": None}
                else:
                    r = {"score": "", "probability": None, "direction": None}
            from worldcup_predictor.forward_evaluation.context import scoreline_side

            sc = str(r.get("score") or "")
            direction = r.get("direction") or scoreline_side(sc)
            prob = r.get("probability")
            prob_s = "" if prob is None else (f"{100*float(prob):.2f}%" if float(prob) <= 1 else f"{float(prob):.2f}%")
            lines.append(f"| Top{i} | {sc} | {prob_s} | {direction or ''} |")
        return lines

    def match_block(title: str, rows: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {title}", ""]
        if not rows:
            lines.append("_None qualified._")
            lines.append("")
            return lines
        for r in rows:
            dirs = r.get("directions") or {}
            pred = r.get("prediction") or {}
            ecse = pred.get("ecse") or {}
            odds = r.get("odds_prep") or {}
            lines += [
                f"### #{r.get('rank')} — {r.get('home_team')} vs {r.get('away_team')}",
                "",
                f"- Tier: `{r.get('alignment_tier')}` · score **{r.get('alignment_score')}**"
                + (" · **CAUTION**" if r.get("caution") else ""),
                f"- Date / kickoff (Vienna): {r.get('vienna_date')} / {r.get('kickoff_vienna')}",
                f"- {r.get('country')} · {r.get('league')} · fixture `{r.get('fixture_id')}`",
                f"- H/D/A: {odds.get('home')} / {odds.get('draw')} / {odds.get('away')} "
                f"(bm={odds.get('bookmaker_count')}, timing=`{r.get('timing_class')}`)",
                f"- WDE / FT / market: `{dirs.get('wde_decision')}` / `{dirs.get('ft_marginal')}` / `{dirs.get('market_direction')}`",
                f"- ECSE Top1 / Top3maj / Top5maj: `{dirs.get('ecse_top1_direction')}` / "
                f"`{dirs.get('ecse_top3_majority')}` / `{dirs.get('ecse_top5_majority')}`",
                f"- BTTS / O/U: `{(pred.get('btts') or {}).get('prediction')}` / `{(pred.get('ou25') or {}).get('preferred_side')}`",
                f"- Top3/Top5 Mass / entropy: {ecse.get('top3_mass')} / {ecse.get('top5_mass')} / {ecse.get('entropy')}",
                f"- consensus=`{pred.get('consensus')}` no_bet=`{pred.get('no_bet')}` stability=`{r.get('stability')}`",
                f"- Selected because: {r.get('selected_reason')}",
            ]
            lines += top5_table(r)
            lines.append("")
        return lines

    disc = payload.get("discovery") or {}
    sel = payload.get("selection") or {}
    zw = payload.get("zero_write_integrity") or {}
    lines = [
        f"# Forward Aligned Fixture Scan — {from_date}",
        "",
        f"**Status:** `{payload.get('status')}`",
        f"**Scan ID:** `{payload.get('scan_id')}`",
        f"**Range:** {(disc.get('range') or {}).get('from_date')} → {(disc.get('range') or {}).get('to_date')} "
        f"({(disc.get('range') or {}).get('days')} Vienna days)",
        f"**Research only — ephemeral:** yes · official freezes created: **no**",
        "",
        "## Coverage",
        "",
        f"- Raw discovered: **{disc.get('raw_discovered')}**",
        f"- Discovery included: **{disc.get('included_count')}**",
        f"- Discovery excluded: **{disc.get('excluded_count')}**",
        f"- Predicted eligible: **{payload.get('predicted_count')}**",
        f"- Tier S/A/B selected: "
        f"{(sel.get('counts') or {}).get('tier_s_selected')}/"
        f"{(sel.get('counts') or {}).get('tier_a_selected')}/"
        f"{(sel.get('counts') or {}).get('tier_b_selected')}",
        "",
        "## Zero-write integrity",
        "",
        f"```text\n{json.dumps(zw, indent=2)}\n```",
        "",
    ]
    lines += match_block("Tier S — FULL_ALIGNMENT", sel.get("tier_s") or [])
    lines += match_block("Tier A — STRONG_ALIGNMENT", sel.get("tier_a") or [])
    lines += match_block("Tier B — DIRECTIONAL watchlist", sel.get("tier_b") or [])

    lines += ["## Rejected / blocked (sample)", ""]
    rejected = (sel.get("rejected") or [])[:40]
    if not rejected:
        lines.append("_None._")
    else:
        lines.append("| Fixture | Reason |")
        lines.append("|---|---|")
        for r in rejected:
            reasons = r.get("reject_reasons") or [r.get("prediction_status")]
            lines.append(
                f"| {r.get('fixture_id')} {r.get('home_team')} vs {r.get('away_team')} | "
                f"{'; '.join(str(x) for x in reasons)} |"
            )
    lines += [
        "",
        "## Limitations",
        "",
        "- Agreement filter remains preliminary (forensic n=71); not production-promoted.",
        "- Very-early odds may be immature; timing classes recorded, not assumed superior.",
        "- Do not freeze automatically; use owner-approved freeze command only.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)
