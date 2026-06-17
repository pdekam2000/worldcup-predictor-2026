import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, FileText } from "lucide-react";

export default function TermsOfService() {
  return (
    <div className="min-h-screen bg-background px-4 py-12">
      <div className="max-w-3xl mx-auto">
        <Link to="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground mb-8 text-sm">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center">
            <FileText className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-display font-bold">Terms of Service</h1>
            <p className="text-xs text-muted-foreground">Last updated: June 2026</p>
          </div>
        </div>
        <div className="glass rounded-2xl p-8 space-y-6 text-sm text-muted-foreground leading-relaxed">
          <section>
            <h2 className="text-foreground font-semibold mb-2">1. Acceptance</h2>
            <p>By accessing WorldCup Predictor Pro, you agree to these Terms of Service. If you do not agree, please do not use the service.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">2. Entertainment Purpose Only</h2>
            <p className="text-yellow-400/80 font-medium">⚠️ This platform provides AI-generated football predictions for informational and entertainment purposes ONLY. It does NOT constitute guaranteed betting advice. We are NOT responsible for any financial losses, betting decisions, or gambling activities made based on our predictions.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">3. Eligibility</h2>
            <p>You must be at least 18 years old to use this service. Users are responsible for complying with their local laws regarding online services and gambling regulations.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">4. Subscriptions & Billing</h2>
            <p>Subscription fees are charged in advance. Refunds are at our discretion. You may cancel anytime; your plan remains active until the end of the billing period.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">5. Intellectual Property</h2>
            <p>All prediction data, reports, and content are owned by WorldCup Predictor Pro. You may not reproduce or distribute content without written permission.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">6. Limitation of Liability</h2>
            <p>To the fullest extent permitted by law, WorldCup Predictor Pro and Pedram Kamangar shall not be liable for any indirect, incidental, or consequential damages arising from use of the service.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">7. Governing Law</h2>
            <p>These terms are governed by Austrian law. Disputes shall be resolved in the courts of Vienna, Austria.</p>
          </section>
        </div>
      </div>
    </div>
  );
}