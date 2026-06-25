import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Crown,
  CreditCard,
  Calendar,
  ArrowUpRight,
  AlertTriangle,
  MessageSquare,
  AlertCircle,
  Loader2,
  ExternalLink,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import {
  contactAdmin,
  fetchSubscription,
  fetchUserQuota,
  fetchBillingStatus,
  fetchBillingHistory,
  createCustomerPortalSession,
  fetchBillingReadiness,
} from "@/api/saasApi";
import {
  CONTACT_CATEGORIES,
  normalizePlanKey,
  canUpgradeTo,
  isPremiumPlan,
  displayPlanLabel,
  isLegacyElitePlan,
} from "@/lib/pricingPlans";
import UpgradeComingSoonDialog from "@/components/subscription/UpgradeComingSoonDialog";
import QuotaWarningBanner from "@/components/subscription/QuotaWarningBanner";
import PlanUsageBar from "@/components/subscription/PlanUsageBar";
import PlanLadder from "@/components/subscription/PlanLadder";
import SubscriptionComparisonTable from "@/components/subscription/SubscriptionComparisonTable";

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return "—";
  }
}

export default function SubscriptionPage() {
  const { toast } = useToast();
  const contactRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [billingHistory, setBillingHistory] = useState([]);
  const [quota, setQuota] = useState(null);
  const [contactSubject, setContactSubject] = useState("");
  const [contactMessage, setContactMessage] = useState("");
  const [contactCategory, setContactCategory] = useState("subscription");
  const [contactSending, setContactSending] = useState(false);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [upgradePlanName, setUpgradePlanName] = useState("");
  const [upgradePlanKey, setUpgradePlanKey] = useState("starter");
  const [billingStatus, setBillingStatus] = useState(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [readiness, setReadiness] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [data, quotaData, statusData, historyData, readinessData] = await Promise.all([
        fetchSubscription(),
        fetchUserQuota().catch(() => null),
        fetchBillingStatus().catch(() => null),
        fetchBillingHistory().catch(() => ({ invoices: [] })),
        fetchBillingReadiness().catch(() => null),
      ]);
      setSubscription(data.subscription);
      setBillingHistory(
        historyData?.invoices?.length
          ? historyData.invoices.map((inv) => ({
              date: inv.date
                ? new Date(inv.date).toLocaleDateString([], {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })
                : "—",
              desc: `${(inv.currency || "EUR").toUpperCase()} subscription`,
              amount: inv.amount_paid != null ? `€${Number(inv.amount_paid).toFixed(2)}` : "—",
              status: inv.status || "—",
              hosted_invoice_url: inv.hosted_invoice_url || "",
            }))
          : data.billing_history || []
      );
      setQuota(quotaData);
      setBillingStatus(statusData);
      setReadiness(readinessData);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not load subscription data");
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

  const rawPlan = subscription?.plan || "free";
  const currentPlan = normalizePlanKey(rawPlan);
  const isPremiumActive = isPremiumPlan(currentPlan);
  const planLabel = displayPlanLabel(rawPlan);
  const priceEur = quota?.price_eur ?? (currentPlan === "starter" ? 5 : currentPlan === "pro" ? 19 : 0);
  const limit = quota?.monthly_limit ?? quota?.daily_limit ?? 0;
  const used = quota?.used_this_period ?? quota?.used_today ?? 0;
  const remaining = quota?.remaining ?? 0;
  const percent = quota?.percent_used ?? (limit > 0 ? Math.round((used / limit) * 100) : 0);

  const checkoutConfigured =
    readiness?.checkout_enabled === true || readiness?.checkout_configured === true;
  const checkoutPending = billingStatus?.checkout_pending === true;
  const cancelAtPeriodEnd = billingStatus?.cancel_at_period_end === true;
  const portalEnabled = billingStatus?.portal_enabled === true || readiness?.portal_enabled === true;
  const renewalDate = billingStatus?.current_period_end || quota?.period_end || quota?.next_reset_date;
  const billingStatusLabel = billingStatus?.billing_status || subscription?.status || "active";
  const lastPaymentStatus = billingStatus?.last_payment_status;

  const openUpgrade = (planName, planKey) => {
    if (!canUpgradeTo(currentPlan, planKey)) return;
    setUpgradePlanName(planName || "Starter");
    setUpgradePlanKey(planKey);
    setUpgradeOpen(true);
  };

  const scrollToContact = () => {
    setUpgradeOpen(false);
    setContactCategory("subscription");
    contactRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleManageSubscription = async () => {
    setPortalLoading(true);
    try {
      const result = await createCustomerPortalSession(`${window.location.origin}/subscription`);
      const url = result?.portal_url;
      if (!url) throw new Error("Billing portal URL is not available from the server.");
      window.location.href = url;
    } catch (err) {
      toast({
        title: "Could not open billing portal",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setPortalLoading(false);
    }
  };

  const onContactAdmin = async (e) => {
    e.preventDefault();
    if (!contactSubject.trim() || !contactMessage.trim()) return;
    setContactSending(true);
    try {
      const res = await contactAdmin({
        subject: contactSubject.trim(),
        message: contactMessage.trim(),
        category: contactCategory,
      });
      setContactSubject("");
      setContactMessage("");
      toast({ title: res.message || "Message sent successfully" });
    } catch (err) {
      toast({
        title: "Could not send message",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setContactSending(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <div>
          <h1 className="text-2xl font-display font-bold">Subscription</h1>
          <p className="text-sm text-muted-foreground mt-1">Loading your plan and billing details…</p>
        </div>
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (loadError && !subscription && !quota) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <div>
          <h1 className="text-2xl font-display font-bold">Subscription</h1>
        </div>
        <div className="glass rounded-xl p-8 border border-red-500/30 text-center space-y-4">
          <AlertCircle className="w-10 h-10 text-red-400 mx-auto" />
          <p className="text-red-200">{loadError}</p>
          <Button variant="secondary" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-2" /> Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold">Subscription & Billing</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Your plan, monthly quota, and billing — all data from live account APIs.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} className="rounded-lg gap-2">
          <RefreshCw className="w-4 h-4" /> Refresh
        </Button>
      </div>

      {quota && !quota.bypass && (
        <QuotaWarningBanner warning={quota.quota_warning} percent={percent} remaining={remaining} />
      )}

      {checkoutPending && (
        <div className="rounded-xl p-4 border border-primary/40 bg-primary/10 flex gap-3 items-start text-primary">
          <Loader2 className="w-5 h-5 animate-spin flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-sm">Payment processing</p>
            <p className="text-xs opacity-90 mt-0.5">
              Waiting for Stripe confirmation. Your plan will update automatically.
            </p>
          </div>
        </div>
      )}

      {cancelAtPeriodEnd && currentPlan !== "free" && (
        <div className="rounded-xl p-4 border border-yellow-500/40 bg-yellow-500/10 flex gap-3 items-start text-yellow-200">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-sm">Cancellation scheduled</p>
            <p className="text-xs opacity-90 mt-0.5">
              Your subscription ends on {formatDate(renewalDate)}. You keep access until then.
            </p>
          </div>
        </div>
      )}

      <div className="glass rounded-xl p-6 glow-blue space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-6">
          <div className="flex items-start gap-4 flex-1 min-w-0">
            <div className="w-12 h-12 rounded-xl bg-primary/20 flex items-center justify-center flex-shrink-0">
              <Crown className="w-6 h-6 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <div className="font-display font-bold text-lg">{planLabel} Plan</div>
                {isPremiumActive && (
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-accent/20 text-accent border border-accent/30">
                    Premium active
                  </span>
                )}
                {isLegacyElitePlan(rawPlan) && (
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-violet-500/15 text-violet-200 border border-violet-500/30">
                    Legacy tier mapped to Pro
                  </span>
                )}
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                {currentPlan === "free" ? "€0/month" : `€${priceEur}/month`}
              </div>
              <dl className="text-xs text-muted-foreground mt-3 space-y-1">
                <div className="flex gap-2">
                  <dt className="shrink-0">Billing cycle start:</dt>
                  <dd>{formatDate(quota?.period_start)}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="shrink-0">Next reset / renewal:</dt>
                  <dd>{formatDate(renewalDate)}</dd>
                </div>
                <div className="flex gap-2 capitalize">
                  <dt className="shrink-0">Subscription:</dt>
                  <dd>{billingStatus?.subscription_status || subscription?.status || "active"}</dd>
                </div>
                {billingStatusLabel && (
                  <div className="flex gap-2 capitalize">
                    <dt className="shrink-0">Billing status:</dt>
                    <dd>{billingStatusLabel.replace(/_/g, " ")}</dd>
                  </div>
                )}
                {lastPaymentStatus && (
                  <div className="flex gap-2 capitalize">
                    <dt className="shrink-0">Last payment:</dt>
                    <dd>{lastPaymentStatus.replace(/_/g, " ")}</dd>
                  </div>
                )}
              </dl>
            </div>
          </div>

          <div className="flex gap-2 flex-shrink-0 flex-wrap lg:flex-col lg:items-stretch">
            {portalEnabled && currentPlan !== "free" && (
              <Button
                size="sm"
                variant="outline"
                className="rounded-lg"
                disabled={portalLoading}
                onClick={handleManageSubscription}
              >
                {portalLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  "Manage billing"
                )}
              </Button>
            )}
            {canUpgradeTo(currentPlan, "pro") && (
              <Button
                size="sm"
                className="bg-accent text-accent-foreground hover:bg-accent/90 rounded-lg glow-gold"
                onClick={() =>
                  openUpgrade(currentPlan === "free" ? "Starter" : "Pro", currentPlan === "free" ? "starter" : "pro")
                }
              >
                Upgrade <ArrowUpRight className="w-4 h-4 ml-1" />
              </Button>
            )}
          </div>
        </div>

        <PlanUsageBar
          used={used}
          limit={limit}
          remaining={remaining}
          percent={percent}
          bypass={quota?.bypass}
        />
      </div>

      <div>
        <h2 className="font-display font-semibold mb-1">Plan ladder</h2>
        <p className="text-xs text-muted-foreground mb-4">
          Free → Starter → Pro. Elite is shown as coming soon — not available for self-serve checkout.
        </p>
        <PlanLadder
          currentPlan={currentPlan}
          checkoutConfigured={checkoutConfigured}
          portalEnabled={portalEnabled}
          onUpgrade={openUpgrade}
          onPortal={handleManageSubscription}
          onContact={scrollToContact}
        />
      </div>

      <SubscriptionComparisonTable currentPlan={currentPlan} />

      <div className="glass rounded-xl p-4 border border-yellow-500/30 flex gap-3 items-start">
        <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-muted-foreground leading-relaxed">
          <span className="text-yellow-400 font-semibold">Entertainment purposes only.</span> For
          informational and entertainment use only.
        </p>
      </div>

      <div ref={contactRef} className="glass rounded-xl p-5">
        <h2 className="font-display font-semibold mb-4 flex items-center gap-2">
          <MessageSquare className="w-4 h-4" /> Message Admin
        </h2>
        <p className="text-xs text-muted-foreground mb-4">
          Use this if checkout or billing portal is unavailable, or for plan change requests.
        </p>
        <form onSubmit={onContactAdmin} className="space-y-3 max-w-lg">
          <Select value={contactCategory} onValueChange={setContactCategory}>
            <SelectTrigger className="bg-white/5 border-white/10 rounded-lg">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent className="bg-card border-white/10">
              {CONTACT_CATEGORIES.map((c) => (
                <SelectItem key={c.value} value={c.value}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            placeholder="Subject"
            value={contactSubject}
            onChange={(e) => setContactSubject(e.target.value)}
            className="bg-white/5 border-white/10 rounded-lg"
            maxLength={200}
            required
          />
          <Textarea
            placeholder="Your message…"
            value={contactMessage}
            onChange={(e) => setContactMessage(e.target.value)}
            className="bg-white/5 border-white/10 rounded-lg min-h-[100px]"
            maxLength={4000}
            required
          />
          <Button type="submit" disabled={contactSending} className="rounded-lg">
            {contactSending ? "Sending…" : "Send Message"}
          </Button>
        </form>
      </div>

      <div className="glass rounded-xl p-5">
        <h2 className="font-display font-semibold mb-4 flex items-center gap-2">
          <CreditCard className="w-4 h-4" /> Billing History
        </h2>
        {billingHistory.length === 0 ? (
          <div className="text-center py-10 text-sm text-muted-foreground">
            <Calendar className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p className="font-medium text-foreground">No invoices yet</p>
            <p className="text-xs mt-1 max-w-sm mx-auto">
              Paid subscriptions will show Stripe invoice history here once billing is active.
            </p>
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
                    <td className="py-3 tabular-nums">{b.amount}</td>
                    <td className="py-3">
                      <span className="px-2 py-1 rounded-md text-xs font-medium bg-green-500/10 text-green-400 capitalize">
                        {b.status}
                      </span>
                      {b.hosted_invoice_url && (
                        <a
                          href={b.hosted_invoice_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-2 inline-flex text-primary"
                          aria-label="Open invoice"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <UpgradeComingSoonDialog
        open={upgradeOpen}
        onOpenChange={setUpgradeOpen}
        planName={upgradePlanName}
        planKey={upgradePlanKey}
        currentPlan={currentPlan}
        onContactAdmin={scrollToContact}
      />
    </div>
  );
}
