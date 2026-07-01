# MT5 Diagnostic EA - Immediate Trade Test

این فایل برای تست پلتفرم/بروکر است، نه برای استراتژی.

EA:

```text
mql5/Experts/InstantTradePlatformCheckEA.mq5
```

## هدف

اگر ربات‌های اصلی 1-2 روز معامله نکرده‌اند، اول باید بفهمیم مشکل از کجاست:

- AutoTrading خاموش است؟
- گزینه Allow Algo Trading برای EA خاموش است؟
- حساب اجازه معامله ندارد؟
- سیمبل قابل معامله نیست؟
- lot با min/step بروکر سازگار نیست؟
- spread یا stops level باعث reject می‌شود؟
- broker retcode خطای مشخص می‌دهد؟
- یا همه چیز سالم است و فقط شرط‌های استراتژی ربات‌های اصلی trigger نشده‌اند؟

این EA به محض attach شدن، یک معامله کوچک تستی روی همان chart باز می‌کند و همه diagnosticها را در Experts log چاپ می‌کند.

## نحوه استفاده امن

فقط روی demo یا حساب تست:

1. فایل `InstantTradePlatformCheckEA.mq5` را داخل مسیر زیر کپی کن:

   ```text
   MQL5/Experts/
   ```

2. در MetaEditor فایل را باز کن و Compile بزن.
3. در MT5 دکمه `Algo Trading` را روشن کن.
4. EA را روی یک chart مثل `EURUSD` یا همان symbol مشکل‌دار drag کن.
5. در تنظیمات EA:
   - `InpEnableTestTrade = true`
   - `InpRequestedLots = 0.01`
   - `InpBlockIfAnyPosition = true`
   - `InpOneTradePerSymbol = true`
   - اگر خواستی خودش ببندد:
     - `InpAutoClose = true`
     - `InpAutoCloseSeconds = 60`
6. تب `Experts` و `Trade` را نگاه کن.

## نتیجه‌ها را چطور بخوانیم؟

### حالت سالم

اگر این را دیدی:

```text
IPC_DIAG order result: sent=true retcode=10009 desc=Request completed
```

یا retcode موفق مشابه، یعنی:

- MT5 درست کار می‌کند.
- حساب اجازه معامله دارد.
- symbol قابل معامله است.
- order routing بروکر سالم است.

در این حالت مشکل از platform نیست؛ ربات‌های اصلی احتمالاً به‌خاطر شرط‌های ورود، new-bar gate، تایم‌فریم، spread filter، session filter، یا magic/position guard معامله نکرده‌اند.

### AutoTrading خاموش

```text
IPC_DIAG BLOCKED: terminal AutoTrading disabled
```

راه‌حل:

- دکمه Algo Trading بالای MT5 را روشن کن.

### Allow Algo Trading خاموش برای خود EA

```text
IPC_DIAG BLOCKED: EA property 'Allow Algo Trading' is disabled.
```

راه‌حل:

- موقع attach کردن EA، در تب Common گزینه Allow Algo Trading را فعال کن.

### حساب اجازه معامله ندارد

```text
IPC_DIAG BLOCKED: account trade not allowed by broker/server.
```

راه‌حل:

- حساب read-only/investor نباشد.
- market باز باشد.
- broker اجازه trading روی آن حساب را بدهد.

### سیمبل قابل معامله نیست

```text
IPC_DIAG BLOCKED: symbol trade mode disabled
```

راه‌حل:

- symbol درست broker را انتخاب کن.
- گاهی اسم symbol suffix دارد مثل `EURUSD.a` یا `AUDUSDm`.

### حجم اشتباه

در log این مقادیر چاپ می‌شود:

```text
volume_min
volume_step
volume_max
```

اگر broker حداقل lot بالاتر از 0.01 دارد، EA خودش volume را normalize می‌کند. اگر باز هم reject شد، مقدار `InpRequestedLots` را با `volume_min` هماهنگ کن.

### spread زیاد

اگر `InpMaxSpreadPoints` را بیشتر از صفر گذاشته باشی و spread زیاد باشد:

```text
IPC_DIAG BLOCKED: spread=...
```

برای تست platform، می‌توانی `InpMaxSpreadPoints = 0` بگذاری.

### position قبلی روی همان symbol وجود دارد

برای امنیت، اگر روی همان symbol معامله باز داشته باشی، EA پیش‌فرض معامله تستی نمی‌زند:

```text
IPC_DIAG no order sent: existing position found on this symbol
```

راه‌حل امن:

- روی یک symbol دیگر تست کن، یا
- position قبلی را در demo ببند، یا
- فقط اگر مطمئنی حساب demo/test است `InpBlockIfAnyPosition=false` بگذار.

## بعد از تست

اگر EA تشخیصی معامله باز کرد اما ربات‌های اصلی نه، این‌ها را در ربات‌های اصلی چک کن:

- آیا فقط روی کندل جدید trade evaluation می‌کنند؟
- آیا روی تایم‌فریم درست attach شده‌اند؟
- آیا session/time filter اجازه معامله می‌دهد؟
- آیا max positions یا one-trade-per-symbol جلوی معامله را گرفته؟
- آیا spread filter خیلی سخت است؟
- آیا lot/min step درست normalize شده؟
- آیا شرط‌های entry خیلی سخت هستند؟
- آیا magic number بین چند robot تداخل دارد؟
- آیا symbol suffix broker در کد لحاظ شده؟

## هشدار

این EA برای تست اتصال معامله است و نباید روی حساب واقعی با حجم بالا استفاده شود.
