#!/usr/bin/env python3
import json
import urllib.request

base = "http://127.0.0.1:8000"
fids = [1489409, 1489410, 1489412, 1489411, 1489416]
for fid in fids:
    try:
        p = json.loads(urllib.request.urlopen(f"{base}/api/predict/{fid}", timeout=15).read())
    except Exception as e:
        print(fid, "ERR", e)
        continue
    o = p.get("publication_overlay") or {}
    checks = {
        "expected_odds": p.get("expected_odds"),
        "value_rating": p.get("value_rating"),
        "public_best_pick": o.get("public_best_pick"),
        "prediction": p.get("prediction"),
        "best_available_pick": p.get("best_available_pick"),
        "caution_label": o.get("caution_label"),
    }
    bad = {k: type(v).__name__ for k, v in checks.items() if isinstance(v, (dict, list))}
    for i, b in enumerate(p.get("recommended_bets") or []):
        if isinstance(b, dict):
            for kk in ("pick", "selection", "market"):
                if isinstance(b.get(kk), dict):
                    bad[f"recommended_bets[{i}].{kk}"] = "dict"
    print(fid, bad or "ok", "expected_odds", checks.get("expected_odds"))
