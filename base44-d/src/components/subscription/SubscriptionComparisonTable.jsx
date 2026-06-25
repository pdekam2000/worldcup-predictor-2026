import React from "react";
import { Check, X } from "lucide-react";
import { COMPARISON_ROWS } from "@/lib/pricingPlans";

function CellValue({ value }) {
  if (value === true) return <Check className="w-4 h-4 text-primary mx-auto" />;
  if (value === false) return <X className="w-4 h-4 text-muted-foreground/40 mx-auto" />;
  return <span className="text-xs text-muted-foreground">{value}</span>;
}

const PLAN_COLUMNS = [
  { key: "free", label: "Free" },
  { key: "starter", label: "Starter" },
  { key: "pro", label: "Pro" },
];

export default function SubscriptionComparisonTable({ currentPlan }) {
  return (
    <div className="glass rounded-2xl p-4 sm:p-6 border border-white/10 overflow-x-auto">
      <h2 className="font-display font-semibold mb-1">Feature comparison</h2>
      <p className="text-xs text-muted-foreground mb-4">
        Compare quotas and product access across plans. Future markets are labeled honestly.
      </p>
      <table className="w-full min-w-[560px] text-sm">
        <thead>
          <tr className="text-left text-muted-foreground text-xs border-b border-white/10">
            <th className="pb-3 pr-4 font-medium">Feature</th>
            {PLAN_COLUMNS.map((col) => (
              <th
                key={col.key}
                className={`pb-3 px-2 font-medium text-center ${
                  col.key === currentPlan ? "text-primary bg-primary/5 rounded-t-lg" : ""
                }`}
              >
                {col.label}
                {col.key === currentPlan && (
                  <span className="block text-[10px] font-normal text-primary/80 mt-0.5">Your plan</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {COMPARISON_ROWS.map((row) => (
            <tr key={row.label}>
              <td className="py-3 pr-4 text-muted-foreground">{row.label}</td>
              {PLAN_COLUMNS.map((col) => (
                <td
                  key={col.key}
                  className={`py-3 px-2 text-center ${col.key === currentPlan ? "bg-primary/5" : ""}`}
                >
                  <CellValue value={row[col.key]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
