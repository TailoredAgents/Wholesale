"use client";

import { useAuth } from "@clerk/nextjs";
import { Plus, Trash2 } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { LeadDetail } from "../../lib/api";
import styles from "./page.module.css";

type Status = "idle" | "saving" | "saved" | "error";
type EditableContactMethod = {
  clientKey: string;
  id: string | null;
  method_type: "phone" | "email";
  value: string;
  is_primary: boolean;
};

const sources = [
  ["website", "Website"],
  ["google_ppc", "Google PPC"],
  ["facebook_ads", "Facebook ads"],
  ["instagram_ads", "Instagram ads"],
  ["meta_ads", "Meta ads"],
  ["referral", "Referral"],
  ["manual", "Manual"],
  ["driving_for_dollars", "Driving for dollars"],
  ["direct_mail", "Direct mail"],
];

const temperatures = [
  ["", "None"],
  ["hot", "Hot"],
  ["warm", "Warm"],
  ["cold", "Cold"],
];

const conditionOptions = [
  ["", "Unknown"],
  ["move_in_ready", "Move-in ready"],
  ["dated", "Dated"],
  ["needs_repairs", "Needs repairs"],
  ["major_repairs", "Major repairs"],
  ["tear_down", "Tear down"],
];

const occupancyOptions = [
  ["", "Unknown"],
  ["owner_occupied", "Owner occupied"],
  ["tenant_occupied", "Tenant occupied"],
  ["vacant", "Vacant"],
  ["unknown", "Unknown"],
];

const appointmentOptions = [
  ["", "None"],
  ["not_scheduled", "Not scheduled"],
  ["appointment_requested", "Appointment requested"],
  ["appointment_scheduled", "Appointment scheduled"],
  ["completed", "Completed"],
  ["no_show", "No show"],
];

function editableContactMethods(lead: LeadDetail): EditableContactMethod[] {
  return lead.contact_methods
    .filter((method) => method.method_type === "phone" || method.method_type === "email")
    .map((method) => ({
      clientKey: method.id,
      id: method.id,
      method_type: method.method_type as "phone" | "email",
      value: method.value,
      is_primary: method.is_primary,
    }));
}

function ensurePrimaryMethods(methods: EditableContactMethod[]) {
  return methods.map((method, index, all) => {
    const group = all.filter((item) => item.method_type === method.method_type);
    const groupHasPrimary = group.some((item) => item.is_primary);
    const isFirstInGroup = all.findIndex((item) => item.method_type === method.method_type) === index;
    return { ...method, is_primary: groupHasPrimary ? method.is_primary : isFirstInGroup };
  });
}

