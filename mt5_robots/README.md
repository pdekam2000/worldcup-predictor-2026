# PedramScalper Pro — MT5 Expert Advisor

**© Pedram Kamangar** | Smart 30-Second Scalping Robot | Version 2.0

---

## Overview

A semi-fully automatic Expert Advisor for MetaTrader 5 that:

1. **Detects the overall trend** on H1 using EMA 50 / EMA 200 + ADX confirmation
2. **Fires every 30 seconds** via `EventSetTimer` — checks RSI + Stochastic for entry
3. **Enters only in the direction of the trend** (no counter-trend trades)
4. **Uses a progressive Martingale**:
   - Win → reset to base lot
   - 1st loss → 2× base lot
   - 2nd+ loss → 4× base lot
   - After 4 consecutive losses → safety halt + Alert
5. **3-Level Smart Take Profit** (SL promotion):
   - TP1 hit → SL moves to break-even
   - TP2 hit → SL moves to TP1 price level (locking profit)
   - TP3 → hard take-profit (set at order placement)
6. **Smart ATR-based Stop Loss** (or manual fixed points)
7. **Smart Trailing Stop** (activates after configurable profit threshold)
8. **Max Drawdown Guard** — halts all trading if equity DD exceeds limit
9. **Colored Logo Panel** with owner name, running status indicator
10. **Full error reporting** to MT5 Experts log + Alert popups
11. **Backtest-ready** — includes pair selection guide

---

## File Structure

```
mt5_robots/
├── PedramScalper_Pro.mq5          ← Main Expert Advisor
├── PedramScalper_Backtest.mq5     ← Backtest reference script
└── README.md                      ← This file
```

---

## Installation

1. Copy `PedramScalper_Pro.mq5` to:
   ```
   C:\Users\<YourName>\AppData\Roaming\MetaQuotes\Terminal\<ID>\MQL5\Experts\
   ```
2. Open **MetaEditor** (F4 in MT5) → compile the file (F7)
3. Attach to any chart (recommended: H1 or M5)
4. Configure inputs in the EA settings dialog

---

## Input Parameters

### Trade Settings
| Parameter | Default | Description |
|-----------|---------|-------------|
| `InpBaseLot` | 0.01 | Base lot size |
| `InpUseMartingale` | true | Enable progressive lot sizing |
| `InpMult2x` | 2.0 | Lot multiplier after 1st loss |
| `InpMult4x` | 4.0 | Lot multiplier after 2nd+ loss |
| `InpMaxConsecLoss` | 4 | Safety halt after N consecutive losses |

### Trend Detection
| Parameter | Default | Description |
|-----------|---------|-------------|
| `InpTrendTF` | H1 | Timeframe for trend analysis |
| `InpEMAFast` | 50 | Fast EMA period |
| `InpEMASlow` | 200 | Slow EMA period |
| `InpADXPeriod` | 14 | ADX period |
| `InpADXMinStrength` | 20.0 | Minimum ADX to confirm trend |

### Scalping Settings
| Parameter | Default | Description |
|-----------|---------|-------------|
| `InpTimerSec` | 30 | Scalp check interval in seconds |
| `InpRSIPeriod` | 7 | RSI period (M1 chart) |
| `InpRSIOB` | 70 | RSI overbought threshold |
| `InpRSIOS` | 30 | RSI oversold threshold |
| `InpStochK/D/Slow` | 5/3/3 | Stochastic parameters |

### Stop Loss
| Parameter | Default | Description |
|-----------|---------|-------------|
| `InpATRStopLoss` | true | Use ATR-based dynamic SL |
| `InpATRPeriod` | 14 | ATR calculation period |
| `InpATRSLMult` | 1.5 | ATR × multiplier = SL distance |
| `InpManualSLPts` | 50 | Fixed SL in points (if ATR off) |

### Take Profit
| Parameter | Default | Description |
|-----------|---------|-------------|
| `InpTP1RR` | 1.0 | TP1 R/R — SL moves to break-even |
| `InpTP2RR` | 2.0 | TP2 R/R — SL moves to TP1 level |
| `InpTP3RR` | 3.0 | TP3 R/R — hard take-profit exit |

### Risk Management
| Parameter | Default | Description |
|-----------|---------|-------------|
| `InpMaxDDPct` | 10.0 | Maximum drawdown % before halt |
| `InpMaxOpenTrades` | 1 | Maximum simultaneous trades |

---

## Recommended Pairs for Backtest

| Pair | Tier | Spread | Best Session | Notes |
|------|------|--------|--------------|-------|
| **EURUSD** | ⭐⭐⭐ | 0.1–0.5 pip | London+NY overlap | Best overall |
| **USDJPY** | ⭐⭐⭐ | 0.2–0.6 pip | Tokyo+London | Strong trends |
| **GBPUSD** | ⭐⭐ | 0.3–1.0 pip | London open | High volatility |
| **AUDUSD** | ⭐⭐ | 0.3–0.8 pip | Sydney+Tokyo | Smooth trends |
| **USDCAD** | ⭐⭐ | 0.4–1.0 pip | NY session | Oil correlated |
| **EURJPY** | ⭐ | 0.6–1.5 pip | Any | Fast swings |
| **XAUUSD** | ⚠ | $0.30–$0.60 | London+NY | Dangerous with Martingale |

### Backtest Configuration (MT5 Strategy Tester)
- **Model**: Every tick (most accurate)
- **Spread**: Broker current or 5 points fixed
- **Date range**: 2020-01-01 to 2024-12-31
- **Starting balance**: $10,000

---

## How the Martingale Works

```
Trade 1 → WIN  → Lot = 0.01  (base)        → reset to base
Trade 2 → LOSS → Lot = 0.01  (base)        → next = 0.02 (2×)
Trade 3 → LOSS → Lot = 0.02  (2×)          → next = 0.04 (4×)
Trade 4 → WIN  → Lot = 0.04  (4×)          → next = 0.01 (reset!)
Trade 5 → LOSS → Lot = 0.01  (base)        → next = 0.02 (2×)
```

After `InpMaxConsecLoss` consecutive losses, the EA halts and fires an Alert.

---

## 3-Level TP Logic (SL Promotion)

```
Price moves 1× SL distance in profit  → SL → Break-Even (TP1)
Price moves 2× SL distance in profit  → SL → TP1 price level (locks profit) (TP2)
Price hits hard TP (3× SL distance)   → Trade closed at full profit (TP3)
```

If trailing stop is enabled, it activates once price moves `InpTrailStartPts` into profit and trails by `InpTrailPts`.

---

## Error Reporting

All errors are written to:
- MT5 **Experts** tab (bottom panel)
- MT5 **Journal** tab
- **Alert** popup for critical events (max DD, max loss streak, order failures)

---

## Risk Warning

> Trading foreign exchange with Martingale strategies carries significant risk of substantial losses.
> Past backtest results do not guarantee future performance.
> Always test on a **demo account** before using real money.
> Never risk funds you cannot afford to lose.

---

*© Pedram Kamangar — All rights reserved.*
