//+------------------------------------------------------------------+
//|                     PedramScalper_Pro.mq5                        |
//|           © 2024 Pedram Kamangar – All Rights Reserved           |
//|     Smart 30-Second Scalping Robot | Two-Phase + Martingale + 3TP|
//|                       Version 3.0                                |
//+------------------------------------------------------------------+
//
//  TWO-PHASE LOGIC:
//  ┌─────────────────────────────────────────────────────────────┐
//  │  PHASE 1 — AGGRESSIVE LAUNCH                                │
//  │  • Starts immediately on robot launch                       │
//  │  • No trend filter — trades in any market condition         │
//  │  • Runs in batches of InpBatchSize (default 5)              │
//  │  • If entire batch = all wins → continue next batch         │
//  │  • If ANY loss in batch → switch to Phase 2 immediately     │
//  │  • If total aggressive trades ≥ InpMaxAggressiveTrades (20) │
//  │    → automatically switch to Phase 2                        │
//  ├─────────────────────────────────────────────────────────────┤
//  │  PHASE 2 — SMART FILTERED                                   │
//  │  • Waits for proper trend: EMA50/200 + ADX confirmation     │
//  │  • Only enters in direction of confirmed trend              │
//  │  • Full 3-level TP + Martingale + trailing stop             │
//  └─────────────────────────────────────────────────────────────┘
//
#property copyright   "© Pedram Kamangar"
#property link        ""
#property version     "3.00"
#property description "Two-Phase Smart Scalping Robot"
#property description "Phase 1: 20 aggressive trades on launch"
#property description "Phase 2: trend-filtered smart trading"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//──────────────────────────────────────────────────────────────────
//  ENUMS
//──────────────────────────────────────────────────────────────────
enum ENUM_PHASE
{
   PHASE_AGGRESSIVE = 0,   // Phase 1 — Aggressive Launch
   PHASE_SMART      = 1,   // Phase 2 — Smart Filtered
};

//──────────────────────────────────────────────────────────────────
//  INPUTS
//──────────────────────────────────────────────────────────────────
input group "════════ PHASE 1 — AGGRESSIVE LAUNCH ════════"
input int    InpMaxAggressiveTrades = 20;  // Max trades in aggressive phase
input int    InpBatchSize           = 5;   // Batch size (all wins = next batch)
input bool   InpShowPhaseAlert      = true;// Alert when phase switches

input group "════════ TRADE SETTINGS ════════"
input double InpBaseLot             = 0.01;
input bool   InpUseMartingale       = true;
input double InpMult2x              = 2.0;
input double InpMult4x              = 4.0;
input int    InpMaxConsecLoss       = 4;

input group "════════ PHASE 2 — TREND DETECTION ════════"
input ENUM_TIMEFRAMES InpTrendTF    = PERIOD_H1;
input int    InpEMAFast             = 50;
input int    InpEMASlow             = 200;
input int    InpADXPeriod           = 14;
input double InpADXMin              = 20.0;

input group "════════ SCALPING SIGNALS ════════"
input int    InpTimerSec            = 30;
input int    InpRSIPeriod           = 7;
input int    InpRSIOB               = 70;
input int    InpRSIOS               = 30;
input int    InpStochK              = 5;
input int    InpStochD              = 3;
input int    InpStochSlow           = 3;

input group "════════ STOP LOSS ════════"
input bool   InpATRStopLoss         = true;
input int    InpATRPeriod           = 14;
input double InpATRSLMult           = 1.5;
input double InpManualSLPts         = 50.0;

input group "════════ TAKE PROFIT (3 LEVELS) ════════"
input double InpTP1RR               = 1.0;
input double InpTP2RR               = 2.0;
input double InpTP3RR               = 3.0;

input group "════════ TRAILING STOP ════════"
input bool   InpUseTrail            = true;
input double InpTrailPts            = 15.0;
input double InpTrailStartPts       = 20.0;

input group "════════ RISK MANAGEMENT ════════"
input double InpMaxDDPct            = 10.0;
input int    InpMaxOpenTrades       = 1;

