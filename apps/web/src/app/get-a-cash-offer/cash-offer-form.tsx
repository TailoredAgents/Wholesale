"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CircleCheck,
  ClipboardPenLine,
  Mail,
  RotateCcw,
} from "lucide-react";
import Link from "next/link";

import {
  type ConversionExperimentContext,
  createMetaBrowserEvent,
  getConversionAttribution,
  getConversionExperimentContext,
  getConversionSessionId,
  getDeviceCategory,
  recordConversionEvent,
  trackMetaPixelEvent,
  waitForMetaBrowserCookies,
} from "../lib/conversion-events";
import { siteConfig } from "../site-config";
import { TrackedEmailLink } from "../tracked-email-link";
import { TrackedPhoneLink } from "../tracked-phone-link";
import styles from "./page.module.css";
import {
  PropertyAddressField,
  type PropertyAddressValue,
} from "./property-address-field";

const consentWording =
  "By submitting this form, you authorize Stonegate Home Buyers to contact you by phone call or email about your property inquiry and possible selling options. This permission does not include text messages.";
const draftStorageKey = "stonegate_cash_offer_draft_v1";
const confirmationStorageKey = "stonegate_cash_offer_confirmation_v1";
const storageLifetimeMs = 24 * 60 * 60 * 1000;

const steps = [
  { key: "property", label: "Property", title: "Where is the property?" },
  { key: "contact", label: "Contact", title: "How can Stonegate reach you?" },
] as const;

type FormValues = {
  property_address: string;
  property_city: string;
  property_state: string;
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
  company_website: string;
};

type FieldName = keyof FormValues;
type FieldErrors = Partial<Record<FieldName, string>>;
type SubmitState =
  | { status: "idle"; message: string }
  | { status: "submitting"; message: string }
  | { status: "error"; message: string };
type EnrichmentState =
  | { status: "idle"; message: string }
  | { status: "submitting"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };
type Confirmation = {
  message: string;
  reference: string;
  matchedExistingLead: boolean;
  submittedAt: string;
  enrichmentToken?: string;
  enrichmentExpiresAt?: string;
  enriched?: boolean;
};
type StoredDraft = {
  values: Partial<FormValues>;
  activeStep: number;
  intakeAttemptId?: string;
};
type AddressCaptureOptions = {
  retryIfInFlight?: boolean;
  retryWithEnrichedCookies?: boolean;
};

