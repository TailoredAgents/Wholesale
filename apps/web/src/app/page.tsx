import Link from "next/link";

import { CashOfferForm } from "./get-a-cash-offer/cash-offer-form";
import { PublicConversionTracker } from "./public-conversion-tracker";
import { PublicSiteFooter } from "./public-site-footer";
import styles from "./page.module.css";
import { sellerSituations } from "./seller-situations";
import { TrackedPhoneLink } from "./tracked-phone-link";

const proofPoints = [
  "No repairs before review",
  "No agent commissions",
  "No obligation to accept",
  "Close on a timeline that works",
];

const processSteps = [
  {
    title: "Tell us where the house is",
    detail: "Start with the address, city, ZIP code, and the best way to reach you.",
  },
  {
    title: "We review the property as-is",
    detail: "Condition, repairs, occupancy, timing, and local buyer demand are part of the review.",
  },
  {
    title: "You compare the offer",
    detail: "You can compare a direct cash-sale path against listing, repairing, or waiting.",
  },
];

const sellerObjections = [
  {
    title: "What if the house needs work?",
    detail:
      "That is exactly when a direct as-is review can help. You do not need to clean, stage, or hire contractors before requesting an offer.",
  },
  {
    title: "What if I am only exploring?",
    detail:
      "The request is no obligation. The goal is to give you a clear option so you can decide whether it fits your timeline and net proceeds.",
  },
  {
    title: "What if there are tenants or family items?",
    detail:
      "Share the basics first. Occupancy, cleanout, inherited property details, and timing can be handled in the follow-up conversation.",
  },
];

const trustMetrics = [
  { value: "24 hr", label: "typical first review window" },
  { value: "0", label: "repairs required to start" },
  { value: "GA", label: "local property focus" },
];

export default function PublicHomePage() {
  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: "home" }} />
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          Stonegate Home Buyers
        </Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          <Link href="/sell-inherited-house">Inherited</Link>
          <Link href="/sell-house-needs-repairs">Repairs</Link>
          <Link href="/sell-house-fast">Fast sale</Link>
          <TrackedPhoneLink href="tel:+16785417725">Call Stonegate</TrackedPhoneLink>
        </nav>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>Georgia cash home buyers</p>
          <h1>Sell your house as-is for cash without repairs, showings, or agent commissions.</h1>
          <p>
            Stonegate Home Buyers gives Georgia homeowners a direct sale option when repairs,
            inheritance, relocation, tenants, or timing make a traditional listing harder.
          </p>
          <div className={styles.heroActions}>
            <a className={styles.primaryAction} href="#cash-offer">
              Start my offer request
            </a>
            <TrackedPhoneLink className={styles.secondaryAction} href="tel:+16785417725">
              Call instead
            </TrackedPhoneLink>
          </div>
          <div className={styles.proofStrip} aria-label="Offer request benefits">
            {proofPoints.map((point) => (
              <span key={point}>{point}</span>
            ))}
          </div>
        </div>

        <aside className={styles.formPanel} id="cash-offer" aria-label="Cash offer request form">
          <CashOfferForm />
        </aside>
      </section>

      <section className={styles.trustBar} aria-label="Stonegate cash offer highlights">
        {trustMetrics.map((metric) => (
          <p key={metric.label}>
            <strong>{metric.value}</strong>
            <span>{metric.label}</span>
          </p>
        ))}
      </section>

      <section className={styles.fitSection} aria-label="Seller situations Stonegate can review">
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>When this helps</p>
          <h2>A direct offer is most useful when certainty matters more than listing prep.</h2>
        </div>
        <div className={styles.reasons}>
          {sellerSituations.map((situation) => (
            <Link href={`/${situation.slug}`} key={situation.slug}>
              <article>
                <p className={styles.cardEyebrow}>{situation.eyebrow}</p>
                <h3>{situation.title}</h3>
                <p>{situation.description}</p>
              </article>
            </Link>
          ))}
        </div>
      </section>

      <section className={styles.process} aria-label="How the cash offer process works">
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>How it works</p>
          <h2>Simple enough to start now, detailed enough for a real offer conversation.</h2>
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

      <section className={styles.objections} aria-label="Common seller questions">
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>Common questions</p>
          <h2>Built for sellers who need a practical option, not pressure.</h2>
        </div>
        <div className={styles.objectionGrid}>
          {sellerObjections.map((item) => (
            <article key={item.title}>
              <h3>{item.title}</h3>
              <p>{item.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.finalCta}>
        <div>
          <p className={styles.eyebrow}>Ready to compare?</p>
          <h2>Start with the address and the best way to reach you.</h2>
        </div>
        <a className={styles.primaryAction} href="#cash-offer">
          Request my cash offer
        </a>
      </section>
      <PublicSiteFooter />
    </main>
  );
}
