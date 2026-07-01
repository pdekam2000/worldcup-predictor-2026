# ECSE OddAlerts Owner Lab Report

**Phase:** ECSE-ODDALERTS-3  
**Generated:** validation run  
**Mode:** Owner/internal lab — no production ECSE writes

---

## Paths

| Layer | Path |
|-------|------|
| API | `GET /api/owner/ecse-oddalerts-shadow` |
| UI | `/owner/ecse-oddalerts-shadow` |
| Segment module | `worldcup_predictor/research/oddalerts_ecse_segments.py` |
| Lab service | `worldcup_predictor/owner/oddalerts_ecse_lab_service.py` |

---

## Segment rules (initial)

- Prefer **inserted** over enriched snapshots
- Boost competitions with higher historical Top-1 (Bundesliga, PL)
- Penalize **World Cup 2026** until sample improves
- Prefer bookmaker implied 1X2 agreement with shadow top-1 outcome
- Prefer sane lambda mid-ranges; penalize extremes
- Prefer high crosswalk confidence
- Penalize 1-1 top-1 without draw market support
- Caution on WDE disagreement and market inconsistency

---

## Counts by badge

```json
{
  "MEDIUM_SHADOW_SIGNAL": 117,
  "WEAK_SHADOW_SIGNAL": 48,
  "STRONG_SHADOW_SIGNAL": 32
}
```

## Best segments

- **Inserted + Bundesliga + bookmaker agreement** — strongest evaluated Top-1 prior
- **Strong badge + inserted** — eligible for limited write later (watch World Cup)

## Weak segments

- **World Cup 2026** — 6.8% Top-1 in shadow eval
- **DO_NOT_USE / WATCH_ONLY** — extreme lambda, low crosswalk, market inconsistency

---

## Validation

- [pass] owner_endpoint_module_exists
- [pass] owner_endpoint_path
- [pass] main_router_registered
- [pass] ui_route_registered
- [pass] ui_page_exists
- [pass] ui_owner_guard
- [pass] owner_nav_entry
- [pass] owner_api_helper
- [pass] owner_warning_copy
- [pass] no_public_shadow_route_predictions
- [pass] no_public_shadow_route_ecse_display
- [pass] owner_api_unauth_401
- [pass] owner_non_owner_403
- [pass] owner_allowed_200
- [pass] response_has_segment_scores
- [pass] shadow_table_has_records
- [pass] no_ecse_production_writes
- [pass] no_wde_writes
- [pass] no_odds_snapshot_writes
- [pass] segment_scores_generated
- [pass] source_trace_available
- [pass] segment_module_scores
- [pass] evaluation_stats_match_artifact
- [pass] owner_lab_json_exists
- [pass] owner_lab_md_exists
- [pass] targeted_reads_only
- [pass] report_exists

Passed: **27** / **27**

---

## Final recommendation

`READY_FOR_OWNER_LAB_REVIEW`
