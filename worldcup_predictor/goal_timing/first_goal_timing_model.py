"""
First Goal Timing Model v3 — Logistic Regression با class balancing.
فقط Bundesliga + Premier League.
Zero external dependencies.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from typing import Any

DB_PATH = "data/football_intelligence.db"

SUPPORTED_LEAGUES = {"bundesliga", "premier_league", "champions_league"}

LEAGUE_BASELINES: dict[str, float] = {
    "bundesliga": 0.549,
    "premier_league": 0.576,
    "champions_league": 0.555,
}


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class Sample:
    """یه بازی برای train/test."""
    fixture_id: int
    competition: str
    features: list[float]
    label: int  # 1=under_30, 0=over_30


@dataclass
class TimingPrediction:
    fixture_id: int
    home_team: str
    away_team: str
    competition: str
    prob_under_30: float
    prob_over_30: float
    prediction: str
    confidence: float
    reasoning: list[str] = field(default_factory=list)


# ─── Logistic Regression ──────────────────────────────────────────────────────

class LogisticRegression:
    """Logistic regression با weighted samples برای class balancing."""

    def __init__(self, lr: float = 0.05, epochs: int = 3000, l2: float = 0.001):
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self.w: list[float] = []
        self.b: float = 0.0

    @staticmethod
    def _sigmoid(x: float) -> float:
        x = max(-500.0, min(500.0, x))
        return 1.0 / (1.0 + math.exp(-x))

    def fit(self, samples: list[Sample], class_weight: dict[int, float] | None = None) -> None:
        if not samples:
            return
        n = len(samples[0].features)
        self.w = [0.0] * n
        self.b = 0.0
        cw = class_weight or {0: 1.0, 1: 1.0}

        for _ in range(self.epochs):
            dw = [0.0] * n
            db = 0.0
            total_w = 0.0
            for s in samples:
                weight = cw.get(s.label, 1.0)
                z = sum(wi * xi for wi, xi in zip(self.w, s.features)) + self.b
                p = self._sigmoid(z)
                err = (p - s.label) * weight
                for i in range(n):
                    dw[i] += err * s.features[i]
                db += err
                total_w += weight

            scale = self.lr / max(total_w, 1.0)
            self.w = [
                wi - scale * dw[i] - self.lr * self.l2 * wi
                for i, wi in enumerate(self.w)
            ]
            self.b -= scale * db

    def predict_proba(self, features: list[float]) -> float:
        z = sum(wi * xi for wi, xi in zip(self.w, features)) + self.b
        return self._sigmoid(z)


# ─── Feature extraction ───────────────────────────────────────────────────────

def _team_avg_goals(conn: sqlite3.Connection, team: str, before: str, n: int = 15) -> tuple[float, float]:
    """(avg_scored, avg_conceded)"""
    rows = conn.execute("""
        SELECT f.home_team, r.home_goals, r.away_goals
        FROM fixtures f
        INNER JOIN fixture_results r ON f.fixture_id = r.fixture_id
        WHERE (f.home_team = ? OR f.away_team = ?)
        AND f.kickoff_utc < ? AND f.is_placeholder = 0
        AND f.competition_key IN ('bundesliga','premier_league','champions_league')
        ORDER BY f.kickoff_utc DESC LIMIT ?
    """, (team, team, before, n)).fetchall()

    if not rows:
        return 1.3, 1.3

    scored, conceded = [], []
    for home, hg, ag in rows:
        if home == team:
            scored.append(hg); conceded.append(ag)
        else:
            scored.append(ag); conceded.append(hg)

    return sum(scored) / len(scored), sum(conceded) / len(conceded)


def _team_early_rate(conn: sqlite3.Connection, team: str, before: str) -> float:
    """نرخ تاریخی early goal — بازی بدون گل = over_30."""
    row = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN fg.first_goal IS NOT NULL AND fg.first_goal <= 30 THEN 1 ELSE 0 END) as early
        FROM fixtures f
        INNER JOIN fixture_results r ON f.fixture_id = r.fixture_id
        LEFT JOIN (
            SELECT fixture_id, MIN(minute) as first_goal
            FROM fixture_goal_events
            WHERE minute IS NOT NULL AND is_own_goal = 0
            GROUP BY fixture_id
        ) fg ON f.fixture_id = fg.fixture_id
        WHERE (f.home_team = ? OR f.away_team = ?)
        AND f.kickoff_utc < ? AND f.is_placeholder = 0
        AND f.competition_key IN ('bundesliga','premier_league','champions_league')
    """, (team, team, before)).fetchone()

    if not row or not row[0] or row[0] < 5:
        return 0.55
    return row[1] / row[0]


