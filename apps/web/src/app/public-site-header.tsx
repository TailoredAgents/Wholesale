"use client";

import { Menu, Phone, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { publicNavigation, siteConfig } from "./site-config";
import styles from "./public-site-header.module.css";

export function PublicSiteHeader() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link className={styles.brand} href="/" onClick={() => setIsOpen(false)}>
          <span aria-hidden="true">S</span>
          <strong>{siteConfig.name}</strong>
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
          <a className={styles.phone} href={siteConfig.phoneHref}>
            <Phone size={16} aria-hidden="true" />
            {siteConfig.phoneDisplay}
          </a>
          <Link className={styles.offer} href="/get-a-cash-offer" onClick={() => setIsOpen(false)}>
            Get a Cash Offer
          </Link>
        </nav>
      </div>
    </header>
  );
}
