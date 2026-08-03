# گزارش استخراج رژیم O/U 2.5

**وضعیت:** `OU25_REGIME_MINING_PARTIAL_ODDS_LIMITED`

## داده
- True-forward: 168
- تاریخی پیش‌از شروع: 52
- مجموع قابل ارزیابی: 220

## عملکرد خام
- دقت کل: 53.2%
- فقط Over: n=98 دقت=59.2%
- فقط Under: n=122 دقت=48.4%

## بهترین قانون N≥30
- نام: over_lambda_ge_2_5_prob_ge_60
- شرایط: ['total_lambda>=2.5', 'over_probability>=0.60', 'selected=over_2_5']
- N=54 پوشش=24.5% دقت=66.7%
- برچسب: OU25_DIAGNOSTIC_RULE
- ROI رسمی: n/a (priced_n=0)

## آیا لبه پایدار وجود دارد؟
False (برچسب برنامه: OU25_PROMISING_RESEARCH_RULE)

## فیلتر ECSE Direction
خام=53.0% · بهترین فیلتر=home_only_agree · N=62 · دقت=72.6%

## محدودیت شانس
شانس رسمی O/U روی True-Forward بسیار کم است؛ ROI فقط با OFFICIAL_PRICED.

## ایمنی
NOT DEPLOYED · CANONICAL/WDE/ECSE UNCHANGED · FREEZES UNCHANGED · NO REGEN · NO AUTO-PROMOTION
