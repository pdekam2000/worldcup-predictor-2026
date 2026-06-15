# Changelog

## Phase 38 — Lineup Intelligence V2

- Added `worldcup_predictor/lineups/` module with structured lineup analysis models and engine.
- Added `LineupIntelligenceAgent` to the specialist pipeline (alongside existing `LineupAgent`).
- Analyzes official/announced XI, substitutes, injuries, goalkeeper status, rotation vs previous match, strength score, risk flags, and safe prediction impact adjustments.
- Integrated into `MasterAnalysisAgent` and `WeightedDecisionEngine` with conservative weighting.
- Streamlit GUI: **Lineup Intelligence V2** card on prediction analysis view.
- CLI: `python main.py lineup-intelligence --fixture-id <id>`

## Phase 39 — Injury & Suspension Intelligence V2

- Added `worldcup_predictor/injuries/` module with player importance, position losses, and team impact scoring.
- Added `InjurySuspensionIntelligenceAgent` alongside existing `InjurySuspensionAgent`.
- Integrated into SpecialistOrchestrator, MasterAnalysisAgent, and WeightedDecisionEngine with conservative weighting.
- Streamlit GUI: **Injury & Suspension Intelligence V2** card on prediction analysis view.
- CLI: `python main.py injury-intelligence --fixture-id <id>`

## Phase 40 — Sharp Money & Odds Movement Intelligence V2

- Added `worldcup_predictor/odds/odds_snapshot_engine.py` for API-Football odds history tracking (SQLite append-only).
- Added `worldcup_predictor/odds/sharp_money_intelligence_engine.py` with movement classification, sharp money scoring, RLM detection, and O/U bias.
- Added `SharpMoneyIntelligenceAgent` after `OddsMovementAgent` in the specialist pipeline.
- Integrated into MasterAnalysisAgent and WeightedDecisionEngine with capped influence.
- Streamlit GUI: **Sharp Money & Market Intelligence V2** card on prediction analysis view.
- CLI: `python main.py market-intelligence --fixture-id <id>`

## Phase 41 — Prediction Explainability & Final Report V2

- Added `worldcup_predictor/explainability/` module with read-only explainability engine.
- Generates agent contributions, agreement/conflict scores, confidence explanation, risk analysis, decision timeline, and executive summary.
- Streamlit GUI: **Prediction Explainability V2** section on prediction analysis view.
- CLI: `python main.py explain-prediction --fixture-id <id>`
- Does not modify prediction logic, scoring, or V2 intelligence agents.

## Phase 42 — Self-Learning Accuracy Engine V2

- Added `learning_records_v2` SQLite table (append-only learning history with specialist snapshots).
- Added `SelfLearningEngineV2` for agent reliability, league/market learning, calibration, and review-only recommendations.
- Learning capture hooks on predict pipeline (non-blocking, no scoring changes).
- Streamlit GUI: **Learning & Accuracy Center V2** page.
- CLI: `learning-report`, `agent-performance`, `calibration-report`.

## Phase 43 — Tournament Intelligence V2

- Added `worldcup_predictor/tournament/` module with match context, qualification scenarios, rotation risk, and pressure scoring.
- Added `TournamentIntelligenceAgent` after `MotivationPsychologyAgent` in the specialist pipeline.
- Integrated into MasterAnalysisAgent and WeightedDecisionEngine with capped influence.
- Streamlit GUI: **Tournament Intelligence V2** card on prediction analysis view.
- CLI: `python main.py tournament-intelligence --fixture-id <id>`.

## Phase 44 — ELO & Team Strength Intelligence V2

- Added `worldcup_predictor/strength/` module with ELO-style ratings, long-term form windows, attack/defense strength, momentum, and matchup advantage.
- Added `EloTeamStrengthIntelligenceAgent` after `PlayerQualityAgent` in the specialist pipeline.
- Integrated into MasterAnalysisAgent, WeightedDecisionEngine, Explainability V2, and Self-Learning capture with capped influence.
- Streamlit GUI: **ELO & Team Strength Intelligence V2** card on prediction analysis view.
- CLI: `python main.py elo-intelligence --fixture-id <id>`.

## Phase 45 — xG & Chance Quality Intelligence V2

- Added `worldcup_predictor/chance_quality/` module with real xG extraction, shot-based fallback, conversion efficiency, and goals pressure scoring.
- Added `XGChanceQualityIntelligenceAgent` after `EloTeamStrengthIntelligenceAgent` in the specialist pipeline.
- Integrated into MasterAnalysisAgent, WeightedDecisionEngine, Explainability V2, and Self-Learning capture with capped influence.
- Streamlit GUI: **xG & Chance Quality Intelligence V2** card on prediction analysis view.
- CLI: `python main.py xg-intelligence --fixture-id <id>`.

## Phase 46 — Final Decision Fusion Engine V2

- Added `worldcup_predictor/fusion/` module with signal normalization, confidence quality filtering, conflict resolution, and consensus scoring.
- Fuses all V2 intelligence agents, legacy specialists, and WeightedDecisionEngine baseline without replacing core prediction fields.
- Integrated into predict pipeline (post-WDE), Explainability V2, Self-Learning capture, and GUI.
- Streamlit GUI: **Final Decision Fusion V2** card on prediction analysis view.
- CLI: `python main.py fusion-report --fixture-id <id>`.

## Phase 47 — Professional Match Report Export V2

- Added `worldcup_predictor/export/` module with Markdown, JSON, and compact summary export.
- Reports include prediction, explainability, fusion, and all V2 intelligence summaries.
- Multilingual summary text for English, German, and Persian (`--locale en/de/fa`).
- Saves timestamped files under `reports/match_reports/` (never overwrites).
- CLI: `python main.py export-report --fixture-id <id> --locale en`.
- Streamlit GUI: **Export Professional Report** section on prediction analysis view.
