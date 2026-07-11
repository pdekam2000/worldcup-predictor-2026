#!/usr/bin/env python3
"""Extract ECSE Top1-Top5 for best 3 model picks from stored payload."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TARGET_IDS = (1494695, 1494204, 1494205)
PAYLOAD = ROOT / "artifacts" / "domestic_league_control_20260712_payload.json"
OUT_JSON = ROOT / "artifacts" / "model_only_best3_exact_score_top5_20260712.json"
OUT_MD = ROOT / "BEST_3_EXACT_SCORE_TOP5_MODEL_OUTPUT_2026_07_12.md"
SOURCE_PROD = "/opt/worldcup-predictor/artifacts/domestic_league_control_20260712/payload.json"


def _mass(items: list[dict]) -> float | None:
    if not items:
        return None
    return round(sum(float(x.get("probability") or 0) for x in items), 2)


def _extract_match(m: dict) -> dict:
    fx = m["fixture"]
    wde = m["wde"]
    ecse = m["ecse"]
    top5_list = ecse.get("top5") or []
    top3_list = ecse.get("top3_list") or top5_list[:3]
    ranks = {}
    for key in ("top1", "top2", "top3"):
        src = ecse.get(key)
        if isinstance(src, dict):
            ranks[key] = {"scoreline": src["scoreline"], "probability_pct": src["probability"]}
    for key, idx in (("top4", 3), ("top5", 4)):
        if len(top5_list) > idx and isinstance(top5_list[idx], dict):
            src = top5_list[idx]
            ranks[key] = {"scoreline": src["scoreline"], "probability_pct": src["probability"]}
    wde_end = (wde.get("predicted_1x2") or "").replace("_win", "").upper()
    if wde_end == "HOME":
        wde_end = "HOME"
    elif wde_end == "AWAY":
        wde_end = "AWAY"
    elif wde_end == "DRAW":
        wde_end = "DRAW"
    return {
        "fixture_id": fx["fixture_id"],
        "match": f"{fx['home_team']} vs {fx['away_team']}",
        "kickoff_vienna": fx.get("kickoff_vienna"),
        "kickoff_utc": fx.get("kickoff_utc"),
        "competition": fx.get("competition_name"),
        "competition_key": fx.get("competition_key"),
        "wde_end_result": wde_end,
        "had_pct": {
            "home": wde.get("home_prob"),
            "draw": wde.get("draw_prob"),
            "away": wde.get("away_prob"),
        },
        "ecse_top1_top5": ranks,
        "top3_mass_pct": _mass(top3_list),
        "top5_mass_pct": _mass(top5_list[:5]),
        "entropy": ecse.get("entropy"),
        "consistency": m.get("consistency"),
        "data_quality": {
            "bookmaker_count": (m.get("data_readiness") or {}).get("bookmaker_count"),
            "odds_freshness": (m.get("data_readiness") or {}).get("odds_freshness"),
            "quality_downgrade": (m.get("data_readiness") or {}).get("quality_downgrade"),
            "owner_label": m.get("owner_label"),
        },
        "source_payload": SOURCE_PROD,
    }


def main() -> int:
    data = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    by_id = {m["fixture"]["fixture_id"]: m for m in data.get("matches", [])}
    picks = []
    for fid in TARGET_IDS:
        if fid not in by_id:
            print(json.dumps({"error": f"missing fixture {fid}"}))
            return 1
        picks.append(_extract_match(by_id[fid]))

    out = {
        "phase": "BEST3_EXACT_SCORE_TOP5_EXTRACTION",
        "generated_from": str(PAYLOAD),
        "production_source": SOURCE_PROD,
        "policy": "model_only_wde_ecse",
        "picks": picks,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Best 3 Exact Score Top5 — Model Output",
        "",
        f"**Source:** `{SOURCE_PROD}`",
        "**Policy:** WDE + ECSE only (no odds-only prediction)",
        "",
    ]
    labels = [
        ("AWAY", "برد مهمان — Bodø/Glimt"),
        ("HOME", "برد میزبان — Hammarby"),
        ("HOME", "برد میزبان — Malmö"),
    ]
    for i, (pick, (end, fa)) in enumerate(zip(picks, labels), 1):
        t = pick["ecse_top1_top5"]
        lines += [
            f"## {i}) {pick['match']}",
            "",
            f"**Kickoff:** {pick['kickoff_vienna']}",
            f"**Competition:** {pick['competition']} (Tier B)",
            f"**fixture_id:** {pick['fixture_id']}",
            "",
            f"**End Result (WDE):** {end} — {fa}",
            f"**H/D/A:** {pick['had_pct']['home']}% / {pick['had_pct']['draw']}% / {pick['had_pct']['away']}%",
            f"**توافق WDE/ECSE:** {pick['consistency'].get('status')}",
            "",
            "**Exact Score ECSE:**",
            f"- Top1: **{t['top1']['scoreline']}** ({t['top1']['probability_pct']}%)",
            f"- Top2: **{t['top2']['scoreline']}** ({t['top2']['probability_pct']}%)",
            f"- Top3: **{t['top3']['scoreline']}** ({t['top3']['probability_pct']}%)",
            f"- Top4: **{t['top4']['scoreline']}** ({t['top4']['probability_pct']}%)",
            f"- Top5: **{t['top5']['scoreline']}** ({t['top5']['probability_pct']}%)",
            "",
            f"**Top3 Mass:** {pick['top3_mass_pct']}%",
            f"**Top5 Mass:** {pick['top5_mass_pct']}%",
            f"**Entropy:** {pick['entropy'] or 'not stored in payload'}",
            "",
            f"**Risk:** bookmakers={pick['data_quality']['bookmaker_count']} (context only); "
            f"freshness={pick['data_quality']['odds_freshness']}; "
            f"label={pick['data_quality']['owner_label']}; "
            f"agreement={pick['consistency'].get('status')}",
            "",
        ]
    lines.append("**Final status:** `BEST3_EXACT_SCORE_TOP5_EXTRACTED`")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "BEST3_EXACT_SCORE_TOP5_EXTRACTED", "json": str(OUT_JSON), "md": str(OUT_MD)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
