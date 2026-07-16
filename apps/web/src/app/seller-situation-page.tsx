import Link from "next/link";

import { PublicConversionTracker } from "./public-conversion-tracker";
import type { SellerSituation } from "./seller-situations";
import styles from "./seller-situation.module.css";
import { TrackedPhoneLink } from "./tracked-phone-link";

type SellerSituationPageProps = {
  situation: SellerSituation;
};

export function SellerSituationPage({ situation }: SellerSituationPageProps) {
  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: situation.slug }} />
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          Stonegate Home Buyers
        </Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          <Link href="/sell-inherited-house">Inherited</Link>
          <Link href="/sell-house-needs-repairs">Repairs</Link>
          <Link href="/sell-house-fast">Fast sale</Link>
          <Link href="/get-a-cash-offer">Get a cash offer</Link>
        </nav>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>{situation.eyebrow}</p>
          <h1>{situation.title}</h1>
          <p>{situation.description}</p>
          <div className={styles.actions}>
            <Link className={styles.primaryAction} href="/get-a-cash-offer">
              Get my cash offer
            </Link>
            <TrackedPhoneLink className={styles.secondaryAction} href="tel:+14045550100">
              Call Stonegate
            </TrackedPhoneLink>
          </div>
          <div className={styles.reassurance}>
            <span>No obligation</span>
            <span>As-is review</span>
            <span>Georgia-focused team</span>
          </div>
        </div>
        <img
          className={styles.heroImage}
          src={situation.image}
          alt={situation.imageAlt}
          width="1200"
          height="900"
          fetchPriority="high"
          decoding="async"
        />
      </section>

      <section className={styles.sectionGrid} aria-label="Seller situation details">
        <article>
          <p className={styles.eyebrow}>Common concerns</p>
          <h2>Why sellers ask for a direct offer</h2>
          <ul>
            {situation.concerns.map((concern) => (
              <li key={concern}>{concern}</li>
            ))}
          </ul>
        </article>

        <article>
          <p className={styles.eyebrow}>Simple process</p>
          <h2>What happens next</h2>
          <ol>
            {situation.process.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </article>
      </section>

      <section className={styles.proofBand} aria-label="Offer expectations">
        {situation.proofPoints.map((point) => (
          <div key={point}>
            <span></span>
            <strong>{point}</strong>
          </div>
        ))}
      </section>

      <section className={styles.finalCta}>
        <div>
          <p className={styles.eyebrow}>Start with the property basics</p>
          <h2>See if a direct cash offer makes sense.</h2>
        </div>
        <Link className={styles.primaryAction} href="/get-a-cash-offer">
          Get my cash offer
        </Link>
      </section>
    </main>
  );
}
