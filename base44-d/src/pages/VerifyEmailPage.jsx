import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Mail, Loader2, CheckCircle, AlertCircle } from "lucide-react";
import AuthLayout from "@/components/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { resendVerificationEmail, verifyEmailToken } from "@/api/authApi";

export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const token = params.get("token") || "";
  const emailParam = params.get("email") || "";

  const [email, setEmail] = useState(emailParam);
  const [status, setStatus] = useState(token ? "verifying" : "pending");
  const [message, setMessage] = useState(location.state?.registrationMessage || "");
  const [deliveryWarning, setDeliveryWarning] = useState(
    location.state?.verification_email_sent === false ? location.state?.registrationMessage || "" : "",
  );
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (location.state?.registrationMessage) {
      navigate(location.pathname + location.search, { replace: true, state: {} });
    }
  }, [location.pathname, location.search, location.state, navigate]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const payload = await verifyEmailToken(token);
        if (cancelled) return;
        setStatus("verified");
        setMessage(payload?.message || "Email verified successfully.");
        setDeliveryWarning("");
      } catch (err) {
        if (cancelled) return;
        setStatus("error");
        setMessage(err.message || "Invalid or expired verification link.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleResend = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setResending(true);
    setMessage("");
    try {
      const payload = await resendVerificationEmail(email.trim());
      if (payload?.already_verified) {
        setMessage(payload.message || "This email address is already verified.");
        setDeliveryWarning("");
        return;
      }
      if (payload?.verification_email_sent) {
        setMessage(payload.message || "Verification email sent. Please check your inbox.");
        setDeliveryWarning("");
      } else if (payload?.email_delivery_status === "email_not_configured") {
        setDeliveryWarning(
          payload.message ||
            "Verification email could not be sent because email delivery is not configured. Please contact support.",
        );
      } else if (payload?.email_delivery_status === "send_failed") {
        setDeliveryWarning(
          payload.message || "Verification email could not be sent. Please try again later or contact support.",
        );
      } else {
        setMessage(payload?.message || "If that email is registered and unverified, a new link was sent.");
      }
    } catch (err) {
      setMessage(err.message || "Could not resend verification email.");
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthLayout
      icon={Mail}
      title={status === "verified" ? "Email verified" : "Verify your email"}
      subtitle={
        status === "verified"
          ? "You can now log in and run predictions."
          : "Please verify your email to unlock prediction access."
      }
      footer={
        <Link to="/login" className="text-primary font-medium hover:underline">
          Back to login
        </Link>
      }
    >
      {status === "verifying" && (
        <div className="flex justify-center py-8">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      )}

      {status === "verified" && (
        <div className="text-center space-y-4 py-4">
          <CheckCircle className="w-12 h-12 text-green-400 mx-auto" />
          <p className="text-sm text-muted-foreground">{message}</p>
          <Button className="w-full" onClick={() => navigate("/login", { replace: true })}>
            Continue to login
          </Button>
        </div>
      )}

      {(status === "pending" || status === "error") && (
        <div className="space-y-4">
          {deliveryWarning && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-yellow-500/10 text-yellow-200 text-sm border border-yellow-500/30">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{deliveryWarning}</span>
            </div>
          )}
          {status === "error" && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{message || "Verification link invalid or expired."}</span>
            </div>
          )}
          {status === "pending" && !deliveryWarning && (
            <p className="text-sm text-muted-foreground text-center">
              {message || "Account created. Please check your email to verify your account."}
            </p>
          )}
          <form onSubmit={handleResend} className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="resend-email">Email</Label>
              <Input
                id="resend-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="h-12"
              />
            </div>
            <Button type="submit" className="w-full h-12" disabled={resending}>
              {resending ? "Sending…" : "Resend verification email"}
            </Button>
          </form>
          {message && status === "pending" && !deliveryWarning && (
            <p className="text-xs text-muted-foreground text-center">{message}</p>
          )}
        </div>
      )}
    </AuthLayout>
  );
}
