#!/usr/bin/env python3
"""CONTROLLED-1X2-ROUND-OF-16-1 — Sync missing fixtures + complete four-match 1X2 set."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.odds.freshness_audit import _latest_odds
from worldcup_predictor.odds.freshness_policy import classify_odds_freshness, is_knockout_match, is_low_priority_match
from worldcup_predictor.odds.freshness_refresh import run_odds_freshness_refresh
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.predictions import run_daily_predictions
from worldcup_predictor.owner_daily.wc_fixture_import import _import_single_fixture

PHASE = "CONTROLLED-1X2-ROUND-OF-16-1"
EXPECTED_BASELINE = "b512e0bd600de12849dfaa0104ae643dff54afe0"
ARTIFACT_DIR = ROOT / "artifacts" / "controlled_1x2_round_of_16_1"
PY = str(ROOT / ".venv" / "bin" / "python")
MAX_ODDS_CALLS = 40

TARGETS = [
    {"key": "mexico_england", "home": "Mexico", "away": "England", "fixture_id": 1570714, "existing": True},
    {"key": "portugal_spain", "home": "Portugal", "away": "Spain", "fixture_id": 1576756, "existing": True},
    {"key": "argentina_egypt", "home": "Argentina", "away": "Egypt", "fixture_id": None, "existing": False},
    {"key": "switzerland_colombia", "home": "Switzerland", "away": "Colombia", "fixture_id": None, "existing": False},
]

TEAM_ALIASES: dict[str, set[str]] = {
    "Mexico": {"mexico", "mex"},
    "England": {"england", "eng"},
    "Portugal": {"portugal", "por"},
    "Spain": {"spain", "esp"},
    "Argentina": {"argentina", "arg"},
    "Egypt": {"egypt", "egy"},
    "Switzerland": {"switzerland", "sui", "schweiz"},
    "Colombia": {"colombia", "col"},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _norm(name: str) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _team_match(name: str, canonical: str) -> bool:
    n = _norm(name)
    if n == _norm(canonical):
        return True
    aliases = TEAM_ALIASES.get(canonical, set())
    return n in aliases or _norm(canonical) in n


def _pair_match(home: str, away: str, t_home: str, t_away: str) -> bool:
    return _team_match(home, t_home) and _team_match(away, t_away)


def _payload_hash(raw: str | None) -> str:
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _run(cmd: list[str], *, timeout: int = 120) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return {
        "cmd": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
    }


@dataclass
class PhaseResult:
    phase: str = PHASE
    started_at: str = field(default_factory=_utc_now)
    finished_at: str = ""
    preflight: dict[str, Any] = field(default_factory=dict)
    discovery: dict[str, Any] = field(default_factory=dict)
    import_result: dict[str, Any] = field(default_factory=dict)
    odds_audit_before: list[dict[str, Any]] = field(default_factory=list)
    odds_refresh: dict[str, Any] = field(default_factory=dict)
    odds_audit_after: list[dict[str, Any]] = field(default_factory=list)
    forensic: dict[str, Any] = field(default_factory=dict)
    predictions: dict[str, Any] = field(default_factory=dict)
    recompute_decisions: dict[str, Any] = field(default_factory=dict)
    owner_table: list[dict[str, Any]] = field(default_factory=list)
    risk: dict[str, Any] = field(default_factory=dict)
    ecse_guard: dict[str, Any] = field(default_factory=dict)
    recommendation: str = "VALIDATION_FAILED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "preflight": self.preflight,
            "discovery": self.discovery,
            "import_result": self.import_result,
            "odds_audit_before": self.odds_audit_before,
            "odds_refresh": self.odds_refresh,
            "odds_audit_after": self.odds_audit_after,
            "forensic": self.forensic,
            "predictions": self.predictions,
            "recompute_decisions": self.recompute_decisions,
            "owner_table": self.owner_table,
            "risk": self.risk,
            "ecse_guard": self.ecse_guard,
            "recommendation": self.recommendation,
        }


def _preflight(settings: Settings) -> dict[str, Any]:
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    git_short = subprocess.run(
        ["git", "log", "-1", "--oneline"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    svc = {}
    for svc_name in ("worldcup-api", "nginx"):
        r = subprocess.run(["systemctl", "is-active", svc_name], capture_output=True, text=True)
        svc[svc_name] = r.stdout.strip()
    timers = _run(["systemctl", "list-timers", "--all"]).get("stdout", "")
    wc_timers = [ln for ln in timers.splitlines() if "worldcup" in ln.lower()]
    db_path = settings.sqlite_path or ""
    db_exists = Path(db_path).exists() if db_path else False
    return {
        "git_head": git_head,
        "git_short": git_short,
        "expected_baseline": EXPECTED_BASELINE,
        "baseline_match": git_head.startswith(EXPECTED_BASELINE[:12]),
        "services": svc,
        "worldcup_timers": wc_timers,
        "timers_note": "timers_present_report_only",
        "db_path": db_path,
        "db_exists": db_exists,
    }


def _discover_from_provider(
    settings: Settings,
    *,
    home: str,
    away: str,
    season_data: list[dict[str, Any]] | None = None,
    api_calls: int = 0,
) -> tuple[dict[str, Any] | None, int]:
    api = ApiFootballClient(settings)
    comp = get_competition("world_cup_2026")
    data = season_data
    calls = api_calls
    if data is None:
        if not api.is_configured:
            return None, calls
        comp = get_competition("world_cup_2026")
        fetch = api.get_historical_fixtures(
            league_id=comp.league_id,
            season=comp.season,
            status="NS",
        )
        calls += 1
        if not fetch.ok or not isinstance(fetch.data, list):
            return None, calls
        data = fetch.data

    for item in data:
        teams = item.get("teams") or {}
        th = str((teams.get("home") or {}).get("name") or "")
        ta = str((teams.get("away") or {}).get("name") or "")
        if not (_pair_match(th, ta, home, away) or _pair_match(ta, th, home, away)):
            continue
        fix = item.get("fixture") or {}
        league = item.get("league") or {}
        fid = int(fix.get("id") or 0)
        if not fid:
            continue
        kickoff = str(fix.get("date") or "")
        dt_vienna = "—"
        try:
            dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_vienna = dt.astimezone(ZoneInfo("Europe/Vienna")).strftime("%Y-%m-%d %H:%M %Z")
        except ValueError:
            pass
        swapped = _pair_match(ta, th, home, away)
        return {
            "provider_fixture_id": fid,
            "home_team": th if not swapped else ta,
            "away_team": ta if not swapped else th,
            "kickoff_utc": kickoff,
            "kickoff_vienna": dt_vienna,
            "stage": league.get("name"),
            "round": league.get("round"),
            "status": (fix.get("status") or {}).get("short") or "NS",
            "provider_source": "api-football",
        }, calls
    return None, calls


def _duplicate_check(conn: sqlite3.Connection, *, fid: int, home: str, away: str, kickoff: str) -> dict[str, Any]:
    by_id = conn.execute(
        "SELECT fixture_id, home_team, away_team, kickoff_utc FROM fixtures WHERE fixture_id=? AND is_placeholder=0",
        (fid,),
    ).fetchone()
    by_teams = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc FROM fixtures
        WHERE is_placeholder=0 AND competition_key='world_cup_2026'
          AND home_team=? AND away_team=? AND kickoff_utc=?
        """,
        (home, away, kickoff.replace("Z", "").replace("+00:00", "")[:19]),
    ).fetchall()
    return {
        "by_provider_id_exists": bool(by_id),
        "by_provider_id_row": dict(by_id) if by_id else None,
        "by_teams_kickoff_count": len(by_teams),
        "duplicate_risk": bool(by_id) or len(by_teams) > 1,
    }