def _get_ou_odds(conn: sqlite3.Connection, fixture_id: int) -> tuple[float, float]:
    """(over_2_5_odds, under_2_5_odds) از odds_snapshots."""
    import json
    row = conn.execute("""
        SELECT payload_json FROM odds_snapshots
        WHERE fixture_id = ? ORDER BY snapshot_at DESC LIMIT 1
    """, (fixture_id,)).fetchone()

    if not row:
        return 0.0, 0.0

    try:
        payload = json.loads(row[0])
        over_list, under_list = [], []
        for bm in payload.get("bookmakers", []):
            for bet in bm.get("bets", []):
                market = str(bet.get("market", "")).lower()
                label = str(bet.get("label", "")).lower()
                if "over" in market and "under" in market or "2.5" in market or "ou" in market:
                    try:
                        val = float(bet.get("value", 0) or bet.get("odd", 0))
                        if val <= 1.0:
                            continue
                        if "over" in label:
                            over_list.append(val)
                        elif "under" in label:
                            under_list.append(val)
                    except (TypeError, ValueError):
                        continue
        avg_over = sum(over_list) / len(over_list) if over_list else 0.0
        avg_under = sum(under_list) / len(under_list) if under_list else 0.0
        return avg_over, avg_under
    except Exception:
        return 0.0, 0.0


def extract_features(
    conn: sqlite3.Connection,
    fixture_id: int,
    kickoff: str,
    home: str,
    away: str,
    competition: str,
) -> list[float]:
    """10 feature برای مدل."""
    baseline = LEAGUE_BASELINES.get(competition, 0.55)
    h_scored, h_conceded = _team_avg_goals(conn, home, kickoff)
    a_scored, a_conceded = _team_avg_goals(conn, away, kickoff)
    h_early = _team_early_rate(conn, home, kickoff)
    a_early = _team_early_rate(conn, away, kickoff)
    over_odds, under_odds = _get_ou_odds(conn, fixture_id)

    # implied probability از odds
    over_prob = (1 / over_odds) if over_odds > 1 else 0.5
    under_prob = (1 / under_odds) if under_odds > 1 else 0.5

    return [
        baseline,                              # 1. league baseline
        h_scored,                              # 2. home avg goals scored
        a_scored,                              # 3. away avg goals scored
        h_conceded,                            # 4. home avg goals conceded
        a_conceded,                            # 5. away avg goals conceded
        h_early,                               # 6. home team early goal rate
        a_early,                               # 7. away team early goal rate
        (h_scored + a_scored) / 2,             # 8. avg attack strength
        over_prob,                             # 9. implied over prob از odds
        1.0 if competition == "bundesliga" else 0.0,  # 10. league flag
    ]


# ─── Build dataset ────────────────────────────────────────────────────────────

def build_dataset(
    db_path: str = DB_PATH,
    competitions: list[str] | None = None,
) -> list[Sample]:
    """همه بازی‌های تموم‌شده — بازی بدون گل = over_30."""
    comps = competitions or list(SUPPORTED_LEAGUES)
    conn = sqlite3.connect(db_path)

    placeholders = ",".join("?" * len(comps))
    rows = conn.execute(f"""
        SELECT f.fixture_id, f.competition_key, f.home_team, f.away_team,
               f.kickoff_utc,
               fg.first_goal
        FROM fixtures f
        INNER JOIN fixture_results r ON f.fixture_id = r.fixture_id
        LEFT JOIN (
            SELECT fixture_id, MIN(minute) as first_goal
            FROM fixture_goal_events
            WHERE minute IS NOT NULL AND is_own_goal = 0
            GROUP BY fixture_id
        ) fg ON f.fixture_id = fg.fixture_id
        WHERE f.is_placeholder = 0
        AND f.competition_key IN ({placeholders})
        ORDER BY f.kickoff_utc ASC
    """, comps).fetchall()

    samples = []
    for fid, comp, home, away, kickoff, first_goal in rows:
        kickoff_str = str(kickoff)[:19]
        # بازی بدون گل یا گل بعد از 30 = over_30
        label = 1 if (first_goal is not None and first_goal <= 30) else 0
        feats = extract_features(conn, fid, kickoff_str, home, away, comp)
        samples.append(Sample(
            fixture_id=fid,
            competition=comp,
            features=feats,
            label=label,
        ))

    conn.close()
    return samples


