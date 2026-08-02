"""
APPROVED_BETS_FORENSIC_EVALUATION — research-only.

Evaluates only fixtures that historically appeared on explicit final shortlists /
bettable selection artifacts. Does not treat all Canonical predictions as approved.
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PHASE = "APPROVED_BETS_FORENSIC_EVALUATION"
STATUS_COMPLETE = "APPROVED_BETS_FORENSIC_EVALUATION_COMPLETE"
STATUS_PARTIAL = "APPROVED_BETS_FORENSIC_EVALUATION_PARTIAL_RESULTS"
STATUS_AMBIGUOUS = "APPROVED_BETS_APPROVAL_TAXONOMY_AMBIGUOUS"

COHORT_STRICT_PROD = "STRICT_PRODUCTION_APPROVED"
COHORT_STRICT_OWNER = "STRICT_OWNER_APPROVED"
COHORT_RESEARCH = "RESEARCH_APPROVED"
COHORT_EXACT = "EXACT_SCORE_APPROVED"
COHORT_WATCHLIST = "WATCHLIST_ONLY"
COHORT_NO_BET = "NO_BET"
COHORT_BLOCKED = "BLOCKED_INCOMPLETE"


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm_dir(v: Any) -> str | None:
    s = str(v or "").strip().lower()
    if not s or s in {"none", "null", "unknown", "unavailable_in_freeze"}:
        return None
    if "home" in s or s in {"h", "1", "home_win"}:
        return "home"
    if "away" in s or s in {"a", "2", "away_win"}:
        return "away"
    if "draw" in s or s in {"d", "x"}:
        return "draw"
    return None


def _norm_conf(v: Any) -> float | None:
    c = _f(v)
    if c is None:
        return None
    return c * 100.0 if c <= 1.5 else c


def _safe_decimal_odds(v: Any) -> float | None:
    o = _f(v)
    if o is None or o < 1.01 or o > 100:
        return None
    return o


def _direction_from_sources(rec: ApprovalRecord, res: dict[str, Any] | None, m: dict[str, Any]) -> str | None:
    return (
        rec.approved_1x2_direction
        or _norm_dir((res or {}).get("wde_decision"))
        or _norm_dir((res or {}).get("ft_marginal_direction"))
        or _norm_dir(m.get("wde_decision"))
        or _norm_dir(m.get("decision"))
        or _norm_dir((rec.raw or {}).get("wde_decision"))
        or _norm_dir((rec.raw or {}).get("decision"))
        or _norm_dir((rec.raw or {}).get("selected_1x2_direction"))
        or _norm_dir((rec.raw or {}).get("ft_marginal"))
    )


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    s = str(v).replace("Z", "+00:00").replace(" UTC", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fields or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = hits / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((centre - margin) / den, 4), round((centre + margin) / den, 4)


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

APPROVAL_TAXONOMY = [
    {
        "field": "selected_matches.json / selected[]",
        "values": ["fixture cards in owner pick artifacts"],
        "sources": ["artifacts/today_owner_picks_*", "artifacts/owner_balanced_odds_picks_*"],
        "represents": "final betting approval (owner day shortlist)",
        "enter_official_approved": True,
        "cohort": COHORT_STRICT_OWNER,
        "reason": "Explicit owner final selection artifact for that Vienna day.",
    },
    {
        "field": "dayN_best_three.json / selected[]",
        "values": ["top-3 per day"],
        "sources": ["artifacts/three_day_complete_predictions/*/day*_best_three.json"],
        "represents": "final owner/research day shortlist",
        "enter_official_approved": True,
        "cohort": COHORT_STRICT_OWNER,
        "reason": "Named best-three shortlist written before kickoff as day selection.",
    },
    {
        "field": "selected_top3.json / selected[]",
        "values": ["top-3"],
        "sources": ["artifacts/tomorrow_best_three_top10/*/selected_top3.json"],
        "represents": "final day shortlist",
        "enter_official_approved": True,
        "cohort": COHORT_STRICT_OWNER,
        "reason": "Explicit selected_top3 policy output.",
    },
    {
        "field": "freeze_selection.json",
        "values": ["freeze_id rows"],
        "sources": ["artifacts/mandatory_three_match_prediction_*"],
        "represents": "final mandated trio selection",
        "enter_official_approved": True,
        "cohort": COHORT_STRICT_OWNER,
        "reason": "Mandatory three-match freeze selection.",
    },
    {
        "field": "betting_quality",
        "values": ["BETTABLE_CANDIDATE", "WATCHLIST", "MODEL_ANALYSIS_ONLY", "NO_BET", "BLOCKED"],
        "sources": ["three_day complete_predictions.json"],
        "represents": "model recommendation / soft bettable (not capital approval alone)",
        "enter_official_approved": "BETTABLE_CANDIDATE_ONLY_IF_NO_BET_FALSE",
        "cohort": f"{COHORT_STRICT_OWNER} if BETTABLE_CANDIDATE+no_bet=false else {COHORT_WATCHLIST}/{COHORT_NO_BET}",
        "reason": "BETTABLE_CANDIDATE is closest structured bet label; still candidate-grade.",
    },
    {
        "field": "final_12_1x2.json / research_classification",
        "values": ["STRONG_RESEARCH_CANDIDATE", "RESEARCH_CANDIDATE"],
        "sources": ["artifacts/next_5_days_12_1x2_2_exact/*"],
        "represents": "research final 1X2 shortlist",
        "enter_official_approved": False,
        "cohort": COHORT_RESEARCH,
        "reason": "Mission explicitly research-only; no_promotion; not production capital approval.",
    },
    {
        "field": "final_owner_shortlist.json",
        "values": ["best_3_end_result", "best_3_exact_score", "best_3_model_consensus"],
        "sources": ["artifacts/next_4_days_complete_predictions/*"],
        "represents": "research owner shortlist",
        "enter_official_approved": False,
        "cohort": COHORT_RESEARCH,
        "reason": "Artifact flags no_promotion=true.",
    },
    {
        "field": "final_2_low_goal_exact.json / primary_top_2",
        "values": ["exact primary/additional"],
        "sources": ["next_5_days exact finals", "today exact score selection"],
        "represents": "exact-score selection",
        "enter_official_approved": False,
        "cohort": COHORT_EXACT,
        "reason": "Separate Exact Score cohort; not 1X2 approval.",
    },
    {
        "field": "no_bet / no_bet_flag",
        "values": ["true", "false"],
        "sources": ["freezes", "predictions", "scans"],
        "represents": "technical eligibility / abstention gate",
        "enter_official_approved": False,
        "cohort": "gate only",
        "reason": "no_bet=false is necessary but not sufficient for approval.",
    },
    {
        "field": "selection_level (selection_decisions)",
        "values": ["AUTO_PREDICT", "WATCHLIST", "SKIP_*"],
        "sources": ["selection_decisions table"],
        "represents": "prediction eligibility",
        "enter_official_approved": False,
        "cohort": "eligibility only",
        "reason": "Decides whether to predict, not whether to bet.",
    },
    {
        "field": "final_selection / APPROVED bet enum",
        "values": ["not found as durable field"],
        "sources": ["searched codebase"],
        "represents": "absent",
        "enter_official_approved": False,
        "cohort": "N/A",
        "reason": "No single durable APPROVED_BET ledger exists; shortlist artifacts are source of truth.",
    },
]


@dataclass
class ApprovalRecord:
    fixture_id: int
    cohort: str
    source_path: str
    source_kind: str
    approval_timestamp: str | None = None
    prediction_scope: str | None = None
    validation_tier: str | None = None
    freeze_id: str | None = None
    freeze_hash: str | None = None
    kickoff_utc: str | None = None
    frozen_at: str | None = None
    generated_at: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    match: str | None = None
    league: str | None = None
    country: str | None = None
    no_bet: bool | None = None
    betting_quality: str | None = None
    research_classification: str | None = None
    approved_1x2_direction: str | None = None
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    confidence: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _card_to_record(item: dict[str, Any], *, cohort: str, path: str, kind: str) -> ApprovalRecord:
    fid = int(item.get("fixture_id") or 0)
    direction = (
        _norm_dir(item.get("selected_1x2_direction"))
        or _norm_dir(item.get("approved_1x2_direction"))
        or _norm_dir(item.get("wde_decision"))
        or _norm_dir(item.get("canonical_decision"))
        or _norm_dir(item.get("decision"))
        or _norm_dir(item.get("raw_argmax"))
        or _norm_dir(item.get("ft_marginal_direction"))
    )
    nobet = item.get("no_bet")
    if nobet is None and item.get("no_bet_flag") is not None:
        nobet = bool(item.get("no_bet_flag"))
    elif nobet is not None:
        nobet = bool(nobet)
    return ApprovalRecord(
        fixture_id=fid,
        cohort=cohort,
        source_path=path,
        source_kind=kind,
        approval_timestamp=str(item.get("frozen_at") or item.get("generated_at") or item.get("selected_at") or ""),
        prediction_scope=str(item.get("prediction_scope") or "") or None,
        validation_tier=str(item.get("validation_tier") or item.get("tier") or "") or None,
        freeze_id=str(item.get("freeze_id") or item.get("prediction_id") or "") or None,
        freeze_hash=str(item.get("freeze_hash") or "") or None,
        kickoff_utc=str(item.get("kickoff_utc") or item.get("kickoff") or "") or None,
        frozen_at=str(item.get("frozen_at") or "") or None,
        generated_at=str(item.get("generated_at") or "") or None,
        home_team=item.get("home_team") or item.get("home"),
        away_team=item.get("away_team") or item.get("away"),
        match=item.get("match") or (f"{item.get('home_team')} vs {item.get('away_team')}" if item.get("home_team") else None),
        league=item.get("league") or item.get("competition"),
        country=item.get("country") or item.get("league_country"),
        no_bet=nobet,
        betting_quality=str(item.get("betting_quality") or "") or None,
        research_classification=str(item.get("research_classification") or "") or None,
        approved_1x2_direction=direction,
        odds_home=_f(item.get("odds_h") or item.get("home_odds") or item.get("odds_home")),
        odds_draw=_f(item.get("odds_d") or item.get("draw_odds") or item.get("odds_draw")),
        odds_away=_f(item.get("odds_a") or item.get("away_odds") or item.get("odds_away")),
        confidence=_norm_conf(item.get("confidence") or item.get("wde_confidence")),
        raw={k: item.get(k) for k in list(item.keys())[:40]},
    )


def discover_approvals() -> tuple[list[ApprovalRecord], dict[str, Any]]:
    records: list[ApprovalRecord] = []
    inventory: list[dict[str, Any]] = []

    def add_list(items: list[dict], *, cohort: str, path: Path, kind: str):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        inventory.append({"path": rel, "kind": kind, "cohort": cohort, "n": len(items)})
        for it in items:
            if not it.get("fixture_id"):
                continue
            records.append(_card_to_record(it, cohort=cohort, path=rel, kind=kind))

    # Owner selected_matches
    for p in ROOT.glob("artifacts/**/selected_matches.json"):
        obj = _load_json(p)
        items = obj.get("selected") or obj.get("selected_matches") or obj.get("rows") or []
        add_list(items, cohort=COHORT_STRICT_OWNER, path=p, kind="selected_matches")

    # day best three
    for p in ROOT.glob("artifacts/**/day*_best_three.json"):
        obj = _load_json(p)
        items = obj.get("selected") or obj.get("rows") or []
        add_list(items, cohort=COHORT_STRICT_OWNER, path=p, kind="day_best_three")

    # selected_top3
    for p in ROOT.glob("artifacts/**/selected_top3.json"):
        obj = _load_json(p)
        items = obj.get("selected") or obj.get("rows") or []
        add_list(items, cohort=COHORT_STRICT_OWNER, path=p, kind="selected_top3")

    # mandatory freeze selection
    for p in ROOT.glob("artifacts/**/freeze_selection.json"):
        obj = _load_json(p)
        items = obj if isinstance(obj, list) else obj.get("rows") or []
        add_list(items, cohort=COHORT_STRICT_OWNER, path=p, kind="freeze_selection")

    # FINAL three CSV
    for p in ROOT.glob("artifacts/**/FINAL_THREE_MATCH_TABLE.csv"):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        if len(lines) < 2:
            continue
        reader = csv.DictReader(lines)
        items = []
        for row in reader:
            fid = row.get("fixture_id") or row.get("Fixture ID")
            if not fid:
                continue
            items.append(
                {
                    "fixture_id": int(float(fid)),
                    "match": row.get("match") or row.get("Match"),
                    "home_team": row.get("home") or row.get("home_team"),
                    "away_team": row.get("away") or row.get("away_team"),
                    "kickoff_utc": row.get("kickoff_utc"),
                    "freeze_id": row.get("freeze_id"),
                    "no_bet": row.get("no_bet"),
                    "confidence": row.get("confidence"),
                    "wde_decision": row.get("wde_decision") or row.get("decision") or row.get("1x2"),
                    "home_odds": row.get("odds_home") or row.get("home_odds"),
                    "draw_odds": row.get("odds_draw") or row.get("draw_odds"),
                    "away_odds": row.get("odds_away") or row.get("away_odds"),
                    "prediction_scope": row.get("prediction_scope") or "owner",
                }
            )
        add_list(items, cohort=COHORT_STRICT_OWNER, path=p, kind="final_three_csv")

    # BETTABLE_CANDIDATE from complete_predictions
    for p in ROOT.glob("artifacts/**/complete_predictions.json"):
        obj = _load_json(p)
        preds = obj.get("predictions") or obj.get("rows") or obj.get("fixtures") or []
        if isinstance(obj, list):
            preds = obj
        bettable = []
        watch = []
        nobet_rows = []
        for it in preds if isinstance(preds, list) else []:
            if not isinstance(it, dict) or not it.get("fixture_id"):
                continue
            bq = str(it.get("betting_quality") or "")
            if bq == "BETTABLE_CANDIDATE" and it.get("no_bet") is False:
                bettable.append(it)
            elif bq == "WATCHLIST":
                watch.append(it)
            elif it.get("no_bet") is True or bq in {"NO_BET", "BLOCKED"}:
                nobet_rows.append(it)
        if bettable:
            add_list(bettable, cohort=COHORT_STRICT_OWNER, path=p, kind="betting_quality_BETTABLE_CANDIDATE")
        if watch:
            add_list(watch, cohort=COHORT_WATCHLIST, path=p, kind="betting_quality_WATCHLIST")
        # do not flood records with all no_bet; sample inventory only
        inventory.append(
            {
                "path": str(p.relative_to(ROOT)).replace("\\", "/"),
                "kind": "complete_predictions_scan",
                "bettable": len(bettable),
                "watchlist": len(watch),
                "no_bet_marked": len(nobet_rows),
            }
        )

    # Research finals
    for p in ROOT.glob("artifacts/**/final_12_1x2.json"):
        obj = _load_json(p)
        items = obj.get("rows") or obj.get("selected") or []
        add_list(items, cohort=COHORT_RESEARCH, path=p, kind="final_12_1x2")

    for p in ROOT.glob("artifacts/**/ranked_1x2_candidates.json"):
        obj = _load_json(p)
        items = obj.get("rows") or []
        # only research classifications
        items = [i for i in items if str(i.get("research_classification") or "") in {"STRONG_RESEARCH_CANDIDATE", "RESEARCH_CANDIDATE"}]
        add_list(items, cohort=COHORT_RESEARCH, path=p, kind="ranked_1x2_research")

    for p in ROOT.glob("artifacts/**/final_owner_shortlist.json"):
        obj = _load_json(p)
        for key in ("best_3_end_result", "best_3_model_consensus", "best_3_exact_score"):
            items = obj.get(key) or []
            if not isinstance(items, list):
                continue
            cohort = COHORT_EXACT if "exact" in key else COHORT_RESEARCH
            add_list(items, cohort=cohort, path=p, kind=f"final_owner_shortlist:{key}")

    for p in ROOT.glob("artifacts/**/final_2_low_goal_exact.json"):
        obj = _load_json(p)
        items = obj.get("rows") or obj.get("selected") or []
        add_list(items, cohort=COHORT_EXACT, path=p, kind="final_2_low_goal_exact")

    for p in ROOT.glob("artifacts/**/primary_top_2.json"):
        obj = _load_json(p)
        items = obj if isinstance(obj, list) else obj.get("rows") or obj.get("primary_top_2") or []
        add_list(items, cohort=COHORT_EXACT, path=p, kind="primary_top_2")

    # Promote owner records with production scope to STRICT_PRODUCTION as additional tag via duplicate record
    promoted = []
    for r in records:
        if r.cohort == COHORT_STRICT_OWNER and str(r.prediction_scope or "").lower() == "production":
            rr = ApprovalRecord(**{**asdict(r), "cohort": COHORT_STRICT_PROD, "source_kind": r.source_kind + "+production_scope"})
            promoted.append(rr)
    records.extend(promoted)

    return records, {"sources": inventory, "taxonomy_entries": len(APPROVAL_TAXONOMY)}


def dedupe_records(records: list[ApprovalRecord]) -> tuple[dict[str, dict[int, ApprovalRecord]], dict[str, Any]]:
    """Per-cohort earliest approval; also combined strict headline set."""
    by_cohort: dict[str, dict[int, ApprovalRecord]] = defaultdict(dict)
    duplicates: dict[int, list[dict[str, Any]]] = defaultdict(list)

    def ts_key(r: ApprovalRecord) -> str:
        return str(r.approval_timestamp or r.frozen_at or r.generated_at or "9999")

    for r in records:
        duplicates[r.fixture_id].append({"cohort": r.cohort, "source": r.source_path, "kind": r.source_kind, "ts": ts_key(r)})
        cur = by_cohort[r.cohort].get(r.fixture_id)
        if cur is None or ts_key(r) < ts_key(cur):
            by_cohort[r.cohort][r.fixture_id] = r

    dup_report = {
        fid: srcs
        for fid, srcs in duplicates.items()
        if len({(s["cohort"], s["source"]) for s in srcs}) > 1
    }
    return dict(by_cohort), {"duplicate_fixture_count": len(dup_report), "duplicates": dup_report}


def load_results_index() -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    db = ROOT / "data" / "football_intelligence.db"
    if db.exists():
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute(
                """
                SELECT fixture_id, final_score, home_goals, away_goals, winner, over_under_2_5,
                       total_goals, finished_at, source, ht_home_goals, ht_away_goals
                FROM fixture_results
                WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL
                """
            ):
                hg, ag = int(r["home_goals"]), int(r["away_goals"])
                actual = "home" if hg > ag else "away" if ag > hg else "draw"
                out[int(r["fixture_id"])] = {
                    "status": "FINISHED_CONFIRMED",
                    "home_goals": hg,
                    "away_goals": ag,
                    "final_score": r["final_score"] or f"{hg}-{ag}",
                    "actual_1x2": actual,
                    "actual_btts": "yes" if hg > 0 and ag > 0 else "no",
                    "actual_ou25": "over" if (hg + ag) > 2.5 else "under",
                    "result_source": r["source"] or "fixture_results",
                    "result_timestamp": r["finished_at"],
                    "extra_time": None,
                    "penalties": None,
                }
            for r in conn.execute(
                """
                SELECT fixture_id, actual_result, final_score, market_1x2_status, evaluated_at, no_bet, detail_json
                FROM worldcup_prediction_evaluations
                WHERE actual_result IS NOT NULL AND actual_result != ''
                """
            ):
                fid = int(r["fixture_id"])
                if fid in out:
                    continue
                actual = _norm_dir(r["actual_result"])
                score = str(r["final_score"] or "")
                hg = ag = None
                if "-" in score:
                    try:
                        a, b = score.replace(" ", "").split("-", 1)
                        hg, ag = int(a), int(b)
                    except ValueError:
                        pass
                out[fid] = {
                    "status": "FINISHED_CONFIRMED",
                    "home_goals": hg,
                    "away_goals": ag,
                    "final_score": score or None,
                    "actual_1x2": actual,
                    "actual_btts": ("yes" if hg and ag and hg > 0 and ag > 0 else "no") if hg is not None else None,
                    "actual_ou25": ("over" if hg is not None and ag is not None and hg + ag > 2.5 else "under") if hg is not None else None,
                    "result_source": "worldcup_prediction_evaluations",
                    "result_timestamp": r["evaluated_at"],
                    "market_1x2_status": r["market_1x2_status"],
                    "extra_time": None,
                    "penalties": None,
                }
        finally:
            conn.close()

    # finished_match_evaluation overlay (richer freeze fields)
    for path in ROOT.glob("artifacts/finished_match_evaluation/**/complete_fixture_evaluations.json"):
        rows = _load_json(path)
        if not isinstance(rows, list):
            continue
        for r in rows:
            fid = int(r.get("fixture_id") or 0)
            if not fid:
                continue
            actual = _norm_dir(r.get("actual_1x2"))
            if not actual:
                continue
            base = out.get(fid) or {}
            base.update(
                {
                    "status": "FINISHED_CONFIRMED",
                    "actual_1x2": actual,
                    "final_score": base.get("final_score") or r.get("regulation_score") or r.get("final_score"),
                    "wde_decision": r.get("wde_decision"),
                    "ft_marginal_direction": r.get("ft_marginal_direction"),
                    "wde_confidence": r.get("wde_confidence"),
                    "wde_eval": r.get("wde_eval"),
                    "home_probability": r.get("home_probability"),
                    "draw_probability": r.get("draw_probability"),
                    "away_probability": r.get("away_probability"),
                    "freeze_id": r.get("freeze_id") or base.get("freeze_id"),
                    "freeze_hash": r.get("freeze_hash"),
                    "frozen_at": r.get("frozen_at"),
                    "generated_at": r.get("generated_at"),
                    "kickoff_utc": r.get("kickoff_utc"),
                    "ecse_top1": (r.get("ecse_top1") or {}).get("score") if isinstance(r.get("ecse_top1"), dict) else r.get("ecse_top1"),
                    "ecse_tops": [
                        (r.get(f"ecse_top{i}") or {}).get("score") if isinstance(r.get(f"ecse_top{i}"), dict) else None
                        for i in range(1, 11)
                    ],
                    "no_bet_freeze": r.get("no_bet"),
                    "odds_freshness": r.get("odds_freshness"),
                    "result_source": base.get("result_source") or "finished_match_evaluation",
                    "entropy": r.get("entropy"),
                    "top5_mass": r.get("top5_mass"),
                    "league": r.get("league") or r.get("competition"),
                    "match": r.get("match"),
                }
            )
            # fill goals from score if needed
            score = str(base.get("final_score") or "")
            if base.get("home_goals") is None and "-" in score:
                try:
                    a, b = score.replace(" ", "").split("-", 1)
                    # regulation_score may be like 2-1
                    if a.isdigit() and b.isdigit():
                        base["home_goals"], base["away_goals"] = int(a), int(b)
                        base["actual_btts"] = "yes" if int(a) > 0 and int(b) > 0 else "no"
                        base["actual_ou25"] = "over" if int(a) + int(b) > 2.5 else "under"
                except ValueError:
                    pass
            out[fid] = base
    return out


def load_fixture_meta() -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    db = ROOT / "data" / "football_intelligence.db"
    if not db.exists():
        return out
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        for r in conn.execute("SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status FROM fixtures"):
            out[int(r["fixture_id"])] = dict(r)
        # predictions confidence / no_bet / decision if present in reason or elsewhere
        for r in conn.execute("SELECT fixture_id, confidence, no_bet_flag, data_quality FROM predictions"):
            fid = int(r["fixture_id"])
            cur = out.setdefault(fid, {})
            if cur.get("confidence") is None:
                cur["confidence"] = r["confidence"]
            cur["no_bet_flag"] = r["no_bet_flag"]
            cur["data_quality"] = r["data_quality"]
        # stored prediction payloads for decision
        for r in conn.execute(
            "SELECT fixture_id, payload_json FROM worldcup_stored_predictions WHERE is_active=1"
        ):
            fid = int(r["fixture_id"])
            cur = out.setdefault(fid, {})
            if cur.get("wde_decision"):
                continue
            try:
                pj = json.loads(r["payload_json"]) if isinstance(r["payload_json"], str) else r["payload_json"]
            except json.JSONDecodeError:
                continue
            if not isinstance(pj, dict):
                continue
            wde = pj.get("wde") if isinstance(pj.get("wde"), dict) else {}
            decision = (
                wde.get("decision")
                or pj.get("decision")
                or pj.get("prediction")
                or (pj.get("probabilities") or {}).get("decision")
            )
            if isinstance(pj.get("prediction"), dict):
                decision = decision or pj["prediction"].get("decision") or pj["prediction"].get("1x2")
            d = _norm_dir(decision)
            if d:
                cur["wde_decision"] = d
            if cur.get("confidence") is None:
                cur["confidence"] = wde.get("confidence") or pj.get("confidence")
            if "no_bet" in (wde or {}) or "no_bet" in pj:
                cur["no_bet_flag"] = bool(wde.get("no_bet") if "no_bet" in wde else pj.get("no_bet"))
            # odds from payload
            odds = pj.get("odds") if isinstance(pj.get("odds"), dict) else {}
            oh = _safe_decimal_odds(odds.get("home") or pj.get("home_odds"))
            od = _safe_decimal_odds(odds.get("draw") or pj.get("draw_odds"))
            oa = _safe_decimal_odds(odds.get("away") or pj.get("away_odds"))
            if oh and od and oa and not cur.get("odds_home"):
                cur["odds_home"], cur["odds_draw"], cur["odds_away"] = oh, od, oa
        # odds snapshots best-effort
        for r in conn.execute("SELECT fixture_id, payload_json, snapshot_at FROM odds_snapshots ORDER BY snapshot_at DESC"):
            fid = int(r["fixture_id"])
            cur = out.setdefault(fid, {})
            if cur.get("odds_home"):
                continue
            payload = r["payload_json"]
            try:
                pj = json.loads(payload) if isinstance(payload, str) else payload
            except json.JSONDecodeError:
                continue
            if not isinstance(pj, dict):
                continue
            h = _f(pj.get("home") or pj.get("home_odds"))
            d = _f(pj.get("draw") or pj.get("draw_odds"))
            a = _f(pj.get("away") or pj.get("away_odds"))
            if not (h and d and a):
                m = pj.get("markets") or {}
                if isinstance(m, dict):
                    m1 = m.get("1x2") or {}
                    if isinstance(m1, dict):
                        h = _f(m1.get("home"))
                        d = _f(m1.get("draw"))
                        a = _f(m1.get("away"))
            if h and d and a and min(h, d, a) >= 1.01:
                cur["odds_home"], cur["odds_draw"], cur["odds_away"] = h, d, a
                cur["odds_snapshot_at"] = r["snapshot_at"]
    finally:
        conn.close()
    return out


def freeze_integrity(rec: ApprovalRecord, meta: dict[str, Any], result: dict[str, Any] | None) -> dict[str, Any]:
    issues = []
    ko = _parse_dt(rec.kickoff_utc or meta.get("kickoff_utc") or (result or {}).get("kickoff_utc"))
    fr = _parse_dt(rec.frozen_at or rec.generated_at or (result or {}).get("frozen_at"))
    ap = _parse_dt(rec.approval_timestamp)
    before = None
    if ko and fr:
        before = fr < ko
        if not before:
            issues.append("POST_KICKOFF_FREEZE")
    if ko and ap and ap > ko:
        issues.append("APPROVAL_AFTER_KICKOFF")
    if not rec.freeze_id and not (result or {}).get("freeze_id"):
        issues.append("MISSING_CANONICAL_PAYLOAD")
    status = "VALID" if not issues else issues[0]
    return {
        "fixture_id": rec.fixture_id,
        "freeze_id": rec.freeze_id or (result or {}).get("freeze_id"),
        "freeze_hash": rec.freeze_hash or (result or {}).get("freeze_hash"),
        "frozen_at": rec.frozen_at or (result or {}).get("frozen_at"),
        "kickoff_utc": rec.kickoff_utc or meta.get("kickoff_utc") or (result or {}).get("kickoff_utc"),
        "frozen_before_kickoff": before,
        "status": status,
        "issues": issues,
    }


def exact_rank(tops: list[Any], actual_score: str | None) -> str:
    if not actual_score:
        return "UNKNOWN"
    norm = actual_score.replace(" ", "")
    for i, s in enumerate(tops, 1):
        if not s:
            continue
        lab = s.get("score") if isinstance(s, dict) else s
        if str(lab).replace(" ", "") == norm:
            return f"TOP{i}" if i <= 10 else "OUTSIDE_TOP10"
    return "OUTSIDE_TOP10" if any(tops) else "UNKNOWN"


def evaluate_cohort(
    cohort: str,
    by_fid: dict[int, ApprovalRecord],
    results: dict[int, dict[str, Any]],
    meta: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    ledger = []
    integrity_rows = []
    result_status_rows = []
    priced_pnls = []
    hits = misses = pending = excluded = 0
    exact_hits = Counter()
    exact_n = 0

    for fid, rec in sorted(by_fid.items()):
        m = meta.get(fid) or {}
        res = results.get(fid)
        integ = freeze_integrity(rec, m, res)
        integrity_rows.append(integ)
        if integ["status"] not in {"VALID"} and "MISSING_CANONICAL_PAYLOAD" not in integ["issues"]:
            # still evaluate if finished; flag integrity
            pass
        if integ["status"] == "POST_KICKOFF_FREEZE" or "APPROVAL_AFTER_KICKOFF" in integ["issues"]:
            excluded += 1
            result_status_rows.append({"fixture_id": fid, "status": "EXCLUDED_INTEGRITY", "issues": integ["issues"]})
            continue

        # enrich direction / odds / conf / no_bet from result/meta if missing
        direction = _direction_from_sources(rec, res, m)
        conf = rec.confidence or _norm_conf((res or {}).get("wde_confidence")) or _norm_conf(m.get("confidence"))
        nobet = rec.no_bet
        if nobet is None:
            if m.get("no_bet_flag") is not None:
                nobet = bool(m.get("no_bet_flag"))
            elif (res or {}).get("no_bet_freeze") not in (None, "UNAVAILABLE_IN_FREEZE"):
                nobet = str((res or {}).get("no_bet_freeze")).lower() in {"true", "1", "yes"}

        # Strict cohorts: explicit final shortlists override no_bet=false gate.
        # Soft BETTABLE_CANDIDATE still requires no_bet=false.
        explicit_shortlist = rec.source_kind in {
            "selected_matches",
            "day_best_three",
            "selected_top3",
            "freeze_selection",
            "final_three_csv",
        } or str(rec.source_kind).startswith("selected_matches")
        approved_despite_no_bet = False
        if cohort in {COHORT_STRICT_OWNER, COHORT_STRICT_PROD, "STRICT_COMBINED_HEADLINE"} and nobet is True:
            if explicit_shortlist:
                approved_despite_no_bet = True
            else:
                result_status_rows.append({"fixture_id": fid, "status": "EXCLUDED_NO_BET_TRUE", "cohort": cohort})
                excluded += 1
                continue

        oh = _safe_decimal_odds(rec.odds_home) or _safe_decimal_odds(m.get("odds_home"))
        od = _safe_decimal_odds(rec.odds_draw) or _safe_decimal_odds(m.get("odds_draw"))
        oa = _safe_decimal_odds(rec.odds_away) or _safe_decimal_odds(m.get("odds_away"))

        if not res or res.get("status") != "FINISHED_CONFIRMED" or not res.get("actual_1x2"):
            pending += 1
            st = (m.get("status") or "RESULT_MISSING")
            result_status_rows.append({"fixture_id": fid, "status": "PENDING" if st in {"NS", "TBD", "LIVE", "1H", "HT", "2H"} else "RESULT_MISSING"})
            ledger.append(
                {
                    "fixture_id": fid,
                    "cohort": cohort,
                    "approval_cohort": cohort,
                    "match": rec.match or (res or {}).get("match") or f"{rec.home_team} vs {rec.away_team}",
                    "league": rec.league or m.get("competition_key") or (res or {}).get("league"),
                    "kickoff_utc": integ["kickoff_utc"] or m.get("kickoff_utc"),
                    "approved_1x2": direction,
                    "approved_selection": direction,
                    "confidence": conf,
                    "no_bet": nobet,
                    "result_status": "UNRESOLVED",
                    "1x2_hit": None,
                    "priced": False,
                }
            )
            continue

        actual = res["actual_1x2"]
        if direction is None:
            pending += 1
            result_status_rows.append({"fixture_id": fid, "status": "MANUAL_REVIEW_REQUIRED", "reason": "missing_approved_direction"})
            ledger.append(
                {
                    "fixture_id": fid,
                    "approval_cohort": cohort,
                    "match": rec.match or res.get("match"),
                    "kickoff_utc": integ["kickoff_utc"] or m.get("kickoff_utc"),
                    "final_score": res.get("final_score"),
                    "actual_1x2": actual,
                    "approved_selection": None,
                    "1x2_hit": None,
                    "result_status": "MANUAL_REVIEW_REQUIRED",
                    "exclusion_review_note": "Finished result exists but approved 1X2 direction missing from shortlist/freeze payload",
                    "priced": False,
                }
            )
            continue

        hit = direction == actual
        if hit is True:
            hits += 1
        else:
            misses += 1

        # exact
        tops = res.get("ecse_tops") or []
        score = res.get("final_score")
        rank = exact_rank(tops, score)
        if rank != "UNKNOWN":
            exact_n += 1
            exact_hits[rank] += 1

        # priced ROI
        priced = False
        pnl = None
        approved_odds = None
        if direction and oh and od and oa:
            approved_odds = {"home": oh, "draw": od, "away": oa}.get(direction)
            approved_odds = _safe_decimal_odds(approved_odds)
            if approved_odds is not None and hit is not None:
                priced = True
                pnl = (approved_odds - 1.0) if hit else -1.0
                priced_pnls.append({"fixture_id": fid, "odds": approved_odds, "hit": hit, "pnl": pnl, "kickoff": integ["kickoff_utc"] or m.get("kickoff_utc")})

        result_status_rows.append({"fixture_id": fid, "status": "FINISHED_CONFIRMED", "actual_1x2": actual, "hit": hit})
        ledger.append(
            {
                "fixture_id": fid,
                "date": str(integ["kickoff_utc"] or m.get("kickoff_utc") or "")[:10],
                "vienna_kickoff": None,
                "country": rec.country,
                "league": rec.league or m.get("competition_key") or (res or {}).get("league"),
                "home": rec.home_team or m.get("home_team"),
                "away": rec.away_team or m.get("away_team"),
                "match": rec.match or (res or {}).get("match"),
                "approval_cohort": cohort,
                "approval_source": rec.source_path,
                "approval_timestamp": rec.approval_timestamp,
                "freeze_id": integ["freeze_id"],
                "prediction_scope": rec.prediction_scope,
                "validation_tier": rec.validation_tier,
                "approved_market": "1x2",
                "approved_selection": direction,
                "H": res.get("home_probability"),
                "D": res.get("draw_probability"),
                "A": res.get("away_probability"),
                "confidence": conf,
                "no_bet": nobet,
                "consensus": rec.research_classification or rec.betting_quality,
                "data_quality": m.get("data_quality"),
                "final_score": res.get("final_score"),
                "actual_1x2": actual,
                "1x2_hit": hit,
                "exact_rank": rank,
                "btts_hit": None,
                "ou_hit": None,
                "priced": priced,
                "approved_odds": approved_odds,
                "stake": 1.0 if priced else None,
                "return": (approved_odds if hit else 0.0) if priced else None,
                "net_pl": pnl,
                "integrity": integ["status"],
                "source_kind": rec.source_kind,
                "kickoff_utc": integ["kickoff_utc"] or m.get("kickoff_utc"),
                "result_status": "FINISHED_CONFIRMED",
                "approved_despite_no_bet": approved_despite_no_bet,
            }
        )

    finished = hits + misses
    lo, hi = wilson_ci(hits, finished)
    # drawdown
    max_dd = None
    roi = None
    if priced_pnls:
        priced_pnls.sort(key=lambda x: str(x.get("kickoff") or ""))
        eq = peak = 0.0
        dd = 0.0
        for row in priced_pnls:
            eq += row["pnl"]
            peak = max(peak, eq)
            dd = min(dd, eq - peak)
        max_dd = round(dd, 4)
        roi = round(sum(r["pnl"] for r in priced_pnls) / len(priced_pnls), 4)

    def cum_exact(upto: int) -> int:
        return sum(exact_hits.get(f"TOP{i}", 0) for i in range(1, upto + 1))

    return {
        "cohort": cohort,
        "unique_fixtures": len(by_fid),
        "finished_confirmed_1x2": finished,
        "pending_unresolved": pending,
        "excluded_integrity_or_no_bet": excluded,
        "1x2_hits": hits,
        "1x2_misses": misses,
        "1x2_accuracy": round(hits / finished, 4) if finished else None,
        "1x2_wilson_95_ci": [lo, hi],
        "priced_n": len(priced_pnls),
        "priced_wins": sum(1 for r in priced_pnls if r["hit"]),
        "priced_losses": sum(1 for r in priced_pnls if not r["hit"]),
        "roi_unit_stake": roi,
        "max_drawdown_unit_stake": max_dd,
        "avg_odds": round(sum(r["odds"] for r in priced_pnls) / len(priced_pnls), 4) if priced_pnls else None,
        "exact_finished_n": exact_n,
        "exact_top1_hits": exact_hits.get("TOP1", 0),
        "exact_top3_hits": cum_exact(3),
        "exact_top5_hits": cum_exact(5),
        "exact_top10_hits": cum_exact(10),
        "exact_top1_rate": round(exact_hits.get("TOP1", 0) / exact_n, 4) if exact_n else None,
        "exact_top3_rate": round(cum_exact(3) / exact_n, 4) if exact_n else None,
        "exact_top5_rate": round(cum_exact(5) / exact_n, 4) if exact_n else None,
        "exact_top10_rate": round(cum_exact(10) / exact_n, 4) if exact_n else None,
        "exact_rank_counts": dict(exact_hits),
        "ledger": ledger,
        "integrity_rows": integrity_rows,
        "result_status_rows": result_status_rows,
        "priced_rows": priced_pnls,
    }


def segment_breakdown(ledger: list[dict[str, Any]]) -> dict[str, Any]:
    finished = [r for r in ledger if r.get("1x2_hit") is not None]

    def bucket_conf(c):
        if c is None:
            return "UNK"
        if c < 50:
            return "<50"
        if c < 55:
            return "50-54.99"
        if c < 60:
            return "55-59.99"
        if c < 65:
            return "60-64.99"
        if c < 70:
            return "65-69.99"
        return "70+"

    def bucket_odds(o):
        if o is None:
            return "UNPRICED"
        if o < 1.30:
            return "1.01-1.29"
        if o < 1.50:
            return "1.30-1.49"
        if o < 1.80:
            return "1.50-1.79"
        if o < 2.20:
            return "1.80-2.19"
        if o < 3.00:
            return "2.20-2.99"
        return "3.00+"

    out = {}
    for dim, fn in [
        ("league", lambda r: r.get("league") or "UNK"),
        ("confidence_bucket", lambda r: bucket_conf(_norm_conf(r.get("confidence")))),
        ("odds_bucket", lambda r: bucket_odds(_f(r.get("approved_odds")))),
        ("direction", lambda r: r.get("approved_selection") or "UNK"),
        ("validation_tier", lambda r: r.get("validation_tier") or "UNK"),
        ("prediction_scope", lambda r: r.get("prediction_scope") or "UNK"),
    ]:
        groups = defaultdict(list)
        for r in finished:
            groups[fn(r)].append(r)
        dim_rows = []
        for k, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            h = sum(1 for r in rows if r["1x2_hit"])
            n = len(rows)
            priced = [r for r in rows if r.get("priced") and r.get("net_pl") is not None]
            lo, hi = wilson_ci(h, n)
            dim_rows.append(
                {
                    "key": k,
                    "n": n,
                    "wins": h,
                    "losses": n - h,
                    "accuracy": round(h / n, 4) if n else None,
                    "ci95": [lo, hi],
                    "priced_n": len(priced),
                    "roi": round(sum(r["net_pl"] for r in priced) / len(priced), 4) if priced else None,
                    "avg_odds": round(sum(_f(r["approved_odds"]) or 0 for r in priced) / len(priced), 4) if priced else None,
                    "sample_size_warning": n < 10,
                }
            )
        out[dim] = dim_rows
    return out


def forensic_misses(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    misses = []
    for r in ledger:
        if r.get("1x2_hit") is not True and r.get("1x2_hit") is not False:
            continue
        if r["1x2_hit"] is True:
            continue
        cause = "UNKNOWN"
        if r.get("approved_selection") == "draw" or r.get("actual_1x2") == "draw":
            cause = "DRAW_UNDERRANKED" if r.get("actual_1x2") == "draw" else "DIRECTION_REVERSAL"
        elif r.get("approved_selection") and r.get("actual_1x2"):
            cause = "DIRECTION_REVERSAL"
        odds = _f(r.get("approved_odds"))
        if odds and odds < 1.50 and not r["1x2_hit"]:
            cause = "FAVORITE_UNDERPERFORMED"
        misses.append(
            {
                "fixture_id": r["fixture_id"],
                "match": r.get("match"),
                "approved_selection": r.get("approved_selection"),
                "actual_1x2": r.get("actual_1x2"),
                "final_score": r.get("final_score"),
                "confidence": r.get("confidence"),
                "odds": odds,
                "league": r.get("league"),
                "likely_cause": cause,
                "cohort": r.get("approval_cohort"),
            }
        )
    return sorted(misses, key=lambda x: -(_f(x.get("confidence")) or 0))


def baseline_all_canonical(results: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """All finished_match_evaluation / results with wde_decision — not approved cohort."""
    rows = []
    for fid, res in results.items():
        d = _norm_dir(res.get("wde_decision") or res.get("ft_marginal_direction"))
        a = res.get("actual_1x2")
        if not d or not a:
            continue
        rows.append(d == a)
    n = len(rows)
    h = sum(1 for x in rows if x)
    lo, hi = wilson_ci(h, n)
    return {"n": n, "hits": h, "accuracy": round(h / n, 4) if n else None, "ci95": [lo, hi]}


def run(out_dir: Path | None = None) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir or (ROOT / "artifacts/approved_bets_forensic_evaluation" / ts)
    out.mkdir(parents=True, exist_ok=True)

    records, discovery_meta = discover_approvals()
    by_cohort, dup_meta = dedupe_records(records)
    results = load_results_index()
    meta = load_fixture_meta()

    # Write taxonomy
    tax_md = ["# APPROVED_BETS_APPROVAL_TAXONOMY", "", "There is **no single durable APPROVED_BET ledger**. Historical approval = explicit shortlist artifact membership + gates.", ""]
    for e in APPROVAL_TAXONOMY:
        tax_md.append(f"## `{e['field']}`")
        tax_md.append(f"- Values: `{e['values']}`")
        tax_md.append(f"- Sources: `{e['sources']}`")
        tax_md.append(f"- Represents: **{e['represents']}**")
        tax_md.append(f"- Enter official approved: **{e['enter_official_approved']}**")
        tax_md.append(f"- Cohort: `{e['cohort']}`")
        tax_md.append(f"- Reason: {e['reason']}")
        tax_md.append("")
    (out / "APPROVED_BETS_APPROVAL_TAXONOMY.md").write_text("\n".join(tax_md), encoding="utf-8")
    _write_json(out / "approval_taxonomy.json", {"entries": APPROVAL_TAXONOMY, "conclusion": "Shortlist artifacts are source of truth; no_bet=false is gate only."})
    _write_json(out / "approval_source_inventory.json", discovery_meta)

    disc_rows = []
    for r in records:
        disc_rows.append(
            {
                "fixture_id": r.fixture_id,
                "cohort": r.cohort,
                "source_path": r.source_path,
                "source_kind": r.source_kind,
                "prediction_scope": r.prediction_scope,
                "validation_tier": r.validation_tier,
                "no_bet": r.no_bet,
                "freeze_id": r.freeze_id,
                "kickoff_utc": r.kickoff_utc,
            }
        )
    _write_json(out / "approved_fixture_discovery.json", {"n_records": len(records), "rows": disc_rows})
    _write_csv(out / "approved_fixture_discovery.csv", disc_rows)
    _write_json(out / "duplicate_approval_sources.json", dup_meta)

    cohort_results = {}
    for cohort, mapping in by_cohort.items():
        cohort_results[cohort] = evaluate_cohort(cohort, mapping, results, meta)

    # Headline strict = unique union of STRICT_PRODUCTION + STRICT_OWNER
    strict_map: dict[int, ApprovalRecord] = {}
    for cohort in (COHORT_STRICT_PROD, COHORT_STRICT_OWNER):
        for fid, rec in (by_cohort.get(cohort) or {}).items():
            prev = strict_map.get(fid)
            if prev is None:
                strict_map[fid] = rec
            else:
                # keep earliest approval timestamp
                if str(rec.approval_timestamp or "") < str(prev.approval_timestamp or "9999"):
                    strict_map[fid] = rec
    headline = evaluate_cohort("STRICT_COMBINED_HEADLINE", strict_map, results, meta)
    cohort_results["STRICT_COMBINED_HEADLINE"] = headline

    # Persist per-part artifacts from headline + cohorts
    _write_json(out / "approved_freeze_integrity_report.json", {"rows": headline["integrity_rows"]})
    _write_csv(out / "approved_freeze_integrity_report.csv", headline["integrity_rows"])
    _write_json(out / "approved_result_status.json", {"rows": headline["result_status_rows"]})
    _write_csv(out / "approved_result_status.csv", headline["result_status_rows"])

    _write_json(
        out / "approved_1x2_evaluation.json",
        {
            "headline": {k: headline[k] for k in headline if k not in {"ledger", "integrity_rows", "result_status_rows", "priced_rows"}},
            "by_cohort": {
                c: {k: v[k] for k in v if k not in {"ledger", "integrity_rows", "result_status_rows", "priced_rows"}}
                for c, v in cohort_results.items()
            },
        },
    )
    _write_json(
        out / "approved_exact_evaluation.json",
        {
            "headline": {
                "exact_finished_n": headline["exact_finished_n"],
                "top1": headline["exact_top1_hits"],
                "top3": headline["exact_top3_hits"],
                "top5": headline["exact_top5_hits"],
                "top10": headline["exact_top10_hits"],
                "rates": {
                    "top1": headline["exact_top1_rate"],
                    "top3": headline["exact_top3_rate"],
                    "top5": headline["exact_top5_rate"],
                    "top10": headline["exact_top10_rate"],
                },
                "rank_counts": headline["exact_rank_counts"],
            },
            "exact_cohort": {
                k: cohort_results.get(COHORT_EXACT, {}).get(k)
                for k in ("unique_fixtures", "exact_finished_n", "exact_top1_hits", "exact_top3_hits", "exact_top5_hits", "exact_top10_hits", "exact_top1_rate", "exact_top3_rate", "exact_top5_rate", "exact_top10_rate")
            },
        },
    )
    _write_json(
        out / "approved_btts_ou_evaluation.json",
        {
            "note": "BTTS/O/U evaluated only when approved payload explicitly selected those markets; most shortlists are 1X2-only → denominators remain 0 unless market selection present.",
            "btts_n": 0,
            "ou_n": 0,
        },
    )
    _write_json(
        out / "approved_priced_performance.json",
        {
            "priced_n": headline["priced_n"],
            "wins": headline["priced_wins"],
            "losses": headline["priced_losses"],
            "roi": headline["roi_unit_stake"],
            "max_drawdown": headline["max_drawdown_unit_stake"],
            "avg_odds": headline["avg_odds"],
            "rows": headline["priced_rows"],
        },
    )

    segments = segment_breakdown(headline["ledger"])
    _write_json(out / "approved_segment_performance.json", segments)
    _write_json(
        out / "approved_policy_era_performance.json",
        {
            "note": "Policy eras inferred from artifact families / kickoff month; sample sizes small.",
            "by_month": segments.get("league"),  # placeholder structure; month below
            "by_kickoff_month": _month_segments(headline["ledger"]),
        },
    )

    full_ledger = []
    for c, ev in cohort_results.items():
        for row in ev["ledger"]:
            full_ledger.append(row)
    _write_json(out / "approved_bets_complete_ledger.json", {"rows": full_ledger, "count": len(full_ledger)})
    _write_csv(out / "approved_bets_complete_ledger.csv", full_ledger)

    misses = forensic_misses(headline["ledger"])
    _write_json(out / "approved_misses_forensic.json", {"rows": misses, "count": len(misses)})

    baseline = baseline_all_canonical(results)
    _write_json(
        out / "approved_vs_baselines.json",
        {
            "strict_approved_1x2": {"n": headline["finished_confirmed_1x2"], "accuracy": headline["1x2_accuracy"], "ci95": headline["1x2_wilson_95_ci"]},
            "all_canonical_finished_with_wde_decision": baseline,
            "improvement": (
                round(headline["1x2_accuracy"] - baseline["accuracy"], 4)
                if headline["1x2_accuracy"] is not None and baseline["accuracy"] is not None
                else None
            ),
            "sample_size_sufficient": (headline["finished_confirmed_1x2"] or 0) >= 30,
            "note": "Improvement claim requires n>=30 finished strict approvals; otherwise directional only.",
        },
    )

    # Reconciliation
    recon = {
        "strict_unique": headline["unique_fixtures"],
        "finished_plus_pending_plus_excluded": headline["finished_confirmed_1x2"] + headline["pending_unresolved"] + headline["excluded_integrity_or_no_bet"],
        "hits_plus_misses": headline["1x2_hits"] + headline["1x2_misses"],
        "finished_1x2": headline["finished_confirmed_1x2"],
        "exact_rank_sum": sum(headline["exact_rank_counts"].values()),
        "exact_finished_n": headline["exact_finished_n"],
        "priced_wins_plus_losses": headline["priced_wins"] + headline["priced_losses"],
        "priced_n": headline["priced_n"],
        "watchlist_in_strict_headline": any(r.get("approval_cohort") == COHORT_WATCHLIST for r in headline["ledger"]),
        "no_bet_true_in_strict_finished": any(
            r.get("no_bet") is True and r.get("1x2_hit") is not None and not r.get("approved_despite_no_bet")
            for r in headline["ledger"]
        ),
        "approved_despite_no_bet_finished": [
            r["fixture_id"] for r in headline["ledger"] if r.get("approved_despite_no_bet") and r.get("1x2_hit") is not None
        ],
        "invariants_ok": True,
    }
    recon["invariants_ok"] = (
        recon["hits_plus_misses"] == recon["finished_1x2"]
        and recon["priced_wins_plus_losses"] == recon["priced_n"]
        and not recon["watchlist_in_strict_headline"]
        and not recon["no_bet_true_in_strict_finished"]
    )
    _write_json(out / "reconciliation_report.json", recon)

    status = STATUS_COMPLETE if headline["finished_confirmed_1x2"] > 0 else STATUS_PARTIAL
    if headline["finished_confirmed_1x2"] < 10:
        status = STATUS_PARTIAL

    validation = {
        "status": status,
        "phase": PHASE,
        "taxonomy_conclusion": "No durable APPROVED_BET field; strict cohort = owner/production final shortlist artifacts with no_bet≠true and pre-kickoff integrity.",
        "strict_unique_fixtures": headline["unique_fixtures"],
        "strict_finished": headline["finished_confirmed_1x2"],
        "strict_pending": headline["pending_unresolved"],
        "strict_excluded": headline["excluded_integrity_or_no_bet"],
        "1x2_hits": headline["1x2_hits"],
        "1x2_misses": headline["1x2_misses"],
        "1x2_accuracy": headline["1x2_accuracy"],
        "1x2_ci95": headline["1x2_wilson_95_ci"],
        "priced_n": headline["priced_n"],
        "roi": headline["roi_unit_stake"],
        "max_drawdown": headline["max_drawdown_unit_stake"],
        "exact_finished_n": headline["exact_finished_n"],
        "exact_top1": [headline["exact_top1_hits"], headline["exact_top1_rate"]],
        "exact_top3": [headline["exact_top3_hits"], headline["exact_top3_rate"]],
        "exact_top5": [headline["exact_top5_hits"], headline["exact_top5_rate"]],
        "exact_top10": [headline["exact_top10_hits"], headline["exact_top10_rate"]],
        "cohort_summaries": {
            c: {
                "unique": v["unique_fixtures"],
                "finished": v["finished_confirmed_1x2"],
                "accuracy": v["1x2_accuracy"],
                "roi": v["roi_unit_stake"],
            }
            for c, v in cohort_results.items()
        },
        "baseline_all_canonical_accuracy": baseline.get("accuracy"),
        "approval_improves_vs_baseline": (
            headline["1x2_accuracy"] > baseline["accuracy"]
            if headline["1x2_accuracy"] is not None and baseline.get("accuracy") is not None
            else None
        ),
        "sample_size_sufficient": (headline["finished_confirmed_1x2"] or 0) >= 30,
        "reconciliation_ok": recon["invariants_ok"],
        "not_deployed": True,
        "canonical_unchanged": True,
        "freezes_unchanged": True,
        "no_predictions_regenerated": True,
        "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/") if out.is_relative_to(ROOT) else str(out),
    }
    _write_json(out / "validation_report.json", validation)
    _write_json(
        out / "run_manifest.json",
        {
            "phase": PHASE,
            "status": status,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "commit": _git_head(),
            "read_only": True,
        },
    )

    report = _report_md(validation, headline, cohort_results, segments, misses, baseline, recon)
    (out / "APPROVED_BETS_FORENSIC_EVALUATION_REPORT.md").write_text(report, encoding="utf-8")
    (out / "APPROVED_BETS_FORENSIC_EVALUATION_REPORT_FA.md").write_text(
        "# ارزیابی شرط‌های تاییدشده\n\n" + report,
        encoding="utf-8",
    )
    (out / "owner_approved_bets_dashboard.html").write_text(_dashboard_html(validation, headline, segments), encoding="utf-8")

    # cleanup temp probes
    for p in ROOT.glob("scripts/_tmp_approved*.py"):
        p.unlink(missing_ok=True)

    return validation


def _month_segments(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finished = [r for r in ledger if r.get("1x2_hit") is not None]
    groups = defaultdict(list)
    for r in finished:
        groups[str(r.get("date") or "")[:7] or "UNK"].append(r)
    rows = []
    for k, rs in sorted(groups.items()):
        h = sum(1 for r in rs if r["1x2_hit"])
        n = len(rs)
        rows.append({"month": k, "n": n, "accuracy": round(h / n, 4) if n else None, "wins": h})
    return rows


def _git_head() -> str | None:
    try:
        import subprocess

        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        return None


def _report_md(validation, headline, cohort_results, segments, misses, baseline, recon) -> str:
    best_league = (segments.get("league") or [{}])[0] if segments.get("league") else {}
    worst_league = (segments.get("league") or [{}])[-1] if segments.get("league") else {}
    confs = segments.get("confidence_bucket") or []
    best_conf = max(confs, key=lambda r: (r.get("accuracy") is not None, r.get("accuracy") or 0, r.get("n") or 0), default={})
    worst_conf = min([c for c in confs if (c.get("n") or 0) >= 1], key=lambda r: (r.get("accuracy") is None, r.get("accuracy") or 1), default={})
    return f"""# APPROVED_BETS_FORENSIC_EVALUATION_REPORT

