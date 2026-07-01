//+------------------------------------------------------------------+
//|                     PedramScalper_Pro.mq5                        |
//|           © 2024 Pedram Kamangar – All Rights Reserved           |
//|     Smart 30-Second Scalping Robot | Trend + Martingale + 3TP    |
//|                       Version 2.0                                |
//+------------------------------------------------------------------+
#property copyright   "© Pedram Kamangar"
#property link        ""
#property version     "2.00"
#property description "Smart Scalping Robot — 30s interval scalping"
#property description "Trend detection (H1 EMA50/200 + ADX)"
#property description "Martingale: Win→Base | Loss1→2x | Loss2→4x"
#property description "3-Level Smart Take Profit + ATR Smart Stop Loss"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\HistoryOrderInfo.mqh>

//──────────────────────────────────────────────────────────────────
//  INPUT GROUPS
//──────────────────────────────────────────────────────────────────
input group "════════ TRADE SETTINGS ════════"
input double   InpBaseLot        = 0.01;   // Base Lot Size
input bool     InpUseMartingale  = true;   // Enable Martingale
input double   InpMult2x         = 2.0;    // Multiplier after 1st loss
input double   InpMult4x         = 4.0;    // Multiplier after 2nd+ loss
input int      InpMaxConsecLoss  = 4;      // Max consecutive losses (safety halt)

input group "════════ TREND DETECTION ════════"
input ENUM_TIMEFRAMES InpTrendTF = PERIOD_H1;  // Trend Analysis Timeframe
input int      InpEMAFast        = 50;     // Fast EMA Period
input int      InpEMASlow        = 200;    // Slow EMA Period
input int      InpADXPeriod      = 14;     // ADX Period
input double   InpADXMinStrength = 20.0;  // Min ADX for trend confirmation

input group "════════ SCALPING SETTINGS ════════"
input int      InpTimerSec       = 30;     // Scalp Check Interval (seconds)
input int      InpRSIPeriod      = 7;      // RSI Period (M1)
input int      InpRSIOB          = 70;     // RSI Overbought Level
input int      InpRSIOS          = 30;     // RSI Oversold Level
input int      InpStochK         = 5;      // Stochastic %K
input int      InpStochD         = 3;      // Stochastic %D
input int      InpStochSlow      = 3;      // Stochastic Slowing

input group "════════ STOP LOSS ════════"
input bool     InpATRStopLoss    = true;   // ATR-based Smart SL
input int      InpATRPeriod      = 14;     // ATR Period
input double   InpATRSLMult      = 1.5;    // ATR SL Multiplier
input double   InpManualSLPts    = 50.0;  // Manual SL in Points (if ATR off)

input group "════════ TAKE PROFIT (3 LEVELS) ════════"
input double   InpTP1RR          = 1.0;    // TP Level 1 – R/R Ratio (move SL to BE)
input double   InpTP2RR          = 2.0;    // TP Level 2 – R/R Ratio (move SL to TP1)
input double   InpTP3RR          = 3.0;    // TP Level 3 – R/R Ratio (full exit)
input bool     InpUsePartialTP   = false;  // Close partial lots at TP1/TP2
input double   InpPartialTP1Pct  = 30.0;  // % to close at TP1
input double   InpPartialTP2Pct  = 30.0;  // % to close at TP2

input group "════════ TRAILING STOP ════════"
input bool     InpUseTrail       = true;   // Enable Trailing Stop
input double   InpTrailPts       = 15.0;  // Trail Distance (points)
input double   InpTrailStartPts  = 20.0;  // Start trailing after (points profit)

input group "════════ RISK MANAGEMENT ════════"
input double   InpMaxDDPct       = 10.0;  // Max Drawdown % (halt trading)
input int      InpMaxOpenTrades  = 1;      // Max simultaneous open trades

