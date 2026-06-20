# Phase 27 — Post-Deploy Audit

**Mode:** Audit only — no code changes  
**Project:** WorldCup Predictor 2026  
**Date:** 2026-06-20  
**Deploy:** Hetzner, commit `1556fc0` (backend confirmed)  
**Symptom:** Specialist Analysis page shows only legacy agents; Phase 22 agents appear missing

---

## Executive Summary

The four Phase 22 specialist agents **do execute on production** and **do appear in fresh API responses**. They **do not disappear in backend code** — they disappear in the UI when the browser loads a **stale pre-deploy prediction cache** that was serialized before orchestrator expansion (18 agents vs 22 today).

| Layer | Verdict | Where agents drop |
|-------|---------|-------------------|
| Pipeline | **PASS** | Nowhere — all four run |
| Orchestrator | **PASS** | Nowhere — all four in `report.signals` |
| Audit trace (internal) | **PASS (internal only)** | Dropped at API boundary — never serialized |
| API serializer | **PASS on live run** / **FAIL on stale cache** | Stale `.cache/predictions/` payloads |
| Frontend rendering | **PASS (no filter)** | Reflects stale API payload; no audit-trace UI |

**Primary root cause:** Cached prediction payloads generated **before** Phase 22–26 deploy contain `specialist_summary.agents` with **18 keys** (legacy orchestrator). Fresh runs produce **22 keys** including all four Phase 22 agents.

**Secondary gaps:** Audit trace and promotion fields exist in `MatchPrediction.audit_report` but are **not exposed** in `/api/predict/*` and **not rendered** in React.

---

## Production Evidence (2026-06-20)

### Server state

| Check | Result |
|-------|--------|
| Git HEAD on server | `1556fc0` — Phase 22–26 bundle |
| API health | `GET /api/health` → `{"status":"ok"}` |
| Frontend static build | `/var/www/worldcup/frontend/dist/index.html` modified **2026-06-19** (pre-backend deploy) |
| Agent imports on server | Confirmed OK (user report) |

### Orchestrator live run (`scripts/audit_specialists_server.py`)

Fixture **1539007** (Netherlands vs Sweden):

| Agent | Status | Notes |
|-------|--------|-------|
| `expected_lineup_agent` | **available** | Expected XI benchmark active |
| `tournament_context_agent` | **available** | Sportmonks standings supplemental |
| `sportmonks_prediction_agent` | unavailable | Sportmonks odds/prediction not in fixture payload |
| `xg_intelligence_agent` | unavailable | Sportmonks xG not in fixture payload |

All four agents **executed** and registered signals in `specialist_signals` / `MatchSpecialistReport.signals`.

### API live run (`scripts/audit_phase5_fixture.py` against production)

Fixture **1539007**, `POST /api/predict/1539007`:

```
agent_count: 22
expected_lineup_agent:        status=available   impact=84.0
tournament_context_agent:     status=available   impact=82.0
sportmonks_prediction_agent:  status=unavailable impact=50.0
xg_intelligence_agent:        status=unavailable impact=0.0
```

`GET /api/predict/1539007` after live run returns the same 22-agent payload from cache.

### Stale cache comparison

Production files under `/opt/worldcup-predictor/.cache/predictions/`:

| Cache file | Fixture | Agent count | Phase 22 agents |
|------------|---------|-------------|-----------------|
| `8a14ac60…json` | 1539007 | **22** | All four present (2 available, 2 unavailable) |
| `df81c5ef…json` | 1489388 | **18** | **All four MISSING** |
| `fded4e16…json` | 1489390 | **18** | **All four MISSING** |
| `1ba15b37…json` | 123 | **0** | Empty/broken payload |

The 18-agent stale payloads contain exactly the pre–Phase 22 orchestrator set:

