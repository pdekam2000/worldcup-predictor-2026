"""PHASE OA-1 — OddAlerts provider trial audit (research only)."""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts"
RAW_DIR = ARTIFACTS / "oddalerts_raw"

TARGET_LEAGUES: dict[str, int] = {
    "world_cup": 1690,
    "champions_league": 51,
    "europa_league": 32,
    "premier_league": 423,
    "bundesliga": 477,
    "la_liga": 419,
    "serie_a": 499,
}

FOCUS_BOOKS = {
    "pinnacle": 1,
    "bet365": 2,
    "1xbet": 3,
    "williamhill": 4,
    "betfair": 5,
    "kambi": 6,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _implied(decimal: float | None) -> float | None:
    if decimal is None or decimal <= 1.0:
        return None
    return round(1.0 / float(decimal), 4)


def _pick_side(home_p: float | None, away_p: float | None, *, tie_band: float = 0.02) -> str | None:
    if home_p is None or away_p is None:
        return None
    if abs(home_p - away_p) < tie_band:
        return "none"
    return "home" if home_p > away_p else "away"


def _save_raw(name: str, payload: Any) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(path.relative_to(ROOT)).replace("\\", "/")


def run_connectivity_test(client: OddAlertsClient) -> dict[str, Any]:
    sample_fixture_id = 420562849
    tests: dict[str, Any] = {"generated_at": _now(), "endpoints": {}}

    def _run(name: str, result: Any, *, save_name: str | None = None) -> None:
        ok = result.ok if hasattr(result, "ok") else result is not None
        err = getattr(result, "error", None)
        data = getattr(result, "data", result)
        entry: dict[str, Any] = {
            "ok": ok,
            "error": err,
            "sample_type": type(data).__name__,
        }
        if isinstance(data, dict):
            entry["keys"] = list(data.keys())[:12]
            entry["info"] = data.get("info")
            rows = data.get("data")
            if isinstance(rows, list):
                entry["row_count"] = len(rows)
        if save_name and data is not None:
            entry["raw_path"] = _save_raw(save_name, data)
        tests["endpoints"][name] = entry

    _run("bookmakers", client.get_bookmakers(), save_name="connectivity_bookmakers")
    _run("competitions", client.get_competitions(page=1, per_page=5), save_name="connectivity_competitions")
    _run("fixtures_list", client._get("fixtures", params={"duration": 86400}), save_name="connectivity_fixtures_list")
    _run("fixture_details", client.get_fixture(sample_fixture_id, include="odds,probability,stats"), save_name="connectivity_fixture_details")
    _run("fixtures_multiple", client.get_fixtures_multiple([sample_fixture_id]), save_name="connectivity_fixtures_multiple")
    _run("odds_history", client.get_odds_history(sample_fixture_id), save_name="connectivity_odds_history")
    _run("odds_latest", client.get_odds_latest(since_minutes=60), save_name="connectivity_odds_latest")
    _run("probability", client.get_probability_fixture(sample_fixture_id), save_name="connectivity_probability")
    _run("predictions", client.get_predictions_fixture(sample_fixture_id), save_name="connectivity_predictions")
    _run("stats_fixture", client.get_stats(stat_type="fixture", entity_id=sample_fixture_id), save_name="connectivity_stats_fixture")
    _run("value_upcoming", client.get_value_upcoming(page=1, per_page=5), save_name="connectivity_value_upcoming")
    _run("trends_homeWin", client.get_trends("homeWin", duration=86400), save_name="connectivity_trends")

    tests["configured"] = client.is_configured
    tests["pass_count"] = sum(1 for e in tests["endpoints"].values() if e.get("ok"))
    tests["fail_count"] = sum(1 for e in tests["endpoints"].values() if not e.get("ok"))
    return tests


def _collect_fixture_ids(client: OddAlertsClient, *, max_pages: int = 8) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for page in range(1, max_pages + 1):
        res = client.get_value_upcoming(page=page, per_page=500)
        if not res.ok or not isinstance(res.data, dict):
            break
        rows = res.data.get("data") or []
        if not rows:
            break
        for row in rows:
            fid = int(row.get("id") or 0)
            if fid and fid not in seen:
                seen.add(fid)
                ids.append(fid)
        info = res.data.get("info") or {}
        if not info.get("has_more"):
            break
        client.throttle()
    for trend in ("homeWin", "btts", "over25"):
        res = client.get_trends(trend, duration=432000, page=1)
        if res.ok and isinstance(res.data, dict):
            for row in res.data.get("data") or []:
                fid = int(row.get("id") or 0)
                if fid and fid not in seen:
                    seen.add(fid)
                    ids.append(fid)
        client.throttle()
    return ids


def run_league_coverage_audit(client: OddAlertsClient) -> dict[str, Any]:
    fixture_ids = _collect_fixture_ids(client)
    by_league: dict[str, dict[str, Any]] = {
        key: {
            "competition_id": cid,
            "fixtures_seen": 0,
            "sample_fixture_ids": [],
            "odds": 0,
            "opening_odds": 0,
            "closing_odds": 0,
            "peak_odds": 0,
            "probability": 0,
            "predictions": 0,
            "stats": 0,
            "list_endpoint_blocked": True,
        }
        for key, cid in TARGET_LEAGUES.items()
    }

    for fid in fixture_ids:
        res = client.get_fixture(fid, include="odds,probability,stats")
        client.throttle(0.1)
        if not res.ok or not isinstance(res.data, dict):
            continue
        fx = (res.data.get("data") or [None])[0]
        if not fx:
            continue
        comp_id = int(fx.get("competition_id") or 0)
        league_key = next((k for k, v in TARGET_LEAGUES.items() if v == comp_id), None)
        if not league_key:
            continue
        row = by_league[league_key]
        row["fixtures_seen"] += 1
        if len(row["sample_fixture_ids"]) < 5:
            row["sample_fixture_ids"].append(fid)
        if fx.get("odds"):
            row["odds"] += 1
        if fx.get("probability"):
            row["probability"] += 1
        if fx.get("stats"):
            row["stats"] += 1
        hist = client.get_odds_history(fid)
        client.throttle(0.1)
        if hist.ok and isinstance(hist.data, dict) and hist.data.get("data"):
            row["opening_odds"] += 1
            row["closing_odds"] += 1
            row["peak_odds"] += 1

    # list endpoint probe per league
    now = int(datetime.now(timezone.utc).timestamp())
    month_ago = now - 30 * 86400
    for key, cid in TARGET_LEAGUES.items():
        res = client._get("fixtures", params={"competition_id": cid, "from": month_ago, "to": now})
        by_league[key]["list_endpoint_status"] = "blocked_redirect" if not res.ok else "ok"
        client.throttle(0.1)

    return {
        "generated_at": _now(),
        "fixture_pool_size": len(fixture_ids),
        "leagues": by_league,
        "note": "Coverage from value/trends pool + per-fixture includes; bulk /fixtures list redirects on this token",
    }


def run_bookmaker_audit(client: OddAlertsClient, sample_fixture_id: int = 420562849) -> dict[str, Any]:
    books_res = client.get_bookmakers()
    books = []
    if books_res.ok and isinstance(books_res.data, dict):
        books = books_res.data.get("data") or []

    hist_res = client.get_odds_history(sample_fixture_id)
    hist_rows = hist_res.data.get("data") if hist_res.ok and isinstance(hist_res.data, dict) else []

    per_book: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"markets": Counter(), "rows": 0, "has_opening": 0, "has_closing": 0, "has_peak": 0}
    )
    for row in hist_rows or []:
        slug = str(row.get("bookmaker_name") or "").lower().replace(" ", "")
        per_book[slug]["rows"] += 1
        per_book[slug]["markets"][row.get("market_key")] += 1
        if row.get("opening"):
            per_book[slug]["has_opening"] += 1
        if row.get("closing"):
            per_book[slug]["has_closing"] += 1
        if row.get("peak"):
            per_book[slug]["has_peak"] += 1

    focus = []
    for name, bid in FOCUS_BOOKS.items():
        slug_hits = [k for k in per_book if name in k or (name == "1xbet" and "1x" in k)]
        rows = sum(per_book[k]["rows"] for k in slug_hits) if slug_hits else 0
        focus.append(
            {
                "bookmaker": name,
                "bookmaker_id": bid,
                "listed_in_api": any(
                    name in str(b.get("slug") or "").lower() or name in str(b.get("name") or "").lower()
                    for b in books
                ),
                "history_rows_sample_fixture": rows,
                "markets_sample": sorted(
                    {m for k in slug_hits for m, c in per_book[k]["markets"].items() for _ in range(c)}
                )[:15],
            }
        )

    return {
        "generated_at": _now(),
        "sample_fixture_id": sample_fixture_id,
        "bookmakers_listed": len(books),
        "history_row_count": len(hist_rows or []),
        "history_markets": sorted({r.get("market_key") for r in hist_rows or []}),
        "per_bookmaker_sample": {k: {**v, "markets": dict(v["markets"])} for k, v in per_book.items()},
        "focus_bookmakers": focus,
        "first_team_to_score_market_present": any(
            "first" in str(m).lower() and "score" in str(m).lower() for m in {r.get("market_key") for r in hist_rows or []}
        ),
    }


