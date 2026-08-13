import type { Metadata } from "next";
import { Check } from "lucide-react";

import { PublicConversionTracker } from "../public-conversion-tracker";
import { PublicSiteFooter } from "../public-site-footer";
import { PublicSiteHeader } from "../public-site-header";
import { CashOfferForm } from "./cash-offer-form";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Get a Cash Offer for Your Georgia House | Stonegate",
  description: "Share a Georgia property address and request a no-obligation, direct cash offer review from Stonegate Home Buyers.",
  alternates: { canonical: "/get-a-cash-offer" },
};

export default function GetCashOfferPage() {
  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: "cash_offer" }} />
      <PublicSiteHeader />
      <section className={styles.hero}>
        <div className={styles.copy}>
          <p className={styles.eyebrow}>No-obligation property review</p>
          <h1>Tell us about the house. We will review the direct-sale option.</h1>
          <p>
            The address and a phone number are enough to start. Additional property details and an
            email address are optional and can help Stonegate prepare for the first conversation.
          </p>
          <div className={styles.trustStack}>
            {[
              ["No obligation", "Requesting a review does not commit you to sell."],
              ["As-is condition", "No repairs, cleaning, or staging are required to start."],
              ["Optional texting", "SMS requires a separate checkbox and is never required."],
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
