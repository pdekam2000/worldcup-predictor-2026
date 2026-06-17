import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Building } from "lucide-react";

export default function ImprintPage() {
  return (
    <div className="min-h-screen bg-background px-4 py-12">
      <div className="max-w-2xl mx-auto">
        <Link to="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground mb-8 text-sm">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center">
            <Building className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-display font-bold">Impressum / Imprint</h1>
            <p className="text-xs text-muted-foreground">Legal disclosure pursuant to § 5 TMG (Germany) / § 25 MedienG (Austria)</p>
          </div>
        </div>
        <div className="glass rounded-2xl p-8 space-y-5 text-sm text-muted-foreground leading-relaxed">
          <section>
            <h2 className="text-foreground font-semibold mb-2">Operator / Betreiber</h2>
            <p className="font-medium text-foreground">Pedram Kamangar</p>
            <p>WorldCup Predictor Pro</p>
            <p>Vienna, Austria</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">Contact / Kontakt</h2>
            <p>Email: contact@wcppredictor.com</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">VAT / USt-ID</h2>
            <p>VAT number will be displayed here once registered with Austrian tax authorities (Finanzamt).</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">Responsible for Content (§ 55 Abs. 2 RStV)</h2>
            <p>Pedram Kamangar (address as above)</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">Dispute Resolution / Streitschlichtung</h2>
            <p>The European Commission provides a platform for online dispute resolution (OS): <a href="https://ec.europa.eu/consumers/odr" target="_blank" rel="noopener" className="text-primary underline">https://ec.europa.eu/consumers/odr</a></p>
            <p className="mt-2">We are not obliged nor willing to participate in dispute settlement proceedings before a consumer arbitration board.</p>
          </section>
          <section>
            <h2 className="text-foreground font-semibold mb-2">Liability Notice / Haftungshinweis</h2>
            <p>Despite careful content control, we assume no liability for the content of external links. The operators of the linked pages are solely responsible for their content.</p>
          </section>
        </div>
      </div>
    </div>
  );
}