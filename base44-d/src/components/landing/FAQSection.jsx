import React from "react";
import { motion } from "framer-motion";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

const faqs = [
  { q: "How does the AI prediction system work?", a: "Our platform uses 10 specialized AI agents that each analyze a different dimension of every match — form, injuries, lineups, weather, tactics, referee tendencies, and more. The results are combined into a unified prediction with confidence scores." },
  { q: "What is the accuracy rate?", a: "Our historical accuracy rate is approximately 73% for 1X2 predictions. We track accuracy transparently across all leagues and time periods in our Accuracy Center." },
  { q: "Can I use this for betting?", a: "Our platform provides analytical predictions for informational purposes. How you use the information is your responsibility. We recommend responsible decision-making." },
  { q: "Which leagues are covered?", a: "We cover major leagues worldwide including the Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, and many more. Coverage is continuously expanding." },
  { q: "What's the difference between Free and Pro?", a: "Free users get 5 predictions per day with basic match information. Pro users get unlimited predictions, over/under markets, specialist analysis breakdowns, and match intelligence reports." },
  { q: "How often are predictions updated?", a: "Predictions are generated and updated daily as new data becomes available. Factors like lineup confirmations and injury news can trigger re-analysis." },
  { q: "Can I cancel my subscription anytime?", a: "Yes, you can cancel at any time from your account settings. You'll retain access until the end of your current billing period." },
];

export default function FAQSection() {
  return (
    <section className="py-24 px-4" id="faq">
      <div className="max-w-3xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-16">
          <span className="text-primary text-sm font-semibold tracking-widest uppercase">FAQ</span>
          <h2 className="text-3xl sm:text-4xl font-display font-bold mt-3 mb-4">Frequently Asked Questions</h2>
        </motion.div>
        <Accordion type="single" collapsible className="space-y-3">
          {faqs.map((faq, i) => (
            <AccordionItem key={i} value={`item-${i}`} className="glass rounded-xl px-6 border-white/10">
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