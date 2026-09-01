"use client";

import { useAuth } from "@clerk/nextjs";
import { MessageSquareText, PhoneCall, ShieldAlert, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "./sms-permission-control.module.css";

type PermissionChannel = "phone" | "sms";
type PermissionStatus = "granted" | "revoked";

export type ContactPermissionRecord = {
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
  consent_records: ContactPermissionRecord[];
  contact_methods?: Array<{
    method_type: string;
    value: string;
    is_primary: boolean;
  }>;
};

type SmsPermissionControlProps = {
  leadId: string;
  initialRecords?: ContactPermissionRecord[];
  canManage?: boolean;
  canManagePhone?: boolean;
  canManageSms?: boolean;
  disabled?: boolean;
  fallbackConsentStatus?: string;
  fallbackPhoneConsentStatus?: string;
  isSuppressed?: boolean;
  isPhoneSuppressed?: boolean;
  onSaved?: () => void | Promise<void>;
  phoneNumber?: string | null;
};

const sourceOptions = [
  ["phone_call", "Phone conversation"],
  ["in_person", "In person"],
  ["facebook", "Facebook form or conversation"],
  ["inbound_sms", "Text conversation"],
  ["website_form", "Website form"],
  ["written_form", "Written form"],
  ["other", "Other confirmed source"],
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
  canManagePhone,
  canManageSms,
  disabled = false,
  fallbackConsentStatus,
  fallbackPhoneConsentStatus,
  isSuppressed = false,
  isPhoneSuppressed = false,
  onSaved,
  phoneNumber,
}: SmsPermissionControlProps) {
  const contentKey = `${leadId}:${initialRecords?.[0]?.id ?? "load"}`;

  return (
    <SmsPermissionControlContent
      canManage={canManage}
      canManagePhone={canManagePhone}
      canManageSms={canManageSms}
      disabled={disabled}
      fallbackConsentStatus={fallbackConsentStatus}
      fallbackPhoneConsentStatus={fallbackPhoneConsentStatus}
      initialRecords={initialRecords}
      isPhoneSuppressed={isPhoneSuppressed}
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
  canManagePhone,
  canManageSms,
  disabled = false,
  fallbackConsentStatus,
  fallbackPhoneConsentStatus,
  isSuppressed = false,
  isPhoneSuppressed = false,
  onSaved,
  phoneNumber,
}: SmsPermissionControlProps) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [loadedRecords, setLoadedRecords] = useState<ContactPermissionRecord[]>([]);
  const [loadedPhoneNumber, setLoadedPhoneNumber] = useState<string | null>(null);
  const [savedRecords, setSavedRecords] = useState<ContactPermissionRecord[] | null>(null);
  const [selectedChannel, setSelectedChannel] = useState<PermissionChannel>(
    canManagePhone === false && canManageSms !== false ? "sms" : "phone",
  );
  const [selectedStatus, setSelectedStatus] = useState<PermissionStatus>("granted");
  const [selectedSource, setSelectedSource] = useState("phone_call");
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
        if (!response.ok) throw new Error("Contact permissions could not be loaded.");
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
          setError(
            caught instanceof Error
              ? caught.message
              : "Contact permissions could not be loaded.",
          );
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
  const mayManagePhone = canManagePhone ?? canManage;
  const mayManageSms = canManageSms ?? canManage;

  function permissionState(
    channel: PermissionChannel,
    fallbackStatus: string | undefined,
    suppressed: boolean,
  ) {
    const channelRecords = records.filter((record) => record.channel === channel);
    const latest =
      channelRecords.find(
        (record) =>
          !record.normalized_address || record.normalized_address === normalizedCurrentNumber,
      ) ?? null;
    const status = fallbackStatus ?? latest?.status ?? "missing";
    return {
      latest,
      status,
      isPermissioned: status === "granted" && !suppressed,
      isSuppressed: suppressed,
      hasMismatchedRecord: channelRecords.length > 0 && !latest,
    };
  }

  const phonePermission = permissionState(
    "phone",
    fallbackPhoneConsentStatus,
    isPhoneSuppressed,
  );
  const smsPermission = permissionState("sms", fallbackConsentStatus, isSuppressed);
  const isCarrierRevoked =
    isSuppressed ||
    (smsPermission.latest?.status === "revoked" &&
      smsPermission.latest.source === "twilio_advanced_opt_out");
  const editableChannels = [
    ...(mayManagePhone && !disabled ? (["phone"] as const) : []),
    ...(mayManageSms && !disabled && !isCarrierRevoked ? (["sms"] as const) : []),
  ];

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/contact-permission`, {
        method: "PATCH",
        headers: await authHeaders(getToken, devUserEmail, true),
        body: JSON.stringify({
          channel: selectedChannel,
          status: selectedStatus,
          source: selectedSource,
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
            : "Contact permission could not be saved.",
        );
      }
      setSavedRecords((payload as LeadConsentResponse).consent_records);
      setMessage(`${selectedChannel === "phone" ? "Call" : "SMS"} permission updated.`);
      form.closest("details")?.removeAttribute("open");
      router.refresh();
      await onSaved?.();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Contact permission could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }

  function statusDetail(
    channel: PermissionChannel,
    permission: ReturnType<typeof permissionState>,
  ) {
    if (loading) return "Checking permission history…";
    if (permission.isSuppressed) {
      return channel === "sms" ? "Seller replied STOP" : "Phone number is suppressed";
    }
    if (permission.latest) {
      return `${labelize(permission.latest.source)} · ${formatDate(permission.latest.created_at)}`;
    }
    if (permission.hasMismatchedRecord) {
      return `No ${channel === "sms" ? "SMS" : "call"} permission for the current number`;
    }
    return `No ${channel === "sms" ? "SMS" : "call"} permission recorded`;
  }

  return (
    <div className={styles.control}>
      <div className={styles.permissionGrid}>
        <div
          className={phonePermission.isPermissioned ? styles.permissioned : styles.notPermissioned}
        >
          {phonePermission.isPermissioned ? (
            <ShieldCheck aria-hidden="true" size={15} />
          ) : (
            <ShieldAlert aria-hidden="true" size={15} />
          )}
          <span>
            <strong>
              Call permission: {phonePermission.isPermissioned ? "Permissioned" : "Not permissioned"}
            </strong>
            <small>{statusDetail("phone", phonePermission)}</small>
          </span>
          <PhoneCall aria-hidden="true" className={styles.channelIcon} size={14} />
        </div>
        <div className={smsPermission.isPermissioned ? styles.permissioned : styles.notPermissioned}>
          {smsPermission.isPermissioned ? (
            <ShieldCheck aria-hidden="true" size={15} />
          ) : (
            <ShieldAlert aria-hidden="true" size={15} />
          )}
          <span>
            <strong>
              SMS permission: {smsPermission.isPermissioned ? "Permissioned" : "Not permissioned"}
            </strong>
            <small>{statusDetail("sms", smsPermission)}</small>
          </span>
          <MessageSquareText aria-hidden="true" className={styles.channelIcon} size={14} />
        </div>
      </div>
      {currentPhoneNumber ? <p className={styles.numberNotice}>Number: {currentPhoneNumber}</p> : null}
      <p className={styles.advisoryNotice}>
        Permission labels are informational for manual CRM calls and one-to-one texts. A STOP,
        DNC, invalid number, or provider block still prevents contact.
      </p>
      {isCarrierRevoked ? (
        <p className={styles.stopNotice}>SMS is locked until the seller texts START from this number.</p>
      ) : null}
      {editableChannels.length > 0 ? (
        <details className={styles.editor}>
          <summary>Edit call or SMS permission</summary>
          <form onSubmit={handleSubmit}>
            <label>
              <span>Permission type</span>
              <select
                name="channel"
                onChange={(event) => {
                  setSelectedChannel(event.target.value as PermissionChannel);
                  setSelectedStatus("granted");
                  setMessage("");
                  setError("");
                }}
                value={selectedChannel}
              >
                {editableChannels.map((channel) => (
                  <option key={channel} value={channel}>
                    {channel === "phone" ? "Phone calls" : "Text messages (SMS)"}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Status</span>
              <select
                name="status"
                onChange={(event) => setSelectedStatus(event.target.value as PermissionStatus)}
                value={selectedStatus}
              >
                <option
                  disabled={selectedChannel === "phone" && phonePermission.isSuppressed}
                  value="granted"
                >
                  Permissioned
                </option>
                <option value="revoked">Not permissioned</option>
              </select>
            </label>
            <label>
              <span>Where was this confirmed?</span>
              <select
                name="source"
                onChange={(event) => setSelectedSource(event.target.value)}
                value={selectedSource}
              >
                {sourceOptions.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <p className={styles.auditNotice}>
              Stonegate records who changed this permission, when it changed, and the source selected above.
            </p>
            <button disabled={saving} type="submit">
              {saving ? "Saving…" : `Save ${selectedChannel === "phone" ? "call" : "SMS"} permission`}
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