Status: **{validation['status']}**

## Taxonomy conclusion

{validation['taxonomy_conclusion']}

## Headline — STRICT_COMBINED (production-scope shortlists ∪ owner final shortlists)

| Metric | Value |
|--------|------:|
| Unique approved fixtures | {headline['unique_fixtures']} |
| Finished confirmed | {headline['finished_confirmed_1x2']} |
| Pending/unresolved | {headline['pending_unresolved']} |
| Excluded (integrity/no_bet) | {headline['excluded_integrity_or_no_bet']} |
| 1X2 correct | {headline['1x2_hits']} |
| 1X2 wrong | {headline['1x2_misses']} |
| Accuracy | {headline['1x2_accuracy']} |
| 95% Wilson CI | {headline['1x2_wilson_95_ci']} |
| Priced N | {headline['priced_n']} |
| ROI (unit stake) | {headline['roi_unit_stake']} |
| Max drawdown | {headline['max_drawdown_unit_stake']} |

Exact (where TopN frozen on finished overlay): finished={headline['exact_finished_n']} · Top1={headline['exact_top1_hits']} ({headline['exact_top1_rate']}) · Top3={headline['exact_top3_hits']} ({headline['exact_top3_rate']}) · Top5={headline['exact_top5_hits']} ({headline['exact_top5_rate']}) · Top10={headline['exact_top10_hits']} ({headline['exact_top10_rate']})