const initialValues: FormValues = {
  property_address: "",
  property_city: "",
  property_state: "GA",
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
  company_website: "",
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
  const [smsConsent, setSmsConsent] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitState, setSubmitState] = useState<SubmitState>({ status: "idle", message: "" });
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [isEnrichmentOpen, setIsEnrichmentOpen] = useState(false);
  const [enrichmentState, setEnrichmentState] = useState<EnrichmentState>({
    status: "idle",
    message: "",
  });
  const [hasRestoredDraft, setHasRestoredDraft] = useState(false);
  const hasTrackedFormStart = useRef(false);
  const hasTrackedFormAbandon = useRef(false);
  const hasSubmitted = useRef(false);
  const isSubmitting = useRef(false);
  const activeStepRef = useRef(activeStep);
  const completedSteps = useRef(new Set<number>());
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);
  const experimentContextRef = useRef<ConversionExperimentContext | null>(null);
  const intakeAttemptIdRef = useRef(createIntakeAttemptId());
  const confirmedAddressCaptureSignatureRef = useRef<string | null>(null);
  const addressCaptureInFlightRef = useRef(new Map<string, number>());
  const addressMetaLeadTrackedRef = useRef(false);
  const latestValuesRef = useRef(values);
  const captureAddressOnlyLeadRef = useRef<
    (snapshot: FormValues, options?: AddressCaptureOptions) => void
  >(() => undefined);

  useEffect(() => {
    activeStepRef.current = activeStep;
  }, [activeStep]);

  useEffect(() => {
    latestValuesRef.current = values;
  }, [values]);

  useEffect(() => {
    void getConversionExperimentContext(apiBaseUrl).then((experiment) => {
      experimentContextRef.current = experiment;
    });
  }, [apiBaseUrl]);

  useEffect(() => {
    try {
      const queryAddress = new URLSearchParams(window.location.search).get("address")?.trim() ?? "";
      const preferredAddress = initialAddress || queryAddress;
      const savedConfirmation = parseStoredValue<Confirmation>(confirmationStorageKey);
      if (savedConfirmation) {
        setConfirmation(savedConfirmation);
        hasSubmitted.current = true;
        setHasRestoredDraft(true);
        return;
      }

      const draft = parseStoredValue<StoredDraft>(draftStorageKey);
      if (draft) {
        if (isIntakeAttemptId(draft.intakeAttemptId)) {
          intakeAttemptIdRef.current = draft.intakeAttemptId;
        }
        const restoredValues = { ...draft.values } as Partial<FormValues> & {
          consent_to_contact?: boolean;
          sms_consent?: boolean;
        };
        delete restoredValues.consent_to_contact;
        delete restoredValues.sms_consent;
        delete (restoredValues as Partial<FormValues> & { preferred_contact_method?: string })
          .preferred_contact_method;
        setValues((current) => ({
          ...current,
          ...restoredValues,
          property_address: preferredAddress || draft.values.property_address || "",
        }));
        setActiveStep(Math.min(Math.max(draft.activeStep, 0), steps.length - 1));
        hasTrackedFormStart.current = true;
        void recordConversionEvent(apiBaseUrl, "form_restore", {
          restored_step: Math.min(Math.max(draft.activeStep + 1, 1), steps.length),
        });
      } else if (preferredAddress) {
        setValues((current) => ({ ...current, property_address: preferredAddress }));
      }
    } finally {
      setHasRestoredDraft(true);
    }
  }, [apiBaseUrl, initialAddress]);

  useEffect(() => {
    if (!hasRestoredDraft || confirmation) return;
    try {
      window.sessionStorage.setItem(
        draftStorageKey,
        JSON.stringify({
          values,
          activeStep,
          intakeAttemptId: intakeAttemptIdRef.current,
          savedAt: Date.now(),
        }),
      );
    } catch {
      // The form remains fully usable when storage is unavailable.
    }
  }, [activeStep, confirmation, hasRestoredDraft, values]);

  const captureAddressOnlyLead = useCallback(
    async (snapshot: FormValues, options: AddressCaptureOptions = {}) => {
      if (Object.keys(validateStep(0, snapshot)).length) return;
      const intakeAttemptId = intakeAttemptIdRef.current;
      const signature = JSON.stringify([
        intakeAttemptId,
        snapshot.property_address.trim().toLowerCase(),
        snapshot.property_city.trim().toLowerCase(),
        snapshot.property_state.trim().toUpperCase(),
        snapshot.property_postal_code.trim(),
      ]);
      if (confirmedAddressCaptureSignatureRef.current === signature) return;

      const inFlightCount = addressCaptureInFlightRef.current.get(signature) ?? 0;
      if (inFlightCount > 0 && !options.retryIfInFlight) return;
      addressCaptureInFlightRef.current.set(signature, inFlightCount + 1);

      const experiment = experimentContextRef.current;
      const initialMetaBrowserEvent = createMetaBrowserEvent(
        addressLeadEventId(intakeAttemptId),
      );
      const sendAddressCapture = (metaBrowserEvent: typeof initialMetaBrowserEvent) =>
        fetch(`${apiBaseUrl}/api/v1/public/seller-leads/address-capture`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          keepalive: true,
          body: JSON.stringify({
            intake_attempt_id: intakeAttemptId,
            property_address: snapshot.property_address.trim(),
            property_city: snapshot.property_city.trim(),
            property_state: snapshot.property_state.trim().toUpperCase(),
            property_postal_code: snapshot.property_postal_code.trim(),
            company_website: snapshot.company_website,
            conversion_session_id: getConversionSessionId(),
            experiment_key: experiment?.experiment_key ?? null,
            experiment_variant: experiment?.experiment_variant ?? null,
            device_category: getDeviceCategory(),
            attribution: getConversionAttribution(),
            meta_browser_event: metaBrowserEvent,
          }),
        });
      const initialAddressCaptureRequest = sendAddressCapture(initialMetaBrowserEvent);
      const strongestMetaBrowserEventPromise = waitForMetaBrowserCookies(
        initialMetaBrowserEvent,
      );

      try {
        // Persist immediately with every identifier already available. Cookie polling continues
        // in parallel and is used by the retry/browser event without delaying this request.
        let response: Response | null = null;
        try {
          response = await initialAddressCaptureRequest;
        } catch {
          // A single enriched retry below recovers a transient or interrupted first request.
        }

        if (!response?.ok && options.retryWithEnrichedCookies !== false) {
          const strongestMetaBrowserEvent = await strongestMetaBrowserEventPromise;
          try {
            response = await sendAddressCapture(strongestMetaBrowserEvent);
          } catch {
            // A later visibility/page-exit fallback can retry this deterministic intake attempt.
          }
        }
        if (!response?.ok) throw new Error("Address capture was not accepted.");
        if (intakeAttemptIdRef.current !== intakeAttemptId) return;

        confirmedAddressCaptureSignatureRef.current = signature;
        const strongestMetaBrowserEvent = await strongestMetaBrowserEventPromise;
        if (!addressMetaLeadTrackedRef.current) {
          addressMetaLeadTrackedRef.current = trackMetaPixelEvent(
            "Lead",
            strongestMetaBrowserEvent.event_id,
          );
        }
      } catch {
        // Unconfirmed captures stay retryable; deterministic IDs keep retries idempotent.
      } finally {
        const remaining = (addressCaptureInFlightRef.current.get(signature) ?? 1) - 1;
        if (remaining > 0) addressCaptureInFlightRef.current.set(signature, remaining);
        else addressCaptureInFlightRef.current.delete(signature);
      }
    },
    [apiBaseUrl],
  );

  useEffect(() => {
    captureAddressOnlyLeadRef.current = (snapshot, options) => {
      void captureAddressOnlyLead(snapshot, options);
    };
  }, [captureAddressOnlyLead]);

  useEffect(() => {
    if (!hasRestoredDraft || confirmation || activeStep === 0) return;
    void captureAddressOnlyLead(values);
  }, [activeStep, captureAddressOnlyLead, confirmation, hasRestoredDraft, values]);

  useEffect(() => {
    function retryAddressCaptureOnExit() {
      if (hasSubmitted.current) return;
      captureAddressOnlyLeadRef.current(latestValuesRef.current, {
        retryIfInFlight: true,
        retryWithEnrichedCookies: false,
      });
    }

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
      if (document.visibilityState === "hidden") {
        retryAddressCaptureOnExit();
        trackAbandonment();
      }
    }

    function handlePageExit() {
      retryAddressCaptureOnExit();
      trackAbandonment();
    }

    window.addEventListener("beforeunload", handlePageExit);
    window.addEventListener("pagehide", handlePageExit);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("beforeunload", handlePageExit);
      window.removeEventListener("pagehide", handlePageExit);
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
    if (errors[name]) {
      setErrors((current) => ({ ...current, [name]: undefined }));
    }
  }

  function updateAddress(address: PropertyAddressValue) {
    handleFormStart();
    setValues((current) => ({
      ...current,
      property_address: address.street_address,
      property_city: address.city,
      property_state: address.state,
      property_postal_code: address.postal_code,
    }));
    setErrors((current) => ({
      ...current,
      property_address: undefined,
      property_city: undefined,
      property_state: undefined,
      property_postal_code: undefined,
    }));
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
    if (activeStep === 0) {
      void captureAddressOnlyLead(values);
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

    const experiment = experimentContextRef.current;
    const metaBrowserEvent = await waitForMetaBrowserCookies(
      createMetaBrowserEvent(contactEventId(intakeAttemptIdRef.current)),
    );
    const payload = {
      intake_attempt_id: intakeAttemptIdRef.current,
      property_address: values.property_address.trim(),
      property_city: values.property_city.trim(),
      property_state: values.property_state.trim().toUpperCase(),
      property_postal_code: values.property_postal_code.trim(),
      property_type: null,
      property_condition: null,
      occupancy_status: null,
      name: values.name.trim(),
      phone: values.phone.trim() || null,
      email: values.email.trim() || null,
      preferred_contact_method: "phone",
      reason_for_selling: null,
      desired_timeline: null,
      asking_price: null,
      mortgage_balance: null,
      comments: null,
      consent_to_contact: true,
      consent_wording_version: "seller-contact-web-v3",
      sms_consent: smsConsent,
      sms_consent_wording_version: "seller-sms-web-v3",
      company_website: values.company_website,
      conversion_session_id: getConversionSessionId(),
      experiment_key: experiment?.experiment_key ?? null,
      experiment_variant: experiment?.experiment_variant ?? null,
      device_category: getDeviceCategory(),
      attribution: getConversionAttribution(),
      meta_browser_event: metaBrowserEvent,
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
        enrichment_token?: string;
        enrichment_expires_at?: string;
        message?: string;
        meta_pixel_event_name?: "Lead" | "Contact";
      };
      const nextConfirmation: Confirmation = {
        message:
          result.message ??
          "Thanks. Your request was received. The Stonegate team will review the property and available options next.",
        reference: result.lead_id.slice(0, 8).toUpperCase(),
        matchedExistingLead: result.matched_existing_lead,
        submittedAt: new Date().toISOString(),
        enrichmentToken: result.enrichment_token,
        enrichmentExpiresAt: result.enrichment_expires_at,
        enriched: false,
      };
      hasSubmitted.current = true;
      const metaPixelEventName = result.meta_pixel_event_name ?? "Lead";
      if (metaPixelEventName === "Contact" && !addressMetaLeadTrackedRef.current) {
        addressMetaLeadTrackedRef.current = trackMetaPixelEvent(
          "Lead",
          addressLeadEventId(intakeAttemptIdRef.current),
        );
      }
      trackMetaPixelEvent(metaPixelEventName, metaBrowserEvent.event_id);
      isSubmitting.current = false;
      setConfirmation(nextConfirmation);
      setSubmitState({ status: "idle", message: "" });
      try {
        window.sessionStorage.removeItem(draftStorageKey);
        storeConfirmation(nextConfirmation);
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

  function openEnrichment() {
    setIsEnrichmentOpen(true);
    setEnrichmentState({ status: "idle", message: "" });
    void recordConversionEvent(apiBaseUrl, "form_enrichment_start", {
      form: "cash_offer",
      request_reference: confirmation?.reference,
    });
    window.requestAnimationFrame(() => document.getElementById("desired_timeline")?.focus());
  }

  async function handleEnrichmentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!confirmation?.enrichmentToken || enrichmentState.status === "submitting") return;

    const nextErrors = validateEnrichment(values);
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      const firstField = Object.keys(nextErrors)[0];
      window.requestAnimationFrame(() => document.getElementById(firstField)?.focus());
      return;
    }
    if (!hasOptionalDetails(values)) {
      setEnrichmentState({
        status: "error",
        message: "Add at least one detail, or choose Skip for now.",
      });
      return;
    }

    setEnrichmentState({ status: "submitting", message: "Adding property details..." });
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/public/seller-leads/enrichment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enrichment_token: confirmation.enrichmentToken,
          property_type: values.property_type || null,
          property_condition: values.property_condition || null,
          occupancy_status: values.occupancy_status || null,
          reason_for_selling: values.reason_for_selling || null,
          desired_timeline: values.desired_timeline || null,
          asking_price: values.asking_price.trim() || null,
          mortgage_balance: values.mortgage_balance.trim() || null,
          comments: values.comments.trim() || null,
          conversion_session_id: getConversionSessionId(),
        }),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const error = new Error(
          extractApiError(errorPayload) ?? "The additional details could not be saved.",
        );
        Object.assign(error, { status: response.status });
        throw error;
      }

      const result = (await response.json()) as { message?: string };
      const updatedConfirmation = { ...confirmation, enriched: true };
      setConfirmation(updatedConfirmation);
      storeConfirmation(updatedConfirmation);
      setIsEnrichmentOpen(false);
      setErrors({});
      setEnrichmentState({
        status: "success",
        message: result.message ?? "The additional property details were added.",
      });
    } catch (caught) {
      setEnrichmentState({
        status: "error",
        message:
          caught instanceof Error && caught.message
            ? caught.message
            : "The details were not saved. Try again, or skip this optional step.",
      });
    }
  }

  function startAnotherProperty() {
    hasSubmitted.current = false;
    isSubmitting.current = false;
    hasTrackedFormStart.current = false;
    hasTrackedFormAbandon.current = false;
    completedSteps.current.clear();
    intakeAttemptIdRef.current = createIntakeAttemptId();
    confirmedAddressCaptureSignatureRef.current = null;
    addressCaptureInFlightRef.current.clear();
    addressMetaLeadTrackedRef.current = false;
    setValues(initialValues);
    setSmsConsent(false);
    setActiveStep(0);
    setErrors({});
    setConfirmation(null);
    setIsEnrichmentOpen(false);
    setEnrichmentState({ status: "idle", message: "" });
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
    const canEnrich =
      Boolean(confirmation.enrichmentToken) &&
      !confirmation.enriched;
    return (
      <section className={styles.confirmation} id="cash-offer-form">
        <div className={styles.confirmationStatus} role="status" aria-live="polite">
          <CircleCheck size={34} aria-hidden="true" />
          <p className={styles.eyebrow}>Request received</p>
          <h2>Thanks. Stonegate has your property request.</h2>
          <p>{confirmation.message}</p>
          <p className={styles.reference}>
            Request reference: <strong>{confirmation.reference}</strong>
          </p>
          {confirmation.matchedExistingLead ? (
            <p className={styles.existingNotice}>
              We matched this request to your existing property record and kept the updated details
              together instead of creating a duplicate lead.
            </p>
          ) : null}
        </div>

        <div className={styles.nextSteps}>
          <div><strong>1. Review</strong><span>We check the property and local market.</span></div>
          <div><strong>2. Understand</strong><span>A real person contacts you to learn what matters most.</span></div>
          <div><strong>3. Compare</strong><span>We explain the available paths so you can decide.</span></div>
        </div>

        {canEnrich ? (
          <div className={styles.enrichmentBand}>
            {!isEnrichmentOpen ? (
              <>
                <div>
                  <ClipboardPenLine size={22} aria-hidden="true" />
                  <span>
                    <strong>Optional: help us prepare</strong>
                    Add condition, timing, or price details now. Your request is already submitted.
                  </span>
                </div>
                <button className={styles.secondaryButton} type="button" onClick={openEnrichment}>
                  Add property details
                </button>
              </>
            ) : (
              <EnrichmentForm
                values={values}
                errors={errors}
                state={enrichmentState}
                updateValue={updateValue}
                onSubmit={handleEnrichmentSubmit}
                onSkip={() => {
                  setIsEnrichmentOpen(false);
                  setErrors({});
                  setEnrichmentState({ status: "idle", message: "" });
                }}
              />
            )}
          </div>
        ) : null}

        {enrichmentState.status === "success" ? (
          <p className={styles.enrichmentSuccess} role="status">
            <Check size={16} aria-hidden="true" /> {enrichmentState.message}
          </p>
        ) : null}

        <div className={styles.confirmationActions}>
          <TrackedPhoneLink className={styles.secondaryButton} href={siteConfig.phoneHref}>
            Call Stonegate
          </TrackedPhoneLink>
          <TrackedEmailLink
            className={styles.secondaryButton}
            href={`${siteConfig.publicEmailHref}?subject=Property%20inquiry%20${confirmation.reference}`}
            metadata={{ placement: "offer_confirmation" }}
          >
            <Mail size={16} aria-hidden="true" /> Email Stonegate
          </TrackedEmailLink>
          <button className={styles.textButton} type="button" onClick={startAnotherProperty}>
            <RotateCcw size={16} aria-hidden="true" /> Submit another property
          </button>
        </div>
      </section>
    );
  }

  const step = steps[activeStep];
  const errorEntries = Object.entries(errors).filter(
    (entry): entry is [FieldName, string] => Boolean(entry[1]),
  );

  return (
    <form
      className={styles.form}
      id="cash-offer-form"
      noValidate
      onFocusCapture={handleFormStart}
      onSubmit={handleSubmit}
    >
      <label className={styles.visuallyHidden} aria-hidden="true">
        Company website
        <input
          name="company_website"
          autoComplete="off"
          tabIndex={-1}
          value={values.company_website}
          onChange={(event) => updateValue("company_website", event.target.value)}
        />
      </label>
      <div className={styles.progressHeader}>
        <div>
          <p className={styles.eyebrow}>Property review</p>
          <span>Step {activeStep + 1} of {steps.length}</span>
        </div>
        <progress
          max={steps.length}
          value={activeStep + 1}
          aria-label={`Step ${activeStep + 1} of ${steps.length}`}
        />
        <ol aria-label="Offer request progress">
          {steps.map((item, index) => (
            <li
              className={
                index === activeStep
                  ? styles.currentStep
                  : index < activeStep
                    ? styles.completedStep
                    : ""
              }
              key={item.key}
            >
              <button
                type="button"
                disabled={index > activeStep}
                onClick={() => moveToStep(index)}
                aria-current={index === activeStep ? "step" : undefined}
              >
                {index < activeStep ? (
                  <Check size={14} aria-hidden="true" />
                ) : (
                  <span>{index + 1}</span>
                )}
                {item.label}
              </button>
            </li>
          ))}
        </ol>
      </div>

      <div className={styles.stepIntro}>
        <p>{step.label} details</p>
        <h2 ref={stepHeadingRef} tabIndex={-1}>{step.title}</h2>
        <span>{stepDescription(step.key)}</span>
      </div>

      {errorEntries.length ? (
        <div className={styles.errorSummary} role="alert" aria-labelledby="form-error-title">
          <strong id="form-error-title">Check the highlighted information.</strong>
          <ul>
            {errorEntries.map(([field, message]) => (
              <li key={field}>
                <button
                  type="button"
                  onClick={() => document.getElementById(field)?.focus()}
                >
                  {message}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {activeStep === 0 ? (
        <fieldset className={styles.stepFields}>
          <legend className={styles.visuallyHidden}>Property location</legend>
          <PropertyAddressField
            apiBaseUrl={apiBaseUrl}
            value={{
              street_address: values.property_address,
              city: values.property_city,
              state: values.property_state,
              postal_code: values.property_postal_code,
            }}
            errors={{
              street_address: errors.property_address,
              city: errors.property_city,
              state: errors.property_state,
              postal_code: errors.property_postal_code,
            }}
            onChange={updateAddress}
            onStart={handleFormStart}
          />
        </fieldset>
      ) : null}

      {activeStep === 1 ? (
        <fieldset className={styles.stepFields}>
          <legend className={styles.visuallyHidden}>Contact details and consent</legend>
          <Field label="Your name" name="name" error={errors.name} required>
            <input
              id="name"
              name="name"
              autoCapitalize="words"
              autoComplete="section-contact name"
              enterKeyHint="next"
              required
              value={values.name}
              onChange={(event) => updateValue("name", event.target.value)}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? "name-error" : undefined}
              placeholder="Jane Seller"
            />
          </Field>
          <Field label="Phone" name="phone" error={errors.phone} required>
            <input
              id="phone"
              name="phone"
              type="tel"
              autoComplete="section-contact tel"
              enterKeyHint="next"
              inputMode="tel"
              required
              value={values.phone}
              onChange={(event) => updateValue("phone", event.target.value)}
              aria-invalid={Boolean(errors.phone)}
              aria-describedby={errors.phone ? "phone-error" : undefined}
              placeholder="404-555-0100"
            />
          </Field>
          <Field label="Email" name="email" error={errors.email} hint="Optional">
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="section-contact email"
              enterKeyHint="next"
              value={values.email}
              onChange={(event) => updateValue("email", event.target.value)}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? "email-hint email-error" : "email-hint"}
              placeholder="jane@example.com"
            />
          </Field>
          <p className={styles.consentDisclosure}>{consentWording}</p>
          <label className={styles.smsConsent}>
            <input
              id="sms_consent"
              name="sms_consent"
              type="checkbox"
              checked={smsConsent}
              onChange={(event) => {
                handleFormStart();
                setSmsConsent(event.target.checked);
              }}
            />
            <span className={styles.smsConsentCopy}>
              <strong>Text me about my property inquiry (optional)</strong>
              <small>
                By checking this optional box, I agree to receive recurring automated text messages
                from Stonegate Home Buyers about my property inquiry, appointments, and possible
                selling options at the number provided. Message frequency varies. Message and data
                rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition
                of purchase. See our <Link href="/terms">Terms &amp; Conditions</Link> and{" "}
                <Link href="/privacy-policy">Privacy Policy</Link>.
              </small>
            </span>
          </label>
        </fieldset>
      ) : null}

      <div className={styles.formActions}>
        {activeStep > 0 ? (
          <button className={styles.backButton} type="button" onClick={handleBack}>
            <ArrowLeft size={17} aria-hidden="true" /> Back
          </button>
        ) : (
          <span />
        )}
        <button
          className={styles.nextButton}
          disabled={submitState.status === "submitting"}
          type="submit"
        >
          {activeStep === steps.length - 1 ? (
            submitState.status === "submitting" ? "Sending request..." : "Request My Options Review"
          ) : (
            <>Continue <ArrowRight size={17} aria-hidden="true" /></>
          )}
        </button>
      </div>
      {submitState.message ? (
        <p className={styles[submitState.status]} role="status">{submitState.message}</p>
      ) : null}
    </form>
  );
}

function EnrichmentForm({
  values,
  errors,
  state,
  updateValue,
  onSubmit,
  onSkip,
}: {
  values: FormValues;
  errors: FieldErrors;
  state: EnrichmentState;
  updateValue: <Name extends FieldName>(name: Name, value: FormValues[Name]) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSkip: () => void;
}) {
  return (
    <form className={styles.enrichmentForm} noValidate onSubmit={onSubmit}>
      <div className={styles.enrichmentHeading}>
        <span>
          <strong>Help us prepare for the first conversation</strong>
          Everything below is optional. Add only what you already know.
        </span>
      </div>

      <Field label="When might you ideally like to sell?" name="desired_timeline" hint="Optional">
        <select
          id="desired_timeline"
          name="desired_timeline"
          value={values.desired_timeline}
          onChange={(event) => updateValue("desired_timeline", event.target.value)}
        >
          <option value="">Select if you have a timeline in mind</option>
          <option value="asap">As soon as possible</option>
          <option value="within_30_days">Within 30 days</option>
          <option value="within_one_to_three_months">Within one to three months</option>
          <option value="within_three_to_six_months">Within three to six months</option>
          <option value="exploring">I am only exploring my options</option>
        </select>
      </Field>

      <Field label="Property type" name="property_type" hint="Optional">
        <select
          id="property_type"
          name="property_type"
          value={values.property_type}
          onChange={(event) => updateValue("property_type", event.target.value)}
        >
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

      <div className={styles.gridTwo}>
        <Field label="Current condition" name="property_condition" hint="Optional">
          <select
            id="property_condition"
            name="property_condition"
            value={values.property_condition}
            onChange={(event) => updateValue("property_condition", event.target.value)}
          >
            <option value="">Select if known</option>
            {conditionOptions.map(([value, label]) => (
              <option value={value} key={value}>{label}</option>
            ))}
          </select>
        </Field>
        <Field label="Occupancy" name="occupancy_status" hint="Optional">
          <select
            id="occupancy_status"
            name="occupancy_status"
            value={values.occupancy_status}
            onChange={(event) => updateValue("occupancy_status", event.target.value)}
          >
            <option value="">Select if known</option>
            {occupancyOptions.map(([value, label]) => (
              <option value={value} key={value}>{label}</option>
            ))}
          </select>
        </Field>
      </div>

      <Field label="Main reason for considering a sale" name="reason_for_selling" hint="Optional">
        <select
          id="reason_for_selling"
          name="reason_for_selling"
          value={values.reason_for_selling}
          onChange={(event) => updateValue("reason_for_selling", event.target.value)}
        >
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

      <div className={styles.gridTwo}>
        <Field
          label="Price you would like to consider"
          name="asking_price"
          hint="Optional"
          error={errors.asking_price}
        >
          <div className={styles.moneyInput}>
            <span aria-hidden="true">$</span>
            <input
              id="asking_price"
              name="asking_price"
              inputMode="numeric"
              value={values.asking_price}
              onChange={(event) => updateValue("asking_price", event.target.value)}
              aria-invalid={Boolean(errors.asking_price)}
              aria-describedby={errors.asking_price ? "asking_price-error" : undefined}
              placeholder="200,000"
            />
          </div>
        </Field>
        <Field
          label="Estimated mortgage balance"
          name="mortgage_balance"
          hint="Optional"
          error={errors.mortgage_balance}
        >
          <div className={styles.moneyInput}>
            <span aria-hidden="true">$</span>
            <input
              id="mortgage_balance"
              name="mortgage_balance"
              inputMode="numeric"
              value={values.mortgage_balance}
              onChange={(event) => updateValue("mortgage_balance", event.target.value)}
              aria-invalid={Boolean(errors.mortgage_balance)}
              aria-describedby={errors.mortgage_balance ? "mortgage_balance-error" : undefined}
              placeholder="90,000"
            />
          </div>
        </Field>
      </div>

      <Field label="Repairs, access, ownership, or timing details" name="comments" hint="Optional">
        <textarea
          id="comments"
          name="comments"
          rows={4}
          maxLength={1000}
          value={values.comments}
          onChange={(event) => updateValue("comments", event.target.value)}
          placeholder="Share only what would help us understand the property or your situation."
        />
      </Field>
      <p className={styles.characterCount}>{values.comments.length} / 1000</p>

      {state.status === "error" ? (
        <p className={styles.error} role="alert">{state.message}</p>
      ) : null}
      <div className={styles.enrichmentActions}>
        <button className={styles.textButton} type="button" onClick={onSkip}>Skip for now</button>
        <button
          className={styles.nextButton}
          disabled={state.status === "submitting"}
          type="submit"
        >
          {state.status === "submitting" ? "Saving details..." : "Save property details"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  name,
  hint,
  error,
  required = false,
  children,
}: {
  label: string;
  name: FieldName;
  hint?: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={styles.field} htmlFor={name}>
      <span>
        <strong>{label}</strong>
        {required ? <span className={styles.visuallyHidden}> (required)</span> : null}
        {hint ? <small id={`${name}-hint`}>{hint}</small> : null}
      </span>
      {children}
      {error ? <p className={styles.fieldError} id={`${name}-error`}>{error}</p> : null}
    </label>
  );
}

function validateStep(step: number, values: FormValues): FieldErrors {
  const errors: FieldErrors = {};
  if (step === 0) {
    if (values.property_address.trim().length < 3) {
      errors.property_address = "Enter the property street address.";
    }
    if (!values.property_city.trim()) errors.property_city = "Enter the property city.";
    if (!/^[A-Za-z]{2}$/.test(values.property_state.trim())) {
      errors.property_state = "Enter a valid 2-letter state.";
    }
    if (!/^\d{5}(?:-\d{4})?$/.test(values.property_postal_code.trim())) {
      errors.property_postal_code = "Enter a valid 5-digit ZIP code.";
    }
  }
  if (step === 1) {
    if (!values.name.trim()) errors.name = "Enter your name.";
    if (!values.phone.trim()) {
      errors.phone = "Phone number is required.";
    } else if (
      values.phone.replace(/\D/g, "").length < 10 ||
      values.phone.replace(/\D/g, "").length > 15
    ) {
      errors.phone = "Enter a complete phone number.";
    }
    if (values.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) {
      errors.email = "Enter a valid email address.";
    }
  }
  return errors;
}

function validateEnrichment(values: FormValues): FieldErrors {
  const errors: FieldErrors = {};
  if (values.asking_price && !containsNumber(values.asking_price)) {
    errors.asking_price = "Enter a price using numbers, or leave it blank.";
  }
  if (values.mortgage_balance && !containsNumber(values.mortgage_balance)) {
    errors.mortgage_balance = "Enter a balance using numbers, or leave it blank.";
  }
  return errors;
}

function hasOptionalDetails(values: FormValues) {
  return [
    values.property_type,
    values.property_condition,
    values.occupancy_status,
    values.reason_for_selling,
    values.desired_timeline,
    values.asking_price,
    values.mortgage_balance,
    values.comments,
  ].some((value) => value.trim());
}

function containsNumber(value: string) {
  return /\d/.test(value) && !/[a-z]/i.test(value);
}

function stepDescription(key: (typeof steps)[number]["key"]) {
  if (key === "property") {
    return "Enter the address so we can identify the property and local market.";
  }
  return "Enter your name and phone number. Email and text-message permission are optional.";
}

function storeConfirmation(confirmation: Confirmation) {
  window.sessionStorage.setItem(
    confirmationStorageKey,
    JSON.stringify({
      ...confirmation,
      savedAt: Date.parse(confirmation.submittedAt),
    }),
  );
}

function createIntakeAttemptId() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    const value = character === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

function addressLeadEventId(intakeAttemptId: string) {
  return `stonegate-lead-${intakeAttemptId}`;
}

function contactEventId(intakeAttemptId: string) {
  return `stonegate-contact-${intakeAttemptId}`;
}

function isIntakeAttemptId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
  );
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
    return detail
      .map((item) =>
        item &&
        typeof item === "object" &&
        "msg" in item &&
        typeof item.msg === "string"
          ? item.msg.replace(/^Value error,\s*/i, "")
          : null,
      )
      .filter(Boolean)
      .join(" ");
  }
  return null;
}
