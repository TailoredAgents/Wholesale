import Link from "next/link";

import { directOfferDisclosure, siteConfig } from "./site-config";
import { TrackedPhoneLink } from "./tracked-phone-link";
import styles from "./public-site-footer.module.css";

export function PublicSiteFooter() {
  return (
    <footer className={styles.footer}>
      <div className={styles.identity}>
        <Link className={styles.brand} href="/">
          <span aria-hidden="true">S</span>
          {siteConfig.name}
        </Link>
        <p>Direct, as-is home sale options for Georgia property owners.</p>
        <TrackedPhoneLink className={styles.phone} href={siteConfig.phoneHref}>
          {siteConfig.phoneDisplay}
        </TrackedPhoneLink>
      </div>
      <div className={styles.links}>
        <nav aria-label="Seller information">
          <strong>Seller information</strong>
          <Link href="/how-it-works">How It Works</Link>
          <Link href="/#selling-situations">Selling Situations</Link>
          <Link href="/faqs">FAQs</Link>
          <Link href="/get-a-cash-offer">Get a Cash Offer</Link>
        </nav>
        <nav aria-label="Company and legal">
          <strong>Company</strong>
          <Link href="/about">About Stonegate</Link>
          <Link href="/privacy-policy">Privacy Policy</Link>
          <Link href="/terms">Terms &amp; Conditions</Link>
        </nav>
      </div>
      <p className={styles.disclosure}>{directOfferDisclosure}</p>
      <p className={styles.copyright}>
        &copy; {new Date().getFullYear()} {siteConfig.name}. All rights reserved.
      </p>
    </footer>
  );
}