input group "════════ DISPLAY ════════"
input bool   InpShowLogo            = true;
input bool   InpShowInfoPanel       = true;
input color  InpColorAccent1        = clrGold;
input color  InpColorAccent2        = clrDodgerBlue;
input color  InpColorProfit         = clrLimeGreen;
input color  InpColorLoss           = clrOrangeRed;
input color  InpColorPhase1         = clrOrange;
input color  InpColorPhase2         = clrDodgerBlue;

//──────────────────────────────────────────────────────────────────
//  CONSTANTS
//──────────────────────────────────────────────────────────────────
#define MAGIC    202412250
#define EA_VER   "v3.0"
#define EA_NAME  "PEDRAM SCALPER PRO"

//──────────────────────────────────────────────────────────────────
//  GLOBALS
//──────────────────────────────────────────────────────────────────
CTrade        g_trade;
CPositionInfo g_pos;

// ── Phase state
ENUM_PHASE g_phase              = PHASE_AGGRESSIVE;
int        g_aggressiveTotal    = 0;   // trades completed in Phase 1
int        g_batchWins          = 0;   // wins in current batch
int        g_batchCount         = 0;   // trades in current batch
bool       g_batchAllWin        = true;// current batch all-win flag

// ── Martingale
int    g_consecLosses   = 0;
int    g_consecWins     = 0;

// ── Risk guards
bool   g_haltedMaxDD    = false;
bool   g_haltedMaxLoss  = false;

// ── Session stats
int    g_totalTrades    = 0;
int    g_winTrades      = 0;
int    g_lossTrades     = 0;
double g_totalProfit    = 0.0;
double g_maxDD          = 0.0;

// ── UI
int    g_timerFired     = 0;
string g_lastSignal     = "—";
string g_trendLabel     = "—";

// ── TP state tracking
struct STPState { ulong ticket; bool beSet; bool tp1SLSet; };
STPState g_tpState[];

// ── Indicator handles
int g_hEMAFast = INVALID_HANDLE;
int g_hEMASlow = INVALID_HANDLE;
int g_hADX     = INVALID_HANDLE;
int g_hRSI     = INVALID_HANDLE;
int g_hStoch   = INVALID_HANDLE;
int g_hATR     = INVALID_HANDLE;

