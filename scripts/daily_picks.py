"""
Daily Picks System — 1x2 predictions with odds and profit calculation.
Bundesliga + Premier League + World Cup 2026.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

SUPPORTED_LEAGUES = {
    "World Cup": {"key": "world_cup_2026", "min_confidence": 40},
    "Bundesliga": {"key": "bundesliga", "min_confidence": 50},
    "Premier League": {"key": "premier_league", "min_confidence": 50},
}

AF_LEAGUE_IDS = {1: "World Cup", 78: "Bundesliga", 39: "Premier League"}
AF_LEAGUE_SEASONS = {1: "2026", 78: "2025", 39: "2025"}
MAX_PICKS = 10


def get_today_fixtures(client: ApiFootballClient) -> list[dict]:
    today = date.today().isoformat()
    seen: set[int] = set()
    fixtures: list[dict] = []

    for league_id, league_name in AF_LEAGUE_IDS.items():
        season = AF_LEAGUE_SEASONS.get(league_id, "2025")
        result = client._safe_get(
            "fixtures",
            {"date": today, "league": str(league_id), "season": season},
            placeholder_factory=lambda: None,
            ttl_seconds=300,
        )
        if not result or not result.data:
            continue

        for f in result.data:
            fid = f["fixture"]["id"]
            if fid in seen:
                continue
            status = f.get("fixture", {}).get("status", {}).get("short", "")
            if status not in ("NS", "TBD", "PST"):
                continue  # فقط بازی‌های شروع‌نشده
            seen.add(fid)
            fixtures.append({
                "fixture_id": fid,
                "league": league_name,
                "league_id": league_id,
                "home": f["teams"]["home"]["name"],
                "away": f["teams"]["away"]["name"],
                "kickoff": f["fixture"]["date"],
            })

    fixtures.sort(key=lambda x: x.get("kickoff") or "")
    return fixtures


def get_odds(home: str, away: str, league: str, settings) -> dict:
    key = getattr(settings, 'the_odds_api_key', '') or ''
    if not key:
        return {}
    sport_map = {
        "World Cup": "soccer_fifa_world_cup",
        "Bundesliga": "soccer_germany_bundesliga",
        "Premier League": "soccer_epl",
    }
    sport = sport_map.get(league, "soccer_fifa_world_cup")
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={key}&regions=eu&markets=h2h&oddsFormat=decimal"
        req = urllib.request.urlopen(url, timeout=10)
        data = json.loads(req.read())
        def norm(s): return s.lower().strip()
        for event in data:
            ah = norm(event.get("home_team", ""))
            aa = norm(event.get("away_team", ""))
            if norm(home) in ah or ah in norm(home) or norm(away) in aa or aa in norm(away):
                odds = {"home": None, "draw": None, "away": None}
                for bm in event.get("bookmakers", [])[:3]:
                    for mkt in bm.get("markets", []):
                        if mkt.get("key") != "h2h":
                            continue
                        for o in mkt.get("outcomes", []):
                            name = norm(o.get("name", ""))
                            price = float(o.get("price", 0))
                            if name == norm(event.get("home_team", "")):
                                odds["home"] = odds["home"] or price
                            elif name == norm(event.get("away_team", "")):
                                odds["away"] = odds["away"] or price
                            elif "draw" in name:
                                odds["draw"] = odds["draw"] or price
                return odds
        return {}
    except Exception as e:
        print(f"  Odds error: {e}")
        return {}


def run_prediction(fixture_id: int, competition_key: str, settings) -> dict | None:
    try:
        from worldcup_predictor.agents.base import AgentContext
        from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
        from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
        from worldcup_predictor.agents.prediction_agent import PredictionAgent
        from worldcup_predictor.schedule.context_loader import load_tournament_context

        context = AgentContext(
            settings=settings,
            competition_key=competition_key,
            locale="en",
        )
        load_tournament_context(context)

        collector = DataCollectorAgent(context)
        collect_result = collector.run(fixture_id=fixture_id)
        if not collect_result.success:
            return None

        specialist = SpecialistOrchestrator(context)
        specialist.run(fixture_id=fixture_id)

        predictor = PredictionAgent(context)
        predict_result = predictor.run(fixture_id=fixture_id)
        if not predict_result.success:
            return None

        pred = predict_result.data
        conf = float(pred.confidence_score or 0)
        breakdown = pred.confidence_breakdown

        return {
            "fixture_id": fixture_id,
            "selection": str(pred.one_x_two.selection or ""),
            "confidence": conf,
            "no_bet": False,  # bypass WDE
            "risk": str(pred.risk_level or ""),
            "dq": float(breakdown.data_quality_score if breakdown else 0),
        }
    except Exception as e:
        print(f"  Prediction error for {fixture_id}: {e}")
        return None


def format_selection(sel: str) -> str:
    return {"home_win": "HOME", "away_win": "AWAY", "draw": "DRAW"}.get(sel, sel.upper())


def kelly_stake(prob: float, odds: float, bankroll: float = 100.0) -> float:
    """Kelly Criterion برای مدیریت سرمایه."""
    if odds <= 1.0:
        return 0.0
    q = 1 - prob
    b = odds - 1
    kelly = (b * prob - q) / b
    kelly = max(0.0, kelly * 0.25)  # quarter kelly برای safety
    return round(bankroll * kelly, 2)


def main():
    settings = get_settings()
    client = ApiFootballClient(settings)

    print(f"\n{'='*60}")
    print(f"  DAILY PICKS — {date.today().strftime('%A, %d %B %Y')}")
    print(f"{'='*60}\n")

    fixtures = get_today_fixtures(client)
    print(f"Found {len(fixtures)} upcoming fixtures in supported leagues\n")

    if not fixtures:
        print("No fixtures today in Bundesliga / Premier League / World Cup.")
        return

    picks = []

    for f in fixtures:
        league_config = SUPPORTED_LEAGUES.get(f["league"], {})
        comp_key = league_config.get("key", "world_cup_2026")
        min_conf = league_config.get("min_confidence", 50)

        print(f"Analyzing: {f['home']} vs {f['away']} ({f['league']})...")
        pred = run_prediction(f["fixture_id"], comp_key, settings)

        if not pred:
            print(f"  → Skipped (prediction failed)")
            continue

        if pred["no_bet"] or pred["confidence"] < min_conf:
            print(f"  → No bet (conf={pred['confidence']:.1f}, no_bet={pred['no_bet']})")
            continue

        odds = get_odds(f["home"], f["away"], f["league"], settings)
        picks.append({**f, **pred, "odds": odds})
        print(f"  → ✅ {format_selection(pred['selection'])} | conf={pred['confidence']:.1f}")

    print(f"\n{'='*60}")
    print(f"  TOP PICKS ({len(picks)} bets)")
    print(f"{'='*60}\n")

    if not picks:
        print("No confident picks today.")
        return

    # sort by confidence
    picks.sort(key=lambda x: x["confidence"], reverse=True)
    top_picks = picks[:MAX_PICKS]

    total_potential = 0.0
    for i, p in enumerate(top_picks, 1):
        sel = format_selection(p["selection"])
        conf = p["confidence"]
        prob = conf / 100

        odds = p.get("odds", {})
        sel_key = {"home_win": "home", "away_win": "away", "draw": "draw"}.get(p["selection"], "")
        real_odds = odds.get(sel_key, 0) or 0
        est_odds = real_odds if real_odds > 1 else round(1 / max(prob, 0.1) * 0.88, 2)
        stake = kelly_stake(prob, est_odds)
        potential = round(stake * (est_odds - 1), 2)
        odds_str = f"{est_odds:.2f}" + (" (real)" if real_odds > 1 else " (est)")
        total_potential += potential

        print(f"{i:2}. {p['home']} vs {p['away']}")
        print(f"    League: {p['league']} | Pick: {sel}")
        print(f"    Confidence: {conf:.1f}% | Odds: {odds_str}")
        print(f"    Kelly stake: €{stake} | Potential profit: €{potential}")
        print()

    print(f"{'─'*60}")
    print(f"Total potential profit (if all win): €{total_potential:.2f}")

    # سیستم پیشنهادی
    n = len(top_picks)
    if n >= 6:
        print(f"\n📊 SYSTEM BET: {n-2} from {n} (covers most combinations)")
    elif n >= 4:
        print(f"\n📊 SYSTEM BET: {n-1} from {n}")
    else:
        print(f"\n📊 Single bets recommended ({n} picks)")

    # ذخیره به فایل
    output = {
        "date": date.today().isoformat(),
        "picks": top_picks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path = Path(f"artifacts/daily_picks_{date.today().isoformat()}.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n💾 Saved to {out_path}")


if __name__ == "__main__":
    main()
