//+------------------------------------------------------------------+
//| InstantTradePlatformCheckEA.mq5                                  |
//| Opens one tiny diagnostic trade immediately to verify MT5 trading |
//| permissions, symbol settings, broker retcodes, and order routing. |
//| Use on DEMO/test accounts only.                                  |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Diagnostic MT5 EA: opens one small trade immediately and logs platform/broker status."

#include <Trade/Trade.mqh>

enum TestDirection
{
   TEST_BUY = 0,
   TEST_SELL = 1
};

input bool          InpEnableTestTrade      = true;       // If false, only logs diagnostics
input TestDirection InpDirection            = TEST_BUY;   // Diagnostic direction
input double        InpRequestedLots        = 0.01;       // Requested test volume
input long          InpMagicNumber          = 90701001;   // Diagnostic magic
input int           InpStopLossPoints       = 300;        // 0 disables SL
input int           InpTakeProfitPoints     = 300;        // 0 disables TP
input int           InpMaxSpreadPoints      = 0;          // 0 disables spread filter
input int           InpDeviationPoints      = 20;         // Max market deviation
input bool          InpAutoClose            = false;      // Close test position automatically
input int           InpAutoCloseSeconds     = 60;         // Auto-close delay
input bool          InpBlockIfAnyPosition   = true;       // Safer on netting accounts
input bool          InpOneTradePerSymbol    = true;       // Avoid duplicate test entries
input string        InpComment              = "MT5_PLATFORM_CHECK";

CTrade trade;

bool     g_trade_attempted = false;
datetime g_open_time       = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpDeviationPoints);
   ConfigureFillingMode();

   Print("IPC_DIAG init: symbol=", _Symbol,
         " period=", EnumToString((ENUM_TIMEFRAMES)_Period),
         " magic=", InpMagicNumber,
         " enable_trade=", BoolText(InpEnableTestTrade),
         " lots=", DoubleToString(InpRequestedLots, 4));

   PrintEnvironmentDiagnostics();

   EventSetTimer(1);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("IPC_DIAG deinit: reason=", reason);
}

//+------------------------------------------------------------------+
//| Tick handler                                                      |
//+------------------------------------------------------------------+
void OnTick()
{
   TryOpenDiagnosticTrade();
}

//+------------------------------------------------------------------+
//| Timer handler lets the EA act even on slow symbols/no fresh tick. |
//+------------------------------------------------------------------+
void OnTimer()
{
   TryOpenDiagnosticTrade();
   TryAutoClose();
}

