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

enum TradingMode
{
   MODE_ADAPTIVE_MULTI = 0,
   MODE_TREND_SCALP = 1,
   MODE_AGGRESSIVE_BURST = 2
};

input string          InpOwnerName              = "Pedram Kamangar";
input string          InpBrokerTag              = "BazarnForex";
input ulong           InpMagicNumber            = 30072026;
input bool            InpEnableAutoTrading      = true;
input bool            InpSignalOnlyMode         = false;
input bool            InpShowAlerts             = true;
input TradingMode     InpTradingMode            = MODE_ADAPTIVE_MULTI;

input int             InpScalpWindowSeconds     = 60;
input int             InpMaxPositionHoldSeconds = 3600;
input int             InpMinSecondsAfterClose   = 8;
input double          InpBaseLot                = 0.01;
input double          InpMaxLot                 = 1.00;
input double          InpRecoveryMultiplier     = 1.0;
input int             InpMaxRecoverySteps       = 0;
input bool            InpAggressiveBurstMode    = false;
input int             InpBurstMaxTrades         = 10;
input int             InpBurstIntervalMinSec    = 5;
input int             InpBurstIntervalMaxSec    = 10;
input int             InpMaxConcurrentPositions = 10;
input bool            InpBurstStopOnFirstLoss   = true;
input int             InpBurstCooldownAfterLoss = 180;
input double          InpBetterOpportunityAdxBonus = 8.0;
input double          InpBetterOpportunityRsiBuffer = 4.0;
input int             InpAdaptiveSignalSeconds  = 60;
input int             InpAdaptiveMaxHoldSeconds = 14400;
input double          InpMinRiskReward          = 1.60;
input int             InpBreakoutLookbackBars   = 16;
input int             InpDonchianLookbackBars   = 20;
input double          InpRangeZonePercent       = 20.0;
input bool            InpUseEvaluatedSymbolProfile = true;

input ENUM_TIMEFRAMES InpTrendTimeframe         = PERIOD_H1;
input ENUM_TIMEFRAMES InpEntryTimeframe         = PERIOD_M15;
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
int      handleMacdH1    = INVALID_HANDLE;
int      handleEma34H4   = INVALID_HANDLE;
int      handleEma55H4   = INVALID_HANDLE;
int      handleRsiH1     = INVALID_HANDLE;
int      handleAdxH1     = INVALID_HANDLE;
int      handleAtrH1     = INVALID_HANDLE;

long     lastSignalCycle = -1;
datetime lastCloseTime   = 0;
int      lossStreak      = 0;
double   peakEquity      = 0.0;
double   dayStartEquity  = 0.0;
int      dayCode         = 0;
bool     burstActive     = false;
int      burstTradesOpened = 0;
int      burstTrend      = 0;
datetime nextBurstTradeTime = 0;
datetime burstCooldownUntil = 0;
long     lastAdaptiveSignalCycle = -1;
string   activeStrategyTag = "TREND_SCALP";
datetime activeStrategyTime = 0;
datetime lastAdaptiveSetupTime = 0;
string   lastAdaptiveSetupTag = "";
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
   if(InpAggressiveBurstMode &&
      (InpBurstMaxTrades <= 0 || InpBurstIntervalMinSec <= 0 ||
       InpBurstIntervalMaxSec < InpBurstIntervalMinSec || InpMaxConcurrentPositions <= 0))
   {
      ReportError("Invalid aggressive burst settings.", 1003);
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
   handleMacdH1    = iMACD(_Symbol, PERIOD_H1, 12, 26, 9, PRICE_CLOSE);
   handleEma34H4   = iMA(_Symbol, PERIOD_H4, 34, 0, MODE_EMA, PRICE_CLOSE);
   handleEma55H4   = iMA(_Symbol, PERIOD_H4, 55, 0, MODE_EMA, PRICE_CLOSE);
   handleRsiH1     = iRSI(_Symbol, PERIOD_H1, InpRsiPeriod, PRICE_CLOSE);
   handleAdxH1     = iADX(_Symbol, PERIOD_H1, InpAdxPeriod);
   handleAtrH1     = iATR(_Symbol, PERIOD_H1, InpAtrPeriod);

   if(handleTrendFast == INVALID_HANDLE || handleTrendSlow == INVALID_HANDLE ||
      handleEntryEma == INVALID_HANDLE || handleAdx == INVALID_HANDLE ||
      handleAtr == INVALID_HANDLE || handleRsi == INVALID_HANDLE ||
      handleMacdH1 == INVALID_HANDLE || handleEma34H4 == INVALID_HANDLE ||
      handleEma55H4 == INVALID_HANDLE || handleRsiH1 == INVALID_HANDLE ||
      handleAdxH1 == INVALID_HANDLE || handleAtrH1 == INVALID_HANDLE)
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
   ReleaseIndicator(handleMacdH1);
   ReleaseIndicator(handleEma34H4);
   ReleaseIndicator(handleEma55H4);
   ReleaseIndicator(handleRsiH1);
   ReleaseIndicator(handleAdxH1);
   ReleaseIndicator(handleAtrH1);
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
      if(InpAggressiveBurstMode && InpBurstStopOnFirstLoss)
      {
         burstActive = false;
         burstTradesOpened = 0;
         burstTrend = 0;
         burstCooldownUntil = TimeCurrent() + InpBurstCooldownAfterLoss;
         nextBurstTradeTime = burstCooldownUntil;
         Print("First losing close stopped aggressive burst. Waiting for better opportunity until ",
               TimeToString(burstCooldownUntil, TIME_DATE | TIME_SECONDS));
      }
      SavePersistentState();
      Print("Losing trade closed. Next recovery step=", lossStreak,
            " next lot=", DoubleToString(NextLot(), 2));
   }
}

