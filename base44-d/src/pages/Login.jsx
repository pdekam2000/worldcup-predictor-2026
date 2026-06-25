import React, { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import { fetchAuthConfig, resendVerificationEmail } from "@/api/authApi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import PasswordInput from "@/components/auth/PasswordInput";
import AuthLayout from "@/components/AuthLayout";
import { LogIn, Mail, Loader2, Lock } from "lucide-react";
import { postLoginPath } from "@/lib/roles";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [infoMessage, setInfoMessage] = useState(location.state?.message || "");
  const [verifyNotice, setVerifyNotice] = useState("");
  const [verificationRequired, setVerificationRequired] = useState(true);
  const [resending, setResending] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchAuthConfig()
      .then((config) => setVerificationRequired(config?.email_verification_required !== false))
      .catch(() => setVerificationRequired(true));
  }, []);

  useEffect(() => {
    if (location.state?.message) {
      setInfoMessage(location.state.message);
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location.pathname, location.state, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setVerifyNotice("");
    setLoading(true);
    try {
      const payload = await login(email, password);
      if (
        verificationRequired &&
        (payload?.verification_required || payload?.user?.email_verified === false)
      ) {
        setVerifyNotice(payload?.message || "Please verify your email before logging in.");
        navigate(`/verify-email?email=${encodeURIComponent(email)}`, {
          replace: true,
          state: { registrationMessage: payload?.message },
        });
        return;
      }
      navigate(postLoginPath(payload?.user), { replace: true });
    } catch (err) {
      if (err.code === "banned") {
        setError("Account has been banned.");
      } else {
        setError(err.message || "Invalid email or password");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResendVerification = async () => {
    if (!email.trim()) {
      setError("Enter your email address first.");
      return;
    }
    setResending(true);
    setError("");
    try {
      const payload = await resendVerificationEmail(email.trim());
      setInfoMessage(payload?.message || "If that email is registered and unverified, a new link was sent.");
    } catch (err) {
      setError(err.message || "Could not resend verification email.");
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthLayout
      icon={LogIn}
      title="Welcome back"
      subtitle="Log in to your account"
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link to="/register" className="text-primary font-medium hover:underline">
            Create one
          </Link>
        </>
      }
    >
      <p className="text-center text-xs text-muted-foreground mb-6">
        Google login coming soon.
      </p>

      {infoMessage && (
        <div className="mb-4 p-3 rounded-lg bg-primary/10 text-primary text-sm">
          {infoMessage}
        </div>
      )}

      {verifyNotice && (
        <div className="mb-4 p-3 rounded-lg bg-yellow-500/10 text-yellow-200 text-sm border border-yellow-500/30">
          {verifyNotice}
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input
              id="email"
              type="email"
              autoComplete="email"
              autoFocus
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="pl-10 h-12"
              required
            />
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link to="/forgot-password" className="text-xs text-primary hover:underline">
              Forgot password?
            </Link>
          </div>
          <PasswordInput
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            leftIcon={Lock}
            label="Password"
          />
        </div>
        <Button type="submit" className="w-full h-12 font-medium" disabled={loading}>
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Logging in...
            </>
          ) : (
            "Log in"
          )}
        </Button>
      </form>

      {verificationRequired && (
        <div className="mt-4 text-center">
          <Button
            type="button"
            variant="link"
            className="text-xs text-primary"
            disabled={resending}
            onClick={handleResendVerification}
          >
            {resending ? "Sending verification email…" : "Resend verification email"}
          </Button>
        </div>
      )}
    </AuthLayout>
  );
}
