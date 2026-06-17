import React from "react";
import { motion } from "framer-motion";
import { Star } from "lucide-react";

const testimonials = [
  { name: "Marcus W.", role: "Sports Analyst", text: "The multi-agent analysis is unlike anything I've seen. The specialist breakdowns give me insights I can't find anywhere else.", rating: 5 },
  { name: "Sarah K.", role: "Pro Subscriber", text: "I've been using prediction platforms for years. WorldCup Predictor Pro's accuracy and transparency set it apart from the competition.", rating: 5 },
  { name: "David R.", role: "Football Enthusiast", text: "The confidence scores and match reports help me understand the reasoning. It's not just a prediction — it's a complete analysis.", rating: 5 },
  { name: "Elena M.", role: "Elite Subscriber", text: "The accuracy tracking is incredible. Being able to see how the AI performs across different leagues gives me real confidence.", rating: 5 },
  { name: "James T.", role: "Data Scientist", text: "As someone who works with ML models daily, I'm impressed by the depth of analysis. The specialist system is well thought out.", rating: 5 },
  { name: "Lisa H.", role: "Football Blogger", text: "My readers love the match intelligence reports. The quality of the AI analysis adds real value to my content.", rating: 5 },
];

export default function TestimonialsSection() {
  return (
    <section className="py-24 px-4" id="testimonials">
      <div className="max-w-6xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-16">
          <span className="text-primary text-sm font-semibold tracking-widest uppercase">Testimonials</span>
          <h2 className="text-3xl sm:text-4xl font-display font-bold mt-3 mb-4">Trusted by Thousands</h2>
          <p className="text-muted-foreground max-w-xl mx-auto">See what our users say about WorldCup Predictor Pro.</p>
        </motion.div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {testimonials.map((t, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="glass rounded-2xl p-6"
            >
              <div className="flex gap-1 mb-4">
                {Array.from({ length: t.rating }).map((_, si) => (
                  <Star key={si} className="w-4 h-4 fill-accent text-accent" />
                ))}
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed mb-4">"{t.text}"</p>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-blue-600 flex items-center justify-center text-sm font-bold text-white">
                  {t.name.charAt(0)}
                </div>
                <div>
                  <div className="text-sm font-semibold">{t.name}</div>
                  <div className="text-xs text-muted-foreground">{t.role}</div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}