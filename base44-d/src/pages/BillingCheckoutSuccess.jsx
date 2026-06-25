import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import AuthLayout from "@/components/AuthLayout";
import { fetchBillingStatus } from "@/api/saasApi";

const PAID_PLANS = new Set(["starter", "pro"]);

export default function BillingCheckoutSuccess() {
  const [message, setMessage] = useState("Payment received. Activating subscription…");
  const [activated, setActivated] = useState(false);

  useEffect(() => {
    let attempts = 0;
    let cancelled = false;

    const poll = async () => {
      if (cancelled || attempts >= 15) return;
      attempts += 1;
      try {
        const data = await fetchBillingStatus();
        const plan = (data?.plan || "free").toLowerCase();
        const pending = data?.checkout_pending === true;
        if (PAID_PLANS.has(plan) && !pending) {
          setActivated(true);
          setMessage("Subscription activated. Your plan is now active.");
          return;
        }
      } catch {
        /* keep polling */
      }
      if (!cancelled && attempts < 15) {
        window.setTimeout(poll, 2500);
      }
    };

    poll();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AuthLayout
      icon={CheckCircle2}
      title={activated ? "Subscription active" : "Payment received"}
      subtitle={message}
      footer={
        <Link to="/subscription" className="text-primary font-medium hover:underline">
          Back to subscription
        </Link>
      }
    >
      <div className="space-y-4 text-sm text-muted-foreground">
        <div className={`flex items-center gap-3 p-4 rounded-lg ${activated ? "bg-green-500/10 text-green-400" : "bg-primary/10 text-primary"}`}>
          {activated ? (
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
          ) : (
            <Loader2 className="w-5 h-5 animate-spin flex-shrink-0" />
          )}
          <p>{message}</p>
        </div>
        <p>
          {activated
            ? "You can manage billing and view invoices on your subscription page."
            : "Your plan will update automatically once Stripe confirms the subscription. This usually takes a few seconds."}
        </p>
        <Button asChild className="w-full h-12">
          <Link to="/subscription">View subscription</Link>
        </Button>
      </div>
    </AuthLayout>
  );
}