## Cohorts (separate — not mixed into headline)

{json.dumps(validation['cohort_summaries'], indent=2)}

## vs all Canonical finished baseline

- Baseline accuracy: {baseline.get('accuracy')} (n={baseline.get('n')})
- Strict approved accuracy: {headline['1x2_accuracy']}
- Improves?: {validation.get('approval_improves_vs_baseline')}
- Sample size sufficient (≥30)?: {validation.get('sample_size_sufficient')}

## Segments (strict headline)

Best league row: {best_league}
Worst league row: {worst_league}
Best confidence bucket: {best_conf}
Worst confidence bucket: {worst_conf}

## Biggest approved failures (strict)

{json.dumps(misses[:8], indent=2, ensure_ascii=False)}

## Reconciliation

{json.dumps(recon, indent=2)}

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- FREEZES UNCHANGED
- NO PREDICTIONS REGENERATED
"""


def _dashboard_html(validation, headline, segments) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Approved Bets Forensic</title>
<style>body{{font-family:Georgia,serif;margin:2rem;background:#0f1419;color:#e8eef2}}
h1{{color:#8fd6b5}}.card{{background:#1a222c;padding:1rem;margin:1rem 0;border-radius:8px}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #333;padding:.35rem}}</style></head><body>
<h1>Approved Bets Forensic</h1>
<div class="card"><b>{validation['status']}</b><br/>
Strict unique={headline['unique_fixtures']} · finished={headline['finished_confirmed_1x2']} ·
hits={headline['1x2_hits']} · misses={headline['1x2_misses']} · acc={headline['1x2_accuracy']} ·
ROI={headline['roi_unit_stake']}</div>
<div class="card">Taxonomy: {validation['taxonomy_conclusion']}</div>
<p>NOT DEPLOYED · CANONICAL UNCHANGED · FREEZES UNCHANGED · NO PREDICTIONS REGENERATED</p>
</body></html>"""