function formString(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

function optionalFormString(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value || null;
}

function optionalDateTime(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value ? new Date(value).toISOString() : null;
}

function dateTimeLocalValue(value: string | null) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export function LeadEditForm({ lead }: { lead: LeadDetail }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [contactMethods, setContactMethods] = useState<EditableContactMethod[]>(() =>
    ensurePrimaryMethods(editableContactMethods(lead)),
  );
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const sourceOptions = useMemo(() => {
    if (sources.some(([value]) => value === lead.source)) {
      return sources;
    }
    return [[lead.source, lead.source], ...sources];
  }, [lead.source]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const submittedMethods = contactMethods
      .map((method) => ({ ...method, value: method.value.trim() }))
      .filter((method) => method.value);
    if (submittedMethods.length === 0) {
      setErrorMessage("Keep at least one phone number or email address on the lead.");
      setStatus("error");
      return;
    }
    setStatus("saving");
    setErrorMessage("");

    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      } else {
        headers["X-Dev-User-Email"] = devUserEmail;
      }
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${lead.id}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({
          seller_name: formString(formData, "seller_name"),
          preferred_name: optionalFormString(formData, "preferred_name"),
          contact_methods: submittedMethods.map(({ id, method_type, value, is_primary }) => ({
            id,
            method_type,
            value,
            is_primary,
          })),
          assigned_user_id: optionalFormString(formData, "assigned_user_id"),
          property_street_address: formString(formData, "property_street_address"),
          property_city: formString(formData, "property_city"),
          property_state: formString(formData, "property_state"),
          property_postal_code: formString(formData, "property_postal_code"),
          property_county: optionalFormString(formData, "property_county"),
          property_type: optionalFormString(formData, "property_type"),
          source: formString(formData, "source"),
          lead_temperature: optionalFormString(formData, "lead_temperature"),
          motivation: optionalFormString(formData, "motivation"),
          desired_timeline: optionalFormString(formData, "desired_timeline"),
          property_condition: optionalFormString(formData, "property_condition"),
          occupancy_status: optionalFormString(formData, "occupancy_status"),
          asking_price: optionalFormString(formData, "asking_price"),
          mortgage_balance: optionalFormString(formData, "mortgage_balance"),
          appointment_status: optionalFormString(formData, "appointment_status"),
          next_follow_up_at: optionalDateTime(formData, "next_follow_up_at"),
          reason: optionalFormString(formData, "reason"),
        }),
      });

      const responsePayload = (await response.json().catch(() => null)) as
        | LeadDetail
        | { detail?: string }
        | null;
      if (!response.ok) {
        throw new Error(
          responsePayload && "detail" in responsePayload && responsePayload.detail
            ? responsePayload.detail
            : "Unable to update lead details.",
        );
      }

      const updatedLead = responsePayload as LeadDetail;
      setContactMethods(ensurePrimaryMethods(editableContactMethods(updatedLead)));
      setStatus("saved");
      router.refresh();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unable to update lead details.");
      setStatus("error");
    }
  }

  function addContactMethod(methodType: "phone" | "email") {
    setContactMethods((current) => [
      ...current,
      {
        clientKey: crypto.randomUUID(),
        id: null,
        method_type: methodType,
        value: "",
        is_primary: !current.some((method) => method.method_type === methodType),
      },
    ]);
    setStatus("idle");
  }

  function updateContactMethod(
    clientKey: string,
    updates: Partial<EditableContactMethod>,
  ) {
    setContactMethods((current) =>
      ensurePrimaryMethods(
        current.map((method) =>
          method.clientKey === clientKey ? { ...method, ...updates } : method,
        ),
      ),
    );
    setStatus("idle");
  }

  function makePrimary(clientKey: string, methodType: "phone" | "email") {
    setContactMethods((current) =>
      current.map((method) => ({
        ...method,
        is_primary:
          method.method_type === methodType ? method.clientKey === clientKey : method.is_primary,
      })),
    );
    setStatus("idle");
  }

  function removeContactMethod(clientKey: string) {
    setContactMethods((current) =>
      ensurePrimaryMethods(current.filter((method) => method.clientKey !== clientKey)),
    );
    setStatus("idle");
  }

  return (
    <form className={styles.editForm} onSubmit={handleSubmit}>
      <div className={styles.editGrid}>
        <label>
          <span>Seller</span>
          <input name="seller_name" defaultValue={lead.seller_name} maxLength={255} required />
        </label>
        <label>
          <span>Preferred name</span>
          <input name="preferred_name" defaultValue={lead.preferred_name ?? ""} maxLength={255} />
        </label>
        <label>
          <span>Lead owner</span>
          <select name="assigned_user_id" defaultValue={lead.assigned_user_id ?? ""}>
            <option value="">Unassigned</option>
            {lead.assignable_users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.display_name} ({user.email})
              </option>
            ))}
          </select>
        </label>
        <div className={`${styles.contactMethodEditor} ${styles.editWide}`}>
          <div className={styles.contactMethodHeading}>
            <strong>Phone numbers and emails</strong>
            <div>
              <button onClick={() => addContactMethod("phone")} type="button">
                <Plus aria-hidden="true" size={14} /> Add phone
              </button>
              <button onClick={() => addContactMethod("email")} type="button">
                <Plus aria-hidden="true" size={14} /> Add email
              </button>
            </div>
          </div>
          <div className={styles.contactMethodRows}>
            {contactMethods.map((method) => (
              <div className={styles.contactMethodRow} key={method.clientKey}>
                <select
                  aria-label="Contact method type"
                  onChange={(event) =>
                    updateContactMethod(method.clientKey, {
                      method_type: event.target.value as "phone" | "email",
                      is_primary: false,
                    })
                  }
                  value={method.method_type}
                >
                  <option value="phone">Phone</option>
                  <option value="email">Email</option>
                </select>
                <input
                  aria-label={method.method_type === "phone" ? "Phone number" : "Email address"}
                  maxLength={method.method_type === "phone" ? 80 : 320}
                  onChange={(event) =>
                    updateContactMethod(method.clientKey, { value: event.target.value })
                  }
                  type={method.method_type === "phone" ? "tel" : "email"}
                  value={method.value}
                />
                <label className={styles.primaryMethod}>
                  <input
                    checked={method.is_primary}
                    name={`primary-${method.method_type}`}
                    onChange={() => makePrimary(method.clientKey, method.method_type)}
                    type="radio"
                  />
                  <span>Primary</span>
                </label>
                <button
                  aria-label={`Remove ${method.method_type}`}
                  className={styles.removeMethod}
                  onClick={() => removeContactMethod(method.clientKey)}
                  title={`Remove ${method.method_type}`}
                  type="button"
                >
                  <Trash2 aria-hidden="true" size={15} />
                </button>
              </div>
            ))}
          </div>
        </div>
        <label className={styles.editWide}>
          <span>Street address</span>
          <input
            name="property_street_address"
            defaultValue={lead.property_street_address}
            maxLength={255}
            required
          />
        </label>
        <label>
          <span>City</span>
          <input name="property_city" defaultValue={lead.property_city} maxLength={120} required />
        </label>
        <label>
          <span>State</span>
          <input
            name="property_state"
            defaultValue={lead.property_state}
            maxLength={2}
            minLength={2}
            required
          />
        </label>
        <label>
          <span>ZIP</span>
          <input
            name="property_postal_code"
            defaultValue={lead.property_postal_code}
            maxLength={20}
            required
          />
        </label>
        <label>
          <span>County</span>
          <input name="property_county" defaultValue={lead.property_county ?? ""} maxLength={120} />
        </label>
        <label>
          <span>Property type</span>
          <input name="property_type" defaultValue={lead.property_type ?? ""} maxLength={80} />
        </label>
        <label>
          <span>Source</span>
          <select name="source" defaultValue={lead.source}>
            {sourceOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Temperature</span>
          <select name="lead_temperature" defaultValue={lead.lead_temperature ?? ""}>
            {temperatures.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.editWide}>
          <span>Motivation</span>
          <input
            name="motivation"
            defaultValue={lead.motivation ?? ""}
            maxLength={500}
            placeholder="Why the seller is considering a cash offer"
          />
        </label>
        <label>
          <span>Timeline</span>
          <input
            name="desired_timeline"
            defaultValue={lead.desired_timeline ?? ""}
            maxLength={120}
            placeholder="ASAP, 30 days, just exploring"
          />
        </label>
        <label>
          <span>Condition</span>
          <select name="property_condition" defaultValue={lead.property_condition ?? ""}>
            {conditionOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Occupancy</span>
          <select name="occupancy_status" defaultValue={lead.occupancy_status ?? ""}>
            {occupancyOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Appointment</span>
          <select name="appointment_status" defaultValue={lead.appointment_status ?? ""}>
            {appointmentOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Asking price</span>
          <input name="asking_price" defaultValue={lead.asking_price ?? ""} maxLength={120} />
        </label>
        <label>
          <span>Mortgage balance</span>
          <input
            name="mortgage_balance"
            defaultValue={lead.mortgage_balance ?? ""}
            maxLength={120}
          />
        </label>
        <label>
          <span>Next follow-up</span>
          <input
            name="next_follow_up_at"
            defaultValue={dateTimeLocalValue(lead.next_follow_up_at)}
            type="datetime-local"
          />
        </label>
        <label className={styles.editWide}>
          <span>Reason</span>
          <input name="reason" placeholder="Optional audit note" />
        </label>
      </div>
      <button disabled={status === "saving"} type="submit">
        {status === "saving" ? "Saving..." : "Save lead"}
      </button>
      {status === "saved" ? <p className={styles.saved}>Lead saved.</p> : null}
      {status === "error" ? <p className={styles.error}>{errorMessage}</p> : null}
    </form>
  );
}
