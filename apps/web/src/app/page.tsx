import Link from "next/link";

import { PublicConversionTracker } from "./public-conversion-tracker";
import styles from "./page.module.css";
import { TrackedPhoneLink } from "./tracked-phone-link";

export default function PublicHomePage() {
  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: "home" }} />
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          Oakwell Home Buyers
        </Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          <Link href="/get-a-cash-offer">Get a cash offer</Link>
        </nav>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <p className={styles.eyebrow}>Georgia home buyers</p>
          <h1>Sell your house for cash without repairs, showings, or agent commissions.</h1>
          <p>
            Oakwell Home Buyers helps homeowners request a direct cash offer and choose a
            closing timeline that fits their situation.
          </p>
          <div className={styles.actions}>
            <Link className={styles.primaryAction} href="/get-a-cash-offer">
              Get my cash offer
            </Link>
            <TrackedPhoneLink className={styles.secondaryAction} href="tel:+14045550100">
              Call Oakwell
            </TrackedPhoneLink>
          </div>
        </div>
        <div className={styles.heroPanel} aria-label="Seller benefits">
          <div>
            <span>01</span>
            <strong>Tell us about the property</strong>
            <p>Share the basics so the acquisitions team can review the opportunity.</p>
          </div>
          <div>
            <span>02</span>
            <strong>Talk with a real person</strong>
            <p>We follow up quickly and ask only the questions needed to evaluate the house.</p>
          </div>
          <div>
            <span>03</span>
            <strong>Choose your next step</strong>
            <p>If the offer works, we coordinate a straightforward closing process.</p>
          </div>
        </div>
      </section>

      <section className={styles.reasons} aria-label="Common seller situations">
        <article>
          <h2>Inherited property</h2>
          <p>Request an offer when you need a practical path forward for a family property.</p>
        </article>
        <article>
          <h2>Repairs needed</h2>
          <p>Skip contractors, cleanup, and inspection surprises.</p>
        </article>
        <article>
          <h2>Fast timeline</h2>
          <p>Start the conversation early when timing matters.</p>
        </article>
      </section>
    </main>
  );
}
