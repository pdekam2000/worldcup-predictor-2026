//+------------------------------------------------------------------+
//| PedramKamangar_30s_SmartScalper.mq5                             |
//| Semi/full automatic MT5 Expert Advisor for 30-second scalping.   |
//| Owner display: Pedram Kamangar                                   |
//+------------------------------------------------------------------+
#property strict
#property copyright "Pedram Kamangar"
#property link      "https://www.metatrader5.com"
#property version   "1.00"
#property description "30-second trend scalper with smart TP, smart SL, recovery sizing, panel, and error logging."

#include <Trade/Trade.mqh>

enum TrendDirection
{
   TREND_DOWN = -1,
   TREND_FLAT = 0,
   TREND_UP = 1
};

input string          InpOwnerName              = "Pedram Kamangar";
input string          InpBrokerTag              = "BazarnForex";
input ulong           InpMagicNumber            = 30072026;
input bool            InpEnableAutoTrading      = true;
input bool            InpSignalOnlyMode         = false;
input bool            InpShowAlerts             = true;

input int             InpScalpWindowSeconds     = 30;
input int             InpMaxPositionHoldSeconds = 30;
input int             InpMinSecondsAfterClose   = 8;
input double          InpBaseLot                = 0.01;
input double          InpMaxLot                 = 1.00;
input double          InpRecoveryMultiplier     = 2.0;
input int             InpMaxRecoverySteps       = 3;

input ENUM_TIMEFRAMES InpTrendTimeframe         = PERIOD_M5;
input ENUM_TIMEFRAMES InpEntryTimeframe         = PERIOD_M1;
input int             InpTrendFastEma           = 21;
input int             InpTrendSlowEma           = 55;
input int             InpEntryEma               = 9;
input int             InpAdxPeriod              = 14;
input double          InpMinAdx                 = 18.0;
input int             InpRsiPeriod              = 14;
input double          InpBuyRsiMin              = 52.0;
input double          InpBuyRsiMax              = 72.0;
input double          InpSellRsiMin             = 28.0;
input double          InpSellRsiMax             = 48.0;

input int             InpAtrPeriod              = 14;
input double          InpStopAtrMultiplier      = 1.35;
input double          InpTp1AtrMultiplier       = 0.55;
input double          InpTp2AtrMultiplier       = 0.95;
input double          InpTp3AtrMultiplier       = 1.55;
input double          InpTrailAtrMultiplier     = 0.75;
input double          InpBreakEvenBufferPoints  = 8.0;
input double          InpTp1ClosePercent        = 33.0;
input double          InpTp2ClosePercent        = 50.0;

input int             InpMaxSpreadPoints        = 28;
input int             InpSlippagePoints         = 10;
input double          InpMaxDailyLossPercent    = 5.0;
input double          InpMaxDrawdownPercent     = 12.0;
input bool            InpAllowNewTradeAfterLoss = true;

input color           InpPanelBackColor         = clrBlack;
input color           InpPanelTitleColor        = clrDeepSkyBlue;
input color           InpPanelProfitColor       = clrLime;
input color           InpPanelWarningColor      = clrOrange;
input color           InpPanelErrorColor        = clrTomato;
input string          InpErrorLogFile           = "PedramKamangar_30s_SmartScalper_errors.csv";

CTrade trade;

int      handleTrendFast = INVALID_HANDLE;
int      handleTrendSlow = INVALID_HANDLE;
int      handleEntryEma  = INVALID_HANDLE;
int      handleAdx       = INVALID_HANDLE;
int      handleAtr       = INVALID_HANDLE;
int      handleRsi       = INVALID_HANDLE;