void EvaluateThirtySecondCycle()
{
   datetime now = TimeCurrent();

   if(InpTradingMode == MODE_ADAPTIVE_MULTI)
   {
      EvaluateAdaptiveMultiStrategy(now);
      return;
   }

   if(InpTradingMode == MODE_AGGRESSIVE_BURST || InpAggressiveBurstMode)
   {
      EvaluateAggressiveBurst(now);
      return;
   }

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

   activeStrategyTag = "TREND_SCALP";
   OpenScalpTrade(trend);
}

void EvaluateAdaptiveMultiStrategy(const datetime now)
{
   int signalSeconds = MathMax(15, InpAdaptiveSignalSeconds);
   long cycle = (long)(now / signalSeconds);
   if(cycle == lastAdaptiveSignalCycle)
      return;

   lastAdaptiveSignalCycle = cycle;

   if(HasOpenPosition())
      return;

   if((now - lastCloseTime) < InpMinSecondsAfterClose)
      return;

   if(!RiskGuardsAllowTrading())
      return;

   if(!AdaptiveIndicatorsReady())
      return;

   if(CurrentSpreadPoints() > InpMaxSpreadPoints)
   {
      UpdatePanel("Spread filter", InpPanelWarningColor);
      return;
   }

   TrendDirection signal = AdaptiveStrategySignal();
   if(signal == TREND_FLAT)
      return;

   if(activeStrategyTime == lastAdaptiveSetupTime && activeStrategyTag == lastAdaptiveSetupTag)
      return;

   lastAdaptiveSetupTime = activeStrategyTime;
   lastAdaptiveSetupTag = activeStrategyTag;
   OpenScalpTrade(signal);
}

void EvaluateAggressiveBurst(const datetime now)
{
   if(burstCooldownUntil > now)
   {
      UpdatePanel("Waiting better setup", InpPanelWarningColor);
      return;
   }

   if(now < nextBurstTradeTime)
      return;

   if(CountOpenPositions() >= InpMaxConcurrentPositions)
      return;

   if((now - lastCloseTime) < InpMinSecondsAfterClose)
      return;

   if(!RiskGuardsAllowTrading())
      return;

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

   bool requireBetterOpportunity = (lossStreak > 0);
   if(requireBetterOpportunity)
   {
      if(!BetterOpportunityEntryAllows(trend))
         return;
   }
   else if(!EntryFilterAllows(trend))
   {
      return;
   }

   if(!burstActive || burstTradesOpened >= InpBurstMaxTrades || burstTrend != (int)trend)
      StartBurst(trend, now);

   if(burstTradesOpened >= InpBurstMaxTrades)
   {
      burstActive = false;
      nextBurstTradeTime = now + InpScalpWindowSeconds;
      SavePersistentState();
      return;
   }

   activeStrategyTag = "BURST";
   if(OpenScalpTrade(trend))
   {
      burstTradesOpened++;
      nextBurstTradeTime = now + NextBurstIntervalSeconds();
      SavePersistentState();
   }
}