input group "════════ DISPLAY ════════"
input bool     InpShowLogo       = true;   // Show Logo Panel
input bool     InpShowInfoPanel  = true;   // Show Info Panel
input color    InpColorAccent1   = clrGold;         // Accent Color 1 (Gold)
input color    InpColorAccent2   = clrDodgerBlue;   // Accent Color 2 (Blue)
input color    InpColorProfit    = clrLimeGreen;    // Profit Color
input color    InpColorLoss      = clrOrangeRed;    // Loss Color

//──────────────────────────────────────────────────────────────────
//  CONSTANTS
//──────────────────────────────────────────────────────────────────
#define MAGIC  202412250
#define EA_VER "v2.0"
#define EA_NAME "PEDRAM SCALPER PRO"

//──────────────────────────────────────────────────────────────────
//  GLOBAL STATE
//──────────────────────────────────────────────────────────────────
CTrade         g_trade;
CPositionInfo  g_pos;

// Martingale state
int    g_consecLosses    = 0;
int    g_consecWins      = 0;
bool   g_haltedMaxDD     = false;
bool   g_haltedMaxLoss   = false;

// Statistics (in-session)
int    g_totalTrades     = 0;
int    g_winTrades       = 0;
int    g_lossTrades      = 0;
double g_totalProfit     = 0.0;
double g_maxDD           = 0.0;

// Timers & state
int    g_timerFired      = 0;
string g_lastSignal      = "—";
string g_trendLabel      = "—";

// TP tracking per ticket (3-level management)
// We track whether SL has been promoted to BE and to TP1 level
struct STPState
{
   ulong  ticket;
   bool   beSet;      // SL moved to break-even
   bool   tp1SLSet;   // SL moved to TP1 level
};
STPState g_tpState[];

// Indicator handles
int g_hEMAFast   = INVALID_HANDLE;
int g_hEMASlow   = INVALID_HANDLE;
int g_hADX       = INVALID_HANDLE;
int g_hRSI       = INVALID_HANDLE;
int g_hStoch     = INVALID_HANDLE;
int g_hATR       = INVALID_HANDLE;