def _import_provider_fixture(
    settings: Settings,
    item: dict[str, Any],
    *,
    dry_run: bool = False,
) -> str:
    comp = get_competition("world_cup_2026")
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    conn = repo._conn
    try:
        outcome = _import_single_fixture(
            item,
            competition_key="world_cup_2026",
            season=comp.season,
            league_id=comp.league_id,
            conn=conn,
            repo=repo,
            dry_run=dry_run,
        )
        if not dry_run:
            conn.commit()
        return outcome
    finally:
        repo.close()


def _audit_fixture(conn: sqlite3.Connection, fid: int, tz: ZoneInfo) -> dict[str, Any]:
    row = conn.execute(
        "SELECT fixture_id, home_team, away_team, kickoff_utc, status, round_name FROM fixtures WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    fx = dict(row) if row else {"fixture_id": fid}
    odds = _latest_odds(conn, fid)
    knockout = is_knockout_match(round_name=fx.get("round_name"), status=fx.get("status"))
    low_pri = is_low_priority_match(kickoff_utc=fx.get("kickoff_utc"))
    cls = classify_odds_freshness(
        odds_snapshot_at=odds["snapshot_at"] if odds else None,
        knockout=knockout,
        low_priority=low_pri,
        odds_source=odds.get("source") if odds else None,
        has_odds=bool(odds),
    )
    status_map = {
        "FRESH": "FRESH_ODDS",
        "STALE": "STALE_ODDS",
        "MISSING": "MISSING_ODDS",
        "UNKNOWN": "UNKNOWN_ODDS",
    }
    bucket = status_map.get(cls.status.value, "UNKNOWN_ODDS")
    has_1x2 = False
    if odds and odds.get("snapshot_at"):
        snap = conn.execute(
            "SELECT payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
            (fid,),
        ).fetchone()
        if snap:
            try:
                p = json.loads(snap["payload_json"])
                txt = json.dumps(p).lower()
                has_1x2 = any(k in txt for k in ("match winner", "1x2", "home/draw/away", "home_win"))
            except (json.JSONDecodeError, TypeError):
                has_1x2 = False
    kickoff_vienna = "—"
    if fx.get("kickoff_utc"):
        try:
            dt = datetime.fromisoformat(str(fx["kickoff_utc"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            kickoff_vienna = dt.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")
        except ValueError:
            kickoff_vienna = str(fx["kickoff_utc"])
    return {
        "fixture_id": fid,
        "match": f"{fx.get('home_team', '?')} vs {fx.get('away_team', '?')}",
        "kickoff_vienna": kickoff_vienna,
        "snapshot_at": odds["snapshot_at"] if odds else None,
        "age_hours": cls.odds_age_hours,
        "source": odds.get("source") if odds else None,
        "freshness_status": bucket,
        "policy_status": cls.status.value,
        "has_1x2_market": has_1x2,
    }


def _forensic_wde(conn: sqlite3.Connection, fid: int) -> dict[str, Any]:
    wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    odds = _latest_odds(conn, fid)
    odds_count = conn.execute(
        "SELECT COUNT(*) FROM odds_snapshots WHERE fixture_id=?", (fid,)
    ).fetchone()[0]
    payload = {}
    if wde and wde["payload_json"]:
        payload = json.loads(wde["payload_json"])
    probs = payload.get("probabilities") or {}
    meta = payload.get("odds_freshness_metadata") or {}
    trace = payload.get("data_source_trace") or {}
    specialist = payload.get("specialist_report") or {}
    intel = payload.get("intelligence_report") or {}
    bookmaker_used = any(
        k in json.dumps(payload).lower()
        for k in ("bookmaker", "implied_prob", "odds_home", "market_odds", "consensus_odds")
    )
    wde_without_odds = odds_count == 0 and meta.get("freshness_flag") == "ODDS_MISSING"
    metadata_gap = odds_count > 0 and meta.get("freshness_flag") == "ODDS_MISSING"
    return {
        "fixture_id": fid,
        "payload_hash": _payload_hash(wde["payload_json"] if wde else None),
        "predicted_at": wde["predicted_at"] if wde else None,
        "odds_snapshots_in_db": int(odds_count),
        "latest_odds_snapshot_at": odds["snapshot_at"] if odds else None,
        "payload_odds_status": payload.get("odds_freshness_status"),
        "payload_odds_metadata": meta,
        "wde_ran_without_bookmaker_odds": wde_without_odds,
        "odds_in_db_but_metadata_missing": metadata_gap,
        "provider_probabilities_consumed": bookmaker_used,
        "odds_missing_classification": (
            "true_input_absence" if wde_without_odds else ("metadata_only_gap" if metadata_gap else "mixed_or_present")
        ),
        "pick_1x2": payload.get("prediction"),
        "confidence": payload.get("confidence"),
        "probabilities_1x2": {
            "home": probs.get("home_win"),
            "draw": probs.get("draw"),
            "away": probs.get("away_win"),
        },
        "engine_version": payload.get("prediction_engine_version"),
        "trace": trace,
        "has_specialist_report": bool(specialist),
        "has_intelligence_report": bool(intel),
    }


def _extract_1x2(conn: sqlite3.Connection, fid: int) -> dict[str, Any]:
    wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    fx = conn.execute(
        "SELECT home_team, away_team, kickoff_utc, round_name, status FROM fixtures WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    if not wde:
        return {"fixture_id": fid, "stored": False}
    p = json.loads(wde["payload_json"])
    probs = p.get("probabilities") or {}
    h, d, a = probs.get("home_win"), probs.get("draw"), probs.get("away_win")
    pick = p.get("prediction")
    meta = p.get("odds_freshness_metadata") or {}
    return {
        "fixture_id": fid,
        "stored": True,
        "match": f"{fx['home_team']} vs {fx['away_team']}" if fx else str(fid),
        "kickoff_utc": fx["kickoff_utc"] if fx else None,
        "round": fx["round_name"] if fx else None,
        "pick_1x2": pick,
        "confidence": p.get("confidence"),
        "H": h,
        "X": d,
        "A": a,
        "prob_sum": round(float(h or 0) + float(d or 0) + float(a or 0), 2) if all(v is not None for v in (h, d, a)) else None,
        "odds_status": p.get("odds_freshness_status") or meta.get("freshness_flag"),
        "odds_snapshot_at": meta.get("odds_snapshot_at") or p.get("odds_snapshot_at"),
        "odds_source": meta.get("odds_source"),
        "predicted_at": wde["predicted_at"],
        "engine_version": p.get("prediction_engine_version"),
        "payload_hash": _payload_hash(wde["payload_json"]),
    }


def _classify_risk(row: dict[str, Any], odds: dict[str, Any]) -> str:
    conf = float(row.get("confidence") or 0)
    odds_st = odds.get("freshness_status") or "MISSING_ODDS"
    if odds_st in ("MISSING_ODDS", "UNKNOWN_ODDS") and conf < 40:
        return "LOW_CONVICTION + INSUFFICIENT_ODDS_CONTEXT"
    if odds_st in ("MISSING_ODDS", "UNKNOWN_ODDS"):
        return "INSUFFICIENT_ODDS_CONTEXT"
    if conf >= 55 and odds_st == "FRESH_ODDS":
        return "HIGH_CONVICTION"
    if conf >= 45:
        return "MEDIUM_CONVICTION"
    return "LOW_CONVICTION"


def _recompute_decision(conn: sqlite3.Connection, fid: int, forensic: dict[str, Any]) -> str:
    fx = conn.execute("SELECT kickoff_utc, status FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
    if not fx:
        return "DO_NOT_REGENERATE_AFTER_KICKOFF"
    status = str(fx["status"] or "").upper()
    if status in ("FT", "AET", "PEN", "LIVE", "1H", "2H", "HT"):
        return "DO_NOT_REGENERATE_AFTER_KICKOFF"
    kickoff = fx["kickoff_utc"]
    if kickoff:
        try:
            dt = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt <= datetime.now(timezone.utc):
                return "DO_NOT_REGENERATE_AFTER_KICKOFF"
        except ValueError:
            pass
    if forensic.get("odds_in_db_but_metadata_missing"):
        return "ODDS_METADATA_ONLY_PATCH"
    if forensic.get("odds_missing_classification") == "true_input_absence":
        if forensic.get("latest_odds_snapshot_at"):
            return "SAFE_TO_REGENERATE_BEFORE_KICKOFF"
        return "KEEP_FROZEN_EXISTING_PICK"
    return "KEEP_FROZEN_EXISTING_PICK"


def _ecse_counts(conn: sqlite3.Connection, fids: list[int]) -> dict[int, int]:
    out = {}
    for fid in fids:
        out[fid] = conn.execute(
            "SELECT COUNT(*) FROM ecse_prediction_snapshots WHERE fixture_id=?", (fid,)
        ).fetchone()[0]
    return out


def _rankings(rows: list[dict[str, Any]], odds_map: dict[int, dict]) -> dict[str, list]:
    by_prob = sorted(
        [r for r in rows if r.get("stored")],
        key=lambda r: max(float(r.get("H") or 0), float(r.get("X") or 0), float(r.get("A") or 0)),
        reverse=True,
    )
    by_conf = sorted([r for r in rows if r.get("stored")], key=lambda r: float(r.get("confidence") or 0), reverse=True)
    fresh_rank = {"FRESH_ODDS": 3, "STALE_ODDS": 2, "UNKNOWN_ODDS": 1, "MISSING_ODDS": 0}

    def _fresh(fid: int) -> int:
        return fresh_rank.get(odds_map.get(fid, {}).get("freshness_status", "MISSING_ODDS"), 0)

    by_odds = sorted([r for r in rows if r.get("stored")], key=lambda r: _fresh(int(r["fixture_id"])), reverse=True)
    return {
        "by_selected_outcome_probability": [r["match"] for r in by_prob],
        "by_model_confidence": [r["match"] for r in by_conf],
        "by_odds_freshness_quality": [r["match"] for r in by_odds],
    }


def render_owner_table(rows: list[dict[str, Any]], odds_map: dict[int, dict], risk_map: dict[int, str]) -> str:
    lines = [
        "# CONTROLLED_1X2_ROUND_OF_16_OWNER_TABLE",
        "",
        f"**Generated:** {_utc_now()}",
        "",
        "| Match | Pick | H | X | A | Confidence | Odds | Status |",
        "| ----- | ---- | -: | -: | -: | ---------: | ---- | ------ |",
    ]
    for r in rows:
        fid = int(r["fixture_id"])
        odds = odds_map.get(fid, {})
        pick = r.get("pick_1x2") or "—"
        if pick == "home":
            pick_disp = "Home"
        elif pick == "away":
            pick_disp = "Away"
        elif pick == "draw":
            pick_disp = "Draw"
        else:
            pick_disp = str(pick)
        lines.append(
            f"| {r.get('match', fid)} | {pick_disp} | {r.get('H', '—')} | {r.get('X', '—')} | {r.get('A', '—')} | "
            f"{r.get('confidence', '—')} | {odds.get('freshness_status', '—')} | {risk_map.get(fid, '—')} |"
        )
    return "\n".join(lines) + "\n"


def render_report(result: PhaseResult) -> str:
    lines = [
        f"# {PHASE} — Report",
        "",
        f"**Started:** {result.started_at}",
        f"**Finished:** {result.finished_at}",
        f"**Recommendation:** `{result.recommendation}`",
        "",
        "## Production commit",
        "",
        f"- HEAD: `{result.preflight.get('git_head')}`",
        f"- Expected baseline: `{EXPECTED_BASELINE}`",
        "",
        "## Fixture discovery",
        "",
        json.dumps(result.discovery, indent=2),
        "",
        "## Missing fixture import",
        "",
        json.dumps(result.import_result, indent=2),
        "",
        "## Odds audit (before / after)",
        "",
        "### Before",
        "",
        json.dumps(result.odds_audit_before, indent=2),
        "",
        "### Refresh",
        "",
        json.dumps(result.odds_refresh, indent=2),
        "",
        "### After",
        "",
        json.dumps(result.odds_audit_after, indent=2),
        "",
        "## Forensic — Mexico & Portugal",
        "",
        json.dumps(result.forensic, indent=2),
        "",
        "## Recompute decisions (Mexico & Portugal)",
        "",
        json.dumps(result.recompute_decisions, indent=2),
        "",
        "## 1X2 predictions",
        "",
        json.dumps(result.owner_table, indent=2),
        "",
        "## Rankings",
        "",
        json.dumps(result.risk.get("rankings", {}), indent=2),
        "",
        "## Risk classification",
        "",
        json.dumps(result.risk.get("by_fixture", {}), indent=2),
        "",
        "## ECSE guard",
        "",
        json.dumps(result.ecse_guard, indent=2),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    result = PhaseResult()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo("Europe/Vienna")

    result.preflight = _preflight(settings)
    conn = connect(settings.sqlite_path)
    api = ApiFootballClient(settings)

    # Capture existing state
    existing_hashes = {}
    for t in TARGETS:
        if t["existing"] and t["fixture_id"]:
            w = conn.execute(
                "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?",
                (t["fixture_id"],),
            ).fetchone()
            existing_hashes[t["fixture_id"]] = _payload_hash(w["payload_json"] if w else None)

    all_fids_pre: list[int] = [t["fixture_id"] for t in TARGETS if t["fixture_id"]]
    ecse_before_all = _ecse_counts(conn, all_fids_pre)

    # Part B — provider discovery (single season fetch)
    season_data: list[dict[str, Any]] | None = None
    provider_calls = 0
    discovery_entries: list[dict[str, Any]] = []
    if api.is_configured:
        comp = get_competition("world_cup_2026")
        fetch = api.get_historical_fixtures(
            league_id=comp.league_id,
            season=comp.season,
            status="NS",
        )
        provider_calls += 1
        if fetch.ok and isinstance(fetch.data, list):
            season_data = fetch.data
        else:
            result.discovery["season_fetch_error"] = fetch.error
    else:
        result.discovery["api_configured"] = False

    for t in TARGETS:
        entry: dict[str, Any] = {"key": t["key"], "home": t["home"], "away": t["away"], "existing": t["existing"]}
        if t["existing"]:
            entry["fixture_id"] = t["fixture_id"]
            entry["status"] = "already_in_db"
            discovery_entries.append(entry)
            continue
        found, provider_calls = _discover_from_provider(
            settings, home=t["home"], away=t["away"], season_data=season_data, api_calls=provider_calls
        )
        if found:
            entry.update(found)
            entry["status"] = "found_in_provider"
        else:
            entry["status"] = "FIXTURE_NOT_AVAILABLE_FROM_PROVIDER"
        discovery_entries.append(entry)
    result.discovery = {"entries": discovery_entries, "provider_calls_discovery": provider_calls}

    # Part C + import missing
    import_log: list[dict[str, Any]] = []
    for entry in discovery_entries:
        if entry.get("status") != "found_in_provider":
            continue
        fid = int(entry["provider_fixture_id"])
        dup = _duplicate_check(
            conn,
            fid=fid,
            home=entry["home_team"],
            away=entry["away_team"],
            kickoff=str(entry["kickoff_utc"]),
        )
        import_item: dict[str, Any] = {"fixture_id": fid, "duplicate_check": dup}
        if dup["duplicate_risk"] and dup["by_provider_id_exists"]:
            import_item["outcome"] = "skipped_existing"
            row = conn.execute(
                "SELECT fixture_id, home_team, away_team, kickoff_utc, status, round_name FROM fixtures WHERE fixture_id=?",
                (fid,),
            ).fetchone()
            if row:
                import_item["local_row"] = dict(row)
            import_log.append(import_item)
            entry["fixture_id"] = fid
            continue
        if not api.is_configured:
            import_item["outcome"] = "api_not_configured"
            import_log.append(import_item)
            continue
        item_fetch = api.get_fixture_by_id(fid)
        provider_calls += 1
        if not item_fetch.ok or not isinstance(item_fetch.data, list) or not item_fetch.data:
            import_item["outcome"] = "provider_fetch_failed"
            import_item["error"] = item_fetch.error
            import_log.append(import_item)
            continue
        outcome = _import_provider_fixture(settings, item_fetch.data[0], dry_run=False)
        import_item["outcome"] = outcome
        row = conn.execute(
            "SELECT fixture_id, home_team, away_team, kickoff_utc, status, round_name FROM fixtures WHERE fixture_id=?",
            (fid,),
        ).fetchone()
        if row:
            import_item["local_row"] = dict(row)
            entry["fixture_id"] = fid
        import_log.append(import_item)

    for t in TARGETS:
        for entry in discovery_entries:
            if entry["key"] == t["key"] and entry.get("fixture_id"):
                t["fixture_id"] = entry["fixture_id"]

    result.import_result = {"imports": import_log, "provider_calls_import": provider_calls}

    # Resolve final fixture ids
    fixture_ids = [t["fixture_id"] for t in TARGETS if t["fixture_id"]]
    if len(fixture_ids) < 4:
        missing = [t["key"] for t in TARGETS if not t["fixture_id"]]
        result.discovery["missing_after_import"] = missing

    # Part D — odds audit before
    for fid in fixture_ids:
        result.odds_audit_before.append(_audit_fixture(conn, fid, tz))

    # Part E — odds refresh (bounded)
    refresh_calls_used = 0
    refresh_runs: list[dict[str, Any]] = []
    for fid in fixture_ids:
        if refresh_calls_used >= MAX_ODDS_CALLS:
            break
        before = next(x for x in result.odds_audit_before if x["fixture_id"] == fid)
        if before["freshness_status"] == "FRESH_ODDS":
            refresh_runs.append({"fixture_id": fid, "skipped": True, "reason": "already_fresh"})
            continue
        remaining = MAX_ODDS_CALLS - refresh_calls_used
        per_fixture_cap = min(10, remaining)
        dry = run_odds_freshness_refresh(
            fixture_id=fid,
            mode="refresh",
            max_provider_calls=per_fixture_cap,
            dry_run=True,
            settings=settings,
        )
        would = dry.would_refresh or 0
        real = None
        if would > 0 and not dry.dry_run:
            pass
        if would > 0:
            real = run_odds_freshness_refresh(
                fixture_id=fid,
                mode="refresh",
                max_provider_calls=per_fixture_cap,
                dry_run=False,
                settings=settings,
            )
            pc = real.provider_calls or {}
            refresh_calls_used += sum(int(v) for v in pc.values())
        refresh_runs.append(
            {
                "fixture_id": fid,
                "before": before["freshness_status"],
                "dry_run_would_refresh": would,
                "refreshed": real.refreshed if real else 0,
                "provider_calls": real.provider_calls if real else {},
            }
        )
    result.odds_refresh = {
        "max_total_calls": MAX_ODDS_CALLS,
        "calls_used": refresh_calls_used,
        "runs": refresh_runs,
    }

    for fid in fixture_ids:
        result.odds_audit_after.append(_audit_fixture(conn, fid, tz))

    # Part F — forensic existing
    result.forensic = {
        "mexico_england": _forensic_wde(conn, 1570714),
        "portugal_spain": _forensic_wde(conn, 1576756),
    }
    result.recompute_decisions = {
        "1570714": _recompute_decision(conn, 1570714, result.forensic["mexico_england"]),
        "1576756": _recompute_decision(conn, 1576756, result.forensic["portugal_spain"]),
    }

    # Part G — WDE-only for newly imported only
    new_fids = [t["fixture_id"] for t in TARGETS if not t["existing"] and t["fixture_id"]]
    pred_fixtures: list[DailyFixture] = []
    for fid in new_fids:
        row = conn.execute(
            "SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key FROM fixtures WHERE fixture_id=?",
            (fid,),
        ).fetchone()
        if not row:
            continue
        pred_fixtures.append(
            DailyFixture(
                fixture_id=int(row["fixture_id"]),
                provider_fixture_id=int(row["fixture_id"]),
                competition_key=str(row["competition_key"]),
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                kickoff_utc=str(row["kickoff_utc"] or ""),
                status=str(row["status"] or "NS"),
                season=None,
                coverage_sources=["local_db"],
            )
        )
    if pred_fixtures:
        pred_out = run_daily_predictions(pred_fixtures, mode="wde_only", dry_run=False, force=False, settings=settings)
        result.predictions = pred_out.to_dict()
    else:
        result.predictions = {"note": "no_new_fixtures_to_predict", "new_fids": new_fids}

    # ECSE guard
    ecse_after_all = _ecse_counts(conn, fixture_ids)
    result.ecse_guard = {
        "before": ecse_before_all,
        "after": ecse_after_all,
        "new_ecse_created": {
            str(fid): ecse_after_all.get(fid, 0) - ecse_before_all.get(fid, 0)
            for fid in fixture_ids
        },
    }

    # Verify existing preserved
    preserved = {}
    for fid, h in existing_hashes.items():
        w = conn.execute(
            "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (fid,)
        ).fetchone()
        preserved[str(fid)] = _payload_hash(w["payload_json"] if w else None) == h
    result.forensic["existing_payload_preserved"] = preserved

    # Owner table + risk
    odds_map = {a["fixture_id"]: a for a in result.odds_audit_after}
    owner_rows = []
    risk_by_fid: dict[int, str] = {}
    for fid in fixture_ids:
        row = _extract_1x2(conn, fid)
        owner_rows.append(row)
        risk_by_fid[fid] = _classify_risk(row, odds_map.get(fid, {}))
    result.owner_table = owner_rows
    result.risk = {
        "by_fixture": {str(k): v for k, v in risk_by_fid.items()},
        "rankings": _rankings(owner_rows, odds_map),
    }

    conn.close()

    # Recommendation
    all_four = len(fixture_ids) == 4
    all_stored = all(r.get("stored") for r in owner_rows)
    all_odds_missing = all(
        odds_map.get(fid, {}).get("freshness_status") in ("MISSING_ODDS", "UNKNOWN_ODDS") for fid in fixture_ids
    )
    ecse_ok = all(v <= 0 for v in result.ecse_guard.get("new_ecse_created", {}).values())
    preserved_ok = all(preserved.values())

    if not preserved_ok:
        result.recommendation = "VALIDATION_FAILED"
    elif not all_four:
        result.recommendation = "MISSING_FIXTURES_NOT_AVAILABLE"
    elif all_stored and all_odds_missing:
        result.recommendation = "ODDS_CONTEXT_INSUFFICIENT" if ecse_ok else "VALIDATION_FAILED"
    elif all_stored and ecse_ok:
        result.recommendation = "FOUR_MATCH_1X2_SET_COMPLETE"
    elif all_stored:
        result.recommendation = "PARTIAL_1X2_SET_COMPLETE"
    else:
        result.recommendation = "PARTIAL_1X2_SET_COMPLETE"

    result.finished_at = _utc_now()

    workflow_path = ARTIFACT_DIR / "workflow.json"
    workflow_path.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    (ROOT / "CONTROLLED_1X2_ROUND_OF_16_OWNER_TABLE.md").write_text(
        render_owner_table(owner_rows, odds_map, risk_by_fid), encoding="utf-8"
    )
    (ROOT / "CONTROLLED_1X2_ROUND_OF_16_1_REPORT.md").write_text(render_report(result), encoding="utf-8")

    print(json.dumps({"artifact": str(workflow_path), "recommendation": result.recommendation}, indent=2))
    return 0 if result.recommendation != "VALIDATION_FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