//+------------------------------------------------------------------+
//| Open one diagnostic trade                                         |
//+------------------------------------------------------------------+
void TryOpenDiagnosticTrade()
{
   if(g_trade_attempted)
      return;

   g_trade_attempted = true;

   Print("IPC_DIAG trade check started.");

   if(!InpEnableTestTrade)
   {
      Print("IPC_DIAG no order sent: InpEnableTestTrade=false.");
      return;
   }

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      Print("IPC_DIAG BLOCKED: terminal AutoTrading disabled or terminal trade not allowed.");
      return;
   }

   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      Print("IPC_DIAG BLOCKED: EA property 'Allow Algo Trading' is disabled.");
      return;
   }

   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
   {
      Print("IPC_DIAG BLOCKED: account trade not allowed by broker/server.");
      return;
   }

   if(!SymbolSelect(_Symbol, true))
   {
      Print("IPC_DIAG BLOCKED: SymbolSelect failed for ", _Symbol, " error=", GetLastError());
      return;
   }

   const long trade_mode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(trade_mode == SYMBOL_TRADE_MODE_DISABLED)
   {
      Print("IPC_DIAG BLOCKED: symbol trade mode disabled for ", _Symbol);
      return;
   }

   if(InpBlockIfAnyPosition && HasAnySymbolPosition())
   {
      Print("IPC_DIAG no order sent: existing position found on this symbol. ",
            "Set InpBlockIfAnyPosition=false only on a safe demo account if you want to test anyway.");
      return;
   }

   if(InpOneTradePerSymbol && HasExistingPositionOrOrder())
   {
      Print("IPC_DIAG no order sent: existing position/order found for symbol+magic.");
      return;
   }

   const long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(InpMaxSpreadPoints > 0 && spread > InpMaxSpreadPoints)
   {
      Print("IPC_DIAG BLOCKED: spread=", spread,
            " points exceeds InpMaxSpreadPoints=", InpMaxSpreadPoints);
      return;
   }

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || tick.bid <= 0.0 || tick.ask <= 0.0)
   {
      Print("IPC_DIAG BLOCKED: invalid tick for ", _Symbol, " error=", GetLastError());
      return;
   }

   const double volume = NormalizeVolume(InpRequestedLots);
   if(volume <= 0.0)
   {
      Print("IPC_DIAG BLOCKED: normalized volume invalid. requested=",
            DoubleToString(InpRequestedLots, 4));
      return;
   }

   double price = 0.0;
   double sl = 0.0;
   double tp = 0.0;
   BuildPrices(tick, price, sl, tp);

   ResetLastError();
   bool sent = false;
   if(InpDirection == TEST_BUY)
      sent = trade.Buy(volume, _Symbol, price, sl, tp, InpComment);
   else
      sent = trade.Sell(volume, _Symbol, price, sl, tp, InpComment);

   const uint retcode = trade.ResultRetcode();
   Print("IPC_DIAG order result: sent=", BoolText(sent),
         " retcode=", retcode,
         " desc=", trade.ResultRetcodeDescription(),
         " deal=", trade.ResultDeal(),
         " order=", trade.ResultOrder(),
         " volume=", DoubleToString(volume, 4),
         " price=", DoubleToString(price, _Digits),
         " sl=", DoubleToString(sl, _Digits),
         " tp=", DoubleToString(tp, _Digits),
         " last_error=", GetLastError());

   if(sent)
      g_open_time = TimeCurrent();
}

//+------------------------------------------------------------------+
//| Auto-close diagnostic position                                    |
//+------------------------------------------------------------------+
void TryAutoClose()
{
   if(!InpAutoClose || g_open_time <= 0)
      return;

   if(TimeCurrent() - g_open_time < InpAutoCloseSeconds)
      return;

   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      ResetLastError();
      const bool closed = trade.PositionClose(ticket);
      Print("IPC_DIAG auto-close result: ticket=", ticket,
            " closed=", BoolText(closed),
            " retcode=", trade.ResultRetcode(),
            " desc=", trade.ResultRetcodeDescription(),
            " last_error=", GetLastError());
   }

   g_open_time = 0;
}

//+------------------------------------------------------------------+
//| Existing position/order guard                                     |
//+------------------------------------------------------------------+
bool HasAnySymbolPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol)
      {
         Print("IPC_DIAG existing same-symbol position: ticket=", ticket,
               " magic=", PositionGetInteger(POSITION_MAGIC),
               " type=", PositionGetInteger(POSITION_TYPE),
               " volume=", DoubleToString(PositionGetDouble(POSITION_VOLUME), 4));
         return true;
      }
   }

   return false;
}

bool HasExistingPositionOrOrder()
{
   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (long)PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         Print("IPC_DIAG existing position: ticket=", ticket,
               " type=", PositionGetInteger(POSITION_TYPE),
               " volume=", DoubleToString(PositionGetDouble(POSITION_VOLUME), 4));
         return true;
      }
   }

   for(int i = OrdersTotal() - 1; i >= 0; --i)
   {
      const ulong ticket = OrderGetTicket(i);
      if(ticket == 0)
         continue;

      if(OrderGetString(ORDER_SYMBOL) == _Symbol &&
         (long)OrderGetInteger(ORDER_MAGIC) == InpMagicNumber)
      {
         Print("IPC_DIAG existing order: ticket=", ticket,
               " type=", OrderGetInteger(ORDER_TYPE),
               " volume=", DoubleToString(OrderGetDouble(ORDER_VOLUME_CURRENT), 4));
         return true;
      }
   }

   return false;
}

