"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "./page.module.css";

type Status = "idle" | "saving" | "saved" | "error";

export type ExecutedContractImportResponse = {
  transaction_id: string;
  contract_package_id: string;
  document_id: string;
  lead_id: string;
  lead_stage: string;
  transaction_status: string;
  disposition_case_id: string | null;
  disposition_handoff_ready: boolean;
  disposition_handoff_status: "ready" | "needs_setup";
  disposition_handoff_blockers: string[];
};

function value(data: FormData, key: string) {
  return String(data.get(key) ?? "").trim();
}

function requiredValue(data: FormData, key: string, label: string) {
  const result = value(data, key);
  if (!result) throw new Error(`${label} is required.`);
  return result;
}

function cents(data: FormData, key: string, label: string, required = false) {
  const normalized = value(data, key).replace(/[$,]/g, "");
  if (!normalized) {
    if (required) throw new Error(`${label} is required.`);
    return "";
  }
  if (!/^(?:\d+|\d*\.\d{1,2})$/.test(normalized)) {
    throw new Error(`${label} must be a valid dollar amount with no more than two decimal places.`);
  }
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed < 0 || (required && parsed === 0)) {
    throw new Error(`${label} must be ${required ? "greater than zero" : "zero or greater"}.`);
  }
  const amountInCents = Math.round(parsed * 100);
  if (!Number.isSafeInteger(amountInCents)) throw new Error(`${label} is too large.`);
  return String(amountInCents);
}