long     lastSignalCycle = -1;
datetime lastCloseTime   = 0;
int      lossStreak      = 0;
double   peakEquity      = 0.0;
double   dayStartEquity  = 0.0;
int      dayCode         = 0;
string   panelPrefix     = "PK30SS_";
string   globalPrefix    = "";

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(InpScalpWindowSeconds <= 0)
   {
      ReportError("Invalid scalp window seconds; must be greater than zero.", 1001);
      return INIT_PARAMETERS_INCORRECT;
   }

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   globalPrefix = BuildGlobalPrefix();
   LoadPersistentState();

   handleTrendFast = iMA(_Symbol, InpTrendTimeframe, InpTrendFastEma, 0, MODE_EMA, PRICE_CLOSE);
   handleTrendSlow = iMA(_Symbol, InpTrendTimeframe, InpTrendSlowEma, 0, MODE_EMA, PRICE_CLOSE);
   handleEntryEma  = iMA(_Symbol, InpEntryTimeframe, InpEntryEma, 0, MODE_EMA, PRICE_CLOSE);
   handleAdx       = iADX(_Symbol, InpTrendTimeframe, InpAdxPeriod);
   handleAtr       = iATR(_Symbol, InpEntryTimeframe, InpAtrPeriod);
   handleRsi       = iRSI(_Symbol, InpEntryTimeframe, InpRsiPeriod, PRICE_CLOSE);

   if(handleTrendFast == INVALID_HANDLE || handleTrendSlow == INVALID_HANDLE ||
      handleEntryEma == INVALID_HANDLE || handleAdx == INVALID_HANDLE ||
      handleAtr == INVALID_HANDLE || handleRsi == INVALID_HANDLE)
   {
      ReportError("Failed to create one or more indicator handles.", GetLastError());
      return INIT_FAILED;
   }

   EventSetTimer(1);
   CreatePanel();
   UpdatePanel("Starting", InpPanelWarningColor);
   Print("Pedram Kamangar 30s SmartScalper initialized for ", _Symbol, " on ", InpBrokerTag,
         " / server=", AccountInfoString(ACCOUNT_SERVER));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   ReleaseIndicator(handleTrendFast);
   ReleaseIndicator(handleTrendSlow);
   ReleaseIndicator(handleEntryEma);
   ReleaseIndicator(handleAdx);
   ReleaseIndicator(handleAtr);
   ReleaseIndicator(handleRsi);
   SavePersistentState();
   DeletePanel();
}

//+------------------------------------------------------------------+
//| Timer gives stable 30-second cadence even on quiet ticks.         |
//+------------------------------------------------------------------+
void OnTimer()
{
   ManageOpenPositions();
   EvaluateThirtySecondCycle();
   UpdatePanel("Running", InpPanelProfitColor);
}

//+------------------------------------------------------------------+
//| Tick handler keeps stop management reactive.                      |
//+------------------------------------------------------------------+
void OnTick()
{
   ManageOpenPositions();
}

//+------------------------------------------------------------------+
//| Track closed trades and update recovery lot state.                |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;

   if(!HistoryDealSelect(trans.deal))
      return;

   string symbol = HistoryDealGetString(trans.deal, DEAL_SYMBOL);
   long magic = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
   ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);

   if(symbol != _Symbol || (ulong)magic != InpMagicNumber)
      return;
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT)
      return;

   ulong dealPositionId = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   if(IsMarkedPartialClose(trans.position) || IsMarkedPartialClose(dealPositionId))
      return;

   double netProfit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
                    + HistoryDealGetDouble(trans.deal, DEAL_SWAP)
                    + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);

   lastCloseTime = TimeCurrent();

   if(netProfit > 0.0)
   {
      lossStreak = 0;
      SavePersistentState();
      Print("Winning trade closed. Recovery size reset to base lot.");
   }
   else if(netProfit < 0.0)
   {
      lossStreak = (lossStreak + 1 > InpMaxRecoverySteps) ? InpMaxRecoverySteps : lossStreak + 1;
      SavePersistentState();
      Print("Losing trade closed. Next recovery step=", lossStreak,
            " next lot=", DoubleToString(NextLot(), 2));
   }
}

