import React from "react";
import { Link } from "react-router-dom";
import { XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import AuthLayout from "@/components/AuthLayout";

export default function BillingCheckoutCancel() {
  return (
    <AuthLayout
      icon={XCircle}
      title="Checkout cancelled"
      subtitle="No charges were made"
      footer={
        <Link to="/subscription" className="text-primary font-medium hover:underline">
          Back to subscription
        </Link>
      }
    >
      <p className="text-sm text-muted-foreground mb-6">Checkout cancelled. You can try again anytime from your subscription page.</p>
      <Button asChild className="w-full h-12">
        <Link to="/subscription">Return to subscription</Link>
      </Button>
    </AuthLayout>
  );
}
