# DATA-1D Backtest Readiness Report

**Registry fixtures:** 223215
**Fixtures with result labels:** 222985
**Registry label coverage:** 99.9%
**Odds rows joinable to results:** 2062130
**Odds join coverage:** 99.94%

## Result 1X2 distribution

- **home:** 98350
- **away:** 71098
- **draw:** 53537

## Market join coverage (odds + results)

| Market | Odds rows | Fixtures with results |
|--------|-----------|------------------------|
| over_under | 580489 | 222857 |
| double_chance | 481979 | 189590 |
| corners_over_under | 449846 | 83581 |
| team_over_under | 337019 | 84252 |
| ft_result | 100559 | 100555 |
| btts | 77398 | 77363 |
| first_half_winner | 34840 | 34840 |

## ECSE/EVME readiness

- Historical odds can join: `historical_csv_odds_imports` → `historical_fixture_registry` → `historical_fixture_results`
- No API calls required for labeled backtests on imported CSV coverage.
- Production `fixtures` / `predictions` unchanged.

