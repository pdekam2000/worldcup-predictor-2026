# PHASE OA-4 — Deep Endpoint Traversal Audit

**Generated:** 2026-06-23T16:48:02.062302+00:00  
**API key fingerprint (sha256/16):** `477361cf28af4afe`  
**API calls:** 1393  
**Fixture endpoint attempts:** 1200  

> This report records measured traversal results only. No early-stop on zero rows.

## Season discovery

Seasons retrieved via `GET competitions/{id}?include=seasons` for each target competition.
Raw samples: `artifacts/oa4_raw/competition_*_with_seasons.json`

## Inventory (competition_id × season_id)

| League | Comp ID | Season | Season ID | Finished | Upcoming |
|--------|---------|--------|-----------|----------|----------|
| premier_league | 423 | 2020/2021 | 433 | 0 | 0 |
| premier_league | 423 | 2021/2022 | 1470 | 0 | 0 |
| premier_league | 423 | 2022/2023 | 2747 | 0 | 0 |
| premier_league | 423 | 2023/2024 | 4630 | 0 | 0 |
| premier_league | 423 | 2024/2025 | 6484 | 0 | 0 |
| premier_league | 423 | 2025/2026 | 667780 | 0 | 0 |
| premier_league | 423 | 2019/2020 | 1036978 | 0 | 0 |
| premier_league | 423 | 2026/2027 | 2263973 | 0 | 0 |
| bundesliga | 477 | 2020/2021 | 487 | 0 | 0 |
| bundesliga | 477 | 2021/2022 | 1468 | 0 | 0 |
| bundesliga | 477 | 2022/2023 | 2745 | 0 | 0 |
| bundesliga | 477 | 2023/2024 | 4675 | 0 | 0 |
| bundesliga | 477 | 2024/2025 | 6597 | 0 | 0 |
| bundesliga | 477 | 2025/2026 | 725788 | 0 | 0 |
| bundesliga | 477 | 2019/2020 | 1037054 | 0 | 0 |
| bundesliga | 477 | 2026/2027 | 2305071 | 0 | 0 |
| champions_league | 51 | 2020/2021 | 53 | 0 | 0 |
| champions_league | 51 | 2021/2022 | 1231 | 0 | 0 |
| champions_league | 51 | 2022/2023 | 2465 | 0 | 0 |
| champions_league | 51 | 2023/2024 | 4326 | 0 | 0 |
| champions_league | 51 | 2024/2025 | 6204 | 0 | 0 |
| champions_league | 51 | 2025/2026 | 660539 | 0 | 0 |
| champions_league | 51 | 2019/2020 | 1036973 | 0 | 0 |
| champions_league | 51 | 2026/2027 | 2264045 | 0 | 0 |
| la_liga | 419 | 2020/2021 | 429 | 0 | 0 |
| la_liga | 419 | 2021/2022 | 1248 | 0 | 0 |
| la_liga | 419 | 2022/2023 | 2858 | 0 | 0 |
| la_liga | 419 | 2023/2024 | 4634 | 0 | 0 |
| la_liga | 419 | 2024/2025 | 6435 | 0 | 0 |
| la_liga | 419 | 2025/2026 | 762170 | 0 | 0 |
| la_liga | 419 | 2019/2020 | 1037107 | 0 | 0 |
| la_liga | 419 | 2026/2027 | 2244302 | 0 | 0 |
| serie_a | 499 | 2020/2021 | 509 | 0 | 0 |
| serie_a | 499 | 2021/2022 | 1555 | 0 | 0 |
| serie_a | 499 | 2022/2023 | 2894 | 0 | 0 |
| serie_a | 499 | 2023/2024 | 4724 | 0 | 0 |
| serie_a | 499 | 2024/2025 | 6526 | 0 | 0 |
| serie_a | 499 | 2025/2026 | 602681 | 0 | 0 |
| serie_a | 499 | 2019/2020 | 1037181 | 0 | 0 |
| serie_a | 499 | 2026/2027 | 2224807 | 0 | 0 |

## Endpoint traversal

- Full traversal log: `artifacts/oa4_raw/oa4_full_traversal_log.json`
- Proof bundle: `artifacts/oa4_endpoint_traversal_proof.json`
- Raw samples: `artifacts/oa4_raw/`

## Derivative tests (when fixture_id available)

- **world_cup_proof** fixture `420562876`: odds/history rows=320, movement=0, probability error=non_json_response

## Artifacts

- `artifacts/oa4_token_capabilities.json`
- `artifacts/oa4_league_access.json`
- `artifacts/oa4_historical_depth.json`
- `artifacts/oa4_odds_history_coverage.json`
- `artifacts/oa4_bookmaker_coverage.json`
- `artifacts/oa4_first_goal_markets.json`
- `artifacts/oa4_backfill_readiness.json`
- `artifacts/oa4_provider_comparison.json`
- `artifacts/oa4_endpoint_traversal_proof.json`

---

**STOP — Audit only. Facts in JSON artifacts.**
