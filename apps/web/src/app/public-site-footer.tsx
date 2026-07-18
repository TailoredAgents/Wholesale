import Link from "next/link";

import { TrackedPhoneLink } from "./tracked-phone-link";
import styles from "./public-site-footer.module.css";

export function PublicSiteFooter() {
  return (
    <footer className={styles.footer}>
      <div>
        <Link className={styles.brand} href="/">
          Stonegate Home Buyers
        </Link>
        <p>Direct cash offer options for Georgia property owners.</p>
      </div>
      <nav aria-label="Legal and contact">
        <TrackedPhoneLink href="tel:+16785417725">(678) 541-7725</TrackedPhoneLink>
        <Link href="/privacy-policy">Privacy Policy</Link>
        <Link href="/terms">Terms &amp; Conditions</Link>
      </nav>
      <p className={styles.copyright}>
        &copy; {new Date().getFullYear()} Stonegate Home Buyers. All rights reserved.
      </p>
    </footer>
  );
}
