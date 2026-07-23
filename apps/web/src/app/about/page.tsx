import type { Metadata } from "next";
import { ArrowRight, Check, Phone } from "lucide-react";
import Link from "next/link";

import { PublicSiteFooter } from "../public-site-footer";
import { PublicSiteHeader } from "../public-site-header";
import { directOfferDisclosure, siteConfig } from "../site-config";
import styles from "../public-content.module.css";

export const metadata: Metadata = {
  title: "About Stonegate Home Buyers | Georgia",
  description: "Learn what Stonegate Home Buyers does, where we operate, and how we approach direct property offers in Georgia.",
  alternates: { canonical: "/about" },
};

const principles = [
  { title: "Explain the tradeoff", detail: "A convenient as-is offer may be lower than potential retail value. Sellers should understand that before deciding." },
  { title: "Use real property context", detail: "Condition, access, occupancy, title, timing, repairs, and local demand all belong in the review." },
  { title: "Keep pressure out", detail: "Requesting or discussing an offer creates no obligation to sell. A decision should survive comparison." },
  { title: "Preserve accountability", detail: "Seller details, conversations, appointments, assumptions, and decisions are retained in one operating record." },
];

export default function AboutPage() {
  return (
    <main className={styles.page}>
      <PublicSiteHeader />
      <section className={styles.hero}>
        <p className={styles.eyebrow}>About Stonegate</p>
        <h1>A Georgia home-buying company built around clear decisions.</h1>
        <p>
          Stonegate Home Buyers provides a direct sale option for owners who value an as-is
          process, fewer listing steps, and a timeline defined in writing.
        </p>
        <div className={styles.heroActions}>
          <Link className={styles.primaryAction} href="/get-a-cash-offer">Request an Offer <ArrowRight size={17} aria-hidden="true" /></Link>
          <a className={styles.secondaryAction} href={siteConfig.phoneHref}><Phone size={17} aria-hidden="true" /> {siteConfig.phoneDisplay}</a>
        </div>
      </section>

      <section className={styles.identitySection}>
        <div>
          <p className={styles.eyebrow}>What we are</p>
          <h2>A direct property buyer and real estate investor.</h2>
          <p>
            Stonegate evaluates properties for direct purchase. Depending on the written contract
            and transaction, Stonegate may buy a property or assign contractual purchase rights to
            another investor.
          </p>
        </div>
        <div>
          <p className={styles.eyebrow}>What we are not</p>
          <h2>Not a brokerage, appraisal service, or guaranteed buyer.</h2>
          <p>
            We do not represent the seller as an agent, and an offer is not an appraisal. Every
            potential purchase depends on property review, title, mutually accepted contract terms,
            and any verification described in that contract.
          </p>
        </div>
      </section>

      <section className={styles.darkBand}>
        <div>
          <p className={styles.eyebrow}>Our starting market</p>
          <h2>Georgia first, with local operating discipline.</h2>
        </div>
        <div>
          <p>
            Stonegate is beginning in Georgia with an initial focus on metro Atlanta and surrounding
            communities. Expansion into nearby states will happen only as local data, buyers,
            service providers, and accountable team coverage are established.
          </p>
          <p>Each inquiry is reviewed by a person before a seller is asked to rely on an offer.</p>
        </div>
      </section>

      <section className={styles.principles}>
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>Operating principles</p>
          <h2>The standards behind the seller experience</h2>
        </div>
        <div className={styles.principleGrid}>
          {principles.map((principle) => (
            <article key={principle.title}>
              <Check size={19} aria-hidden="true" />
              <h3>{principle.title}</h3>
              <p>{principle.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.finalCta}>
        <div><p className={styles.eyebrow}>Have a property to discuss?</p><h2>Start with the address or speak with Stonegate.</h2></div>
        <Link className={styles.primaryAction} href="/get-a-cash-offer">Start My Offer <ArrowRight size={17} aria-hidden="true" /></Link>
      </section>
      <p className={styles.disclosure}>{directOfferDisclosure}</p>
      <PublicSiteFooter />
    </main>
  );
}
