import React from "react";
import PricingContent from "@/components/pricing/PricingContent";

/** Landing page pricing section — Phase 39A */
export default function PricingSection() {
  return (
    <section className="py-24 px-4" id="pricing">
      <PricingContent showHeader ctaBase="/register" />
    </section>
  );
}