void EvaluateThirtySecondCycle()
{
   datetime now = TimeCurrent();
   long cycle = (long)(now / InpScalpWindowSeconds);
   if(cycle == lastSignalCycle)
      return;

   lastSignalCycle = cycle;

   if(HasOpenPosition())
      return;

   if((now - lastCloseTime) < InpMinSecondsAfterClose)
      return;

   if(!RiskGuardsAllowTrading())
      return;

   if(!InpAllowNewTradeAfterLoss && lossStreak > 0)
   {
      UpdatePanel("Paused after loss", InpPanelWarningColor);
      return;
   }

   if(!IndicatorsReady())
      return;

   if(CurrentSpreadPoints() > InpMaxSpreadPoints)
   {
      UpdatePanel("Spread filter", InpPanelWarningColor);
      return;
   }

   TrendDirection trend = DetectTrend();
   if(trend == TREND_FLAT)
      return;

   if(!EntryFilterAllows(trend))
      return;

   OpenScalpTrade(trend);
}

bool IndicatorsReady()
{
   if(BarsCalculated(handleTrendFast) < InpTrendSlowEma ||
      BarsCalculated(handleTrendSlow) < InpTrendSlowEma ||
      BarsCalculated(handleEntryEma) < InpEntryEma ||
      BarsCalculated(handleAdx) < InpAdxPeriod ||
      BarsCalculated(handleAtr) < InpAtrPeriod ||
      BarsCalculated(handleRsi) < InpRsiPeriod)
   {
      return false;
   }
   return true;
}

TrendDirection DetectTrend()
{
   double fast[];
   double slow[];
   double adx[];
   ArrayResize(fast, 3);
   ArrayResize(slow, 3);
   ArrayResize(adx, 2);
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(slow, true);
   ArraySetAsSeries(adx, true);

   if(CopyBuffer(handleTrendFast, 0, 0, 3, fast) < 3 ||
      CopyBuffer(handleTrendSlow, 0, 0, 3, slow) < 3 ||
      CopyBuffer(handleAdx, 0, 0, 2, adx) < 2)
   {
      ReportError("Failed to read trend indicator buffers.", GetLastError());
      return TREND_FLAT;
   }

   bool fastRising = fast[0] > fast[1] && fast[1] >= fast[2];
   bool fastFalling = fast[0] < fast[1] && fast[1] <= fast[2];

   if(adx[0] >= InpMinAdx && fast[0] > slow[0] && fastRising)
      return TREND_UP;
   if(adx[0] >= InpMinAdx && fast[0] < slow[0] && fastFalling)
      return TREND_DOWN;

   return TREND_FLAT;
}

bool EntryFilterAllows(const TrendDirection trend)
{
   double ema[];
   double rsi[];
   ArrayResize(ema, 2);
   ArrayResize(rsi, 2);
   ArraySetAsSeries(ema, true);
   ArraySetAsSeries(rsi, true);

   if(CopyBuffer(handleEntryEma, 0, 0, 2, ema) < 2 ||
      CopyBuffer(handleRsi, 0, 0, 2, rsi) < 2)
   {
      ReportError("Failed to read entry indicator buffers.", GetLastError());
      return false;
   }

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   if(trend == TREND_UP)
      return ask > ema[0] && rsi[0] >= InpBuyRsiMin && rsi[0] <= InpBuyRsiMax;

   if(trend == TREND_DOWN)
      return bid < ema[0] && rsi[0] >= InpSellRsiMin && rsi[0] <= InpSellRsiMax;

   return false;
}

void OpenScalpTrade(const TrendDirection trend)
{
   double atr = CurrentAtr();
   if(atr <= 0.0)
      return;

   double lot = NextLot();
   double stopDistance = SmartStopDistance(atr);
   double tpDistance = atr * InpTp3AtrMultiplier;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price = trend == TREND_UP ? ask : bid;
   double sl = trend == TREND_UP ? price - stopDistance : price + stopDistance;
   double tp = trend == TREND_UP ? price + tpDistance : price - tpDistance;

   sl = NormalizeDouble(sl, _Digits);
   tp = NormalizeDouble(tp, _Digits);

   string side = trend == TREND_UP ? "BUY" : "SELL";
   string comment = "PK30 SmartScalper " + InpBrokerTag;
   string signalMessage = StringFormat("%s signal %s lot=%.2f recovery_step=%d", _Symbol, side, lot, lossStreak);

   if(InpShowAlerts)
      Alert(signalMessage);
   Print(signalMessage);

   if(InpSignalOnlyMode || !InpEnableAutoTrading)
   {
      UpdatePanel("Signal only: " + side, InpPanelWarningColor);
      return;
   }

   if(!TerminalTradeAllowed())
   {
      ReportError("Auto trading is disabled in terminal or EA settings.", 1002);
      UpdatePanel("Trading disabled", InpPanelErrorColor);
      return;
   }

   bool ok = false;
   if(trend == TREND_UP)
      ok = trade.Buy(lot, _Symbol, 0.0, sl, tp, comment);
   else
      ok = trade.Sell(lot, _Symbol, 0.0, sl, tp, comment);

   if(!ok)
   {
      int code = (int)trade.ResultRetcode();
      ReportError("Order send failed: " + trade.ResultRetcodeDescription(), code);
      UpdatePanel("Order error", InpPanelErrorColor);
   }
   else
   {
      UpdatePanel("Opened " + side, InpPanelProfitColor);
   }
}

