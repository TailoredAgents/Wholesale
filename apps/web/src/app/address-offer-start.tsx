"use client";

import { ArrowRight, MapPin } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  getConversionExperimentContext,
  recordConversionEvent,
} from "./lib/conversion-events";
import styles from "./address-offer-start.module.css";

type AddressOfferStartProps = {
  compact?: boolean;
  inputId?: string;
};

export function AddressOfferStart({ compact = false, inputId }: AddressOfferStartProps) {
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const addressInputId =
    inputId ?? (compact ? "property-address-compact" : "property-address");
  const [ctaLabel, setCtaLabel] = useState("Start My Offer");

  useEffect(() => {
    if (compact) return;
    void getConversionExperimentContext(apiBaseUrl).then((experiment) => {
      if (experiment?.surface_key === "homepage_offer_cta") {
        setCtaLabel(experiment.cta_label);
      }
    });
  }, [apiBaseUrl, compact]);

  return (
    <form
      action="/get-a-cash-offer"
      className={`${styles.form} ${compact ? styles.compact : ""}`}
      method="get"
      onSubmit={() => {
        window.sessionStorage.removeItem("stonegate_cash_offer_draft_v1");
        window.sessionStorage.removeItem("stonegate_cash_offer_confirmation_v1");
        void recordConversionEvent(apiBaseUrl, "offer_start", {
          entry_point: compact ? "supporting_cta" : "homepage_hero",
        });
      }}
    >
      <label htmlFor={addressInputId}>Property address</label>
      <div className={styles.control}>
        <MapPin size={20} aria-hidden="true" />
        <input
          id={addressInputId}
          name="address"
          autoComplete="street-address"
          placeholder="Enter the property street address"
          required
        />
        <button type="submit">
          <span>{ctaLabel}</span>
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      </div>
      <p>No obligation. No SMS consent required to request an offer.</p>
    </form>
  );
}
