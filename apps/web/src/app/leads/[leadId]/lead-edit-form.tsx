"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { LeadDetail } from "../../lib/api";
import styles from "./page.module.css";

type Status = "idle" | "saving" | "saved" | "error";

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

function primaryContactValue(lead: LeadDetail, methodType: string) {
  const primary = lead.contact_methods.find(
    (method) => method.method_type === methodType && method.is_primary,
  );
  const first = lead.contact_methods.find((method) => method.method_type === methodType);
  return primary?.value ?? first?.value ?? "";
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
    setStatus("saving");

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
          phone: optionalFormString(formData, "phone"),
          email: optionalFormString(formData, "email"),
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

      if (!response.ok) {
        throw new Error("Unable to update lead details.");
      }

      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
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
          <span>Phone</span>
          <input name="phone" defaultValue={primaryContactValue(lead, "phone")} maxLength={80} />
        </label>
        <label>
          <span>Email</span>
          <input
            name="email"
            defaultValue={primaryContactValue(lead, "email")}
            maxLength={320}
            type="email"
          />
        </label>
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
        Save details
      </button>
      {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
    </form>
  );
}
