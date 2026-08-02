"""Finished-fixture recovery ledger: account for every finished fixture."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.prediction_engine_75 import phase1 as p1
from worldcup_predictor.research.prediction_engine_75.phase2 import extract_1x2_from_snapshot

ROOT = Path(__file__).resolve().parents[4]
FI_DB = ROOT / "data" / "football_intelligence.db"
FWD_DB = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"

PRIMARY_EXCLUSIONS = {
    "NO_PREMATCH_PREDICTION",
    "NO_IMMUTABLE_FREEZE",
    "POST_KICKOFF_PREDICTION",
    "NO_PREMATCH_ODDS",
    "INCOMPLETE_ODDS",
    "ODDS_TIMESTAMP_INVALID",
    "RESULT_ONLY_FIXTURE",
    "MISSING_WDE",
    "MISSING_ECSE",
    "FEATURE_PROVENANCE_MISSING",
    "DUPLICATE",
    "RESULT_CONFLICT",
    "HOME_AWAY_MAPPING_CONFLICT",
    "UNSUPPORTED_HISTORICAL_DOMAIN",
    "RECOVERABLE_FROM_ARCHIVE",
    "RECOVERABLE_FROM_PROVIDER_CACHE",
    "VALID_ALREADY_INCLUDED",
    "MANUAL_REVIEW",
}


def _open_ro(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _actual_1x2(row: sqlite3.Row) -> str | None:
    if row["regulation_home_goals"] is not None and row["regulation_away_goals"] is not None:
        hg, ag = int(row["regulation_home_goals"]), int(row["regulation_away_goals"])
    elif row["home_goals"] is not None and row["away_goals"] is not None:
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
    else:
        return None
    return "home" if hg > ag else "away" if ag > hg else "draw"


@dataclass
class LedgerRow:
    fixture_id: int
    date: str | None = None
    country: str | None = None
    league: str | None = None
    season: str | None = None
    home: str | None = None
    away: str | None = None
    kickoff: str | None = None
    confirmed_regulation_result: str | None = None
    final_score: str | None = None
    canonical_prediction_exists: bool = False
    prediction_timestamp: str | None = None
    freeze_exists: bool = False
    freeze_timestamp: str | None = None
    odds_snapshot_exists: bool = False
    odds_timestamp: str | None = None
    complete_hda_exists: bool = False
    odds_prematch_valid: bool = False
    wde_payload_exists: bool = False
    ecse_payload_exists: bool = False
    team_history_features_exist: bool = False
    provider_cache_exists: bool = False
    artifact_references: str = ""
    current_eligibility: str = "EXCLUDED"
    primary_exclusion_reason: str = "RESULT_ONLY_FIXTURE"
    secondary_exclusion_reasons: list[str] = field(default_factory=list)
    recoverable: bool = False
    recovery_source: str | None = None
    leakage_risk: str = "NONE"
    already_in_prior_corpus: bool = False
    recovery_type: str | None = None
    cohort_label: str | None = None


def _load_finished(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT fr.fixture_id, fr.home_goals, fr.away_goals, fr.final_score,
                   fr.regulation_home_goals, fr.regulation_away_goals,
                   fx.kickoff_utc, fx.home_team, fx.away_team, fx.competition_key,
                   fx.season, fx.league_id, fx.city, fx.competition_type
            FROM fixture_results fr
            LEFT JOIN fixtures fx ON fx.fixture_id = fr.fixture_id
            WHERE fr.home_goals IS NOT NULL
            ORDER BY fx.kickoff_utc, fr.fixture_id
            """
        )
    )


