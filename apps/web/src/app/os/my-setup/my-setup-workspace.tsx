"use client";

import { useAuth } from "@clerk/nextjs";
import { BookOpenCheck, CheckCircle2, ClipboardCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { ComplianceTraining, MyRoleSetup } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./my-setup.module.css";

const manualStandards: Record<string, string[]> = {
  owner: [
    "Set policy, staffing, approval authority, and market priorities.",
    "Approve employee setup only after testing access and restrictions.",
    "Review exceptions without changing historical evidence.",
  ],
  lead_manager: [
    "Respond to warm leads, qualify the seller, and schedule appropriate appointments.",
    "Keep an owner, next action, and due date on every active lead.",
    "Do not promise price or bypass communication restrictions.",
  ],
  va_caller: [
    "Work only assigned calling batches and the approved script.",
    "Record an accurate disposition and preserve every opt-out.",
    "Create a warm handoff only when the seller shows genuine interest.",
  ],
  closer: [
    "Review the meeting brief and unresolved questions before the appointment.",
    "Negotiate only within approved authority and record the outcome.",
    "Do not alter approved offer limits without the required approval.",
  ],
  transaction_coordinator: [
    "Own deadlines and evidence from signed contract through funded closing.",
    "Escalate missing or conflicting evidence instead of completing a blocked gate.",
    "Do not make legal decisions or fabricate provider status.",
  ],
  dispositions: [
    "Prepare approved packages and match only appropriate, verified buyers.",
    "Track offers, proof of funds, deposits, primary buyer, and backup buyer.",
    "Do not release a package or select a buyer by bypassing approval.",
  ],
  finance: [
    "Record source-linked revenue, costs, compensation, and payouts.",
    "Reconcile funded deals before commissions become payable.",
    "Correct errors through traceable adjustments, not deleted history.",
  ],
  marketing: [
    "Maintain campaign source, cost, consent, and conversion evidence.",
    "Use approved audiences, suppression controls, and company senders.",
    "Do not treat modeled attribution as confirmed revenue.",
  ],
};

export function MySetupWorkspace({
  roleSetup,
  training,
}: {
  roleSetup: MyRoleSetup;
  training: ComplianceTraining[];
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [savingId, setSavingId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
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

  async function submitAcceptance(
    event: FormEvent<HTMLFormElement>,
    acceptanceId: string,
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;

    setSavingId(acceptanceId);
    setMessage("");
    const response = await fetch(
      `${apiBaseUrl}/api/v1/operating-model/my-setup/role-acceptances/${acceptanceId}/submit`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          workspace_test_evidence: String(data.get("workspace_test_evidence") ?? ""),
          employee_notes: String(data.get("employee_notes") ?? "") || null,
        }),
      },
    );
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      setMessage(payload?.detail ?? "The workspace test could not be submitted.");
      setSavingId(null);
      return;
    }
    setMessage("Workspace test submitted for manager approval.");
    setSavingId(null);
    router.refresh();
  }

  async function submitTraining(
    event: FormEvent<HTMLFormElement>,
    trainingId: string,
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    setSavingId(trainingId);
    setMessage("");
    const response = await fetch(
      `${apiBaseUrl}/api/v1/compliance/my-training/${trainingId}/submit`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          completion_evidence: String(data.get("completion_evidence") ?? ""),
          employee_attestation: String(data.get("employee_attestation") ?? ""),
        }),
      },
    );
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      setMessage(payload?.detail ?? "Training evidence could not be submitted.");
      setSavingId(null);
      return;
    }
    setMessage("Training evidence submitted for manager approval.");
    setSavingId(null);
    router.refresh();
  }

  return (
    <div className={styles.workspace}>
      <section className={styles.summary}>
        <div>
          <span>Team member</span>
          <strong>{roleSetup.user_name}</strong>
        </div>
        <div>
          <span>Assigned roles</span>
          <strong>{roleSetup.role_keys.map(labelize).join(", ")}</strong>
        </div>
        <div>
          <span>Approved</span>
          <strong>
            {
              roleSetup.acceptances.filter((item) => item.status === "approved")
                .length
            }
            /{roleSetup.acceptances.length}
          </strong>
        </div>
      </section>

      {message ? <p className={styles.feedback}>{message}</p> : null}

      <div className={styles.acceptances}>
        {roleSetup.acceptances.map((acceptance) => {
          const submitted = ["submitted", "approved"].includes(acceptance.status);
          return (
            <article className={styles.acceptance} key={acceptance.id}>
              <header>
                <div className={styles.icon}>
                  {acceptance.status === "approved" ? (
                    <CheckCircle2 aria-hidden="true" />
                  ) : (
                    <BookOpenCheck aria-hidden="true" />
                  )}
                </div>
                <div>
                  <span>{labelize(acceptance.role_key)}</span>
                  <h2>{labelize(acceptance.manual_key)} role manual</h2>
                  <p>Version {acceptance.manual_version}</p>
                </div>
                <strong data-status={acceptance.status}>
                  {labelize(acceptance.status)}
                </strong>
              </header>

              <div className={styles.instructions}>
                <ClipboardCheck aria-hidden="true" />
                <p>
                  Review your role instructions, then test the pages and actions used in
                  your normal work. Record what you tested and confirm that restricted
                  areas are not available.
                </p>
              </div>

              <div className={styles.standards}>
                <strong>Role standards</strong>
                <ul>
                  {(manualStandards[acceptance.manual_key] ?? []).map((standard) => (
                    <li key={standard}>{standard}</li>
                  ))}
                </ul>
              </div>

              {submitted ? (
                <dl>
                  <div>
                    <dt>Workspace test</dt>
                    <dd>{acceptance.workspace_test_evidence}</dd>
                  </div>
                  {acceptance.employee_notes ? (
                    <div>
                      <dt>Your notes</dt>
                      <dd>{acceptance.employee_notes}</dd>
                    </div>
                  ) : null}
                  {acceptance.manager_notes ? (
                    <div>
                      <dt>Manager review</dt>
                      <dd>{acceptance.manager_notes}</dd>
                    </div>
                  ) : null}
                </dl>
              ) : (
                <form onSubmit={(event) => submitAcceptance(event, acceptance.id)}>
                  <label>
                    <span>What did you test?</span>
                    <textarea
                      minLength={10}
                      name="workspace_test_evidence"
                      placeholder="Example: Opened my assigned leads, reviewed a conversation, and created a follow-up task."
                      required
                      rows={4}
                    />
                  </label>
                  <label>
                    <span>Notes for your manager</span>
                    <textarea name="employee_notes" rows={2} />
                  </label>
                  <button disabled={savingId === acceptance.id} type="submit">
                    {savingId === acceptance.id
                      ? "Submitting..."
                      : "Submit workspace test"}
                  </button>
                </form>
              )}
            </article>
          );
        })}
        {!roleSetup.acceptances.length ? (
          <section className={styles.empty}>
            <BookOpenCheck aria-hidden="true" />
            <h2>No role manual is assigned yet</h2>
            <p>Your manager will assign the correct manual and workspace test.</p>
          </section>
        ) : null}
      </div>

      <div className={styles.sectionHeading}>
        <div>
          <span>Required controls</span>
          <h2>Compliance training</h2>
        </div>
        <strong>
          {training.filter((item) => item.status === "approved").length}/
          {training.length} approved
        </strong>
      </div>
      <div className={styles.acceptances}>
        {training.map((item) => {
          const submitted = ["submitted", "approved"].includes(item.status);
          return (
            <article className={styles.acceptance} key={item.id}>
              <header>
                <div className={styles.icon}>
                  {item.status === "approved" ? (
                    <CheckCircle2 aria-hidden="true" />
                  ) : (
                    <BookOpenCheck aria-hidden="true" />
                  )}
                </div>
                <div>
                  <span>{labelize(item.training_key)}</span>
                  <h2>Compliance training</h2>
                  <p>Version {item.training_version}</p>
                </div>
                <strong data-status={item.status}>{labelize(item.status)}</strong>
              </header>
              {submitted ? (
                <dl>
                  <div>
                    <dt>Completion evidence</dt>
                    <dd>{item.completion_evidence}</dd>
                  </div>
                  <div>
                    <dt>Attestation</dt>
                    <dd>{item.employee_attestation}</dd>
                  </div>
                  {item.manager_notes ? (
                    <div>
                      <dt>Manager review</dt>
                      <dd>{item.manager_notes}</dd>
                    </div>
                  ) : null}
                </dl>
              ) : (
                <form onSubmit={(event) => submitTraining(event, item.id)}>
                  <label>
                    <span>Completion evidence</span>
                    <textarea
                      minLength={3}
                      name="completion_evidence"
                      placeholder="Training completed and scenarios reviewed."
                      required
                      rows={3}
                    />
                  </label>
                  <label>
                    <span>Employee attestation</span>
                    <textarea
                      minLength={10}
                      name="employee_attestation"
                      placeholder="I understand and will follow Stonegate's approved communication policy."
                      required
                      rows={3}
                    />
                  </label>
                  <button disabled={savingId === item.id} type="submit">
                    {savingId === item.id ? "Submitting..." : "Submit training"}
                  </button>
                </form>
              )}
            </article>
          );
        })}
        {!training.length ? (
          <section className={styles.empty}>
            <BookOpenCheck aria-hidden="true" />
            <h2>No compliance training assigned</h2>
            <p>Your manager assigns training from the Compliance workspace.</p>
          </section>
        ) : null}
      </div>
    </div>
  );
}
