import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Mail, Send, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { trackEvent } from "@/lib/analytics";

const SUPPORT_EMAIL = "contact@wcppredictor.com";

export default function ContactPage() {
  const [sent, setSent] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });

  const handleSubmit = (e) => {
    e.preventDefault();
    const body = `Name: ${form.name}\nEmail: ${form.email}\n\n${form.message}`;
    const mailto = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(form.subject || "WorldCup Predictor support")}&body=${encodeURIComponent(body)}`;
    trackEvent("support_contact_submit", { channel: "mailto" });
    window.location.href = mailto;
    setSent(true);
  };

  return (
    <div className="min-h-screen bg-background px-4 py-12">
      <div className="max-w-2xl mx-auto">
        <Link to="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground mb-8 text-sm">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center">
            <Mail className="w-5 h-5 text-primary" />
          </div>
          <h1 className="text-2xl font-display font-bold">Contact & Support</h1>
        </div>
        <p className="text-sm text-muted-foreground mb-8">
          Soft launch is invite-only. Need an invite code, billing help, or account access? We respond within 24–48 hours.
        </p>
        {sent ? (
          <div className="glass rounded-2xl p-8 text-center">
            <div className="text-4xl mb-4">✉️</div>
            <h2 className="font-display font-bold text-lg mb-2">Open your email app</h2>
            <p className="text-muted-foreground text-sm mb-4">
              Your message is ready to send to {SUPPORT_EMAIL}. If nothing opened, use the button below.
            </p>
            <Button asChild variant="outline" className="rounded-xl">
              <a href={`mailto:${SUPPORT_EMAIL}`}>
                <ExternalLink className="w-4 h-4 mr-2" />
                Email {SUPPORT_EMAIL}
              </a>
            </Button>
            <p className="text-xs text-muted-foreground mt-4">
              Logged-in users can also message admin from{" "}
              <Link to="/subscription" className="text-primary hover:underline">Subscription</Link>.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="glass rounded-2xl p-8 space-y-4">
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted-foreground mb-1.5 block">Name</label>
                <Input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} placeholder="Your name" className="bg-white/5 border-white/10 rounded-lg" required />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1.5 block">Email</label>
                <Input type="email" value={form.email} onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))} placeholder="you@example.com" className="bg-white/5 border-white/10 rounded-lg" required />
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block">Subject</label>
              <Input value={form.subject} onChange={(e) => setForm((p) => ({ ...p, subject: e.target.value }))} placeholder="Invite code, billing, or technical issue" className="bg-white/5 border-white/10 rounded-lg" required />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block">Message</label>
              <textarea value={form.message} onChange={(e) => setForm((p) => ({ ...p, message: e.target.value }))} placeholder="How can we help?" rows={5} className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none" required />
            </div>
            <Button type="submit" className="w-full rounded-xl">
              <Send className="w-4 h-4 mr-2" /> Continue in email app
            </Button>
            <p className="text-xs text-muted-foreground text-center">
              Or email directly:{" "}
              <a href={`mailto:${SUPPORT_EMAIL}`} className="text-primary hover:underline">{SUPPORT_EMAIL}</a>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
