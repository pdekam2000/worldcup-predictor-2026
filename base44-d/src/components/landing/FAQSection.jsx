import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

const faqs = [
  {
    q: "What is Best Bet Winrate?",
    a: "Winrate calculated only from public Best Bets — evaluated program picks after matches finish. It excludes research-only probabilities, partial markets, and fixtures where the model flagged no_bet.",
  },
  {
    q: "What does No Bet Recommended mean?",
    a: "No Bet Recommended means model found no strong edge on that fixture. You can still review market probabilities for research, but nothing is promoted as a program best bet.",
  },
  {
    q: "How does the prediction system work?",
    a: "Each fixture is analyzed across multiple markets (1X2, over/under, BTTS, and more). The engine produces confidence tiers and flags program best bets separately from research-only probabilities.",
  },
  {
    q: "What accuracy should I expect?",
    a: "We publish evaluated best-bet winrate on the Public Accuracy page — not marketing guesses. Sample size grows as World Cup fixtures finish. Past performance does not guarantee future results.",
  },
  {
    q: "Why do I need an invite code?",
    a: "We are in a controlled soft launch. Request an invite via the Contact page if you do not have a code yet.",
  },
  {
    q: "Can I use this for betting?",
    a: "Predictions are for informational and entertainment purposes only. You are responsible for any financial or gambling decisions.",
  },
  {
    q: "What's the difference between Free and Pro?",
    a: "Free includes a monthly prediction quota and core markets. Starter and Pro increase limits and unlock advanced views. See Pricing for the full comparison.",
  },
  {
    q: "How do I upgrade or get billing help?",
    a: "Open Subscription after login. Stripe checkout is available when configured; otherwise use Message Admin on that page or Contact support.",
  },
  {
    q: "What do confidence and tier mean?",
    a: "Probability is the model's estimated chance of an outcome. Confidence reflects model trust in the recommendation. Tier (A–D) indicates recommendation strength — best bets are filtered separately in Results and Archive.",
  },
];

export default function FAQSection() {
  return (
    <section className="py-24 px-4" id="faq">
      <div className="max-w-3xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-16">
          <span className="text-primary text-sm font-semibold tracking-widest uppercase">FAQ</span>
          <h2 className="text-3xl sm:text-4xl font-display font-bold mt-3 mb-4">Frequently Asked Questions</h2>
          <p className="text-sm text-muted-foreground">
            Still stuck?{" "}
            <Link to="/contact" className="text-primary hover:underline">Contact support</Link>
            {" "}or read the{" "}
            <Link to="/public/accuracy" className="text-primary hover:underline">public accuracy archive</Link>.
          </p>
        </motion.div>
        <Accordion type="single" collapsible className="space-y-3">
          {faqs.map((faq, i) => (
            <AccordionItem key={i} value={`item-${i}`} className="wc-premium-card px-6 border-amber-200/60">
              <AccordionTrigger className="text-left font-medium py-5 hover:no-underline">
                {faq.q}
              </AccordionTrigger>
              <AccordionContent className="text-muted-foreground pb-5 leading-relaxed">
                {faq.a}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </section>
  );
}