//──────────────────────────────────────────────────────────────────
//  INIT
//──────────────────────────────────────────────────────────────────
int OnInit()
{
   g_trade.SetExpertMagicNumber(MAGIC);
   g_trade.SetDeviationInPoints(20);
   g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   g_trade.LogLevel(LOG_LEVEL_ERRORS);

   g_hEMAFast = iMA(_Symbol, InpTrendTF, InpEMAFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hEMASlow = iMA(_Symbol, InpTrendTF, InpEMASlow, 0, MODE_EMA, PRICE_CLOSE);
   g_hADX     = iADX(_Symbol, InpTrendTF, InpADXPeriod);
   g_hRSI     = iRSI(_Symbol, PERIOD_M1, InpRSIPeriod, PRICE_CLOSE);
   g_hStoch   = iStochastic(_Symbol, PERIOD_M1, InpStochK, InpStochD, InpStochSlow, MODE_SMA, STO_LOWHIGH);
   g_hATR     = iATR(_Symbol, PERIOD_M1, InpATRPeriod);

   if(g_hEMAFast == INVALID_HANDLE || g_hEMASlow == INVALID_HANDLE ||
      g_hADX == INVALID_HANDLE || g_hRSI == INVALID_HANDLE ||
      g_hStoch == INVALID_HANDLE || g_hATR == INVALID_HANDLE)
   {
      ReportError("OnInit", "Indicator handle creation failed", GetLastError());
      return INIT_FAILED;
   }

   g_phase = PHASE_AGGRESSIVE;
   Print(EA_NAME, " ", EA_VER, " | Phase 1 AGGRESSIVE started | ",
         InpMaxAggressiveTrades, " trades max | batch=", InpBatchSize);

   if(InpShowLogo)      DrawLogo();
   if(InpShowInfoPanel) DrawInfoPanel();
   EventSetTimer(InpTimerSec);

   return INIT_SUCCEEDED;
}

//──────────────────────────────────────────────────────────────────
//  DEINIT
//──────────────────────────────────────────────────────────────────
void OnDeinit(const int reason)
{
   EventKillTimer();
   IndicatorRelease(g_hEMAFast); IndicatorRelease(g_hEMASlow);
   IndicatorRelease(g_hADX);    IndicatorRelease(g_hRSI);
   IndicatorRelease(g_hStoch);  IndicatorRelease(g_hATR);
   ObjectsDeleteAll(0, "PS_");
   Comment("");
}

//──────────────────────────────────────────────────────────────────
//  TIMER — main cycle every 30 seconds
//──────────────────────────────────────────────────────────────────
void OnTimer()
{
   g_timerFired++;

   if(g_haltedMaxDD || g_haltedMaxLoss) { RefreshPanel(); return; }
   if(IsMaxDrawdownHit()) return;
   if(CountOwnTrades() >= InpMaxOpenTrades) { RefreshPanel(); return; }

   // ── PHASE 1: Aggressive — fire without trend filter
   if(g_phase == PHASE_AGGRESSIVE)
   {
      int signal = GetScalpSignalAny();  // no trend requirement
      g_trendLabel = "▶ PHASE 1 AGGRESSIVE";
      g_lastSignal = (signal == 1) ? "BUY ▶" : (signal == -1) ? "SELL ◀" : "WAIT";

      if(signal != 0 && CountOwnTrades() == 0)
         PlaceTrade(signal);
   }
   // ── PHASE 2: Smart — wait for confirmed trend
   else
   {
      int trend  = DetectTrend();
      int signal = (trend != 0) ? GetScalpSignalWithTrend(trend) : 0;

      g_trendLabel = (trend == 1)  ? "▲ UPTREND"   :
                     (trend == -1) ? "▼ DOWNTREND" : "─ SIDEWAYS (waiting)";
      g_lastSignal = (signal == 1) ? "BUY ▶" : (signal == -1) ? "SELL ◀" : "WAIT";

      if(signal != 0 && CountOwnTrades() == 0)
         PlaceTrade(signal);
   }

   ManageThreeLevelTP();
   if(InpUseTrail) ManageTrailingStop();
   RefreshPanel();
}

void OnTick()
{
   if(g_haltedMaxDD || g_haltedMaxLoss) return;
   ManageThreeLevelTP();
   if(InpUseTrail) ManageTrailingStop();
}

//──────────────────────────────────────────────────────────────────
//  TRADE TRANSACTION — Martingale + Phase transition
//──────────────────────────────────────────────────────────────────
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest     &request,
                        const MqlTradeResult      &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;

   ulong deal = trans.deal;
   if(!HistoryDealSelect(deal)) return;
   if(HistoryDealGetInteger(deal, DEAL_MAGIC)  != MAGIC)   return;
   if(HistoryDealGetString(deal,  DEAL_SYMBOL) != _Symbol) return;

   ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT) return;

   double profit = HistoryDealGetDouble(deal, DEAL_PROFIT);
   double swap   = HistoryDealGetDouble(deal, DEAL_SWAP);
   double comm   = HistoryDealGetDouble(deal, DEAL_COMMISSION);
   double net    = profit + swap + comm;

   g_totalTrades++;
   g_totalProfit += net;

   bool isWin = (net > 0.0);

   // ── Update Martingale counters
   if(isWin)
   {
      g_winTrades++;
      g_consecLosses = 0;
      g_consecWins++;
   }
   else
   {
      g_lossTrades++;
      g_consecLosses++;
      g_consecWins = 0;
   }

   // ── Phase 1 batch tracking
   if(g_phase == PHASE_AGGRESSIVE)
   {
      g_aggressiveTotal++;
      g_batchCount++;

      if(!isWin)
         g_batchAllWin = false;

      bool batchComplete = (g_batchCount >= InpBatchSize);
      bool maxReached    = (g_aggressiveTotal >= InpMaxAggressiveTrades);

      if(!isWin)
      {
         // First loss in batch → switch to Phase 2 immediately
         SwitchToSmart("Loss in aggressive batch (trade #" +
                        IntegerToString(g_aggressiveTotal) + ")");
      }
      else if(batchComplete)
      {
         if(g_batchAllWin && !maxReached)
         {
            // All wins in batch → start new batch
            Print("[PHASE1] Batch ", g_aggressiveTotal / InpBatchSize,
                  " complete — ALL WINS — continuing next batch");
            g_batchCount   = 0;
            g_batchAllWin  = true;
         }
         else
         {
            // Batch had a loss, or max reached
            SwitchToSmart(maxReached ?
               "Max aggressive trades (" + IntegerToString(InpMaxAggressiveTrades) + ") reached" :
               "Batch complete with loss");
         }
      }
   }

   // ── Safety halts (any phase)
   if(g_consecLosses >= InpMaxConsecLoss && !g_haltedMaxLoss)
   {
      g_haltedMaxLoss = true;
      ReportError("Martingale Safety",
                  IntegerToString(g_consecLosses) + " consecutive losses — halted", 0);
      Alert(EA_NAME + ": Safety halt — " + IntegerToString(g_consecLosses) + " consecutive losses");
   }

   Print((isWin ? "[WIN ] " : "[LOSS] "),
         "Net=", DoubleToString(net,2),
         " | Phase=", (g_phase == PHASE_AGGRESSIVE ? "1-Aggr" : "2-Smart"),
         " | ConsecLoss=", g_consecLosses,
         " | NextLot=", DoubleToString(CalcLot(),2));

   RemoveTPState(trans.position);
   RefreshPanel();
}

