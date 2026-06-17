import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Shield } from "lucide-react";

export default function PrivacyPolicy() {
  return (
    <div className="min-h-screen bg-background px-4 py-12">
      <div className="max-w-3xl mx-auto">
        <Link to="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground mb-8 text-sm">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center">
            <Shield className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-display font-bold">Privacy Policy</h1>
            <p className="text-xs text-muted-foreground">Last updated: June 2026 | GDPR compliant</p>
          </div>
        </div>
        <div className="glass rounded-2xl p-8 space-y-6 text-sm text-muted-foreground leading-relaxed">
          <section>
            <h2 className="text-foreground font-semibold mb-2">1. Data Controller</h2>
            <p>WorldCup Predictor Pro is operated by Pedram Kamangar. For any privacy-related queries, contact: privacy@wcppredictor.com</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">2. Data We Collect</h2>
            <p>We collect: email address and full name (upon registration), prediction usage data, subscription and billing information, device and browser information for analytics. We do NOT sell your personal data to third parties.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">3. Purpose of Processing</h2>
            <p>Your data is used to provide and improve the service, manage your account and subscription, send transactional emails and alerts you have opted into, and comply with legal obligations under GDPR.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">4. Legal Basis (GDPR Art. 6)</h2>
            <p>Processing is based on: contract performance (Art. 6(1)(b)), legitimate interest (analytics), and your explicit consent (marketing emails, cookies).</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">5. Cookies</h2>
            <p>We use essential cookies for authentication and optional analytics cookies. You can withdraw consent at any time via the cookie banner or your browser settings.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">6. Data Retention</h2>
            <p>Account data is retained for the duration of your account plus 2 years after deletion for legal compliance. You may request deletion at any time.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">7. Your Rights (GDPR)</h2>
            <p>You have the right to: access, rectify, erase, restrict, port, and object to processing of your personal data. Contact us to exercise these rights.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">8. Third-Party Services</h2>
            <p>We use Stripe for payment processing (their privacy policy applies) and may use Google Analytics. No personal data is shared with prediction API providers.</p>
          </section>
        </div>
      </div>
    </div>
  );
}