import { ArrowRight, Check, Phone } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { AddressOfferStart } from "./address-offer-start";
import { PublicConversionTracker } from "./public-conversion-tracker";
import { PublicSiteFooter } from "./public-site-footer";
import { PublicSiteHeader } from "./public-site-header";
import type { SellerSituation } from "./seller-situations";
import { directOfferDisclosure, siteConfig } from "./site-config";
import styles from "./seller-situation.module.css";

type SellerSituationPageProps = {
  situation: SellerSituation;
};

export function SellerSituationPage({ situation }: SellerSituationPageProps) {
  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: situation.slug }} />
      <PublicSiteHeader />

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>{situation.eyebrow}</p>
          <h1>{situation.title}</h1>
          <p>{situation.description}</p>
          <AddressOfferStart compact />
          <a className={styles.phone} href={siteConfig.phoneHref}>
            <Phone size={17} aria-hidden="true" />
            Talk through the property: {siteConfig.phoneDisplay}
          </a>
        </div>
        <div className={styles.heroMedia}>
          <Image
            className={styles.heroImage}
            src={situation.image}
            alt={situation.imageAlt}
            fill
            priority
            sizes="(max-width: 860px) 100vw, 48vw"
          />
        </div>
      </section>

      <section className={styles.proofBand} aria-label="Offer request expectations">
        {situation.proofPoints.map((point) => (
          <div key={point}>
            <Check size={18} aria-hidden="true" />
            <strong>{point}</strong>
          </div>
        ))}
      </section>

      <section className={styles.sectionGrid} aria-label="Seller situation details">
        <article>
          <p className={styles.eyebrow}>What sellers are balancing</p>
          <h2>Common reasons to compare a direct offer</h2>
          <ul>
            {situation.concerns.map((concern) => (
              <li key={concern}>{concern}</li>
            ))}
          </ul>
        </article>

        <article>
          <p className={styles.eyebrow}>What happens next</p>
          <h2>A practical review, not a promise</h2>
          <ol>
            {situation.process.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </article>
      </section>

      <section className={styles.tradeoff}>
        <div>
          <p className={styles.eyebrow}>Know the tradeoff</p>
          <h2>Convenience may mean accepting less than a retail sale could produce.</h2>
        </div>
        <div>
          <p>
            Stonegate considers the property&apos;s current condition, local market information,
            expected repairs, transaction risk, and resale costs. You can compare any written
            offer with an agent&apos;s opinion, an appraisal, or your own repair-and-list plan.
          </p>
          <Link href="/how-it-works">
            See how offers are reviewed <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className={styles.finalCta}>
        <div>
          <p className={styles.eyebrow}>No obligation to continue</p>
          <h2>Start with the property and see whether the direct path fits.</h2>
        </div>
        <Link className={styles.primaryAction} href="/get-a-cash-offer">
          Get My Cash Offer <ArrowRight size={17} aria-hidden="true" />
        </Link>
      </section>
      <p className={styles.disclosure}>{directOfferDisclosure}</p>
      <PublicSiteFooter />
    </main>
  );
}
