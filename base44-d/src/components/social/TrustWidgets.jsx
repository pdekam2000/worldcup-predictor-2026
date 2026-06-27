import React, { useEffect, useState } from "react";
import { BarChart3, Shield, Target } from "lucide-react";
import { fetchPublicAccuracy } from "@/api/socialTrustApi";
import { TerminalCard } from "@/components/terminal";

export default function TrustWidgets({ trust: trustProp, compact = false }) {
  const [trust, setTrust] = useState(trustProp || null);

  useEffect(() => {
    if (trustProp) {
      setTrust(trustProp);
      return;
    }
    fetchPublicAccuracy()
      .then((d) => setTrust(d.accuracy))
      .catch(() => setTrust(null));
  }, [trustProp]);

  if (!trust?.data_available && !trust?.evaluated_predictions) {
    return (
      <TerminalCard className="text-sm text-muted-foreground">
        <Shield className="w-4 h-4 inline mr-2 opacity-60" />
        Trust metrics appear when enough evaluated predictions exist.
      </TerminalCard>
    );
  }

  const items = [
    {
      label: "30-day accuracy",
      value: trust.accuracy_30d_pct != null ? `${trust.accuracy_30d_pct}%` : "—",
      icon: Target,
    },
    {
      label: "Evaluated",
      value: trust.evaluated_predictions ?? "—",
      icon: BarChart3,
    },
    {
      label: "Best market",
      value: trust.best_market || "—",
      icon: Shield,
    },
  ];

  if (compact) {
    return (
      <p className="text-xs text-muted-foreground flex flex-wrap gap-3">
        {items.map((i) => (
          <span key={i.label}>
            {i.label}: <strong className="text-foreground">{i.value}</strong>
          </span>
        ))}
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {items.map((i) => (
        <TerminalCard key={i.label}>
          <p className="text-[10px] uppercase text-muted-foreground flex items-center gap-1">
            <i.icon className="w-3 h-3" /> {i.label}
          </p>
          <p className="text-xl font-bold mt-1">{i.value}</p>
        </TerminalCard>
      ))}
    </div>
  );
}
