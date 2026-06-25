#!/usr/bin/env python3
"""Re-probe cached Phase 54F-3 fixture payloads after parser fixes (0 API calls)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f3_xg_discovery"
RAW_DIR = ARTIFACT_DIR / "raw"
PROBES_PATH = ARTIFACT_DIR / "fixture_probes.json"
DISCOVERY_PATH = ARTIFACT_DIR / "discovery_result.json"


def main() -> int:
    from worldcup_predictor.feature_store.xg_discovery.coverage_matrix import build_coverage_matrix
    from worldcup_predictor.feature_store.xg_discovery.fixture_probe import probe_fixture_payload

    if not DISCOVERY_PATH.is_file():
        print("missing discovery_result.json")
        return 1

    discovery = json.loads(DISCOVERY_PATH.read_text(encoding="utf-8"))
    probes_doc = json.loads(PROBES_PATH.read_text(encoding="utf-8")) if PROBES_PATH.is_file() else []
    season_sample_ids: dict[tuple[str, int], list[int]] = {}
    for block in probes_doc:
        key = (str(block.get("league_key")), int(block.get("season_id") or 0))
        season_sample_ids[key] = [int(p.get("fixture_id") or 0) for p in block.get("probes") or [] if p.get("fixture_id")]
    fixture_to_probe: dict[int, dict] = {}
    for path in RAW_DIR.glob("fixtures_*_*.json"):
        m = re.match(r"fixtures_(\d+)_", path.name)
        if not m:
            continue
        fid = int(m.group(1))
        blob = json.loads(path.read_text(encoding="utf-8"))
        payload = blob.get("payload")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            continue
        probe = probe_fixture_payload(data)
        probe["fixture_id"] = fid
        fixture_to_probe[fid] = probe

    season_rows_out = []
    for row in discovery.get("season_audits") or []:
        key = (str(row.get("league_key")), int(row.get("season_id") or 0))
        sample_ids = season_sample_ids.get(key, [])
        probes = [fixture_to_probe[fid] for fid in sample_ids if fid in fixture_to_probe]
        for p in probes:
            p["fixture_id"] = p.get("fixture_id") or sample_ids[probes.index(p)]
        sample_with_xg = sum(1 for p in probes if p.get("has_team_xg"))
        sampled = len(probes)
        total = int(row.get("total_fixtures") or 0)
        extrapolated = int(round((sample_with_xg / sampled) * total)) if sampled and total else 0
        season_rows_out.append(
            {
                **row,
                "fixtures_sampled": sampled,
                "sample_with_xg": sample_with_xg,
                "fixtures_with_xg": extrapolated,
                "team_xg_count": sum(1 for p in probes if p.get("has_team_xg")),
                "player_xg_count": sum(1 for p in probes if p.get("has_player_xg")),
                "xgot_count": sum(1 for p in probes if p.get("has_team_xgot")),
                "coverage_pct": round(100.0 * extrapolated / total, 2) if total else None,
            }
        )

    matrix = build_coverage_matrix(season_rows_out)
    discovery["season_audits"] = [{k: v for k, v in r.items() if k != "probes"} for r in season_rows_out]
    discovery["XG_COVERAGE_MATRIX"] = matrix
    discovery["parser_replay"] = {
        "fixtures_reprobed": len(fixture_to_probe),
        "sample_with_xg_total": sum(int(r.get("sample_with_xg") or 0) for r in season_rows_out),
        "sample_total": sum(int(r.get("fixtures_sampled") or 0) for r in season_rows_out),
    }

    total_fixtures = sum(int(r.get("fixtures") or 0) for r in matrix)
    est_xg = sum(int(r.get("fixtures_with_xg") or 0) for r in matrix)
    sampled = discovery["parser_replay"]["sample_total"]
    with_xg = discovery["parser_replay"]["sample_with_xg_total"]
    api_rate = with_xg / sampled if sampled else 0

    discovery["root_cause_analysis"] = {
        **(discovery.get("root_cause_analysis") or {}),
        "api_sample_xg_rate_corrected": round(api_rate, 4),
        "primary_causes": ["B", "E"] if api_rate > 0.5 else ["A", "B", "E"],
        "cause_labels": [
            "Our importer/parser missed available xG (lowercase xgfixture list)",
            "Wrong include/parser configuration",
        ],
        "evidence": [
            f"Corrected API sample xG rate {api_rate:.1%} from {len(fixture_to_probe)} cached fixture pulls",
            "Raw payloads contain type_id 5304 in xgfixture[] but pre-fix parser returned expected_row_count=0",
        ],
    }
    discovery["summary"] = {
        "total_fixtures_estimated": total_fixtures,
        "fixtures_with_xg_estimated": est_xg,
        "overall_coverage_pct_estimated": round(100.0 * est_xg / total_fixtures, 2) if total_fixtures else 0.0,
        "api_sample_xg_rate_corrected": round(api_rate, 4),
        "fixtures_reprobed": len(fixture_to_probe),
    }
    discovery["api_capability"] = {
        "historical_xg_retrievable": "YES" if api_rate >= 0.5 else "PARTIAL" if api_rate > 0 else "NO",
        "league_wide_xg": "PARTIAL",
        "season_wide_xg": "YES",
        "fixture_level_xg": "YES" if api_rate > 0 else "NO",
        "player_xg_retrievable": "PARTIAL",
    }

    DISCOVERY_PATH.write_text(json.dumps(discovery, indent=2, default=str), encoding="utf-8")
    (ARTIFACT_DIR / "XG_COVERAGE_MATRIX.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    probes_out = [
        {
            "season_id": r.get("season_id"),
            "league_key": r.get("league_key"),
            "probes": [fixture_to_probe[fid] for fid in season_sample_ids.get((str(r.get("league_key")), int(r.get("season_id") or 0)), []) if fid in fixture_to_probe],
        }
        for r in season_rows_out
    ]
    PROBES_PATH.write_text(json.dumps(probes_out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(discovery["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
