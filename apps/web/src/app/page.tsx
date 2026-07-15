import Link from "next/link";

import { PublicConversionTracker } from "./public-conversion-tracker";
import styles from "./page.module.css";
import { sellerSituations } from "./seller-situations";
import { TrackedPhoneLink } from "./tracked-phone-link";

const processSteps = [
  {
    title: "Send the basics",
    detail: "Start with the address and the best way to reach you. Extra details are optional.",
  },
  {
    title: "Get a real review",
    detail: "We check the property, timing, condition, and local buyer demand before follow-up.",
  },
  {
    title: "Compare your options",
    detail: "Review the cash-offer path against listing, repairs, or waiting. No obligation.",
  },
];

const trustPoints = [
  "As-is review before you spend money on repairs",
  "No agent commissions, open houses, or listing prep",
  "Clear consent, privacy, and follow-up tracking",
  "Every request enters our local acquisition workflow",
];

const heroStats = [
  { value: "24 hr", label: "typical first review window" },
  { value: "0", label: "repairs required before requesting" },
  { value: "GA", label: "local market focus" },
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
          <p className={styles.eyebrow}>Georgia cash home buyers</p>
          <h1>Get a fair as-is cash offer without repairs, showings, or agent commissions.</h1>
          <p>
            Oakwell Home Buyers helps Georgia homeowners compare a direct sale when repairs,
            timing, inherited property issues, or uncertainty make listing harder.
          </p>
          <div className={styles.actions}>
            <Link className={styles.primaryAction} href="/get-a-cash-offer">
              Get my cash offer
            </Link>
            <TrackedPhoneLink className={styles.secondaryAction} href="tel:+14045550100">
              Call Oakwell
            </TrackedPhoneLink>
          </div>
          <div className={styles.reassurance} aria-label="Offer request benefits">
            <span>No obligation</span>
            <span>No cleanup required</span>
            <span>Phone or email is enough to start</span>
          </div>
        </div>
        <div className={styles.heroVisual}>
          <img
            className={styles.heroImage}
            src="https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=1200&q=72"
            alt="A bright home exterior with a front porch."
            width="1200"
            height="900"
            fetchPriority="high"
            decoding="async"
          />
          <div className={styles.offerPanel} aria-label="Oakwell offer process highlights">
            {heroStats.map((stat) => (
              <p key={stat.label}>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </p>
            ))}
          </div>
        </div>
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
          <h2>A low-friction path from property details to a clear option.</h2>
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
