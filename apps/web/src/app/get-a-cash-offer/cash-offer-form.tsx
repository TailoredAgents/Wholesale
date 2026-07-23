"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, CircleCheck, RotateCcw } from "lucide-react";
import Link from "next/link";

import {
  getConversionAttribution,
  getConversionSessionId,
  recordConversionEvent,
} from "../lib/conversion-events";
import { TrackedPhoneLink } from "../tracked-phone-link";
import styles from "./page.module.css";

const consentWording =
  "By submitting this form, you authorize Stonegate Home Buyers to contact you by phone call or email about your property and cash offer request. This permission does not include text messages.";
const draftStorageKey = "stonegate_cash_offer_draft_v1";
const confirmationStorageKey = "stonegate_cash_offer_confirmation_v1";
const storageLifetimeMs = 24 * 60 * 60 * 1000;

const steps = [
  { key: "property", label: "Property", title: "Where is the property?", optional: false },
  { key: "situation", label: "Situation", title: "What should we know about the sale?", optional: true },
  { key: "details", label: "Details", title: "Add any numbers or details you already know.", optional: true },
  { key: "contact", label: "Contact", title: "How should Stonegate follow up?", optional: false },
] as const;

type FormValues = {
  property_address: string;
  property_city: string;
  property_postal_code: string;
  property_type: string;
  property_condition: string;
  occupancy_status: string;
  reason_for_selling: string;
  desired_timeline: string;
  asking_price: string;
  mortgage_balance: string;
  comments: string;
  name: string;
  phone: string;
  email: string;
  preferred_contact_method: "phone" | "email" | "sms";
  consent_to_contact: boolean;
  sms_consent: boolean;
};

type FieldName = keyof FormValues;
type FieldErrors = Partial<Record<FieldName, string>>;
type SubmitState =
  | { status: "idle"; message: string }
  | { status: "submitting"; message: string }
  | { status: "error"; message: string };
type Confirmation = {
  message: string;
  reference: string;
  matchedExistingLead: boolean;
  submittedAt: string;
};

const initialValues: FormValues = {
  property_address: "",
  property_city: "",
  property_postal_code: "",
  property_type: "",
  property_condition: "",
  occupancy_status: "",
  reason_for_selling: "",
  desired_timeline: "",
  asking_price: "",
  mortgage_balance: "",
  comments: "",
  name: "",
  phone: "",
  email: "",
  preferred_contact_method: "phone",
  consent_to_contact: false,
  sms_consent: false,
};

const conditionOptions = [
  ["move_in_ready", "Move-in ready", "Only routine maintenance"],
  ["minor_repairs", "Minor repairs", "Cosmetic updates or small fixes"],
  ["major_repairs", "Major repairs", "Several systems or rooms need work"],
  ["full_renovation", "Full renovation", "Extensive work is likely"],
  ["not_sure", "Not sure", "Stonegate can review it with you"],
] as const;

const occupancyOptions = [
  ["owner_occupied", "Owner occupied"],
  ["tenant_occupied", "Tenant occupied"],
  ["vacant", "Vacant"],
  ["inherited_estate", "Inherited or estate"],
  ["other", "Other"],
] as const;

type CashOfferFormProps = {
  initialAddress?: string;
};

