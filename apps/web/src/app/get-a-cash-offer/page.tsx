import type { Metadata } from "next";
import { Check } from "lucide-react";

import { PublicConversionTracker } from "../public-conversion-tracker";
import { CashOfferForm } from "./cash-offer-form";
import { OfferPageFooter, OfferPageHeader } from "./offer-page-chrome";
import { OfferPageScrollController } from "./offer-page-scroll-controller";
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
      <OfferPageScrollController />
      <PublicConversionTracker metadata={{ page: "cash_offer" }} />
      <OfferPageHeader />
      <section className={styles.hero}>
        <div className={styles.leftRail}>
          <div className={styles.copy}>
            <p className={styles.eyebrow}>No-pressure property review</p>
            <h1>Find the right way to sell your Georgia property.</h1>
            <p>Start with the address. We&apos;ll review your options—no pressure or obligation.</p>
          </div>
          <ul className={styles.trustStack} role="list">
            {[
              ["Sell as-is", "No repairs, cleaning, or staging are needed."],
              ["No pressure", "We explain the potential paths and tradeoffs clearly."],
              ["No obligation", "You decide whether you want to move forward."],
            ].map(([title, detail]) => (
              <li key={title}>
                <Check size={18} aria-hidden="true" />
                <span>
                  <strong>{title}</strong>
                  <span className={styles.trustDetail}>{detail}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <CashOfferForm />
      </section>
      <OfferPageFooter />
    </main>
  );
}