//──────────────────────────────────────────────────────────────────
//  INIT
//──────────────────────────────────────────────────────────────────
int OnInit()
{
   g_trade.SetExpertMagicNumber(MAGIC);
   g_trade.SetDeviationInPoints(20);
   g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   g_trade.LogLevel(LOG_LEVEL_ERRORS);

   // Trend indicators on user-selected TF (default H1)
   g_hEMAFast = iMA(_Symbol, InpTrendTF, InpEMAFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEMASlow = iMA(_Symbol, InpTrendTF, InpEMASlow, 0, MODE_EMA, PRICE_CLOSE);
   g_hADX     = iADX(_Symbol, InpTrendTF, InpADXPeriod);

   // Scalp indicators on M1
   g_hRSI   = iRSI(_Symbol, PERIOD_M1, InpRSIPeriod, PRICE_CLOSE);
   g_hStoch = iStochastic(_Symbol, PERIOD_M1, InpStochK, InpStochD, InpStochSlow, MODE_SMA, STO_LOWHIGH);
   g_hATR   = iATR(_Symbol, PERIOD_M1, InpATRPeriod);

   if(g_hEMAFast == INVALID_HANDLE || g_hEMASlow == INVALID_HANDLE ||
      g_hADX     == INVALID_HANDLE || g_hRSI    == INVALID_HANDLE ||
      g_hStoch   == INVALID_HANDLE || g_hATR    == INVALID_HANDLE)
   {
      ReportError("OnInit", "Failed to create one or more indicator handles", GetLastError());
      return INIT_FAILED;
   }

   // UI
   if(InpShowLogo)      DrawLogo();
   if(InpShowInfoPanel) DrawInfoPanel();

   // Timer for 30-second scalp cycles
   EventSetTimer(InpTimerSec);

   Print(EA_NAME, " ", EA_VER, " initialized | Symbol: ", _Symbol,
         " | Trend TF: ", EnumToString(InpTrendTF),
         " | Base Lot: ", InpBaseLot);

   return INIT_SUCCEEDED;
}

//──────────────────────────────────────────────────────────────────
//  DEINIT
//──────────────────────────────────────────────────────────────────
void OnDeinit(const int reason)
{
   EventKillTimer();

   IndicatorRelease(g_hEMAFast);
   IndicatorRelease(g_hEMASlow);
   IndicatorRelease(g_hADX);
   IndicatorRelease(g_hRSI);
   IndicatorRelease(g_hStoch);
   IndicatorRelease(g_hATR);

   ObjectsDeleteAll(0, "PS_");
   Comment("");

   Print(EA_NAME, " deinitialized | Trades=", g_totalTrades,
         " Wins=", g_winTrades, " Losses=", g_lossTrades,
         " Net P/L=", DoubleToString(g_totalProfit, 2));
}

//──────────────────────────────────────────────────────────────────
//  TIMER — 30-second scalp cycle
//──────────────────────────────────────────────────────────────────
void OnTimer()
{
   g_timerFired++;

   if(g_haltedMaxDD || g_haltedMaxLoss)
   {
      RefreshPanel();
      return;
   }

   if(IsMaxDrawdownHit()) return;

   if(CountOwnTrades() >= InpMaxOpenTrades)
   {
      RefreshPanel();
      return;
   }

   int trend  = DetectTrend();
   int signal = (trend != 0) ? GetScalpSignal(trend) : 0;

   g_trendLabel = (trend == 1) ? "▲ UPTREND" : (trend == -1) ? "▼ DOWNTREND" : "─ SIDEWAYS";
   g_lastSignal = (signal == 1) ? "BUY ▶" : (signal == -1) ? "SELL ◀" : "WAIT";

   if(signal != 0 && CountOwnTrades() == 0)
      PlaceTrade(signal);

   RefreshPanel();
}

//──────────────────────────────────────────────────────────────────
//  TICK — trailing stop & TP management
//──────────────────────────────────────────────────────────────────
void OnTick()
{
   if(g_haltedMaxDD || g_haltedMaxLoss) return;

   ManageThreeLevelTP();
   if(InpUseTrail) ManageTrailingStop();
}

//──────────────────────────────────────────────────────────────────
//  TRADE TRANSACTION — Martingale state machine
//──────────────────────────────────────────────────────────────────
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest     &request,
                        const MqlTradeResult      &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;

   ulong deal = trans.deal;
   if(!HistoryDealSelect(deal)) return;
   if(HistoryDealGetInteger(deal, DEAL_MAGIC)  != MAGIC)  return;
   if(HistoryDealGetString(deal, DEAL_SYMBOL)  != _Symbol) return;

   ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT) return;

   double profit  = HistoryDealGetDouble(deal, DEAL_PROFIT);
   double swap    = HistoryDealGetDouble(deal, DEAL_SWAP);
   double comm    = HistoryDealGetDouble(deal, DEAL_COMMISSION);
   double net     = profit + swap + comm;

   g_totalTrades++;
   g_totalProfit += net;

   if(net > 0.0)  // WIN
   {
      g_winTrades++;
      g_consecLosses = 0;
      g_consecWins++;
      Print("[WIN  ] Net=", DoubleToString(net,2),
            " | Streak=", g_consecWins,
            " | Next lot=", DoubleToString(InpBaseLot,2), " (reset)");
   }
   else           // LOSS
   {
      g_lossTrades++;
      g_consecLosses++;
      g_consecWins = 0;

      double nextLot = CalcLot();
      string mult    = DoubleToString(nextLot / InpBaseLot, 1);

      Print("[LOSS ] Net=", DoubleToString(net,2),
            " | ConsecLoss=", g_consecLosses,
            " | Next lot=", DoubleToString(nextLot,2), " (", mult, "x)");

      if(g_consecLosses >= InpMaxConsecLoss)
      {
         g_haltedMaxLoss = true;
         string msg = "Safety halt: " + IntegerToString(g_consecLosses) +
                      " consecutive losses reached.";
         ReportError("Martingale Safety", msg, 0);
         Alert(EA_NAME + ": " + msg);
      }
   }

   // Remove TP tracking entry for this trade
   RemoveTPState(trans.position);
   RefreshPanel();
}