# ─── Train ────────────────────────────────────────────────────────────────────

def train_model(samples: list[Sample]) -> LogisticRegression:
    """Train با class balancing — under_30 وزن بیشتری میگیره."""
    n_pos = sum(1 for s in samples if s.label == 1)
    n_neg = sum(1 for s in samples if s.label == 0)
    total = len(samples)

    # وزن برعکس frequency
    w_pos = total / (2 * n_pos) if n_pos else 1.0
    w_neg = total / (2 * n_neg) if n_neg else 1.0

    model = LogisticRegression(lr=0.05, epochs=3000, l2=0.001)
    model.fit(samples, class_weight={1: w_pos, 0: w_neg})
    return model


# ─── Evaluate ─────────────────────────────────────────────────────────────────

def evaluate(db_path: str = DB_PATH) -> dict[str, Any]:
    """Train روی 80%، test روی 20% — temporal split."""
    all_samples = build_dataset(db_path=db_path)
    if len(all_samples) < 50:
        return {"error": "insufficient data"}

    split = int(len(all_samples) * 0.8)
    train = all_samples[:split]
    test = all_samples[split:]

    model = train_model(train)

    results: dict[str, Any] = {}
    for comp_filter in [None, "bundesliga", "premier_league", "champions_league"]:
        test_subset = [s for s in test if comp_filter is None or s.competition == comp_filter]
        if not test_subset:
            continue

        correct = under_c = over_c = under_t = over_t = 0
        for s in test_subset:
            prob = model.predict_proba(s.features)
            pred = 1 if prob >= 0.5 else 0
            if pred == s.label:
                correct += 1
            if s.label == 1:
                under_t += 1
                if pred == 1:
                    under_c += 1
            else:
                over_t += 1
                if pred == 0:
                    over_c += 1

        label = comp_filter or "ALL"
        results[label] = {
            "total": len(test_subset),
            "accuracy": round(correct / len(test_subset), 3),
            "under30_acc": round(under_c / under_t, 3) if under_t else 0,
            "over30_acc": round(over_c / over_t, 3) if over_t else 0,
            "under30_n": under_t,
            "over30_n": over_t,
        }

    return results


# ─── Predict fixture ──────────────────────────────────────────────────────────

def predict_fixture(
    fixture_id: int,
    model: LogisticRegression,
    db_path: str = DB_PATH,
) -> TimingPrediction | None:
    conn = sqlite3.connect(db_path)
    row = conn.execute("""
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc
        FROM fixtures WHERE fixture_id = ?
    """, (fixture_id,)).fetchone()

    if not row:
        conn.close()
        return None

    fid, comp, home, away, kickoff = row
    if comp not in SUPPORTED_LEAGUES:
        conn.close()
        return None

    feats = extract_features(conn, fid, str(kickoff)[:19], home, away, comp)
    conn.close()

    prob = model.predict_proba(feats)
    prediction = "under_30" if prob >= 0.5 else "over_30"
    confidence = abs(prob - 0.5) * 2

    return TimingPrediction(
        fixture_id=fid,
        home_team=home,
        away_team=away,
        competition=comp,
        prob_under_30=round(prob, 3),
        prob_over_30=round(1 - prob, 3),
        prediction=prediction,
        confidence=round(confidence, 3),
        reasoning=[
            f"League: {comp} (baseline {LEAGUE_BASELINES.get(comp, 0.55):.1%})",
            f"Under 30 prob: {prob:.1%}",
        ],
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== First Goal Timing Model v3 ===")
    print("Building dataset...")
    samples = build_dataset()
    split = int(len(samples) * 0.8)
    print(f"Total samples: {len(samples)} | Train: {split} | Test: {len(samples)-split}")
    print(f"Under 30: {sum(1 for s in samples if s.label==1)} | Over 30: {sum(1 for s in samples if s.label==0)}")
    print()

    print("Evaluating (temporal split 80/20)...")
    results = evaluate()
    for label, r in results.items():
        if "error" in r:
            continue
        print(f"{label} ({r['total']} test samples):")
        print(f"  Accuracy:  {r['accuracy']:.1%}")
        print(f"  Under 30:  {r['under30_acc']:.1%} ({r['under30_n']} samples)")
        print(f"  Over  30:  {r['over30_acc']:.1%} ({r['over30_n']} samples)")
        print()
