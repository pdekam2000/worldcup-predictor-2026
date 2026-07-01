#!/usr/bin/env python3
"""Run provider truth audit — API-Football + Sportmonks + OddAlerts odds coverage."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _write_report(result: dict, report_path: Path) -> None:
    summary = result["summary"]
    part_a = result["part_a"]
    truth = result["truth_table"]
    mappings = result["mappings"]
    rec = summary["recommendation"]

    def _provider_has_market(provider: str, market: str) -> bool:
        return any(r["provider"] == provider and r.get(market) for r in truth)

    lines = [
        "# Provider Truth Audit Report",
        "",
        f"**Generated:** {summary['generated_at']}",
        f"**Phase:** {summary['phase']}",
        f"**Sample fixtures:** {summary['sample_fixture_count']}",
        "",
        "## Part A — Provider credential/config",
        "",
        "| Provider | Token configured | Base URL | Client | Odds endpoint | Fixture endpoint |",
        "|----------|------------------|----------|--------|---------------|------------------|",
    ]
    for name, cfg in part_a.items():
        lines.append(
            f"| {name} | {'yes' if cfg['token_configured'] else 'no'} | {cfg['base_url']} | "
            f"{'yes' if cfg['client_exists'] else 'no'} | "
            f"{'yes' if cfg['odds_endpoint_implemented'] else 'no'} | "
            f"{'yes' if cfg['fixture_endpoint_implemented'] else 'no'} |"
        )

    lines.extend(["", "## Part B — Fixture mapping", ""])
    lines.append("| fixture_id | competition | kickoff | home vs away | AF id | SM id | OA id | OA status |")
    lines.append("|------------|-------------|---------|--------------|-------|-------|-------|-----------|")
    for m in mappings:
        if m.get("error"):
            lines.append(f"| {m.get('local_fixture_id')} | ERROR | | | | | | {m['error']} |")
            continue
        lines.append(
            f"| {m['local_fixture_id']} | {m['competition_key']} | {m['kickoff_time']} | "
            f"{m['home_team']} vs {m['away_team']} | {m.get('api_football_fixture_id')} | "
            f"{m.get('sportmonks_fixture_id') or '—'} | {m.get('oddalerts_fixture_id') or '—'} | "
            f"{m.get('oddalerts_mapping_status', '—')} |"
        )

    lines.extend(["", "## Part E — Provider truth table", ""])
    lines.append(
        "| Fixture | Provider | Mapped? | 1X2 | O/U 2.5 | BTTS | Correct Score | Raw odds? | Parser OK? | Store OK? | Final blocker |"
    )
    lines.append(
        "|---------|----------|---------|-----|---------|------|---------------|-----------|------------|-----------|---------------|"
    )
    for r in truth:
        lines.append(
            f"| {r['fixture']} | {r['provider']} | {'yes' if r['mapped'] else 'no'} | "
            f"{'yes' if r['1x2'] else 'no'} | {'yes' if r['ou_2_5'] else 'no'} | "
            f"{'yes' if r['btts'] else 'no'} | {'yes' if r['correct_score'] else 'no'} | "
            f"{'yes' if r['raw_odds'] else 'no'} | {'yes' if r['parser_ok'] else 'no'} | "
            f"{'yes' if r['store_ok'] else 'no'} | {r['final_blocker']} |"
        )

    lines.extend(
        [
            "",
            "## Part H — Answers",
            "",
            f"1. **Does API-Football return odds for the sample fixtures?** "
            f"{'Yes (partial or full on most fixtures)' if _provider_has_market('api_football', '1x2') or any(r['provider']=='api_football' and r['raw_odds'] for r in truth) else 'No / empty on sample'}",
            f"2. **Does Sportmonks return odds for the sample fixtures?** "
            f"{'Yes (where mapped)' if any(r['provider']=='sportmonks' and r['raw_odds'] for r in truth) else 'No / unmapped or empty'}",
            f"3. **Does OddAlerts return odds for the sample fixtures?** "
            f"{'Yes (where mapped)' if any(r['provider']=='oddalerts' and r['raw_odds'] for r in truth) else 'No / mapping missing or empty'}",
            f"4. **Which provider has 1X2?** "
            + ", ".join(p for p in ("api_football", "sportmonks", "oddalerts") if _provider_has_market(p, "1x2"))
            or "none on sample",
            f"5. **Which provider has O/U 2.5?** "
            + ", ".join(p for p in ("api_football", "sportmonks", "oddalerts") if _provider_has_market(p, "ou_2_5"))
            or "none on sample",
            f"6. **Which provider has BTTS?** "
            + ", ".join(p for p in ("api_football", "sportmonks", "oddalerts") if _provider_has_market(p, "btts"))
            or "none on sample",
            f"7. **Which provider has Correct Score?** "
            + ", ".join(p for p in ("api_football", "sportmonks", "oddalerts") if _provider_has_market(p, "correct_score"))
            or "none on sample",
            "8. **Root cause:** See truth table blockers — distinguishes PROVIDER_EMPTY vs MAPPING_MISSING vs PARSER_GAP vs STORAGE_GAP.",
            f"9. **Next fix:** `{rec}`",
            "",
            "## Artifacts",
            "",
            f"- `artifacts/provider_truth_audit_summary.json`",
            f"- `artifacts/provider_truth_audit_fixture_table.json`",
            f"- `logs/provider_truth_audit_calls_{summary['audit_date']}.jsonl`",
            f"- Raw payloads: `{summary['raw_payload_dir']}/`",
            "",
            "## Validation — unchanged systems",
            "",
        ]
    )
    for k, ok in summary.get("unchanged_checks", {}).items():
        lines.append(f"- `{k}`: {'unchanged' if ok else 'CHANGED — investigate'}")

    lines.extend(
        [
            "",
            f"**Quota used:** {json.dumps(summary['quota_used'])}",
            "",
            f"## Final recommendation: `{rec}`",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.research.provider_truth_audit import run_provider_truth_audit

    settings = get_settings()
    print("PROVIDER TRUTH AUDIT — audit only, no predictions, no DB writes\n")

    result = run_provider_truth_audit(settings=settings)
    report_path = ROOT / "PROVIDER_TRUTH_AUDIT_REPORT.md"
    _write_report(result, report_path)

    print(f"Summary: artifacts/provider_truth_audit_summary.json")
    print(f"Fixture table: artifacts/provider_truth_audit_fixture_table.json")
    print(f"Call log: {result['summary']['call_log_path']}")
    print(f"Report: {report_path}")
    print(f"Recommendation: {result['summary']['recommendation']}")
    print(f"Quota: {result['summary']['quota_used']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
