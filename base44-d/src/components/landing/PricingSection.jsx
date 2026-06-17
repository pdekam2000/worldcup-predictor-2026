import React, { useState } from "react";
import { motion } from "framer-motion";
import { Check, Crown, Zap, User, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

const langs = {
  en: {
    title: "Choose Your Plan",
    subtitle: "Start free and upgrade as you grow. All plans include our core AI prediction engine.",
    monthly: "Monthly",
    yearly: "Yearly",
    save: "Save 20%",
    popular: "Most Popular",
    disclaimer: "⚠️ For Entertainment Purposes Only",
    disclaimerText: "WorldCup Predictor Pro is intended strictly for entertainment and informational purposes. We are not responsible for any financial decisions, betting, or gambling activity made based on our predictions. Please gamble responsibly.",
  },
  de: {
    title: "Wählen Sie Ihren Plan",
    subtitle: "Starten Sie kostenlos und wachsen Sie. Alle Pläne beinhalten unsere KI-Vorhersagemaschine.",
    monthly: "Monatlich",
    yearly: "Jährlich",
    save: "20% sparen",
    popular: "Beliebteste",
    disclaimer: "⚠️ Nur zu Unterhaltungszwecken",
    disclaimerText: "WorldCup Predictor Pro dient ausschließlich der Unterhaltung und Information. Wir übernehmen keine Verantwortung für finanzielle Entscheidungen, Wetten oder Glücksspiel auf Basis unserer Vorhersagen. Bitte spielen Sie verantwortungsbewusst.",
  },
  fa: {
    title: "پلن خود را انتخاب کنید",
    subtitle: "رایگان شروع کنید و هر زمان ارتقا دهید. تمام پلن‌ها شامل موتور پیش‌بینی هوش مصنوعی ما هستند.",
    monthly: "ماهانه",
    yearly: "سالانه",
    save: "۲۰٪ صرفه‌جویی",
    popular: "محبوب‌ترین",
    disclaimer: "⚠️ صرفاً برای سرگرمی",
    disclaimerText: "WorldCup Predictor Pro صرفاً برای سرگرمی و اطلاع‌رسانی طراحی شده است. ما هیچ‌گونه مسئولیتی در قبال تصمیمات مالی، شرط‌بندی یا قمار بر اساس پیش‌بینی‌های این برنامه نداریم. لطفاً مسئولانه رفتار کنید.",
  },
};

const plans = [
  {
    nameKey: "Free",
    icon: User,
    monthly: 0,
    yearly: 0,
    predictions: 1,
    desc: { en: "Get started with 1 free prediction", de: "Starten Sie mit 1 kostenlosen Vorhersage", fa: "با ۱ پیش‌بینی رایگان شروع کنید" },
    features: {
      en: ["1 prediction per day", "1X2 predictions", "Basic match info", "Community access"],
      de: ["1 Vorhersage pro Tag", "1X2-Vorhersagen", "Grundlegende Spielinfos", "Community-Zugang"],
      fa: ["۱ پیش‌بینی در روز", "پیش‌بینی ۱X2", "اطلاعات پایه بازی", "دسترسی به جامعه"],
    },
    cta: { en: "Get Started", de: "Jetzt starten", fa: "شروع کنید" },
    popular: false,
    color: "border-white/10",
  },
  {
    nameKey: "Pro",
    icon: Zap,
    monthly: 5,
    yearly: 50,
    predictions: 3,
    desc: { en: "3 predictions per day — great value", de: "3 Vorhersagen pro Tag — großer Wert", fa: "۳ پیش‌بینی در روز — ارزش عالی" },
    features: {
      en: ["3 predictions per day", "Over/Under & BTTS", "Confidence scores", "Match reports", "Specialist analysis", "Email alerts"],
      de: ["3 Vorhersagen pro Tag", "Über/Unter & BTTS", "Konfidenzwerte", "Spielberichte", "Spezialistenanalyse", "E-Mail-Benachrichtigungen"],
      fa: ["۳ پیش‌بینی در روز", "بیش/کمتر از ۲.۵ گل و BTTS", "امتیاز اطمینان", "گزارش بازی", "تحلیل متخصص", "اعلان ایمیل"],
    },
    cta: { en: "Upgrade to Pro", de: "Auf Pro upgraden", fa: "ارتقا به Pro" },
    popular: false,
    color: "border-white/10",
  },
  {
    nameKey: "Elite",
    icon: Crown,
    monthly: 19,
    yearly: 190,
    predictions: 10,
    desc: { en: "10 predictions per day — serious analyst", de: "10 Vorhersagen pro Tag — ernsthafter Analyst", fa: "۱۰ پیش‌بینی در روز — تحلیلگر جدی" },
    features: {
      en: ["10 predictions per day", "Everything in Pro", "Premium analytics", "Historical data", "League performance", "Priority support"],
      de: ["10 Vorhersagen pro Tag", "Alles in Pro", "Premium-Analytik", "Historische Daten", "Liga-Performance", "Prioritätssupport"],
      fa: ["۱۰ پیش‌بینی در روز", "همه امکانات Pro", "تحلیل پیشرفته", "داده‌های تاریخی", "عملکرد لیگ", "پشتیبانی ویژه"],
    },
    cta: { en: "Go Elite", de: "Zu Elite wechseln", fa: "انتخاب Elite" },
    popular: true,
    color: "border-primary",
  },
  {
    nameKey: "Unlimited",
    icon: Crown,
    monthly: 85,
    yearly: 850,
    predictions: Infinity,
    desc: { en: "Unlimited predictions — full power", de: "Unbegrenzte Vorhersagen — volle Kraft", fa: "پیش‌بینی نامحدود — قدرت کامل" },
    features: {
      en: ["Unlimited predictions", "All Elite features", "API access", "Early predictions", "Dedicated support", "White-label reports"],
      de: ["Unbegrenzte Vorhersagen", "Alle Elite-Funktionen", "API-Zugang", "Frühzeitige Vorhersagen", "Dedizierter Support", "White-Label-Berichte"],
      fa: ["پیش‌بینی نامحدود", "تمام امکانات Elite", "دسترسی API", "پیش‌بینی زودهنگام", "پشتیبانی اختصاصی", "گزارش‌های سفارشی"],
    },
    cta: { en: "Go Unlimited", de: "Unbegrenzt wählen", fa: "انتخاب نامحدود" },
    popular: false,
    color: "border-accent",
  },
];

export default function PricingSection() {
  const [yearly, setYearly] = useState(false);
  const [lang, setLang] = useState("en");
  const t = langs[lang];

  return (
    <section className="py-24 px-4" id="pricing">
      <div className="max-w-6xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-12">
          <div className="flex justify-center gap-2 mb-6">
            {["en", "de", "fa"].map(l => (
              <button key={l} onClick={() => setLang(l)} className={`px-3 py-1 rounded-full text-xs font-semibold border transition-all ${lang === l ? "bg-primary text-primary-foreground border-primary" : "border-white/10 text-muted-foreground hover:text-foreground"}`}>
                {l === "en" ? "🇬🇧 EN" : l === "de" ? "🇩🇪 DE" : "🇮🇷 FA"}
              </button>
            ))}
          </div>
          <span className="text-primary text-sm font-semibold tracking-widest uppercase">Pricing</span>
          <h2 className="text-3xl sm:text-4xl font-display font-bold mt-3 mb-4">{t.title}</h2>
          <p className="text-muted-foreground max-w-xl mx-auto mb-8">{t.subtitle}</p>

          <div className="inline-flex items-center glass rounded-full p-1">
            <button onClick={() => setYearly(false)} className={`px-6 py-2 rounded-full text-sm font-medium transition-all ${!yearly ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {t.monthly}
            </button>
            <button onClick={() => setYearly(true)} className={`px-6 py-2 rounded-full text-sm font-medium transition-all ${yearly ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {t.yearly} <span className="text-green-400 text-xs ml-1">{t.save}</span>
            </button>
          </div>
        </motion.div>

        <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-5">
          {plans.map((plan, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
              className={`relative glass rounded-2xl p-6 border ${plan.color} ${plan.popular ? "glow-blue" : ""}`}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-primary text-primary-foreground text-xs font-semibold rounded-full whitespace-nowrap">
                  {t.popular}
                </div>
              )}
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${plan.popular ? "bg-primary/20" : plan.nameKey === "Unlimited" ? "bg-yellow-500/10" : "bg-white/5"}`}>
                  <plan.icon className={`w-4 h-4 ${plan.popular ? "text-primary" : plan.nameKey === "Unlimited" ? "text-accent" : "text-muted-foreground"}`} />
                </div>
                <h3 className="text-lg font-display font-bold">{plan.nameKey}</h3>
              </div>
              <p className="text-xs text-muted-foreground mb-4">{plan.desc[lang]}</p>
              <div className="mb-5">
                <span className="text-3xl font-display font-bold">€{yearly ? plan.yearly : plan.monthly}</span>
                {plan.monthly > 0 && <span className="text-muted-foreground text-xs">/{yearly ? "yr" : "mo"}</span>}
              </div>
              <Link to="/register">
                <Button className={`w-full rounded-xl font-semibold text-sm ${plan.popular ? "glow-blue" : plan.nameKey === "Unlimited" ? "bg-accent text-accent-foreground hover:bg-accent/90 glow-gold" : "bg-white/5 hover:bg-white/10 text-foreground border border-white/10"}`}>
                  {plan.cta[lang]}
                </Button>
              </Link>
              <ul className="mt-5 space-y-2.5">
                {plan.features[lang].map((f, fi) => (
                  <li key={fi} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Check className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>

        {/* Disclaimer */}
        <motion.div initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="mt-10 glass rounded-2xl p-5 border border-yellow-500/30 flex gap-4 items-start" dir={lang === "fa" ? "rtl" : "ltr"}>
          <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-yellow-400 font-semibold text-sm mb-1">{t.disclaimer}</p>
            <p className="text-muted-foreground text-xs leading-relaxed">{t.disclaimerText}</p>
          </div>
        </motion.div>
      </div>
    </section>
  );
}