import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Calendar,
  Copy,
  Layers,
  PiggyBank,
  Plus,
  RefreshCw,
  Shield,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { fetchBettingPlanToday } from "@/api/bettingPlanApi";
import { useBetSlip } from "@/context/BetSlipContext";
import { useAuth } from "@/lib/AuthContext";
import { qualityColorClass } from "@/lib/betQualityOverlay";
import {
  BANKROLL_PRESETS,
  RISK_PROFILES,
  formatCurrency,
  recommendStake,
} from "@/lib/bankrollCalculator";
import { canViewCombos, normalizePlan } from "@/lib/planGating";
import { Button } from "@/components/ui/button";
import { SectionHeader, TerminalCard } from "@/components/terminal";
import BetSlipDrawer from "@/components/match-center/BetSlipDrawer";
import AddToPaperBetButton from "@/components/paper-betting/AddToPaperBetButton";
import ShareButton from "@/components/social/ShareButton";

const DAY_QUALITY_STYLE = {
  Excellent: "border-[#00C853]/40 bg-[#00C853]/10 text-[#00C853]",
  Good: "border-[#00E676]/40 bg-[#00E676]/10 text-[#00E676]",
  Risky: "border-[#FF9F43]/40 bg-[#FF9F43]/10 text-[#FF9F43]",
  Poor: "border-[#FF6B6B]/40 bg-[#FF6B6B]/10 text-[#FF6B6B]",
};

const SINGLE_LABELS = {
  elite: "Elite Singles (≥90)",
  strong: "Strong Singles (≥80)",
  good: "Good Singles (≥70)",
  risky: "Risky Singles (≥45)",
  avoid: "Avoid (<45)",
  best_single: "Best Single",
};