//══════════════════════════════════════════════════════════════════
//  PHASE SWITCH
//══════════════════════════════════════════════════════════════════
void SwitchToSmart(string reason)
{
   if(g_phase == PHASE_SMART) return;

   g_phase = PHASE_SMART;
   string msg = "Switched to Phase 2 SMART — " + reason;
   Print("[PHASE] ", msg);
   if(InpShowPhaseAlert) Alert(EA_NAME + ": " + msg);
}

//══════════════════════════════════════════════════════════════════
//  SIGNAL GENERATORS
//══════════════════════════════════════════════════════════════════

// Phase 1: any signal regardless of trend
int GetScalpSignalAny()
{
   double rsi[3], stK[3], stD[3];
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(stK, true);
   ArraySetAsSeries(stD, true);

   if(CopyBuffer(g_hRSI,   0, 0, 3, rsi) < 3) return 0;
   if(CopyBuffer(g_hStoch, 0, 0, 3, stK) < 3) return 0;
   if(CopyBuffer(g_hStoch, 1, 0, 3, stD) < 3) return 0;

   bool rsiCrossUp = (rsi[1] < InpRSIOS) && (rsi[0] >= InpRSIOS);
   bool rsiCrossDn = (rsi[1] > InpRSIOB) && (rsi[0] <= InpRSIOB);
   bool stCrossUp  = (stK[1] < stD[1])   && (stK[0] >= stD[0]) && (stK[0] < 50.0);
   bool stCrossDn  = (stK[1] > stD[1])   && (stK[0] <= stD[0]) && (stK[0] > 50.0);

   if(rsiCrossUp || stCrossUp) return  1;
   if(rsiCrossDn || stCrossDn) return -1;

   return 0;
}

// Phase 2: signal must align with confirmed trend
int DetectTrend()
{
   double emaF[3], emaS[3], adx[3];
   ArraySetAsSeries(emaF, true);
   ArraySetAsSeries(emaS, true);
   ArraySetAsSeries(adx,  true);

   if(CopyBuffer(g_hEMAFast, 0, 0, 3, emaF) < 3) return 0;
   if(CopyBuffer(g_hEMASlow, 0, 0, 3, emaS) < 3) return 0;
   if(CopyBuffer(g_hADX,     0, 0, 3, adx)  < 3) return 0;

   if(adx[0] < InpADXMin) return 0;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(emaF[0] > emaS[0] && bid > emaF[0]) return  1;
   if(emaF[0] < emaS[0] && bid < emaF[0]) return -1;
   return 0;
}

