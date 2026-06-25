import React from "react";
import { Check, Crown, Zap, User, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  PRICING_PLANS,
  ELITE_PLAN_COMING_SOON,
  canUpgradeTo,
  planRank,
} from "@/lib/pricingPlans";

const ICONS = { free: User, starter: Zap, pro: Crown, elite: Sparkles };

function planButtonState(plan, { currentPlan, checkoutConfigured, portalEnabled }) {
  if (plan.comingSoon) {
    return {
      label: "Coming soon",
      disabled: true,
      hint: "Not available for self-serve checkout",
      action: "none",
    };
  }

  if (plan.key === currentPlan) {
    return { label: "Current plan", disabled: true, hint: null, action: "none" };
  }

  if (planRank(plan.key) < planRank(currentPlan)) {
    if (portalEnabled) {
      return {
        label: "Manage in billing portal",
        disabled: false,
        hint: "Downgrades are handled in Stripe customer portal",
        action: "portal",
      };
    }
    return {
      label: "Contact admin to change",
      disabled: false,
      hint: "Billing portal not available — contact support",
      action: "contact",
    };
  }

  if (!canUpgradeTo(currentPlan, plan.key)) {
    return { label: "Included", disabled: true, hint: null, action: "none" };
  }

  if (!checkoutConfigured) {
    return {
      label: `Upgrade to ${plan.name}`,
      disabled: false,
      hint: "Checkout may be unavailable — we'll show options",
      action: "upgrade",
    };
  }

  return {
    label: `Upgrade to ${plan.name}`,
    disabled: false,
    hint: null,
    action: "upgrade",
  };
}

export default function PlanLadder({
  currentPlan,
  onUpgrade,
  onPortal,
  onContact,
  checkoutConfigured,
  portalEnabled,
}) {
  const ladder = [...PRICING_PLANS, ELITE_PLAN_COMING_SOON];

  return (
    <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4">
      {ladder.map((plan) => {
        const Icon = ICONS[plan.key] || User;
        const isCurrent = !plan.comingSoon && plan.key === currentPlan;
        const btn = planButtonState(plan, { currentPlan, checkoutConfigured, portalEnabled });

        const handleClick = () => {
          if (btn.action === "upgrade") onUpgrade(plan.name, plan.key);
          else if (btn.action === "portal") onPortal();
          else if (btn.action === "contact") onContact();
        };

        return (
          <div
            key={plan.key}
            className={`terminal-card p-5 relative flex flex-col ${
              isCurrent
                ? "terminal-card-glow border-[#00E676]/35"
                : plan.recommended
                  ? "border-[#FFD166]/25"
                  : ""
            }`}
          >
            {isCurrent && (
              <div className="absolute -top-2.5 right-4 px-3 py-0.5 bg-[#00E676] text-[#070B14] text-xs font-bold rounded-full">
                Current
              </div>
            )}
            {plan.comingSoon && (
              <div className="absolute -top-2.5 left-4 px-3 py-0.5 bg-violet-500/20 text-violet-200 text-xs font-semibold rounded-full border border-violet-500/30">
                Coming soon
              </div>
            )}
            {plan.recommended && !isCurrent && !plan.comingSoon && (
              <div className="absolute -top-2.5 left-4 px-3 py-0.5 bg-[#FFD166]/20 text-[#FFD166] text-xs font-semibold rounded-full">
                Recommended
              </div>
            )}

            <div className="flex items-center gap-2 mb-3">
              <Icon className={`w-5 h-5 ${isCurrent || plan.recommended ? "text-[#00E676]" : "text-[#94A3B8]"}`} />
              <h3 className="font-display font-bold text-[#F8FAFC]">{plan.name}</h3>
            </div>

            <div className="mb-2">
              {plan.comingSoon || plan.price == null ? (
                <span className="text-lg font-display font-bold text-[#94A3B8]">TBD</span>
              ) : (
                <>
                  <span className="text-3xl font-display font-bold text-[#F8FAFC]">€{plan.price}</span>
                  {plan.price > 0 && <span className="text-[#94A3B8] text-sm">/mo</span>}
                </>
              )}
            </div>

            {!plan.comingSoon && (
              <p className="text-xs text-[#94A3B8] mb-3">
                {plan.monthlyPredictions}/month · {plan.markets.join(", ")}
              </p>
            )}
            {plan.comingSoon && (
              <p className="text-xs text-[#94A3B8] mb-3">{plan.description}</p>
            )}

            <ul className="space-y-1.5 mb-4 flex-1">
              {(plan.features || []).slice(0, 4).map((f) => (
                <li key={f} className="flex items-center gap-2 text-xs text-[#94A3B8]">
                  <Check className="w-3.5 h-3.5 text-[#00E676] flex-shrink-0" /> {f}
                </li>
              ))}
            </ul>

            <Button
              size="sm"
              className={`w-full rounded-lg mt-auto ${!btn.disabled && !isCurrent ? "bg-[#00E676] text-[#070B14] hover:bg-[#00E676]/90" : ""}`}
              variant={btn.disabled ? "outline" : isCurrent ? "outline" : "default"}
              disabled={btn.disabled}
              onClick={handleClick}
            >
              {btn.label}
            </Button>
            {btn.hint && (
              <p className="text-[10px] text-muted-foreground mt-2 text-center">{btn.hint}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
