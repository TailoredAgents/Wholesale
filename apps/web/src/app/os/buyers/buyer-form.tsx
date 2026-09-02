"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type {
  BuyerDuplicateMatch,
  BuyerDuplicatePreflight,
  BuyerListItem,
  BuyerRelationshipOwner,
} from "../../lib/api";
import { labelize } from "../os-utils";
import formStyles from "../page.module.css";
import styles from "./buyers.module.css";

type SaveStatus = "idle" | "checking" | "saving" | "error";

type BuyerFormProps = {
  buyer?: BuyerListItem | null;
  compact?: boolean;
  onCancel?: () => void;
  onSaved?: (buyer: BuyerListItem) => void;
  onUseExisting?: (buyerId: string) => void;
  relationshipOwners: BuyerRelationshipOwner[];
  sourceOptions: string[];
};

type BuyerPayload = Record<string, unknown>;

function formString(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

function optionalString(formData: FormData, key: string) {
  return formString(formData, key) || null;
}

function dateTimeInput(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function optionalDateTimeIso(formData: FormData, key: string) {
  const value = formString(formData, key);
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

async function responseError(response: Response) {
  const fallback = `Stonegate could not save this buyer (HTTP ${response.status}).`;
  try {
    const payload = (await response.json()) as {
      detail?: string | { message?: string; matches?: BuyerDuplicateMatch[] } | Array<{ msg?: string }>;
    };
    if (typeof payload.detail === "string") return { message: payload.detail, matches: [] as BuyerDuplicateMatch[] };
    if (Array.isArray(payload.detail)) {
      const messages = payload.detail.map((item) => item.msg).filter(Boolean);
      return { message: messages.join(" ") || fallback, matches: [] as BuyerDuplicateMatch[] };
    }
    return {
      message: payload.detail?.message || fallback,
      matches: payload.detail?.matches ?? [],
    };
  } catch {
    return { message: fallback, matches: [] as BuyerDuplicateMatch[] };
  }
}

export function BuyerForm({
  buyer,
  compact = false,
  onCancel,
  onSaved,
  onUseExisting,
  relationshipOwners,
  sourceOptions,
}: BuyerFormProps) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [duplicateMatches, setDuplicateMatches] = useState<BuyerDuplicateMatch[]>([]);
  const [pendingPayload, setPendingPayload] = useState<BuyerPayload | null>(null);
  const [separateReason, setSeparateReason] = useState("");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const availableSources = useMemo(
    () => Array.from(new Set(["manual", ...sourceOptions, buyer?.source_key].filter(Boolean) as string[])),
    [buyer?.source_key, sourceOptions],
  );

  async function getHeaders() {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com";
    return headers;
  }

  function payloadFromForm(form: HTMLFormElement): BuyerPayload | null {
    const data = new FormData(form);
    const name = formString(data, "name");
    const email = optionalString(data, "email");
    const phone = optionalString(data, "phone");
    if (!name) {
      setError("Enter the buyer or company contact name.");
      return null;
    }
    if (!email && !phone) {
      setError("Enter at least one way to reach this buyer: a phone number or email address.");
      return null;
    }
    const phonePermission = formString(data, "phone_permission_action");
    const smsPermission = formString(data, "sms_permission_action");
    if (!phone && (phonePermission === "grant" || smsPermission === "grant")) {
      setError("Enter a phone number before recording call or text permission as granted.");
      return null;
    }
    const payload: BuyerPayload = {
      name,
      company_name: optionalString(data, "company_name"),
      email,
      phone,
      buyer_type: formString(data, "buyer_type"),
      status: formString(data, "status"),
      source_key: formString(data, "source_key") || "manual",
      source_detail: optionalString(data, "source_detail"),
      source_external_key: optionalString(data, "source_external_key"),
      relationship_owner_user_id: optionalString(data, "relationship_owner_user_id"),
      relationship_status: formString(data, "relationship_status") || "new",
      tier: formString(data, "tier") || "unclassified",
      temperature: formString(data, "temperature") || "unknown",
      tags: formString(data, "tags").split(",").map((tag) => tag.trim()).filter(Boolean),
      next_follow_up_at: optionalDateTimeIso(data, "next_follow_up_at"),
      last_verified_at: optionalDateTimeIso(data, "last_verified_at"),
      notes: optionalString(data, "notes"),
      permission_evidence_source: formString(data, "permission_evidence_source") || "buyer_crm_manual",
    };
    if (!buyer || phonePermission !== "preserve") {
      payload.phone_contact_permission = phonePermission === "grant";
    }
    if (!buyer || smsPermission !== "preserve") {
      payload.sms_consent = smsPermission === "grant";
    }
    return payload;
  }

  async function save(payload: BuyerPayload, allowSeparate = false) {
    setStatus("saving");
    setError(null);
    const url = buyer
      ? `${apiBaseUrl}/api/v1/buyers/${buyer.id}`
      : `${apiBaseUrl}/api/v1/buyers`;
    const response = await fetch(url, {
      method: buyer ? "PATCH" : "POST",
      headers: await getHeaders(),
      body: JSON.stringify({
        ...payload,
        allow_separate_record: allowSeparate,
        separate_record_reason: allowSeparate ? separateReason.trim() : null,
      }),
    });
    if (!response.ok) {
      const failure = await responseError(response);
      if (failure.matches.length) {
        setDuplicateMatches(failure.matches);
        setPendingPayload(payload);
      }
      setError(failure.message);
      setStatus("error");
      return;
    }
    const saved = (await response.json()) as BuyerListItem;
    setStatus("idle");
    setDuplicateMatches([]);
    router.refresh();
    onSaved?.(saved);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "checking" || status === "saving") return;
    const payload = payloadFromForm(event.currentTarget);
    if (!payload) return;
    if (
      payload.status === "do_not_contact" &&
      buyer?.status !== "do_not_contact" &&
      !window.confirm("Mark this buyer Do not contact? This removes them from active matching and outreach.")
    ) return;
    setError(null);
    setDuplicateMatches([]);
    setSeparateReason("");
    setPendingPayload(payload);
    setStatus("checking");
    const response = await fetch(`${apiBaseUrl}/api/v1/buyers/duplicates/preflight`, {
      method: "POST",
      headers: await getHeaders(),
      body: JSON.stringify({
        email: payload.email,
        phone: payload.phone,
        company_name: payload.company_name,
        exclude_buyer_id: buyer?.id ?? null,
      }),
    });
    if (!response.ok) {
      const failure = await responseError(response);
      setError(failure.message);
      setStatus("error");
      return;
    }
    const preflight = (await response.json()) as BuyerDuplicatePreflight;
    if (preflight.has_matches) {
      setDuplicateMatches(preflight.matches);
      setStatus("idle");
      return;
    }
    await save(payload);
  }

  return (
    <form className={formStyles.buyerForm} onSubmit={handleSubmit}>
      <div className={styles.formIntro}>
        <strong>{buyer ? "Update the relationship record" : compact ? "Quick add this investor" : "Start in Needs review"}</strong>
        <p>{buyer ? "Identity and relationship changes are audited." : compact ? "Enter the contact information you have now. Buying criteria and relationship details can be completed later." : "Add the relationship first, then verify each House or Land buy box before matching."}</p>
      </div>
      <label><span>Buyer name</span><input defaultValue={buyer?.name} name="name" maxLength={255} placeholder="Jordan Smith" required /></label>
      <label><span>Company</span><input defaultValue={buyer?.company_name ?? ""} name="company_name" maxLength={255} placeholder="Smith Investments" /></label>
      <div className={formStyles.formGrid}>
        <label><span>Email</span><input defaultValue={buyer?.email ?? ""} name="email" maxLength={255} placeholder="buyer@example.com" type="email" /></label>
        <label><span>Phone</span><input autoComplete="tel" defaultValue={buyer?.phone ?? ""} inputMode="tel" name="phone" maxLength={80} placeholder="404-555-0101" /></label>
      </div>
      <p className={styles.fieldHint}>A phone number or email address is required.</p>
      <fieldset className={styles.permissionFields}>
        <legend>Contact permission</legend>
        <label><span>Phone calls</span><select defaultValue={buyer ? "preserve" : "not_recorded"} name="phone_permission_action">{buyer ? <option value="preserve">Keep current: {labelize(buyer.phone_permission.status)}</option> : <option value="not_recorded">Not recorded</option>}<option value="grant">Record permission granted</option>{buyer ? <option value="revoke">Record permission not granted</option> : null}</select></label>
        <label><span>Text messages</span><select defaultValue={buyer ? "preserve" : "not_recorded"} name="sms_permission_action">{buyer ? <option value="preserve">Keep current: {labelize(buyer.sms_permission.status)}</option> : <option value="not_recorded">Not recorded</option>}<option value="grant">Record permission granted</option>{buyer ? <option value="revoke">Record permission not granted</option> : null}</select></label>
        <label><span>Permission source</span><select defaultValue={buyer?.phone_permission.source ?? buyer?.sms_permission.source ?? "buyer_crm_manual"} name="permission_evidence_source"><option value="buyer_crm_manual">Recorded manually in Buyer CRM</option><option value="written_form">Written form</option><option value="phone_call">Phone conversation</option><option value="in_person">In person</option><option value="provider_import">Imported provider evidence</option></select></label>
      </fieldset>
      {compact && !buyer ? <>
        <input name="buyer_type" type="hidden" value="cash_buyer" />
        <input name="status" type="hidden" value="needs_review" />
        <input name="relationship_status" type="hidden" value="new" />
        <input name="tier" type="hidden" value="unclassified" />
        <input name="temperature" type="hidden" value="unknown" />
        <input name="source_key" type="hidden" value="manual" />
        <label><span>Quick note</span><textarea name="notes" maxLength={2000} placeholder="What do you know about this investor?" rows={2} /></label>
      </> : <>
      <div className={formStyles.formGrid}>
        <label><span>Type</span><select defaultValue={buyer?.buyer_type ?? "cash_buyer"} name="buyer_type"><option value="cash_buyer">Cash buyer</option><option value="landlord">Landlord</option><option value="flipper">Flipper</option><option value="builder">Builder</option><option value="hedge_fund">Fund</option><option value="agent">Agent</option></select></label>
        {buyer ? <label><span>Status</span><select defaultValue={buyer.status === "archived" ? "needs_review" : buyer.status} name="status"><option value="needs_review">Needs review</option><option value="active">Active</option><option value="paused">Paused</option><option value="do_not_contact">Do not contact</option></select></label> : <label><span>Status</span><input aria-describedby="new-buyer-status-help" readOnly value="Needs review" /><input name="status" type="hidden" value="needs_review" /><small id="new-buyer-status-help">Activate after verifying the buyer.</small></label>}
      </div>
      <label><span>Relationship</span><select defaultValue={buyer?.relationship_status ?? "new"} name="relationship_status"><option value="new">New</option><option value="active">Active</option><option value="nurture">Nurture</option><option value="paused">Paused</option><option value="do_not_contact">Do not contact</option><option value="inactive">Inactive</option></select></label>
      <div className={formStyles.formGrid}>
        <label><span>Tier</span><select defaultValue={buyer?.tier ?? "unclassified"} name="tier"><option value="unclassified">Unclassified</option><option value="a">A - proven priority buyer</option><option value="b">B - qualified buyer</option><option value="c">C - developing relationship</option></select></label>
        <label><span>Temperature</span><select defaultValue={buyer?.temperature ?? "unknown"} name="temperature"><option value="unknown">Unknown</option><option value="cold">Cold</option><option value="warm">Warm</option><option value="hot">Hot</option></select></label>
      </div>
      <label><span>Tags</span><input defaultValue={buyer?.tags?.join(", ") ?? ""} name="tags" placeholder="land developer, fast close, north Georgia" /><small>Separate tags with commas.</small></label>
      <div className={formStyles.formGrid}>
        <label><span>Relationship owner</span><select defaultValue={buyer?.relationship_owner_user_id ?? ""} name="relationship_owner_user_id"><option value="">Unassigned</option>{relationshipOwners.map((owner) => <option key={owner.user_id} value={owner.user_id}>{owner.display_name} - {owner.email}</option>)}</select></label>
        <label><span>Last verified</span><input defaultValue={dateTimeInput(buyer?.last_verified_at)} name="last_verified_at" type="datetime-local" /></label>
      </div>
      <label><span>Next relationship follow-up</span><input defaultValue={dateTimeInput(buyer?.next_follow_up_at)} name="next_follow_up_at" type="datetime-local" /></label>
      <div className={formStyles.formGrid}>
        <label><span>Source</span><select defaultValue={buyer?.source_key ?? "manual"} name="source_key">{availableSources.map((source) => <option key={source} value={source}>{labelize(source)}</option>)}</select></label>
        <label><span>Source detail</span><input defaultValue={buyer?.source_detail ?? ""} name="source_detail" maxLength={255} placeholder="Alex's investor list" /></label>
      </div>
      <label><span>External source ID (optional)</span><input defaultValue={buyer?.source_external_key ?? ""} name="source_external_key" maxLength={255} placeholder="Original system record ID" /></label>
      <label><span>Buyer notes</span><textarea defaultValue={buyer?.notes ?? ""} name="notes" maxLength={2000} rows={3} /></label>
      </>}

      {duplicateMatches.length ? (
        <section aria-labelledby="duplicate-title" className={styles.duplicateReview}>
          <h3 id="duplicate-title">Possible buyer already exists</h3>
          <p>Using the existing relationship is safest. Only create a separate record when these are genuinely different buyers.</p>
          {duplicateMatches.map((match) => (
            <article key={match.buyer_id}>
              <div><strong>{match.name}</strong><span>{labelize(match.status)}</span></div>
              <p>{match.company_name ?? "Independent buyer"} - {match.phone ?? match.email ?? "No contact shown"}</p>
              <small>Matched: {match.matched_fields.map(labelize).join(", ")}</small>
              <button className={styles.safeAction} onClick={() => onUseExisting?.(match.buyer_id)} type="button">Use existing buyer</button>
            </article>
          ))}
          <label><span>Reason for a separate record</span><textarea onChange={(event) => setSeparateReason(event.target.value)} placeholder="Explain why this is a different buyer relationship" value={separateReason} /></label>
          <button className={styles.separateAction} disabled={!pendingPayload || separateReason.trim().length < 3 || status === "saving"} onClick={() => pendingPayload && void save(pendingPayload, true)} type="button">Create separate record</button>
        </section>
      ) : null}

      {error ? <p aria-live="polite" className={styles.formError}>{error}</p> : null}
      <div className={styles.formActions}>
        {onCancel ? <button className={styles.secondaryAction} onClick={onCancel} type="button">Cancel</button> : null}
        <button disabled={status === "checking" || status === "saving"} type="submit">{status === "checking" ? "Checking duplicates..." : status === "saving" ? "Saving..." : buyer ? "Save buyer" : compact ? "Add to outreach" : "Add buyer"}</button>
      </div>
      <span aria-live="polite" className={styles.srOnly}>{status === "checking" ? "Checking for duplicate buyers" : status === "saving" ? "Saving buyer" : ""}</span>
    </form>
  );
}
