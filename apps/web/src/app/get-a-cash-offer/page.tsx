import type { Metadata } from "next";
import { Check } from "lucide-react";

import { PublicConversionTracker } from "../public-conversion-tracker";
import { PublicSiteFooter } from "../public-site-footer";
import { PublicSiteHeader } from "../public-site-header";
import { CashOfferForm } from "./cash-offer-form";
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
      <PublicSiteHeader />
      <section className={styles.hero}>
        <div className={styles.copy}>
          <p className={styles.eyebrow}>No-pressure property review</p>
          <h1>Let&apos;s find the selling option that fits your situation.</h1>
          <p>
            Tell us a little about your Georgia property. We&apos;ll review the property, learn what
            matters most to you, and walk you through the options that may fit&mdash;from a quick,
            as-is sale to other ways of selling. No pressure. No obligation.
          </p>
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
      <PublicSiteFooter />
    </main>
  );
}
