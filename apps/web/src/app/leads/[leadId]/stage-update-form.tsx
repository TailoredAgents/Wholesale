"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ExecutedContractImportForm } from "./executed-contract-import-form";
import { OfferStageAction } from "./offer-stage-action";
import styles from "./page.module.css";

const stages = [
  ["new", "New"],
  ["contact_attempt_due", "Contact attempt due"],
  ["attempting_contact", "Attempting contact"],
  ["contacted", "Contacted"],
  ["qualification_in_progress", "Qualification in progress"],
  ["qualified", "Qualified"],
  ["appointment_scheduling", "Appointment scheduling"],
  ["appointment_scheduled", "Appointment scheduled"],
  ["underwriting", "Underwriting"],
  ["long_term_follow_up", "Long-term follow-up"],
];

const lifecycleStageLabels: Record<string, string> = {
  dead: "Dead",
  disqualified: "Disqualified",
  reopened: "Reopened",
};

const offerWorkflowStages = new Set([
  "offer_pending_approval",
  "offer_ready",
  "offer_presented",
  "negotiating",
]);

const offerWorkflowStageLabels: Record<string, string> = {
  offer_pending_approval: "Offer pending approval",
  offer_ready: "Offer ready",
  offer_presented: "Offer presented",
  negotiating: "Negotiating",
};

type Status = "idle" | "saving" | "saved" | "error";

export function StageUpdateForm({
  assetClass,
  canEditLead,
  canImportExecutedContract,
  canRecordOutsideOffer,
  hasExecutedTransaction,
  leadId,
  currentStage,
  sellerName,
}: {
  assetClass: "house" | "land";
  canEditLead: boolean;
  canImportExecutedContract: boolean;
  canRecordOutsideOffer: boolean;
  hasExecutedTransaction: boolean;
  leadId: string;
  currentStage: string;
  sellerName: string;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const selectRef = useRef<HTMLSelectElement>(null);
  const [selectedStage, setSelectedStage] = useState(currentStage);
  const [status, setStatus] = useState<Status>("idle");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  if (currentStage === "under_contract") {
    return <p>Use Contract & Deal to manage the signed contract.</p>;
  }

  const canUseExecutedContractShortcut =
    canImportExecutedContract && !hasExecutedTransaction;
  const canUseAnyStageAction =
    canEditLead || canRecordOutsideOffer || canUseExecutedContractShortcut;

  if (!canUseAnyStageAction) {
    return <p>You do not have access to update this lead or record offer and contract evidence.</p>;
  }

  function cancelExecutedContractImport() {
    setSelectedStage(currentStage);
    setStatus("idle");
    requestAnimationFrame(() => selectRef.current?.focus());
  }

  function cancelOfferAction() {
    setSelectedStage(currentStage);
    setStatus("idle");
    requestAnimationFrame(() => selectRef.current?.focus());
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const requestedStage = String(formData.get("stage_key") ?? currentStage);
    if (requestedStage === "offer_action") {
      // Offer is also an action shortcut. The user must either enter the governed Stonegate
      // workflow or record the real outside offer before an offer milestone is stored.
      setSelectedStage("offer_action");
      setStatus("idle");
      return;
    }
    if (requestedStage === "under_contract") {
      // Under Contract is an action shortcut, never a generic stage mutation. The signed-contract
      // import below creates the transaction evidence and advances the stage atomically.
      setSelectedStage("under_contract");
      setStatus("idle");
      return;
    }
    if (!canEditLead) {
      setStatus("error");
      return;
    }
    setStatus("saving");

    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      } else {
        headers["X-Dev-User-Email"] = devUserEmail;
      }
      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/stage`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({
          stage_key: requestedStage,
          expected_stage_key: currentStage,
          reason: String(formData.get("reason") ?? "").trim() || null,
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to update lead stage.");
      }

      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className={styles.stageActionFlow}>
      <form className={styles.stageForm} onSubmit={handleSubmit}>
      {offerWorkflowStages.has(currentStage) ? (
        <p>
          Use Valuation &amp; Offer to advance the offer. This control can only move the lead back
          to a normal pipeline stage when the offer needs correction or follow-up.
        </p>
      ) : null}
      <label>
        <span>Stage</span>
        <select
          name="stage_key"
          onChange={(event) => {
            setSelectedStage(event.target.value);
            setStatus("idle");
          }}
          ref={selectRef}
          value={selectedStage}
        >
          {offerWorkflowStageLabels[currentStage] ? (
            <option disabled value={currentStage}>{offerWorkflowStageLabels[currentStage]}</option>
          ) : null}
          {lifecycleStageLabels[currentStage] ? (
            <option disabled value={currentStage}>{lifecycleStageLabels[currentStage]}</option>
          ) : null}
          {!canEditLead && !offerWorkflowStageLabels[currentStage] && !lifecycleStageLabels[currentStage] ? (
            <option disabled value={currentStage}>
              {currentStage.split("_").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ")}
            </option>
          ) : null}
          {canEditLead
            ? stages.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))
            : null}
          {canRecordOutsideOffer ? (
            <option value="offer_action">Offer - choose workflow</option>
          ) : null}
          {canUseExecutedContractShortcut ? (
            <option value="under_contract">Under Contract - record signed agreement</option>
          ) : null}
        </select>
      </label>
        {canEditLead && !["offer_action", "under_contract"].includes(selectedStage) ? (
          <>
            <label>
              <span>Reason</span>
              <input
                minLength={offerWorkflowStages.has(currentStage) ? 10 : undefined}
                name="reason"
                placeholder={offerWorkflowStages.has(currentStage) ? "Why is this offer moving back?" : "Optional audit note"}
                required={offerWorkflowStages.has(currentStage)}
              />
            </label>
            <button disabled={status === "saving"} type="submit">
              Update stage
            </button>
            {status !== "idle" ? <p className={styles[status]}>{status}</p> : null}
          </>
        ) : !["offer_action", "under_contract"].includes(selectedStage) ? (
          <p>Select an available evidence-backed action.</p>
        ) : null}
      </form>
      {selectedStage === "offer_action" && canRecordOutsideOffer ? (
        <section aria-labelledby="offer-stage-shortcut-heading" className={styles.stageWorkflowAction}>
          <header>
            <strong id="offer-stage-shortcut-heading">Choose how this offer happened</strong>
            <p>
              Continue in Stonegate or record an offer already presented outside the CRM.
            </p>
          </header>
          <OfferStageAction
            assetClass={assetClass}
            expectedStageKey={currentStage}
            leadId={leadId}
            onCancel={cancelOfferAction}
            onRecorded={() => setStatus("saved")}
            sellerName={sellerName}
          />
        </section>
      ) : null}
      {selectedStage === "under_contract" && canUseExecutedContractShortcut ? (
        <section aria-labelledby="signed-contract-shortcut-heading" className={styles.stageWorkflowAction}>
          <header>
            <strong id="signed-contract-shortcut-heading">Record the signed agreement</strong>
            <p>
              Under Contract requires the actual executed purchase agreement. Upload it here and
              Stonegate will move the deal safely and open Dispositions.
            </p>
          </header>
          <ExecutedContractImportForm
            leadId={leadId}
            onCancel={cancelExecutedContractImport}
            sellerName={sellerName}
          />
        </section>
      ) : null}
    </div>
  );
}
