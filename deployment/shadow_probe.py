#!/usr/bin/env python3
"""Non-blocking shadow infrastructure probe.

Exercises historical service, form snapshots, alternate totals, and shadow orchestration
against a throwaway fixture id. Never writes canonical freezes or changes canonical λ.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fi-db", default="data/football_intelligence.db")
    ap.add_argument("--out-md", default="shadow_probe_report.md")
    ap.add_argument("--out-json", default="shadow_probe.json")
    ap.add_argument("--fixture-id", type=int, default=537266999)
    args = ap.parse_args()

    results: dict[str, Any] = {
        "generated_at_utc": _now(),
        "fixture_id": args.fixture_id,
        "stages": [],
        "canonical_blocked": False,
        "status": "PASS",
    }

    def stage(name: str, ok: bool, detail: str = "", data: Any = None) -> None:
        results["stages"].append(
            {"stage": name, "ok": ok, "detail": detail, "data": data or {}}
        )
        if not ok:
            results["status"] = "FAIL"

    fi = Path(args.fi_db)
    try:
        from worldcup_predictor.research.football_strength_foundation.historical_match_service import (
            HistoricalMatchService,
        )
        from worldcup_predictor.research.football_strength_foundation.team_strength_engine import (
            TeamStrengthEngine,
        )
        from worldcup_predictor.research.infra_l2f_forward.alternate_totals_capture_service import (
            capture_alternate_totals,
        )
        from worldcup_predictor.research.infra_l2f_forward.shadow_orchestrator import (
            run_shadow_pipeline,
        )
    except Exception as exc:  # noqa: BLE001
        stage("imports", False, str(exc))
        _write(args, results)
        return 1

    stage("imports", True)

    # Use ephemeral DB for writes so probe never pollutes production tables unless desired.
    # Still validates against FI for historical reads when available.
    tmp = Path(tempfile.mkdtemp(prefix="shadow_probe_")) / "probe.sqlite"
    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row

    try:
        if fi.exists():
            hist = HistoricalMatchService(fi_path=str(fi))
            _ = hist.resolve_team("Arsenal")
            stage("historical_service", True, "resolve_team ok")
            engine = TeamStrengthEngine(hist)
        else:
            stage("historical_service", False, f"FI missing: {fi}")
            engine = None

        odds_row = {
            "ou_over_25_closing": 1.9,
            "ou_under_25_closing": 1.95,
            "ou_over_35_closing": None,
            "ou_under_35_closing": None,
            "ou_over_45_closing": None,
            "ou_under_45_closing": None,
        }
        cap = capture_alternate_totals(conn, fixture_id=args.fixture_id, odds_row=odds_row)
        stage("alternate_totals", True, "capture returned", cap)

        if engine is not None:
            cutoff = datetime.now(timezone.utc)
            res = run_shadow_pipeline(
                conn=conn,
                fixture_id=args.fixture_id,
                home_team="__PROBE_HOME__",
                away_team="__PROBE_AWAY__",
                league="probe",
                cutoff=cutoff,
                engine=engine,
                odds_row=odds_row,
                canonical_lh=1.25,
                canonical_la=1.10,
                odds_fresh=True,
            )
            results["canonical_blocked"] = bool(res.canonical_blocked)
            stage(
                "shadow_orchestration",
                res.canonical_blocked is False,
                f"stages={len(res.stages)} all_ok={res.all_ok}",
                [{"stage": s.stage, "ok": s.ok, "detail": s.detail[:160]} for s in res.stages],
            )
            if res.canonical_blocked:
                results["status"] = "FAIL"
        else:
            stage("shadow_orchestration", False, "engine unavailable")
    except Exception as exc:  # noqa: BLE001
        stage("probe_exception", False, f"{type(exc).__name__}: {exc}")
    finally:
        conn.close()

    _write(args, results)
    print(json.dumps({"status": results["status"], "canonical_blocked": results["canonical_blocked"]}, indent=2))
    return 0 if results["status"] == "PASS" else 1


def _write(args: argparse.Namespace, results: dict[str, Any]) -> None:
    Path(args.out_json).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Shadow probe report",
        "",
        f"Generated: `{results['generated_at_utc']}`",
        f"Status: **{results['status']}**",
        f"canonical_blocked: `{results['canonical_blocked']}` (must be False)",
        "",
        "## Stages",
        "",
    ]
    for s in results["stages"]:
        mark = "PASS" if s["ok"] else "FAIL"
        lines.append(f"- **{s['stage']}**: {mark} — {s.get('detail', '')}")
    lines.extend(
        [
            "",
            "## Guarantees",
            "",
            "- Does not mutate canonical freezes",
            "- Does not promote Lambda V2 / Exact V2",
            "- Shadow failure must not set canonical_blocked",
            "",
        ]
    )
    text = "\n".join(lines) + "\n"
    Path(args.out_md).write_text(text, encoding="utf-8")
    if Path(args.out_md).name == "shadow_probe_report.md":
        Path("shadow_probe_report.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
