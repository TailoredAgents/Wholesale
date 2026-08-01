"use client";

import { useAuth } from "@clerk/nextjs";
import { Check, FileClock, X } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type {
  UnderwritingCalibrationDecision,
  UnderwritingCalibrationMetric,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./calibration-governance.module.css";

type Draft = {
  scopeKey: string;
  decisionType: string;
  title: string;
  rationale: string;
  proposedVersion: string;
  changeSummary: string;
};

const emptyDraft: Draft = {
  scopeKey: "All markets",
  decisionType: "continue_current_method",
  title: "",
  rationale: "",
  proposedVersion: "",
  changeSummary: "",
};

export function CalibrationGovernance({
  markets,
  decisions,
}: {
  markets: UnderwritingCalibrationMetric[];
  decisions: UnderwritingCalibrationDecision[];
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [draft, setDraft] = useState(emptyDraft);
  const [decisionNotes, setDecisionNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
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

  async function headers() {
    const token = await getToken().catch(() => null);
    return {
      "Content-Type": "application/json",
      ...(token
        ? { Authorization: `Bearer ${token}` }
        : { "X-Dev-User-Email": devUserEmail }),
    };
  }

  function update(
    field: "scopeKey" | "decisionType" | "title" | "rationale" | "proposedVersion" | "changeSummary",
    value: string,
  ) {
    setDraft((current) => ({
      ...current,
      [field]: value,
    }));
    setMessage(null);
    setError(null);
  }

  async function request(path: string, init: RequestInit) {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: await headers(),
    });
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    if (!response.ok) {
      throw new Error(payload?.detail ?? "Unable to save the calibration decision.");
    }
    return payload;
  }

  async function createDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("create");
    setError(null);
    setMessage(null);
    try {
      await request("/api/v1/underwriting/calibration-decisions", {
        method: "POST",
        body: JSON.stringify({
          scope_key: draft.scopeKey,
          decision_type: draft.decisionType,
          title: draft.title,
          rationale: draft.rationale,
          proposed_methodology_version:
            draft.decisionType === "methodology_change"
              ? draft.proposedVersion || null
              : null,
          proposed_changes:
            draft.decisionType === "continue_current_method"
              ? {}
              : { summary: draft.changeSummary },
        }),
      });
      setDraft(emptyDraft);
      setMessage("Evidence snapshot and decision draft saved.");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create the decision.");
    } finally {
      setBusy(null);
    }
  }

  async function decide(id: string, status: "approved" | "rejected") {
    const notes = decisionNotes[id]?.trim();
    if (!notes) {
      setError("Enter decision notes before approving or rejecting.");
      return;
    }
    setBusy(id);
    setError(null);
    setMessage(null);
    try {
      await request(`/api/v1/underwriting/calibration-decisions/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status, decision_notes: notes }),
      });
      setMessage(`Decision ${status}.`);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to decide the proposal.");
    } finally {
      setBusy(null);
    }
  }

  const draftDecisions = decisions.filter((item) => item.status === "draft");

  return (
    <section className={styles.governance}>
      <header>
        <div>
          <span>Method control</span>
          <h3>Calibration decisions</h3>
        </div>
        <strong>{draftDecisions.length} open</strong>
      </header>
      <div className={styles.layout}>
        <form className={styles.form} onSubmit={createDecision}>
          <div className={styles.formHeading}>
            <FileClock size={18} />
            <div>
              <strong>Record a review</strong>
              <span>The current scorecard is frozen into the decision record.</span>
            </div>
          </div>
          <div className={styles.fields}>
            <label>
              Market
              <select
                onChange={(event) => update("scopeKey", event.target.value)}
                value={draft.scopeKey}
              >
                <option value="All markets">All markets</option>
                {markets.map((market) => (
                  <option key={market.market_key} value={market.market_key}>
                    {market.market_key}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Decision
              <select
                onChange={(event) => update("decisionType", event.target.value)}
                value={draft.decisionType}
              >
                <option value="continue_current_method">Continue current method</option>
                <option value="methodology_change">Propose formula change</option>
                <option value="provider_change">Propose provider change</option>
              </select>
            </label>
            <label className={styles.wide}>
              Review title
              <input
                maxLength={255}
                onChange={(event) => update("title", event.target.value)}
                placeholder="Quarterly Fulton County calibration review"
                required
                value={draft.title}
              />
            </label>
            {draft.decisionType === "methodology_change" ? (
              <label>
                Proposed version
                <input
                  maxLength={80}
                  onChange={(event) => update("proposedVersion", event.target.value)}
                  placeholder="v2.2-candidate"
                  required
                  value={draft.proposedVersion}
                />
              </label>
            ) : null}
            {draft.decisionType !== "continue_current_method" ? (
              <label className={styles.wide}>
                Proposed change
                <textarea
                  maxLength={1000}
                  onChange={(event) => update("changeSummary", event.target.value)}
                  placeholder="State exactly what should change and why."
                  required
                  rows={3}
                  value={draft.changeSummary}
                />
              </label>
            ) : null}
            <label className={styles.wide}>
              Evidence rationale
              <textarea
                maxLength={3000}
                minLength={10}
                onChange={(event) => update("rationale", event.target.value)}
                placeholder="Explain what the verified outcomes support."
                required
                rows={4}
                value={draft.rationale}
              />
            </label>
          </div>
          <button disabled={busy === "create"} type="submit">
            {busy === "create" ? "Saving..." : "Save decision draft"}
          </button>
        </form>

        <div className={styles.ledger}>
          {decisions.length === 0 ? (
            <div className={styles.empty}>
              No methodology decisions have been recorded.
            </div>
          ) : null}
          {decisions.map((decision) => (
            <article key={decision.id}>
              <div className={styles.decisionHeader}>
                <div>
                  <strong>{decision.title}</strong>
                  <span>
                    {decision.scope_key} / {labelize(decision.decision_type)}
                  </span>
                </div>
                <span data-status={decision.status}>{labelize(decision.status)}</span>
              </div>
              <p>{decision.rationale}</p>
              <dl>
                <div>
                  <dt>Evidence</dt>
                  <dd>{decision.sample_count} verified cases</dd>
                </div>
                <div>
                  <dt>Method</dt>
                  <dd>
                    {decision.current_methodology_version ?? "Unversioned"}
                    {decision.proposed_methodology_version
                      ? ` to ${decision.proposed_methodology_version}`
                      : ""}
                  </dd>
                </div>
              </dl>
              {decision.approval_blocked ? (
                <p className={styles.blocked}>
                  Approval unlocks at {decision.minimum_sample_required} verified cases.
                </p>
              ) : null}
              {decision.status === "draft" ? (
                <div className={styles.actions}>
                  <input
                    aria-label={`Decision notes for ${decision.title}`}
                    maxLength={2000}
                    onChange={(event) =>
                      setDecisionNotes((current) => ({
                        ...current,
                        [decision.id]: event.target.value,
                      }))
                    }
                    placeholder="Required decision notes"
                    value={decisionNotes[decision.id] ?? ""}
                  />
                  <button
                    aria-label={`Reject ${decision.title}`}
                    className={styles.reject}
                    disabled={busy === decision.id}
                    onClick={() => void decide(decision.id, "rejected")}
                    title="Reject decision"
                    type="button"
                  >
                    <X size={15} />
                  </button>
                  <button
                    aria-label={`Approve ${decision.title}`}
                    disabled={busy === decision.id || decision.approval_blocked}
                    onClick={() => void decide(decision.id, "approved")}
                    title={
                      decision.approval_blocked
                        ? "Minimum verified sample not reached"
                        : "Approve decision"
                    }
                    type="button"
                  >
                    <Check size={15} />
                  </button>
                </div>
              ) : (
                <small>{decision.decision_notes}</small>
              )}
            </article>
          ))}
        </div>
      </div>
      <div aria-live="polite" className={styles.feedback}>
        {error ? <span data-tone="error">{error}</span> : null}
        {message ? <span data-tone="success">{message}</span> : null}
      </div>
    </section>
  );
}
