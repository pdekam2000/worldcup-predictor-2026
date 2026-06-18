import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Check, Crown, Zap, User, CreditCard, Calendar, ArrowUpRight, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { fetchSubscription } from "@/api/saasApi";

const plans = [
  { name: "Free", key: "free", icon: User, monthly: 0, yearly: 0, features: ["1 prediction/day", "1X2 predictions", "Basic match info"], color: "border-white/10" },
  { name: "Pro", key: "pro", icon: Zap, monthly: 5, yearly: 50, features: ["3 predictions/day", "Over/Under & BTTS", "Confidence scores", "Match reports", "Specialist analysis"], color: "border-white/10" },
  { name: "Elite", key: "elite", icon: Crown, monthly: 19, yearly: 190, features: ["10 predictions/day", "Everything in Pro", "Premium analytics", "Historical data", "Priority support"], color: "border-primary", popular: true },
  { name: "Unlimited", key: "unlimited", icon: Crown, monthly: 85, yearly: 850, features: ["Unlimited predictions", "All Elite features", "API access", "Early predictions", "Dedicated support"], color: "border-accent" },
];

const planLabels = { free: "Free", pro: "Pro", elite: "Elite", unlimited: "Unlimited" };

export default function SubscriptionPage() {
  const { toast } = useToast();
  const [yearly, setYearly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [subscription, setSubscription] = useState(null);
  const [billingHistory, setBillingHistory] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSubscription();
      setSubscription(data.subscription);
      setBillingHistory(data.billing_history || []);
      setYearly(data.subscription?.billing_cycle === "yearly");
    } catch (err) {
      toast({
        title: "Could not load subscription",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const currentPlan = subscription?.plan || "free";
  const planLabel = planLabels[currentPlan] || "Free";
  const amount = subscription?.amount != null ? `€${Number(subscription.amount).toFixed(2)}` : "€0.00";
  const cycleLabel = subscription?.billing_cycle === "yearly" ? "year" : "month";
  const renewDate = subscription?.end_date
    ? new Date(subscription.end_date).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })
    : null;

  const onPlanSwitch = () => {
    toast({
      title: "Coming soon",
      description: "Stripe billing integration is planned for a future release.",
    });
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold">Subscription</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage your plan and billing.</p>
      </div>

      <div className="glass rounded-xl p-6 glow-blue">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-primary/20 flex items-center justify-center">
              <Crown className="w-6 h-6 text-primary" />
            </div>
            <div>
              <div className="font-display font-bold text-lg">{planLabel} Plan</div>
              <div className="text-sm text-muted-foreground">
                {currentPlan === "free"
                  ? "Free tier — upgrade anytime"
                  : `${amount}/${cycleLabel}${renewDate ? ` • Renews ${renewDate}` : ""}`}
              </div>
              <div className="text-xs text-muted-foreground mt-1 capitalize">Status: {subscription?.status || "active"}</div>
            </div>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" size="sm" className="border-white/10 rounded-lg" disabled={currentPlan === "free"} onClick={onPlanSwitch}>
              Cancel Plan
            </Button>
            <Button size="sm" className="bg-accent text-accent-foreground hover:bg-accent/90 rounded-lg glow-gold" disabled={currentPlan === "unlimited"} onClick={onPlanSwitch}>
              Upgrade <ArrowUpRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
        </div>
      </div>

      <div className="glass rounded-xl p-4 border border-yellow-500/30 flex gap-3 items-start">
        <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-muted-foreground leading-relaxed">
          <span className="text-yellow-400 font-semibold">Entertainment purposes only.</span> This platform is for informational and entertainment use only.
        </p>
      </div>

      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display font-semibold">Available Plans</h2>
          <div className="inline-flex items-center glass rounded-full p-1">
            <button onClick={() => setYearly(false)} className={`px-4 py-1.5 rounded-full text-xs font-medium transition-all ${!yearly ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>Monthly</button>
            <button onClick={() => setYearly(true)} className={`px-4 py-1.5 rounded-full text-xs font-medium transition-all ${yearly ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>Yearly</button>
          </div>
        </div>
        <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {plans.map((plan) => (
            <div key={plan.key} className={`glass rounded-xl p-5 border ${plan.color} ${plan.popular ? "glow-blue" : ""} relative`}>
              {plan.key === currentPlan && (
                <div className="absolute -top-2.5 right-4 px-3 py-0.5 bg-primary text-primary-foreground text-xs font-semibold rounded-full">Current</div>
              )}
              <div className="flex items-center gap-2 mb-3">
                <plan.icon className={`w-5 h-5 ${plan.popular ? "text-primary" : plan.key === "elite" ? "text-accent" : "text-muted-foreground"}`} />
                <h3 className="font-display font-bold">{plan.name}</h3>
              </div>
              <div className="mb-4">
                <span className="text-3xl font-display font-bold">€{yearly ? plan.yearly : plan.monthly}</span>
                {plan.monthly > 0 && <span className="text-muted-foreground text-sm">/{yearly ? "yr" : "mo"}</span>}
              </div>
              <ul className="space-y-2 mb-4">
                {plan.features.map((f, fi) => (
                  <li key={fi} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Check className="w-3.5 h-3.5 text-primary flex-shrink-0" /> {f}
                  </li>
                ))}
              </ul>
              <Button size="sm" className="w-full rounded-lg" variant={plan.key === currentPlan ? "outline" : "default"} disabled={plan.key === currentPlan} onClick={onPlanSwitch}>
                {plan.key === currentPlan ? "Current Plan" : `Switch to ${plan.name}`}
              </Button>
            </div>
          ))}
        </div>
      </div>

      <div className="glass rounded-xl p-5">
        <h2 className="font-display font-semibold mb-4 flex items-center gap-2"><CreditCard className="w-4 h-4" /> Billing History</h2>
        {billingHistory.length === 0 ? (
          <div className="text-center py-10 text-sm text-muted-foreground">
            <Calendar className="w-8 h-8 mx-auto mb-2 opacity-40" />
            No billing history yet. Payments will appear here after Stripe is connected.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted-foreground text-xs">
                  <th className="pb-3 font-medium">Date</th>
                  <th className="pb-3 font-medium">Description</th>
                  <th className="pb-3 font-medium">Amount</th>
                  <th className="pb-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {billingHistory.map((b, i) => (
                  <tr key={i}>
                    <td className="py-3 text-muted-foreground">{b.date}</td>
                    <td className="py-3 font-medium">{b.desc}</td>
                    <td className="py-3">{b.amount}</td>
                    <td className="py-3"><span className="px-2 py-1 rounded-md text-xs font-medium bg-green-500/10 text-green-400">{b.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
