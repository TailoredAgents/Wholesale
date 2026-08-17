/* eslint-disable @next/next/no-html-link-for-pages -- Native navigation keeps exit-route data off the conversion landing page. */
import Image from "next/image";
import { House, Phone } from "lucide-react";

import { siteConfig } from "../site-config";
import { TrackedPhoneLink } from "../tracked-phone-link";
import { OfferPageActionLink } from "./offer-page-action-link";
import styles from "./page.module.css";

type OfferPageLogoProps = {
  inverse?: boolean;
};

function OfferPageLogo({ inverse = false }: OfferPageLogoProps) {
  return (
    <span
      aria-label="Stonegate Home Buyers"
      className={`${styles.offerLogo} ${inverse ? styles.offerLogoInverse : ""}`}
      role="img"
    >
      <Image
        alt=""
        aria-hidden="true"
        className={styles.offerLogoMark}
        height={512}
        sizes="44px"
        src="/brand/stonegate-mark.png"
        width={512}
      />
      <span aria-hidden="true" className={styles.offerLogoWordmark}>
        <strong>STONEGATE</strong>
        <span>HOME BUYERS</span>
      </span>
    </span>
  );
}

export function OfferPageHeader() {
  return (
    <header className={styles.offerHeader}>
      <div className={styles.offerHeaderInner}>
        <a
          aria-label="Stonegate Home Buyers home"
          className={styles.offerHeaderBrand}
          href="/"
        >
          <OfferPageLogo />
        </a>
        <TrackedPhoneLink
          className={styles.offerHeaderPhone}
          href={siteConfig.phoneHref}
          metadata={{ placement: "offer_landing_header" }}
        >
          <Phone size={17} aria-hidden="true" />
          <span className={styles.offerHeaderPhoneLabel}>Questions? Call</span>
          <strong>{siteConfig.phoneDisplay}</strong>
        </TrackedPhoneLink>
      </div>
    </header>
  );
}

export function OfferPageFooter() {
  return (
    <>
      <footer className={styles.offerFooter}>
        <div className={styles.offerFooterIdentity}>
          <a className={styles.offerFooterBrand} href="/">
            <OfferPageLogo inverse />
          </a>
          <p>Flexible home-selling options for Georgia property owners.</p>
          <TrackedPhoneLink
            className={styles.offerFooterPhone}
            href={siteConfig.phoneHref}
            metadata={{ placement: "offer_landing_footer" }}
          >
            {siteConfig.phoneDisplay}
          </TrackedPhoneLink>
        </div>
        <nav className={styles.offerFooterLegal} aria-label="Legal information">
          <a href="/privacy-policy">Privacy Policy</a>
          <a href="/terms">Terms &amp; Conditions</a>
        </nav>
        <p className={styles.offerFooterCopyright}>
          &copy; {new Date().getFullYear()} {siteConfig.name}. All rights reserved.
        </p>
      </footer>
      <nav className={styles.offerMobileBar} aria-label="Quick seller actions">
        <TrackedPhoneLink
          className={styles.offerMobileCall}
          href={siteConfig.phoneHref}
          metadata={{
            placement: "mobile_action_bar",
            device_context: "mobile",
            source_path: "/get-a-cash-offer",
          }}
        >
          <Phone size={18} aria-hidden="true" />
          Call
        </TrackedPhoneLink>
        <OfferPageActionLink className={styles.offerMobileAction}>
          <House size={18} aria-hidden="true" />
          See My Options
        </OfferPageActionLink>
      </nav>
    </>
  );
}
