"use client";

import { useAuth } from "@clerk/nextjs";
import { Plus, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { OperationsUser } from "../../lib/api";
import { Dialog } from "../_components/design-system";
import styles from "./new-lead-control.module.css";

function value(data: FormData, key: string) {
  return String(data.get(key) ?? "").trim();
}

export function NewLeadControl({
  currentUserId,
  initialOpen = false,
  users,
}: {
  currentUserId: string;
  initialOpen?: boolean;
  users: OperationsUser[];
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [open, setOpen] = useState(initialOpen);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const activeUsers = users.filter(
    (user) =>
      user.is_active &&
      user.role_keys.some((role) =>
        [
          "owner",
          "founder_operator",
          "ceo",
          "administrator",
          "acquisition_manager",
          "acquisition_rep",
        ].includes(role),
      ),
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const phone = value(data, "phone");
    const email = value(data, "email");
    if (!phone && !email) {
      setError("Enter at least one phone number or email address.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
    const nextFollowUp = value(data, "next_follow_up_at");
    const assetClass = value(data, "asset_class") || "house";
    const selectedPropertyType = value(data, "property_type");
      const response = await fetch(`${apiBaseUrl}/api/v1/leads`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          contact: {
            legal_name: value(data, "legal_name"),
            preferred_name: value(data, "preferred_name") || null,
            contact_type: "seller",
          },
          property: {
            street_address: value(data, "street_address"),
            city: value(data, "city"),
            state: value(data, "state"),
            postal_code: value(data, "postal_code"),
            county: value(data, "county") || null,
            property_type: selectedPropertyType || (assetClass === "land" ? "land" : null),
            parcel_id: value(data, "parcel_id") || null,
          },
          phone: phone || null,
          email: email || null,
          assigned_user_id: value(data, "assigned_user_id") || currentUserId,
          source: value(data, "source"),
          asset_class: assetClass,
          stage_key: "new",
          lead_temperature: value(data, "lead_temperature") || null,
          motivation: value(data, "motivation") || null,
          desired_timeline: value(data, "desired_timeline") || null,
          property_condition: value(data, "property_condition") || null,
          occupancy_status: value(data, "occupancy_status") || null,
          asking_price: value(data, "asking_price") || null,
          mortgage_balance: value(data, "mortgage_balance") || null,
          appointment_status: "not_scheduled",
          next_follow_up_at: nextFollowUp ? new Date(nextFollowUp).toISOString() : null,
          initial_note: value(data, "initial_note") || null,
        }),
      });
      const payload = (await response.json().catch(() => null)) as
        | { id?: string; detail?: string }
        | null;
      if (!response.ok || !payload?.id) {
        throw new Error(payload?.detail ?? "The lead could not be created.");
      }
      form.reset();
      setOpen(false);
      router.push(`/os/leads/${payload.id}`);
      router.refresh();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "The lead could not be created.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button className={styles.openButton} onClick={() => setOpen(true)} type="button">
        <Plus aria-hidden="true" size={16} />
        New Lead
      </button>
      <Dialog
        description="Create a warm, referral, phone, or staff-entered opportunity."
        footer={
          <>
            <button className={styles.cancelButton} onClick={() => setOpen(false)} type="button">Cancel</button>
            <button className={styles.saveButton} disabled={saving} form="new-lead-form" type="submit">
              <UserPlus aria-hidden="true" size={16} />
              {saving ? "Creating..." : "Create lead"}
            </button>
          </>
        }
        onClose={() => setOpen(false)}
        open={open}
        size="wide"
        title="New lead"
      >
            <form className={styles.form} id="new-lead-form" onSubmit={submit}>
              <fieldset>
                <legend>Seller and contact</legend>
                <label><span>Seller name</span><input autoFocus name="legal_name" required /></label>
                <label><span>Preferred name</span><input name="preferred_name" /></label>
                <label><span>Phone</span><input autoComplete="tel" name="phone" type="tel" /></label>
                <label><span>Email</span><input autoComplete="email" name="email" type="email" /></label>
              </fieldset>

              <fieldset>
                <legend>Property</legend>
                <label><span>Lead type</span><select defaultValue="house" name="asset_class" required><option value="house">House</option><option value="land">Land</option></select></label>
                <label className={styles.wide}><span>Street address</span><input autoComplete="street-address" name="street_address" required /></label>
                <label><span>City</span><input autoComplete="address-level2" name="city" required /></label>
                <label><span>State</span><input autoComplete="address-level1" defaultValue="GA" maxLength={2} name="state" required /></label>
                <label><span>ZIP code</span><input autoComplete="postal-code" name="postal_code" required /></label>
                <label><span>County</span><input name="county" /></label>
                <label><span>Parcel / APN</span><input maxLength={255} name="parcel_id" /></label>
                <label><span>Property type</span><select name="property_type"><option value="">Unknown</option><option value="single_family">Single family</option><option value="townhouse">Townhouse</option><option value="condo">Condo</option><option value="multi_family">Multi-family</option><option value="mobile_home">Mobile home</option><option value="land">Land</option><option value="other">Other</option></select></label>
              </fieldset>

              <fieldset>
                <legend>Lead ownership and source</legend>
                <label><span>Source</span><select defaultValue="inbound_phone" name="source" required><option value="inbound_phone">Inbound phone call</option><option value="referral">Referral</option><option value="website">Website</option><option value="networking">Networking</option><option value="google_ppc">Google paid search</option><option value="organic">Organic search</option><option value="direct_mail">Direct mail</option><option value="cold_call">Cold call</option><option value="other">Other</option></select></label>
                <label><span>Assigned owner</span><select defaultValue={currentUserId} name="assigned_user_id" required>{!activeUsers.some((user) => user.id === currentUserId) ? <option value={currentUserId}>Current user</option> : null}{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label>
                <label><span>Lead temperature</span><select defaultValue="warm" name="lead_temperature"><option value="">Unknown</option><option value="hot">Hot</option><option value="warm">Warm</option><option value="cold">Cold</option></select></label>
                <label><span>Next follow-up</span><input name="next_follow_up_at" type="datetime-local" /></label>
              </fieldset>

              <fieldset>
                <legend>Known seller context</legend>
                <label className={styles.wide}><span>Motivation</span><input name="motivation" placeholder="Why they may sell" /></label>
                <label><span>Timeline</span><input name="desired_timeline" placeholder="For example, within 30 days" /></label>
                <label><span>Condition</span><input name="property_condition" placeholder="Known repairs or condition" /></label>
                <label><span>Occupancy</span><select name="occupancy_status"><option value="">Unknown</option><option value="owner_occupied">Owner occupied</option><option value="tenant_occupied">Tenant occupied</option><option value="vacant">Vacant</option><option value="other">Other</option></select></label>
                <label><span>Asking price</span><input inputMode="decimal" name="asking_price" /></label>
                <label><span>Mortgage balance</span><input inputMode="decimal" name="mortgage_balance" /></label>
                <label className={styles.wide}><span>Initial note</span><textarea maxLength={500} name="initial_note" rows={3} /></label>
              </fieldset>

              {error ? <p className={styles.error} role="alert">{error}</p> : null}
            </form>
      </Dialog>
    </>
  );
}
