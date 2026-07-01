//+------------------------------------------------------------------+
//|              PedramScalper_Backtest.mq5                          |
//|           © 2024 Pedram Kamangar – All Rights Reserved           |
//|   Multi-Symbol Backtest Helper for PedramScalper_Pro             |
//|                                                                  |
//|  HOW TO USE:                                                     |
//|  1. Compile this script in MT5 MetaEditor                        |
//|  2. Open Strategy Tester (Ctrl+R in MT5)                         |
//|  3. Select PedramScalper_Pro.mq5 as the Expert                   |
//|  4. Run optimization or single test on each pair below           |
//|  5. Compare results using the Report tab                         |
//|                                                                  |
//|  RECOMMENDED TEST SETTINGS:                                      |
//|  - Model: Every tick (most accurate)                             |
//|  - Period: H1 chart, 30s timer via EventSetTimer                 |
//|  - Date range: 2020.01.01 to 2024.12.31                          |
//|  - Spread: Current or fixed (5 points for majors)                |
//+------------------------------------------------------------------+
#property script_show_inputs
#property copyright "© Pedram Kamangar"

//──────────────────────────────────────────────────────────────────
//  Backtest Pairs Matrix
//  Based on research: best pairs for 30s scalping
//──────────────────────────────────────────────────────────────────

/*
  ═══════════════════════════════════════════════════════════════
  PAIR SELECTION GUIDE FOR 30-SECOND SCALPING
  ═══════════════════════════════════════════════════════════════

  TIER 1 — BEST (High liquidity, tight spread, strong trends)
  ─────────────────────────────────────────────────────────────
  • EURUSD  — Tightest spread (~0.1–0.3 pip), deepest liquidity
              Best hours: London + NY overlap (12:00–17:00 UTC)
              Typical spread on ECN: 0.1–0.5 pip

  • USDJPY  — Very tight spread, strong intraday trends
              Best hours: Tokyo + London (02:00–10:00 UTC)
              Typical spread: 0.2–0.6 pip

  • GBPUSD  — Higher volatility than EUR/USD, wider moves
              Good for Martingale (bigger swings = bigger recovery)
              Best hours: London open (07:00–12:00 UTC)
              Typical spread: 0.3–1.0 pip  ⚠ wider than EUR/USD

  TIER 2 — GOOD (Moderate liquidity, sometimes wider spread)
  ─────────────────────────────────────────────────────────────
  • AUDUSD  — Follows commodity trends, moderate volatility
              Best hours: Sydney + Tokyo (22:00–08:00 UTC)
              Typical spread: 0.3–0.8 pip

  • USDCAD  — Correlated with oil; moderate trend clarity
              Best hours: NY session (13:00–21:00 UTC)
              Typical spread: 0.4–1.0 pip

  • EURJPY  — Fast-moving cross; good for Martingale recovery
              Higher risk — wider spread and larger ATR
              Typical spread: 0.6–1.5 pip

  TIER 3 — CAUTION (Wider spread may hurt scalping)
  ─────────────────────────────────────────────────────────────
  • XAUUSD  — Gold, very high ATR; can be extremely profitable
              but Martingale is DANGEROUS — 4x lot on gold = huge risk
              Use with reduced base lot (0.01 absolute minimum)
              Typical spread: $0.30–$0.60 on ECN

  • GBPJPY  — Very volatile cross; wide spread hurts scalps
              Only use with ATR SL >= 2.0 multiplier

  ═══════════════════════════════════════════════════════════════
  OPTIMISATION PARAMETERS TO TEST
  ═══════════════════════════════════════════════════════════════
  1. InpEMAFast      : 21, 34, 50
  2. InpEMASlow      : 100, 144, 200
  3. InpADXMinStrength: 18, 22, 25
  4. InpATRSLMult    : 1.2, 1.5, 2.0
  5. InpTP3RR        : 2.0, 3.0, 4.0
  6. InpTrailPts     : 10, 15, 20
  7. InpRSIPeriod    : 5, 7, 9

  ═══════════════════════════════════════════════════════════════
  RECOMMENDED BACKTEST RESULTS TARGETS
  ═══════════════════════════════════════════════════════════════
  • Win Rate    : > 52%  (break-even vs spread is ~50%)
  • Profit Factor: > 1.3
  • Max DD       : < 20%
  • Sharpe Ratio : > 1.0
  • Recovery Factor: > 2.0

  ═══════════════════════════════════════════════════════════════
  MARTINGALE RISK WARNING
  ═══════════════════════════════════════════════════════════════
  With base lot 0.01:
    Normal trade  : 0.01 lot
    After 1 loss  : 0.02 lot  (2×)
    After 2 losses: 0.04 lot  (4×)
    Safety halt   : after 4 consecutive losses

  Ensure account balance supports worst-case drawdown:
    Minimum recommended balance per 0.01 base lot = $500 USD
    For XAUUSD: minimum $2,000 per 0.01 base lot

*/

input string InpTestPair    = "EURUSD";   // Test Symbol
input double InpTestBalance = 10000;      // Test Starting Balance

//+------------------------------------------------------------------+
void OnStart()
{
   Print("═══════════════════════════════════════════════════");
   Print("  PedramScalper Pro — Backtest Reference Script");
   Print("  © Pedram Kamangar");
   Print("═══════════════════════════════════════════════════");
   Print("");
   Print("Recommended test pairs (in order of suitability):");
   Print("  1. EURUSD  — Primary target (tightest spread)");
   Print("  2. USDJPY  — Strong trends, Asian session boost");
   Print("  3. GBPUSD  — High volatility, good for Martingale");
   Print("  4. AUDUSD  — Commodity-linked, smooth trends");
   Print("  5. USDCAD  — NY session, oil correlation");
   Print("  6. EURJPY  — Cross pair, faster recovery swings");
   Print("  7. XAUUSD  — ⚠ High risk, reduce base lot to 0.01");
   Print("");
   Print("Selected test pair: ", InpTestPair);
   Print("Recommended backtest date: 2020.01.01 — 2024.12.31");
   Print("Model: Every tick (highest quality)");
   Print("Starting balance: ", InpTestBalance, " USD");
   Print("");
   Print("Open Strategy Tester (Ctrl+R), load PedramScalper_Pro");
   Print("and select the above symbol + date range to run.");
   Print("═══════════════════════════════════════════════════");
}
//+------------------------------------------------------------------+