def _extract_signals(fx: dict[str, Any], hist_rows: list[dict[str, Any]]) -> dict[str, Any]:
    odds = fx.get("odds") or {}
    prob = fx.get("probability") or {}
    ft = odds.get("ft_result") or {}

    def _consensus_implied() -> tuple[float | None, float | None, float | None]:
        return _implied(ft.get("home")), _implied(ft.get("draw")), _implied(ft.get("away"))

    def _from_history(book_ids: set[int], field: str) -> tuple[float | None, float | None]:
        home_vals, away_vals = [], []
        for row in hist_rows:
            if row.get("market_key") != "ft_result":
                continue
            if int(row.get("bookmaker_id") or 0) not in book_ids:
                continue
            val = row.get(field) or row.get("latest")
            side = str(row.get("outcome") or "")
            impl = _implied(float(val)) if val is not None else None
            if impl is None:
                continue
            if side == "home":
                home_vals.append(impl)
            elif side == "away":
                away_vals.append(impl)
        return (
            statistics.mean(home_vals) if home_vals else None,
            statistics.mean(away_vals) if away_vals else None,
        )

    ch, ca = _from_history(set(FOCUS_BOOKS.values()), "closing")
    sh, sa = _from_history({FOCUS_BOOKS["pinnacle"]}, "closing")
    if sh is None:
        sh, sa = _from_history({FOCUS_BOOKS["pinnacle"]}, "peak")

    cons_h, cons_d, cons_a = _consensus_implied()
    # FTS proxy: no dedicated market — use home_goals over_05 vs away_goals over_05 implied under as weak proxy
    hg = odds.get("home_goals") or {}
    ag = odds.get("away_goals") or {}
    fts_h = _implied(hg.get("over_05"))
    fts_a = _implied(ag.get("over_05"))

    return {
        "consensus_mw": (cons_h, cons_a),
        "closing_mw": (ch, ca),
        "sharp_mw": (sh, sa),
        "fts_proxy": (fts_h, fts_a),
        "combined": (
            (cons_h + (fts_h or 0)) / 2 if cons_h and fts_h else cons_h,
            (cons_a + (fts_a or 0)) / 2 if cons_a and fts_a else cons_a,
        ),
        "probability_home": prob.get("home_win"),
        "probability_away": prob.get("away_win"),
    }


