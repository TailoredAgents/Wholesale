"use client";

import { useAuth } from "@clerk/nextjs";
import {
  CirclePause,
  CirclePlay,
  FlaskConical,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Square,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type {
  MarketingExperiment,
  MarketingExperimentOverview,
} from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import styles from "./experiment-workspace.module.css";

type RequestStatus = "idle" | "saving" | "saved" | "error";

function value(data: FormData, key: string) {
  return String(data.get(key) ?? "").trim();
}

function numberValue(data: FormData, key: string) {
  return Number(value(data, key));
}

function tone(status: string) {
  if (["running", "ready_for_human_review"].includes(status)) return "success";
  if (["paused", "collecting_data"].includes(status)) return "warning";
  return "neutral";
}

function percent(basisPoints: number | null) {
  return basisPoints === null ? "No baseline" : `${(basisPoints / 100).toFixed(1)}%`;
}

function money(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function experimentPayload(data: FormData) {
  return {
    experiment_key: value(data, "experiment_key"),
    name: value(data, "name"),
    hypothesis: value(data, "hypothesis"),
    surface_key: "homepage_offer_cta",
    primary_metric: value(data, "primary_metric"),
    variants: [
      {
        key: "control",
        label: "Current CTA",
        weight_basis_points: 5000,
        cta_label: value(data, "control_cta"),
      },
      {
        key: "treatment",
        label: "Test CTA",
        weight_basis_points: 5000,
        cta_label: value(data, "treatment_cta"),
      },
    ],
    minimum_sessions_per_variant: numberValue(data, "minimum_sessions_per_variant"),
    minimum_runtime_days: numberValue(data, "minimum_runtime_days"),
    decision_rule: value(data, "decision_rule"),
  };
}

export function ExperimentWorkspace({
  initialData,
  apiConnected,
}: {
  initialData: MarketingExperimentOverview;
  apiConnected: boolean;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [editingId, setEditingId] = useState<string | null>(
    () =>
      initialData.experiments.find((experiment) => experiment.status === "running")?.id ??
      initialData.experiments[0]?.id ??
      null,
  );
  const [status, setStatus] = useState<RequestStatus>("idle");
  const [message, setMessage] = useState("");
  const selected =
    initialData.experiments.find((experiment) => experiment.id === editingId) ?? null;
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
    const result: Record<string, string> = { "Content-Type": "application/json" };
    if (token) result.Authorization = `Bearer ${token}`;
    else result["X-Dev-User-Email"] = devUserEmail;
    return result;
  }

  async function mutate(
    path: string,
    method: "POST" | "PUT",
    body: object,
  ): Promise<{ id?: string } | null> {
    setStatus("saving");
    setMessage("");
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers: await headers(),
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(payload?.detail ?? "The experiment operation could not be completed.");
      }
      const payload = (await response.json()) as { id?: string };
      setStatus("saved");
      setMessage("Experiment record updated.");
      router.refresh();
      return payload;
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof Error
          ? error.message
          : "The experiment operation could not be completed.",
      );
      return null;
    }
  }

  async function saveExperiment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const saved = await mutate(
      selected
        ? `/api/v1/marketing/experiments/${selected.id}`
        : "/api/v1/marketing/experiments",
      selected ? "PUT" : "POST",
      experimentPayload(new FormData(form)),
    );
    if (saved && !selected) {
      form.reset();
      if (saved.id) setEditingId(saved.id);
    }
  }

  async function decide(
    experiment: MarketingExperiment,
    decision: "start" | "pause" | "resume" | "complete",
  ) {
    const prompt =
      decision === "complete"
        ? "Record the final decision and the business evidence used."
        : `Document why this experiment should ${decision}.`;
    const reason = window.prompt(prompt);
    if (!reason) return;
    await mutate(`/api/v1/marketing/experiments/${experiment.id}/decision`, "POST", {
      decision,
      reason,
    });
  }

  const running = initialData.experiments.filter((item) => item.status === "running").length;
  const ready = initialData.experiments.filter(
    (item) => item.decision_status === "ready_for_human_review",
  ).length;

  return (
    <section className={styles.workspace} aria-labelledby="experiment-title">
      <div className={styles.heading}>
        <div>
          <span>Conversion experiments</span>
          <h2 id="experiment-title">Controlled website testing tied to real deal outcomes</h2>
          <p>
            Test one homepage CTA at a time. Stonegate keeps the assigned version with the lead
            through qualification, appointments, contracts, and collected revenue.
          </p>
        </div>
        <div className={styles.summary}>
          <span><strong>{running}</strong> Running</span>
          <span><strong>{ready}</strong> Ready for review</span>
          <span><strong>{initialData.experiments.length}</strong> Total</span>
        </div>
      </div>

      {!apiConnected ? (
        <p className={styles.error} role="status">Experiment reporting is unavailable.</p>
      ) : null}
      {status !== "idle" ? (
        <p className={styles[status]} role="status">
          {status === "saving" ? "Saving..." : message}
        </p>
      ) : null}

      <div className={styles.layout}>
        <div className={styles.experimentList}>
          <div className={styles.listHeader}>
            <strong>Experiment ledger</strong>
            {initialData.can_manage ? (
              <button type="button" onClick={() => setEditingId(null)}>
                <Plus size={15} aria-hidden="true" />
                New test
              </button>
            ) : null}
          </div>
          {initialData.experiments.length ? (
            initialData.experiments.map((experiment) => (
              <article key={experiment.id}>
                <button
                  className={editingId === experiment.id ? styles.selected : undefined}
                  type="button"
                  onClick={() => setEditingId(experiment.id)}
                >
                  <span>
                    <small>{experiment.experiment_key}</small>
                    <strong>{experiment.name}</strong>
                  </span>
                  <Pencil size={15} aria-hidden="true" />
                </button>
                <div>
                  <StatusBadge tone={tone(experiment.status)}>
                    {labelize(experiment.status)}
                  </StatusBadge>
                  <StatusBadge tone={tone(experiment.decision_status)}>
                    {labelize(experiment.decision_status)}
                  </StatusBadge>
                </div>
              </article>
            ))
          ) : (
            <div className={styles.empty}>
              <FlaskConical size={22} aria-hidden="true" />
              <p>No experiment has been created. The current homepage remains the only version.</p>
            </div>
          )}
        </div>

        {selected && selected.status !== "draft" ? (
          <ExperimentReport experiment={selected} onDecision={decide} />
        ) : initialData.can_manage ? (
          <form
            className={styles.editor}
            key={selected?.id ?? "new-experiment"}
            onSubmit={saveExperiment}
          >
            <div className={styles.editorHeader}>
              <div>
                <span>{selected ? "Draft experiment" : "New controlled test"}</span>
                <h3>{selected?.name ?? "Define the test before collecting traffic"}</h3>
              </div>
              {selected ? <StatusBadge tone="neutral">Draft</StatusBadge> : null}
            </div>
            <div className={styles.formGrid}>
              <label>
                Experiment key
                <input
                  name="experiment_key"
                  pattern="[a-z][a-z0-9_]{2,79}"
                  required
                  defaultValue={selected?.experiment_key ?? ""}
                  placeholder="homepage_cta_2026_01"
                />
              </label>
              <label>
                Primary business outcome
                <select name="primary_metric" defaultValue={selected?.primary_metric ?? "qualified_lead"}>
                  <option value="form_submit">Submitted lead</option>
                  <option value="qualified_lead">Qualified lead</option>
                  <option value="appointment_scheduled">Appointment scheduled</option>
                  <option value="contract_signed">Contract signed</option>
                  <option value="funded_deal">Funded deal</option>
                </select>
              </label>
              <label className={styles.full}>
                Experiment name
                <input name="name" required defaultValue={selected?.name ?? ""} />
              </label>
              <label className={styles.full}>
                Hypothesis
                <textarea
                  name="hypothesis"
                  rows={3}
                  required
                  defaultValue={selected?.hypothesis ?? ""}
                  placeholder="We believe this CTA will increase qualified seller inquiries because..."
                />
              </label>
              <label>
                Current CTA
                <input
                  name="control_cta"
                  maxLength={40}
                  required
                  defaultValue={selected?.variants.find((item) => item.key === "control")?.cta_label ?? "Start My Offer"}
                />
              </label>
              <label>
                Test CTA
                <input
                  name="treatment_cta"
                  maxLength={40}
                  required
                  defaultValue={selected?.variants.find((item) => item.key === "treatment")?.cta_label ?? ""}
                  placeholder="Get My Cash Offer"
                />
              </label>
              <label>
                Sessions per version
                <input
                  name="minimum_sessions_per_variant"
                  type="number"
                  min="20"
                  max="100000"
                  required
                  defaultValue={selected?.minimum_sessions_per_variant ?? 50}
                />
              </label>
              <label>
                Minimum runtime days
                <input
                  name="minimum_runtime_days"
                  type="number"
                  min="7"
                  max="365"
                  required
                  defaultValue={selected?.minimum_runtime_days ?? 14}
                />
              </label>
              <label className={styles.full}>
                Decision rule
                <textarea
                  name="decision_rule"
                  rows={3}
                  required
                  defaultValue={selected?.decision_rule ?? ""}
                  placeholder="Review only after both thresholds. Prefer qualified-lead rate unless contract or funded outcomes contradict it."
                />
              </label>
            </div>
            <div className={styles.actions}>
              <button className={styles.primary} type="submit">
                <Save size={16} aria-hidden="true" />
                {selected ? "Save draft" : "Create draft"}
              </button>
              {selected ? (
                <button type="button" onClick={() => decide(selected, "start")}>
                  <CirclePlay size={16} aria-hidden="true" />
                  Start test
                </button>
              ) : null}
            </div>
          </form>
        ) : (
          <div className={styles.empty}>
            <p>Your role can read experiment results but cannot change public testing.</p>
          </div>
        )}
      </div>
    </section>
  );
}