def _index_stored(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for r in conn.execute(
        """
        SELECT fixture_id, predicted_at, payload_json, is_quarantined, quarantine_reason
        FROM worldcup_stored_predictions
        WHERE COALESCE(is_active,1)=1
        ORDER BY predicted_at DESC
        """
    ):
        fid = int(r["fixture_id"])
        if fid in out:
            continue
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        wde = None
        if isinstance(payload, dict):
            wde = p1._norm_dir(payload.get("prediction") or payload.get("selected_1x2") or payload.get("direction"))
        out[fid] = {
            "predicted_at": r["predicted_at"],
            "wde": wde,
            "quarantined": bool(r["is_quarantined"]),
            "quarantine_reason": r["quarantine_reason"],
            "has_payload": bool(payload),
        }
    return out


def _index_ecse(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for r in conn.execute(
        """
        SELECT fixture_id, generated_at, kickoff_utc, is_frozen
        FROM ecse_prediction_snapshots
        WHERE COALESCE(is_frozen,0)=1
        ORDER BY generated_at DESC
        """
    ):
        fid = int(r["fixture_id"])
        if fid in out:
            continue
        out[fid] = {"generated_at": r["generated_at"], "kickoff_utc": r["kickoff_utc"], "frozen": True}
    return out


def _index_odds(conn: sqlite3.Connection, finished_ids: set[int]) -> dict[int, dict[str, Any]]:
    """Best prematch extractable H/D/A per fixture among finished set."""
    out: dict[int, dict[str, Any]] = {}
    if not finished_ids:
        return out
    # pull only finished
    ids = sorted(finished_ids)
    # chunk
    for i in range(0, len(ids), 400):
        chunk = ids[i : i + 400]
        qmarks = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT fixture_id, snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id IN ({qmarks})",
            tuple(chunk),
        ).fetchall()
        by: dict[int, list] = {}
        for r in rows:
            by.setdefault(int(r["fixture_id"]), []).append(r)
        ko_map = {
            int(r["fixture_id"]): p1._parse_dt(r["kickoff_utc"])
            for r in conn.execute(
                f"SELECT fixture_id, kickoff_utc FROM fixtures WHERE fixture_id IN ({qmarks})",
                tuple(chunk),
            )
        }
        for fid, snaps in by.items():
            ko = ko_map.get(fid)
            has_any = True
            candidates = []
            post_only = 0
            bad_ts = 0
            no_1x2 = 0
            for s in snaps:
                st = p1._parse_dt(s["snapshot_at"])
                if ko and st and st >= ko:
                    post_only += 1
                    continue
                if st is None:
                    bad_ts += 1
                    continue
                try:
                    payload = json.loads(s["payload_json"] or "{}")
                except json.JSONDecodeError:
                    continue
                odds = extract_1x2_from_snapshot(payload)
                if not odds:
                    no_1x2 += 1
                    continue
                candidates.append((st, odds, s["snapshot_at"]))
            if candidates:
                candidates.sort(key=lambda x: x[0])
                earliest, latest = candidates[0], candidates[-1]
                out[fid] = {
                    "exists": True,
                    "complete_hda": True,
                    "prematch_valid": True,
                    "earliest_at": earliest[2],
                    "latest_at": latest[2],
                    "home": latest[1]["home"],
                    "draw": latest[1]["draw"],
                    "away": latest[1]["away"],
                    "n_books": latest[1].get("n_books"),
                    "n_prematch_snaps": len(candidates),
                    "post_only_snaps": post_only,
                    "bad_ts_snaps": bad_ts,
                }
            else:
                reason = "NO_PREMATCH_ODDS"
                if post_only and not bad_ts:
                    reason = "ODDS_TIMESTAMP_INVALID" if False else "POST_KICKOFF_ONLY_ODDS"
                if bad_ts and not post_only:
                    reason = "ODDS_TIMESTAMP_INVALID"
                elif post_only:
                    reason = "POST_KICKOFF_ONLY_ODDS"
                elif no_1x2:
                    reason = "INCOMPLETE_ODDS"
                out[fid] = {
                    "exists": has_any,
                    "complete_hda": False,
                    "prematch_valid": False,
                    "block_reason": reason,
                    "post_only_snaps": post_only,
                    "bad_ts_snaps": bad_ts,
                }
    return out


def _index_freezes() -> dict[int, dict[str, Any]]:
    conn = _open_ro(FWD_DB)
    if conn is None:
        return {}
    out: dict[int, dict[str, Any]] = {}
    try:
        for r in conn.execute(
            """
            SELECT fixture_id, frozen_at, kickoff, wde_decision, odds_home, odds_draw, odds_away,
                   immutable, freeze_status, content_hash, payload_hash
            FROM frozen_predictions
            ORDER BY frozen_at DESC
            """
        ):
            fid = int(r["fixture_id"])
            if fid in out:
                continue
            ko, fr = p1._parse_dt(r["kickoff"]), p1._parse_dt(r["frozen_at"])
            prematch = bool(ko and fr and fr < ko)
            out[fid] = {
                "frozen_at": r["frozen_at"],
                "kickoff": r["kickoff"],
                "wde": p1._norm_dir(r["wde_decision"]),
                "prematch": prematch,
                "immutable": bool(r["immutable"]),
                "priced": all(x is not None and float(x) > 1.0 for x in (r["odds_home"], r["odds_draw"], r["odds_away"])),
                "content_hash": r["content_hash"] or r["payload_hash"],
            }
    finally:
        conn.close()
    return out


def _index_form(conn: sqlite3.Connection) -> set[int]:
    try:
        return {
            int(r[0])
            for r in conn.execute("SELECT DISTINCT fixture_id FROM derived_historical_team_form_snapshots")
        }
    except Exception:
        return set()


def _index_provider_map(conn: sqlite3.Connection) -> set[int]:
    try:
        return {
            int(r[0])
            for r in conn.execute(
                """
                SELECT DISTINCT CAST(provider_fixture_id AS INTEGER)
                FROM historical_provider_mapping
                WHERE provider_fixture_id GLOB '[0-9]*'
                """
            )
        }
    except Exception:
        return set()


def classify_row(
    *,
    actual: str | None,
    stored: dict | None,
    ecse: dict | None,
    odds: dict | None,
    freeze: dict | None,
    has_form: bool,
    has_provider_map: bool,
    prior_valid_ids: set[int],
    fid: int,
    kickoff: str | None,
) -> LedgerRow:
    row = LedgerRow(fixture_id=fid)
    secondary: list[str] = []
    ko_dt = p1._parse_dt(kickoff)

    if stored:
        row.canonical_prediction_exists = True
        row.prediction_timestamp = stored.get("predicted_at")
        row.wde_payload_exists = bool(stored.get("wde"))
    if freeze:
        row.freeze_exists = True
        row.freeze_timestamp = freeze.get("frozen_at")
        if freeze.get("wde"):
            row.wde_payload_exists = True
    if ecse:
        row.ecse_payload_exists = True
    if odds:
        row.odds_snapshot_exists = bool(odds.get("exists"))
        row.odds_timestamp = odds.get("latest_at") or odds.get("earliest_at")
        row.complete_hda_exists = bool(odds.get("complete_hda"))
        row.odds_prematch_valid = bool(odds.get("prematch_valid"))
    row.team_history_features_exist = has_form
    row.provider_cache_exists = has_provider_map
    row.already_in_prior_corpus = fid in prior_valid_ids

    pred_at = None
    if freeze and freeze.get("prematch") and freeze.get("wde"):
        pred_at = freeze.get("frozen_at")
        row.recovery_type = "A"
        row.recovery_source = "forward_prediction_tracking.frozen_predictions"
        row.cohort_label = "HISTORICAL_IMMUTABLE_PREMATCH_FREEZE"
    elif stored and stored.get("wde") and not stored.get("quarantined"):
        pred_at = stored.get("predicted_at")
        pr_dt = p1._parse_dt(pred_at)
        if ko_dt and pr_dt and pr_dt >= ko_dt:
            row.primary_exclusion_reason = "POST_KICKOFF_PREDICTION"
            row.leakage_risk = "HIGH"
            row.current_eligibility = "EXCLUDED"
            row.recoverable = False
            return row
        if ko_dt and pr_dt and pr_dt < ko_dt:
            row.recovery_type = "B"
            row.recovery_source = "worldcup_stored_predictions"
            row.cohort_label = "HISTORICAL_TIMESTAMPED_PREMATCH_PAYLOAD"
        elif not pr_dt:
            secondary.append("PREDICTION_TIMESTAMP_MISSING")
            row.primary_exclusion_reason = "FEATURE_PROVENANCE_MISSING"
            row.leakage_risk = "MEDIUM"
            row.recoverable = False
            row.current_eligibility = "EXCLUDED"
            row.secondary_exclusion_reasons = secondary
            return row
    elif ecse:
        gen = ecse.get("generated_at")
        g_dt = p1._parse_dt(gen)
        ko2 = ko_dt or p1._parse_dt(ecse.get("kickoff_utc"))
        if ko2 and g_dt and g_dt >= ko2:
            row.primary_exclusion_reason = "POST_KICKOFF_PREDICTION"
            row.leakage_risk = "HIGH"
            row.current_eligibility = "EXCLUDED"
            return row
        if ko2 and g_dt and g_dt < ko2:
            pred_at = gen
            row.recovery_type = "A"
            row.recovery_source = "ecse_prediction_snapshots"
            row.cohort_label = "HISTORICAL_IMMUTABLE_PREMATCH_FREEZE"
            row.prediction_timestamp = gen
        else:
            secondary.append("ECSE_TIMESTAMP_UNVERIFIED")

    has_model = bool(row.wde_payload_exists or row.ecse_payload_exists)
    has_priced = bool(row.odds_prematch_valid and row.complete_hda_exists)

    if fid in prior_valid_ids and has_model and actual:
        row.primary_exclusion_reason = "VALID_ALREADY_INCLUDED"
        row.current_eligibility = "VALID"
        row.recoverable = False
        row.secondary_exclusion_reasons = secondary
        return row

    if has_model and actual and row.cohort_label:
        if fid in prior_valid_ids:
            row.primary_exclusion_reason = "VALID_ALREADY_INCLUDED"
            row.recoverable = False
            row.current_eligibility = "VALID"
        else:
            row.primary_exclusion_reason = "RECOVERABLE_FROM_ARCHIVE"
            row.recoverable = True
            row.current_eligibility = "VALID_RECOVERABLE"
        if not has_priced:
            br = (odds or {}).get("block_reason") if odds else None
            secondary.append("NO_PREMATCH_ODDS" if not row.odds_snapshot_exists else (br or "INCOMPLETE_ODDS"))
        row.secondary_exclusion_reasons = secondary
        row.prediction_timestamp = row.prediction_timestamp or pred_at
        return row

    # No model prediction — classify exclusion
    if not stored and not freeze and not ecse:
        if has_priced:
            row.primary_exclusion_reason = "NO_PREMATCH_PREDICTION"
            row.recoverable = True
            row.recovery_type = "C"
            row.recovery_source = "odds_snapshots"
            row.cohort_label = "HISTORICAL_PROVIDER_PREMATCH_DATA"
            row.current_eligibility = "ODDS_ONLY_RECOVERABLE"
            secondary.append("MISSING_WDE")
            secondary.append("MISSING_ECSE")
            row.leakage_risk = "LOW"
        elif row.odds_snapshot_exists and odds and odds.get("block_reason") == "POST_KICKOFF_ONLY_ODDS":
            row.primary_exclusion_reason = "ODDS_TIMESTAMP_INVALID"
            secondary.append("POST_KICKOFF_ONLY_ODDS")
            row.leakage_risk = "HIGH"
            row.recoverable = False
            row.current_eligibility = "EXCLUDED"
        elif row.odds_snapshot_exists:
            row.primary_exclusion_reason = odds.get("block_reason") if odds else "INCOMPLETE_ODDS"
            if row.primary_exclusion_reason not in PRIMARY_EXCLUSIONS:
                # map custom
                if row.primary_exclusion_reason == "POST_KICKOFF_ONLY_ODDS":
                    row.primary_exclusion_reason = "ODDS_TIMESTAMP_INVALID"
                else:
                    row.primary_exclusion_reason = "INCOMPLETE_ODDS"
            row.recoverable = False
            row.current_eligibility = "EXCLUDED"
        elif has_provider_map:
            row.primary_exclusion_reason = "RECOVERABLE_FROM_PROVIDER_CACHE"
            row.recoverable = True
            row.recovery_source = "historical_provider_mapping"
            row.current_eligibility = "POTENTIALLY_RECOVERABLE"
            secondary.append("NO_PREMATCH_PREDICTION")
            secondary.append("FEATURE_PROVENANCE_MISSING")
            row.leakage_risk = "MEDIUM"
        else:
            row.primary_exclusion_reason = "RESULT_ONLY_FIXTURE"
            row.recoverable = False
            row.current_eligibility = "EXCLUDED"
            secondary.append("NO_PREMATCH_PREDICTION")
            secondary.append("NO_IMMUTABLE_FREEZE")
            secondary.append("NO_PREMATCH_ODDS")
    elif stored and not stored.get("wde"):
        row.primary_exclusion_reason = "MISSING_WDE"
        row.recoverable = bool(ecse)
        row.current_eligibility = "EXCLUDED"
    else:
        row.primary_exclusion_reason = "NO_PREMATCH_PREDICTION"
        row.current_eligibility = "EXCLUDED"
        row.recoverable = False

    if not has_form:
        secondary.append("FEATURE_PROVENANCE_MISSING")
    row.secondary_exclusion_reasons = sorted(set(secondary))
    return row


def build_ledger(prior_valid_ids: set[int] | None = None) -> tuple[list[LedgerRow], dict[str, Any]]:
    prior_valid_ids = prior_valid_ids or set()
    conn = _open_ro(FI_DB)
    if conn is None:
        raise FileNotFoundError(str(FI_DB))
    try:
        finished = _load_finished(conn)
        finished_ids = {int(r["fixture_id"]) for r in finished}
        stored = _index_stored(conn)
        ecse = _index_ecse(conn)
        odds = _index_odds(conn, finished_ids)
        form_ids = _index_form(conn)
        provider_ids = _index_provider_map(conn)
    finally:
        conn.close()
    freezes = _index_freezes()

    rows: list[LedgerRow] = []
    for fr in finished:
        fid = int(fr["fixture_id"])
        actual = _actual_1x2(fr)
        ko = str(fr["kickoff_utc"] or "") or None
        base = classify_row(
            actual=actual,
            stored=stored.get(fid),
            ecse=ecse.get(fid),
            odds=odds.get(fid),
            freeze=freezes.get(fid),
            has_form=fid in form_ids,
            has_provider_map=fid in provider_ids,
            prior_valid_ids=prior_valid_ids,
            fid=fid,
            kickoff=ko,
        )
        base.date = (ko or "")[:10] or None
        base.league = str(fr["competition_key"] or "") or None
        base.season = str(fr["season"] or "") or None
        base.home = fr["home_team"]
        base.away = fr["away_team"]
        base.kickoff = ko
        base.confirmed_regulation_result = actual
        base.final_score = str(fr["final_score"] or "") or None
        base.country = None  # not separately stored on fixtures
        if freezes.get(fid):
            base.artifact_references = "forward_prediction_tracking.frozen_predictions"
        elif stored.get(fid):
            base.artifact_references = "worldcup_stored_predictions"
        elif ecse.get(fid):
            base.artifact_references = "ecse_prediction_snapshots"
        rows.append(base)

    # funnel
    primary = Counter(r.primary_exclusion_reason for r in rows)
    eligibility = Counter(r.current_eligibility for r in rows)
    funnel = {
        "total_finished": len(rows),
        "with_canonical_prediction": sum(1 for r in rows if r.canonical_prediction_exists),
        "with_freeze": sum(1 for r in rows if r.freeze_exists),
        "with_ecse_frozen": sum(1 for r in rows if r.ecse_payload_exists),
        "with_odds_any": sum(1 for r in rows if r.odds_snapshot_exists),
        "with_prematch_priced_hda": sum(1 for r in rows if r.odds_prematch_valid),
        "valid_already_included": sum(1 for r in rows if r.primary_exclusion_reason == "VALID_ALREADY_INCLUDED"),
        "valid_recoverable_model": sum(1 for r in rows if r.current_eligibility == "VALID_RECOVERABLE"),
        "odds_only_recoverable": sum(1 for r in rows if r.current_eligibility == "ODDS_ONLY_RECOVERABLE"),
        "result_only": sum(1 for r in rows if r.primary_exclusion_reason == "RESULT_ONLY_FIXTURE"),
        "primary_exclusion_counts": dict(primary),
        "eligibility_counts": dict(eligibility),
        "accounted_for": len(rows),
        "silent_drop": 0,
    }
    assert funnel["accounted_for"] == funnel["total_finished"]
    return rows, funnel


def ledger_to_dicts(rows: list[LedgerRow]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        d = asdict(r)
        d["secondary_exclusion_reasons"] = "|".join(r.secondary_exclusion_reasons)
        out.append(d)
    return out


def content_hash_obj(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
