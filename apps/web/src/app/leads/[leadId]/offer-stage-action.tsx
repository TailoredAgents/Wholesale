"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import styles from "./page.module.css";

export type OutsideOfferResponse = {
  event_id: string;
  lead_id: string;
  previous_stage_key: string;
  stage_key: "offer_presented" | "negotiating";
  amount_cents: number;
  occurred_at: string;
  method: string;
  outcome: string;
  seller_response: string | null;
  notes: string | null;
};

type Status = "idle" | "saving" | "saved" | "error";
type Choice = "choose" | "outside";

function value(data: FormData, key: string) {
  return String(data.get(key) ?? "").trim();
}

function amountInCents(data: FormData) {
  const normalized = value(data, "amount").replace(/[$,]/g, "");
  if (!/^(?:\d+|\d*\.\d{1,2})$/.test(normalized)) {
    throw new Error("Offer amount must be a valid dollar amount with no more than two decimal places.");
  }
  const amount = Number(normalized);
  const cents = Math.round(amount * 100);
  if (!Number.isFinite(amount) || amount <= 0 || !Number.isSafeInteger(cents)) {
    throw new Error("Offer amount must be greater than zero.");
  }
  return cents;
}

function occurredAt(data: FormData) {
  const raw = value(data, "occurred_at");
  const parsed = new Date(raw);
  if (!raw || Number.isNaN(parsed.getTime())) {
    throw new Error("Enter when the offer was presented.");
  }
  return parsed.toISOString();
}

async function responseError(response: Response) {
  const payload = (await response.json().catch(() => ({}))) as { detail?: unknown };
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    const messages = payload.detail.flatMap((issue) => {
      if (!issue || typeof issue !== "object") return [];
      const record = issue as { loc?: unknown; msg?: unknown };
      if (typeof record.msg !== "string") return [];
      const location = Array.isArray(record.loc)
        ? record.loc
            .filter((part) => part !== "body")
            .map((part) => String(part).replaceAll("_", " "))
            .join(" ")
        : "";
      return [location ? `${location}: ${record.msg}` : record.msg];
    });
    if (messages.length) return messages.slice(0, 3).join("; ");
  }
  return "Unable to record the outside offer. Review the offer facts and try again.";
}

export function OfferStageAction({
  assetClass,
  expectedStageKey,
  leadId,
  onCancel,
  onRecorded,
  sellerName,
}: {
  assetClass: "house" | "land";
  expectedStageKey: string;
  leadId: string;
  onCancel?: () => void;
  onRecorded?: (result: OutsideOfferResponse) => void;
  sellerName: string;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [choice, setChoice] = useState<Choice>("choose");
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const stonegateOfferHref =
    assetClass === "land"
      ? `/os/leads/${leadId}?tab=valuation`
      : `/os/leads/${leadId}?tab=valuation#offer-decision`;

  async function submitOutsideOffer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setStatus("saving");
    setMessage(null);

    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;

      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/outside-offers`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          amount_cents: amountInCents(data),
          expected_stage_key: expectedStageKey,
          occurred_at: occurredAt(data),
          method: value(data, "method"),
          outcome: value(data, "outcome"),
          seller_response: value(data, "seller_response") || null,
          notes: value(data, "notes") || null,
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));

      const result = (await response.json()) as OutsideOfferResponse;
      setStatus("saved");
      setMessage(
        result.stage_key === "negotiating"
          ? "Outside offer recorded. This lead is now in Negotiating."
          : "Outside offer recorded. This lead is now in Offer Presented.",
      );
      onRecorded?.(result);
      router.refresh();
      form.reset();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Unable to record the outside offer.");
    }
  }

  return (
    <div className={styles.offerStageAction}>
      <p className={styles.workflowNotice}>
        Choose the path that matches what actually happened with {sellerName}. Both paths keep the
        offer milestone backed by real facts instead of changing only a pipeline label.
      </p>
      <div className={styles.offerWorkflowOptions}>
        <Link
          className={styles.offerWorkflowOption}
          href={stonegateOfferHref}
        >
          <strong>
            {assetClass === "land" ? "Review Land valuation" : "Stonegate Valuation & Offer"}
          </strong>
          <span>
            {assetClass === "land"
              ? "Review parcel evidence and value guidance. Use Record an outside offer for an offer already presented."
              : "Review valuation, request offer authority, and manage the governed offer plan."}
          </span>
        </Link>
        <button
          aria-expanded={choice === "outside"}
          className={styles.offerWorkflowOption}
          onClick={() => {
            setChoice("outside");
            setStatus("idle");
            setMessage(null);
          }}
          type="button"
        >
          <strong>Record an outside offer</strong>
          <span>Capture an offer already presented by phone, text, email, video, or in person.</span>
        </button>
      </div>

      {choice === "outside" ? (
        <form className={`${styles.transactionForm} ${styles.outsideOfferForm}`} onSubmit={submitOutsideOffer}>
          <header>
            <strong>Offer already presented</strong>
            <p>
              Record the actual amount, timing, delivery method, and seller response. An accepted
              offer remains Offer Presented until a fully signed purchase agreement is recorded.
            </p>
          </header>
          <div className={styles.taskGrid}>
            <label>
              <span>Offer amount</span>
              <input min="0.01" name="amount" placeholder="170000" required step="0.01" type="number" />
            </label>
            <label>
              <span>Presented date and time</span>
              <input name="occurred_at" required type="datetime-local" />
            </label>
          </div>
          <div className={styles.taskGrid}>
            <label>
              <span>How it was presented</span>
              <select defaultValue="phone" name="method" required>
                <option value="phone">Phone</option>
                <option value="in_person">In person</option>
                <option value="sms">Text / SMS</option>
                <option value="email">Email</option>
                <option value="video">Video meeting</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label>
              <span>Seller outcome</span>
              <select defaultValue="presented" name="outcome" required>
                <option value="presented">Presented</option>
                <option value="considering">Considering</option>
                <option value="countered">Countered</option>
                <option value="negotiating">Negotiating</option>
                <option value="accepted">Verbally accepted</option>
                <option value="declined">Declined</option>
                <option value="no_response">No response</option>
                <option value="other">Other</option>
              </select>
            </label>
          </div>
          <label>
            <span>Seller response</span>
            <textarea
              maxLength={2000}
              name="seller_response"
              placeholder="What did the seller say or counter with?"
              rows={3}
            />
          </label>
          <label>
            <span>Internal notes</span>
            <textarea maxLength={2000} name="notes" rows={3} />
          </label>
          <div className={styles.transactionFormActions}>
            <button
              className={styles.secondaryFormAction}
              disabled={status === "saving"}
              onClick={() => {
                setChoice("choose");
                setStatus("idle");
                setMessage(null);
              }}
              type="button"
            >
              Back to offer choices
            </button>
            <button disabled={status === "saving" || status === "saved"} type="submit">
              {status === "saving"
                ? "Recording offer..."
                : status === "saved"
                  ? "Outside offer recorded"
                  : "Record outside offer"}
            </button>
          </div>
          {message ? (
            <p className={status === "error" ? styles.error : styles.saved} role={status === "error" ? "alert" : "status"}>
              {message}
            </p>
          ) : null}
        </form>
      ) : null}

      {onCancel ? (
        <button className={styles.offerActionCancel} onClick={onCancel} type="button">
          Cancel and keep current stage
        </button>
      ) : null}
    </div>
  );
}
