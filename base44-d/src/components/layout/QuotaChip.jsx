import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Zap } from "lucide-react";
import { fetchUserQuota } from "@/api/saasApi";
import { normalizePlanKey } from "@/lib/pricingPlans";

const PLAN_LABELS = { free: "Free", starter: "Starter", pro: "Pro" };

export default function QuotaChip() {
  const [quota, setQuota] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchUserQuota()
      .then((data) => {
        if (!cancelled) setQuota(data);
      })
      .catch(() => {
        if (!cancelled) setQuota(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!quota || quota.bypass) return null;

  const plan = normalizePlanKey(quota.plan);
  const planLabel = PLAN_LABELS[plan] || "Free";
  const remaining = quota.remaining ?? 0;
  const limit = quota.monthly_limit ?? 0;

  return (
    <Link
      to="/subscription"
      className="flex items-center gap-2 px-2 sm:px-3 py-1.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 transition-colors text-xs"
      title="View subscription"
    >
      <Zap className="w-3.5 h-3.5 text-primary flex-shrink-0" />
      <span className="text-muted-foreground">{planLabel}</span>
      <span className="text-foreground font-medium tabular-nums">
        {remaining}/{limit}
      </span>
    </Link>
  );
}
