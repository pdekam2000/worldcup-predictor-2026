"""Forensic inventory of historical freezes for L2-F safe replay cohorts."""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

OWNER_SCOPES = frozenset({"production", "owner_shadow", "owner_daily"})

CLASS_ELIGIBLE_HISTORICAL = "eligible_historical_replay"
CLASS_ELIGIBLE_TRUE_FORWARD = "eligible_true_forward"
CLASS_BLOCKED_MISSING_FREEZE = "blocked_missing_freeze"
CLASS_BLOCKED_POSTKICKOFF = "blocked_postkickoff_contamination_risk"
CLASS_BLOCKED_MISSING_INPUTS = "blocked_missing_inputs"
CLASS_BLOCKED_INVALID_ODDS = "blocked_invalid_odds"
CLASS_BLOCKED_MISSING_RESULT = "blocked_missing_result"
CLASS_DUPLICATE = "duplicate/already_processed"


@dataclass
class FreezeCandidate:
    freeze_id: str
    fixture_id: int
    kickoff: str | None
    frozen_at: str | None
    prediction_scope: str | None
    validation_tier: str | None
    competition: str | None
    freeze_status: str | None
    lambda_home: float | None
    lambda_away: float | None
    has_result: bool
    actual_home: int | None
    actual_away: int | None
    classification: str
    block_reason: str | None = None
    is_first_for_fixture: bool = True


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "T").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s[:19] if len(s) >= 19 else s[:10], fmt if len(s) >= 16 else "%Y-%m-%d")
            except Exception:
                continue
    return None


def classify_row(
    *,
    freeze_status: str | None,
    quarantine_reason: str | None,
    scope: str | None,
    lh: Any,
    la: Any,
    kickoff: str | None,
    frozen_at: str | None,
    has_result: bool,
    now: datetime | None = None,
) -> tuple[str, str | None]:
    if freeze_status and str(freeze_status).upper() not in ("ACTIVE", ""):
        return CLASS_BLOCKED_MISSING_FREEZE, f"freeze_status_{freeze_status}"
    if quarantine_reason:
        return CLASS_BLOCKED_MISSING_FREEZE, "quarantined"
    if scope not in OWNER_SCOPES:
        return CLASS_BLOCKED_MISSING_INPUTS, f"scope_{scope}"
    if lh is None or la is None:
        return CLASS_BLOCKED_MISSING_INPUTS, "missing_canonical_lambdas"
    try:
        float(lh)
        float(la)
    except (TypeError, ValueError):
        return CLASS_BLOCKED_INVALID_ODDS, "invalid_lambda"
    ko = _parse_dt(kickoff)
    fr = _parse_dt(frozen_at)
    if ko is None or fr is None:
        return CLASS_BLOCKED_MISSING_INPUTS, "missing_timestamps"
    if fr >= ko:
        return CLASS_BLOCKED_POSTKICKOFF, "frozen_at_not_before_kickoff"
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if ko > now:
        # Future kickoff with valid freeze = true forward candidate
        return CLASS_ELIGIBLE_TRUE_FORWARD, None
    if not has_result:
        return CLASS_BLOCKED_MISSING_RESULT, "missing_final_result"
    return CLASS_ELIGIBLE_HISTORICAL, None


def inventory_eval_db(
    eval_conn: sqlite3.Connection,
    *,
    scopes: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[FreezeCandidate]:
    eval_conn.row_factory = sqlite3.Row
    scopes = list(scopes or OWNER_SCOPES)
    placeholders = ",".join("?" for _ in scopes)
    sql = f"""
        SELECT
          f.prediction_id AS freeze_id,
          f.fixture_id,
          f.kickoff,
          f.frozen_at,
          f.prediction_scope,
          f.validation_tier,
          f.competition,
          f.freeze_status,
          f.quarantine_reason,
          f.lambda_home,
          f.lambda_away,
          a.actual_home_goals,
          a.actual_away_goals,
          a.actual_score
        FROM frozen_predictions f
        LEFT JOIN actual_results a ON a.fixture_id = f.fixture_id
        WHERE IFNULL(f.prediction_scope, '') IN ({placeholders})
        ORDER BY f.fixture_id ASC, f.frozen_at ASC
    """
    rows = eval_conn.execute(sql, scopes).fetchall()
    out: list[FreezeCandidate] = []
    seen_fx: set[int] = set()
    for r in rows:
        fid = int(r["fixture_id"])
        first = fid not in seen_fx
        has_result = r["actual_score"] is not None and r["actual_home_goals"] is not None
        cls, reason = classify_row(
            freeze_status=r["freeze_status"],
            quarantine_reason=r["quarantine_reason"],
            scope=r["prediction_scope"],
            lh=r["lambda_home"],
            la=r["lambda_away"],
            kickoff=r["kickoff"],
            frozen_at=r["frozen_at"],
            has_result=has_result,
        )
        if not first and cls in (CLASS_ELIGIBLE_HISTORICAL, CLASS_ELIGIBLE_TRUE_FORWARD):
            cls = CLASS_DUPLICATE
            reason = "later_freeze_for_fixture"
        if first:
            seen_fx.add(fid)
        out.append(
            FreezeCandidate(
                freeze_id=str(r["freeze_id"]),
                fixture_id=fid,
                kickoff=r["kickoff"],
                frozen_at=r["frozen_at"],
                prediction_scope=r["prediction_scope"],
                validation_tier=r["validation_tier"],
                competition=r["competition"],
                freeze_status=r["freeze_status"],
                lambda_home=float(r["lambda_home"]) if r["lambda_home"] is not None else None,
                lambda_away=float(r["lambda_away"]) if r["lambda_away"] is not None else None,
                has_result=has_result,
                actual_home=int(r["actual_home_goals"]) if r["actual_home_goals"] is not None else None,
                actual_away=int(r["actual_away_goals"]) if r["actual_away_goals"] is not None else None,
                classification=cls,
                block_reason=reason,
                is_first_for_fixture=first,
            )
        )
        if limit is not None and len(out) >= limit:
            break
    return out


def summarize(candidates: list[FreezeCandidate]) -> dict[str, Any]:
    by_class = Counter(c.classification for c in candidates)
    by_league = Counter((c.competition or "unknown") for c in candidates if c.classification == CLASS_ELIGIBLE_HISTORICAL)
    by_scope = Counter((c.prediction_scope or "unknown") for c in candidates)
    by_date = Counter((c.kickoff or "")[:10] for c in candidates if c.classification == CLASS_ELIGIBLE_HISTORICAL)
    return {
        "total_rows": len(candidates),
        "by_classification": dict(by_class),
        "eligible_historical_replay": by_class.get(CLASS_ELIGIBLE_HISTORICAL, 0),
        "eligible_true_forward": by_class.get(CLASS_ELIGIBLE_TRUE_FORWARD, 0),
        "eligible_historical_by_league": dict(by_league.most_common(30)),
        "by_scope": dict(by_scope),
        "eligible_historical_by_date_top": dict(by_date.most_common(20)),
    }


def write_inventory_csv(candidates: list[FreezeCandidate], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not candidates:
        path.write_text("freeze_id,fixture_id,classification\n", encoding="utf-8")
        return
    fields = list(asdict(candidates[0]).keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in candidates:
            w.writerow(asdict(c))


def write_inventory_report(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
