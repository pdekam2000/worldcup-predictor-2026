"""Generate database + learning audit report."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT = ROOT / "reports" / "database_learning_audit.md"


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for (name,) in rows:
        if name.startswith("sqlite_"):
            continue
        try:
            counts[name] = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        except sqlite3.Error:
            counts[name] = -1
    return counts


def main() -> int:
    from worldcup_predictor.access.config import access_db_path
    from worldcup_predictor.database.connection import get_db_path
    from worldcup_predictor.learning.model_coach_agent import ModelCoachAgent

    db_path = get_db_path(access_db_path())
    coach_report = None
    coach_error = None
    try:
        coach_report = ModelCoachAgent().run()
    except Exception as exc:
        coach_error = str(exc)

    counts: dict[str, int] = {}
    if db_path.is_file():
        conn = sqlite3.connect(str(db_path))
        counts = _table_counts(conn)
        conn.close()

    lines = [
        "# Database & Learning Audit",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"**Database path:** `{db_path}`",
        f"**Exists:** {db_path.is_file()}",
        "",
        "## Tables & row counts",
        "",
        "| Table | Rows |",
        "| --- | ---: |",
    ]
    for table, n in sorted(counts.items()):
        lines.append(f"| {table} | {n} |")

    lines.extend(
        [
            "",
            "## Data domains",
            "",
            "- **Fixtures & results:** `fixtures`, `fixture_results`",
            "- **Predictions:** `predictions`, `prediction_markets`, JSONL `data/predictions/prediction_history.jsonl`",
            "- **Verification:** `verification_results`, JSONL `data/verification/prediction_verification.jsonl`",
            "- **Learning:** `learning_records_v2`, `model_coach_reports`",
            "- **Access:** `app_users`, `user_usage_limits`, `user_entitlements`, `remember_tokens`",
            "- **Odds / cache:** `odds_snapshots`, `xg_snapshots`, `player_stats_snapshots`, `agent_signals`",
            "",
            "## Learning system policy",
            "",
            "- Model Coach re-analyzes stored predictions vs verified results.",
            "- Recommendations only — **no automatic weight changes** without admin approval.",
            "- See `APPLY_RECOMMENDATIONS_AFTER_USER_APPROVAL` in learning models.",
            "",
        ]
    )

    if coach_report:
        lines.append("## Latest Model Coach recommendations")
        lines.append("")
        lines.append(f"- **Strongest market:** {coach_report.strongest_market or '—'}")
        lines.append(f"- **Weakest market:** {coach_report.weakest_market or '—'}")
        if coach_report.suggested_focus_area:
            lines.append(f"- **Focus area:** {coach_report.suggested_focus_area}")
        for rule in (coach_report.recommended_market_rules or [])[:5]:
            lines.append(f"- {rule}")
        for market, recs in list((coach_report.market_specific_recommendations or {}).items())[:4]:
            for rec in recs[:2]:
                lines.append(f"- **{market}:** {rec}")
        for advice in (coach_report.decision_agent_advice or [])[:3]:
            lines.append(f"- {advice}")
        if coach_report.warnings_about_small_sample_size:
            lines.append("")
            lines.append("**Sample warnings:**")
            for w in coach_report.warnings_about_small_sample_size[:3]:
                lines.append(f"- {w}")
        lines.append("")
        lines.append(
            f"Evaluated matches: {coach_report.evaluated_matches} · "
            f"Market rows: {coach_report.total_market_rows} · "
            f"Auto-apply weights: {coach_report.apply_recommendations_after_user_approval}"
        )
    elif coach_error:
        lines.append(f"## Model Coach run skipped: {coach_error}")

    lines.extend(
        [
            "",
            "## Improvement notes",
            "",
            "- Live predict pipeline writes JSONL; run `migrate-jsonl` to sync SQLite mirrors.",
            "- Verification auto-runs on Match Center load; persists to JSONL verification store.",
            "- Learning records captured on prediction via `learning_capture` when enabled.",
            "",
        ]
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
