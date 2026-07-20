"""Report builders for ECSE timing experiment."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_timing_experiment.constants import ARTIFACT_ROOT, REPORT_ROOT, TZ_NAME
from worldcup_predictor.research.ecse_timing_experiment.windows import to_vienna


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k) for k in fields})


def _score_cell(t: dict | None) -> str:
    if not isinstance(t, dict):
        return "—"
    sc = t.get("score") or "?"
    pr = t.get("probability")
    try:
        p = float(pr) if pr is not None else None
    except (TypeError, ValueError):
        p = None
    if p is None:
        return str(sc)
    pct = p * 100 if p <= 1 else p
    return f"{sc} ({pct:.1f}%)"


def build_early_report(
    *,
    root: Path,
    experiment_date: str,
    summary: dict[str, Any],
    discovery: dict[str, Any],
    results: list[dict[str, Any]],
    integrity: dict[str, Any],
) -> Path:
    report_path = root / REPORT_ROOT / f"ecse_timing_experiment_{experiment_date}_EARLY.md"
    art = root / ARTIFACT_ROOT / experiment_date / "early"
    vienna_now = to_vienna(datetime.now(timezone.utc))

    captured_rows = [r for r in results if r.get("status") == "CAPTURED" or r.get("inserted")]
    # Prefer prediction payloads
    table_rows = []
    for r in results:
        pred = r.get("prediction") or {}
        if not pred and r.get("status") not in {"CAPTURED", "IDEMPOTENT_ALREADY_CAPTURED"}:
            continue
        ecse = pred.get("ecse") or {}
        wde = pred.get("wde") or {}
        odds = r.get("odds") or pred.get("odds") or {}
        table_rows.append(
            {
                "fixture_id": r.get("fixture_id"),
                "match": f"{r.get('home_team')} vs {r.get('away_team')}",
                "league": r.get("league"),
                "kickoff_vienna": r.get("kickoff_vienna"),
                "hours_to_kickoff": r.get("hours_to_kickoff"),
                "window": r.get("window_classification"),
                "odds_h": odds.get("home"),
                "odds_d": odds.get("draw"),
                "odds_a": odds.get("away"),
                "freshness": odds.get("freshness_status"),
                "bookmakers": odds.get("bookmaker_count"),
                "wde": wde.get("decision"),
                "btts": (pred.get("btts") or {}).get("prediction"),
                "ou25": (pred.get("ou25") or {}).get("preferred_side"),
                "top1": _score_cell(ecse.get("top1")),
                "top2": _score_cell(ecse.get("top2")),
                "top3": _score_cell(ecse.get("top3")),
                "top4": _score_cell(ecse.get("top4")),
                "top5": _score_cell(ecse.get("top5")),
                "top3_mass": ecse.get("top3_mass"),
                "top5_mass": ecse.get("top5_mass"),
                "entropy": ecse.get("entropy"),
                "consensus": pred.get("consensus"),
                "no_bet": pred.get("no_bet"),
                "status": r.get("status"),
            }
        )

    _write_csv(
        art / "early_snapshots.csv",
        table_rows,
        [
            "fixture_id",
            "match",
            "league",
            "kickoff_vienna",
            "hours_to_kickoff",
            "window",
            "odds_h",
            "odds_d",
            "odds_a",
            "freshness",
            "bookmakers",
            "wde",
            "btts",
            "ou25",
            "top1",
            "top2",
            "top3",
            "top4",
            "top5",
            "top3_mass",
            "top5_mass",
            "entropy",
            "consensus",
            "no_bet",
            "status",
        ],
    )
    _write_json(art / "early_snapshots.json", table_rows)
    _write_json(art / "excluded.json", discovery.get("excluded") or [])

    lines = [
        f"# ECSE Timing Experiment — EARLY — {experiment_date}",
        "",
        f"**Status:** `{summary.get('final_status')}`",
        f"**Generated (Vienna):** {vienna_now}",
        f"**Experiment ID:** `{summary.get('experiment_id')}`",
        f"**Audit ID:** `{summary.get('audit_id')}`",
        f"**Git SHA:** `{summary.get('git_sha')}`",
        "",
        "## Research posture",
        "",
        "- Research only. No production decision mutation.",
        "- `freeze_capture=false`. Canonical freezes not overwritten.",
        "- WSP/ECSE restored after temporary runs.",
        "- Do **not** conclude EARLY is more accurate until forward results support it.",
        "",
        "## Discovery summary",
        "",
        f"- Raw discovery count: **{discovery.get('discovery_raw_count')}**",
        f"- Included (fresh complete odds): **{discovery.get('included_count')}**",
        f"- Excluded (with reasons): **{discovery.get('excluded_count')}**",
        f"- Tier A included: **{discovery.get('tier_a_count')}** · Tier B included: **{discovery.get('tier_b_count')}**",
        "",
        "### Excluded fixtures",
        "",
        "| Fixture | Match | Reason |",
        "|---|---|---|",
    ]
    for x in discovery.get("excluded") or []:
        lines.append(
            f"| {x.get('fixture_id')} | {x.get('home_team')} vs {x.get('away_team')} | `{x.get('exclusion_reason')}` |"
        )
    if not discovery.get("excluded"):
        lines.append("| — | — | none |")

    lines += [
        "",
        "## EARLY snapshot table",
        "",
        "| Fixture | Match | Kickoff (Vienna) | Hours | Window | H/D/A | WDE | Top1–Top5 | Top5 Mass | Entropy | Consensus | no_bet |",
        "|---|---|---|---:|---|---|---|---|---:|---:|---|---|",
    ]
    for r in table_rows:
        odds = f"{r.get('odds_h')}/{r.get('odds_d')}/{r.get('odds_a')}"
        tops = " · ".join(
            [
                str(r.get("top1")),
                str(r.get("top2")),
                str(r.get("top3")),
                str(r.get("top4")),
                str(r.get("top5")),
            ]
        )
        lines.append(
            f"| {r.get('fixture_id')} | {r.get('match')} | {r.get('kickoff_vienna')} | "
            f"{r.get('hours_to_kickoff')} | `{r.get('window')}` | {odds} | {r.get('wde')} | {tops} | "
            f"{r.get('top5_mass')} | {r.get('entropy')} | {r.get('consensus')} | {r.get('no_bet')} |"
        )
    if not table_rows:
        lines.append("| — | no successful EARLY captures | — | — | — | — | — | — | — | — | — | — |")

    integ = integrity or summary.get("integrity") or {}
    lines += [
        "",
        "## Integrity proof",
        "",
        f"- `freeze_capture`: **false**",
        f"- Freeze hashes unchanged: **{integ.get('freeze_unchanged')}**",
        f"- WSP/ECSE restore OK: **{integ.get('wsp_restore_ok')}**",
        f"- Restore meta: `{json.dumps(integ.get('restore_meta') or {})}`",
        f"- Temporary run audit ID: `{integ.get('temporary_run_audit_id') or summary.get('audit_id')}`",
        "",
        "## MID / LATE capture commands (do not fake)",
        "",
        "```bash",
        summary.get("mid_command")
        or f"python scripts/run_ecse_timing_experiment.py --date {experiment_date} --snapshot mid --scope owner",
        "```",
        "",
        "```bash",
        summary.get("late_command")
        or f"python scripts/run_ecse_timing_experiment.py --date {experiment_date} --snapshot late --scope owner",
        "```",
        "",
        "```bash",
        summary.get("evaluate_command")
        or f"python scripts/evaluate_ecse_timing_experiment.py --date {experiment_date}",
        "```",
        "",
        "## Capture counts",
        "",
        f"- Captured: **{summary.get('captured')}**",
        f"- Blocked: **{summary.get('blocked')}**",
        f"- Idempotent already captured: **{summary.get('idempotent')}**",
        "",
        "## Artifacts",
        "",
        f"- `{art.as_posix()}/`",
        "",
        "_Research-only. Owner visibility. Not a betting recommendation._",
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
