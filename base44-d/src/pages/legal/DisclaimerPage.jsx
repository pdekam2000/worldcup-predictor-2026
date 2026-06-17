import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, AlertTriangle } from "lucide-react";

export default function DisclaimerPage() {
  return (
    <div className="min-h-screen bg-background px-4 py-12">
      <div className="max-w-3xl mx-auto">
        <Link to="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground mb-8 text-sm">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-yellow-500/20 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-yellow-400" />
          </div>
          <div>
            <h1 className="text-2xl font-display font-bold">Betting Disclaimer</h1>
            <p className="text-xs text-muted-foreground">Please read carefully before using predictions</p>
          </div>
        </div>
        <div className="glass rounded-2xl p-8 space-y-6 text-sm text-muted-foreground leading-relaxed border border-yellow-500/20">
          <div className="p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/30 text-yellow-300 font-medium text-base">
            ⚠️ FOR INFORMATIONAL AND ENTERTAINMENT PURPOSES ONLY
          </div>
          <section>
            <h2 className="text-foreground font-semibold mb-2">No Guaranteed Betting Advice</h2>
            <p>WorldCup Predictor Pro provides AI-generated statistical analysis and predictions. These predictions do NOT constitute guaranteed betting advice, tips, or recommendations to place bets.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">No Financial Responsibility</h2>
            <p>We are NOT responsible for any financial decisions, monetary losses, gambling debts, or any other consequences that may arise from using our predictions. All financial decisions are made entirely at your own risk.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">Responsible Gambling</h2>
            <p>If you choose to participate in sports betting, please do so responsibly. Set limits, gamble only with money you can afford to lose, and seek help if gambling becomes a problem.</p>
            <p className="mt-2">Resources: <a href="https://www.begambleaware.org" target="_blank" rel="noopener" className="text-primary underline">BeGambleAware.org</a> | <a href="https://www.gamblingtherapy.org" target="_blank" rel="noopener" className="text-primary underline">GamblingTherapy.org</a></p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">Age Restriction</h2>
            <p>This service is strictly for users 18 years of age and older. By using this platform, you confirm you are of legal age in your jurisdiction.</p>
          </section>
          <div className="grid md:grid-cols-3 gap-3 pt-2">
            <div className="p-3 rounded-xl bg-white/5 text-center text-xs"><span className="block text-lg">🇩🇪</span>Nur zur Unterhaltung. Keine Wettberatung.</div>
            <div className="p-3 rounded-xl bg-white/5 text-center text-xs"><span className="block text-lg">🇮🇷</span>صرفاً برای سرگرمی. مسئولیت شرط‌بندی با ما نیست.</div>
            <div className="p-3 rounded-xl bg-white/5 text-center text-xs"><span className="block text-lg">🇸🇦</span>للترفيه فقط. لسنا مسؤولين عن قرارات المراهنة.</div>
          </div>
        </div>
      </div>
    </div>
  );
}