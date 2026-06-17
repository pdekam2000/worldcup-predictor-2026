import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Mail, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ContactPage() {
  const [sent, setSent] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });

  const handleSubmit = (e) => {
    e.preventDefault();
    setSent(true);
  };

  return (
    <div className="min-h-screen bg-background px-4 py-12">
      <div className="max-w-2xl mx-auto">
        <Link to="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground mb-8 text-sm">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center">
            <Mail className="w-5 h-5 text-primary" />
          </div>
          <h1 className="text-2xl font-display font-bold">Contact Us</h1>
        </div>
        {sent ? (
          <div className="glass rounded-2xl p-8 text-center">
            <div className="text-4xl mb-4">✅</div>
            <h2 className="font-display font-bold text-lg mb-2">Message Sent!</h2>
            <p className="text-muted-foreground text-sm">We'll get back to you within 24-48 hours.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="glass rounded-2xl p-8 space-y-4">
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted-foreground mb-1.5 block">Name</label>
                <Input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="Your name" className="bg-white/5 border-white/10 rounded-lg" required />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1.5 block">Email</label>
                <Input type="email" value={form.email} onChange={e => setForm(p => ({ ...p, email: e.target.value }))} placeholder="you@example.com" className="bg-white/5 border-white/10 rounded-lg" required />
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block">Subject</label>
              <Input value={form.subject} onChange={e => setForm(p => ({ ...p, subject: e.target.value }))} placeholder="What's this about?" className="bg-white/5 border-white/10 rounded-lg" required />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1.5 block">Message</label>
              <textarea value={form.message} onChange={e => setForm(p => ({ ...p, message: e.target.value }))} placeholder="Your message..." rows={5} className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none" required />
            </div>
            <Button type="submit" className="w-full rounded-xl">
              <Send className="w-4 h-4 mr-2" /> Send Message
            </Button>
            <p className="text-xs text-muted-foreground text-center">Or email directly: <span className="text-primary">contact@wcppredictor.com</span></p>
          </form>
        )}
      </div>
    </div>
  );
}