int GetScalpSignalWithTrend(int trend)
{
   double rsi[3], stK[3], stD[3];
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(stK, true);
   ArraySetAsSeries(stD, true);

   if(CopyBuffer(g_hRSI,   0, 0, 3, rsi) < 3) return 0;
   if(CopyBuffer(g_hStoch, 0, 0, 3, stK) < 3) return 0;
   if(CopyBuffer(g_hStoch, 1, 0, 3, stD) < 3) return 0;

   bool rsiCrossUp = (rsi[1] < InpRSIOS) && (rsi[0] >= InpRSIOS);
   bool rsiCrossDn = (rsi[1] > InpRSIOB) && (rsi[0] <= InpRSIOB);
   bool stCrossUp  = (stK[1] < stD[1])   && (stK[0] >= stD[0]) && (stK[0] < 50.0);
   bool stCrossDn  = (stK[1] > stD[1])   && (stK[0] <= stD[0]) && (stK[0] > 50.0);

   if(trend ==  1 && (rsiCrossUp || stCrossUp)) return  1;
   if(trend == -1 && (rsiCrossDn || stCrossDn)) return -1;
   return 0;
}

//══════════════════════════════════════════════════════════════════
//  TRADE EXECUTION
//══════════════════════════════════════════════════════════════════
double CalcLot()
{
   double lot = InpBaseLot;
   if(InpUseMartingale)
   {
      if(g_consecLosses == 1)      lot = InpBaseLot * InpMult2x;
      else if(g_consecLosses >= 2) lot = InpBaseLot * InpMult4x;
   }
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lot = MathRound(lot / step) * step;
   return NormalizeDouble(MathMax(minL, MathMin(maxL, lot)), 2);
}

void PlaceTrade(int signal)
{
   double lot = CalcLot();

   double atrBuf[1];
   ArraySetAsSeries(atrBuf, true);
   double slDist = InpManualSLPts * _Point;
   if(InpATRStopLoss && CopyBuffer(g_hATR, 0, 0, 1, atrBuf) > 0)
      slDist = atrBuf[0] * InpATRSLMult;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price, sl, tp;
   string phase = (g_phase == PHASE_AGGRESSIVE) ? "P1-Aggr" : "P2-Smart";

   if(signal == 1)
   {
      price = ask;
      sl    = NormalizeDouble(price - slDist, _Digits);
      tp    = NormalizeDouble(price + slDist * InpTP3RR, _Digits);
      if(!g_trade.Buy(lot, _Symbol, price, sl, tp, EA_NAME + " " + EA_VER + " [" + phase + "]"))
      {
         ReportError("PlaceTrade BUY",
                     g_trade.ResultRetcodeDescription(), g_trade.ResultRetcode());
         return;
      }
   }
   else
   {
      price = bid;
      sl    = NormalizeDouble(price + slDist, _Digits);
      tp    = NormalizeDouble(price - slDist * InpTP3RR, _Digits);
      if(!g_trade.Sell(lot, _Symbol, price, sl, tp, EA_NAME + " " + EA_VER + " [" + phase + "]"))
      {
         ReportError("PlaceTrade SELL",
                     g_trade.ResultRetcodeDescription(), g_trade.ResultRetcode());
         return;
      }
   }

   // Track TP state
   Sleep(50);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(g_pos.SelectByIndex(i) && g_pos.Magic() == MAGIC && g_pos.Symbol() == _Symbol)
      { AddTPState(g_pos.Ticket()); break; }

   Print("[", phase, "] ", (signal==1?"BUY":"SELL"),
         " lot=", DoubleToString(lot,2),
         " sl=", DoubleToString(sl,_Digits),
         " tp=", DoubleToString(tp,_Digits),
         " | aggr#", g_aggressiveTotal+1,
         " batch=", g_batchCount+1, "/", InpBatchSize);
}

