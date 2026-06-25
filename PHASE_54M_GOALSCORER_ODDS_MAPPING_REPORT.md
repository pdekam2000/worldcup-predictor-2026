# PHASE 54M — Goalscorer Odds Mapping & Calibration Layer

**Date:** 2026-06-24  
**Mode:** Mapping Research → Odds Alignment → Calibration Study → Report  
**Status:** Complete — validation **18/18 PASS**  
**API calls:** 0

---

## Executive summary

Built a research-only **goalscorer odds mapping layer** with name normalization, lineup-constrained fuzzy matching, ML vs bookmaker comparison, and calibration study. Cache audit found **703 goalscorer selections across 3 fixtures** (bet365). **38.4% mapping rate** (270/703) with HIGH/MEDIUM confidence only. Sample too small for production; mapping pipeline works but needs more odds-rich ingest.

### Final recommendation: **`NEED_MORE_GOALSCORER_ODDS`**

Secondary: **`NEED_BETTER_PLAYER_MAPPING`** for Team Goalscorer rows (team names vs player names).

---

## Part A — Odds source audit

| Metric | Value |
|--------|-------|
| Fixtures audited (cache) | 1,689 |
| **Fixtures with goalscorer odds** | **3** |
| Selections | **703** |
| Bookmakers | 1 (bet365) |
| Markets | 2 (Goalscorers, Team Goalscorer) |
| Historical | 3 |
| Upcoming | 0 |

### Market breakdown

| Market | Label | Count |
|--------|-------|-------|
| Goalscorers | Anytime | 137 |
| Goalscorers | First | 140 |
| Goalscorers | Last | 140 |
| Team Goalscorer | First | 143 |
| Team Goalscorer | Last | 143 |

**Note:** 70 UEFA cache files have odds, but only **3** include player goalscorer markets; others are Correct Score / O-U only.

---

## Part B — Player name mapping

**Package:** `worldcup_predictor/egie/goalscorer_odds_mapping/`

| Method | Description |
|--------|-------------|
| exact | Case-insensitive name match |
| normalized_exact | Accent-stripped compact match |
| initial_last | Surname + first-initial |
| token_overlap | Shared surname tokens |
| fuzzy_high / fuzzy_medium | SequenceMatcher ≥0.92 / ≥0.85 |

**Constraints:** same fixture, lineup players only, confidence tier required.

### Mapping results

| Metric | Value |
|--------|-------|
| Mapped (HIGH+MEDIUM) | **270** (38.4%) |
| Unmapped / rejected | **433** (61.6%) |
| HIGH confidence | 225 |
| MEDIUM confidence | 45 |
| LOW (rejected) | 0 forced |

**Primary unmapped cause:** `Team Goalscorer` selections use **team names** (e.g. club names), not player names — not mappable to `player_id` without market parser changes.

---

## Part C — Artifacts

`artifacts/phase54m_goalscorer_odds_mapping/`

| File | Description |
|------|-------------|
| `goalscorer_odds_raw.csv` | 703 raw selections |
| `goalscorer_odds_mapped.csv` | 270 mapped rows |
| `goalscorer_odds_unmapped.csv` | 433 unmapped |
| `mapping_summary.json` | Audit + mapping stats |
| `phase54m_report.json` | Full comparison + calibration |

---

## Part D — ML vs bookmaker (Anytime, 3 fixtures, 32 mapped rows)

| Signal | Top-1 | Top-3 | Top-5 |
|--------|-------|-------|-------|
| ML probability | 66.7% | **66.7%** | 66.7% |
| Book implied | 33.3% | 33.3% | 100% |
| ML+odds blend | 66.7% | 66.7% | 100% |

| Overlap metric | Value |
|----------------|-------|
| Top-3 overlap ML∩Book | 33.3% |
| Top-3 disagreement | 66.7% |
| ML-only hits | 33.3% |
| Book-only hits | 0% |

**Caveat:** n=3 fixtures — directional only, not statistically significant.

---

## Part E — Calibration study

| Track | Brier | LogLoss | ECE |
|-------|-------|---------|-----|
| ML only | 0.164 | 0.508 | 0.312 |
| **Odds only** | **0.076** | **0.264** | **0.030** |
| ML+odds blend | 0.103 | 0.372 | 0.231 |
| Market-adjusted ML | 0.168 | 0.516 | 0.356 |

- **ML beats odds on ranking** (top-3) in tiny sample
- **Odds beat ML on calibration** (Brier/ECE)
- **Blend does not beat ML** on top-3 hit rate

---

## Report answers

### 1. How many goalscorer odds fixtures exist?

**3 fixtures** in cache (703 selections).

### 2. How many selections exist?

**703** (417 Goalscorers + 286 Team Goalscorer).

### 3. What mapping rate was achieved?

**38.4%** (270/703) at HIGH+MEDIUM confidence.

### 4. What mapping confidence distribution?

| Tier | Count |
|------|-------|
| HIGH | 225 |
| MEDIUM | 45 |
| LOW rejected | 433 unmapped |

### 5. Are bookmaker odds useful?

**Yes for calibration** (low ECE); **mixed for ranking** on n=3. Implied probabilities are better calibrated than raw ML on this slice.

### 6. Does ML + odds beat ML alone?

**No** on top-3 (tie 66.7%). Blend improves top-5 only.

### 7. Is odds calibration possible now?

**Partially** — odds-implied probs calibrate well; player mapping limits usable rows to 270. Need more Goalscorers (not Team Goalscorer) selections.

### 8. What is the next step?

1. **Ingest more fixtures** with `odds.bookmaker;odds.market` include (target 50+ goalscorer fixtures)
2. **Parse Team Goalscorer** separately (team-level market, not player mapping)
3. Re-run 54M on expanded cache before shadow promotion

---

## Validation

**18/18 PASS** (`artifacts/phase54m_goalscorer_odds_mapping/validation.json`)

---

**Phase 54M complete. No deploy. No live prediction changes. No EGIE scoring changes.**
