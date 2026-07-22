"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { LeadDetail } from "../../lib/api";
import styles from "./page.module.css";

type Validation = LeadDetail["property_validation"];
type Status = "idle" | "loading" | "error";

function statusLabel(status: Validation["status"]) {
  if (status === "provider_confirmed") return "Provider confirmed";
  if (status === "needs_review") return "Needs review";
  if (status === "not_found") return "Not found";
  return "Unverified";
}

function factValue(value: unknown) {
  if (typeof value === "number") return new Intl.NumberFormat("en-US").format(value);
  return typeof value === "string" && value ? value : null;
}

export function PropertyValidationControl({
  leadId,
  initialValidation,
}: {
  leadId: string;
  initialValidation: Validation;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [validation, setValidation] = useState(initialValidation);
  const [status, setStatus] = useState<Status>("idle");
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

  async function validateAddress() {
    setStatus("loading");
    setError(null);
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : { "X-Dev-User-Email": devUserEmail };
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/property-validation`,
        { method: "POST", headers },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Unable to validate the property address.");
      }
      setValidation((await response.json()) as Validation);
      setStatus("idle");
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to validate the property address.",
      );
      setStatus("error");
    }
  }

  const facts = [
    ["Type", factValue(validation.facts.propertyType)],
    ["Living area", factValue(validation.facts.squareFootage)],
    ["Year built", factValue(validation.facts.yearBuilt)],
  ].filter((item): item is string[] => Boolean(item[1]));

  return (
    <div className={styles.propertyValidation} data-status={validation.status}>
      <div className={styles.propertyValidationHeader}>
        <div>
          <span>Address record</span>
          <strong>{statusLabel(validation.status)}</strong>
          {validation.match_score !== null ? (
            <small>{validation.match_score}% match</small>
          ) : null}
        </div>
        <button disabled={status === "loading"} onClick={validateAddress} type="button">
          {status === "loading"
            ? "Checking..."
            : validation.status === "unverified"
              ? "Validate address"
              : "Refresh validation"}
        </button>
      </div>
      {validation.validated_address ? (
        <p>{validation.validated_address}</p>
      ) : null}
      {facts.length ? (
        <dl>
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}{label === "Living area" ? " sqft" : ""}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {validation.issues.length ? (
        <ul>
          {validation.issues.map((issue) => <li key={issue}>{issue}</li>)}
        </ul>
      ) : null}
      {error ? <p className={styles.error}>{error}</p> : null}
    </div>
  );
}
