"use client";

import { FormEvent, useMemo, useRef, useState } from "react";

import { getConversionAttribution, recordConversionEvent } from "../lib/conversion-events";
import styles from "./page.module.css";

const consentWording =
  "By submitting this form, you agree that the company may contact you about your property using the phone number or email provided. Message and data rates may apply. Consent is not required as a condition of purchase.";

type SubmitState =
  | { status: "idle"; message: string }
  | { status: "submitting"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

function getValue(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

export function CashOfferForm() {
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const hasTrackedFormStart = useRef(false);
  const [submitState, setSubmitState] = useState<SubmitState>({
    status: "idle",
    message: "",
  });

  function handleFormStart() {
    if (hasTrackedFormStart.current) {
      return;
    }
    hasTrackedFormStart.current = true;
    void recordConversionEvent(apiBaseUrl, "form_start", { form: "cash_offer" });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const payload = {
      property_address: getValue(formData, "property_address"),
      property_city: getValue(formData, "property_city"),
      property_state: getValue(formData, "property_state") || "GA",
      property_postal_code: getValue(formData, "property_postal_code"),
      name: getValue(formData, "name"),
      phone: getValue(formData, "phone") || null,
      email: getValue(formData, "email") || null,
      preferred_contact_method: getValue(formData, "preferred_contact_method") || "phone",
      reason_for_selling: getValue(formData, "reason_for_selling") || null,
      desired_timeline: getValue(formData, "desired_timeline") || null,
      asking_price: getValue(formData, "asking_price") || null,
      comments: getValue(formData, "comments") || null,
      consent_to_contact: formData.get("consent_to_contact") === "on",
      consent_wording_version: "seller-web-v1",
      attribution: getConversionAttribution(),
    };

    setSubmitState({ status: "submitting", message: "Submitting..." });

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/public/seller-leads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error("The form could not be submitted.");
      }

      const result = (await response.json()) as { message?: string };
      event.currentTarget.reset();
      setSubmitState({
        status: "success",
        message: result.message ?? "Thanks. Your information was received.",
      });
    } catch {
      setSubmitState({
        status: "error",
        message: "Submission failed. Check that the local API is running.",
      });
    }
  }

  return (
    <form className={styles.form} onFocusCapture={handleFormStart} onSubmit={handleSubmit}>
      <div className={styles.gridTwo}>
        <label>
          <span>Property address</span>
          <input name="property_address" autoComplete="street-address" required />
        </label>
        <label>
          <span>ZIP code</span>
          <input name="property_postal_code" autoComplete="postal-code" required />
        </label>
      </div>

      <div className={styles.gridTwo}>
        <label>
          <span>City</span>
          <input name="property_city" autoComplete="address-level2" required />
        </label>
        <label>
          <span>State</span>
          <input name="property_state" autoComplete="address-level1" defaultValue="GA" required />
        </label>
      </div>

      <div className={styles.gridTwo}>
        <label>
          <span>Name</span>
          <input name="name" autoComplete="name" required />
        </label>
        <label>
          <span>Phone</span>
          <input name="phone" autoComplete="tel" />
        </label>
      </div>

      <div className={styles.gridTwo}>
        <label>
          <span>Email</span>
          <input name="email" type="email" autoComplete="email" />
        </label>
        <label>
          <span>Preferred contact</span>
          <select name="preferred_contact_method" defaultValue="phone">
            <option value="phone">Phone</option>
            <option value="sms">Text</option>
            <option value="email">Email</option>
          </select>
        </label>
      </div>

      <div className={styles.gridTwo}>
        <label>
          <span>Reason for selling</span>
          <input name="reason_for_selling" />
        </label>
        <label>
          <span>Timeline</span>
          <select name="desired_timeline" defaultValue="">
            <option value="">Select</option>
            <option value="asap">As soon as possible</option>
            <option value="30_days">Within 30 days</option>
            <option value="60_90_days">60-90 days</option>
            <option value="just_exploring">Just exploring</option>
          </select>
        </label>
      </div>

      <label>
        <span>Asking price</span>
        <input name="asking_price" inputMode="numeric" />
      </label>

      <label>
        <span>Anything else we should know?</span>
        <textarea name="comments" rows={4} />
      </label>

      <label className={styles.consent}>
        <input name="consent_to_contact" type="checkbox" required />
        <span>{consentWording}</span>
      </label>

      <button disabled={submitState.status === "submitting"} type="submit">
        Get my cash offer
      </button>

      {submitState.message ? (
        <p className={styles[submitState.status]} role="status">
          {submitState.message}
        </p>
      ) : null}
    </form>
  );
}
