"use client";

import { useAuth } from "@clerk/nextjs";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "./sms-permission-control.module.css";

export type SmsPermissionRecord = {
  id: string;
  channel: string;
  status: string;
  source: string;
  wording_version: string;
  wording: string;
  normalized_address: string | null;
  captured_ip: string | null;
  created_at: string;
};

type LeadConsentResponse = {
  consent_records: SmsPermissionRecord[];
  contact_methods?: Array<{
    method_type: string;
    value: string;
    is_primary: boolean;
  }>;
};

type SmsPermissionControlProps = {
  leadId: string;
  initialRecords?: SmsPermissionRecord[];
  canManage?: boolean;
  disabled?: boolean;
  fallbackConsentStatus?: string;
  isSuppressed?: boolean;
  onSaved?: () => void | Promise<void>;
  phoneNumber?: string | null;
};

const sourceOptions = [
  ["phone_call", "Phone call"],
  ["in_person", "In person"],
  ["facebook", "Facebook opt-in or message with explicit SMS permission"],
  ["inbound_sms", "Explicit permission by text"],
  ["written_form", "Written form"],
  ["other", "Other documented source"],
] as const;

function labelize(value: string) {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function normalizeUsPhone(value: string | null) {
  if (!value) return null;
  const digits = value.replace(/\D/g, "");
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith("1")) return `+${digits}`;
  if (digits.length >= 11 && digits.length <= 15) return `+${digits}`;
  return null;
}

export function SmsPermissionControl({
  leadId,
  initialRecords,
  canManage = true,
  disabled = false,
  fallbackConsentStatus,
  isSuppressed = false,
  onSaved,
  phoneNumber,
}: SmsPermissionControlProps) {
  const contentKey = `${leadId}:${initialRecords?.[0]?.id ?? "load"}`;

  return (
    <SmsPermissionControlContent
      canManage={canManage}
      disabled={disabled}
      fallbackConsentStatus={fallbackConsentStatus}
      initialRecords={initialRecords}
      isSuppressed={isSuppressed}
      key={contentKey}
      leadId={leadId}
      onSaved={onSaved}
      phoneNumber={phoneNumber}
    />
  );
}

