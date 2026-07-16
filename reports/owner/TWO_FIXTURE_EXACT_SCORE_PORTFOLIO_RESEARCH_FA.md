# پژوهش پورتفوی دو بازی — اسکور دقیق (۲۵ ترکیب اصلی + پوشش)

**حالت:** فقط تحقیق و سایه — بدون استقرار تولید، بدون شرط‌بندی خودکار، بدون تغییر ECSE/فریز.

**وضعیت نهایی:** `TWO_FIXTURE_PORTFOLIO_REAL_ODDS_DATA_REQUIRED`

**زمان تولید:** 2026-07-15 21:38:57 UTC

## نتیجه پژوهش قبلی (قفل‌شده)

- Canonical Top5 ≈ **۴۳٫۳۴٪**
- Shift Both +1 به‌عنوان مدل جایگزین **رد** شد (≈۲۳٫۶۶٪)
- اتحاد Canonical ∪ Shifted تا ۱۰ ≈ **۵۳٫۲۴٪**
- سیاست: شیفت فقط به‌عنوان نامزد پوشش مکمل

Canonical Top5 **هرگز جایگزین نمی‌شود**.

## موجودی ضرایب

- ضرایب تاریخی اسکور دقیق در CSV: **یافت نشد** (`real_exact_score_odds_available=False`)
- Over 3.5 واقعی (در صورت وجود closing): موجود در دیتاست آموزشی
- سودآوری ارزی پکیج ۲۵تایی **قابل اثبات نیست** تا ضرایب واقعی اسکور دقیق گردآوری شوند

## ساختار

```text
۵ اسکور کنونیکال بازی A × ۵ اسکور کنونیکال بازی B = ۲۵ بلیت اصلی
```

احتمال مشترک با فرض استقلال تقریب زده می‌شود و وابستگی مسابقات هم‌روز ممکن است اثر بگذارد.

فضای تمام اسکورها با Top5 کامل نیست → ادعای آربیتراژ برای ۲۵ بلیت **ممنوع**.

## پوشش Walk-Forward

بهترین دروازه انتخاب: **highest_expected_joint**

- نرخ برخورد ۲۵تایی: **0.38929440389294406 (best gate); mean across gates ≈ 0.24957937113307763**
- پوشش مشترک مدل Top5×Top5: **0.148306558779411 on demo pair; walk-forward avg 0.3442009553009059**
- بهبود پوشش با پوشش‌ها: **demo Δjoint=0.2585260299318361; walk-forward union avg 0.7188373862207772**
- ROI تاریخی با ضرایب واقعی اسکور دقیق: **در دسترس نیست**

## Over 3.5

پوشش نمی‌کند: 2-1, 1-2, 3-0, 0-3.

## پاسخ به ۲۰ سؤال

1. Yes as a coverage/upside structure; not proven as a profitable betting system
2. 0.38929440389294406 (best gate); mean across gates ≈ 0.24957937113307763
3. 0.148306558779411 on demo pair; walk-forward avg 0.3442009553009059
4. demo Δjoint=0.2585260299318361; walk-forward union avg 0.7188373862207772
5. ~5 extra tickets by gain/ticket on curve (research)
6. canonical_top6_10
7. inconclusive_without_cs_odds
8. 2-1, 1-2, 3-0, 0-3
9. Only if hedge odds × stake ≥ total portfolio stake; not guaranteed; not proven with real CS odds
10. Requires stake_h ≥ TotalStake / Odds_h and non-overlapping win conditions; bookmaker min stake may block
11. Full stake loss on uncovered outcomes (demo −€50.0 if budget=50.0)
12. ≈ 1 − joint_union_model (demo 0.5931674112887528); WF full-loss 0.19951338199513383
13. EQUAL expected_net=-7.627 min_covered=138.876; MINIMAX expected_net=-7.627 min_covered=235.711 (SYNTHETIC only)
14. Minimax equalizes covered-scenario return (synthetic); does not eliminate uncovered full-loss drawdown
15. Unknown historically — no CS odds; synthetic medium margin implies negative EV on average
16. NO — trustworthy currency ROI test blocked
17. highest_expected_joint
18. Yes — owner-only shadow report after real CS odds wired; never public auto-bet
19. NO
20. Ingest legitimate prematch exact-score odds (bookmaker+timestamp+settlement) then rerun stake/ROI validation

## یکپارچه‌سازی روزانه (فقط طراحی)

جدا از پیش‌بینی عمومی SaaS؛ فقط گزارش مالک؛ تأیید دستی؛ بدون شرط خودکار.

## وضعیت نهایی

`TWO_FIXTURE_PORTFOLIO_REAL_ODDS_DATA_REQUIRED`

توقف.