def _infer_first_goal_side(fx: dict[str, Any]) -> str | None:
    """Infer FG side from finished score + HT score when events unavailable."""
    if str(fx.get("status", "")).upper() not in ("FT", "AET", "PEN", "FINISHED"):
        return None
    hg = fx.get("home_goals")
    ag = fx.get("away_goals")
    if hg is None or ag is None:
        return None
    if int(hg) == 0 and int(ag) == 0:
        return "none"
    ht = str(fx.get("ht_score") or "")
    if "-" in ht:
        try:
            hht, aht = [int(x) for x in ht.split("-", 1)]
            if hht > 0 and aht == 0:
                return "home"
            if aht > 0 and hht == 0:
                return "away"
        except ValueError:
            pass
    return None


def run_fg_signal_test(client: OddAlertsClient, *, max_fixtures: int = 120) -> dict[str, Any]:
    fixture_ids = _collect_fixture_ids(client)[:max_fixtures]
    strategies = {
        "A_consensus_match_winner": lambda s: _pick_side(*s["consensus_mw"]),
        "B_closing_match_winner": lambda s: _pick_side(*s["closing_mw"]),
        "C_sharp_match_winner": lambda s: _pick_side(*s["sharp_mw"]),
        "D_first_team_to_score_proxy": lambda s: _pick_side(*s["fts_proxy"]),
        "E_combined_odds_signal": lambda s: _pick_side(*s["combined"]),
    }
    stats = {k: {"correct": 0, "wrong": 0, "pending": 0, "coverage": 0} for k in strategies}
    evaluable_fixtures = 0
    signal_coverage = {k: 0 for k in strategies}

    for fid in fixture_ids:
        fx_res = client.get_fixture(fid, include="odds,probability")
        client.throttle(0.1)
        if not fx_res.ok:
            continue
        fx = (fx_res.data.get("data") or [None])[0]
        if not fx:
            continue
        hist = client.get_odds_history(fid)
        client.throttle(0.1)
        hist_rows = hist.data.get("data") if hist.ok and isinstance(hist.data, dict) else []
        signals = _extract_signals(fx, hist_rows or [])
        actual = _infer_first_goal_side(fx)

        if actual in ("home", "away"):
            evaluable_fixtures += 1

        for name, fn in strategies.items():
            pred = fn(signals)
            if pred is None:
                stats[name]["pending"] += 1
                continue
            stats[name]["coverage"] += 1
            signal_coverage[name] += 1
            if actual not in ("home", "away"):
                stats[name]["pending"] += 1
                continue
            if pred == actual:
                stats[name]["correct"] += 1
            else:
                stats[name]["wrong"] += 1

    summary = {}
    for name, st in stats.items():
        decided = st["correct"] + st["wrong"]
        summary[name] = {
            **st,
            "fg_accuracy": round(st["correct"] / decided, 4) if decided else None,
            "pending_rate": round(st["pending"] / max(len(fixture_ids), 1), 4),
            "signal_coverage_rate": round(signal_coverage[name] / max(len(fixture_ids), 1), 4),
        }

    return {
        "generated_at": _now(),
        "fixtures_scanned": len(fixture_ids),
        "evaluable_finished_fixtures": evaluable_fixtures,
        "strategies": summary,
        "limitation": "No finished fixtures with FG labels in OA pool; FG accuracy null unless evaluable_finished_fixtures>0",
        "k2_sportmonks_reference": {
            "sharp_mw_fg_accuracy": 0.7872,
            "consensus_mw_fg_accuracy": 0.7766,
            "evaluable_fixtures": 104,
        },
    }


