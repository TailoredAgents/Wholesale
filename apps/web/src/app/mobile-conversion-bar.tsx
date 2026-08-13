"use client";

import { House, Phone } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo } from "react";

import { recordConversionEvent } from "./lib/conversion-events";
import styles from "./mobile-conversion-bar.module.css";
import { siteConfig } from "./site-config";
import { TrackedPhoneLink } from "./tracked-phone-link";

export function MobileConversionBar() {
  const pathname = usePathname();
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const offerHref =
    pathname === "/get-a-cash-offer"
      ? "#cash-offer-form"
      : "/get-a-cash-offer";

  return (
    <nav className={styles.bar} aria-label="Quick seller actions">
      <TrackedPhoneLink
        className={styles.call}
        href={siteConfig.phoneHref}
        metadata={{
          placement: "mobile_action_bar",
          device_context: "mobile",
          source_path: pathname,
        }}
      >
        <Phone size={18} aria-hidden="true" />
        Call
      </TrackedPhoneLink>
      <Link
        className={styles.offer}
        href={offerHref}
        onClick={() => {
          void recordConversionEvent(apiBaseUrl, "offer_start", {
            entry_point: "mobile_action_bar",
            device_context: "mobile",
            source_path: pathname,
          });
        }}
      >
        <House size={18} aria-hidden="true" />
        See My Options
      </Link>
    </nav>
  );
}
