"use client";

import { Menu, Phone, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { publicNavigation, siteConfig } from "./site-config";
import { StonegateLogo } from "./stonegate-logo";
import { TrackedPhoneLink } from "./tracked-phone-link";
import styles from "./public-site-header.module.css";

type PublicSiteHeaderProps = {
  variant?: "standard" | "conversion";
};

export function PublicSiteHeader({ variant = "standard" }: PublicSiteHeaderProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (variant === "conversion") {
    return (
      <header className={`${styles.header} ${styles.conversionHeader}`}>
        <div className={`${styles.inner} ${styles.conversionInner}`}>
          <Link className={styles.brand} href="/" aria-label="Stonegate Home Buyers home">
            <StonegateLogo />
          </Link>
          <TrackedPhoneLink
            className={styles.conversionPhone}
            href={siteConfig.phoneHref}
            metadata={{ placement: "offer_landing_header" }}
          >
            <Phone size={17} aria-hidden="true" />
            <span className={styles.conversionPhoneLabel}>Questions? Call</span>
            <strong>{siteConfig.phoneDisplay}</strong>
          </TrackedPhoneLink>
        </div>
      </header>
    );
  }

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link className={styles.brand} href="/" onClick={() => setIsOpen(false)}>
          <StonegateLogo />
        </Link>

        <button
          className={styles.menuButton}
          type="button"
          aria-expanded={isOpen}
          aria-controls="public-navigation"
          aria-label={isOpen ? "Close navigation" : "Open navigation"}
          onClick={() => setIsOpen((current) => !current)}
        >
          {isOpen ? <X size={20} /> : <Menu size={20} />}
        </button>

        <nav
          className={`${styles.navigation} ${isOpen ? styles.navigationOpen : ""}`}
          id="public-navigation"
          aria-label="Primary navigation"
        >
          {publicNavigation.map((item) => (
            <Link href={item.href} key={item.href} onClick={() => setIsOpen(false)}>
              {item.label}
            </Link>
          ))}
          <TrackedPhoneLink
            className={styles.phone}
            href={siteConfig.phoneHref}
            metadata={{ placement: "public_header" }}
          >
            <Phone size={16} aria-hidden="true" />
            {siteConfig.phoneDisplay}
          </TrackedPhoneLink>
          <Link className={styles.offer} href="/get-a-cash-offer" onClick={() => setIsOpen(false)}>
            See My Selling Options
          </Link>
        </nav>
      </div>
    </header>
  );
}