def run_market_audit(client: OddAlertsClient, *, sample_size: int = 80) -> dict[str, Any]:
    fixture_ids = _collect_fixture_ids(client)[:sample_size]
    btts_rows = []
    ou_rows = []
    egie_btts_baseline = 0.5525
    egie_ou25_baseline = 0.5463

    for fid in fixture_ids:
        res = client.get_fixture(fid, include="odds,probability")
        client.throttle(0.1)
        if not res.ok:
            continue
        fx = (res.data.get("data") or [None])[0]
        if not fx:
            continue
        prob = fx.get("probability") or {}
        odds = fx.get("odds") or {}
        btts_odds = odds.get("btts") or {}
        tg = odds.get("total_goals") or {}

        if prob.get("btts") is not None:
            implied_yes = _implied(btts_odds.get("yes"))
            btts_rows.append(
                {
                    "fixture_id": fid,
                    "oa_probability_btts": prob.get("btts"),
                    "market_implied_btts": implied_yes,
                    "status": fx.get("status"),
                }
            )
        if prob.get("o25") is not None:
            ou_rows.append(
                {
                    "fixture_id": fid,
                    "oa_probability_over25": prob.get("o25"),
                    "market_implied_over25": _implied(tg.get("over_25")),
                    "status": fx.get("status"),
                }
            )

    def _mean_delta(rows: list[dict[str, Any]], p_key: str, i_key: str) -> float | None:
        deltas = []
        for r in rows:
            p, i = r.get(p_key), r.get(i_key)
            if p is None or i is None:
                continue
            deltas.append(abs(float(p) / 100 - float(i)))
        return round(statistics.mean(deltas), 4) if deltas else None

    return {
        "generated_at": _now(),
        "sample_size": sample_size,
        "btts": {
            "rows_with_probability": len(btts_rows),
            "mean_abs_delta_prob_vs_market": _mean_delta(btts_rows, "oa_probability_btts", "market_implied_btts"),
            "egie_lgbm_test_baseline": egie_btts_baseline,
            "finished_rows_for_accuracy": sum(1 for r in btts_rows if str(r.get("status")).upper() in ("FT", "AET", "PEN")),
            "accuracy_measurable": False,
        },
        "over_under_25": {
            "rows_with_probability": len(ou_rows),
            "mean_abs_delta_prob_vs_market": _mean_delta(ou_rows, "oa_probability_over25", "market_implied_over25"),
            "egie_lgbm_test_baseline": egie_ou25_baseline,
            "finished_rows_for_accuracy": sum(1 for r in ou_rows if str(r.get("status")).upper() in ("FT", "AET", "PEN")),
            "accuracy_measurable": False,
        },
        "note": "Outcome accuracy requires finished fixtures; OA pool sampled is overwhelmingly upcoming (NS)",
    }


