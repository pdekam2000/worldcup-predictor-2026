import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Lock, AlertTriangle } from "lucide-react";
import AuthLayout from "@/components/AuthLayout";

export default function ResetPassword() {
  return (
    <AuthLayout
      icon={Lock}
      title="Password reset"
      subtitle="Invite-only access"
      footer={
        <Link to="/login" className="text-primary font-medium hover:underline">
          Return to login
        </Link>
      }
    >
      <div className="p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/30 flex gap-3 items-start mb-6">
        <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-muted-foreground">
          Password reset is not available for self-service accounts yet. Access is invite-only —
          contact the administrator for credentials.
        </p>
      </div>
      <Button asChild className="w-full h-12">
        <Link to="/login">Back to login</Link>
      </Button>
    </AuthLayout>
  );
}