void ManageOpenPositions()
{
   double atr = CurrentAtr();
   if(atr <= 0.0)
      return;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol ||
         (ulong)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
      {
         continue;
      }

      ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentTp = PositionGetDouble(POSITION_TP);
      double volume = PositionGetDouble(POSITION_VOLUME);
      datetime openedAt = (datetime)PositionGetInteger(POSITION_TIME);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double marketPrice = type == POSITION_TYPE_BUY ? bid : ask;
      double profitDistance = type == POSITION_TYPE_BUY ? marketPrice - openPrice : openPrice - marketPrice;

      int stage = PositionStage(ticket);
      double tp1Distance = atr * InpTp1AtrMultiplier;
      double tp2Distance = atr * InpTp2AtrMultiplier;

      if(stage < 1 && profitDistance >= tp1Distance)
      {
         TryPartialClose(ticket, volume, InpTp1ClosePercent);
         MoveStopToBreakEven(ticket, type, openPrice, currentTp);
         SetPositionStage(ticket, 1);
         stage = 1;
      }

      if(stage < 2 && profitDistance >= tp2Distance)
      {
         if(PositionSelectByTicket(ticket))
            volume = PositionGetDouble(POSITION_VOLUME);

         TryPartialClose(ticket, volume, InpTp2ClosePercent);
         LockProfitStop(ticket, type, openPrice, currentTp, atr);
         SetPositionStage(ticket, 2);
         stage = 2;
      }

      if(stage >= 2)
         TrailSmartStop(ticket, type, currentTp, atr);

      if(InpMaxPositionHoldSeconds > 0 && (TimeCurrent() - openedAt) >= InpMaxPositionHoldSeconds)
      {
         if(!trade.PositionClose(ticket))
         {
            ReportError("Timed scalp close failed: " + trade.ResultRetcodeDescription(),
                        (int)trade.ResultRetcode());
         }
         else
         {
            GlobalVariableDel(PositionStageKey(ticket));
         }
      }
   }
}

void TryPartialClose(const ulong ticket, const double currentVolume, const double percent)
{
   double minVolume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double closeVolume = NormalizeVolume(currentVolume * percent / 100.0);

   if(closeVolume < minVolume || (currentVolume - closeVolume) < minVolume)
      return;

   GlobalVariableSet(PendingPartialKey(ticket), (double)TimeCurrent());
   if(!trade.PositionClosePartial(ticket, closeVolume))
   {
      GlobalVariableDel(PendingPartialKey(ticket));
      ReportError("Partial close failed: " + trade.ResultRetcodeDescription(), (int)trade.ResultRetcode());
   }
}

void MoveStopToBreakEven(const ulong ticket,
                         const ENUM_POSITION_TYPE type,
                         const double openPrice,
                         const double currentTp)
{
   double buffer = InpBreakEvenBufferPoints * _Point;
   double newSl = type == POSITION_TYPE_BUY ? openPrice + buffer : openPrice - buffer;
   ModifyStopIfBetter(ticket, type, newSl, currentTp);
}