//+------------------------------------------------------------------+
//| Price and stop construction                                       |
//+------------------------------------------------------------------+
void BuildPrices(const MqlTick &tick, double &price, double &sl, double &tp)
{
   const double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   const int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   const int min_stop_points = MathMax(stops_level + 1, 0);
   const int sl_points = InpStopLossPoints > 0 ? MathMax(InpStopLossPoints, min_stop_points) : 0;
   const int tp_points = InpTakeProfitPoints > 0 ? MathMax(InpTakeProfitPoints, min_stop_points) : 0;

   if(InpDirection == TEST_BUY)
   {
      price = tick.ask;
      if(sl_points > 0)
         sl = NormalizeDouble(price - sl_points * point, _Digits);
      if(tp_points > 0)
         tp = NormalizeDouble(price + tp_points * point, _Digits);
   }
   else
   {
      price = tick.bid;
      if(sl_points > 0)
         sl = NormalizeDouble(price + sl_points * point, _Digits);
      if(tp_points > 0)
         tp = NormalizeDouble(price - tp_points * point, _Digits);
   }

   price = NormalizeDouble(price, _Digits);
}

//+------------------------------------------------------------------+
//| Volume normalization                                              |
//+------------------------------------------------------------------+
double NormalizeVolume(const double requested)
{
   const double min_volume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   const double max_volume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   const double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(min_volume <= 0.0 || max_volume <= 0.0 || step <= 0.0)
      return 0.0;

   double volume = MathMax(requested, min_volume);
   volume = MathMin(volume, max_volume);
   volume = MathFloor(volume / step) * step;

   const int digits = VolumeDigits(step);
   volume = NormalizeDouble(volume, digits);

   if(volume < min_volume)
      volume = min_volume;

   return NormalizeDouble(volume, digits);
}

int VolumeDigits(const double step)
{
   for(int digits = 0; digits <= 8; ++digits)
   {
      const double scaled = step * MathPow(10.0, digits);
      if(MathAbs(scaled - MathRound(scaled)) < 0.00000001)
         return digits;
   }
   return 2;
}

//+------------------------------------------------------------------+
//| Filling mode                                                      |
//+------------------------------------------------------------------+
void ConfigureFillingMode()
{
   const long filling = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);

   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      trade.SetTypeFilling(ORDER_FILLING_IOC);
   else
      trade.SetTypeFilling(ORDER_FILLING_RETURN);
}

//+------------------------------------------------------------------+
//| Diagnostics                                                       |
//+------------------------------------------------------------------+
void PrintEnvironmentDiagnostics()
{
   Print("IPC_DIAG env: terminal_trade_allowed=", BoolText((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)),
         " mql_trade_allowed=", BoolText((bool)MQLInfoInteger(MQL_TRADE_ALLOWED)),
         " account_trade_allowed=", BoolText((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)),
         " connected=", BoolText((bool)TerminalInfoInteger(TERMINAL_CONNECTED)));

   Print("IPC_DIAG account: login=", AccountInfoInteger(ACCOUNT_LOGIN),
         " server=", AccountInfoString(ACCOUNT_SERVER),
         " trade_mode=", AccountInfoInteger(ACCOUNT_TRADE_MODE),
         " margin_mode=", AccountInfoInteger(ACCOUNT_MARGIN_MODE),
         " balance=", DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
         " equity=", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));

   Print("IPC_DIAG symbol: trade_mode=", SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE),
         " spread=", SymbolInfoInteger(_Symbol, SYMBOL_SPREAD),
         " stops_level=", SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL),
         " filling_mode=", SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE),
         " volume_min=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 4),
         " volume_step=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP), 4),
         " volume_max=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX), 4),
         " digits=", _Digits);
}

string BoolText(const bool value)
{
   return value ? "true" : "false";
}
