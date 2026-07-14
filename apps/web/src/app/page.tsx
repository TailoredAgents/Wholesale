import Link from "next/link";

import { PublicConversionTracker } from "./public-conversion-tracker";
import styles from "./page.module.css";
import { sellerSituations } from "./seller-situations";
import { TrackedPhoneLink } from "./tracked-phone-link";

const processSteps = [
  {
    title: "Request an offer",
    detail: "Send the address, contact details, and what you know about the property.",
  },
  {
    title: "Review the property",
    detail: "The acquisitions team checks condition, location, timing, and seller priorities.",
  },
  {
    title: "Choose your next step",
    detail: "Compare the cash offer against your other options before making a decision.",
  },
];

const trustPoints = [
  "No repairs required before requesting an offer",
  "No agent commissions or open-house schedule",
  "Your consent and property details are captured with each request",
  "Every form submission is routed for follow-up",
];

export default function PublicHomePage() {
  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: "home" }} />
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          Oakwell Home Buyers
        </Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          <Link href="/sell-inherited-house">Inherited</Link>
          <Link href="/sell-house-needs-repairs">Repairs</Link>
          <Link href="/sell-house-fast">Fast sale</Link>
          <Link href="/get-a-cash-offer">Get a cash offer</Link>
        </nav>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <p className={styles.eyebrow}>Georgia home buyers</p>
          <h1>Sell your house for cash without repairs, showings, or agent commissions.</h1>
          <p>
            Oakwell Home Buyers helps Georgia homeowners compare a direct cash-offer option
            when the property, repairs, or timeline make a traditional listing harder.
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
        <img
          className={styles.heroImage}
          src="https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=1400&q=80"
          alt="A bright home exterior with a front porch."
        />
      </section>

      <section className={styles.reasons} aria-label="Common seller situations">
        {sellerSituations.map((situation) => (
          <Link href={`/${situation.slug}`} key={situation.slug}>
            <article>
              <p className={styles.cardEyebrow}>{situation.eyebrow}</p>
              <h2>{situation.title}</h2>
              <p>{situation.description}</p>
            </article>
          </Link>
        ))}
      </section>

      <section className={styles.process} aria-label="How the cash offer process works">
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>How it works</p>
          <h2>A simple path from property details to a clear option.</h2>
        </div>
        <div className={styles.processGrid}>
          {processSteps.map((step, index) => (
            <article key={step.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{step.title}</h3>
              <p>{step.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.trustBand} aria-label="What sellers can expect">
        <div>
          <p className={styles.eyebrow}>What to expect</p>
          <h2>Designed for sellers who need a practical option, not a listing pitch.</h2>
        </div>
        <ul>
          {trustPoints.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </section>

      <section className={styles.finalCta}>
        <div>
          <p className={styles.eyebrow}>Start with the address</p>
          <h2>Request a cash offer and compare your options.</h2>
        </div>
        <Link className={styles.primaryAction} href="/get-a-cash-offer">
          Get my cash offer
        </Link>
      </section>
    </main>
  );
}