export function CashOfferForm({ initialAddress = "" }: CashOfferFormProps) {
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const [values, setValues] = useState<FormValues>({
    ...initialValues,
    property_address: initialAddress,
  });
  const [activeStep, setActiveStep] = useState(0);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitState, setSubmitState] = useState<SubmitState>({ status: "idle", message: "" });
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [hasRestoredDraft, setHasRestoredDraft] = useState(false);
  const hasTrackedFormStart = useRef(false);
  const hasTrackedFormAbandon = useRef(false);
  const hasSubmitted = useRef(false);
  const isSubmitting = useRef(false);
  const activeStepRef = useRef(activeStep);
  const completedSteps = useRef(new Set<number>());
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    activeStepRef.current = activeStep;
  }, [activeStep]);

  useEffect(() => {
    try {
      const savedConfirmation = parseStoredValue<Confirmation>(confirmationStorageKey);
      if (savedConfirmation) {
        setConfirmation(savedConfirmation);
        hasSubmitted.current = true;
        setHasRestoredDraft(true);
        return;
      }

      const draft = parseStoredValue<{ values: Partial<FormValues>; activeStep: number }>(
        draftStorageKey,
      );
      if (draft) {
        setValues((current) => ({
          ...current,
          ...draft.values,
          property_address: initialAddress || draft.values.property_address || "",
          consent_to_contact: false,
          sms_consent: false,
        }));
        setActiveStep(Math.min(Math.max(draft.activeStep, 0), steps.length - 1));
        hasTrackedFormStart.current = true;
        void recordConversionEvent(apiBaseUrl, "form_restore", {
          restored_step: Math.min(Math.max(draft.activeStep + 1, 1), steps.length),
        });
      }
    } finally {
      setHasRestoredDraft(true);
    }
  }, [apiBaseUrl, initialAddress]);

  useEffect(() => {
    if (!hasRestoredDraft || confirmation) return;
    const draftValues = {
      ...values,
      consent_to_contact: false,
      sms_consent: false,
    };
    try {
      window.sessionStorage.setItem(
        draftStorageKey,
        JSON.stringify({ values: draftValues, activeStep, savedAt: Date.now() }),
      );
    } catch {
      // The form remains fully usable when storage is unavailable.
    }
  }, [activeStep, confirmation, hasRestoredDraft, values]);

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
      void recordConversionEvent(apiBaseUrl, "form_abandon", {
        form: "cash_offer",
        active_step: activeStepRef.current + 1,
        completed_steps: completedSteps.current.size,
      });
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "hidden") trackAbandonment();
    }

    window.addEventListener("beforeunload", trackAbandonment);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("beforeunload", trackAbandonment);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [apiBaseUrl]);

  function handleFormStart() {
    if (hasTrackedFormStart.current) return;
    hasTrackedFormStart.current = true;
    void recordConversionEvent(apiBaseUrl, "form_start", {
      form: "cash_offer",
      starting_step: activeStep + 1,
    });
  }

  function updateValue<Name extends FieldName>(name: Name, value: FormValues[Name]) {
    handleFormStart();
    setValues((current) => ({ ...current, [name]: value }));
    if (errors[name]) setErrors((current) => ({ ...current, [name]: undefined }));
  }

  function moveToStep(nextStep: number) {
    setActiveStep(nextStep);
    setErrors({});
    window.requestAnimationFrame(() => stepHeadingRef.current?.focus());
  }

  function handleNext() {
    handleFormStart();
    const nextErrors = validateStep(activeStep, values);
    if (Object.keys(nextErrors).length) {
      reportValidationErrors(nextErrors);
      return;
    }
    if (!completedSteps.current.has(activeStep)) {
      completedSteps.current.add(activeStep);
      void recordConversionEvent(apiBaseUrl, "form_step_complete", {
        step_key: steps[activeStep].key,
        step_number: activeStep + 1,
      });
    }
    moveToStep(Math.min(activeStep + 1, steps.length - 1));
  }

  function handleBack() {
    if (activeStep === 0) return;
    void recordConversionEvent(apiBaseUrl, "form_step_back", {
      from_step: activeStep + 1,
      to_step: activeStep,
    });
    moveToStep(activeStep - 1);
  }

  function reportValidationErrors(nextErrors: FieldErrors) {
    setErrors(nextErrors);
    void recordConversionEvent(apiBaseUrl, "form_validation_error", {
      step_key: steps[activeStep].key,
      fields: Object.keys(nextErrors),
    });
    const firstField = Object.keys(nextErrors)[0];
    window.requestAnimationFrame(() => document.getElementById(firstField)?.focus());
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (activeStep < steps.length - 1) {
      handleNext();
      return;
    }
    if (isSubmitting.current) return;

    const nextErrors = validateStep(activeStep, values);
    if (Object.keys(nextErrors).length) {
      reportValidationErrors(nextErrors);
      return;
    }
    if (!completedSteps.current.has(activeStep)) {
      completedSteps.current.add(activeStep);
      void recordConversionEvent(apiBaseUrl, "form_step_complete", {
        step_key: steps[activeStep].key,
        step_number: activeStep + 1,
      });
    }

    setSubmitState({ status: "submitting", message: "Sending your request..." });
    isSubmitting.current = true;
    void recordConversionEvent(apiBaseUrl, "form_submit_attempt", {
      form: "cash_offer",
      completed_steps: steps.length,
    });

    const payload = {
      property_address: values.property_address.trim(),
      property_city: values.property_city.trim(),
      property_state: "GA",
      property_postal_code: values.property_postal_code.trim(),
      property_type: values.property_type || null,
      property_condition: values.property_condition || null,
      occupancy_status: values.occupancy_status || null,
      name: values.name.trim(),
      phone: values.phone.trim() || null,
      email: values.email.trim() || null,
      preferred_contact_method: values.preferred_contact_method,
      reason_for_selling: values.reason_for_selling || null,
      desired_timeline: values.desired_timeline || null,
      asking_price: values.asking_price.trim() || null,
      mortgage_balance: values.mortgage_balance.trim() || null,
      comments: values.comments.trim() || null,
      consent_to_contact: values.consent_to_contact,
      consent_wording_version: "seller-contact-web-v2",
      sms_consent: values.sms_consent,
      sms_consent_wording_version: "seller-sms-web-v2",
      conversion_session_id: getConversionSessionId(),
      attribution: getConversionAttribution(),
    };

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/public/seller-leads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const error = new Error(extractApiError(errorPayload) ?? "The form could not be submitted.");
        Object.assign(error, { status: response.status });
        throw error;
      }

      const result = (await response.json()) as {
        lead_id: string;
        matched_existing_lead: boolean;
        message?: string;
      };
      const nextConfirmation: Confirmation = {
        message:
          result.message ??
          "Thanks. Your request was received. The acquisitions team will review it next.",
        reference: result.lead_id.slice(0, 8).toUpperCase(),
        matchedExistingLead: result.matched_existing_lead,
        submittedAt: new Date().toISOString(),
      };
      hasSubmitted.current = true;
      isSubmitting.current = false;
      setConfirmation(nextConfirmation);
      setSubmitState({ status: "idle", message: "" });
      try {
        window.sessionStorage.removeItem(draftStorageKey);
        window.sessionStorage.setItem(
          confirmationStorageKey,
          JSON.stringify({
            ...nextConfirmation,
            savedAt: Date.parse(nextConfirmation.submittedAt),
          }),
        );
      } catch {
        // The visible confirmation still remains for this page lifecycle.
      }
    } catch (caught) {
      isSubmitting.current = false;
      const status =
        caught instanceof Error && "status" in caught ? String(caught.status) : "network";
      void recordConversionEvent(apiBaseUrl, "form_submit_error", {
        category: status === "network" ? "network" : `http_${status}`,
        step_key: "contact",
      });
      setSubmitState({
        status: "error",
        message:
          caught instanceof Error && caught.message
            ? caught.message
            : "Submission failed. Your answers are still here. Try again or call Stonegate.",
      });
    }
  }

  function startAnotherProperty() {
    hasSubmitted.current = false;
    isSubmitting.current = false;
    hasTrackedFormStart.current = false;
    hasTrackedFormAbandon.current = false;
    completedSteps.current.clear();
    setValues(initialValues);
    setActiveStep(0);
    setErrors({});
    setConfirmation(null);
    setSubmitState({ status: "idle", message: "" });
    try {
      window.sessionStorage.removeItem(draftStorageKey);
      window.sessionStorage.removeItem(confirmationStorageKey);
      window.history.replaceState({}, "", "/get-a-cash-offer");
    } catch {
      // Resetting the visible form is sufficient if browser storage is unavailable.
    }
    window.requestAnimationFrame(() => stepHeadingRef.current?.focus());
  }

  if (confirmation) {
    return (
      <section className={styles.confirmation} role="status" aria-live="polite">
        <CircleCheck size={34} aria-hidden="true" />
        <p className={styles.eyebrow}>Request received</p>
        <h2>Thanks. Stonegate has the property request.</h2>
        <p>{confirmation.message}</p>
        <p className={styles.reference}>Request reference: <strong>{confirmation.reference}</strong></p>
        {confirmation.matchedExistingLead ? (
          <p className={styles.existingNotice}>
            We matched this request to your existing property record and kept the updated details
            together instead of creating a duplicate lead.
          </p>
        ) : null}
        <div className={styles.nextSteps}>
          <div><strong>1. Review</strong><span>We check the property details, location, and timing.</span></div>
          <div><strong>2. Follow up</strong><span>A real person reaches out using your preferred contact method.</span></div>
          <div><strong>3. Compare</strong><span>You decide whether a direct cash offer makes sense.</span></div>
        </div>
        <div className={styles.confirmationActions}>
          <TrackedPhoneLink className={styles.secondaryButton} href="tel:+16785417725">Call Stonegate</TrackedPhoneLink>
          <button className={styles.textButton} type="button" onClick={startAnotherProperty}>
            <RotateCcw size={16} aria-hidden="true" /> Submit another property
          </button>
        </div>
      </section>
    );
  }

  const step = steps[activeStep];
  const errorEntries = Object.entries(errors).filter((entry): entry is [FieldName, string] => Boolean(entry[1]));

  return (
    <form className={styles.form} noValidate onFocusCapture={handleFormStart} onSubmit={handleSubmit}>
      <div className={styles.progressHeader}>
        <div>
          <p className={styles.eyebrow}>Cash offer request</p>
          <span>Step {activeStep + 1} of {steps.length}</span>
        </div>
        <progress max={steps.length} value={activeStep + 1} aria-label={`Step ${activeStep + 1} of ${steps.length}`} />
        <ol aria-label="Offer request progress">
          {steps.map((item, index) => (
            <li className={index === activeStep ? styles.currentStep : index < activeStep ? styles.completedStep : ""} key={item.key}>
              <button type="button" disabled={index > activeStep} onClick={() => moveToStep(index)} aria-current={index === activeStep ? "step" : undefined}>
                {index < activeStep ? <Check size={14} aria-hidden="true" /> : <span>{index + 1}</span>}
                {item.label}
              </button>
            </li>
          ))}
        </ol>
      </div>

      <div className={styles.stepIntro}>
        <p>{step.optional ? "Optional step" : "Required step"}</p>
        <h2 ref={stepHeadingRef} tabIndex={-1}>{step.title}</h2>
        <span>{stepDescription(step.key)}</span>
      </div>

      {errorEntries.length ? (
        <div className={styles.errorSummary} role="alert" aria-labelledby="form-error-title">
          <strong id="form-error-title">Check the highlighted information.</strong>
          <ul>
            {errorEntries.map(([field, message]) => (
              <li key={field}><button type="button" onClick={() => document.getElementById(field)?.focus()}>{message}</button></li>
            ))}
          </ul>
        </div>
      ) : null}

      {activeStep === 0 ? (
        <fieldset className={styles.stepFields}>
          <legend className={styles.visuallyHidden}>Property location</legend>
          <Field label="Property street address" name="property_address" error={errors.property_address} required>
            <input id="property_address" name="property_address" autoComplete="street-address" value={values.property_address} onChange={(event) => updateValue("property_address", event.target.value)} aria-invalid={Boolean(errors.property_address)} aria-describedby={errors.property_address ? "property_address-error" : undefined} placeholder="123 Main St" />
          </Field>
          <div className={styles.gridTwo}>
            <Field label="City" name="property_city" error={errors.property_city} required>
              <input id="property_city" name="property_city" autoComplete="address-level2" value={values.property_city} onChange={(event) => updateValue("property_city", event.target.value)} aria-invalid={Boolean(errors.property_city)} aria-describedby={errors.property_city ? "property_city-error" : undefined} placeholder="Atlanta" />
            </Field>
            <Field label="ZIP code" name="property_postal_code" error={errors.property_postal_code} required>
              <input id="property_postal_code" name="property_postal_code" autoComplete="postal-code" inputMode="numeric" value={values.property_postal_code} onChange={(event) => updateValue("property_postal_code", event.target.value)} aria-invalid={Boolean(errors.property_postal_code)} aria-describedby={errors.property_postal_code ? "property_postal_code-error" : undefined} placeholder="30303" />
            </Field>
          </div>
          <Field label="Property type" name="property_type" hint="Optional">
            <select id="property_type" name="property_type" value={values.property_type} onChange={(event) => updateValue("property_type", event.target.value)}>
              <option value="">Select if known</option>
              <option value="single_family">Single-family house</option>
              <option value="townhouse">Townhouse</option>
              <option value="condo">Condo</option>
              <option value="multi_family">Multi-family property</option>
              <option value="mobile_manufactured">Mobile or manufactured home</option>
              <option value="land">Land</option>
              <option value="other">Other</option>
            </select>
          </Field>
        </fieldset>
      ) : null}

      {activeStep === 1 ? (
        <div className={styles.stepFields}>
          <fieldset className={styles.choiceGroup}>
            <legend className={styles.choiceLegend}>Current condition <span>Optional</span></legend>
            <div className={styles.choiceGrid}>
              {conditionOptions.map(([value, label, detail]) => (
                <label className={styles.choice} key={value}>
                  <input type="radio" name="property_condition" value={value} checked={values.property_condition === value} onChange={() => updateValue("property_condition", value)} />
                  <span><strong>{label}</strong><small>{detail}</small></span>
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className={styles.choiceGroup}>
            <legend className={styles.choiceLegend}>Occupancy <span>Optional</span></legend>
            <div className={styles.occupancyGrid}>
              {occupancyOptions.map(([value, label]) => (
                <label className={styles.choice} key={value}>
                  <input type="radio" name="occupancy_status" value={value} checked={values.occupancy_status === value} onChange={() => updateValue("occupancy_status", value)} />
                  <span><strong>{label}</strong></span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className={styles.gridTwo}>
            <Field label="Main reason for considering a sale" name="reason_for_selling" hint="Optional">
              <select id="reason_for_selling" name="reason_for_selling" value={values.reason_for_selling} onChange={(event) => updateValue("reason_for_selling", event.target.value)}>
                <option value="">Select if you would like</option>
                <option value="inherited_property">Inherited property</option>
                <option value="repairs_or_condition">Repairs or condition</option>
                <option value="relocation">Relocation</option>
                <option value="landlord_or_tenants">Landlord or tenant situation</option>
                <option value="financial_change">Financial change</option>
                <option value="vacant_property">Vacant property</option>
                <option value="other">Other</option>
                <option value="just_exploring">Just exploring</option>
              </select>
            </Field>
            <Field label="Preferred timeline" name="desired_timeline" hint="Optional">
              <select id="desired_timeline" name="desired_timeline" value={values.desired_timeline} onChange={(event) => updateValue("desired_timeline", event.target.value)}>
                <option value="">Select if known</option>
                <option value="asap">As soon as reasonably possible</option>
                <option value="within_30_days">Within 30 days</option>
                <option value="within_60_90_days">Within 60-90 days</option>
                <option value="flexible">Flexible</option>
                <option value="just_exploring">Just exploring</option>
              </select>
            </Field>
          </div>
        </div>
      ) : null}

      {activeStep === 2 ? (
        <fieldset className={styles.stepFields}>
          <legend className={styles.visuallyHidden}>Optional price and property details</legend>
          <div className={styles.gridTwo}>
            <Field label="Price you would like to consider" name="asking_price" hint="Optional" error={errors.asking_price}>
              <div className={styles.moneyInput}><span aria-hidden="true">$</span><input id="asking_price" name="asking_price" inputMode="numeric" value={values.asking_price} onChange={(event) => updateValue("asking_price", event.target.value)} aria-invalid={Boolean(errors.asking_price)} aria-describedby={errors.asking_price ? "asking_price-error" : undefined} placeholder="200,000" /></div>
            </Field>
            <Field label="Estimated mortgage balance" name="mortgage_balance" hint="Optional" error={errors.mortgage_balance}>
              <div className={styles.moneyInput}><span aria-hidden="true">$</span><input id="mortgage_balance" name="mortgage_balance" inputMode="numeric" value={values.mortgage_balance} onChange={(event) => updateValue("mortgage_balance", event.target.value)} aria-invalid={Boolean(errors.mortgage_balance)} aria-describedby={errors.mortgage_balance ? "mortgage_balance-error" : undefined} placeholder="90,000" /></div>
            </Field>
          </div>
          <Field label="Repairs, access, ownership, or timing details" name="comments" hint="Optional">
            <textarea id="comments" name="comments" rows={5} maxLength={1000} value={values.comments} onChange={(event) => updateValue("comments", event.target.value)} placeholder="Share only what would help us understand the property or your situation." />
          </Field>
          <p className={styles.characterCount}>{values.comments.length} / 1000</p>
        </fieldset>
      ) : null}

      {activeStep === 3 ? (
        <fieldset className={styles.stepFields}>
          <legend className={styles.visuallyHidden}>Contact details and consent</legend>
          <Field label="Your name" name="name" error={errors.name} required>
            <input id="name" name="name" autoComplete="name" value={values.name} onChange={(event) => updateValue("name", event.target.value)} aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? "name-error" : undefined} placeholder="Jane Seller" />
          </Field>
          <div className={styles.gridTwo}>
            <Field label="Phone" name="phone" error={errors.phone} hint="Required for phone or text follow-up">
              <input id="phone" name="phone" autoComplete="tel" inputMode="tel" value={values.phone} onChange={(event) => updateValue("phone", event.target.value)} aria-invalid={Boolean(errors.phone)} aria-describedby={errors.phone ? "phone-error" : undefined} placeholder="404-555-0100" />
            </Field>
            <Field label="Email" name="email" error={errors.email} hint="Required for email follow-up">
              <input id="email" name="email" type="email" autoComplete="email" value={values.email} onChange={(event) => updateValue("email", event.target.value)} aria-invalid={Boolean(errors.email)} aria-describedby={errors.email ? "email-error" : undefined} placeholder="jane@example.com" />
            </Field>
          </div>
          <fieldset className={styles.contactPreference}>
            <legend>Preferred follow-up method</legend>
            <div>
              {[{ value: "phone", label: "Phone call" }, { value: "email", label: "Email" }, { value: "sms", label: "Text message" }].map((option) => (
                <label key={option.value}><input type="radio" name="preferred_contact_method" value={option.value} checked={values.preferred_contact_method === option.value} onChange={() => updateValue("preferred_contact_method", option.value as FormValues["preferred_contact_method"])} /><span>{option.label}</span></label>
              ))}
            </div>
          </fieldset>

          <label className={`${styles.consent} ${errors.consent_to_contact ? styles.consentError : ""}`}>
            <input id="consent_to_contact" name="consent_to_contact" type="checkbox" checked={values.consent_to_contact} onChange={(event) => updateValue("consent_to_contact", event.target.checked)} aria-invalid={Boolean(errors.consent_to_contact)} aria-describedby={errors.consent_to_contact ? "consent_to_contact-error" : undefined} />
            <span>{consentWording}</span>
          </label>
          {errors.consent_to_contact ? <p className={styles.fieldError} id="consent_to_contact-error">{errors.consent_to_contact}</p> : null}

          <div className={styles.smsConsentBlock}>
            <p><strong>Optional text-message consent</strong><span>Leave unchecked to receive only your selected non-SMS follow-up.</span></p>
            <label className={`${styles.consent} ${errors.sms_consent ? styles.consentError : ""}`}>
              <input id="sms_consent" name="sms_consent" type="checkbox" checked={values.sms_consent} onChange={(event) => updateValue("sms_consent", event.target.checked)} aria-invalid={Boolean(errors.sms_consent)} aria-describedby={errors.sms_consent ? "sms_consent-error" : undefined} />
              <span>
                By checking this optional box, I agree to receive recurring automated text messages
                from Stonegate Home Buyers about my property inquiry, appointments, and cash offer
                updates at the number provided. Message frequency varies. Message and data rates may
                apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase.
                See our <Link href="/terms">Terms &amp; Conditions</Link> and <Link href="/privacy-policy">Privacy Policy</Link>.
              </span>
            </label>
            {errors.sms_consent ? <p className={styles.fieldError} id="sms_consent-error">{errors.sms_consent}</p> : null}
          </div>
        </fieldset>
      ) : null}

      <div className={styles.formActions}>
        {activeStep > 0 ? <button className={styles.backButton} type="button" onClick={handleBack}><ArrowLeft size={17} aria-hidden="true" /> Back</button> : <span />}
        <button className={styles.nextButton} disabled={submitState.status === "submitting"} type="submit">
          {activeStep === steps.length - 1 ? (submitState.status === "submitting" ? "Sending request..." : "Request My Cash Offer") : <>Continue <ArrowRight size={17} aria-hidden="true" /></>}
        </button>
      </div>
      {submitState.message ? <p className={styles[submitState.status]} role="status">{submitState.message}</p> : null}
      <p className={styles.formPrivacy}>Your information is used to review this property inquiry. SMS consent is optional.</p>
    </form>
  );
}

function Field({ label, name, hint, error, required = false, children }: { label: string; name: FieldName; hint?: string; error?: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className={styles.field} htmlFor={name}>
      <span><strong>{label}</strong>{required ? <em>Required</em> : hint ? <small>{hint}</small> : null}</span>
      {children}
      {error ? <p className={styles.fieldError} id={`${name}-error`}>{error}</p> : null}
    </label>
  );
}

function validateStep(step: number, values: FormValues): FieldErrors {
  const errors: FieldErrors = {};
  if (step === 0) {
    if (values.property_address.trim().length < 3) errors.property_address = "Enter the property street address.";
    if (!values.property_city.trim()) errors.property_city = "Enter the property city.";
    if (!/^\d{5}(?:-\d{4})?$/.test(values.property_postal_code.trim())) errors.property_postal_code = "Enter a valid 5-digit ZIP code.";
  }
  if (step === 2) {
    if (values.asking_price && !containsNumber(values.asking_price)) errors.asking_price = "Enter a price using numbers, or leave it blank.";
    if (values.mortgage_balance && !containsNumber(values.mortgage_balance)) errors.mortgage_balance = "Enter a balance using numbers, or leave it blank.";
  }
  if (step === 3) {
    if (!values.name.trim()) errors.name = "Enter your name.";
    if (!values.phone.trim() && !values.email.trim()) {
      errors.phone = "Enter a phone number or email address.";
      errors.email = "Enter a phone number or email address.";
    }
    if (values.phone && values.phone.replace(/\D/g, "").length < 10) errors.phone = "Enter a complete phone number.";
    if (values.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) errors.email = "Enter a valid email address.";
    if (values.preferred_contact_method === "phone" && !values.phone.trim()) errors.phone = "Enter a phone number for phone follow-up.";
    if (values.preferred_contact_method === "email" && !values.email.trim()) errors.email = "Enter an email address for email follow-up.";
    if (values.preferred_contact_method === "sms" && !values.phone.trim()) errors.phone = "Enter a phone number for text follow-up.";
    if (values.sms_consent && !values.phone.trim()) errors.phone = "Enter a phone number to consent to text messages.";
    if (values.preferred_contact_method === "sms" && !values.sms_consent) errors.sms_consent = "Check the optional SMS consent box to select text messages, or choose phone or email.";
    if (!values.consent_to_contact) errors.consent_to_contact = "Confirm that Stonegate may contact you by phone or email about this property.";
  }
  return errors;
}

function containsNumber(value: string) {
  return /\d/.test(value) && !/[a-z]/i.test(value);
}

function stepDescription(key: (typeof steps)[number]["key"]) {
  if (key === "property") return "We use this to identify the house and local market.";
  if (key === "situation") return "Skip anything you do not know. These answers help prepare the first conversation.";
  if (key === "details") return "No price or mortgage information is required to request a review.";
  return "Phone or email is required. Text messaging always requires separate permission.";
}

function parseStoredValue<T>(key: string): T | null {
  const raw = window.sessionStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as T & { savedAt?: number };
    if (!parsed.savedAt || Date.now() - parsed.savedAt > storageLifetimeMs) {
      window.sessionStorage.removeItem(key);
      return null;
    }
    return parsed;
  } catch {
    window.sessionStorage.removeItem(key);
    return null;
  }
}

function extractApiError(payload: unknown) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return null;
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item && typeof item === "object" && "msg" in item && typeof item.msg === "string" ? item.msg.replace(/^Value error,\s*/i, "") : null).filter(Boolean).join(" ");
  }
  return null;
}
