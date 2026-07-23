import { ArrowRight, MapPin } from "lucide-react";

import styles from "./address-offer-start.module.css";

type AddressOfferStartProps = {
  compact?: boolean;
};

export function AddressOfferStart({ compact = false }: AddressOfferStartProps) {
  return (
    <form
      action="/get-a-cash-offer"
      className={`${styles.form} ${compact ? styles.compact : ""}`}
      method="get"
    >
      <label htmlFor={compact ? "property-address-compact" : "property-address"}>
        Property address
      </label>
      <div className={styles.control}>
        <MapPin size={20} aria-hidden="true" />
        <input
          id={compact ? "property-address-compact" : "property-address"}
          name="address"
          autoComplete="street-address"
          placeholder="Enter the property street address"
          required
        />
        <button type="submit">
          <span>Start My Offer</span>
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      </div>
      <p>No obligation. No SMS consent required to request an offer.</p>
    </form>
  );
}
