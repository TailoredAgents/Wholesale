"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { getConversionAttribution, recordConversionEvent } from "../lib/conversion-events";
import { TrackedPhoneLink } from "../tracked-phone-link";
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
  const hasTrackedFormAbandon = useRef(false);
  const hasSubmitted = useRef(false);
  const isSubmitting = useRef(false);
  const [submitState, setSubmitState] = useState<SubmitState>({
    status: "idle",
    message: "",
  });

  useEffect(() => {
    function trackAbandonment() {
      if (
        !hasTrackedFormStart.current ||
        hasSubmitted.current ||
        isSubmitting.current ||
        hasTrackedFormAbandon.current
      ) {
        return;
      }
      hasTrackedFormAbandon.current = true;
      void recordConversionEvent(apiBaseUrl, "form_abandon", { form: "cash_offer" });
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "hidden") {
        trackAbandonment();
      }
    }

    window.addEventListener("beforeunload", trackAbandonment);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("beforeunload", trackAbandonment);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [apiBaseUrl]);

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
      company_website: getValue(formData, "company_website") || null,
      consent_to_contact: formData.get("consent_to_contact") === "on",
      consent_wording_version: "seller-web-v1",
      attribution: getConversionAttribution(),
    };

    setSubmitState({ status: "submitting", message: "Submitting..." });
    isSubmitting.current = true;

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
      hasSubmitted.current = true;
      isSubmitting.current = false;
      event.currentTarget.reset();
      setSubmitState({
        status: "success",
        message:
          result.message ??
          "Thanks. Your request was received. The acquisitions team will review it next.",
      });
    } catch {
      isSubmitting.current = false;
      setSubmitState({
        status: "error",
        message:
          "Submission failed. Please check the required fields or call Oakwell directly.",
      });
    }
  }

  if (submitState.status === "success") {
    return (
      <section className={styles.confirmation} role="status" aria-live="polite">
        <p className={styles.eyebrow}>Request received</p>
        <h2>Thanks. We have the property details.</h2>
        <p>{submitState.message}</p>
        <div className={styles.nextSteps}>
          <div>
            <strong>1. Review</strong>
            <span>We check the property details, location, and timing.</span>
          </div>
          <div>
            <strong>2. Follow up</strong>
            <span>A real person reaches out using your preferred contact method.</span>
          </div>
          <div>
            <strong>3. Compare options</strong>
            <span>You decide whether a direct cash offer makes sense.</span>
          </div>
        </div>
        <div className={styles.confirmationActions}>
          <TrackedPhoneLink className={styles.secondaryButton} href="tel:+14045550100">
            Call Oakwell
          </TrackedPhoneLink>
          <button
            className={styles.textButton}
            type="button"
            onClick={() => {
              hasSubmitted.current = false;
              isSubmitting.current = false;
              hasTrackedFormStart.current = false;
              hasTrackedFormAbandon.current = false;
              setSubmitState({ status: "idle", message: "" });
            }}
          >
            Submit another property
          </button>
        </div>
      </section>
    );
  }

  return (
    <form className={styles.form} onFocusCapture={handleFormStart} onSubmit={handleSubmit}>
      <div className={styles.formIntro}>
        <p className={styles.eyebrow}>Cash offer request</p>
        <h2>Get started in about a minute.</h2>
        <p>Required fields are marked. Phone or email is enough to start.</p>
      </div>

      <label className={styles.hiddenField} aria-hidden="true">
        <span>Company website</span>
        <input name="company_website" autoComplete="off" tabIndex={-1} />
      </label>

      <fieldset className={styles.fieldset}>
        <legend>Property basics</legend>
        <div className={styles.gridTwo}>
          <label>
            <span>Property address *</span>
            <input
              name="property_address"
              autoComplete="street-address"
              placeholder="123 Main St"
              required
            />
          </label>
          <label>
            <span>ZIP code *</span>
            <input
              name="property_postal_code"
              autoComplete="postal-code"
              inputMode="numeric"
              placeholder="30303"
              required
            />
          </label>
        </div>

        <div className={styles.gridTwo}>
          <label>
            <span>City *</span>
            <input
              name="property_city"
              autoComplete="address-level2"
              placeholder="Atlanta"
              required
            />
          </label>
          <input name="property_state" type="hidden" defaultValue="GA" />
        </div>
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend>Contact</legend>
        <div className={styles.gridTwo}>
          <label>
            <span>Name *</span>
            <input name="name" autoComplete="name" placeholder="Jane Seller" required />
          </label>
          <label>
            <span>Phone</span>
            <input name="phone" autoComplete="tel" inputMode="tel" placeholder="404-555-0100" />
            <small>Best for the fastest response.</small>
          </label>
        </div>

        <div className={styles.gridTwo}>
          <label>
            <span>Email</span>
            <input name="email" type="email" autoComplete="email" placeholder="jane@example.com" />
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
      </fieldset>

      <details className={styles.optionalDetails}>
        <summary>Add timing, repairs, or price details</summary>
        <fieldset className={styles.fieldset}>
          <legend>Optional context</legend>
          <div className={styles.gridTwo}>
            <label>
              <span>Reason for selling</span>
              <input name="reason_for_selling" placeholder="Inherited, repairs, moving, etc." />
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
            <span>Target price or mortgage balance</span>
            <input name="asking_price" inputMode="numeric" placeholder="Optional" />
            <small>Optional, but useful if you already have a number in mind.</small>
          </label>

          <label>
            <span>Anything else we should know?</span>
            <textarea
              name="comments"
              rows={4}
              placeholder="Repairs needed, occupancy, access, deadline, or other context."
            />
          </label>
        </fieldset>
      </details>

      <label className={styles.consent}>
        <input name="consent_to_contact" type="checkbox" required />
        <span>{consentWording}</span>
      </label>

      <button disabled={submitState.status === "submitting"} type="submit">
        {submitState.status === "submitting" ? "Sending request..." : "Request my cash offer"}
      </button>

      {submitState.message ? (
        <p className={styles[submitState.status]} role="status">
          {submitState.message}
        </p>
      ) : null}
    </form>
  );
}
