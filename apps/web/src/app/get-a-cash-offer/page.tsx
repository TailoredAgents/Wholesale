import Link from "next/link";

import { PublicConversionTracker } from "../public-conversion-tracker";
import { CashOfferForm } from "./cash-offer-form";
import styles from "./page.module.css";

export const metadata = {
  title: "Get a Cash Offer | Stonegate Home Buyers",
  description: "Request a cash offer for a Georgia property.",
};

export default function GetCashOfferPage() {
  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: "cash_offer" }} />
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          Stonegate Home Buyers
        </Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          <Link href="/sell-inherited-house">Inherited</Link>
          <Link href="/sell-house-needs-repairs">Repairs</Link>
          <Link href="/sell-house-fast">Fast sale</Link>
        </nav>
      </header>
      <section className={styles.hero}>
        <div className={styles.copy}>
          <p className={styles.eyebrow}>Fast as-is review</p>
          <h1>Start with the address. We will handle the rest from there.</h1>
          <p>
            The fastest requests include the property address, city, ZIP code, your name, and
            a phone or email. Extra details help, but they are optional.
          </p>
          <div className={styles.trustStack}>
            <p>
              <strong>No obligation.</strong>
              <span>You can compare the offer before making a decision.</span>
            </p>
            <p>
              <strong>No repairs first.</strong>
              <span>Condition, cleanup, and timing are part of the review.</span>
            </p>
            <p>
              <strong>Clear consent.</strong>
              <span>We only follow up using the contact details you submit.</span>
            </p>
          </div>
        </div>
        <CashOfferForm />
      </section>
    </main>
  );
}
