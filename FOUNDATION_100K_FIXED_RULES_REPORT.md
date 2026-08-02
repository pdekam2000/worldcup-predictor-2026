# Fixed rules (diagnostic only)

## ea08ac971da53246

Market: home

Conditions:
- market_family = home
- direction_source = wde
- selected_odds <= 1.5
- lambda_total >= 2.0

Validation: N=8 acc=0.875 roi=0.1056
Status: NOT_PROMOTABLE_SMALL_SAMPLE

## de9110e24996fc5a

Market: home

Conditions:
- market_family = home
- direction_source = wde
- selected_odds <= 1.5
- lambda_total >= 2.0
- lambda_total <= 3.5

Validation: N=8 acc=0.875 roi=0.1056
Status: NOT_PROMOTABLE_SMALL_SAMPLE

## cd94fa9b9cd44136

Market: home

Conditions:
- market_family = home
- direction_source = wde
- selected_odds <= 1.5
- model direction == market favorite
- lambda_total >= 2.0

Validation: N=8 acc=0.875 roi=0.1056
Status: NOT_PROMOTABLE_SMALL_SAMPLE

## f92722cfa5f4dd74

Market: home

Conditions:
- market_family = home
- direction_source = wde
- selected_odds <= 1.5
- model direction == market favorite
- lambda_total >= 2.0
- lambda_total <= 3.5

Validation: N=8 acc=0.875 roi=0.1056
Status: NOT_PROMOTABLE_SMALL_SAMPLE

## 56732695db7d58c6

Market: home

Conditions:
- market_family = home
- direction_source = wde
- selected_odds <= 1.5
- WDE direction == ECSE direction
- lambda_total >= 2.0

Validation: N=8 acc=0.875 roi=0.1056
Status: NOT_PROMOTABLE_SMALL_SAMPLE