void StartBurst(const TrendDirection trend, const datetime now)
{
   burstActive = true;
   burstTradesOpened = 0;
   burstTrend = (int)trend;
   activeStrategyTag = "BURST";
   nextBurstTradeTime = now;
   SavePersistentState();
}

bool AdaptiveIndicatorsReady()
{
   return IndicatorsReady() &&
          BarsCalculated(handleMacdH1) >= 60 &&
          BarsCalculated(handleEma34H4) >= 60 &&
          BarsCalculated(handleEma55H4) >= 60 &&
          BarsCalculated(handleRsiH1) >= InpRsiPeriod &&
          BarsCalculated(handleAdxH1) >= InpAdxPeriod &&
          BarsCalculated(handleAtrH1) >= InpAtrPeriod;
}

TrendDirection AdaptiveStrategySignal()
{
   activeStrategyTime = 0;
   TrendDirection signal = DonchianBreakoutSignal();
   if(signal != TREND_FLAT)
   {
      activeStrategyTag = "ADAPT:DONCHIAN";
      if(SymbolStrategyAllowed(activeStrategyTag))
         return signal;
   }

   signal = IntradayBreakoutSignal();
   if(signal != TREND_FLAT)
   {
      activeStrategyTag = "ADAPT:BREAKOUT";
      if(SymbolStrategyAllowed(activeStrategyTag))
         return signal;
   }

   signal = MacdMomentumSignal();
   if(signal != TREND_FLAT)
   {
      activeStrategyTag = "ADAPT:MACD";
      if(SymbolStrategyAllowed(activeStrategyTag))
         return signal;
   }

   signal = EmaPullbackSignal();
   if(signal != TREND_FLAT)
   {
      activeStrategyTag = "ADAPT:EMA_H4";
      if(SymbolStrategyAllowed(activeStrategyTag))
         return signal;
   }

   signal = MeanReversionSignal();
   if(signal != TREND_FLAT)
   {
      activeStrategyTag = "ADAPT:MEAN_REVERSION";
      if(SymbolStrategyAllowed(activeStrategyTag))
         return signal;
   }

   activeStrategyTag = "ADAPT:NO_SETUP";
   return TREND_FLAT;
}

bool SymbolStrategyAllowed(const string strategyTag)
{
   if(!InpUseEvaluatedSymbolProfile)
      return true;

   string symbol = _Symbol;
   if(StringFind(symbol, "EURUSD") >= 0)
      return strategyTag == "ADAPT:DONCHIAN" || strategyTag == "ADAPT:EMA_H4" || strategyTag == "ADAPT:MEAN_REVERSION";
   if(StringFind(symbol, "USDJPY") >= 0)
      return false;
   if(StringFind(symbol, "GBPUSD") >= 0)
      return strategyTag == "ADAPT:DONCHIAN";
   if(StringFind(symbol, "EURJPY") >= 0)
      return false;
   if(StringFind(symbol, "XAUUSD") >= 0 || StringFind(symbol, "GOLD") >= 0)
      return false;

   return true;
}

TrendDirection IntradayBreakoutSignal()
{
   MqlRates rates[];
   int lookback = MathMax(6, InpBreakoutLookbackBars);
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, PERIOD_M15, 0, lookback + 3, rates) < lookback + 3)
      return TREND_FLAT;

   double rangeHigh = rates[2].high;
   double rangeLow = rates[2].low;
   for(int i = 3; i < lookback + 2; i++)
   {
      rangeHigh = MathMax(rangeHigh, rates[i].high);
      rangeLow = MathMin(rangeLow, rates[i].low);
   }

   double rangeHeight = rangeHigh - rangeLow;
   double atr = CurrentAdaptiveAtr();
   if(atr <= 0.0 || rangeHeight < atr * 0.45)
      return TREND_FLAT;

   if(rates[1].close > rangeHigh && rates[1].close > rates[1].open)
   {
      activeStrategyTime = rates[1].time;
      return TREND_UP;
   }
   if(rates[1].close < rangeLow && rates[1].close < rates[1].open)
   {
      activeStrategyTime = rates[1].time;
      return TREND_DOWN;
   }

   return TREND_FLAT;
}

