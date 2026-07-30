"""TeamFormH2HForensicAgent — read-only prematch forensic validation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.owner_daily.pipeline.constants import day_dir
from worldcup_predictor.research.team_form_h2h_forensic.constants import AGENT_NAME, RULE_VERSION
from worldcup_predictor.research.team_form_h2h_forensic.evidence import load_fixture_evidence
from worldcup_predictor.research.team_form_h2h_forensic.scoring import build_forensic_result


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


class TeamFormH2HForensicAgent:
    """Owner-only forensic agent. Does not modify canonical predictions."""

    def __init__(self, *, settings: Settings | None = None, root: Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = root or project_root()
        self.prod_conn = connect(self.settings.sqlite_path)
        self.eval_conn = connect_eval_db(self.root)

    def close(self) -> None:
        self.prod_conn.close()
        self.eval_conn.close()

    def analyze_fixture(
        self,
        *,
        fixture_id: int,
        home_team: str | None = None,
        away_team: str | None = None,
        kickoff_utc: str | None = None,
        competition_key: str | None = None,
    ) -> dict[str, Any]:
        if not home_team or not away_team or not kickoff_utc:
            row = self.prod_conn.execute(
                "SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key FROM fixtures WHERE fixture_id=?",
                (int(fixture_id),),
            ).fetchone()
            if not row:
                return {"fixture_id": fixture_id, "classification": "INSUFFICIENT_FORENSIC_DATA", "error": "fixture_not_found"}
            home_team = home_team or row["home_team"]
            away_team = away_team or row["away_team"]
            kickoff_utc = kickoff_utc or row["kickoff_utc"]
            competition_key = competition_key or row["competition_key"]

        evidence = load_fixture_evidence(
            fixture_id=int(fixture_id),
            home_team=str(home_team),
            away_team=str(away_team),
            kickoff_utc=str(kickoff_utc),
            competition_key=str(competition_key or ""),
            prod_conn=self.prod_conn,
            eval_conn=self.eval_conn,
            settings=self.settings,
        )
        return build_forensic_result(evidence)

    def analyze_frozen_fixtures_for_date(self, report_date: str) -> list[dict[str, Any]]:
        manifest = day_dir(report_date) / "freeze_manifest.json"
        fixture_ids: list[int] = []
        if manifest.is_file():
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else (payload.get("freezes") or payload.get("rows") or [])
            for row in rows:
                fid = row.get("fixture_id")
                if fid is not None:
                    fixture_ids.append(int(fid))
        if not fixture_ids:
            rows = self.eval_conn.execute(
                """
                SELECT fixture_id, match_name, kickoff, competition
                FROM frozen_predictions
                WHERE kickoff LIKE ?
                ORDER BY kickoff
                """,
                (f"{report_date}%",),
            ).fetchall()
            fixture_ids = [int(r["fixture_id"]) for r in rows]

        results = []
        for fid in fixture_ids:
            results.append(self.analyze_fixture(fixture_id=fid))
        return results


def get_fixture_team_forensic_analysis(fixture_id: int, *, settings: Settings | None = None) -> dict[str, Any]:
    """Owner-only on-demand read-only forensic analysis."""
    agent = TeamFormH2HForensicAgent(settings=settings)
    try:
        return agent.analyze_fixture(fixture_id=int(fixture_id))
    finally:
        agent.close()


def run_forensic_batch(
    *,
    report_date: str,
    root: Path | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    root = root or project_root()
    settings = settings or get_settings()
    agent = TeamFormH2HForensicAgent(settings=settings, root=root)
    evaluated: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
    try:
        results = agent.analyze_frozen_fixtures_for_date(report_date)
        eval_conn = connect_eval_db(root)
        try:
            evaluated = _shadow_validation(agent_eval_conn=eval_conn, results=results)
            evaluated["historical_evaluated"] = _shadow_historical_eval(agent)
        finally:
            eval_conn.close()
    finally:
        agent.close()

    art_dir = day_dir(report_date)
    art_dir.mkdir(parents=True, exist_ok=True)
    out_path = art_dir / "team_form_h2h_forensics.json"
    payload = {
        "agent": AGENT_NAME,
        "rule_version": RULE_VERSION,
        "report_date": report_date,
        "generated_at": _utc_now(),
        "fixture_count": len(results),
        "results": results,
        "public_visible": False,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    report_dir = root / "reports" / "owner" / "daily"
    report_dir.mkdir(parents=True, exist_ok=True)
    fa_path = report_dir / f"{report_date}_TEAM_FORM_H2H_FORENSIC_FA.md"
    fa_path.write_text(_report_fa(report_date, results), encoding="utf-8")

    shadow_dir = root / "artifacts" / "team_form_h2h_forensic"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    (shadow_dir / f"{report_date}_shadow.json").write_text(
        json.dumps({"report_date": report_date, "results": results}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (shadow_dir / "shadow_validation.json").write_text(json.dumps(evaluated, indent=2), encoding="utf-8")

    final_status = _final_status(results, evaluated)
    return {
        "final_status": final_status,
        "report_date": report_date,
        "fixture_count": len(results),
        "artifact_path": str(out_path),
        "report_fa_path": str(fa_path),
        "shadow_validation": evaluated,
    }


def _shadow_historical_eval(agent: TeamFormH2HForensicAgent) -> dict[str, Any]:
    """Replay-safe shadow metrics on fixtures with market evaluations."""
    rows = agent.eval_conn.execute(
        """
        SELECT fp.fixture_id, me.ecse_top5_hit, me.ecse_top1_hit
        FROM frozen_predictions fp
        JOIN market_evaluations me ON me.prediction_id = fp.prediction_id
        ORDER BY fp.kickoff DESC
        LIMIT 200
        """
    ).fetchall()
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        fid = int(row["fixture_id"])
        try:
            res = agent.analyze_fixture(fixture_id=fid)
        except Exception:
            continue
        cls = str(res.get("classification") or "UNKNOWN")
        buckets.setdefault(cls, []).append(
            {
                "fixture_id": fid,
                "top5_hit": row["ecse_top5_hit"] == "HIT",
                "top1_hit": row["ecse_top1_hit"] == "HIT",
            }
        )
    summary = {}
    for cls, items in buckets.items():
        n = len(items)
        summary[cls] = {
            "n": n,
            "top5_accuracy_pct": round(100.0 * sum(1 for x in items if x["top5_hit"]) / max(n, 1), 4),
            "top1_accuracy_pct": round(100.0 * sum(1 for x in items if x["top1_hit"]) / max(n, 1), 4),
        }
    return {"fixture_count": len(rows), "classified_evaluated": summary}


def _shadow_validation(*, agent_eval_conn: sqlite3.Connection, results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = agent_eval_conn.execute(
        """
        SELECT fp.fixture_id, me.ecse_top5_hit, me.ecse_top1_hit
        FROM frozen_predictions fp
        JOIN market_evaluations me ON me.prediction_id = fp.prediction_id
        """
    ).fetchall()
    by_fid = {int(r["fixture_id"]): dict(r) for r in rows}
    buckets: dict[str, list[dict[str, Any]]] = {}
    for res in results:
        fid = int(res.get("fixture_id") or 0)
        ev = by_fid.get(fid)
        if not ev:
            continue
        cls = str(res.get("classification") or "UNKNOWN")
        buckets.setdefault(cls, []).append(
            {
                "fixture_id": fid,
                "top5_hit": ev.get("ecse_top5_hit") == "HIT",
                "top1_hit": ev.get("ecse_top1_hit") == "HIT",
            }
        )
    summary = {}
    for cls, items in buckets.items():
        n = len(items)
        summary[cls] = {
            "n": n,
            "top5_accuracy_pct": round(100.0 * sum(1 for x in items if x["top5_hit"]) / max(n, 1), 4),
            "top1_accuracy_pct": round(100.0 * sum(1 for x in items if x["top1_hit"]) / max(n, 1), 4),
        }
    return {"evaluated_fixtures": len(by_fid), "classified_evaluated": summary}


def _final_status(results: list[dict[str, Any]], shadow: dict[str, Any]) -> str:
    if not results:
        return "TEAM_FORM_H2H_FORENSIC_AGENT_MORE_DATA_REQUIRED"
    hist = shadow.get("historical_evaluated") or {}
    evaluated_n = int(shadow.get("evaluated_fixtures") or hist.get("fixture_count") or 0)
    classified = hist.get("classified_evaluated") or shadow.get("classified_evaluated") or {}
    if evaluated_n < 20:
        return "TEAM_FORM_H2H_FORENSIC_AGENT_SHADOW_READY"
    fragile = classified.get("TOP5_FRAGILE", {})
    strong = classified.get("TOP5_STRONGLY_SUPPORTED", {})
    if fragile.get("n", 0) >= 5 and fragile.get("top5_accuracy_pct", 100) < strong.get("top5_accuracy_pct", 0) - 5:
        return "TEAM_FORM_H2H_FORENSIC_AGENT_VALIDATED"
    return "TEAM_FORM_H2H_FORENSIC_AGENT_SHADOW_READY"


def _report_fa(report_date: str, results: list[dict[str, Any]]) -> str:
    lines = [
        f"# گزارش forensic فرم تیم و H2H — {report_date}",
        "",
        f"**Agent:** `{AGENT_NAME}`  ",
        f"**Rule version:** `{RULE_VERSION}`  ",
        f"**تعداد fixture:** {len(results)}  ",
        "",
        "این گزارش فقط prematch و read-only است. canonical Top5 تغییر نکرده است.",
        "",
    ]
    for res in results[:25]:
        lines.extend(
            [
                f"## {res.get('match')}",
                "",
                f"- **طبقه‌بندی:** `{res.get('classification')}`",
                f"- **Support / Contradiction:** {res.get('support_score')} / {res.get('contradiction_score')}",
                f"- **Underdog goal risk:** {res.get('underdog_scoring_risk')}",
                f"- **Data completeness:** {res.get('data_completeness')}",
                f"- **Strongest support:** {res.get('strongest_supporting_evidence')}",
                f"- **Strongest conflict:** {res.get('strongest_conflicting_evidence')}",
                "",
            ]
        )
    return "\n".join(lines)
