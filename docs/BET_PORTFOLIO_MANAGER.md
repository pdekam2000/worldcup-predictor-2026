# Bet Portfolio Manager — Research

**Status:** `BET_PORTFOLIO_MANAGER_RESEARCH_COMPLETE`  
**Deploy:** **NOT DEPLOYED**

## Role

Final capital decision layer after Coverage + Insurance.

Does **not** predict football. Does **not** modify WDE / ECSE / Coverage / Insurance / freezes.

Decides: bet or skip, which fixtures, how much capital, risk limits.

## Distinct from OBPE

`optimal_betting_portfolio_engine` selects markets.  
`bet_portfolio_manager` allocates capital and day quality for existing BCO outputs (read-only).

## Runner

```bash
python scripts/run_bet_portfolio_manager_research.py --bankroll 500 --mode score_weighted
```
