import React from "react";
import { motion } from "framer-motion";
import { Check, Crown, Zap, User, AlertTriangle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { PRICING_PLANS, COMPARISON_ROWS } from "@/lib/pricingPlans";

const ICONS = { free: User, starter: Zap, pro: Crown };

function CellValue({ value }) {
  if (value === true) return <Check className="w-4 h-4 text-primary mx-auto" />;
  if (value === false) return <X className="w-4 h-4 text-muted-foreground/40 mx-auto" />;
  return <span className="text-xs text-muted-foreground">{value}</span>;
}

export default function PricingContent({ showHeader = true, ctaBase = "/register" }) {
  return (
    <div className="max-w-6xl mx-auto">
      {showHeader && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-12"
        >
          <span className="text-primary text-sm font-semibold tracking-widest uppercase">Pricing</span>
          <h2 className="text-3xl sm:text-4xl font-display font-bold mt-3 mb-4">Simple, transparent plans</h2>
          <p className="text-muted-foreground max-w-xl mx-auto">
            Start free with a monthly quota. Upgrade for higher limits and Pro markets. Paid plans use Stripe when billing is enabled; otherwise contact admin for early access.
          </p>
        </motion.div>
      )}

      <div className="grid md:grid-cols-3 gap-5 mb-12">
        {PRICING_PLANS.map((plan, i) => {
          const Icon = ICONS[plan.key] || User;
          return (
            <motion.div
              key={plan.key}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.06 }}
              className={`relative glass rounded-2xl p-6 border ${
                plan.recommended ? "border-primary glow-blue" : "border-white/10"
              }`}
            >
              {plan.recommended && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-primary text-primary-foreground text-xs font-semibold rounded-full whitespace-nowrap">
                  Recommended
                </div>
              )}
              <div className="flex items-center gap-3 mb-2">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${plan.recommended ? "bg-primary/20" : "bg-white/5"}`}>
                  <Icon className={`w-5 h-5 ${plan.recommended ? "text-primary" : "text-muted-foreground"}`} />
                </div>
                <h3 className="text-xl font-display font-bold">{plan.name}</h3>
              </div>
              <div className="mb-1">
                <span className="text-4xl font-display font-bold">€{plan.price}</span>
                {plan.price > 0 && <span className="text-muted-foreground text-sm">/month</span>}
              </div>
              <p className="text-xs text-muted-foreground mb-4">{plan.monthlyPredictions} predictions per month</p>
              <Link to={ctaBase}>
                <Button
                  className={`w-full rounded-xl mb-5 ${plan.recommended ? "glow-blue" : "bg-white/5 hover:bg-white/10 text-foreground border border-white/10"}`}
                  variant={plan.recommended ? "default" : "outline"}
                >
                  {plan.key === "free" ? "Get Started Free" : `Choose ${plan.name}`}
                </Button>
              </Link>
              <ul className="space-y-2">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-xs text-muted-foreground">
                    <Check className="w-3.5 h-3.5 text-primary flex-shrink-0 mt-0.5" />
                    {f}
                  </li>
                ))}
              </ul>
            </motion.div>
          );
        })}
      </div>

      <div className="glass rounded-2xl p-4 sm:p-6 border border-white/10 overflow-x-auto">
        <h3 className="font-display font-semibold mb-4 text-center sm:text-left">Compare plans</h3>
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="text-left text-muted-foreground text-xs border-b border-white/10">
              <th className="pb-3 pr-4 font-medium">Feature</th>
              <th className="pb-3 px-2 font-medium text-center">Free</th>
              <th className="pb-3 px-2 font-medium text-center text-primary">Starter</th>
              <th className="pb-3 px-2 font-medium text-center">Pro</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {COMPARISON_ROWS.map((row) => (
              <tr key={row.label}>
                <td className="py-3 pr-4 text-muted-foreground">{row.label}</td>
                <td className="py-3 px-2 text-center"><CellValue value={row.free} /></td>
                <td className="py-3 px-2 text-center bg-primary/5"><CellValue value={row.starter} /></td>
                <td className="py-3 px-2 text-center"><CellValue value={row.pro} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        className="mt-8 glass rounded-2xl p-5 border border-yellow-500/30 flex gap-4 items-start"
      >
        <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-yellow-400 font-semibold text-sm mb-1">For entertainment purposes only</p>
          <p className="text-muted-foreground text-xs leading-relaxed">
            WorldCup Predictor Pro is for informational and entertainment use only. We are not responsible for financial decisions or gambling activity based on our predictions.
          </p>
        </div>
      </motion.div>
    </div>
  );
}
