import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Loader2, MessageSquare } from "lucide-react";
import { createCheckoutSession, fetchBillingReadiness } from "@/api/saasApi";
import { useToast } from "@/components/ui/use-toast";
import { canUpgradeTo, normalizePlanKey } from "@/lib/pricingPlans";
import { CHECKOUT_INACTIVE_MSG, checkoutErrorMessage } from "@/lib/checkoutErrors";

const PLAN_KEY = {
  Starter: "starter",
  starter: "starter",
  Pro: "pro",
  pro: "pro",
};

/** Upgrade dialog — Stripe checkout when configured; safe fallback otherwise. */
export default function UpgradeComingSoonDialog({
  open,
  onOpenChange,
  planName,
  planKey: planKeyProp,
  currentPlan = "free",
  onContactAdmin,
}) {
  const { toast } = useToast();
  const [readiness, setReadiness] = useState(null);
  const [loadingReadiness, setLoadingReadiness] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [error, setError] = useState("");

  const normalizedCurrent = normalizePlanKey(currentPlan);
  const planKey = planKeyProp || PLAN_KEY[planName] || PLAN_KEY.Starter;
  const upgradeAllowed = canUpgradeTo(normalizedCurrent, planKey);
  const checkoutConfigured =
    readiness?.checkout_enabled === true || readiness?.checkout_configured === true;

  useEffect(() => {
    if (!open || !upgradeAllowed) {
      setReadiness(null);
      setError("");
      return;
    }
    setError("");
    setLoadingReadiness(true);
    fetchBillingReadiness()
      .then(setReadiness)
      .catch(() =>
        setReadiness({
          checkout_enabled: false,
          checkout_configured: false,
          message: CHECKOUT_INACTIVE_MSG,
        }),
      )
      .finally(() => setLoadingReadiness(false));
  }, [open, upgradeAllowed]);

  const handleCheckout = async () => {
    if (!upgradeAllowed || !checkoutConfigured) return;
    setError("");
    setCheckoutLoading(true);
    try {
      const result = await createCheckoutSession(planKey);
      const url = result?.checkout_url;
      if (!url || typeof url !== "string" || !/^https?:\/\//i.test(url)) {
        throw new Error(readiness?.message || CHECKOUT_INACTIVE_MSG);
      }
      window.location.href = url;
    } catch (err) {
      const message = checkoutErrorMessage(err, CHECKOUT_INACTIVE_MSG);
      setError(message);
      toast({
        title: "Checkout unavailable",
        description: message,
        variant: "destructive",
      });
    } finally {
      setCheckoutLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass border-white/10 sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display">
            {!upgradeAllowed
              ? "Premium Active"
              : planName
                ? `Upgrade to ${planName}`
                : "Upgrade plan"}
          </DialogTitle>
          <DialogDescription className="text-muted-foreground pt-2 space-y-2">
            {!upgradeAllowed ? (
              <p>You already have an active premium plan. Lower tiers are included — no additional purchase needed.</p>
            ) : loadingReadiness ? (
              <p>Checking payment availability…</p>
            ) : checkoutConfigured ? (
              <>
                <p>Continue to secure Stripe checkout for {planName || "your plan"}.</p>
                <p className="text-xs">Your plan activates after payment is confirmed — not on this screen.</p>
              </>
            ) : (
              <p>{readiness?.message || CHECKOUT_INACTIVE_MSG}</p>
            )}
            {error && <p className="text-destructive text-sm">{error}</p>}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-lg">
            Close
          </Button>
          {!upgradeAllowed ? null : checkoutConfigured ? (
            <Button
              onClick={handleCheckout}
              disabled={checkoutLoading || loadingReadiness}
              className="rounded-lg gap-2"
            >
              {checkoutLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                `Checkout ${planName || "plan"}`
              )}
            </Button>
          ) : onContactAdmin ? (
            <Button onClick={onContactAdmin} className="rounded-lg gap-2">
              <MessageSquare className="w-4 h-4" /> Message Admin
            </Button>
          ) : (
            <Button asChild className="rounded-lg gap-2">
              <Link to="/subscription">
                <MessageSquare className="w-4 h-4" /> Message Admin
              </Link>
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
