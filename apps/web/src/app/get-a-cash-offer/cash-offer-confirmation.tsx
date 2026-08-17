"use client";

import type { FormEvent, ReactNode } from "react";
import {
  Check,
  CircleCheck,
  ClipboardPenLine,
  Mail,
  RotateCcw,
} from "lucide-react";

import { siteConfig } from "../site-config";
import { TrackedEmailLink } from "../tracked-email-link";
import { TrackedPhoneLink } from "../tracked-phone-link";
import type {
  Confirmation,
  EnrichmentState,
  FieldErrors,
  FieldName,
  FormValues,
} from "./cash-offer-form";
import styles from "./page.module.css";

const conditionOptions = [
  ["move_in_ready", "Move-in ready"],
  ["minor_repairs", "Minor repairs"],
  ["major_repairs", "Major repairs"],
  ["full_renovation", "Full renovation"],
  ["not_sure", "Not sure"],
] as const;

const occupancyOptions = [
  ["owner_occupied", "Owner occupied"],
  ["tenant_occupied", "Tenant occupied"],
  ["vacant", "Vacant"],
  ["inherited_estate", "Inherited or estate"],
  ["other", "Other"],
] as const;

type CashOfferConfirmationProps = {
  confirmation: Confirmation;
  values: FormValues;
  errors: FieldErrors;
  enrichmentState: EnrichmentState;
  isEnrichmentOpen: boolean;
  onOpenEnrichment: () => void;
  onUpdateValue: <Name extends FieldName>(name: Name, value: FormValues[Name]) => void;
  onSubmitEnrichment: (event: FormEvent<HTMLFormElement>) => void;
  onSkipEnrichment: () => void;
  onStartAnotherProperty: () => void;
};

export function CashOfferConfirmation({
  confirmation,
  values,
  errors,
  enrichmentState,
  isEnrichmentOpen,
  onOpenEnrichment,
  onUpdateValue,
  onSubmitEnrichment,
  onSkipEnrichment,
  onStartAnotherProperty,
}: CashOfferConfirmationProps) {
  const canEnrich = Boolean(confirmation.enrichmentToken) && !confirmation.enriched;

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
              <button className={styles.secondaryButton} type="button" onClick={onOpenEnrichment}>
                Add property details
              </button>
            </>
          ) : (
            <EnrichmentForm
              values={values}
              errors={errors}
              state={enrichmentState}
              updateValue={onUpdateValue}
              onSubmit={onSubmitEnrichment}
              onSkip={onSkipEnrichment}
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
        <button className={styles.textButton} type="button" onClick={onStartAnotherProperty}>
          <RotateCcw size={16} aria-hidden="true" /> Submit another property
        </button>
      </div>
    </section>
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

      <EnrichmentField
        label="When might you ideally like to sell?"
        name="desired_timeline"
        hint="Optional"
      >
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
      </EnrichmentField>

      <EnrichmentField label="Property type" name="property_type" hint="Optional">
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
      </EnrichmentField>

      <div className={styles.gridTwo}>
        <EnrichmentField label="Current condition" name="property_condition" hint="Optional">
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
        </EnrichmentField>
        <EnrichmentField label="Occupancy" name="occupancy_status" hint="Optional">
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
        </EnrichmentField>
      </div>

      <EnrichmentField
        label="Main reason for considering a sale"
        name="reason_for_selling"
        hint="Optional"
      >
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
      </EnrichmentField>

      <div className={styles.gridTwo}>
        <EnrichmentField
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
        </EnrichmentField>
        <EnrichmentField
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
        </EnrichmentField>
      </div>

      <EnrichmentField
        label="Repairs, access, ownership, or timing details"
        name="comments"
        hint="Optional"
      >
        <textarea
          id="comments"
          name="comments"
          rows={4}
          maxLength={1000}
          value={values.comments}
          onChange={(event) => updateValue("comments", event.target.value)}
          placeholder="Share only what would help us understand the property or your situation."
        />
      </EnrichmentField>
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

function EnrichmentField({
  label,
  name,
  hint,
  error,
  children,
}: {
  label: string;
  name: FieldName;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className={styles.field} htmlFor={name}>
      <span>
        <strong>{label}</strong>
        {hint ? <small id={`${name}-hint`}>{hint}</small> : null}
      </span>
      {children}
      {error ? <p className={styles.fieldError} id={`${name}-error`}>{error}</p> : null}
    </label>
  );
}