//══════════════════════════════════════════════════════════════════
//  CORE LOGIC
//══════════════════════════════════════════════════════════════════

//──────────────────────────────────────────────────────────────────
//  Detect overall trend using EMA50/200 + ADX on TrendTF
//  Returns  1 = Uptrend | -1 = Downtrend | 0 = No clear trend
//──────────────────────────────────────────────────────────────────
int DetectTrend()
{
   double emaF[3], emaS[3], adx[3];
   ArraySetAsSeries(emaF, true);
   ArraySetAsSeries(emaS, true);
   ArraySetAsSeries(adx,  true);

   if(CopyBuffer(g_hEMAFast, 0, 0, 3, emaF) < 3) return 0;
   if(CopyBuffer(g_hEMASlow, 0, 0, 3, emaS) < 3) return 0;
   if(CopyBuffer(g_hADX,     0, 0, 3, adx)  < 3) return 0;

   if(adx[0] < InpADXMinStrength) return 0;  // Weak / sideways

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(emaF[0] > emaS[0] && bid > emaF[0]) return  1; // Uptrend
   if(emaF[0] < emaS[0] && bid < emaF[0]) return -1; // Downtrend

   return 0;
}

//──────────────────────────────────────────────────────────────────
//  Get scalp entry signal aligned to trend
//  Returns  1 = Buy | -1 = Sell | 0 = No signal
//──────────────────────────────────────────────────────────────────
int GetScalpSignal(int trend)
{
   double rsi[3], stK[3], stD[3];
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(stK, true);
   ArraySetAsSeries(stD, true);

   if(CopyBuffer(g_hRSI,   0, 0, 3, rsi) < 3) return 0;
   if(CopyBuffer(g_hStoch, 0, 0, 3, stK) < 3) return 0;
   if(CopyBuffer(g_hStoch, 1, 0, 3, stD) < 3) return 0;

   bool rsiCrossUp   = (rsi[1] < InpRSIOS) && (rsi[0] >= InpRSIOS);
   bool rsiCrossDn   = (rsi[1] > InpRSIOB) && (rsi[0] <= InpRSIOB);
   bool stochCrossUp = (stK[1] < stD[1])   && (stK[0] >= stD[0]) && (stK[0] < 50.0);
   bool stochCrossDn = (stK[1] > stD[1])   && (stK[0] <= stD[0]) && (stK[0] > 50.0);

   if(trend == 1  && (rsiCrossUp || stochCrossUp)) return  1;
   if(trend == -1 && (rsiCrossDn || stochCrossDn)) return -1;

   return 0;
}

//──────────────────────────────────────────────────────────────────
//  Calculate lot size (Martingale state machine)
//──────────────────────────────────────────────────────────────────
double CalcLot()
{
   double lot = InpBaseLot;

   if(InpUseMartingale)
   {
      if(g_consecLosses == 1)       lot = InpBaseLot * InpMult2x;
      else if(g_consecLosses >= 2)  lot = InpBaseLot * InpMult4x;
   }

   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   lot = MathRound(lot / step) * step;
   lot = MathMax(minL, MathMin(maxL, lot));

   return NormalizeDouble(lot, 2);
}