TrendDirection MacdMomentumSignal()
{
   double macdMain[];
   double macdSignal[];
   MqlRates rates[];
   ArrayResize(macdMain, 3);
   ArrayResize(macdSignal, 3);
   ArraySetAsSeries(macdMain, true);
   ArraySetAsSeries(macdSignal, true);
   ArraySetAsSeries(rates, true);

   if(CopyBuffer(handleMacdH1, 0, 0, 3, macdMain) < 3 ||
      CopyBuffer(handleMacdH1, 1, 0, 3, macdSignal) < 3 ||
      CopyRates(_Symbol, PERIOD_H1, 0, 4, rates) < 4)
   {
      return TREND_FLAT;
   }

   double hist0 = macdMain[1] - macdSignal[1];
   double hist1 = macdMain[2] - macdSignal[2];

   if(hist0 > 0.0 && hist1 <= 0.0 && rates[1].close > rates[2].high)
   {
      activeStrategyTime = rates[1].time;
      return TREND_UP;
   }
   if(hist0 < 0.0 && hist1 >= 0.0 && rates[1].close < rates[2].low)
   {
      activeStrategyTime = rates[1].time;
      return TREND_DOWN;
   }

   return TREND_FLAT;
}

TrendDirection EmaPullbackSignal()
{
   double ema34[];
   double ema55[];
   MqlRates rates[];
   ArrayResize(ema34, 3);
   ArrayResize(ema55, 3);
   ArraySetAsSeries(ema34, true);
   ArraySetAsSeries(ema55, true);
   ArraySetAsSeries(rates, true);

   if(CopyBuffer(handleEma34H4, 0, 0, 3, ema34) < 3 ||
      CopyBuffer(handleEma55H4, 0, 0, 3, ema55) < 3 ||
      CopyRates(_Symbol, PERIOD_H4, 0, 4, rates) < 4)
   {
      return TREND_FLAT;
   }

   if(ema34[1] > ema55[1] && rates[1].low <= ema34[1] && rates[1].close > ema34[1] && rates[1].close > rates[1].open)
   {
      activeStrategyTime = rates[1].time;
      return TREND_UP;
   }

   if(ema34[1] < ema55[1] && rates[1].high >= ema34[1] && rates[1].close < ema34[1] && rates[1].close < rates[1].open)
   {
      activeStrategyTime = rates[1].time;
      return TREND_DOWN;
   }

   return TREND_FLAT;
}

TrendDirection MeanReversionSignal()
{
   double adx[];
   double rsi[];
   MqlRates rates[];
   int lookback = 24;
   ArrayResize(adx, 2);
   ArrayResize(rsi, 2);
   ArraySetAsSeries(adx, true);
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(rates, true);

   if(CopyBuffer(handleAdxH1, 0, 0, 2, adx) < 2 ||
      CopyBuffer(handleRsiH1, 0, 0, 2, rsi) < 2 ||
      CopyRates(_Symbol, PERIOD_H1, 0, lookback + 2, rates) < lookback + 2)
   {
      return TREND_FLAT;
   }

   if(adx[1] >= InpMinAdx)
      return TREND_FLAT;

   double rangeHigh = rates[2].high;
   double rangeLow = rates[2].low;
   for(int i = 3; i < lookback + 2; i++)
   {
      rangeHigh = MathMax(rangeHigh, rates[i].high);
      rangeLow = MathMin(rangeLow, rates[i].low);
   }

   double zone = (rangeHigh - rangeLow) * InpRangeZonePercent / 100.0;
   if(zone <= 0.0)
      return TREND_FLAT;

   if(rates[1].low <= rangeLow + zone && rsi[1] <= 35.0 && rates[1].close > rates[1].open)
   {
      activeStrategyTime = rates[1].time;
      return TREND_UP;
   }
   if(rates[1].high >= rangeHigh - zone && rsi[1] >= 65.0 && rates[1].close < rates[1].open)
   {
      activeStrategyTime = rates[1].time;
      return TREND_DOWN;
   }

   return TREND_FLAT;
}