function QualityBadge({ score, tier, color }) {
  if (score == null) return null;
  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${qualityColorClass(color)}`}>
      {score} · {tier}
    </span>
  );
}

function SingleCard({ item, onAdd, bankroll, profile, showStake }) {
  const stake = showStake
    ? recommendStake(bankroll, { profile, quality: item.bet_quality_score })
  : null;
  const copyText = `${item.fixture_label} — ${item.market_label}: ${item.prediction}`;
  return (
    <div className="rounded-xl border border-white/[0.06] bg-black/25 p-4">
      <div className="flex flex-wrap justify-between gap-2 mb-2">
        <div>
          <p className="text-xs text-[#64748B]">{item.league}</p>
          <p className="font-semibold text-white">{item.fixture_label}</p>
        </div>
        <QualityBadge score={item.bet_quality_score} tier={item.bet_quality_tier} color={item.bet_quality_color} />
      </div>
      <p className="text-sm text-[#F8FAFC]">
        <span className="text-[#94A3B8]">{item.market_label}:</span> {item.prediction}
      </p>
      <p className="text-[11px] text-[#64748B] mt-1">{item.reason}</p>
      {item.caution && <p className="text-[10px] text-[#FF9F43] mt-1">Caution — best available</p>}
      <div className="flex flex-wrap gap-2 mt-3 text-[11px] text-[#94A3B8]">
        <span>Risk {item.risk_level}</span>
        {item.odds_decimal && (
          <span>
            Odds {item.odds_decimal}{item.odds_estimated ? " (est.)" : ""}
          </span>
        )}
        {showStake && stake && <span>Stake {formatCurrency(stake.recommended_stake)}</span>}
      </div>
      <div className="flex gap-2 mt-3">
        <Button type="button" size="sm" variant="outline" className="border-white/10" onClick={() => onAdd(item)}>
          <Plus className="w-3 h-3 mr-1" /> Slip
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => navigator.clipboard?.writeText(copyText)}
        >
          <Copy className="w-3 h-3 mr-1" /> Copy
        </Button>
        <Button asChild size="sm" variant="ghost">
          <Link to={`/matches/${item.fixture_id}?competition=${item.competition_key || ""}`}>Detail</Link>
        </Button>
        <AddToPaperBetButton
          size="sm"
          variant="ghost"
          bet={{
            fixture_id: item.fixture_id,
            market: item.market,
            prediction: item.prediction,
            bet_quality_score: item.bet_quality_score,
            odds_decimal: item.odds_decimal,
            odds_estimated: item.odds_estimated,
            competition_key: item.competition_key,
            home_team: item.home_team,
            away_team: item.away_team,
            snapshot_id: item.snapshot_id,
            source_page: "betting-plan",
          }}
        />
      </div>
    </div>
  );
}

function ComboBlock({ combo, onAddCombo }) {
  if (!combo) return null;
  const empty = combo.empty_reason;
  return (
    <TerminalCard className={combo.risk === "High" ? "border-[#FF6B6B]/30" : ""}>
      <div className="flex justify-between items-start gap-2 mb-3">
        <div>
          <h3 className="font-bold text-[#F8FAFC] flex items-center gap-2">
            <Layers className="w-4 h-4 text-[#FFD166]" /> {combo.label}
          </h3>
          <p className="text-xs text-[#94A3B8]">Risk {combo.risk}</p>
        </div>
        {combo.combined_quality != null && (
          <span className="text-sm text-[#7DD3FC]">Avg quality {combo.combined_quality}</span>
        )}
      </div>
      {combo.preview_only ? (
        <p className="text-sm text-[#94A3B8]">Preview — upgrade to see full combo legs.</p>
      ) : empty ? (
        <p className="text-sm text-[#94A3B8]">
          No combo — {empty.replace(/_/g, " ")} ({combo.eligible_candidate_count || 0} candidates)
        </p>
      ) : (
        <>
          {combo.caution_warning && <p className="text-xs text-[#FF9F43] mb-2">{combo.caution_warning}</p>}
          {combo.missing_odds_warning && (
            <p className="text-xs text-[#FFD166] mb-2">Some legs missing odds — returns are estimates only.</p>
          )}
          <div className="space-y-2 mb-3">
            {(combo.legs || []).map((leg, i) => (
              <div key={i} className="rounded-lg bg-black/30 px-3 py-2 text-sm">
                <p className="text-[#64748B] text-xs">{leg.fixture_label}</p>
                <p className="text-white">{leg.market_label}: {leg.prediction}</p>
                <p className="text-[10px] text-[#94A3B8]">{leg.reason}</p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-3 text-sm mb-3">
            {combo.combined_odds && <span className="text-[#FFD166]">Combined odds {combo.combined_odds}</span>}
            <span className="text-[#94A3B8]">{combo.leg_count} legs</span>
          </div>
          <Button type="button" size="sm" onClick={() => onAddCombo(combo)} disabled={!combo.legs?.length}>
            <Plus className="w-4 h-4 mr-1" /> Add combo to slip
          </Button>
          {!combo.preview_only && combo.legs?.length > 0 && (
            <AddToPaperBetButton
              label="Track This Combo"
              combo={{
                legs: combo.legs,
                combo_type: combo.type,
                source_page: "betting-plan",
              }}
            />
          )}
        </>
      )}
    </TerminalCard>
  );
}

function PortfolioCard({ portfolio }) {
  if (!portfolio) return null;
  return (
    <TerminalCard>
      <h3 className="font-bold text-white mb-1">{portfolio.name}</h3>
      {portfolio.warning && <p className="text-xs text-[#FF9F43] mb-2">{portfolio.warning}</p>}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div><span className="text-[#64748B]">Bets</span><p>{portfolio.bet_count}</p></div>
        <div><span className="text-[#64748B]">Exposure</span><p>{portfolio.total_exposure_pct}%</p></div>
        <div><span className="text-[#64748B]">Total stake</span><p>{formatCurrency(portfolio.total_stake)}</p></div>
        <div><span className="text-[#64748B]">Avg quality</span><p>{portfolio.average_quality ?? "—"}</p></div>
      </div>
      {portfolio.expected_return != null && (
        <p className="text-xs text-[#7DD3FC] mt-2">Est. return {formatCurrency(portfolio.expected_return)}</p>
      )}
      <p className="text-[10px] text-[#64748B] mt-2">{portfolio.risk_warning}</p>
    </TerminalCard>
  );
}

export default function BettingPlanPage() {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [bankroll, setBankroll] = useState(100);
  const [profile, setProfile] = useState("balanced");
  const [activeDay, setActiveDay] = useState(null);
  const { addLeg, clearSlip } = useBetSlip();
  const { user } = useAuth();

  const subscriptionPlan = normalizePlan(user?.subscription || user);
  const showCombos = canViewCombos({ plan: subscriptionPlan });
  const showBankroll = subscriptionPlan !== "free";
  const showPortfolios = ["pro", "enterprise", "owner"].includes(subscriptionPlan) || user?.role === "owner";
  const isOwner = ["owner", "admin", "super_admin"].includes(String(user?.role || "").toLowerCase());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBettingPlanToday({
        bankroll: showBankroll ? bankroll : undefined,
        profile,
      });
      setPlan(data);
      const keys = Object.keys(data.days || {});
      setActiveDay((prev) => (prev && keys.includes(prev) ? prev : keys[0] || null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load betting plan");
      setPlan(null);
    } finally {
      setLoading(false);
    }
  }, [bankroll, profile, showBankroll]);

  useEffect(() => {
    load();
  }, [load]);

  const dayData = useMemo(() => (plan?.days && activeDay ? plan.days[activeDay] : null), [plan, activeDay]);
  const dayKeys = useMemo(() => Object.keys(plan?.days || {}), [plan]);

  const addSingle = (item) => {
    addLeg({
      fixture_id: item.fixture_id,
      competition_key: item.competition_key,
      home_team: item.home_team,
      away_team: item.away_team,
      market: item.market,
      selection: item.prediction,
      label: `${item.market_label}: ${item.prediction}`,
      confidence: item.confidence,
    });
  };

  const addCombo = (combo) => {
    clearSlip();
    (combo.legs || []).forEach((leg) => addSingle(leg));
  };

  const dq = dayData?.day_quality;

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-24">
      <SectionHeader
        eyebrow="🤖 AI Assistant"
        title="AI Betting Plan"
        subtitle="Daily singles, combos, bankroll sizing, and portfolios from PredOps + Bet Quality. Research only — not betting advice."
      />

      {dayData && (
        <ShareButton
          type="plan"
          label="Share today's plan"
          payload={{
            date: activeDay,
            day_quality: dayData.day_quality,
            best_singles: dayData.best_single_bets || [],
            combos: dayData.combos,
          }}
        />
      )}

      <TerminalCard className="border-[#FFD166]/20">
        <p className="text-sm text-[#FFD166]">Planning only — we never place bets. Uses cached PredOps snapshots and Bet Quality overlay.</p>
      </TerminalCard>

      <div className="flex flex-wrap gap-3 items-end justify-between">
        {showBankroll && (
          <div className="flex flex-wrap gap-2 items-center">
            <PiggyBank className="w-4 h-4 text-[#94A3B8]" />
            <span className="text-xs text-[#94A3B8]">Bankroll</span>
            {BANKROLL_PRESETS.map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setBankroll(v)}
                className={`px-2 py-1 rounded text-xs border ${bankroll === v ? "border-[#00E676] text-[#00E676]" : "border-white/10 text-[#94A3B8]"}`}
              >
                €{v}
              </button>
            ))}
            <input
              type="number"
              min={1}
              value={bankroll}
              onChange={(e) => setBankroll(Number(e.target.value) || 0)}
              className="w-20 px-2 py-1 rounded bg-black/30 border border-white/10 text-sm"
            />
          </div>
        )}
        {showBankroll && (
          <div className="flex gap-1">
            {Object.entries(RISK_PROFILES).map(([k, v]) => (
              <button
                key={k}
                type="button"
                onClick={() => setProfile(k)}
                className={`px-3 py-1 rounded-lg text-xs border ${profile === k ? "border-[#3B82F6] text-white bg-[#3B82F6]/20" : "border-white/10 text-[#94A3B8]"}`}
              >
                {v.label}
              </button>
            ))}
          </div>
        )}
        <Button variant="outline" size="sm" onClick={load} disabled={loading} className="border-white/10 ml-auto">
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {error && <TerminalCard className="text-red-300 border-red-500/30">{error}</TerminalCard>}

      {loading && (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-[#00E676]/20 border-t-[#00E676] rounded-full animate-spin" />
        </div>
      )}

      {!loading && plan && (
        <>
          <div className="flex gap-2">
            {dayKeys.map((dk) => (
              <button
                key={dk}
                type="button"
                onClick={() => setActiveDay(dk)}
                className={`px-4 py-2 rounded-lg text-sm border flex items-center gap-1 ${activeDay === dk ? "bg-[#00E676]/15 border-[#00E676]/40 text-[#00E676]" : "border-white/10 text-[#94A3B8]"}`}
              >
                <Calendar className="w-3.5 h-3.5" /> {dk}
              </button>
            ))}
          </div>

          {dq && (
            <TerminalCard className={DAY_QUALITY_STYLE[dq.label] || DAY_QUALITY_STYLE.Good}>
              <div className="flex items-start gap-3">
                <Sparkles className="w-6 h-6 shrink-0" />
                <div>
                  <p className="text-lg font-bold">Today is a {dq.overall_day_quality} betting day</p>
                  <p className="text-sm mt-1 opacity-90">{dq.recommendation}</p>
                  <p className="text-xs mt-2 opacity-75">
                    Elite {dq.elite_count} · Strong+ {dq.strong_count} · Avoid {dq.avoid_count} · Avg quality {dq.average_quality}
                  </p>
                </div>
              </div>
            </TerminalCard>
          )}

          <section className="space-y-3">
            <h2 className="text-lg font-semibold flex items-center gap-2 text-white">
              <Target className="w-5 h-5 text-[#00E676]" /> Best Singles
            </h2>
            <div className="grid md:grid-cols-2 gap-3">
              {(dayData?.best_single_bets || []).length === 0 ? (
                <p className="text-sm text-[#94A3B8]">No singles for this day yet.</p>
              ) : (
                dayData.best_single_bets.map((item) => (
                  <SingleCard
                    key={`${item.fixture_id}-${item.market}`}
                    item={item}
                    onAdd={addSingle}
                    bankroll={bankroll}
                    profile={profile}
                    showStake={showBankroll}
                  />
                ))
              )}
            </div>
          </section>

          {Object.entries(dayData?.singles || {}).map(([cat, items]) => {
            if (cat === "best_single" || !items?.length) return null;
            if (subscriptionPlan === "free" && cat !== "best_single") return null;
            return (
              <section key={cat} className="space-y-2">
                <h3 className="text-sm font-medium text-[#94A3B8]">{SINGLE_LABELS[cat] || cat}</h3>
                <div className="grid md:grid-cols-2 gap-2">
                  {items.slice(0, 6).map((item) => (
                    <SingleCard
                      key={`${cat}-${item.fixture_id}-${item.market}`}
                      item={item}
                      onAdd={addSingle}
                      bankroll={bankroll}
                      profile={profile}
                      showStake={showBankroll}
                    />
                  ))}
                </div>
              </section>
            );
          })}

          {showCombos && (
            <section className="space-y-3">
              <h2 className="text-lg font-semibold flex items-center gap-2 text-white">
                <Layers className="w-5 h-5 text-[#FFD166]" /> Combo Manager
              </h2>
              <div className="grid lg:grid-cols-2 gap-4">
                {["safe", "balanced", "value", "high_odds"].map((k) => (
                  <ComboBlock key={k} combo={dayData?.combos?.[k]} onAddCombo={addCombo} />
                ))}
              </div>
            </section>
          )}

          {showPortfolios && plan.portfolios && (
            <section className="space-y-3">
              <h2 className="text-lg font-semibold flex items-center gap-2 text-white">
                <Shield className="w-5 h-5 text-[#7DD3FC]" /> Portfolios
              </h2>
              <div className="grid md:grid-cols-3 gap-3">
                <PortfolioCard portfolio={plan.portfolios.conservative} />
                <PortfolioCard portfolio={plan.portfolios.balanced} />
                <PortfolioCard portfolio={plan.portfolios.aggressive} />
              </div>
            </section>
          )}

          <section className="space-y-2">
            <h2 className="text-lg font-semibold flex items-center gap-2 text-[#FF6B6B]">
              <AlertTriangle className="w-5 h-5" /> Avoid List
            </h2>
            {(dayData?.avoid || []).length === 0 ? (
              <p className="text-sm text-[#94A3B8]">No avoid-rated markets today.</p>
            ) : (
              <div className="grid md:grid-cols-2 gap-2">
                {dayData.avoid.slice(0, 8).map((item) => (
                  <SingleCard key={`av-${item.fixture_id}-${item.market}`} item={item} onAdd={addSingle} bankroll={bankroll} profile={profile} showStake={false} />
                ))}
              </div>
            )}
          </section>

          {plan.performance_insights && (
            <section className="space-y-2">
              <h2 className="text-lg font-semibold flex items-center gap-2 text-white">
                <TrendingUp className="w-5 h-5" /> Performance Insights
              </h2>
              <TerminalCard>
                {plan.performance_insights.available ? (
                  <div className="space-y-2 text-sm">
                    <p>Evaluated: {plan.performance_insights.total_evaluated} · Overall {((plan.performance_insights.overall_accuracy || 0) * 100).toFixed(1)}%</p>
                    <ul className="text-[#94A3B8]">
                      {(plan.performance_insights.by_market || []).slice(0, 5).map((m) => (
                        <li key={m.market}>{m.market}: {m.winrate != null ? `${(m.winrate * 100).toFixed(1)}%` : "—"} (n={m.sample_size})</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="text-sm text-[#94A3B8]">{plan.performance_insights.message}</p>
                )}
              </TerminalCard>
            </section>
          )}

          {isOwner && dayData?.leg_count != null && (
            <p className="text-[10px] text-[#64748B]">Owner debug: {dayData.leg_count} market legs scanned for {activeDay}</p>
          )}
        </>
      )}

      <BetSlipDrawer />
    </div>
  );
}