def run_correct_score_audit(client: OddAlertsClient, sample_fixture_id: int = 420562849) -> dict[str, Any]:
    res = client.get_fixture(sample_fixture_id, include="odds,probability,predictions")
    fx = (res.data.get("data") or [None])[0] if res.ok else {}
    prob = (fx or {}).get("probability") or {}
    xg_proxy = {
        "o05_home_goals_prob": prob.get("o05_home_goals"),
        "o15_home_goals_prob": prob.get("o15_home_goals"),
        "o05_away_goals_prob": prob.get("o05_away_goals"),
        "o15_away_goals_prob": prob.get("o15_away_goals"),
    }
    return {
        "generated_at": _now(),
        "sample_fixture_id": sample_fixture_id,
        "correct_score_market_in_odds_history": False,
        "correct_score_predictions_field_present": "predictions" in (fx or {}),
        "expected_goals_proxy_from_probability": xg_proxy,
        "useful_for_exact_score_engine": prob.get("home_win") is not None,
        "useful_for_goal_timing_engine": prob.get("o15") is not None and prob.get("highest_scoring_half") is None,
        "highest_scoring_half_odds": ((fx or {}).get("odds") or {}).get("highest_scoring_half"),
        "probability_fields_count": len(prob),
        "note": "No discrete correct-score distribution vector exposed on fixture include; only marginal goal-count probs",
    }


