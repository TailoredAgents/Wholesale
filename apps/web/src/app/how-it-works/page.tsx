import type { Metadata } from "next";
import { ArrowRight, Check, Phone } from "lucide-react";
import Link from "next/link";

import { PublicSiteFooter } from "../public-site-footer";
import { PublicSiteHeader } from "../public-site-header";
import { directOfferDisclosure, siteConfig } from "../site-config";
import styles from "../public-content.module.css";

export const metadata: Metadata = {
  title: "How Our Direct Cash Offer Works | Stonegate Home Buyers",
  description: "See how Stonegate reviews a Georgia property, prepares a direct cash offer, and explains the tradeoffs before you decide.",
  alternates: { canonical: "/how-it-works" },
};

const steps = [
  { title: "Request a review", detail: "Share the property address and the best way to reach you. Repairs, timing, and price details are helpful but optional at the start." },
  { title: "Talk with a real person", detail: "We confirm ownership context, occupancy, condition, access, timing, and what outcome would actually help you." },
  { title: "Review the property", detail: "Stonegate considers local sales information, property characteristics, expected repairs, resale costs, title risk, and market demand." },
  { title: "Compare a written offer", detail: "If the property fits, we explain the price and proposed timeline. You can accept, decline, negotiate, or pursue another path." },
];

export default function HowItWorksPage() {
  return (
    <main className={styles.page}>
      <PublicSiteHeader />
      <section className={styles.hero}>
        <p className={styles.eyebrow}>How it works</p>
        <h1>A direct offer process designed for clear decisions.</h1>
        <p>
          Stonegate reviews the house in its current condition, explains what affects the offer,
          and gives you room to compare the direct path with listing or repairing.
        </p>
        <div className={styles.heroActions}>
          <Link className={styles.primaryAction} href="/get-a-cash-offer">
            Start My Offer <ArrowRight size={17} aria-hidden="true" />
          </Link>
          <a className={styles.secondaryAction} href={siteConfig.phoneHref}>
            <Phone size={17} aria-hidden="true" /> {siteConfig.phoneDisplay}
          </a>
        </div>
      </section>

      <section className={styles.process}>
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>From address to decision</p>
          <h2>What happens after you contact Stonegate</h2>
        </div>
        <div className={styles.processGrid}>
          {steps.map((step, index) => (
            <article key={step.title}>
              <span>{index + 1}</span>
              <h3>{step.title}</h3>
              <p>{step.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.darkBand}>
        <div>
          <p className={styles.eyebrow}>How price is considered</p>
          <h2>A direct offer is not an appraisal or a promise of retail value.</h2>
        </div>
        <div>
          <p>
            We start with property and market information, then account for current condition,
            likely repairs, holding and resale costs, title or access concerns, and the uncertainty
            an investor assumes.
          </p>
          <p>
            That commonly produces an offer below what a fully prepared home might sell for on the
            retail market. The benefit is an as-is process without Stonegate charging an agent
            commission or requiring showings.
          </p>
        </div>
      </section>

      <section className={styles.splitSection}>
        <div>
          <p className={styles.eyebrow}>Helpful, not required</p>
          <h2>What to have ready</h2>
          <p>More context can improve the first review, but you do not need perfect information.</p>
        </div>
        <div>
          <ul className={styles.checkList}>
            {["Known repair or maintenance issues", "Whether the property is occupied", "Your preferred sale timeline", "Mortgage, title, probate, or ownership context", "Any price or net proceeds you need to evaluate"].map((item) => (
              <li key={item}><Check size={18} aria-hidden="true" /><span>{item}</span></li>
            ))}
          </ul>
        </div>
      </section>

      <section className={styles.finalCta}>
        <div>
          <p className={styles.eyebrow}>Your decision stays yours</p>
          <h2>Request a review without committing to sell.</h2>
        </div>
        <Link className={styles.primaryAction} href="/get-a-cash-offer">Get a Cash Offer <ArrowRight size={17} aria-hidden="true" /></Link>
      </section>
      <p className={styles.disclosure}>{directOfferDisclosure}</p>
      <PublicSiteFooter />
    </main>
  );
}