//──────────────────────────────────────────────────────────────────
//  Place trade
//──────────────────────────────────────────────────────────────────
void PlaceTrade(int signal)
{
   double lot = CalcLot();

   // ATR for SL distance
   double atrBuf[1];
   ArraySetAsSeries(atrBuf, true);
   double slDist = InpManualSLPts * _Point;
   if(InpATRStopLoss && CopyBuffer(g_hATR, 0, 0, 1, atrBuf) > 0)
      slDist = atrBuf[0] * InpATRSLMult;

   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price, sl, tp;
   string comment = EA_NAME + " " + EA_VER;

   if(signal == 1) // BUY
   {
      price = ask;
      sl    = NormalizeDouble(price - slDist, _Digits);
      tp    = NormalizeDouble(price + slDist * InpTP3RR, _Digits);

      if(!g_trade.Buy(lot, _Symbol, price, sl, tp, comment))
      {
         ReportError("PlaceTrade BUY",
                     "Code=" + IntegerToString(g_trade.ResultRetcode()) +
                     " " + g_trade.ResultRetcodeDescription(),
                     g_trade.ResultRetcode());
         return;
      }
   }
   else // SELL
   {
      price = bid;
      sl    = NormalizeDouble(price + slDist, _Digits);
      tp    = NormalizeDouble(price - slDist * InpTP3RR, _Digits);

      if(!g_trade.Sell(lot, _Symbol, price, sl, tp, comment))
      {
         ReportError("PlaceTrade SELL",
                     "Code=" + IntegerToString(g_trade.ResultRetcode()) +
                     " " + g_trade.ResultRetcodeDescription(),
                     g_trade.ResultRetcode());
         return;
      }
   }

   // Record TP tracking state for this position
   ulong posTicket = g_trade.ResultDeal();
   // Use position ticket (deal may differ); find it
   Sleep(100);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(g_pos.SelectByIndex(i) && g_pos.Magic() == MAGIC && g_pos.Symbol() == _Symbol)
      {
         AddTPState(g_pos.Ticket());
         break;
      }
   }

   Print("[ORDER] ", (signal == 1 ? "BUY" : "SELL"),
         " | Lot=", DoubleToString(lot,2),
         " | Price=", DoubleToString(price, _Digits),
         " | SL=", DoubleToString(sl, _Digits),
         " | TP=", DoubleToString(tp, _Digits),
         " | ConsecLoss=", g_consecLosses,
         " | Mult=", DoubleToString(lot/InpBaseLot,1), "x");
}

//──────────────────────────────────────────────────────────────────
//  3-Level Take Profit Management (SL promotion)
//    TP1 hit → SL to break-even
//    TP2 hit → SL to TP1 price level
//    TP3     → set as initial hard TP (already in order)
//──────────────────────────────────────────────────────────────────
void ManageThreeLevelTP()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i))  continue;
      if(g_pos.Magic()  != MAGIC)  continue;
      if(g_pos.Symbol() != _Symbol) continue;

      ulong  ticket    = g_pos.Ticket();
      double open      = g_pos.PriceOpen();
      double curSL     = g_pos.StopLoss();
      double curTP     = g_pos.TakeProfit();
      double curPrice  = (g_pos.PositionType() == POSITION_TYPE_BUY) ?
                          SymbolInfoDouble(_Symbol, SYMBOL_BID) :
                          SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double slDist    = MathAbs(open - curSL);
      if(slDist < _Point) continue;

      double pnlPts  = (g_pos.PositionType() == POSITION_TYPE_BUY) ?
                        (curPrice - open) : (open - curPrice);

      // Find or create TP state
      int idx = FindTPState(ticket);
      if(idx < 0) { AddTPState(ticket); idx = FindTPState(ticket); }
      if(idx < 0) continue;

      bool isBuy = (g_pos.PositionType() == POSITION_TYPE_BUY);

      // ── Level 1: move SL to break-even (+ small buffer)
      if(!g_tpState[idx].beSet && pnlPts >= slDist * InpTP1RR)
      {
         double beSL = isBuy ? open + 2 * _Point : open - 2 * _Point;
         if((isBuy && beSL > curSL) || (!isBuy && beSL < curSL))
         {
            if(g_trade.PositionModify(ticket, beSL, curTP))
            {
               g_tpState[idx].beSet = true;
               Print("[TP1 ] Ticket=", ticket, " SL moved to break-even");
            }
         }
      }

      // ── Level 2: move SL to TP1 price level
      if(g_tpState[idx].beSet && !g_tpState[idx].tp1SLSet &&
         pnlPts >= slDist * InpTP2RR)
      {
         double tp1Price = isBuy ? open + slDist * InpTP1RR : open - slDist * InpTP1RR;
         if((isBuy && tp1Price > curSL) || (!isBuy && tp1Price < curSL))
         {
            if(g_trade.PositionModify(ticket, tp1Price, curTP))
            {
               g_tpState[idx].tp1SLSet = true;
               Print("[TP2 ] Ticket=", ticket, " SL promoted to TP1 level");
            }
         }
      }

      // Level 3 is the hard TP already placed in the order — no action needed
   }
}

