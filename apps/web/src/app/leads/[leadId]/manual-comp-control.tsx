"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import styles from "./page.module.css";

export type ManualComparable = {
  id: string;
  status: "active" | "voided";
  formatted_address: string;
  sale_date: string;
  sale_price_cents: number;
  property_type: string;
  bedrooms: number | null;
  bathrooms: number | null;
  square_footage: number;
  year_built: number | null;
  lot_size: number | null;
  distance_miles: number | null;
  subdivision: string | null;
  condition_classification: "unknown" | "as_is" | "renovated";
  condition_evidence: string | null;
  source_type:
    | "county_record"
    | "mls_record"
    | "closing_document"
    | "broker_confirmation"
    | "other_verified";
  source_reference: string;
  source_url: string | null;
  verification_notes: string;
};

type ManualCompControlProps = {
  leadId: string;
  selectedIds: string[] | null;
  onSelectedIdsChange: (ids: string[]) => void;
  onEvidenceChanged: () => void;
};

const EMPTY_FORM = {
  street_address: "",
  city: "",
  state: "GA",
  postal_code: "",
  sale_date: "",
  sale_price: "",
  property_type: "Single Family",
  bedrooms: "",
  bathrooms: "",
  square_footage: "",
  year_built: "",
  lot_size: "",
  distance_miles: "",
  subdivision: "",
  condition_classification: "unknown",
  condition_evidence: "",
  source_type: "county_record",
  source_reference: "",
  source_url: "",
  verification_notes: "",
};

