import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  BarChart3,
  NotebookPen,
  PiggyBank,
  RefreshCw,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  createPaperAccount,
  fetchPaperAccount,
  fetchPaperBets,
  fetchPaperMonthlyReport,
  fetchPaperStrategyComparison,
  fetchPaperSummary,
  settlePaperBets,
} from "@/api/paperBettingApi";
import { BANKROLL_PRESETS, RISK_PROFILES, formatCurrency } from "@/lib/bankrollCalculator";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { SectionHeader, TerminalCard } from "@/components/terminal";
import ShareButton from "@/components/social/ShareButton";

const PERIODS = [
  { id: "today", label: "Today" },
  { id: "week", label: "This week" },
  { id: "month", label: "This month" },
  { id: "all", label: "All time" },
];

const DISCLAIMER =
  "Virtual betting is for analysis and education only. It does not guarantee real-money results.";

export default function PaperBettingPage() {
  const { isAuthenticated } = useAuth();
  const [account, setAccount] = useState(null);
  const [summary, setSummary] = useState(null);
  const [bets, setBets] = useState([]);
  const [monthly, setMonthly] = useState(null);
  const [strategy, setStrategy] = useState(null);
  const [period, setPeriod] = useState("month");
  const [bankroll, setBankroll] = useState(100);
  const [currency, setCurrency] = useState("EUR");
  const [profile, setProfile] = useState("balanced");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await settlePaperBets().catch(() => {});
      const [acc, sum, betList, mon, strat] = await Promise.all([
        fetchPaperAccount(),
        fetchPaperSummary(period),
        fetchPaperBets(),
        fetchPaperMonthlyReport().catch(() => ({ report: null })),
        fetchPaperStrategyComparison(bankroll).catch(() => ({ available: false })),
      ]);
      setAccount(acc.account);
      setSummary(sum);
      setBets(betList.bets || []);
      setMonthly(mon.report);
      setStrategy(strat);
      if (acc.account) {
        setBankroll(acc.account.starting_bankroll);
        setCurrency(acc.account.currency || "EUR");
        setProfile(acc.account.risk_profile || "balanced");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, period, bankroll]);

  useEffect(() => {
    load();
  }, [load]);

  const createAccount = async (reset = false) => {
    try {
      const res = await createPaperAccount({
        starting_bankroll: bankroll,
        currency,
        risk_profile: profile,
        reset_month: reset,
      });
      setAccount(res.account);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create account");
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="max-w-3xl mx-auto py-16 text-center space-y-4">
        <NotebookPen className="w-12 h-12 mx-auto text-[#94A3B8]" />
        <p className="text-[#94A3B8]">Log in to use the paper betting simulator.</p>
        <Button asChild><Link to="/login">Log in</Link></Button>
      </div>
    );
  }

  const sym = currency === "EUR" ? "€" : currency;

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-24">
      <SectionHeader
        eyebrow="📓 Simulation"
        title="Paper Betting"
        subtitle="Track AI tips with virtual money — profit, ROI, winrate, and monthly performance."
      />

      <TerminalCard className="border-[#FFD166]/25">
        <p className="text-sm text-[#FFD166] flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          {DISCLAIMER}
        </p>
      </TerminalCard>

      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={load} disabled={loading} className="border-white/10">
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh & settle
        </Button>
      </div>

      {error && <TerminalCard className="text-red-300 border-red-500/30">{error}</TerminalCard>}

      <TerminalCard>
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
          <PiggyBank className="w-5 h-5 text-[#00E676]" /> Virtual Bankroll
        </h2>
        <div className="flex flex-wrap gap-3 items-end mb-4">
          {BANKROLL_PRESETS.map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setBankroll(v)}
              className={`px-3 py-1.5 rounded-lg text-sm border ${bankroll === v ? "border-[#00E676] text-[#00E676]" : "border-white/10 text-[#94A3B8]"}`}
            >
              {sym}{v}
            </button>
          ))}
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            className="bg-black/30 border border-white/10 rounded px-2 py-1.5 text-sm"
          >
            <option value="EUR">EUR</option>
            <option value="USD">USD</option>
            <option value="GBP">GBP</option>
          </select>
          {Object.entries(RISK_PROFILES).map(([k, v]) => (
            <button
              key={k}
              type="button"
              onClick={() => setProfile(k)}
              className={`px-3 py-1.5 rounded-lg text-xs border ${profile === k ? "border-[#3B82F6] text-white" : "border-white/10 text-[#94A3B8]"}`}
            >
              {v.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => createAccount(false)} className="bg-[#00E676] text-[#0B1220]">
            {account ? "Update bankroll" : "Create virtual bankroll"}
          </Button>
          {account && (
            <Button variant="outline" onClick={() => createAccount(true)} className="border-white/10">
              Reset for new month
            </Button>
          )}
        </div>
        {account && (
          <p className="text-sm text-[#94A3B8] mt-3">
            Current: <strong className="text-white">{formatCurrency(account.current_bankroll, sym)}</strong>
            {" · "}Started: {formatCurrency(account.starting_bankroll, sym)}
            {" · "}Month {account.month}
          </p>
        )}
      </TerminalCard>

      {summary && (
        <>
          <div className="flex flex-wrap gap-2">
            {PERIODS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setPeriod(p.id)}
                className={`px-3 py-1.5 rounded-lg text-xs border ${period === p.id ? "bg-white/10 border-white/20 text-white" : "border-white/10 text-[#94A3B8]"}`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "P/L", value: formatCurrency(summary.profit_loss, sym), icon: summary.profit_loss >= 0 ? TrendingUp : TrendingDown, color: summary.profit_loss >= 0 ? "text-[#00E676]" : "text-[#FF6B6B]" },
              { label: "ROI", value: `${summary.roi_pct ?? "—"}%`, icon: BarChart3, color: "text-[#7DD3FC]" },
              { label: "Winrate", value: summary.winrate != null ? `${summary.winrate}%` : "—", icon: BarChart3, color: "text-[#FFD166]" },
              { label: "Pending", value: summary.pending ?? 0, icon: NotebookPen, color: "text-[#94A3B8]" },
            ].map((card) => (
              <TerminalCard key={card.label}>
                <p className="text-[10px] uppercase text-[#64748B]">{card.label}</p>
                <p className={`text-2xl font-bold ${card.color}`}>{card.value}</p>
              </TerminalCard>
            ))}
          </div>

          <TerminalCard>
            <p className="text-sm text-[#94A3B8]">
              Won {summary.won} · Lost {summary.lost} · Void {summary.void} · Avg quality {summary.average_quality ?? "—"}
              {summary.best_market && ` · Best market: ${summary.best_market}`}
              {summary.worst_market && ` · Worst: ${summary.worst_market}`}
            </p>
          </TerminalCard>
        </>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-white">Pending & recent bets</h2>
        {bets.length === 0 ? (
          <TerminalCard className="text-center py-8 text-[#94A3B8]">
            No paper bets yet. Add from{" "}
            <Link to="/betting-plan" className="text-[#00E676] hover:underline">AI Betting Plan</Link>
            {" or "}
            <Link to="/combo-tips" className="text-[#00E676] hover:underline">Combo Tips</Link>.
          </TerminalCard>
        ) : (
          <div className="space-y-2">
            {bets.slice(0, 20).map((b) => (
              <TerminalCard key={b.id} className="py-3">
                <div className="flex flex-wrap justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-white">
                      {b.home_team && b.away_team ? `${b.home_team} vs ${b.away_team}` : `Fixture ${b.fixture_id}`}
                    </p>
                    <p className="text-xs text-[#94A3B8]">{b.market}: {b.prediction} · Stake {formatCurrency(b.stake, sym)}</p>
                  </div>
                  <div className="text-right">
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${
                      b.status === "won" ? "border-[#00E676]/40 text-[#00E676]" :
                      b.status === "lost" ? "border-[#FF6B6B]/40 text-[#FF6B6B]" :
                      b.status === "pending" ? "border-[#FFD166]/40 text-[#FFD166]" : "border-white/20 text-[#94A3B8]"
                    }`}>
                      {b.status}
                    </span>
                    {b.profit_loss != null && (
                      <p className={`text-sm mt-1 ${b.profit_loss >= 0 ? "text-[#00E676]" : "text-[#FF6B6B]"}`}>
                        {b.profit_loss >= 0 ? "+" : ""}{formatCurrency(b.profit_loss, sym)}
                      </p>
                    )}
                  </div>
                </div>
              </TerminalCard>
            ))}
          </div>
        )}
      </section>

      {monthly && !monthly.message && (
        <TerminalCard>
          <div className="flex flex-wrap justify-between gap-2 items-start mb-2">
            <h3 className="font-semibold text-white">Monthly report</h3>
            <ShareButton
              type="paper_report"
              label="Share report"
              requireOptIn
              payload={{
                month: monthly.month,
                starting_bankroll: monthly.starting_bankroll,
                ending_bankroll: monthly.ending_bankroll,
                net_profit_loss: monthly.net_profit_loss,
                roi_pct: monthly.roi_pct,
                winrate: monthly.winrate,
                total_bets: monthly.total_bets,
                best_market: monthly.best_market,
                worst_market: monthly.worst_market,
                best_combo_type: monthly.best_combo_type,
                currency: account?.currency || "EUR",
                headline: monthly.headline,
                recommendation_next_month: monthly.recommendation_next_month,
              }}
            />
          </div>
          <p className="text-sm text-[#F8FAFC]">{monthly.headline}</p>
          <p className="text-xs text-[#94A3B8] mt-2">{monthly.recommendation_next_month}</p>
        </TerminalCard>
      )}

      {strategy?.available && (
        <TerminalCard>
          <h3 className="font-semibold text-white mb-3">Strategy comparison</h3>
          <div className="grid md:grid-cols-3 gap-3">
            {strategy.profiles?.map((p) => (
              <div key={p.profile} className={`rounded-lg border p-3 ${p.profile === strategy.best_profile ? "border-[#00E676]/40 bg-[#00E676]/5" : "border-white/10"}`}>
                <p className="font-medium capitalize text-white">{p.profile}</p>
                <p className="text-sm text-[#94A3B8]">ROI {p.roi_pct}% · P/L {p.profit_loss}</p>
                <p className="text-xs text-[#64748B]">Winrate {p.winrate}% · Drawdown {p.max_drawdown_pct}%</p>
              </div>
            ))}
          </div>
        </TerminalCard>
      )}

      {strategy && !strategy.available && (
        <TerminalCard className="text-sm text-[#94A3B8]">{strategy.message}</TerminalCard>
      )}
    </div>
  );
}
