"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type { UnderwritingCalibrationCase } from "../../lib/api";
import styles from "./page.module.css";

type CalibrationDraft = {
  benchmarkType: string;
  evidenceDate: string;
  benchmarkArv: string;
  actualRehab: string;
  sellerContract: string;
  dispositionPrice: string;
  evidenceReference: string;
  notes: string;
};

const emptyDraft: CalibrationDraft = {
  benchmarkType: "expert_review",
  evidenceDate: "",
  benchmarkArv: "",
  actualRehab: "",
  sellerContract: "",
  dispositionPrice: "",
  evidenceReference: "",
  notes: "",
};

function centsToDollars(value: number | null) {
  return value === null ? "" : String(value / 100);
}

function dollarsToCents(value: string) {
  if (!value.trim()) {
    return null;
  }
  const amount = Number(value.replace(/,/g, ""));
  return Number.isFinite(amount) && amount >= 0 ? Math.round(amount * 100) : null;
}

function draftFromCase(value: UnderwritingCalibrationCase): CalibrationDraft {
  return {
    benchmarkType: value.benchmark_type,
    evidenceDate: value.evidence_date.slice(0, 10),
    benchmarkArv: centsToDollars(value.benchmark_arv_cents),
    actualRehab: centsToDollars(value.actual_rehab_cents),
    sellerContract: centsToDollars(value.actual_seller_contract_cents),
    dispositionPrice: centsToDollars(value.actual_disposition_cents),
    evidenceReference: value.evidence_reference ?? "",
    notes: value.notes ?? "",
  };
}

export function CalibrationOutcomeForm({ analysisId }: { analysisId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [draft, setDraft] = useState<CalibrationDraft>(emptyDraft);
  const [existingCase, setExistingCase] = useState<UnderwritingCalibrationCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
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

    async function loadCase() {
      setLoading(true);
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/underwriting/calibration-cases/${analysisId}`,
          { headers: await getHeaders(), signal: controller.signal },
        );
        if (!response.ok) {
          throw new Error("Unable to load the saved benchmark.");
        }
        const value = (await response.json()) as UnderwritingCalibrationCase | null;
        if (value) {
          setExistingCase(value);
          setDraft(draftFromCase(value));
        } else {
          setDraft((current) => ({
            ...current,
            evidenceDate: new Date().toISOString().slice(0, 10),
          }));
        }
      } catch (caught) {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setError(caught instanceof Error ? caught.message : "Unable to load the benchmark.");
        }
      } finally {
        setLoading(false);
      }
    }

    void loadCase();
    return () => controller.abort();
  }, [analysisId, apiBaseUrl, getHeaders]);

  function update(field: keyof CalibrationDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
    setMessage(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const benchmarkArvCents = dollarsToCents(draft.benchmarkArv);
    if (!benchmarkArvCents || !draft.evidenceDate) {
      setError("Benchmark ARV and evidence date are required.");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const headers: Record<string, string> = await getHeaders();
      headers["Content-Type"] = "application/json";
      const response = await fetch(
        `${apiBaseUrl}/api/v1/underwriting/calibration-cases/${analysisId}`,
        {
          method: "PUT",
          headers,
          body: JSON.stringify({
            benchmark_type: draft.benchmarkType,
            evidence_date: `${draft.evidenceDate}T12:00:00Z`,
            benchmark_arv_cents: benchmarkArvCents,
            actual_rehab_cents: dollarsToCents(draft.actualRehab),
            actual_seller_contract_cents: dollarsToCents(draft.sellerContract),
            actual_disposition_cents: dollarsToCents(draft.dispositionPrice),
            evidence_reference: draft.evidenceReference.trim() || null,
            notes: draft.notes.trim() || null,
          }),
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(payload?.detail ?? "Unable to save the verified outcome.");
      }
      const value = (await response.json()) as UnderwritingCalibrationCase;
      setExistingCase(value);
      setDraft(draftFromCase(value));
      setMessage("Verified outcome saved.");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save the outcome.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <details className={styles.calibrationInputs} open={existingCase !== null}>
      <summary>
        <div>
          <strong>Verified outcome</strong>
          <span>Compare this saved estimate with later human or market evidence.</span>
        </div>
        <span className={existingCase ? styles.calibrationSaved : styles.calibrationPending}>
          {loading ? "Loading" : existingCase ? "Recorded" : "Not recorded"}
        </span>
      </summary>
      <form className={styles.calibrationForm} onSubmit={submit}>
        <div className={styles.calibrationGrid}>
          <label>
            Evidence type
            <select
              onChange={(event) => update("benchmarkType", event.target.value)}
              value={draft.benchmarkType}
            >
              <option value="expert_review">Expert comp review</option>
              <option value="appraisal">Appraisal</option>
              <option value="completed_resale">Completed resale</option>
              <option value="verified_market_sale">Verified market sale</option>
            </select>
          </label>
          <label>
            Evidence date
            <input
              onChange={(event) => update("evidenceDate", event.target.value)}
              required
              type="date"
              value={draft.evidenceDate}
            />
          </label>
          <label>
            Benchmark ARV
            <input
              inputMode="decimal"
              min="1"
              onChange={(event) => update("benchmarkArv", event.target.value)}
              placeholder="285000"
              required
              step="0.01"
              type="number"
              value={draft.benchmarkArv}
            />
          </label>
          <label>
            Actual rehab
            <input
              inputMode="decimal"
              min="0"
              onChange={(event) => update("actualRehab", event.target.value)}
              placeholder="Optional"
              step="0.01"
              type="number"
              value={draft.actualRehab}
            />
          </label>
          <label>
            Seller contract
            <input
              inputMode="decimal"
              min="0"
              onChange={(event) => update("sellerContract", event.target.value)}
              placeholder="Optional"
              step="0.01"
              type="number"
              value={draft.sellerContract}
            />
          </label>
          <label>
            Disposition price
            <input
              inputMode="decimal"
              min="0"
              onChange={(event) => update("dispositionPrice", event.target.value)}
              placeholder="Optional"
              step="0.01"
              type="number"
              value={draft.dispositionPrice}
            />
          </label>
          <label className={styles.calibrationWide}>
            Evidence reference
            <input
              maxLength={500}
              onChange={(event) => update("evidenceReference", event.target.value)}
              placeholder="Appraisal, closing record, BPO, or reviewer"
              value={draft.evidenceReference}
            />
          </label>
          <label className={styles.calibrationWide}>
            Notes
            <textarea
              maxLength={2000}
              onChange={(event) => update("notes", event.target.value)}
              placeholder="Condition, evidence quality, and relevant market context"
              rows={3}
              value={draft.notes}
            />
          </label>
        </div>
        <div className={styles.calibrationFooter}>
          <div aria-live="polite">
            {error ? <span className={styles.calibrationError}>{error}</span> : null}
            {message ? <span className={styles.calibrationSuccess}>{message}</span> : null}
          </div>
          <button disabled={saving || loading} type="submit">
            {saving ? "Saving..." : existingCase ? "Update outcome" : "Save outcome"}
          </button>
        </div>
      </form>
    </details>
  );
}