TrendDirection DonchianBreakoutSignal()
{
   MqlRates rates[];
   int lookback = MathMax(10, InpDonchianLookbackBars);
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, PERIOD_H4, 0, lookback + 3, rates) < lookback + 3)
      return TREND_FLAT;

   double upper = rates[2].high;
   double lower = rates[2].low;
   for(int i = 3; i < lookback + 2; i++)
   {
      upper = MathMax(upper, rates[i].high);
      lower = MathMin(lower, rates[i].low);
   }

   TrendDirection broadTrend = DetectTrend();
   if(rates[1].close > upper && broadTrend != TREND_DOWN)
   {
      activeStrategyTime = rates[1].time;
      return TREND_UP;
   }
   if(rates[1].close < lower && broadTrend != TREND_UP)
   {
      activeStrategyTime = rates[1].time;
      return TREND_DOWN;
   }

   return TREND_FLAT;
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

bool BetterOpportunityEntryAllows(const TrendDirection trend)
{
   if(!EntryFilterAllows(trend))
      return false;

   double adx[];
   double rsi[];
   ArrayResize(adx, 1);
   ArrayResize(rsi, 1);
   ArraySetAsSeries(adx, true);
   ArraySetAsSeries(rsi, true);

   if(CopyBuffer(handleAdx, 0, 0, 1, adx) != 1 ||
      CopyBuffer(handleRsi, 0, 0, 1, rsi) != 1)
   {
      ReportError("Failed to read better-opportunity buffers.", GetLastError());
      return false;
   }

   if(adx[0] < InpMinAdx + InpBetterOpportunityAdxBonus)
      return false;

   if(trend == TREND_UP)
      return rsi[0] >= InpBuyRsiMin + InpBetterOpportunityRsiBuffer &&
             rsi[0] <= InpBuyRsiMax - InpBetterOpportunityRsiBuffer;

   if(trend == TREND_DOWN)
      return rsi[0] >= InpSellRsiMin + InpBetterOpportunityRsiBuffer &&
             rsi[0] <= InpSellRsiMax - InpBetterOpportunityRsiBuffer;

   return false;
}

