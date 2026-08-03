# گزارش ارزیابی کامل True-Forward 472

**وضعیت:** `TRUE_FORWARD_472_EVALUATION_PARTIAL_RESULTS_PENDING`

## پاسخ مستقیم به ۱۴ سؤال

1. **عدد ۴۷۲ دقیقاً چه چیزی بوده است؟**
   472 frozen_predictions rows in forward_prediction_tracking.db; each row is a prematch freeze bundle (WDE+ECSE+BTTS+OU), not one independent fixture evidence unit. 316 unique fixtures; 156 extra rows from multi-freeze snapshots/reuses.

2. **چند بازی یکتا؟** 316

3. **چند بازی پایان یافته؟** 168

4. **چند بازی واقعاً قابل ارزیابی؟** 168

5. **WDE چند درست/غلط؟** درست=82 غلط=86 دقت=48.8% (n=168)

6. **ECSE Direction چند درست/غلط؟** درست=89 غلط=79 دقت=53.0% (n=168)

7. **Strict shortlist چند درست/غلط؟** درست=0 غلط=0 دقت=n/a (n=0)

8. **Exact Top1/Top3/Top5/Top10؟** 15.5% / 31.5% / 45.2% / None
   (فروزن‌ها فقط Top1–Top5 ذخیره کرده‌اند؛ Top10 در استور موجود نیست)

9. **بهترین Win Rate؟** canonical_ecse_direction = 53.0% (n=168)

10. **بهترین ROI؟** canonical_wde_raw_argmax = 77.3% (priced_n=3)

11. **آیا Gate A/B/C واقعاً پاس شده؟**
    Gate A=True (نیاز≥۳۰، مقدار=168) ·
    Gate B=True (نیاز≥۱۰۰) ·
    Gate C=False (نیاز≥۲۵۰)
    **شمارش خام ۴۷۲ ملاک گیت نیست.**

12. **آیا هیچ Candidate به ۷۵٪ روی نمونه معتبر (n≥۳۰) رسیده؟** False

13. **آیا نتیجه از نظر آماری قابل اعتماد است؟** MODERATE — نمونه‌ی ارزیابی‌شده=168

14. **مرحله بعدی چیست؟** Gate A/B already met on evaluated unique fixtures; continue accumulating until Gate C (≥250). Do not treat raw 472 as evidence. Capture prematch odds on freezes (priced N is currently tiny). Optionally backfill market_evaluations for 26 finished-but-unevaluated freezes via the official evaluator (no prediction regen).

## قانون ثابت ea08ac97 (فقط true-forward)

- واجد شرایط: 1 (پایان‌یافته=1، در انتظار=0)
- دقت: 100.0%
- ROI: 40.0%
- مرجع تاریخی (ترکیب نشود): N=49، ۷۵٫۵٪، ROI=−۶٫۸٪

## ایمنی

NOT DEPLOYED · CANONICAL UNCHANGED · WDE UNCHANGED · ECSE UNCHANGED · FREEZES UNCHANGED · NO PREDICTIONS REGENERATED · NO AUTO-PROMOTION · NO RESULT LEAKAGE