void LockProfitStop(const ulong ticket,
                    const ENUM_POSITION_TYPE type,
                    const double openPrice,
                    const double currentTp,
                    const double atr)
{
   double lockDistance = atr * MathMax(InpTp1AtrMultiplier * 0.50, 0.20);
   double newSl = type == POSITION_TYPE_BUY ? openPrice + lockDistance : openPrice - lockDistance;
   ModifyStopIfBetter(ticket, type, newSl, currentTp);
}

void TrailSmartStop(const ulong ticket,
                    const ENUM_POSITION_TYPE type,
                    const double currentTp,
                    const double atr)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double trailDistance = MathMax(atr * InpTrailAtrMultiplier, SmartStopDistance(atr) * 0.35);
   double newSl = type == POSITION_TYPE_BUY ? bid - trailDistance : ask + trailDistance;
   ModifyStopIfBetter(ticket, type, newSl, currentTp);
}

void ModifyStopIfBetter(const ulong ticket,
                        const ENUM_POSITION_TYPE type,
                        const double requestedSl,
                        const double currentTp)
{
   if(!PositionSelectByTicket(ticket))
      return;

   double currentSl = PositionGetDouble(POSITION_SL);
   double normalizedSl = NormalizeDouble(requestedSl, _Digits);

   if(!StopRespectsBrokerLimits(type, normalizedSl))
      return;

   bool improves = false;
   if(type == POSITION_TYPE_BUY)
      improves = currentSl == 0.0 || normalizedSl > currentSl + _Point;
   else
      improves = currentSl == 0.0 || normalizedSl < currentSl - _Point;

   if(!improves)
      return;

   if(!trade.PositionModify(ticket, normalizedSl, currentTp))
   {
      ReportError("Stop modification failed: " + trade.ResultRetcodeDescription(), (int)trade.ResultRetcode());
   }
}

bool StopRespectsBrokerLimits(const ENUM_POSITION_TYPE type, const double sl)
{
   int stopLevel = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freezeLevel = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double minDistance = (MathMax(stopLevel, freezeLevel) + 2) * _Point;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   if(type == POSITION_TYPE_BUY)
      return (bid - sl) >= minDistance;

   return (sl - ask) >= minDistance;
}

double SmartStopDistance(const double atr)
{
   int stopLevel = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freezeLevel = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double brokerMin = (MathMax(stopLevel, freezeLevel) + CurrentSpreadPoints() + 3) * _Point;
   double atrStop = atr * InpStopAtrMultiplier;
   return MathMax(atrStop, brokerMin);
}

double CurrentAtr()
{
   double atr[];
   ArrayResize(atr, 1);
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(handleAtr, 0, 0, 1, atr) != 1)
      return 0.0;
   return atr[0];
}

int CurrentSpreadPoints()
{
   return (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
}

double NextLot()
{
   int cappedStep = lossStreak;
   if(cappedStep < 0)
      cappedStep = 0;
   if(cappedStep > InpMaxRecoverySteps)
      cappedStep = InpMaxRecoverySteps;

   double lot = InpBaseLot * MathPow(InpRecoveryMultiplier, cappedStep);
   lot = MathMin(lot, InpMaxLot);
   return NormalizeVolume(lot);
}

double NormalizeVolume(double volume)
{
   double minVolume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxVolume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(step <= 0.0)
      step = minVolume;

   volume = MathMax(minVolume, MathMin(volume, maxVolume));
   volume = MathFloor((volume - minVolume) / step + 0.0000001) * step + minVolume;
   return NormalizeDouble(volume, VolumeDigits(step));
}

int VolumeDigits(const double step)
{
   int digits = 0;
   double scaled = step;
   while(digits < 8 && MathAbs(scaled - MathRound(scaled)) > 0.0000001)
   {
      scaled *= 10.0;
      digits++;
   }
   return digits;
}

bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         return true;
      }
   }
   return false;
}

bool TerminalTradeAllowed()
{
   return (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) &&
          (bool)MQLInfoInteger(MQL_TRADE_ALLOWED) &&
          (bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED);
}

