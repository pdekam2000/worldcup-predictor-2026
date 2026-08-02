# APPROVED_BETS_APPROVAL_TAXONOMY

There is **no single durable APPROVED_BET ledger**. Historical approval = explicit shortlist artifact membership + gates.

## `selected_matches.json / selected[]`
- Values: `['fixture cards in owner pick artifacts']`
- Sources: `['artifacts/today_owner_picks_*', 'artifacts/owner_balanced_odds_picks_*']`
- Represents: **final betting approval (owner day shortlist)**
- Enter official approved: **True**
- Cohort: `STRICT_OWNER_APPROVED`
- Reason: Explicit owner final selection artifact for that Vienna day.

## `dayN_best_three.json / selected[]`
- Values: `['top-3 per day']`
- Sources: `['artifacts/three_day_complete_predictions/*/day*_best_three.json']`
- Represents: **final owner/research day shortlist**
- Enter official approved: **True**
- Cohort: `STRICT_OWNER_APPROVED`
- Reason: Named best-three shortlist written before kickoff as day selection.

## `selected_top3.json / selected[]`
- Values: `['top-3']`
- Sources: `['artifacts/tomorrow_best_three_top10/*/selected_top3.json']`
- Represents: **final day shortlist**
- Enter official approved: **True**
- Cohort: `STRICT_OWNER_APPROVED`
- Reason: Explicit selected_top3 policy output.

## `freeze_selection.json`
- Values: `['freeze_id rows']`
- Sources: `['artifacts/mandatory_three_match_prediction_*']`
- Represents: **final mandated trio selection**
- Enter official approved: **True**
- Cohort: `STRICT_OWNER_APPROVED`
- Reason: Mandatory three-match freeze selection.

## `betting_quality`
- Values: `['BETTABLE_CANDIDATE', 'WATCHLIST', 'MODEL_ANALYSIS_ONLY', 'NO_BET', 'BLOCKED']`
- Sources: `['three_day complete_predictions.json']`
- Represents: **model recommendation / soft bettable (not capital approval alone)**
- Enter official approved: **BETTABLE_CANDIDATE_ONLY_IF_NO_BET_FALSE**
- Cohort: `STRICT_OWNER_APPROVED if BETTABLE_CANDIDATE+no_bet=false else WATCHLIST_ONLY/NO_BET`
- Reason: BETTABLE_CANDIDATE is closest structured bet label; still candidate-grade.

## `final_12_1x2.json / research_classification`
- Values: `['STRONG_RESEARCH_CANDIDATE', 'RESEARCH_CANDIDATE']`
- Sources: `['artifacts/next_5_days_12_1x2_2_exact/*']`
- Represents: **research final 1X2 shortlist**
- Enter official approved: **False**
- Cohort: `RESEARCH_APPROVED`
- Reason: Mission explicitly research-only; no_promotion; not production capital approval.

## `final_owner_shortlist.json`
- Values: `['best_3_end_result', 'best_3_exact_score', 'best_3_model_consensus']`
- Sources: `['artifacts/next_4_days_complete_predictions/*']`
- Represents: **research owner shortlist**
- Enter official approved: **False**
- Cohort: `RESEARCH_APPROVED`
- Reason: Artifact flags no_promotion=true.

## `final_2_low_goal_exact.json / primary_top_2`
- Values: `['exact primary/additional']`
- Sources: `['next_5_days exact finals', 'today exact score selection']`
- Represents: **exact-score selection**
- Enter official approved: **False**
- Cohort: `EXACT_SCORE_APPROVED`
- Reason: Separate Exact Score cohort; not 1X2 approval.

## `no_bet / no_bet_flag`
- Values: `['true', 'false']`
- Sources: `['freezes', 'predictions', 'scans']`
- Represents: **technical eligibility / abstention gate**
- Enter official approved: **False**
- Cohort: `gate only`
- Reason: no_bet=false is necessary but not sufficient for approval.

## `selection_level (selection_decisions)`
- Values: `['AUTO_PREDICT', 'WATCHLIST', 'SKIP_*']`
- Sources: `['selection_decisions table']`
- Represents: **prediction eligibility**
- Enter official approved: **False**
- Cohort: `eligibility only`
- Reason: Decides whether to predict, not whether to bet.

## `final_selection / APPROVED bet enum`
- Values: `['not found as durable field']`
- Sources: `['searched codebase']`
- Represents: **absent**
- Enter official approved: **False**
- Cohort: `N/A`
- Reason: No single durable APPROVED_BET ledger exists; shortlist artifacts are source of truth.