function SmsPermissionControlContent({
  leadId,
  initialRecords,
  canManage = true,
  disabled = false,
  fallbackConsentStatus,
  isSuppressed = false,
  onSaved,
  phoneNumber,
}: SmsPermissionControlProps) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [loadedRecords, setLoadedRecords] = useState<SmsPermissionRecord[]>([]);
  const [loadedPhoneNumber, setLoadedPhoneNumber] = useState<string | null>(null);
  const [savedRecords, setSavedRecords] = useState<SmsPermissionRecord[] | null>(null);
  const [loading, setLoading] = useState(initialRecords === undefined);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );

  useEffect(() => {
    if (initialRecords !== undefined) return;
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}`, {
          headers: await authHeaders(getToken, devUserEmail),
          cache: "no-store",
        });
        if (!response.ok) throw new Error("SMS permission could not be loaded.");
        const payload = (await response.json()) as LeadConsentResponse;
        if (active) {
          setLoadedRecords(payload.consent_records);
          setLoadedPhoneNumber(
            payload.contact_methods?.find(
              (method) => method.method_type === "phone" && method.is_primary,
            )?.value ??
              payload.contact_methods?.find((method) => method.method_type === "phone")?.value ??
              null,
          );
        }
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "SMS permission could not be loaded.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, devUserEmail, getToken, initialRecords, leadId]);

  const records = savedRecords ?? initialRecords ?? loadedRecords;
  const currentPhoneNumber = phoneNumber ?? loadedPhoneNumber;
  const normalizedCurrentNumber = normalizeUsPhone(currentPhoneNumber);
  const smsRecords = records.filter((record) => record.channel === "sms");
  const hasSmsRecords = smsRecords.length > 0;
  const latest =
    smsRecords.find(
      (record) =>
        !record.normalized_address || record.normalized_address === normalizedCurrentNumber,
    ) ?? null;
  const recordMatchesCurrentNumber = Boolean(latest);
  const currentStatus =
    fallbackConsentStatus ?? (recordMatchesCurrentNumber ? latest?.status : undefined) ?? "missing";
  const isPermissioned = currentStatus === "granted" && !isSuppressed;
  const isCarrierRevoked =
    isSuppressed ||
    (recordMatchesCurrentNumber &&
      latest?.status === "revoked" &&
      latest.source === "twilio_advanced_opt_out");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/sms-permission`, {
        method: "PATCH",
        headers: await authHeaders(getToken, devUserEmail, true),
        body: JSON.stringify({
          status: String(formData.get("status") ?? "revoked"),
          source: String(formData.get("source") ?? "other"),
          evidence_note: String(formData.get("evidence_note") ?? "").trim(),
        }),
      });
      const payload = (await response.json().catch(() => null)) as
        | LeadConsentResponse
        | { detail?: string }
        | null;
      if (!response.ok) {
        throw new Error(
          payload && "detail" in payload && payload.detail
            ? payload.detail
            : "SMS permission could not be saved.",
        );
      }
      setSavedRecords((payload as LeadConsentResponse).consent_records);
      setMessage("SMS permission updated.");
      form.closest("details")?.removeAttribute("open");
      router.refresh();
      await onSaved?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "SMS permission could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.control}>
      <div className={isPermissioned ? styles.permissioned : styles.notPermissioned}>
        {isPermissioned ? (
          <ShieldCheck aria-hidden="true" size={15} />
        ) : (
          <ShieldAlert aria-hidden="true" size={15} />
        )}
        <span>
          <strong>
            SMS permission: {isPermissioned ? "Permissioned" : "Not permissioned"}
          </strong>
          <small>
            {loading
              ? "Checking permission history…"
              : isCarrierRevoked
                ? "Seller replied STOP"
                : latest?.status === currentStatus
                  ? `${labelize(latest.source)} · ${formatDate(latest.created_at)}`
                  : currentStatus === "missing"
                    ? hasSmsRecords && !recordMatchesCurrentNumber
                      ? "No SMS permission is recorded for the current number"
                      : "No SMS permission has been recorded"
                    : `Recorded status: ${labelize(currentStatus)}`}
          </small>
          {currentPhoneNumber ? <small>Number: {currentPhoneNumber}</small> : null}
        </span>
      </div>
      {isCarrierRevoked ? (
        <p className={styles.stopNotice}>Locked until the seller texts START from this number.</p>
      ) : null}
      {canManage && !disabled && !isCarrierRevoked ? (
        <details className={styles.editor}>
          <summary>Edit SMS permission</summary>
          <form onSubmit={handleSubmit}>
            <label>
              <span>Status</span>
              <select defaultValue={isPermissioned ? "granted" : "revoked"} name="status">
                <option value="granted">Permissioned</option>
                <option value="revoked">Not permissioned</option>
              </select>
            </label>
            <label>
              <span>Where was this decision confirmed?</span>
              <select defaultValue="phone_call" name="source">
                {sourceOptions.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            {currentPhoneNumber ? (
              <p className={styles.numberNotice}>
                This entry applies to the current primary number: {currentPhoneNumber}
              </p>
            ) : null}
            <label>
              <span>Evidence note</span>
              <textarea
                maxLength={500}
                minLength={3}
                name="evidence_note"
                placeholder="Example: Seller said we may text during today's intake call."
                required
                rows={3}
              />
            </label>
            <button disabled={saving} type="submit">
              {saving ? "Saving…" : "Save SMS permission"}
            </button>
          </form>
        </details>
      ) : null}
      {message ? <p className={styles.success} role="status">{message}</p> : null}
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
    </div>
  );
}

async function authHeaders(
  getToken: () => Promise<string | null>,
  devUserEmail: string,
  json = false,
) {
  const token = await getToken().catch(() => null);
  const headers: Record<string, string> = {};
  if (json) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  else headers["X-Dev-User-Email"] = devUserEmail;
  return headers;
}