//──────────────────────────────────────────────────────────────────
//  Smart Trailing Stop
//──────────────────────────────────────────────────────────────────
void ManageTrailingStop()
{
   double trailDist  = InpTrailPts      * _Point;
   double trailStart = InpTrailStartPts * _Point;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i))  continue;
      if(g_pos.Magic()  != MAGIC)  continue;
      if(g_pos.Symbol() != _Symbol) continue;

      ulong  ticket = g_pos.Ticket();
      double open   = g_pos.PriceOpen();
      double curSL  = g_pos.StopLoss();
      double curTP  = g_pos.TakeProfit();

      if(g_pos.PositionType() == POSITION_TYPE_BUY)
      {
         double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(bid - open < trailStart) continue;
         double newSL = NormalizeDouble(bid - trailDist, _Digits);
         if(newSL > curSL + _Point)
            g_trade.PositionModify(ticket, newSL, curTP);
      }
      else
      {
         double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         if(open - ask < trailStart) continue;
         double newSL = NormalizeDouble(ask + trailDist, _Digits);
         if(newSL < curSL - _Point)
            g_trade.PositionModify(ticket, newSL, curTP);
      }
   }
}

//──────────────────────────────────────────────────────────────────
//  Max drawdown guard
//──────────────────────────────────────────────────────────────────
bool IsMaxDrawdownHit()
{
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
   if(bal <= 0.0) return false;

   double dd = (bal - eq) / bal * 100.0;
   if(dd > g_maxDD) g_maxDD = dd;

   if(dd >= InpMaxDDPct)
   {
      if(!g_haltedMaxDD)
      {
         g_haltedMaxDD = true;
         string msg = "Max drawdown " + DoubleToString(dd, 2) + "% hit — trading halted.";
         ReportError("DrawdownGuard", msg, 0);
         Alert(EA_NAME + ": " + msg);
      }
      return true;
   }
   return false;
}

//══════════════════════════════════════════════════════════════════
//  TP STATE HELPERS
//══════════════════════════════════════════════════════════════════
void AddTPState(ulong ticket)
{
   int n = ArraySize(g_tpState);
   ArrayResize(g_tpState, n + 1);
   g_tpState[n].ticket   = ticket;
   g_tpState[n].beSet    = false;
   g_tpState[n].tp1SLSet = false;
}

int FindTPState(ulong ticket)
{
   for(int i = 0; i < ArraySize(g_tpState); i++)
      if(g_tpState[i].ticket == ticket) return i;
   return -1;
}

void RemoveTPState(ulong ticket)
{
   int n = ArraySize(g_tpState);
   for(int i = 0; i < n; i++)
   {
      if(g_tpState[i].ticket == ticket)
      {
         for(int j = i; j < n - 1; j++)
            g_tpState[j] = g_tpState[j + 1];
         ArrayResize(g_tpState, n - 1);
         return;
      }
   }
}