//══════════════════════════════════════════════════════════════════
//  3-LEVEL TP MANAGEMENT
//══════════════════════════════════════════════════════════════════
void ManageThreeLevelTP()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i))   continue;
      if(g_pos.Magic()  != MAGIC)   continue;
      if(g_pos.Symbol() != _Symbol) continue;

      ulong  ticket   = g_pos.Ticket();
      double open     = g_pos.PriceOpen();
      double curSL    = g_pos.StopLoss();
      double curTP    = g_pos.TakeProfit();
      bool   isBuy    = (g_pos.PositionType() == POSITION_TYPE_BUY);
      double curPrice = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                               : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double slDist   = MathAbs(open - curSL);
      if(slDist < _Point) continue;

      double pnlPts = isBuy ? (curPrice - open) : (open - curPrice);

      int idx = FindTPState(ticket);
      if(idx < 0) { AddTPState(ticket); idx = FindTPState(ticket); }
      if(idx < 0) continue;

      // TP1 → Break-even
      if(!g_tpState[idx].beSet && pnlPts >= slDist * InpTP1RR)
      {
         double beSL = isBuy ? open + 2*_Point : open - 2*_Point;
         if((isBuy && beSL > curSL) || (!isBuy && beSL < curSL))
            if(g_trade.PositionModify(ticket, beSL, curTP))
               g_tpState[idx].beSet = true;
      }

      // TP2 → SL to TP1 level
      if(g_tpState[idx].beSet && !g_tpState[idx].tp1SLSet && pnlPts >= slDist * InpTP2RR)
      {
         double tp1SL = isBuy ? open + slDist*InpTP1RR : open - slDist*InpTP1RR;
         if((isBuy && tp1SL > curSL) || (!isBuy && tp1SL < curSL))
            if(g_trade.PositionModify(ticket, tp1SL, curTP))
               g_tpState[idx].tp1SLSet = true;
      }
   }
}

//══════════════════════════════════════════════════════════════════
//  TRAILING STOP
//══════════════════════════════════════════════════════════════════
void ManageTrailingStop()
{
   double trailDist  = InpTrailPts      * _Point;
   double trailStart = InpTrailStartPts * _Point;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_pos.SelectByIndex(i))   continue;
      if(g_pos.Magic()  != MAGIC)   continue;
      if(g_pos.Symbol() != _Symbol) continue;

      ulong  ticket = g_pos.Ticket();
      double open   = g_pos.PriceOpen();
      double curSL  = g_pos.StopLoss();
      double curTP  = g_pos.TakeProfit();

      if(g_pos.PositionType() == POSITION_TYPE_BUY)
      {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(bid - open < trailStart) continue;
         double newSL = NormalizeDouble(bid - trailDist, _Digits);
         if(newSL > curSL + _Point) g_trade.PositionModify(ticket, newSL, curTP);
      }
      else
      {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         if(open - ask < trailStart) continue;
         double newSL = NormalizeDouble(ask + trailDist, _Digits);
         if(newSL < curSL - _Point) g_trade.PositionModify(ticket, newSL, curTP);
      }
   }
}

//══════════════════════════════════════════════════════════════════
//  DRAWDOWN GUARD
//══════════════════════════════════════════════════════════════════
bool IsMaxDrawdownHit()
{
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
   if(bal <= 0.0) return false;
   double dd = (bal - eq) / bal * 100.0;
   if(dd > g_maxDD) g_maxDD = dd;
   if(dd >= InpMaxDDPct && !g_haltedMaxDD)
   {
      g_haltedMaxDD = true;
      ReportError("DrawdownGuard",
                  "Max DD " + DoubleToString(dd,2) + "% hit — halted", 0);
      Alert(EA_NAME + ": Max drawdown hit — trading halted");
      return true;
   }
   return g_haltedMaxDD;
}

//══════════════════════════════════════════════════════════════════
//  TP STATE ARRAY
//══════════════════════════════════════════════════════════════════
void AddTPState(ulong t)
{ int n=ArraySize(g_tpState); ArrayResize(g_tpState,n+1);
  g_tpState[n].ticket=t; g_tpState[n].beSet=false; g_tpState[n].tp1SLSet=false; }

int FindTPState(ulong t)
{ for(int i=0;i<ArraySize(g_tpState);i++) if(g_tpState[i].ticket==t) return i; return -1; }

void RemoveTPState(ulong t)
{ int n=ArraySize(g_tpState);
  for(int i=0;i<n;i++) if(g_tpState[i].ticket==t)
  { for(int j=i;j<n-1;j++) g_tpState[j]=g_tpState[j+1]; ArrayResize(g_tpState,n-1); return; } }

int CountOwnTrades()
{ int c=0; for(int i=PositionsTotal()-1;i>=0;i--)
  if(g_pos.SelectByIndex(i)&&g_pos.Magic()==MAGIC&&g_pos.Symbol()==_Symbol) c++;
  return c; }

void ReportError(string ctx, string msg, uint code)
{ Print(StringFormat("[ERROR][%s][%s] %s (code=%u)",
        TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),ctx,msg,code)); }

