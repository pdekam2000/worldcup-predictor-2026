#!/usr/bin/env python3
"""Controlled owner-only true-forward for three 2026-07-31 fixtures.

Canonical WDE/ECSE first → immutable freeze → Lambda V2 / Exact V2 shadow.
No promotion. Screenshot odds are reference-only (never injected).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.forward_evaluation.bridge import (
    ForwardEvalBridgeContext,
    maybe_capture_after_prediction_persistence,
)
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
from worldcup_predictor.gpt_actions.config import GptActionsConfig, load_gpt_actions_config
from worldcup_predictor.gpt_actions.job_status import build_job_status_fields
from worldcup_predictor.gpt_actions.jobs import JobStore
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.gpt_actions.wde_runtime import register_tier_b_competition_runtime
from worldcup_predictor.gpt_actions.worker import enqueue_prediction_job
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.odds.refresh_gate import ensure_fresh_odds_before_prediction, refresh_live_odds
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.research.ecse_live.store import get_snapshot
from worldcup_predictor.research.infra_l2f_forward.research_preview import build_fixture_preview
from worldcup_predictor.research.team_form_h2h_forensic.agent import TeamFormH2HForensicAgent

TZ = ZoneInfo("Europe/Vienna")
FRESH_OK = frozenset({FreshnessStatus.FRESH_ODDS.value, "fresh", "ODDS_FRESH", "FRESH_ODDS"})
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
ART = ROOT / "artifacts" / "owner_three_fixture_tf" / "2026-07-31" / RUN_ID

TARGETS = [
    {
        "label": "Dundee United vs Glasgow Rangers",
        "fixture_id": 1556628,
        "expect_home": ("dundee",),
        "expect_away": ("ranger",),
        "bookmaker_comp": "Scotland Premiership",
        "expect_vienna": "2026-07-31 21:00",
        "screenshot_odds": {"home": 5.25, "draw": 4.50, "away": 1.53},
        "provider_league_id": 179,
        "canonical_key": "scottish_premiership",
    },
    {
        "label": "Bodø/Glimt vs Lillestrøm SK",
        "fixture_id": 1494717,
        "expect_home": ("bodo", "glimt"),
        "expect_away": ("lille",),
        "bookmaker_comp": "Norway Eliteserien",
        "expect_vienna": "2026-07-31 21:00",
        "screenshot_odds": {"home": 1.25, "draw": 6.75, "away": 9.50},
        "provider_league_id": 103,
        "canonical_key": "eliteserien",
    },
    {
        "label": "FC Flyeralarm Admira vs SK Rapid Wien II",
        "fixture_id": 1567860,
        "expect_home": ("admira",),
        "expect_away": ("rapid",),
        "bookmaker_comp": "Austria 2. Liga",
        "expect_vienna": "2026-07-31 18:30",
        "screenshot_odds": {"home": 2.40, "draw": 3.40, "away": 2.75},
        "provider_league_id": 219,
        "canonical_key": "austria_2_liga",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _vienna(v: str | None) -> str | None:
    dt = _parse_dt(v)
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M %Z") if dt else None


def _f(v: Any) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _odds_blob(snap: Any) -> dict[str, Any]:
    if snap is None:
        return {"complete": False}
    home = _f(getattr(snap, "home_odds", None))
    draw = _f(getattr(snap, "draw_odds", None))
    away = _f(getattr(snap, "away_odds", None))
    if home is None and isinstance(snap, dict):
        home = _f(snap.get("home") or snap.get("home_odds"))
        draw = _f(snap.get("draw") or snap.get("draw_odds"))
        away = _f(snap.get("away") or snap.get("away_odds"))
    freshness = getattr(snap, "freshness_class", None) or getattr(snap, "freshness_status", None)
    if isinstance(snap, dict):
        freshness = freshness or snap.get("freshness_status") or snap.get("freshness_class")
    age = getattr(snap, "odds_age_minutes", None)
    if age is None and hasattr(snap, "age_seconds") and getattr(snap, "age_seconds") is not None:
        age = float(snap.age_seconds) / 60.0
    ts = getattr(snap, "fetched_at_utc", None) or getattr(snap, "captured_at", None)
    if isinstance(snap, dict):
        ts = ts or snap.get("captured_at") or snap.get("fetched_at_utc")
        age = age if age is not None else snap.get("odds_age_minutes")
    return {
        "home": home,
        "draw": draw,
        "away": away,
        "bookmaker_count": getattr(snap, "bookmaker_count", None)
        if not isinstance(snap, dict)
        else snap.get("bookmaker_count"),
        "provider": "api-football",
        "odds_timestamp": ts,
        "odds_age_minutes": age,
        "freshness_status": freshness,
        "complete": bool(home and draw and away and home > 1 and draw > 1 and away > 1),
        "snapshot_id": getattr(snap, "row_id", None) if not isinstance(snap, dict) else snap.get("snapshot_id"),
    }


def _poll(job_id: str, store: JobStore, cfg: GptActionsConfig, deadline_s: int = 600) -> dict:
    final = None
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        rec = store.get(job_id)
        if not rec or not rec.get("job_id"):
            time.sleep(1)
            continue
        fields = build_job_status_fields(rec, poll_after_seconds=cfg.poll_after_seconds)
        if fields.get("terminal"):
            final = {**rec, **fields}
            break
        time.sleep(max(1, int(fields.get("poll_after_seconds") or 3)))
    return {"final": final, "timed_out": final is None}


def _name_ok(name: str, tokens: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(t in low for t in tokens)


def _sync_fixture(settings, target: dict[str, Any]) -> dict[str, Any]:
    client = ApiFootballClient(settings)
    fid = int(target["fixture_id"])
    res = client.get_fixture_by_id(fid)
    if not res.ok or not res.data:
        return {"ok": False, "reason": f"provider_fetch_failed:{getattr(res, 'error', None)}"}
    item = res.data[0] if isinstance(res.data, list) else res.data
    parsed = parse_api_fixture_item(item, source="api_football")
    if not parsed:
        return {"ok": False, "reason": "parse_failed"}
    league = (item.get("league") or {})
    season = league.get("season") or 2026
    canon = target["canonical_key"]
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    register_tier_b_competition_runtime(canon, repo=repo, season=int(season))
    repo.upsert_fixture(parsed, competition_key=canon, league_id=int(target["provider_league_id"]), season=int(season))
    repo._conn.commit()
    return {
        "ok": True,
        "home": parsed.home_team,
        "away": parsed.away_team,
        "kickoff_utc": parsed.kickoff_time.isoformat() if parsed.kickoff_time else None,
        "status": parsed.status,
        "provider_league_name": league.get("name"),
        "provider_country": league.get("country"),
        "season": season,
    }


def _load_freeze(eval_conn, fid: int) -> dict[str, Any] | None:
    row = eval_conn.execute(
        "SELECT * FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at DESC LIMIT 1",
        (int(fid),),
    ).fetchone()
    return dict(row) if row else None


def _extract_pred(prod, fid: int) -> dict[str, Any]:
    from worldcup_predictor.gpt_actions.bridge_semantics import extract_wde_semantics

    stored = prod.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
        (fid,),
    ).fetchone()
    snap = get_snapshot(prod, fid) or {}
    if not stored:
        return {"complete": False}
    try:
        payload = json.loads(stored["payload_json"] if hasattr(stored, "keys") else stored[0])
    except Exception:
        return {"complete": False}
    sem = extract_wde_semantics(payload)
    probs = payload.get("probabilities") or {}
    return {
        "complete": bool(sem.get("decision_pick")),
        "wde": {
            "decision": sem.get("decision_pick"),
            "confidence": sem.get("confidence") or payload.get("confidence"),
            "p_home": sem.get("p_home"),
            "p_draw": sem.get("p_draw"),
            "p_away": sem.get("p_away"),
        },
        "btts": probs.get("btts"),
        "ou25": probs.get("over_under_2_5"),
        "no_bet": payload.get("no_bet"),
        "predicted_at": stored["predicted_at"] if hasattr(stored, "keys") else stored[1],
        "ecse_snapshot": snap,
    }


def _map_forensic_verdict(fr: dict[str, Any], agreement: dict[str, Any] | None) -> str:
    cls = str(fr.get("classification") or "")
    agr = str((agreement or {}).get("agreement_classification") or "")
    if cls in {"INSUFFICIENT_FORENSIC_DATA"} or fr.get("error"):
        return "HIGH_UNCERTAINTY"
    if cls == "NO_BET":
        return "BLOCK"
    if agr in {"MODELS_CONFLICT", "EXACT_V2_HIGH_GOAL_SHIFT"} and cls in {"TOP5_FRAGILE", "HEDGE_RECOMMENDED"}:
        return "MIXED"
    if cls in {"TOP5_STRONGLY_SUPPORTED", "TOP5_SUPPORTED_WITH_RISK", "DIRECTION_ONLY_RECOMMENDED"}:
        if agr in {"MODELS_AGREE", "MODELS_PARTIAL_AGREEMENT"}:
            return "SUPPORTS_CANONICAL"
        if agr == "EXACT_V2_HIGH_GOAL_SHIFT":
            return "MIXED"
        return "SUPPORTS_CANONICAL"
    if agr == "MODELS_AGREE":
        return "SUPPORTS_CANONICAL"
    return "MIXED"


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    bootstrap_gpt_actions_runtime()
    settings = get_settings()
    prod = connect(settings.sqlite_path)
    eval_conn = connect_eval_db()
    base_cfg = load_gpt_actions_config()
    job_dir = ART / "jobs"
    cfg = GptActionsConfig(
        host=base_cfg.host,
        port=base_cfg.port,
        api_key=base_cfg.api_key,
        audit_log_path=str(ART / "audit.jsonl"),
        job_store_dir=str(job_dir),
        max_jobs_retained=50,
        rate_limit_per_minute=base_cfg.rate_limit_per_minute,
        max_fixture_ids_per_job=base_cfg.max_fixture_ids_per_job,
        max_response_chars=base_cfg.max_response_chars,
        poll_after_seconds=base_cfg.poll_after_seconds,
    )
    store = JobStore(str(job_dir), max_retained=50)
    forensic_agent = TeamFormH2HForensicAgent(settings=settings)
    results: list[dict[str, Any]] = []

    try:
        for t in TARGETS:
            fid = int(t["fixture_id"])
            out: dict[str, Any] = {
                "label": t["label"],
                "fixture_id": fid,
                "screenshot_odds_reference_only": t["screenshot_odds"],
                "bookmaker_competition_label": t["bookmaker_comp"],
            }
            sync = _sync_fixture(settings, t)
            out["sync"] = sync
            if not sync.get("ok"):
                out["status"] = "BLOCKED_SYNC"
                out["block_reason"] = sync.get("reason")
                results.append(out)
                continue

            prod.close()
            prod = connect(settings.sqlite_path)
            fx = prod.execute(
                "SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key, league_id, season FROM fixtures WHERE fixture_id=?",
                (fid,),
            ).fetchone()
            if not fx:
                out["status"] = "BLOCKED_FIXTURE_NOT_IN_DB"
                results.append(out)
                continue

            home, away = str(fx["home_team"]), str(fx["away_team"])
            ko = str(fx["kickoff_utc"])
            status = str(fx["status"] or "NS").upper()
            comp_raw = str(fx["competition_key"] or "")
            comp = normalize_competition_key(comp_raw) or t["canonical_key"]
            tier = fixture_tier(comp) or fixture_tier(t["canonical_key"])
            vie = _vienna(ko)
            out.update(
                {
                    "home_team": home,
                    "away_team": away,
                    "kickoff_utc": ko,
                    "kickoff_vienna": vie,
                    "fixture_status": status,
                    "competition_key": comp,
                    "provider_league_id": fx["league_id"],
                    "validation_tier": tier,
                    "prediction_scope": "owner_shadow",
                    "competition_name_mismatch": {
                        "bookmaker_label": t["bookmaker_comp"],
                        "provider_league_name": sync.get("provider_league_name"),
                        "provider_country": sync.get("provider_country"),
                        "canonical_key": comp,
                        "flagged": True
                        if t["bookmaker_comp"].lower() not in str(sync.get("provider_league_name") or "").lower()
                        and str(sync.get("provider_league_name") or "").lower() not in t["bookmaker_comp"].lower()
                        else False,
                        "note": "Naming may differ (e.g. Scotland Premiership vs Premiership) while league_id matches.",
                    },
                }
            )

            if not _name_ok(home, t["expect_home"]) or not _name_ok(away, t["expect_away"]):
                out["status"] = "BLOCKED_TEAM_MISMATCH"
                out["block_reason"] = f"expected tokens home={t['expect_home']} away={t['expect_away']} got {home} vs {away}"
                results.append(out)
                continue
            if not vie or not vie.startswith(t["expect_vienna"][:16]):
                # soft check: allow if same hour
                if t["expect_vienna"] not in str(vie):
                    out["kickoff_warning"] = f"expected {t['expect_vienna']} Vienna, got {vie}"
            if status not in {"NS", "TBD", "SCHEDULED", "TIMED", ""}:
                out["status"] = f"BLOCKED_STATUS:{status}"
                results.append(out)
                continue
            if tier not in ("A", "B"):
                out["status"] = "BLOCKED_UNSUPPORTED_COMPETITION"
                out["block_reason"] = f"tier={tier} competition={comp}"
                results.append(out)
                continue

            ko_dt = _parse_dt(ko)
            if ko_dt and datetime.now(timezone.utc) >= ko_dt:
                out["status"] = "BLOCKED_POST_KICKOFF"
                results.append(out)
                continue

            daily = DailyFixture(
                fixture_id=fid,
                provider_fixture_id=fid,
                competition_key=comp,
                home_team=home,
                away_team=away,
                kickoff_utc=ko,
                status=status,
                season=fx["season"],
            )
            before = _odds_blob(get_latest_valid_1x2_odds_snapshot(prod, fid, kickoff_utc=ko))
            forced = refresh_live_odds(daily, settings=settings)
            prod.close()
            prod = connect(settings.sqlite_path)
            gate = ensure_fresh_odds_before_prediction(
                prod,
                {"fixture_id": fid, "kickoff_utc": ko, "status": status},
                daily,
                settings=settings,
                refresh_if_needed=True,
            )
            after = _odds_blob(get_latest_valid_1x2_odds_snapshot(prod, fid, kickoff_utc=ko))
            fresh = bool(gate.get("allowed")) and after.get("complete") and (
                str(after.get("freshness_status") or "") in FRESH_OK
                or str((gate.get("freshness") or {}).get("odds_freshness_status") or "") in FRESH_OK
            )
            out["odds"] = {
                "before": before,
                "after": after,
                "refresh_success": bool(forced.get("success")),
                "gate_allowed": bool(gate.get("allowed")),
                "fresh": fresh,
                "block": None
                if fresh
                else str(gate.get("final_block_reason") or gate.get("reason") or "STALE_OR_MISSING_ODDS"),
                "screenshot_vs_provider_delta": {
                    "home": round(float(after["home"]) - float(t["screenshot_odds"]["home"]), 3)
                    if after.get("home")
                    else None,
                    "draw": round(float(after["draw"]) - float(t["screenshot_odds"]["draw"]), 3)
                    if after.get("draw")
                    else None,
                    "away": round(float(after["away"]) - float(t["screenshot_odds"]["away"]), 3)
                    if after.get("away")
                    else None,
                    "note": "reference comparison only; screenshot odds not injected",
                },
            }
            if not fresh:
                out["status"] = "BLOCKED_ODDS"
                out["block_reason"] = out["odds"]["block"]
                results.append(out)
                continue

            existing_fr = _load_freeze(eval_conn, fid)
            pred_exists = prod.execute(
                "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1", (fid,)
            ).fetchone()
            snap = get_snapshot(prod, fid)
            reused = bool(existing_fr and pred_exists and snap)

            if reused:
                out["prediction_mode"] = "REUSE_IMMUTABLE_FREEZE"
                freeze_meta = {
                    "capture_status": "reused",
                    "freeze_id": existing_fr.get("prediction_id"),
                    "content_hash": existing_fr.get("content_hash"),
                    "frozen_at": existing_fr.get("frozen_at"),
                    "reused": True,
                    "created": False,
                    "prediction_scope": "owner_shadow",
                }
                job_id = None
                terminal = "reused_existing"
            else:
                out["prediction_mode"] = "NEW_PREDICTION_JOB"
                job_id = str(uuid.uuid4())
                record = {
                    "job_id": job_id,
                    "status": "queued",
                    "created_at": _utc_now(),
                    "request": {
                        "fixture_ids": [fid],
                        "prediction_scope": "owner_shadow",
                        "refresh_if_stale": True,
                        "include_all_predictions": True,
                        "date": "2026-07-31",
                        "timezone": "Europe/Vienna",
                        "scope": "owner",
                    },
                }
                store._path(job_id).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
                enqueue_prediction_job(job_id, store=store, config=cfg)
                poll = _poll(job_id, store, cfg)
                final = poll.get("final") or store.get(job_id) or {}
                terminal = str(final.get("status") or ("timeout" if poll.get("timed_out") else "unknown"))
                prod.close()
                prod = connect(settings.sqlite_path)
                snap_id = None
                pred_tmp = _extract_pred(prod, fid)
                snap = get_snapshot(prod, fid) or {}
                if snap.get("snapshot_id") is not None:
                    snap_id = int(snap["snapshot_id"])
                elif snap.get("id") is not None:
                    snap_id = int(snap["id"])
                bridge = maybe_capture_after_prediction_persistence(
                    fid,
                    prod_conn=prod,
                    bridge_context=ForwardEvalBridgeContext(
                        prediction_scope="owner_shadow",
                        validation_tier="B",
                        public_visible=False,
                        source_job_id=job_id,
                        bridge_origin="gpt_actions",
                        worldcup_stored_prediction_id=fid,
                        ecse_snapshot_id=snap_id,
                    ),
                    quality_status="OK" if pred_tmp.get("complete") else "PARTIAL",
                    ecse_snapshot_id=snap_id,
                )
                freeze_meta = bridge.to_metadata_block() if hasattr(bridge, "to_metadata_block") else {}
                fr = _load_freeze(eval_conn, fid) or {}
                if not freeze_meta.get("frozen_at"):
                    freeze_meta["frozen_at"] = fr.get("frozen_at")
                freeze_meta["prediction_scope"] = "owner_shadow"

            # True-forward shadow after freeze
            from worldcup_predictor.research.infra_l2f_forward.forward_hook import maybe_run_l2f_forward_shadow

            hash_before = (_load_freeze(eval_conn, fid) or {}).get("content_hash")
            shadow = maybe_run_l2f_forward_shadow(
                conn=prod,
                fixture_id=fid,
                freeze_meta=freeze_meta,
                prediction_scope="owner_shadow",
                settings=settings,
                backfill=False,
            )
            hash_after = (_load_freeze(eval_conn, fid) or {}).get("content_hash")

            preview = build_fixture_preview(
                prod=prod,
                fi=prod,
                eval_conn=eval_conn,
                fixture_id=fid,
                freeze_hash_before=hash_before,
            )
            # Integrity odds from fresh snapshot
            if preview.get("integrity") is not None and after.get("odds_timestamp"):
                preview["integrity"]["odds_timestamp_before_kickoff"] = (
                    _parse_dt(str(after["odds_timestamp"])) is not None
                    and ko_dt is not None
                    and _parse_dt(str(after["odds_timestamp"])) < ko_dt
                )
                preview["integrity"]["canonical_freeze_hash_unchanged_after_shadow"] = hash_before == hash_after

            forensic = forensic_agent.analyze_fixture(
                fixture_id=fid,
                home_team=home,
                away_team=away,
                kickoff_utc=ko,
                competition_key=comp,
            )
            agent_verdict = _map_forensic_verdict(forensic, preview.get("agreement"))

            out.update(
                {
                    "status": "OK",
                    "job_id": job_id,
                    "job_terminal": terminal,
                    "freeze": freeze_meta,
                    "l2f_forward_shadow": shadow,
                    "preview": preview,
                    "forensic": forensic,
                    "agent_verdict": agent_verdict,
                    "freeze_hash_before": hash_before,
                    "freeze_hash_after": hash_after,
                    "canonical_pred": _extract_pred(prod, fid),
                }
            )
            results.append(out)
    finally:
        forensic_agent.close()
        try:
            prod.close()
        except Exception:
            pass
        try:
            eval_conn.close()
        except Exception:
            pass

    payload = {
        "run_id": RUN_ID,
        "generated_at_utc": _utc_now(),
        "labels": {"canonical": "CANONICAL", "shadow": "SHADOW_RESEARCH_ONLY"},
        "no_promotion": True,
        "no_routing_activation": True,
        "results": results,
    }
    _write_json(ART / "results.json", payload)
    print(json.dumps({"run_id": RUN_ID, "art": str(ART), "statuses": [(r["fixture_id"], r.get("status"), r.get("block_reason")) for r in results]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
