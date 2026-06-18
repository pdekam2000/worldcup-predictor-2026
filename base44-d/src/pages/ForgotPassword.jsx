import React, { useState } from "react";
import { Link } from "react-router-dom";
import { requestPasswordReset } from "@/api/authApi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Mail, ArrowLeft, Loader2 } from "lucide-react";
import AuthLayout from "@/components/AuthLayout";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const result = await requestPasswordReset();
      setMessage(result?.message || "If your account exists, instructions have been sent.");
      void email;
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      icon={Mail}
      title="Forgot password"
      subtitle="We'll help you get back in"
      footer={
        <Link to="/login" className="inline-flex items-center text-sm text-primary hover:underline">
          <ArrowLeft className="w-4 h-4 mr-1" />
          Back to login
        </Link>
      }
    >
      {message && (
        <div className="mb-4 p-3 rounded-lg bg-primary/10 text-primary text-sm">{message}</div>
      )}
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">{error}</div>
      )}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-12"
          />
        </div>
        <Button type="submit" className="w-full h-12" disabled={loading}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send reset link"}
        </Button>
      </form>
    </AuthLayout>
  );
}
