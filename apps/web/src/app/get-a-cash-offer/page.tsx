import Link from "next/link";

import { PublicConversionTracker } from "../public-conversion-tracker";
import { CashOfferForm } from "./cash-offer-form";
import styles from "./page.module.css";

export const metadata = {
  title: "Get a Cash Offer | Oakwell Home Buyers",
  description: "Request a cash offer for a Georgia property.",
};

export default function GetCashOfferPage() {
  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: "cash_offer" }} />
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          Oakwell Home Buyers
        </Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          <Link href="/sell-inherited-house">Inherited</Link>
          <Link href="/sell-house-needs-repairs">Repairs</Link>
          <Link href="/sell-house-fast">Fast sale</Link>
        </nav>
      </header>
      <section className={styles.hero}>
        <div className={styles.copy}>
          <p className={styles.eyebrow}>Georgia home buyers</p>
          <h1>Get a cash offer for your property</h1>
          <p>
            Share the basics and our acquisitions team will review the property, timing,
            and condition before following up with your next step.
          </p>
        </div>
        <CashOfferForm />
      </section>
    </main>
  );
}
