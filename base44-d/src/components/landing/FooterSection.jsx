import React from "react";
import { Link } from "react-router-dom";
import { Zap, AlertTriangle } from "lucide-react";

export default function FooterSection() {
  return (
    <footer className="border-t border-white/10 py-12 px-4">
      <div className="max-w-6xl mx-auto space-y-8">

        {/* Disclaimer box */}
        <div className="glass rounded-2xl p-5 border border-yellow-500/30 flex gap-4 items-start">
          <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-yellow-400 font-semibold text-sm mb-1">⚠️ For Entertainment Purposes Only / Nur zur Unterhaltung / صرفاً برای سرگرمی</p>
            <p className="text-muted-foreground text-xs leading-relaxed">
              <span className="block mb-1"><strong className="text-foreground/70">EN:</strong> This platform is for entertainment and informational purposes only. We are not responsible for any financial decisions, betting, or gambling made based on our predictions. Please gamble responsibly.</span>
              <span className="block mb-1"><strong className="text-foreground/70">DE:</strong> Diese Plattform dient ausschließlich der Unterhaltung. Wir übernehmen keine Verantwortung für finanzielle Entscheidungen oder Glücksspiel auf Basis unserer Vorhersagen.</span>
              <span className="block" dir="rtl"><strong className="text-foreground/70">FA:</strong> این برنامه صرفاً برای سرگرمی است. ما هیچ مسئولیتی در قبال هرگونه هزینه‌کردن، شرط‌بندی یا قمار بر اساس پیش‌بینی‌های این برنامه نداریم.</span>
            </p>
          </div>
        </div>

        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
              <Zap className="w-4 h-4 text-primary-foreground" />
            </div>
            <span className="font-display font-bold text-lg">WorldCup Predictor Pro</span>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
            <Link to="/terms" className="hover:text-foreground transition-colors">Terms</Link>
            <Link to="/privacy" className="hover:text-foreground transition-colors">Privacy</Link>
            <Link to="/disclaimer" className="hover:text-foreground transition-colors">Disclaimer</Link>
            <Link to="/contact" className="hover:text-foreground transition-colors">Contact</Link>
            <Link to="/imprint" className="hover:text-foreground transition-colors">Imprint</Link>
          </div>
          <div className="text-sm text-muted-foreground text-center md:text-right space-y-1">
            <div>© 2026 WorldCup Predictor Pro. All rights reserved.</div>
            <div className="text-xs text-muted-foreground/60">Owner & Developer: <span className="text-foreground/70 font-medium">Pedram Kamangar</span></div>
          </div>
        </div>
      </div>
    </footer>
  );
}