```
elo_team_strength_intelligence_agent, injury_suspension_agent,
injury_suspension_intelligence_agent, lineup_agent, lineup_intelligence_agent,
market_consensus_agent, motivation_psychology_agent, odds_control_agent,
odds_market_agent, odds_movement_agent, player_quality_agent, referee_agent,
sharp_money_intelligence_agent, tactics_agent, team_form_agent,
tournament_intelligence_agent, weather_agent, xg_chance_quality_intelligence_agent
```

Missing keys (the four Phase 22 agents):

- `expected_lineup_agent`
- `tournament_context_agent`
- `xg_intelligence_agent`
- `sportmonks_prediction_agent`

**22 − 4 = 18** — matches pre-deploy orchestrator cardinality.

---

## Layer 1 — Pipeline

**Path:** `PredictPipeline.run()` → `DataCollectorAgent` → `SpecialistOrchestrator` → `PredictionAgent`

```55:57:worldcup_predictor/orchestration/predict_pipeline.py
        specialist = SpecialistOrchestrator(context)
        specialist_result = specialist.run(fixture_id=fixture_id)
        results.append(specialist_result)
```

**Finding:** **PASS.** All four agents are registered in `SpecialistOrchestrator.AGENT_CLASSES` and run on every prediction.

```48:71:worldcup_predictor/agents/specialists/orchestrator.py
    AGENT_CLASSES = (
        WeatherAgent,
        ...
        ExpectedLineupAgent,
        ...
        SportmonksPredictionAgent,
        XGIntelligenceAgent,
        ...
        TournamentContextAgent,
        MasterAnalysisAgent,
    )
```

Each agent writes to `context.shared["specialist_signals"][agent.name]` on success.

---

## Layer 2 — Orchestrator Output

**Path:** `SpecialistOrchestrator.run()` → per-agent `run()` → `MasterAnalysisAgent.run()` → `MatchSpecialistReport`

**Finding:** **PASS.** Master synthesis includes all four agents in `SPECIALIST_NAMES` and applies trace-only conflict/adjustment logic for each:

```882:905:worldcup_predictor/agents/specialists/agents.py
    SPECIALIST_NAMES = (
        ...
        "expected_lineup_agent",
        ...
        "sportmonks_prediction_agent",
        "xg_intelligence_agent",
        ...
        "tournament_context_agent",
    )
```

Final report includes every specialist signal except master:

```1161:1164:worldcup_predictor/agents/specialists/agents.py
        report_obj = MatchSpecialistReport(
            fixture_id=fid,
            signals={k: v for k, v in signals.items() if k != self.name},
            master=master,
```

Production orchestrator audit confirms all four keys present in `spec_report.signals`.

---

## Layer 3 — Prediction Audit Trace

**Path:** `ScoringEngine` → `WeightedDecisionEngine.decide()` → `PredictionAuditReport` + `FinalDecisionTrace`

**Finding:** **PASS internally / FAIL at API export.**

Trace fields for Phase 24 promotions exist on `FinalDecisionTrace`:

- `lineup_promotion_*`, `expected_vs_confirmed_history` (24A / ExpectedLineup)
- `context_promotion_*`, `must_win_influence`, `draw_acceptability_influence` (24B / TournamentContext)
- `xg_promotion_*` (24C / XG)
- `sportmonks_promotion_*`, `sportmonks_no_bet_review_trace` (24C / Sportmonks)

MasterAnalysisAgent also emits trace strings when these signals disagree (e.g. Sportmonks benchmark conflict, expected lineup divergence, tournament context vs motivation).

**Drop point:** `_success_payload()` in `worldcup_predictor/api/routes/predictions.py` serializes prediction fields and `specialist_summary` only. It does **not** include `prediction.audit_report` or `FinalDecisionTrace`.

Production check: `audit_report_in_api: False` for live fixture 1539007.

The React Specialist Analysis page has **no audit-trace section** — even a fresh prediction would not show WDE promotion trace in the UI.

---

## Layer 4 — API Serializer

**Path:** `PredictPipelineResult` → `_specialist_summary()` → `store_prediction()` / `get_cached_prediction()`