//══════════════════════════════════════════════════════════════════
//  UTILITIES
//══════════════════════════════════════════════════════════════════
int CountOwnTrades()
{
   int c = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(g_pos.SelectByIndex(i) && g_pos.Magic() == MAGIC && g_pos.Symbol() == _Symbol)
         c++;
   return c;
}

//──────────────────────────────────────────────────────────────────
//  Error reporter — logs to Experts tab & Journal
//──────────────────────────────────────────────────────────────────
void ReportError(string context, string message, uint code)
{
   string ts  = TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS);
   string out = StringFormat("[ERROR][%s][%s] %s (code=%u)", ts, context, message, code);
   Print(out);
}

//══════════════════════════════════════════════════════════════════
//  UI — LOGO PANEL
//══════════════════════════════════════════════════════════════════
void DrawLogo()
{
   // ── Outer frame
   CreateRect("PS_LogoFrame", 8, 8, 310, 88, C'15,18,38', InpColorAccent1, 2);

   // ── Gradient stripe (simulated with a thinner rect)
   CreateRect("PS_LogoStripe", 8, 8, 310, 6, InpColorAccent1, InpColorAccent1, 0);

   // ── Robot play-button icon
   CreateLabel("PS_LogoIcon",  22, 22, "▶", 34, InpColorAccent1);

   // ── EA name (large)
   CreateLabel("PS_LogoName",  68, 18, EA_NAME, 13, InpColorAccent1);

   // ── Owner line
   CreateLabel("PS_LogoOwner", 68, 40, "© Pedram Kamangar", 10, InpColorAccent2);

   // ── Sub-line
   CreateLabel("PS_LogoSub",   68, 58, "Smart Scalping Robot | MT5 | " + EA_VER, 8, clrSilver);

   // ── Status dot — updated dynamically
   CreateLabel("PS_LogoStatus", 68, 74, "● INITIALIZING", 8, clrGray);

   ChartRedraw(0);
}

//══════════════════════════════════════════════════════════════════
//  UI — INFO PANEL
//══════════════════════════════════════════════════════════════════
void DrawInfoPanel()
{
   int y0 = 105;
   int h  = 25;

   CreateRect("PS_PanelBG", 8, y0, 310, 260, C'8,10,25', C'40,44,70', 1);

   string ids[] = {
      "PS_PnTrend","PS_PnSignal","PS_PnLot","PS_PnMart",
      "PS_PnTrades","PS_PnWinRate","PS_PnProfit","PS_PnDD",
      "PS_PnTimer","PS_PnHalt"
   };
   for(int i = 0; i < ArraySize(ids); i++)
      CreateLabel(ids[i], 18, y0 + 8 + i * h, "—", 9, clrWhiteSmoke);

   RefreshPanel();
}