export function ManualCompControl({
  leadId,
  selectedIds,
  onSelectedIdsChange,
  onEvidenceChanged,
}: ManualCompControlProps) {
  const { getToken } = useAuth();
  const [comparables, setComparables] = useState<ManualComparable[]>([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
  const selectedIdsRef = useRef(selectedIds);
  useEffect(() => {
    selectedIdsRef.current = selectedIds;
  }, [selectedIds]);
  const getHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await getToken().catch(() => null);
    return token
      ? { Authorization: `Bearer ${token}` }
      : { "X-Dev-User-Email": devUserEmail };
  }, [devUserEmail, getToken]);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/manual-comps`,
          { headers: await getHeaders(), signal: controller.signal },
        );
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(payload?.detail ?? "Unable to load manual comparable sales.");
        }
        const records = (await response.json()) as ManualComparable[];
        setComparables(records);
        const currentSelection = selectedIdsRef.current;
        if (currentSelection === null) {
          onSelectedIdsChange(records.map((record) => record.id));
        } else {
          const activeIds = new Set(records.map((record) => record.id));
          const validSelection = currentSelection.filter((id) => activeIds.has(id));
          if (validSelection.length !== currentSelection.length) {
            onSelectedIdsChange(validSelection);
          }
        }
      } catch (caught) {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Unable to load manual comparable sales.",
          );
        }
      } finally {
        setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [apiBaseUrl, getHeaders, leadId, onSelectedIdsChange]);

  function update(field: keyof typeof EMPTY_FORM, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const headers: Record<string, string> = await getHeaders();
      headers["Content-Type"] = "application/json";
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/manual-comps`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({
            street_address: form.street_address,
            city: form.city,
            state: form.state,
            postal_code: form.postal_code,
            sale_date: form.sale_date,
            sale_price_cents: Math.round(Number(form.sale_price.replaceAll(",", "")) * 100),
            property_type: form.property_type,
            bedrooms: optionalNumber(form.bedrooms),
            bathrooms: optionalNumber(form.bathrooms),
            square_footage: Number(form.square_footage),
            year_built: optionalNumber(form.year_built),
            lot_size: optionalNumber(form.lot_size),
            distance_miles: optionalNumber(form.distance_miles),
            subdivision: form.subdivision || null,
            condition_classification: form.condition_classification,
            condition_evidence: form.condition_evidence || null,
            source_type: form.source_type,
            source_reference: form.source_reference,
            source_url: form.source_url || null,
            verification_notes: form.verification_notes,
          }),
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(validationMessage(payload?.detail));
      }
      const record = (await response.json()) as ManualComparable;
      setComparables((current) => [record, ...current]);
      onSelectedIdsChange([...(selectedIds ?? []), record.id]);
      onEvidenceChanged();
      setForm(EMPTY_FORM);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save the comparable sale.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(comparableId: string) {
    if (!window.confirm("Remove this manual sale from future analyses?")) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/manual-comps/${comparableId}`,
        { method: "DELETE", headers: await getHeaders() },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Unable to remove the manual comparable.");
      }
      setComparables((current) => current.filter((record) => record.id !== comparableId));
      onSelectedIdsChange((selectedIds ?? []).filter((id) => id !== comparableId));
      onEvidenceChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to remove the comparable.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <details className={styles.manualCompControl}>
      <summary>
        <div>
          <strong>Verified manual sales</strong>
          <span>{comparables.length} saved</span>
        </div>
        <span>{selectedIds?.length ?? 0} included</span>
      </summary>
      <div className={styles.manualCompBody}>
        {error ? <p className={styles.error}>{error}</p> : null}
        {comparables.length ? (
          <div className={styles.manualCompList}>
            {comparables.map((comparable) => {
              const checked = selectedIds?.includes(comparable.id) ?? false;
              return (
                <article key={comparable.id}>
                  <label>
                    <input
                      checked={checked}
                      onChange={(event) => {
                        const next = event.target.checked
                          ? [...(selectedIds ?? []), comparable.id]
                          : (selectedIds ?? []).filter((id) => id !== comparable.id);
                        onSelectedIdsChange(Array.from(new Set(next)));
                        onEvidenceChanged();
                      }}
                      type="checkbox"
                    />
                    <span>
                      <strong>{comparable.formatted_address}</strong>
                      <small>
                        {formatMoney(comparable.sale_price_cents)} · {comparable.sale_date} · {" "}
                        {comparable.square_footage.toLocaleString()} sqft
                      </small>
                      <small>
                        {comparable.source_type.replaceAll("_", " ")} · {" "}
                        {comparable.source_reference}
                      </small>
                    </span>
                  </label>
                  <button disabled={saving} onClick={() => remove(comparable.id)} type="button">
                    Remove
                  </button>
                </article>
              );
            })}
          </div>
        ) : loading ? (
          <p>Loading saved sales...</p>
        ) : null}

        <form className={styles.manualCompForm} onSubmit={submit}>
          <div className={styles.manualCompFormHeader}>
            <strong>Add a known closed sale</strong>
            <span>Source verification is required</span>
          </div>
          <div className={styles.manualCompAddressGrid}>
            <label>
              <span>Street address</span>
              <input required value={form.street_address} onChange={(event) => update("street_address", event.target.value)} />
            </label>
            <label>
              <span>City</span>
              <input required value={form.city} onChange={(event) => update("city", event.target.value)} />
            </label>
            <label>
              <span>State</span>
              <input maxLength={2} required value={form.state} onChange={(event) => update("state", event.target.value.toUpperCase())} />
            </label>
            <label>
              <span>ZIP</span>
              <input required value={form.postal_code} onChange={(event) => update("postal_code", event.target.value)} />
            </label>
          </div>
          <div className={styles.manualCompFields}>
            <label>
              <span>Closed date</span>
              <input required type="date" value={form.sale_date} onChange={(event) => update("sale_date", event.target.value)} />
            </label>
            <label>
              <span>Closed price</span>
              <input min="1000" required step="100" type="number" value={form.sale_price} onChange={(event) => update("sale_price", event.target.value)} />
            </label>
            <label>
              <span>Property type</span>
              <select value={form.property_type} onChange={(event) => update("property_type", event.target.value)}>
                <option>Single Family</option>
                <option>Condo</option>
                <option>Townhouse</option>
                <option>Manufactured</option>
                <option>Multi-Family</option>
              </select>
            </label>
            <label>
              <span>Square feet</span>
              <input min="100" required type="number" value={form.square_footage} onChange={(event) => update("square_footage", event.target.value)} />
            </label>
            <label><span>Bedrooms</span><input min="0" type="number" value={form.bedrooms} onChange={(event) => update("bedrooms", event.target.value)} /></label>
            <label><span>Bathrooms</span><input min="0" step="0.5" type="number" value={form.bathrooms} onChange={(event) => update("bathrooms", event.target.value)} /></label>
            <label><span>Year built</span><input min="1700" type="number" value={form.year_built} onChange={(event) => update("year_built", event.target.value)} /></label>
            <label><span>Distance (mi)</span><input min="0" step="0.01" type="number" value={form.distance_miles} onChange={(event) => update("distance_miles", event.target.value)} /></label>
            <label><span>Lot size (sqft)</span><input min="0" type="number" value={form.lot_size} onChange={(event) => update("lot_size", event.target.value)} /></label>
            <label><span>Subdivision</span><input value={form.subdivision} onChange={(event) => update("subdivision", event.target.value)} /></label>
            <label>
              <span>Condition at sale</span>
              <select value={form.condition_classification} onChange={(event) => update("condition_classification", event.target.value)}>
                <option value="unknown">Unknown</option>
                <option value="as_is">As-is</option>
                <option value="renovated">Renovated</option>
              </select>
            </label>
            <label>
              <span>Verification source</span>
              <select value={form.source_type} onChange={(event) => update("source_type", event.target.value)}>
                <option value="county_record">County record</option>
                <option value="mls_record">MLS record</option>
                <option value="closing_document">Closing document</option>
                <option value="broker_confirmation">Broker confirmation</option>
                <option value="other_verified">Other verified source</option>
              </select>
            </label>
          </div>
          <label>
            <span>Source reference</span>
            <input placeholder="MLS number, deed book/page, or document reference" required value={form.source_reference} onChange={(event) => update("source_reference", event.target.value)} />
          </label>
          <label>
            <span>Source link</span>
            <input placeholder="https://" type="url" value={form.source_url} onChange={(event) => update("source_url", event.target.value)} />
          </label>
          <label>
            <span>Condition evidence</span>
            <textarea required={form.condition_classification !== "unknown"} rows={2} value={form.condition_evidence} onChange={(event) => update("condition_evidence", event.target.value)} />
          </label>
          <label>
            <span>Verification notes</span>
            <textarea minLength={10} required rows={2} value={form.verification_notes} onChange={(event) => update("verification_notes", event.target.value)} />
          </label>
          <button disabled={saving} type="submit">
            {saving ? "Saving..." : "Save verified sale"}
          </button>
        </form>
      </div>
    </details>
  );
}

function optionalNumber(value: string) {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value / 100);
}

function validationMessage(detail: unknown) {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") {
    return detail[0].msg;
  }
  return "Unable to save the comparable sale.";
}