bool RiskGuardsAllowTrading()
{
   RefreshRiskBaselineIfNeeded();

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity > peakEquity)
   {
      peakEquity = equity;
      GlobalVariableSet(globalPrefix + "_peak_equity", peakEquity);
   }

   if(dayStartEquity > 0.0 && InpMaxDailyLossPercent > 0.0)
   {
      double dailyLossPercent = 100.0 * (dayStartEquity - equity) / dayStartEquity;
      if(dailyLossPercent >= InpMaxDailyLossPercent)
      {
         UpdatePanel("Daily loss guard", InpPanelErrorColor);
         return false;
      }
   }

   if(peakEquity > 0.0 && InpMaxDrawdownPercent > 0.0)
   {
      double drawdownPercent = 100.0 * (peakEquity - equity) / peakEquity;
      if(drawdownPercent >= InpMaxDrawdownPercent)
      {
         UpdatePanel("Drawdown guard", InpPanelErrorColor);
         return false;
      }
   }

   return true;
}

void RefreshRiskBaselineIfNeeded()
{
   MqlDateTime nowStruct;
   TimeToStruct(TimeCurrent(), nowStruct);
   int currentDayCode = nowStruct.year * 1000 + nowStruct.day_of_year;

   if(currentDayCode == dayCode && dayStartEquity > 0.0)
      return;

   dayCode = currentDayCode;
   dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   peakEquity = MathMax(peakEquity, dayStartEquity);
   GlobalVariableSet(globalPrefix + "_day_code", dayCode);
   GlobalVariableSet(globalPrefix + "_day_start_equity", dayStartEquity);
   GlobalVariableSet(globalPrefix + "_peak_equity", peakEquity);
}

void LoadPersistentState()
{
   if(GlobalVariableCheck(globalPrefix + "_loss_streak"))
      lossStreak = (int)GlobalVariableGet(globalPrefix + "_loss_streak");
   else
      lossStreak = 0;

   if(GlobalVariableCheck(globalPrefix + "_last_close_time"))
      lastCloseTime = (datetime)GlobalVariableGet(globalPrefix + "_last_close_time");

   if(GlobalVariableCheck(globalPrefix + "_peak_equity"))
      peakEquity = GlobalVariableGet(globalPrefix + "_peak_equity");
   else
      peakEquity = AccountInfoDouble(ACCOUNT_EQUITY);

   if(GlobalVariableCheck(globalPrefix + "_day_code"))
      dayCode = (int)GlobalVariableGet(globalPrefix + "_day_code");

   if(GlobalVariableCheck(globalPrefix + "_day_start_equity"))
      dayStartEquity = GlobalVariableGet(globalPrefix + "_day_start_equity");

   RefreshRiskBaselineIfNeeded();
}

void SavePersistentState()
{
   GlobalVariableSet(globalPrefix + "_loss_streak", lossStreak);
   GlobalVariableSet(globalPrefix + "_last_close_time", (double)lastCloseTime);
   GlobalVariableSet(globalPrefix + "_peak_equity", peakEquity);
   GlobalVariableSet(globalPrefix + "_day_code", dayCode);
   GlobalVariableSet(globalPrefix + "_day_start_equity", dayStartEquity);
}

string BuildGlobalPrefix()
{
   return "PK30SS_" + _Symbol + "_" + IntegerToString((long)InpMagicNumber) + "_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
}

string PositionStageKey(const ulong ticket)
{
   return globalPrefix + "_stage_" + IntegerToString((long)ticket);
}

string PendingPartialKey(const ulong ticket)
{
   return globalPrefix + "_pending_partial_" + IntegerToString((long)ticket);
}

bool IsMarkedPartialClose(const ulong ticket)
{
   if(ticket == 0)
      return false;

   string key = PendingPartialKey(ticket);
   if(!GlobalVariableCheck(key))
      return false;

   double markedAt = GlobalVariableGet(key);
   if((TimeCurrent() - (datetime)markedAt) > 120)
   {
      GlobalVariableDel(key);
      return false;
   }

   GlobalVariableDel(key);
   return true;
}

int PositionStage(const ulong ticket)
{
   string key = PositionStageKey(ticket);
   if(!GlobalVariableCheck(key))
      return 0;
   return (int)GlobalVariableGet(key);
}

