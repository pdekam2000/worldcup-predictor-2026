# Provider Field Inventory — Phase 46D

Audit of API-Football and Sportmonks fields: availability, current usage, and gaps.

**Legend:** ✅ Used · ⚠️ Partial · ❌ Unused · 📦 Cached only

---

## API-Football

| Domain | Field / Endpoint | Available | Status | Used By |
|--------|------------------|-----------|--------|---------|
| **Fixtures** | `fixtures` (by id, season, live) | ✅ | ✅ | `ApiFootballClient`, `MatchIntelligenceBuilder`, schedule |
| | `fixture.status`, `score` (FT/HT) | ✅ | ✅ | Outcome resolver, result refresh |
| | `fixture.venue`, `referee` | ✅ | ⚠️ | Referee agent (partial) |
| **Events** | `fixtures/events` — goals | ✅ | ✅ | Outcome persistence (46C-1), evaluation |
| | `fixtures/events` — cards | ✅ | ⚠️ | **46D** unified event layer |
| | `fixtures/events` — substitutions | ✅ | ⚠️ | **46D** unified event layer |
| | `fixtures/events` — assists | ✅ | ⚠️ | Goal events only (46C-1) |
| **Lineups** | `fixtures/lineups` startXI | ✅ | ✅ | Lineup agents, player intelligence (46D) |
| | formation, coach | ✅ | ⚠️ | Tactics agent |
| **Injuries** | `injuries` | ✅ | ✅ | Injury agents, player availability (46D) |
| **Standings** | `standings` | ✅ | ✅ | Tournament context, schedule |
| **Statistics** | `fixtures/statistics` | ✅ | ✅ | Tactics, xG chance quality agents |
| | team stats (season) | ✅ | ✅ | `get_team_statistics`, form |
| **Odds** | `odds` bookmakers | ✅ | ✅ | Odds agents, snapshots, movement (46D) |
| **H2H** | `fixtures/headtohead` | ✅ | ✅ | Intelligence builder |
| **Players** | `fixtures/players` | ✅ | ⚠️ | Player quality (partial) |
| | top scorers / squads | ✅ | ❌ | Not in WC pipeline |
| **Teams** | team id, name, logo | ✅ | ✅ | Throughout |
| **Predictions** | `predictions` endpoint | ✅ | ❌ | Not primary (internal engine) |

---

## Sportmonks

| Domain | Field / Include | Available | Status | Used By |
|--------|-----------------|-----------|--------|---------|
| **Scores** | `scores` (FT/HT) | ✅ | ⚠️ | Consumption map; **46D** fusion fallback |
| **State** | `state` (period, finished) | ✅ | ⚠️ | Normalization metadata |
| **Events** | `events` include | ✅ | ⚠️ | **46D** unified event layer (gap-fill) |
| **xG** | `xGFixture` / statistics xG | ✅ | ✅ | XG intelligence agent, **46D** AdvancedMatchIntelligence |
| **Advanced statistics** | shots, possession, etc. | ✅ | ⚠️ | Tactics via consumption; **46D** efficiency metrics |
| **Player data** | lineups, sidelined | ✅ | ⚠️ | Enrichment cache |
| **Timelines** | event ordering | ✅ | ⚠️ | Merged in unified events |
| **Odds** | premium odds | ✅ | ✅ | Sportmonks odds prediction agent |
| **Predictions** | SM predictions | ✅ | ✅ | Sportmonks prediction agent (benchmark) |
| **Standings** | standings include | ✅ | ✅ | Standings enrichment |

---

## Gap Summary (pre-46D → post-46D)

| Gap | 46D Action |
|-----|------------|
| Cards/subs not in evaluation analytics | Unified event layer + SQLite `fixture_unified_events` |
| Sportmonks events unused | Sportmonks event parser + fusion |
| Odds movement underutilized | `odds_movement_intelligence` → specialists supplemental |
| xG not aggregated for analytics | `AdvancedMatchIntelligence` bundle |
| Player form fragmented | `PlayerIntelligence` from lineups + events + injuries |
| No fusion policy | `PROVIDER_FUSION_POLICY.md` + `provider_fusion.py` |

---

## Storage

| Table / Key | Content |
|-------------|---------|
| `fixture_goal_events` | Goals only (46C-1 evaluation) |
| `fixture_unified_events` | Full event taxonomy (46D) |
| `supplemental_sources.provider_utilization_v1` | Runtime bundle on intelligence report |
| `sportmonks_fixture_enrichment` | Cached SM fixture payload |

**Updated:** Phase 46D audit — extend-only; no fake data.
