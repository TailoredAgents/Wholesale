"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  BookOpenCheck,
  CheckCircle2,
  FileCheck2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { ComplianceOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./compliance.module.css";

type Section = "policies" | "dnc" | "training" | "incidents" | "controls";

export function ComplianceWorkspace({
  compliance,
}: {
  compliance: ComplianceOverview;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [section, setSection] = useState<Section>("policies");
  const [busy, setBusy] = useState("");
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

  async function request(path: string, method: string, body?: object) {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    setBusy(path);
    setMessage("");
    const response = await fetch(`${apiBaseUrl}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    if (!response.ok) {
      setMessage(payload?.detail ?? "The compliance action could not be completed.");
      setBusy("");
      return false;
    }
    setMessage("Compliance record updated.");
    setBusy("");
    router.refresh();
    return true;
  }

  async function recordLegalReview(
    event: FormEvent<HTMLFormElement>,
    policyId: string,
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await request(`/api/v1/compliance/policies/${policyId}/legal-review`, "PATCH", {
      legal_reviewer_name: String(data.get("reviewer_name") ?? ""),
      legal_reviewer_company: String(data.get("reviewer_company") ?? ""),
      legal_evidence_reference: String(data.get("evidence_reference") ?? ""),
      legal_reviewed_at: new Date(String(data.get("reviewed_at"))).toISOString(),
      review_due_at: new Date(String(data.get("review_due_at"))).toISOString(),
      notes: String(data.get("notes") ?? "") || null,
    });
  }

  async function addDncSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (
      await request("/api/v1/compliance/dnc-sources", "POST", {
        name: String(data.get("name") ?? ""),
        provider_type: String(data.get("provider_type") ?? ""),
        account_reference: String(data.get("account_reference") ?? "") || null,
        coverage_area_codes: String(data.get("coverage_area_codes") ?? "")
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
        refresh_interval_days: 31,
        notes: String(data.get("notes") ?? "") || null,
      })
    ) {
      event.currentTarget.reset();
    }
  }

  async function refreshDnc(event: FormEvent<HTMLFormElement>, sourceId: string) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await request(`/api/v1/compliance/dnc-sources/${sourceId}/refresh`, "POST", {
      refreshed_at: new Date().toISOString(),
      evidence_reference: String(data.get("evidence_reference") ?? ""),
      notes: String(data.get("notes") ?? "") || null,
    });
  }

  async function assignTraining(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await request("/api/v1/compliance/training", "POST", {
      user_id: String(data.get("user_id") ?? ""),
      training_key: String(data.get("training_key") ?? ""),
      training_version: String(data.get("training_version") ?? "1.0"),
    });
  }

  async function addIncident(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await request("/api/v1/compliance/incidents", "POST", {
      incident_type: String(data.get("incident_type") ?? ""),
      channel: String(data.get("channel") ?? ""),
      severity: String(data.get("severity") ?? ""),
      summary: String(data.get("summary") ?? ""),
      details: String(data.get("details") ?? "") || null,
    });
  }

  const latestRun = compliance.control_runs[0];

  return (
    <div className={styles.workspace}>
      <nav aria-label="Compliance areas" className={styles.tabs}>
        {(["policies", "dnc", "training", "incidents", "controls"] as Section[]).map(
          (item) => (
            <button
              aria-current={section === item ? "page" : undefined}
              key={item}
              onClick={() => setSection(item)}
              type="button"
            >
              {labelize(item)}
            </button>
          ),
        )}
      </nav>
      {message ? <p className={styles.feedback}>{message}</p> : null}

      {section === "policies" ? (
        <section className={styles.panel}>
          <header className={styles.panelHeader}>
            <div>
              <span>Versioned control</span>
              <h2>Communication policies</h2>
            </div>
            {!compliance.policies.length ? (
              <button
                disabled={Boolean(busy)}
                onClick={() => request("/api/v1/compliance/install", "POST")}
                type="button"
              >
                <ShieldCheck aria-hidden="true" /> Install policy set
              </button>
            ) : null}
          </header>
          <div className={styles.grid}>
            {compliance.policies.map((policy) => (
              <article className={styles.card} key={policy.id}>
                <header>
                  <div>
                    <span>{labelize(policy.policy_key)}</span>
                    <h3>{policy.name}</h3>
                  </div>
                  <strong data-status={policy.status}>{labelize(policy.status)}</strong>
                </header>
                <dl>
                  <div>
                    <dt>Legal review</dt>
                    <dd>{labelize(policy.legal_review_status)}</dd>
                  </div>
                  <div>
                    <dt>Review due</dt>
                    <dd>
                      {policy.review_due_at
                        ? new Date(policy.review_due_at).toLocaleDateString()
                        : "Not recorded"}
                    </dd>
                  </div>
                </dl>
                {policy.legal_review_status !== "approved" ? (
                  <form onSubmit={(event) => recordLegalReview(event, policy.id)}>
                    <div className={styles.twoColumns}>
                      <label>
                        <span>Reviewer</span>
                        <input name="reviewer_name" required />
                      </label>
                      <label>
                        <span>Firm</span>
                        <input name="reviewer_company" required />
                      </label>
                    </div>
                    <label>
                      <span>Evidence reference</span>
                      <input name="evidence_reference" required />
                    </label>
                    <div className={styles.twoColumns}>
                      <label>
                        <span>Reviewed</span>
                        <input name="reviewed_at" required type="date" />
                      </label>
                      <label>
                        <span>Review due</span>
                        <input name="review_due_at" required type="date" />
                      </label>
                    </div>
                    <button disabled={Boolean(busy)} type="submit">
                      <FileCheck2 aria-hidden="true" /> Record review
                    </button>
                  </form>
                ) : policy.status !== "active" ? (
                  <button
                    disabled={Boolean(busy)}
                    onClick={() =>
                      request(
                        `/api/v1/compliance/policies/${policy.id}/decision`,
                        "POST",
                        {
                          decision: "approve",
                          reason: "Owner approved reviewed policy for operations.",
                        },
                      )
                    }
                    type="button"
                  >
                    <CheckCircle2 aria-hidden="true" /> Activate policy
                  </button>
                ) : (
                  <p className={styles.current}>
                    <CheckCircle2 aria-hidden="true" /> Active operating policy
                  </p>
                )}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {section === "dnc" ? (
        <section className={styles.panel}>
          <header className={styles.panelHeader}>
            <div>
              <span>31-day control</span>
              <h2>DNC screening evidence</h2>
            </div>
          </header>
          <form className={styles.entryForm} onSubmit={addDncSource}>
            <div className={styles.formGrid}>
              <label>
                <span>Source name</span>
                <input name="name" required />
              </label>
              <label>
                <span>Provider type</span>
                <select name="provider_type">
                  <option value="ftc_registry">FTC registry</option>
                  <option value="third_party">Third-party provider</option>
                  <option value="manual_review">Manual review</option>
                </select>
              </label>
              <label>
                <span>Account reference</span>
                <input name="account_reference" />
              </label>
              <label>
                <span>Covered area codes</span>
                <input name="coverage_area_codes" placeholder="404, 470, 678, 770" />
              </label>
            </div>
            <button disabled={Boolean(busy)} type="submit">
              Add screening source
            </button>
          </form>
          <div className={styles.stack}>
            {compliance.dnc_sources.map((source) => (
              <article className={styles.row} key={source.id}>
                <div>
                  <span>{labelize(source.provider_type)}</span>
                  <h3>{source.name}</h3>
                  <p>
                    {source.next_refresh_due_at
                      ? `Next evidence due ${new Date(source.next_refresh_due_at).toLocaleDateString()}`
                      : "Refresh evidence not recorded"}
                  </p>
                </div>
                {source.status === "draft" ? (
                  <button
                    onClick={() =>
                      request(
                        `/api/v1/compliance/dnc-sources/${source.id}/decision`,
                        "POST",
                        { decision: "approve", reason: "Owner approved DNC source." },
                      )
                    }
                    type="button"
                  >
                    Approve
                  </button>
                ) : (
                  <form
                    className={styles.inlineForm}
                    onSubmit={(event) => refreshDnc(event, source.id)}
                  >
                    <input
                      name="evidence_reference"
                      placeholder="Evidence URL or file reference"
                      required
                    />
                    <button type="submit">
                      <RefreshCw aria-hidden="true" /> Record refresh
                    </button>
                  </form>
                )}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {section === "training" ? (
        <section className={styles.panel}>
          <header className={styles.panelHeader}>
            <div>
              <span>Staff evidence</span>
              <h2>Training assignments</h2>
            </div>
          </header>
          <form className={styles.entryForm} onSubmit={assignTraining}>
            <div className={styles.formGrid}>
              <label>
                <span>Team member</span>
                <select name="user_id">
                  {compliance.users
                    .filter((user) => user.is_active)
                    .map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.display_name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                <span>Training</span>
                <select name="training_key">
                  <option value="outbound_contact">Outbound contact</option>
                  <option value="sms_email_consent">SMS and email consent</option>
                  <option value="recording_disclosure">Recording disclosure</option>
                  <option value="complaints_and_escalation">
                    Complaints and escalation
                  </option>
                </select>
              </label>
              <label>
                <span>Version</span>
                <input defaultValue="1.0" name="training_version" />
              </label>
            </div>
            <button disabled={Boolean(busy)} type="submit">
              <BookOpenCheck aria-hidden="true" /> Assign training
            </button>
          </form>
          <div className={styles.stack}>
            {compliance.training_records.map((record) => (
              <article className={styles.row} key={record.id}>
                <div>
                  <span>{labelize(record.training_key)}</span>
                  <h3>{record.user_name}</h3>
                  <p>Version {record.training_version}</p>
                </div>
                <strong data-status={record.status}>{labelize(record.status)}</strong>
                {record.status === "submitted" ? (
                  <button
                    onClick={() =>
                      request(
                        `/api/v1/compliance/training/${record.id}/decision`,
                        "POST",
                        {
                          decision: "approve",
                          manager_notes: "Training evidence reviewed and approved.",
                          score_basis_points: 10000,
                        },
                      )
                    }
                    type="button"
                  >
                    Approve
                  </button>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {section === "incidents" ? (
        <section className={styles.panel}>
          <header className={styles.panelHeader}>
            <div>
              <span>Exception register</span>
              <h2>Compliance incidents</h2>
            </div>
          </header>
          <form className={styles.entryForm} onSubmit={addIncident}>
            <div className={styles.formGrid}>
              <label>
                <span>Type</span>
                <select name="incident_type">
                  <option value="complaint">Complaint</option>
                  <option value="wrong_number">Wrong number</option>
                  <option value="do_not_contact">Do not contact</option>
                  <option value="recording_objection">Recording objection</option>
                  <option value="policy_exception">Policy exception</option>
                  <option value="provider_failure">Provider failure</option>
                </select>
              </label>
              <label>
                <span>Channel</span>
                <select name="channel">
                  <option value="phone">Phone</option>
                  <option value="sms">SMS</option>
                  <option value="email">Email</option>
                  <option value="recording">Recording</option>
                  <option value="all">All</option>
                </select>
              </label>
              <label>
                <span>Severity</span>
                <select name="severity">
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </label>
              <label>
                <span>Summary</span>
                <input name="summary" required />
              </label>
            </div>
            <button disabled={Boolean(busy)} type="submit">
              <AlertTriangle aria-hidden="true" /> Record incident
            </button>
          </form>
          <div className={styles.stack}>
            {compliance.incidents.map((incident) => (
              <article className={styles.row} key={incident.id}>
                <div>
                  <span>
                    {labelize(incident.incident_type)} · {labelize(incident.channel)}
                  </span>
                  <h3>{incident.summary}</h3>
                  <p>{new Date(incident.occurred_at).toLocaleString()}</p>
                </div>
                <strong data-status={incident.status}>{labelize(incident.status)}</strong>
                {incident.status === "open" ? (
                  <button
                    onClick={() =>
                      request(
                        `/api/v1/compliance/incidents/${incident.id}/resolve`,
                        "POST",
                        { resolution: "Owner reviewed and resolved this incident." },
                      )
                    }
                    type="button"
                  >
                    Resolve
                  </button>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {section === "controls" ? (
        <section className={styles.panel}>
          <header className={styles.panelHeader}>
            <div>
              <span>Repeatable verification</span>
              <h2>Control run</h2>
            </div>
            <button
              disabled={Boolean(busy)}
              onClick={() => request("/api/v1/compliance/control-runs", "POST")}
              type="button"
            >
              <RefreshCw aria-hidden="true" /> Run controls
            </button>
          </header>
          {latestRun ? (
            <div className={styles.stack}>
              {latestRun.results.map((result) => (
                <article className={styles.control} key={result.key}>
                  {result.status === "pass" ? (
                    <CheckCircle2 aria-hidden="true" />
                  ) : (
                    <AlertTriangle aria-hidden="true" />
                  )}
                  <div>
                    <h3>{result.label}</h3>
                    <p>{result.detail}</p>
                  </div>
                  <strong data-status={result.status}>{labelize(result.status)}</strong>
                </article>
              ))}
            </div>
          ) : (
            <p className={styles.emptyState}>No control run has been recorded.</p>
          )}
        </section>
      ) : null}
    </div>
  );
}