void SetPositionStage(const ulong ticket, const int stage)
{
   GlobalVariableSet(PositionStageKey(ticket), stage);
}

void ReportError(const string message, const int code)
{
   string full = StringFormat("PK30 SmartScalper [%s/%s] code=%d %s",
                              InpBrokerTag, _Symbol, code, message);
   Print(full);

   if(InpShowAlerts)
      Alert(full);

   int file = FileOpen(InpErrorLogFile,
                       FILE_READ | FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(file == INVALID_HANDLE)
   {
      Print("Error log file open failed. LastError=", GetLastError());
      return;
   }

   FileSeek(file, 0, SEEK_END);
   FileWrite(file,
             TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
             InpBrokerTag,
             AccountInfoString(ACCOUNT_SERVER),
             _Symbol,
             IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)),
             IntegerToString(code),
             message);
   FileClose(file);
}

void ReleaseIndicator(int &handle)
{
   if(handle != INVALID_HANDLE)
   {
      IndicatorRelease(handle);
      handle = INVALID_HANDLE;
   }
}

void CreatePanel()
{
   DeletePanel();

   ObjectCreate(0, panelPrefix + "back", OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, panelPrefix + "back", OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, panelPrefix + "back", OBJPROP_XDISTANCE, 8);
   ObjectSetInteger(0, panelPrefix + "back", OBJPROP_YDISTANCE, 18);
   ObjectSetInteger(0, panelPrefix + "back", OBJPROP_XSIZE, 300);
   ObjectSetInteger(0, panelPrefix + "back", OBJPROP_YSIZE, 128);
   ObjectSetInteger(0, panelPrefix + "back", OBJPROP_BGCOLOR, InpPanelBackColor);
   ObjectSetInteger(0, panelPrefix + "back", OBJPROP_COLOR, InpPanelTitleColor);
   ObjectSetInteger(0, panelPrefix + "back", OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, panelPrefix + "back", OBJPROP_BACK, false);

   CreateLabel("title", 18, 26, "PK 30s Smart Scalper", InpPanelTitleColor, 12);
   CreateLabel("owner", 18, 48, "Owner: " + InpOwnerName, clrGold, 10);
   CreateLabel("broker", 18, 68, "Broker: " + InpBrokerTag, clrWhite, 9);
   CreateLabel("status", 18, 88, "Status: Starting", InpPanelWarningColor, 9);
   CreateLabel("risk", 18, 108, "Lot: -- | Recovery: -- | Spread: --", clrWhite, 9);
   CreateLabel("mode", 18, 128, "Mode: --", clrWhite, 9);
}

void CreateLabel(const string suffix,
                 const int x,
                 const int y,
                 const string text,
                 const color labelColor,
                 const int fontSize)
{
   string name = panelPrefix + suffix;
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_COLOR, labelColor);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, fontSize);
   ObjectSetString(0, name, OBJPROP_FONT, "Arial");
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

void UpdatePanel(const string status, const color statusColor)
{
   if(ObjectFind(0, panelPrefix + "status") < 0)
      CreatePanel();

   ObjectSetString(0, panelPrefix + "status", OBJPROP_TEXT, "Status: " + status);
   ObjectSetInteger(0, panelPrefix + "status", OBJPROP_COLOR, statusColor);

   string riskLine = StringFormat("Lot: %.2f | Recovery: %d/%d | Spread: %d",
                                  NextLot(), lossStreak, InpMaxRecoverySteps, CurrentSpreadPoints());
   string modeLine = "Mode: ";
   if(InpSignalOnlyMode || !InpEnableAutoTrading)
      modeLine += "semi-auto signal";
   else
      modeLine += "full-auto execution";

   ObjectSetString(0, panelPrefix + "risk", OBJPROP_TEXT, riskLine);
   ObjectSetString(0, panelPrefix + "mode", OBJPROP_TEXT, modeLine);
   ChartRedraw(0);
}

void DeletePanel()
{
   for(int i = ObjectsTotal(0, 0, -1) - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, panelPrefix) == 0)
         ObjectDelete(0, name);
   }
}