void RefreshPanel()
{
   if(!InpShowInfoPanel) return;

   // Status dot in logo
   string statusTxt;
   color  statusCol;
   if(g_haltedMaxDD || g_haltedMaxLoss)
   { statusTxt = "● HALTED"; statusCol = InpColorLoss; }
   else if(CountOwnTrades() > 0)
   { statusTxt = "● IN TRADE"; statusCol = clrOrange; }
   else
   { statusTxt = "● SCANNING"; statusCol = InpColorProfit; }

   SetLabelText("PS_LogoStatus", statusTxt, statusCol);

   double eq   = AccountInfoDouble(ACCOUNT_EQUITY);
   double bal  = AccountInfoDouble(ACCOUNT_BALANCE);
   double dd   = (bal > 0) ? (bal - eq) / bal * 100.0 : 0.0;

   double wr   = (g_totalTrades > 0) ? (double)g_winTrades / g_totalTrades * 100.0 : 0.0;
   double curLot = CalcLot();
   double mult   = (InpBaseLot > 0) ? curLot / InpBaseLot : 1.0;

   SetLabelText("PS_PnTrend",   "Trend   : " + g_trendLabel,
                (g_trendLabel == "▲ UPTREND") ? InpColorProfit :
                (g_trendLabel == "▼ DOWNTREND") ? InpColorLoss : clrGray);

   SetLabelText("PS_PnSignal",  "Signal  : " + g_lastSignal,
                (g_lastSignal == "BUY ▶") ? InpColorProfit :
                (g_lastSignal == "SELL ◀") ? InpColorLoss : clrSilver);

   SetLabelText("PS_PnLot",     "Lot     : " + DoubleToString(curLot, 2), clrWhiteSmoke);

   color martColor = (g_consecLosses == 0) ? clrWhiteSmoke :
                     (g_consecLosses == 1) ? clrOrange : InpColorLoss;
   SetLabelText("PS_PnMart",    "Martingale: " + DoubleToString(mult, 1) + "x  (loss=" +
                IntegerToString(g_consecLosses) + ")", martColor);

   SetLabelText("PS_PnTrades",  "Trades  : " + IntegerToString(g_totalTrades) +
                "  W:" + IntegerToString(g_winTrades) +
                "  L:" + IntegerToString(g_lossTrades), clrWhiteSmoke);

   SetLabelText("PS_PnWinRate", "Win Rate: " + DoubleToString(wr, 1) + "%",
                (wr >= 55) ? InpColorProfit : (wr >= 45) ? clrOrange : InpColorLoss);

   color profCol = (g_totalProfit >= 0) ? InpColorProfit : InpColorLoss;
   SetLabelText("PS_PnProfit",  "Net P/L : " + DoubleToString(g_totalProfit, 2), profCol);

   color ddCol = (dd < 3) ? InpColorProfit : (dd < 7) ? clrOrange : InpColorLoss;
   SetLabelText("PS_PnDD",      "Drawdown: " + DoubleToString(dd, 2) + "%  max:" +
                DoubleToString(g_maxDD, 2) + "%", ddCol);

   SetLabelText("PS_PnTimer",   "Pulses  : " + IntegerToString(g_timerFired) +
                "  " + TimeToString(TimeCurrent(), TIME_SECONDS), clrGray);

   string haltMsg = "";
   color  haltCol = clrGray;
   if(g_haltedMaxDD)
   { haltMsg = "⛔ HALTED — Max DD reached"; haltCol = InpColorLoss; }
   else if(g_haltedMaxLoss)
   { haltMsg = "⛔ HALTED — Max consec loss"; haltCol = InpColorLoss; }
   else
   { haltMsg = "✔  Running normally"; haltCol = InpColorProfit; }
   SetLabelText("PS_PnHalt", haltMsg, haltCol);

   ChartRedraw(0);
}

//──────────────────────────────────────────────────────────────────
//  UI helpers
//──────────────────────────────────────────────────────────────────
void CreateRect(string name, int x, int y, int w, int h,
                color bg, color border, int bw)
{
   ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,   x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,   y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE,        w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE,        h);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR,      bg);
   ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE,  BORDER_FLAT);
   ObjectSetInteger(0, name, OBJPROP_COLOR,        border);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,        bw);
   ObjectSetInteger(0, name, OBJPROP_CORNER,       CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_BACK,         false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE,   false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN,       true);
}

void CreateLabel(string name, int x, int y, string txt, int sz, color col)
{
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,  y);
   ObjectSetInteger(0, name, OBJPROP_CORNER,     CORNER_LEFT_UPPER);
   ObjectSetString(0,  name, OBJPROP_TEXT,       txt);
   ObjectSetString(0,  name, OBJPROP_FONT,       "Courier New");
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   sz);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      col);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN,     true);
}

void SetLabelText(string name, string txt, color col)
{
   ObjectSetString(0,  name, OBJPROP_TEXT,  txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
}
//+------------------------------------------------------------------+
