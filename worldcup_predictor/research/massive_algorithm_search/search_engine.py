"""Resumable deterministic strategy search engine (historical, no API calls)."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterator

from worldcup_predictor.research.massive_algorithm_search.corpus import MassiveRow

SEED = 20260802


def cfg_hash(cfg: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = hits / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) / n) + (z * z / (4 * n * n)))
    return round((centre - margin) / den, 4), round((centre + margin) / den, 4)


@dataclass(frozen=True)
class RuleConfig:
    market: str  # home|draw|away|favorite|underdog
    direction_source: str  # wde|ecse|argmax|market
    min_confidence: float
    min_edge: float
    max_entropy: float | None
    min_top5: float | None
    odds_min: float | None
    odds_max: float | None
    require_wde_ecse_agree: bool
    require_market_agree: bool
    max_margin: float | None
    balanced_only: bool
    exclude_no_bet: bool
    min_lambda_total: float | None
    max_lambda_total: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def iter_search_space(max_n: int) -> Iterator[RuleConfig]:
    markets = ["home", "draw", "away", "favorite", "underdog"]
    sources = ["wde", "ecse", "argmax", "market"]
    confs = [0, 45, 50, 55, 58, 60, 62, 65, 70]
    edges = [0.0, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    ents = [None, 1.80, 1.70, 1.62, 1.55]
    top5s = [None, 0.40, 0.50, 0.55, 0.60, 0.65]
    odds_mins = [None, 1.20, 1.40, 1.50, 1.70]
    odds_maxs = [None, 1.50, 1.80, 2.00, 2.20, 2.50, 3.00, 4.00]
    margins = [None, 0.08, 0.12, 0.18]
    lam_mins = [None, 1.5, 2.0]
    lam_maxs = [None, 2.2, 2.8, 3.5]
    seen: set[str] = set()
    n = 0
    for vals in product(
        markets,
        sources,
        confs,
        edges,
        ents,
        top5s,
        odds_mins,
        odds_maxs,
        [False, True],
        [False, True],
        margins,
        [False, True],
        [True, False],
        lam_mins,
        lam_maxs,
    ):
        # skip invalid odds band
        omin, omax = vals[6], vals[7]
        if omin is not None and omax is not None and omin >= omax:
            continue
        cfg = RuleConfig(*vals)
        h = cfg_hash(cfg.to_dict())
        if h in seen:
            continue
        seen.add(h)
        yield cfg
        n += 1
        if n >= max_n:
            return


def _direction(r: MassiveRow, source: str) -> str | None:
    if source == "wde":
        return r.wde_decision
    if source == "ecse":
        return r.ecse_direction
    if source == "market":
        return r.market_favorite
    if source == "argmax":
        if not any(x is not None for x in (r.home_p, r.draw_p, r.away_p)):
            return r.wde_decision or r.ecse_direction
        return max([("home", r.home_p or 0), ("draw", r.draw_p or 0), ("away", r.away_p or 0)], key=lambda x: x[1])[0]
    return None


def _bet_side(r: MassiveRow, cfg: RuleConfig, direction: str) -> str | None:
    """Map market family to concrete 1X2 side for settlement."""
    if cfg.market in {"home", "draw", "away"}:
        return cfg.market if direction == cfg.market else None
    if cfg.market == "favorite":
        return r.market_favorite if direction == r.market_favorite else None
    if cfg.market == "underdog":
        if not r.market_favorite:
            return None
        # underdog = not favorite (prefer opposite side among H/A, skip draw as underdog unless direction is draw and fav isn't)
        if direction == r.market_favorite:
            return None
        return direction
    return None


def apply_rule(rows: list[MassiveRow], cfg: RuleConfig) -> list[tuple[str, MassiveRow]]:
    out: list[tuple[str, MassiveRow]] = []
    for r in rows:
        if cfg.exclude_no_bet and r.no_bet:
            continue
        if r.has_wde is False and cfg.direction_source == "wde":
            continue
        if cfg.min_confidence and (r.confidence or 0) < cfg.min_confidence:
            continue
        if cfg.min_edge and (r.edge() or 0) < cfg.min_edge:
            continue
        if cfg.max_entropy is not None and r.entropy is not None and r.entropy > cfg.max_entropy:
            continue
        if cfg.min_top5 is not None and (r.top5_mass or 0) < cfg.min_top5:
            continue
        if cfg.require_wde_ecse_agree:
            if not (r.wde_decision and r.ecse_direction and r.wde_decision == r.ecse_direction):
                continue
        direction = _direction(r, cfg.direction_source)
        if not direction:
            continue
        if cfg.require_market_agree and r.market_favorite and direction != r.market_favorite:
            continue
        if cfg.balanced_only and r.balanced_market is False:
            continue
        if cfg.max_margin is not None and r.book_margin is not None and r.book_margin > cfg.max_margin:
            continue
        lt = r.lambda_total()
        if cfg.min_lambda_total is not None and (lt is None or lt < cfg.min_lambda_total):
            continue
        if cfg.max_lambda_total is not None and (lt is None or lt > cfg.max_lambda_total):
            continue
        side = _bet_side(r, cfg, direction)
        if not side:
            continue
        o = {"home": r.odds_home, "draw": r.odds_draw, "away": r.odds_away}.get(side)
        if cfg.odds_min is not None or cfg.odds_max is not None:
            if o is None:
                continue
            if cfg.odds_min is not None and o < cfg.odds_min:
                continue
            if cfg.odds_max is not None and o > cfg.odds_max:
                continue
        out.append((side, r))
    return out


def evaluate_bets(bets: list[tuple[str, MassiveRow]], universe: int) -> dict[str, Any]:
    n = len(bets)
    hits = sum(1 for side, r in bets if side == r.actual_1x2)
    lo, hi = wilson_ci(hits, n)
    pnls = []
    odds_vals = []
    for side, r in bets:
        o = {"home": r.odds_home, "draw": r.odds_draw, "away": r.odds_away}.get(side)
        if o is None or o < 1.01:
            continue
        odds_vals.append(o)
        pnls.append((o - 1.0) if side == r.actual_1x2 else -1.0)
    max_dd = None
    if pnls:
        eq = peak = 0.0
        dd = 0.0
        for x in pnls:
            eq += x
            peak = max(peak, eq)
            dd = min(dd, eq - peak)
        max_dd = round(dd, 4)
    leagues = Counter(r.league or "?" for _, r in bets)
    top_league_share = (leagues.most_common(1)[0][1] / n) if n and leagues else None
    avg_odds = round(sum(odds_vals) / len(odds_vals), 4) if odds_vals else None
    # flag extreme favorites
    extreme_fav = sum(1 for o in odds_vals if o < 1.20) / len(odds_vals) if odds_vals else None
    return {
        "n": n,
        "hits": hits,
        "accuracy": round(hits / n, 4) if n else None,
        "ci95": [lo, hi],
        "coverage": round(n / universe, 4) if universe else None,
        "priced_n": len(pnls),
        "roi": round(sum(pnls) / len(pnls), 4) if pnls else None,
        "max_drawdown": max_dd,
        "avg_odds": avg_odds,
        "median_odds": round(sorted(odds_vals)[len(odds_vals) // 2], 4) if odds_vals else None,
        "net_profit": round(sum(pnls), 4) if pnls else None,
        "top_league_share": round(top_league_share, 4) if top_league_share is not None else None,
        "extreme_fav_share": round(extreme_fav, 4) if extreme_fav is not None else None,
        "flags": _flags(n, hits / n if n else None, avg_odds, extreme_fav, top_league_share),
    }


def _flags(n, acc, avg_odds, extreme_fav, top_league_share) -> list[str]:
    flags = []
    if n is not None and n < 50:
        flags.append("N_LT_50_NOT_DISCOVERY")
    if n is not None and n < 100:
        flags.append("SMALL_SAMPLE")
    if extreme_fav is not None and extreme_fav >= 0.5:
        flags.append("EXTREME_FAVORITE_HEAVY")
    if avg_odds is not None and avg_odds < 1.20:
        flags.append("AVG_ODDS_BELOW_1_20")
    if top_league_share is not None and top_league_share > 0.35:
        flags.append("LEAGUE_CONCENTRATION")
    if acc is not None and n and n >= 50 and acc >= 0.75:
        flags.append("ACC_GE_75_CHECK_GATES")
    return flags


class SearchEngine:
    def __init__(self, out_dir: Path, *, target_n: int = 100_000):
        self.out_dir = out_dir
        self.target_n = target_n
        self.checkpoint_path = out_dir / "experiment_checkpoint.json"
        self.registry_path = out_dir / "experiment_registry.jsonl.gz"
        self.progress_path = out_dir / "progress_history.jsonl"
        self.seen_path = out_dir / "seen_hashes.txt"

    def load_checkpoint(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {
                "tested": 0,
                "unique": 0,
                "offset": 0,
                "best_val_acc": None,
                "best_val_roi": None,
                "status": "NEW",
            }
        return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))

    def save_checkpoint(self, cp: dict[str, Any]) -> None:
        cp["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.checkpoint_path.write_text(json.dumps(cp, indent=2), encoding="utf-8")

    def run(
        self,
        train: list[MassiveRow],
        val: list[MassiveRow],
        *,
        max_new: int | None = None,
        checkpoint_every: int = 2000,
    ) -> dict[str, Any]:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        cp = self.load_checkpoint()
        tested = int(cp.get("tested") or 0)
        offset = int(cp.get("offset") or 0)
        budget = max_new if max_new is not None else max(0, self.target_n - tested)
        if budget <= 0:
            return {**cp, "status": "TARGET_ALREADY_MET"}

        seen: set[str] = set()
        if self.seen_path.exists():
            seen = {ln.strip() for ln in self.seen_path.read_text(encoding="utf-8").splitlines() if ln.strip()}

        t0 = time.perf_counter()
        new_count = 0
        best_acc = cp.get("best_val_acc")
        best_roi = cp.get("best_val_roi")
        best_acc_row = cp.get("best_val_acc_row")
        best_roi_row = cp.get("best_val_roi_row")

        # skip offset configs
        gen = iter_search_space(self.target_n + 500_000)
        for _ in range(offset):
            try:
                next(gen)
            except StopIteration:
                break

        mode = "ab" if self.registry_path.exists() else "wb"
        with gzip.open(self.registry_path, mode) as reg_fh, self.seen_path.open("a", encoding="utf-8") as seen_fh:
            while new_count < budget:
                try:
                    cfg = next(gen)
                except StopIteration:
                    break
                offset += 1
                h = cfg_hash(cfg.to_dict())
                if h in seen:
                    continue
                seen.add(h)
                seen_fh.write(h + "\n")
                tr = apply_rule(train, cfg)
                va = apply_rule(val, cfg)
                if not va and not tr:
                    continue
                tm = evaluate_bets(tr, len(train))
                vm = evaluate_bets(va, len(val))
                row = {
                    "config_hash": h,
                    "config": cfg.to_dict(),
                    "train": tm,
                    "validation": vm,
                    "holdout": "SEALED_UNOPENED",
                }
                reg_fh.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
                tested += 1
                new_count += 1
                acc = vm.get("accuracy")
                roi = vm.get("roi")
                n = vm.get("n") or 0
                if acc is not None and n >= 10 and (best_acc is None or acc > best_acc):
                    best_acc = acc
                    best_acc_row = {"config_hash": h, "validation": vm, "config": cfg.to_dict()}
                if roi is not None and n >= 10 and (best_roi is None or roi > best_roi):
                    best_roi = roi
                    best_roi_row = {"config_hash": h, "validation": vm, "config": cfg.to_dict()}

                if new_count % checkpoint_every == 0:
                    elapsed = time.perf_counter() - t0
                    rate = new_count / elapsed if elapsed else 0
                    cp = {
                        "tested": tested,
                        "unique": tested,
                        "offset": offset,
                        "best_val_acc": best_acc,
                        "best_val_roi": best_roi,
                        "best_val_acc_row": best_acc_row,
                        "best_val_roi_row": best_roi_row,
                        "status": "RUNNING",
                        "rate_cfg_per_sec": round(rate, 2),
                        "target_n": self.target_n,
                    }
                    self.save_checkpoint(cp)
                    with self.progress_path.open("a", encoding="utf-8") as pf:
                        pf.write(
                            json.dumps(
                                {
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                    "tested": tested,
                                    "new_in_session": new_count,
                                    "rate": round(rate, 2),
                                    "best_val_acc": best_acc,
                                    "best_val_roi": best_roi,
                                }
                            )
                            + "\n"
                        )

        elapsed = time.perf_counter() - t0
        rate = new_count / elapsed if elapsed else 0
        cp = {
            "tested": tested,
            "unique": tested,
            "offset": offset,
            "best_val_acc": best_acc,
            "best_val_roi": best_roi,
            "best_val_acc_row": best_acc_row,
            "best_val_roi_row": best_roi_row,
            "status": "COMPLETE_SESSION" if tested >= self.target_n else "PARTIAL_SESSION",
            "rate_cfg_per_sec": round(rate, 2),
            "session_elapsed_sec": round(elapsed, 3),
            "session_new": new_count,
            "target_n": self.target_n,
        }
        self.save_checkpoint(cp)
        with self.progress_path.open("a", encoding="utf-8") as pf:
            pf.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **cp}) + "\n")
        return cp