//══════════════════════════════════════════════════════════════════
//  UI — LOGO
//══════════════════════════════════════════════════════════════════
void DrawLogo()
{
   CreateRect("PS_LogoFrame",  8, 8, 320, 90, C'15,18,38', InpColorAccent1, 2);
   CreateRect("PS_LogoStripe", 8, 8, 320,  5, InpColorAccent1, InpColorAccent1, 0);
   CreateLabel("PS_LogoIcon",  22,  20, "▶",  34, InpColorAccent1);
   CreateLabel("PS_LogoName",  70,  16, EA_NAME, 13, InpColorAccent1);
   CreateLabel("PS_LogoOwner", 70,  38, "© Pedram Kamangar", 10, InpColorAccent2);
   CreateLabel("PS_LogoSub",   70,  56, "Two-Phase Smart Scalping | MT5 | " + EA_VER, 8, clrSilver);
   CreateLabel("PS_LogoStatus",70,  73, "● INITIALIZING", 9, clrGray);
   ChartRedraw(0);
}

//══════════════════════════════════════════════════════════════════
//  UI — INFO PANEL
//══════════════════════════════════════════════════════════════════
void DrawInfoPanel()
{
   int y0 = 107;
   CreateRect("PS_PanelBG", 8, y0, 320, 290, C'8,10,25', C'40,44,70', 1);

   string ids[] = {
      "PS_PnPhase","PS_PnBatch","PS_PnTrend","PS_PnSignal",
      "PS_PnLot","PS_PnMart","PS_PnTrades","PS_PnWinRate",
      "PS_PnProfit","PS_PnDD","PS_PnTimer","PS_PnHalt"
   };
   for(int i=0; i<ArraySize(ids); i++)
   {
      CreateLabel(ids[i], 18, y0+8+i*23, "—", 9, clrWhiteSmoke);
   }
   RefreshPanel();
}

void RefreshPanel()
{
   if(!InpShowInfoPanel) return;

   bool phase1 = (g_phase == PHASE_AGGRESSIVE);

   // Status dot in logo
   string sTxt; color sCol;
   if(g_haltedMaxDD||g_haltedMaxLoss) { sTxt="● HALTED";    sCol=InpColorLoss; }
   else if(CountOwnTrades()>0)        { sTxt="● IN TRADE";  sCol=clrOrange; }
   else if(phase1)                    { sTxt="● AGGRESSIVE"; sCol=InpColorPhase1; }
   else                               { sTxt="● SMART";     sCol=InpColorPhase2; }
   SetLabelText("PS_LogoStatus", sTxt, sCol);

   // Phase line
   string phaseStr = phase1 ?
      "PHASE 1 — AGGRESSIVE (" + IntegerToString(g_aggressiveTotal) + "/" +
       IntegerToString(InpMaxAggressiveTrades) + " trades)" :
      "PHASE 2 — SMART FILTERED";
   SetLabelText("PS_PnPhase", phaseStr, phase1 ? InpColorPhase1 : InpColorPhase2);

   // Batch progress (Phase 1 only)
   string batchStr = phase1 ?
      "Batch : " + IntegerToString(g_batchCount) + "/" + IntegerToString(InpBatchSize) +
      "  wins=" + IntegerToString(g_batchWins) +
      (g_batchAllWin ? "  ✔ all-win" : "  ✗ loss") :
      "Batch : — (smart mode)";
   SetLabelText("PS_PnBatch", batchStr, phase1 ? clrOrange : clrGray);

   SetLabelText("PS_PnTrend", "Trend  : " + g_trendLabel,
      (g_trendLabel=="▲ UPTREND") ? InpColorProfit :
      (g_trendLabel=="▼ DOWNTREND") ? InpColorLoss : clrGray);

   SetLabelText("PS_PnSignal","Signal : " + g_lastSignal,
      (g_lastSignal=="BUY ▶") ? InpColorProfit :
      (g_lastSignal=="SELL ◀") ? InpColorLoss : clrSilver);

   double curLot = CalcLot();
   double mult   = (InpBaseLot>0) ? curLot/InpBaseLot : 1.0;
   SetLabelText("PS_PnLot", "Lot    : " + DoubleToString(curLot,2), clrWhiteSmoke);

   color mc = (g_consecLosses==0)?clrWhiteSmoke:(g_consecLosses==1)?clrOrange:InpColorLoss;
   SetLabelText("PS_PnMart",
      "Martingale: "+DoubleToString(mult,1)+"x  (consec loss="+IntegerToString(g_consecLosses)+")", mc);

   SetLabelText("PS_PnTrades",
      "Trades : "+IntegerToString(g_totalTrades)+"  W:"+IntegerToString(g_winTrades)+
      "  L:"+IntegerToString(g_lossTrades), clrWhiteSmoke);

   double wr=(g_totalTrades>0)?(double)g_winTrades/g_totalTrades*100.0:0.0;
   SetLabelText("PS_PnWinRate","Win Rate: "+DoubleToString(wr,1)+"%",
      (wr>=55)?InpColorProfit:(wr>=45)?clrOrange:InpColorLoss);

   double bal=AccountInfoDouble(ACCOUNT_BALANCE);
   double eq =AccountInfoDouble(ACCOUNT_EQUITY);
   double dd =(bal>0)?(bal-eq)/bal*100.0:0.0;

   SetLabelText("PS_PnProfit","Net P/L : "+DoubleToString(g_totalProfit,2),
      (g_totalProfit>=0)?InpColorProfit:InpColorLoss);
   SetLabelText("PS_PnDD","Drawdown: "+DoubleToString(dd,2)+"%  max:"+DoubleToString(g_maxDD,2)+"%",
      (dd<3)?InpColorProfit:(dd<7)?clrOrange:InpColorLoss);
   SetLabelText("PS_PnTimer","Pulses  : "+IntegerToString(g_timerFired)+"  "+
      TimeToString(TimeCurrent(),TIME_SECONDS), clrGray);

   string hMsg; color hCol;
   if(g_haltedMaxDD)     { hMsg="⛔ HALTED — Max DD";       hCol=InpColorLoss; }
   else if(g_haltedMaxLoss){ hMsg="⛔ HALTED — Max Loss Streak"; hCol=InpColorLoss; }
   else if(phase1)         { hMsg="▶ Aggressive: fire on any signal"; hCol=InpColorPhase1; }
   else                    { hMsg="✔ Smart: waiting for trend";       hCol=InpColorPhase2; }
   SetLabelText("PS_PnHalt", hMsg, hCol);

   ChartRedraw(0);
}