function wholeNumber(
  data: FormData,
  key: string,
  label: string,
  minimum: number,
  maximum: number,
) {
  const raw = value(data, key);
  if (!raw) return "";
  if (!/^\d+$/.test(raw)) {
    throw new Error(`${label} must be a whole number between ${minimum} and ${maximum}.`);
  }
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${label} must be between ${minimum} and ${maximum}.`);
  }
  return String(parsed);
}

function isoDate(data: FormData, key: string, label: string, required = false) {
  const raw = value(data, key);
  if (!raw) {
    if (required) throw new Error(`${label} is required.`);
    return "";
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) throw new Error(`${label} is not a valid date and time.`);
  return parsed.toISOString();
}

function calendarDate(data: FormData, key: string, label: string) {
  const raw = value(data, key);
  if (!raw) return "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) throw new Error(`${label} is not a valid date.`);
  const parsed = new Date(`${raw}T17:00:00Z`);
  if (Number.isNaN(parsed.getTime())) throw new Error(`${label} is not a valid date.`);
  return parsed.toISOString();
}

async function responseError(response: Response) {
  const payload = (await response.json().catch(() => ({}))) as { detail?: unknown };
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    const messages = payload.detail
      .map((issue) => {
        if (!issue || typeof issue !== "object") return null;
        const record = issue as { loc?: unknown; msg?: unknown };
        if (typeof record.msg !== "string") return null;
        const location = Array.isArray(record.loc)
          ? record.loc
              .filter((part) => part !== "query" && part !== "body")
              .map((part) => String(part).replaceAll("_", " "))
              .join(" ")
          : "";
        return location ? `${location}: ${record.msg}` : record.msg;
      })
      .filter((item): item is string => Boolean(item));
    if (messages.length) return messages.slice(0, 3).join("; ");
  }
  return "Unable to record the signed contract. Review the highlighted contract details and try again.";
}

export function ExecutedContractImportForm({
  leadId,
  onCancel,
  onRecorded,
  sellerName,
}: {
  leadId: string;
  onCancel?: () => void;
  onRecorded?: (result: ExecutedContractImportResponse) => void;
  sellerName: string;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [handoffReview, setHandoffReview] = useState<ExecutedContractImportResponse | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function headers() {
    const token = await getToken().catch(() => null);
    const result: Record<string, string> = {};
    if (token) result.Authorization = `Bearer ${token}`;
    else result["X-Dev-User-Email"] = devUserEmail;
    return result;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("contract_pdf");
    if (!(file instanceof File) || file.size === 0) {
      setStatus("error");
      setMessage("Choose the fully executed purchase agreement PDF.");
      return;
    }

    setStatus("saving");
    setMessage(null);
    setHandoffReview(null);
    try {
      const requestData = new FormData();
      requestData.set("file", file, file.name);
      requestData.set("seller_name", requiredValue(data, "seller_name", "Seller name"));
      requestData.set("buyer_entity_name", requiredValue(data, "buyer_entity_name", "Buyer entity"));
      requestData.set("purchase_price_cents", cents(data, "purchase_price", "Purchase price", true));
      requestData.set("executed_at", isoDate(data, "executed_at", "Execution date and time", true));
      requestData.set("execution_source", requiredValue(data, "execution_source", "Signature source"));
      if (!data.get("confirm_fully_executed")) {
        throw new Error("Confirm that every required party signed this exact PDF.");
      }
      requestData.set("confirm_fully_executed", "true");
      requestData.set(
        "attestation_reason",
        requiredValue(data, "attestation_reason", "Import audit note"),
      );
      const optional = {
        assignment_fee_cents: cents(data, "assignment_fee", "Assignment fee"),
        earnest_money_cents: cents(data, "earnest_money", "Earnest money"),
        title_company: value(data, "title_company"),
        closing_date: calendarDate(data, "closing_date", "Contract closing date"),
        inspection_period_days: wholeNumber(
          data,
          "inspection_period_days",
          "Inspection period",
          0,
          120,
        ),
        earnest_money_due_at: isoDate(data, "earnest_money_due_at", "Earnest money due date"),
        due_diligence_deadline: isoDate(
          data,
          "due_diligence_deadline",
          "Due-diligence deadline",
        ),
        external_reference: value(data, "external_reference"),
        notes: value(data, "notes"),
      };
      for (const [key, item] of Object.entries(optional)) {
        if (item) requestData.set(key, item);
      }

      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/transactions/import-executed-contract`,
        {
          method: "POST",
          headers: await headers(),
          body: requestData,
        },
      );
      if (!response.ok) throw new Error(await responseError(response));
      const imported = (await response.json()) as ExecutedContractImportResponse;
      setStatus("saved");
      onRecorded?.(imported);
      if (
        imported.disposition_handoff_status === "ready" &&
        imported.disposition_handoff_ready &&
        imported.disposition_case_id
      ) {
        setMessage("Signed contract recorded. The deal is Under Contract and its Dispositions case is open.");
        router.push(`/os/dispositions?case=${encodeURIComponent(imported.disposition_case_id)}`);
        router.refresh();
        return;
      }
      setHandoffReview(imported);
      setMessage(
        "Signed contract recorded and the deal is Under Contract. It is visible to Dispositions as Needs setup until the listed handoff blockers are resolved.",
      );
      router.refresh();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Unable to record the signed contract.");
    }
  }

  return (
    <form className={styles.transactionForm} onSubmit={submit}>
      <p className={styles.workflowNotice}>
        Use this only when every required party has already signed outside Stonegate. This records
        the actual agreement, moves the deal to Under Contract, and opens the Dispositions handoff.
      </p>
      <label>
        <span>Fully executed purchase agreement PDF</span>
        <input accept="application/pdf,.pdf" name="contract_pdf" required type="file" />
      </label>
      <div className={styles.taskGrid}>
        <label>
          <span>Seller name on agreement</span>
          <input defaultValue={sellerName} maxLength={255} name="seller_name" required />
        </label>
        <label>
          <span>Buyer entity on agreement</span>
          <input maxLength={255} name="buyer_entity_name" placeholder="Exact legal buyer name" required />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Purchase price</span>
          <input min="0.01" name="purchase_price" placeholder="170000" required step="0.01" type="number" />
        </label>
        <label>
          <span>Date and time fully executed</span>
          <input name="executed_at" required type="datetime-local" />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Signature source</span>
          <select defaultValue="docusign" name="execution_source">
            <option value="docusign">DocuSign</option>
            <option value="signwell">SignWell</option>
            <option value="pandadoc">PandaDoc</option>
            <option value="adobe_sign">Adobe Acrobat Sign</option>
            <option value="manual_upload">Signed manually</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          <span>Envelope or external reference (optional)</span>
          <input maxLength={255} name="external_reference" placeholder="Optional envelope ID" />
        </label>
      </div>
      <p className={styles.secondaryTermsNotice}>
        The remaining closing terms are optional for catch-up. Enter what you know now; Stonegate
        creates follow-up work for important terms that still need to be confirmed.
      </p>
      <div className={styles.taskGrid}>
        <label>
          <span>Earnest money (optional)</span>
          <input min="0" name="earnest_money" placeholder="1000" step="0.01" type="number" />
        </label>
        <label>
          <span>Assignment fee (optional)</span>
          <input min="0" name="assignment_fee" placeholder="Optional" step="0.01" type="number" />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Title company / closing attorney (optional)</span>
          <input maxLength={255} name="title_company" />
        </label>
        <label>
          <span>Contract closing date (optional)</span>
          <input name="closing_date" type="date" />
        </label>
      </div>
      <div className={styles.taskGrid}>
        <label>
          <span>Earnest money due (optional)</span>
          <input name="earnest_money_due_at" type="datetime-local" />
        </label>
        <label>
          <span>Due-diligence deadline (optional)</span>
          <input name="due_diligence_deadline" type="datetime-local" />
        </label>
      </div>
      <label>
        <span>Inspection / due-diligence period in days (optional)</span>
        <input max={120} min={0} name="inspection_period_days" step={1} type="number" />
      </label>
      <label>
        <span>Contract notes (optional)</span>
        <textarea maxLength={2000} name="notes" rows={3} />
      </label>
      <label>
        <span>Import audit note</span>
        <textarea
          minLength={10}
          maxLength={500}
          name="attestation_reason"
          placeholder="Example: Reviewed the completed DocuSign envelope and confirmed every required party signed."
          required
          rows={3}
        />
      </label>
      <label className={styles.checkboxLabel}>
        <input name="confirm_fully_executed" required type="checkbox" />
        <span>I reviewed this exact PDF and confirm the purchase agreement is fully executed.</span>
      </label>
      <div className={styles.transactionFormActions}>
        {onCancel ? (
          <button
            className={styles.secondaryFormAction}
            disabled={status === "saving" || status === "saved"}
            onClick={onCancel}
            type="button"
          >
            Cancel and keep current stage
          </button>
        ) : null}
        <button disabled={status === "saving" || status === "saved"} type="submit">
          {status === "saving"
            ? "Recording signed contract..."
            : status === "saved"
              ? "Signed contract recorded"
              : "Record contract and open Dispositions"}
        </button>
      </div>
      {message ? <p className={status === "error" ? styles.error : styles.saved}>{message}</p> : null}
      {handoffReview ? (
        <div className={styles.handoffReview}>
          {handoffReview.disposition_handoff_blockers.length ? (
            <div className={styles.handoffBlockers} role="status">
              <strong>Dispositions setup still needed</strong>
              <ul>
                {handoffReview.disposition_handoff_blockers.map((blocker) => (
                  <li key={blocker}>{blocker}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className={styles.handoffReviewActions}>
            <Link
              href={`/os/transactions?transaction=${encodeURIComponent(handoffReview.transaction_id)}&tab=timeline`}
            >
              Review transaction handoff
            </Link>
            <Link href="/os/settings/people">Check People &amp; Access</Link>
            <Link href="/os/settings/finance-policy">Check Finance Policy</Link>
          </div>
        </div>
      ) : null}
    </form>
  );
}
