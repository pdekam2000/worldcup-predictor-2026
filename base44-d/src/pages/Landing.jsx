import React from "react";
import LandingNav from "@/components/landing/LandingNav";
import HeroSection from "@/components/landing/HeroSection";
import FeaturesSection from "@/components/landing/FeaturesSection";
import StatsSection from "@/components/landing/StatsSection";
import UnderstandingSection from "@/components/landing/UnderstandingSection";
import TrustStrip from "@/components/landing/TrustStrip";
import PricingSection from "@/components/landing/PricingSection";
import FAQSection from "@/components/landing/FAQSection";
import FooterSection from "@/components/landing/FooterSection";

export default function Landing() {
  return (
    <div className="min-h-screen bg-background">
      <LandingNav />
      <HeroSection />
      <FeaturesSection />
      <UnderstandingSection />
      <StatsSection />
      <TrustStrip />
      <PricingSection />
      <FAQSection />
      <FooterSection />
    </div>
  );
}