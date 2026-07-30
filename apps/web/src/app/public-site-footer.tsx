import Link from "next/link";

import { directOfferDisclosure, siteConfig } from "./site-config";
import { MobileConversionBar } from "./mobile-conversion-bar";
import { StonegateLogo } from "./stonegate-logo";
import { TrackedEmailLink } from "./tracked-email-link";
import { TrackedPhoneLink } from "./tracked-phone-link";
import styles from "./public-site-footer.module.css";

export function PublicSiteFooter() {
  return (
    <>
      <footer className={styles.footer}>
        <div className={styles.identity}>
          <Link className={styles.brand} href="/">
            <StonegateLogo inverse />
          </Link>
          <p>Direct, as-is home sale options for Georgia property owners.</p>
          <TrackedPhoneLink className={styles.phone} href={siteConfig.phoneHref}>
            {siteConfig.phoneDisplay}
          </TrackedPhoneLink>
          <TrackedEmailLink
            className={styles.email}
            href={siteConfig.publicEmailHref}
            metadata={{ placement: "public_footer" }}
          >
            {siteConfig.publicEmail}
          </TrackedEmailLink>
        </div>
        <div className={styles.links}>
          <nav aria-label="Seller information">
            <strong>Seller information</strong>
            <Link href="/how-it-works">How It Works</Link>
            <Link href="/#selling-situations">Selling Situations</Link>
            <Link href="/faqs">FAQs</Link>
            <Link href="/service-areas/metro-atlanta">Metro Atlanta Service Area</Link>
            <Link href="/contact">Contact Stonegate</Link>
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
      <MobileConversionBar />
    </>
  );
}
