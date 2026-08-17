import type { Metadata } from "next";
import { Check } from "lucide-react";

import { PublicConversionTracker } from "../public-conversion-tracker";
import { CashOfferForm } from "./cash-offer-form";
import { OfferPageFooter, OfferPageHeader } from "./offer-page-chrome";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Explore Ways to Sell Your Georgia House | Stonegate",
  description:
    "Tell Stonegate about your Georgia property and request a no-obligation review of the selling options that may fit your situation.",
  alternates: { canonical: "/get-a-cash-offer" },
};

export default function GetCashOfferPage() {
  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: "cash_offer" }} />
      <OfferPageHeader />
      <section className={styles.hero}>
        <div className={styles.leftRail}>
          <div className={styles.copy}>
            <p className={styles.eyebrow}>No-pressure property review</p>
            <h1>Let&apos;s find the selling option that fits your situation.</h1>
            <p>
              Tell us about your Georgia property. We&apos;ll review it, learn what matters most, and
              explain the selling options that may fit. No pressure. No obligation.
            </p>
          </div>
          <div className={styles.trustStack}>
            {[
              ["Start as-is", "No repairs, cleaning, or staging are needed."],
              ["Understand your options", "We explain the potential paths and tradeoffs clearly."],
              ["You decide", "There is no pressure or obligation to move forward."],
            ].map(([title, detail]) => (
              <p key={title}>
                <Check size={18} aria-hidden="true" />
                <span><strong>{title}</strong>{detail}</span>
              </p>
            ))}
          </div>
        </div>
        <CashOfferForm />
      </section>
      <OfferPageFooter />
    </main>
  );
}
