"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import styles from "./page.module.css";

export type RepairEstimateItem = {
  category: string;
  estimated_cost_cents: number;
  labor_cost_cents?: number | null;
  material_cost_cents?: number | null;
  details?: string | null;
};

export type RepairEstimate = {
  id: string;
  lead_id: string;
  property_id: string;
  source_type: string;
  contractor_name: string | null;
  estimate_date: string;
  scope_items: RepairEstimateItem[];
  subtotal_cents: number;
  contingency_percentage: number;
  contingency_cents: number;
  total_cents: number;
  evidence_reference: string | null;
  notes: string | null;
  created_by_user_id: string | null;
  created_at: string;
};

type Props = {
  leadId: string;
  currentItems: RepairEstimateItem[];
  currentNotes: string;
  contingencyPercentage: number;
  selectedEstimateId: string | null;
  onApply: (estimate: RepairEstimate) => void;
  onClear: () => void;
};

function formatMoney(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

export function RepairEstimateControl({
  leadId,
  currentItems,
  currentNotes,
  contingencyPercentage,
  selectedEstimateId,
  onApply,
  onClear,
}: Props) {
  const { getToken } = useAuth();
  const [estimates, setEstimates] = useState<RepairEstimate[]>([]);
  const [sourceType, setSourceType] = useState("contractor_bid");
  const [contractorName, setContractorName] = useState("");
  const [estimateDate, setEstimateDate] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [evidenceReference, setEvidenceReference] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const getHeaders = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      headers["X-Dev-User-Email"] = devUserEmail;
    }
    return headers;
  }, [devUserEmail, getToken]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadEstimates() {
      setLoading(true);
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/repair-estimates`, {
          headers: await getHeaders(),
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error("Unable to load repair estimates.");
        }
        setEstimates((await response.json()) as RepairEstimate[]);
      } catch (caught) {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setError(caught instanceof Error ? caught.message : "Unable to load repair estimates.");
        }
      } finally {
        setLoading(false);
      }
    }

    void loadEstimates();
    return () => controller.abort();
  }, [apiBaseUrl, getHeaders, leadId]);

  const selectedEstimate = estimates.find((estimate) => estimate.id === selectedEstimateId);

  async function saveEstimate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentItems.length) {
      setError("Enter or apply an itemized repair scope first.");
      return;
    }
    if (sourceType === "contractor_bid" && !contractorName.trim()) {
      setError("Enter the contractor name.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const headers = await getHeaders();
      headers["Content-Type"] = "application/json";
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/repair-estimates`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          source_type: sourceType,
          contractor_name: contractorName.trim() || null,
          estimate_date: `${estimateDate}T12:00:00Z`,
          scope_items: currentItems,
          contingency_percentage: contingencyPercentage,
          evidence_reference: evidenceReference.trim() || null,
          notes: currentNotes.trim() || null,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(payload?.detail ?? "Unable to save the repair estimate.");
      }
      const saved = (await response.json()) as RepairEstimate;
      setEstimates((current) => [saved, ...current]);
      setEvidenceReference("");
      onApply(saved);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save the estimate.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={styles.repairEvidence}>
      <div className={styles.repairEvidenceHeader}>
        <div>
          <strong>Saved repair evidence</strong>
          <span>Contractor bids and walkthrough scopes remain unchanged after saving.</span>
        </div>
        <select
          aria-label="Saved repair estimate"
          disabled={loading}
          onChange={(event) => {
            const estimate = estimates.find((item) => item.id === event.target.value);
            if (estimate) {
              onApply(estimate);
            } else {
              onClear();
            }
          }}
          value={selectedEstimateId ?? ""}
        >
          <option value="">Direct inputs</option>
          {estimates.map((estimate) => (
            <option key={estimate.id} value={estimate.id}>
              {estimate.contractor_name ?? estimate.source_type.replaceAll("_", " ")} -{" "}
              {formatMoney(estimate.total_cents)}
            </option>
          ))}
        </select>
      </div>

      {selectedEstimate ? (
        <dl className={styles.repairEvidenceSummary}>
          <div>
            <dt>Source</dt>
            <dd>{selectedEstimate.contractor_name ?? selectedEstimate.source_type.replaceAll("_", " ")}</dd>
          </div>
          <div>
            <dt>Subtotal</dt>
            <dd>{formatMoney(selectedEstimate.subtotal_cents)}</dd>
          </div>
          <div>
            <dt>Contingency</dt>
            <dd>{selectedEstimate.contingency_percentage}%</dd>
          </div>
          <div>
            <dt>Total</dt>
            <dd>{formatMoney(selectedEstimate.total_cents)}</dd>
          </div>
        </dl>
      ) : null}

      <details className={styles.repairEvidenceForm}>
        <summary>Record current itemized scope as evidence</summary>
        <form onSubmit={saveEstimate}>
          <div className={styles.repairEvidenceGrid}>
            <label>
              <span>Evidence type</span>
              <select onChange={(event) => setSourceType(event.target.value)} value={sourceType}>
                <option value="contractor_bid">Contractor bid</option>
                <option value="walkthrough_scope">Walkthrough scope</option>
                <option value="internal_scope">Internal scope</option>
              </select>
            </label>
            <label>
              <span>Contractor</span>
              <input
                maxLength={255}
                onChange={(event) => setContractorName(event.target.value)}
                placeholder={sourceType === "contractor_bid" ? "Required" : "Optional"}
                value={contractorName}
              />
            </label>
            <label>
              <span>Estimate date</span>
              <input
                onChange={(event) => setEstimateDate(event.target.value)}
                required
                type="date"
                value={estimateDate}
              />
            </label>
            <label>
              <span>Quote or reference</span>
              <input
                maxLength={500}
                onChange={(event) => setEvidenceReference(event.target.value)}
                placeholder="Quote number or document reference"
                value={evidenceReference}
              />
            </label>
          </div>
          <div className={styles.repairEvidenceFooter}>
            <span>{currentItems.length} scoped work items</span>
            <button disabled={saving || currentItems.length === 0} type="submit">
              {saving ? "Saving..." : "Save repair evidence"}
            </button>
          </div>
        </form>
      </details>
      {error ? <p className={styles.repairEvidenceError}>{error}</p> : null}
    </section>
  );
}