```103:128:worldcup_predictor/api/routes/predictions.py
def _specialist_summary(
    result: PredictPipelineResult,
    prediction: MatchPrediction,
) -> dict[str, Any]:
    ...
    if report is not None:
        agents: dict[str, Any] = {}
        for name, signal in report.signals.items():
            agents[name] = {
                "domain": signal.domain,
                "status": signal.status,
                "status_reason": signal.status_reason,
                "impact_score": signal.impact_score,
            }
        return {
            "aggregated_score": report.aggregated_signal_score,
            "source": report.source,
            "agents": agents,
        }
```

**Finding:**

| Scenario | Verdict |
|----------|---------|
| Fresh `POST /api/predict/{id}` after deploy | **PASS** — all 22 agents, including four Phase 22 keys |
| `GET /api/predict/{id}` serving pre-deploy cache | **FAIL** — 18 agents, four Phase 22 keys absent |
| Fallback when orchestrator report missing | **FAIL** — returns `{aggregated_score}` only, **no `agents` dict** |

There is **no agent whitelist** and **no serializer filter** removing Phase 22 agents. The serializer faithfully exports whatever is in `MatchSpecialistReport.signals` at run time.

**Cache behavior:** `GET /api/predict/{id}` returns stored JSON without re-running the pipeline. Users who opened predictions before deploy (or fixtures with old cache files) receive legacy 18-agent payloads until **force refresh** or cache TTL expiry + new run.

---

## Layer 5 — Frontend Rendering

**Path:** `fetchCachedPrediction` / `runPrediction` → `PredictionDetail.jsx` → Specialist Analysis grid

```199:205:base44-d/src/pages/PredictionDetail.jsx
  const specialists = Object.entries(result?.specialist_summary?.agents ?? {}).map(([name, agent]) => ({
    name,
    domain: agent?.domain ?? "—",
    status: agent?.status ?? "—",
    status_reason: agent?.status_reason ?? null,
    impact_score: agent?.impact_score,
  }));
```

```343:384:base44-d/src/pages/PredictionDetail.jsx
      {specialists.length > 0 && (
        ...
            {specialists.map((s, i) => {
              const Icon = specialistIcons[s.name] || Brain;
```

**Finding:** **PASS — no agent filter.** Every key in `specialist_summary.agents` renders as a card.

**UX gaps (not visibility blockers):**

| Gap | Detail |
|-----|--------|
| Labels/icons | `specialistLabels` / `specialistIcons` only define 10 legacy short keys (`form`, `injury`, `lineup`, …). Phase 22 agents use fallback title case (`Expected Lineup Agent`) and generic `Brain` icon. |
| Audit trace | No component reads `audit_report` — field not in API anyway. |
| Frontend deploy lag | Static bundle at `/var/www/worldcup/frontend/dist` dated **2026-06-19**; backend at **1556fc0** dated **2026-06-20**. Current JSX already renders dynamic agent lists, so this lag is **not** the primary cause of missing agents. |

**Observed user symptom explained:** Viewing fixture **1489388** or **1489390** (or any fixture with pre-deploy cache) shows **18 legacy cards** because the API returns 18 agents — not because React filters Phase 22 agents out.

After **Run Prediction** / refresh on fixture **1539007**, production API returns 22 cards including Expected Lineup and Tournament Context.

---

## Agent-by-Agent Status (Production, fixture 1539007)

| Agent | Executes | In orchestrator report | In fresh API | In stale 18-agent cache | In UI (fresh) | In audit trace (internal) |
|-------|----------|------------------------|--------------|-------------------------|---------------|----------------------------|
| ExpectedLineupAgent | Yes | Yes | Yes (`available`) | **No** | Yes | Yes (Master + WDE lineup promotion fields) |
| TournamentContextAgent | Yes | Yes | Yes (`available`) | **No** | Yes | Yes (Master + WDE context promotion fields) |
| XGIntelligenceAgent | Yes | Yes | Yes (`unavailable`) | **No** | Yes (card shows unavailable) | Yes (Master xG divergence notes; WDE xG promotion fields) |
| SportmonksPredictionAgent | Yes | Yes | Yes (`unavailable`) | **No** | Yes (card shows unavailable) | Yes (Master SM benchmark notes; WDE sportmonks promotion fields) |