def run_historical_depth_audit(client: OddAlertsClient) -> dict[str, Any]:
    seasons: list[dict[str, Any]] = []
    for page in range(1, 25):
        res = client.get_competitions(page=page, per_page=250)
        client.throttle(0.1)
        if not res.ok:
            break
        rows = res.data.get("data") if isinstance(res.data, dict) else []
        if not rows:
            break
        for row in rows:
            sid = row.get("current_season")
            if sid:
                seasons.append({"competition": row.get("name"), "country": row.get("country"), "season_id": sid})
        info = res.data.get("info") if isinstance(res.data, dict) else {}
        if not info.get("next_page_url") and page > 1:
            break

    hist = client.get_odds_history(420562849)
    hist_rows = len(hist.data.get("data") or []) if hist.ok and isinstance(hist.data, dict) else 0

    return {
        "generated_at": _now(),
        "competitions_paginated": len(seasons),
        "oldest_season_note": "Season IDs are numeric; bulk historical fixture list endpoint redirects",
        "odds_history_sample_rows": hist_rows,
        "odds_history_window_documented": "~6 months opening/closing/peak per OddAlerts docs",
        "predictions_bulk_endpoint": "redirects without fixture context",
        "value_past_endpoint": "returns empty body on trial token",
        "fixtures_list_endpoint": "redirects (302) on competition/date filters",
        "sample_season_ids": seasons[:10],
    }


def build_provider_decision(
    connectivity: dict[str, Any],
    coverage: dict[str, Any],
    books: dict[str, Any],
    fg: dict[str, Any],
    markets: dict[str, Any],
    cs: dict[str, Any],
    depth: dict[str, Any],
) -> dict[str, Any]:
    oa_strengths = []
    oa_gaps = []
    if connectivity.get("pass_count", 0) >= 6:
        oa_strengths.append("Core endpoints reachable (fixture detail, odds/history, value, trends)")
    if books.get("history_row_count", 0) > 50:
        oa_strengths.append("Rich opening/closing/peak odds history per fixture")
    if not books.get("first_team_to_score_market_present"):
        oa_gaps.append("No first_team_to_score market in odds history sample")
    if fg.get("evaluable_finished_fixtures", 0) == 0:
        oa_gaps.append("FG Team accuracy not measurable — zero finished fixtures in sampled pool")
    if coverage.get("leagues", {}).get("premier_league", {}).get("fixtures_seen", 0) == 0:
        oa_gaps.append("Low Premier League visibility in upcoming value pool during audit window")

    ranking = [
        {
            "provider": "Sportmonks",
            "score": 88,
            "fg_team_evidence": "78.7% sharp MW (K2, n=104 UEFA)",
            "role": "UEFA odds + enrichment",
        },
        {
            "provider": "OddAlerts",
            "score": 72,
            "fg_team_evidence": "Not measured — no finished FG sample",
            "role": "Probability model + multi-book odds history",
        },
        {
            "provider": "API-Football",
            "score": 65,
            "fg_team_evidence": "EGIE events + 1617 finished rows; odds enrichment 4.3%",
            "role": "Primary fixtures/results/events store",
        },
    ]

    return {
        "generated_at": _now(),
        "is_oddalerts_useful": len(oa_strengths) >= 2,
        "strengths": oa_strengths,
        "gaps": oa_gaps,
        "provider_ranking": ranking,
        "recommended_architecture": (
            "Keep API-Football as fixture/results spine; keep Sportmonks for UEFA sharp odds; "
            "add OddAlerts as OPTIONAL enrichment shadow for probability model + odds history "
            "(not primary FG path until finished-fixture API access and FTS market verified)."
        ),
        "worth_monthly_pay": "Conditional — yes for probability+odds-history bundle if PL/BL list access unlocked; "
        "no as FG primary replacement for Sportmonks today",
    }