//══════════════════════════════════════════════════════════════════
//  UI HELPERS
//══════════════════════════════════════════════════════════════════
void CreateRect(string nm,int x,int y,int w,int h,color bg,color bd,int bw)
{
   ObjectCreate(0,nm,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,nm,OBJPROP_XDISTANCE,x);  ObjectSetInteger(0,nm,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,nm,OBJPROP_XSIZE,w);       ObjectSetInteger(0,nm,OBJPROP_YSIZE,h);
   ObjectSetInteger(0,nm,OBJPROP_BGCOLOR,bg);    ObjectSetInteger(0,nm,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(0,nm,OBJPROP_COLOR,bd);      ObjectSetInteger(0,nm,OBJPROP_WIDTH,bw);
   ObjectSetInteger(0,nm,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,nm,OBJPROP_BACK,false);    ObjectSetInteger(0,nm,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,nm,OBJPROP_HIDDEN,true);
}
void CreateLabel(string nm,int x,int y,string txt,int sz,color col)
{
   ObjectCreate(0,nm,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,nm,OBJPROP_XDISTANCE,x);  ObjectSetInteger(0,nm,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,nm,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetString(0,nm,OBJPROP_TEXT,txt);       ObjectSetString(0,nm,OBJPROP_FONT,"Courier New");
   ObjectSetInteger(0,nm,OBJPROP_FONTSIZE,sz);   ObjectSetInteger(0,nm,OBJPROP_COLOR,col);
   ObjectSetInteger(0,nm,OBJPROP_SELECTABLE,false); ObjectSetInteger(0,nm,OBJPROP_HIDDEN,true);
}
void SetLabelText(string nm,string txt,color col)
{ ObjectSetString(0,nm,OBJPROP_TEXT,txt); ObjectSetInteger(0,nm,OBJPROP_COLOR,col); }
//+------------------------------------------------------------------+