function ExperimentReport({
  experiment,
  onDecision,
}: {
  experiment: MarketingExperiment;
  onDecision: (
    experiment: MarketingExperiment,
    decision: "start" | "pause" | "resume" | "complete",
  ) => void;
}) {
  return (
    <div className={styles.report}>
      <div className={styles.reportHeader}>
        <div>
          <span>{labelize(experiment.primary_metric)} is the primary outcome</span>
          <h3>{experiment.name}</h3>
          <p>{experiment.hypothesis}</p>
        </div>
        <StatusBadge tone={tone(experiment.decision_status)}>
          {labelize(experiment.decision_status)}
        </StatusBadge>
      </div>
      <div className={styles.thresholds}>
        <span><strong>{experiment.runtime_days}</strong> / {experiment.minimum_runtime_days} days</span>
        <span><strong>{experiment.minimum_sessions_per_variant}</strong> sessions required per version</span>
        <span><strong>50% / 50%</strong> stable allocation</span>
      </div>
      <div className={styles.variantGrid}>
        {experiment.performance.map((row) => (
          <article key={row.key}>
            <div>
              <span>{row.label}</span>
              <strong>&ldquo;{row.cta_label}&rdquo;</strong>
            </div>
            <dl>
              <div><dt>Assigned sessions</dt><dd>{row.assigned_sessions}</dd></div>
              <div><dt>Primary rate</dt><dd>{percent(row.primary_rate_basis_points)}</dd></div>
              <div><dt>Submitted leads</dt><dd>{row.leads_created}</dd></div>
              <div><dt>Qualified</dt><dd>{row.qualified_leads}</dd></div>
              <div><dt>Appointments</dt><dd>{row.appointments_scheduled}</dd></div>
              <div><dt>Contracts</dt><dd>{row.contracts_signed}</dd></div>
              <div><dt>Funded deals</dt><dd>{row.funded_deals}</dd></div>
              <div><dt>Revenue</dt><dd>{money(row.collected_revenue_cents)}</dd></div>
            </dl>
            <p>
              Device mix: {row.mobile_sessions} mobile, {row.tablet_sessions} tablet,{" "}
              {row.desktop_sessions} desktop.
            </p>
            <div className={styles.sourceBreakdown}>
              <strong>Source and campaign mix</strong>
              {row.source_breakdown.length ? (
                row.source_breakdown.map((source) => (
                  <div key={`${source.source}-${source.medium}-${source.campaign}`}>
                    <span>
                      {labelize(source.source)}
                      {source.campaign !== "uncategorized"
                        ? ` / ${labelize(source.campaign)}`
                        : ""}
                    </span>
                    <small>
                      {source.assigned_sessions} sessions · {source.qualified_leads} qualified ·{" "}
                      {source.contracts_signed} contracts
                    </small>
                  </div>
                ))
              ) : (
                <small>No attributed sessions yet.</small>
              )}
            </div>
          </article>
        ))}
      </div>
      <div className={styles.decision}>
        <div>
          <strong>Decision rule</strong>
          <p>{experiment.decision_rule}</p>
          {experiment.decision_blockers.length ? (
            <ul>
              {experiment.decision_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
            </ul>
          ) : (
            <p>Runtime and traffic thresholds are met. Review business outcomes before deciding.</p>
          )}
          {experiment.decision_notes ? <small>Final decision: {experiment.decision_notes}</small> : null}
        </div>
        {experiment.status !== "completed" ? (
          <div className={styles.actions}>
            {experiment.status === "running" ? (
              <button type="button" onClick={() => onDecision(experiment, "pause")}>
                <CirclePause size={16} aria-hidden="true" />
                Pause
              </button>
            ) : (
              <button type="button" onClick={() => onDecision(experiment, "resume")}>
                <RotateCcw size={16} aria-hidden="true" />
                Resume
              </button>
            )}
            <button type="button" onClick={() => onDecision(experiment, "complete")}>
              <Square size={15} aria-hidden="true" />
              Complete test
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
