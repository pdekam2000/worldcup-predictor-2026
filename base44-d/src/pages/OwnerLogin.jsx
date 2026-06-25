import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import PasswordInput from "@/components/auth/PasswordInput";
import { Shield, Mail, Loader2, Lock } from "lucide-react";
import AuthLayout from "@/components/AuthLayout";
import { isOwnerUser } from "@/lib/roles";

/**
 * Hidden owner / super_admin access — not linked from public navigation.
 */
export default function OwnerLogin() {
  const { login, logout } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const payload = await login(email.trim(), password);
      const user = payload?.user;
      if (!isOwnerUser(user)) {
        await logout(false);
        setError("Invalid email or password");
        return;
      }
      navigate("/owner", { replace: true });
    } catch {
      setError("Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      icon={Shield}
      title="System Access"
      subtitle="Authorized operators only"
      footer={
        <Link to="/login" className="text-[#94A3B8] hover:text-[#F8FAFC] text-sm">
          Return to standard login
        </Link>
      }
    >
      <p className="text-center text-xs text-[#94A3B8] mb-6">
        This route is not indexed. Access is restricted to verified system operators.
      </p>

      {error && (
        <div className="mb-4 p-3 rounded-xl border border-red-500/30 bg-red-500/10 text-red-200 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="owner-email">Email</Label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              id="owner-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="pl-10 h-12 bg-[#070B14]/50 border-white/10"
              required
            />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="owner-password">Password</Label>
          <PasswordInput
            id="owner-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            leftIcon={Lock}
            label="Password"
          />
        </div>
        <Button type="submit" className="w-full h-12 font-semibold bg-gradient-to-r from-[#00E676] to-[#3B82F6] text-[#070B14]" disabled={loading}>
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Verifying…
            </>
          ) : (
            "Access Command Center"
          )}
        </Button>
      </form>
    </AuthLayout>
  );
}