bool OpenScalpTrade(const TrendDirection trend)
{
   double atr = (InpTradingMode == MODE_ADAPTIVE_MULTI) ? CurrentAdaptiveAtr() : CurrentAtr();
   if(atr <= 0.0)
      return false;

   double lot = NextLot();
   double stopDistance = SmartStopDistance(atr);
   double tpDistance = (InpTradingMode == MODE_ADAPTIVE_MULTI)
                       ? stopDistance * MathMax(1.0, InpMinRiskReward)
                       : atr * InpTp3AtrMultiplier;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price = trend == TREND_UP ? ask : bid;
   double sl = trend == TREND_UP ? price - stopDistance : price + stopDistance;
   double tp = trend == TREND_UP ? price + tpDistance : price - tpDistance;

   sl = NormalizeDouble(sl, _Digits);
   tp = NormalizeDouble(tp, _Digits);

   string side = trend == TREND_UP ? "BUY" : "SELL";
   string comment = "PK30 " + activeStrategyTag + " " + InpBrokerTag;
   string signalMessage = StringFormat("%s %s signal %s lot=%.2f recovery_step=%d",
                                       _Symbol, activeStrategyTag, side, lot, lossStreak);

   if(InpShowAlerts)
      Alert(signalMessage);
   Print(signalMessage);

   if(InpSignalOnlyMode || !InpEnableAutoTrading)
   {
      UpdatePanel("Signal only: " + side, InpPanelWarningColor);
      return false;
   }

   if(!TerminalTradeAllowed())
   {
      ReportError("Auto trading is disabled in terminal or EA settings.", 1002);
      UpdatePanel("Trading disabled", InpPanelErrorColor);
      return false;
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
      return false;
   }
   else
   {
      UpdatePanel("Opened " + side, InpPanelProfitColor);
   }

   return true;
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
      double currentSl = PositionGetDouble(POSITION_SL);
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

      if(IsAdaptivePosition())
      {
         ManageAdaptivePosition(ticket, type, openPrice, currentSl, currentTp, profitDistance);
      }
      else
      {
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
      }

      int maxHoldSeconds = PositionMaxHoldSeconds();
      if(maxHoldSeconds > 0 && (TimeCurrent() - openedAt) >= maxHoldSeconds)
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

bool IsAdaptivePosition()
{
   return StringFind(PositionGetString(POSITION_COMMENT), "ADAPT:") >= 0;
}

void ManageAdaptivePosition(const ulong ticket,
                            const ENUM_POSITION_TYPE type,
                            const double openPrice,
                            const double currentSl,
                            const double currentTp,
                            const double profitDistance)
{
   double initialRisk = MathAbs(openPrice - currentSl);
   if(initialRisk <= 0.0)
      return;

   if(profitDistance >= initialRisk)
      MoveStopToBreakEven(ticket, type, openPrice, currentTp);

   if(profitDistance >= initialRisk * 1.20)
      TrailSmartStop(ticket, type, currentTp, CurrentAdaptiveAtr());
}

int PositionMaxHoldSeconds()
{
   string comment = PositionGetString(POSITION_COMMENT);
   if(StringFind(comment, "ADAPT:") >= 0)
      return InpAdaptiveMaxHoldSeconds;
   return InpMaxPositionHoldSeconds;
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

double CurrentAdaptiveAtr()
{
   double atr[];
   ArrayResize(atr, 1);
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(handleAtrH1, 0, 0, 1, atr) != 1)
      return CurrentAtr();
   return atr[0];
}

int CurrentSpreadPoints()
{
   return (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
}

int NextBurstIntervalSeconds()
{
   int minSeconds = MathMax(1, InpBurstIntervalMinSec);
   int maxSeconds = MathMax(minSeconds, InpBurstIntervalMaxSec);
   int span = maxSeconds - minSeconds + 1;
   if(span <= 1)
      return minSeconds;

   return minSeconds + (int)((long)TimeCurrent() % span);
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
   return CountOpenPositions() > 0;
}

int CountOpenPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         count++;
      }
   }
   return count;
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

   if(GlobalVariableCheck(globalPrefix + "_burst_active"))
      burstActive = GlobalVariableGet(globalPrefix + "_burst_active") > 0.5;

   if(GlobalVariableCheck(globalPrefix + "_burst_trades_opened"))
      burstTradesOpened = (int)GlobalVariableGet(globalPrefix + "_burst_trades_opened");

   if(GlobalVariableCheck(globalPrefix + "_burst_trend"))
      burstTrend = (int)GlobalVariableGet(globalPrefix + "_burst_trend");

   if(GlobalVariableCheck(globalPrefix + "_next_burst_trade_time"))
      nextBurstTradeTime = (datetime)GlobalVariableGet(globalPrefix + "_next_burst_trade_time");

   if(GlobalVariableCheck(globalPrefix + "_burst_cooldown_until"))
      burstCooldownUntil = (datetime)GlobalVariableGet(globalPrefix + "_burst_cooldown_until");

   RefreshRiskBaselineIfNeeded();
}

void SavePersistentState()
{
   GlobalVariableSet(globalPrefix + "_loss_streak", lossStreak);
   GlobalVariableSet(globalPrefix + "_last_close_time", (double)lastCloseTime);
   GlobalVariableSet(globalPrefix + "_peak_equity", peakEquity);
   GlobalVariableSet(globalPrefix + "_day_code", dayCode);
   GlobalVariableSet(globalPrefix + "_day_start_equity", dayStartEquity);
   GlobalVariableSet(globalPrefix + "_burst_active", burstActive ? 1.0 : 0.0);
   GlobalVariableSet(globalPrefix + "_burst_trades_opened", burstTradesOpened);
   GlobalVariableSet(globalPrefix + "_burst_trend", burstTrend);
   GlobalVariableSet(globalPrefix + "_next_burst_trade_time", (double)nextBurstTradeTime);
   GlobalVariableSet(globalPrefix + "_burst_cooldown_until", (double)burstCooldownUntil);
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
   else if(InpTradingMode == MODE_ADAPTIVE_MULTI)
      modeLine += "adaptive " + activeStrategyTag;
   else if(InpTradingMode == MODE_AGGRESSIVE_BURST || InpAggressiveBurstMode)
   {
      modeLine += StringFormat("aggressive burst %d/%d open=%d",
                               burstTradesOpened, InpBurstMaxTrades, CountOpenPositions());
      if(burstCooldownUntil > TimeCurrent())
         modeLine += " cooldown";
   }
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