**Note:** `unavailable` still appears in API and UI as a specialist card. User perception of “missing” for Sportmonks/xG may conflate **data unavailable** with **agent absent** — on fresh runs the agents are present with `status=unavailable`.

---

## Data Availability Note (Sportmonks)

On production fixture 1539007:

- `sportmonks_prediction_agent` → unavailable (Sportmonks odds/prediction not in fixture payload)
- `xg_intelligence_agent` → unavailable (Sportmonks xG not in payload; xG add-on / include gap)

Orchestrator audit with `.env.production` loaded reported `Sportmonks configured: True`, but `audit_phase5_fixture.py` reported `sportmonks_configured: False` when run without explicit production env — environment loading context matters for supplemental data, not for agent registration.

---

## Disappearance Map

```
[Pipeline]  DataCollector → SpecialistOrchestrator (22 agents run)
                ↓ PASS — all 4 Phase 22 agents execute
[Orchestrator] specialist_signals → MasterAnalysisAgent → MatchSpecialistReport.signals (22 keys)
                ↓ PASS
[Audit trace]  WDE FinalDecisionTrace + Master conflicts/adjustments
                ↓ DROP — not serialized to API; not in React
[API]          _specialist_summary(report.signals) → JSON specialist_summary.agents
                ↓ PASS on fresh run (22 keys)
                ↓ DROP on stale pre-deploy cache (18 keys) ← PRIMARY UI SYMPTOM
[Frontend]     Object.entries(specialist_summary.agents) → Specialist Analysis cards
                ↓ PASS (renders all keys returned by API)
                ↓ UX gap: no dedicated labels/icons for Phase 22 agent names
```

---

## Conclusions

1. **Backend deploy is correct.** Commit `1556fc0` runs all four Phase 22 agents; orchestrator and fresh API output include them.
2. **The UI “missing agents” symptom is explained by stale prediction cache**, not by a broken orchestrator or frontend filter. Pre-deploy cache entries have exactly 18 legacy agent keys.
3. **Audit trace is invisible end-to-end** in the SaaS API and React app despite being populated internally during WDE.
4. **Sportmonks xG and Sportmonks prediction agents run but often report `unavailable`** due to supplemental payload gaps — distinct from “not in UI.”
5. **Frontend rebuild is recommended** for label/icon polish and any future audit-trace panel, but is **not required** to display Phase 22 agents once cache is refreshed.

---

## Recommended Next Steps (post-audit — not implemented)

| Priority | Action |
|----------|--------|
| P0 | Invalidate or bump prediction cache schema after orchestrator changes; force-refresh high-traffic fixtures post-deploy |
| P1 | Add Phase 22 agent keys to `specialistLabels` / `specialistIcons` in `PredictionDetail.jsx` |
| P2 | Expose `audit_report.trace` (or subset) on `/api/predict/{id}` or dedicated audit endpoint |
| P3 | Investigate Sportmonks xG / odds-prediction includes on production enrichment path |
| P4 | Rebuild and rsync frontend (`npm run build` → `/var/www/worldcup/frontend/dist/`) to align static deploy with backend |

---

## Audit Commands Used

```bash
# Orchestrator agent statuses (production)
bash /opt/worldcup-predictor/scripts/audit_specialists_server.py

# API specialist_summary enumeration
python scripts/audit_phase5_fixture.py http://127.0.0.1:8000 1539007

# Cache file agent counts
python scripts/_phase27_cache_probe.py /opt/worldcup-predictor/.cache/predictions
```

---

*End of Phase 27 post-deploy audit. No code changes were made.*
