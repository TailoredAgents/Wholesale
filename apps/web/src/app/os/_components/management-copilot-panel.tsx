"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  Bot,
  Check,
  FileSearch,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import type {
  ManagementCopilotOutput,
  ManagementCopilotOverview,
  ManagementCopilotRecommendation,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./management-copilot-panel.module.css";

type ReviewDecision = "accepted" | "edited" | "rejected";

const workspacePaths: Record<string, string> = {
  dashboard: "/os",
  finance: "/os/finance",
  marketing: "/os/marketing",
  operations: "/os/operations",
  dispositions: "/os/dispositions",
  transactions: "/os/transactions",
  ai: "/os/ai",
};

export function ManagementCopilotPanel({
  endpointBase,
  initialData,
}: {
  endpointBase: string;
  initialData: ManagementCopilotOverview;
}) {
  const { getToken } = useAuth();
  const [copilot, setCopilot] = useState(initialData);
  const [selectedId, setSelectedId] = useState(
    initialData.recommendations[0]?.id ?? "",
  );
  const [briefCorrections, setBriefCorrections] = useState<
    Record<string, string>
  >({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );
  const selected =
    copilot.recommendations.find((item) => item.id === selectedId) ??
    copilot.recommendations[0] ??
    null;
  const draft = selected?.output_payload;
  const correctedBrief = selected
    ? briefCorrections[selected.id] ?? selected.output_payload.brief
    : "";
  const enabled = copilot.capability_status === "enabled";

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devEmail;
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: { ...headers, ...(options.headers ?? {}) },
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as {
        detail?: string;
      };
      throw new Error(
        typeof payload.detail === "string" ? payload.detail : "Request failed.",
      );
    }
    return response.json() as Promise<T>;
  }

  async function refresh() {
    const result = await request<ManagementCopilotOverview>(
      `${endpointBase}?period_days=${copilot.reporting_period_days}`,
    );
    setCopilot(result);
    setSelectedId((current) =>
      result.recommendations.some((item) => item.id === current)
        ? current
        : result.recommendations[0]?.id ?? "",
    );
  }

  async function generate() {
    setBusy(true);
    setMessage(null);
    try {
      await request(`${endpointBase}/analyze`, {
        method: "POST",
        body: JSON.stringify({
          period_days: copilot.reporting_period_days,
        }),
      });
      await refresh();
      setMessage("New governed draft prepared.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to generate.");
    } finally {
      setBusy(false);
    }
  }

  async function review(
    recommendation: ManagementCopilotRecommendation,
    decision: ReviewDecision,
    finalOutput?: ManagementCopilotOutput,
  ) {
    setBusy(true);
    setMessage(null);
    try {
      await request(
        `${endpointBase}/recommendations/${recommendation.id}/review`,
        {
          method: "POST",
          body: JSON.stringify({
            decision,
            final_output: finalOutput ?? null,
            notes: "Management owner reviewed the governed draft.",
            estimated_time_saved_seconds: 600,
          }),
        },
      );
      await refresh();
      setMessage(`Draft ${labelize(decision).toLowerCase()}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to review.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel}>
      <header className={styles.header}>
        <div>
          <span>
            <Bot size={16} />
            {copilot.copilot_name}
          </span>
          <h2>Evidence-backed management review</h2>
        </div>
        <strong>
          <ShieldCheck size={15} />
          Draft only
        </strong>
      </header>

      <div className={styles.metrics}>
        <div className={styles.health}>
          <span>Control health</span>
          <strong>{copilot.health_score}<small>/100</small></strong>
          <em>{labelize(copilot.health_band)}</em>
        </div>
        {copilot.metric_cards.map((item) => (
          <div data-tone={item.tone} key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            <small>{item.detail}</small>
          </div>
        ))}
      </div>

      {copilot.readiness_gaps.length || copilot.risk_alerts.length ? (
        <div className={styles.riskBand}>
          <div>
            <strong>Evidence gaps</strong>
            {copilot.readiness_gaps.map((item) => (
              <span key={item}><AlertTriangle size={14} />{item}</span>
            ))}
            {!copilot.readiness_gaps.length ? <span>None identified.</span> : null}
          </div>
          <div>
            <strong>Active exceptions</strong>
            {copilot.risk_alerts.map((item) => (
              <span data-severity={item.severity} key={`${item.item}-${item.reason}`}>
                <AlertTriangle size={14} />{item.item}: {item.reason}
              </span>
            ))}
            {!copilot.risk_alerts.length ? <span>None identified.</span> : null}
          </div>
        </div>
      ) : null}

      <div className={styles.command}>
        <button disabled={busy || !enabled} onClick={() => void generate()} type="button">
          <RefreshCw size={15} />
          {copilot.recommendations.length ? "Refresh analysis" : "Prepare analysis"}
        </button>
        <small>
          {enabled
            ? `Period: ${copilot.reporting_period_days} days · human review required`
            : "Capability disabled in AI Controls"}
        </small>
        {message ? <span role="status">{message}</span> : null}
      </div>

      {draft && selected ? (
        <div className={styles.draft}>
          <div className={styles.draftHeader}>
            <label>
              <span>Governed draft</span>
              <select
                onChange={(event) => setSelectedId(event.target.value)}
                value={selected.id}
              >
                {copilot.recommendations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {labelize(item.status)} · {new Date(item.generated_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
            <strong>{selected.confidence_score ?? 0}% confidence</strong>
          </div>

          <textarea
            aria-label={`Corrected ${copilot.copilot_name} brief`}
            onChange={(event) =>
              setBriefCorrections((current) => ({
                ...current,
                [selected.id]: event.target.value,
              }))
            }
            rows={3}
            value={correctedBrief}
          />

          <div className={styles.factGrid}>
            {draft.confirmed_facts.map((item) => (
              <div key={`${item.label}-${item.value}`}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <small>{item.evidence.join(" · ")}</small>
              </div>
            ))}
          </div>

          <ReviewRows
            empty="No model exceptions."
            items={draft.exceptions.map((item) => ({
              eyebrow: `${labelize(item.category)} · ${labelize(item.severity)}`,
              title: item.title,
              detail: item.detail,
              evidence: item.evidence,
              tone: item.severity,
            }))}
            title="Exceptions"
          />
          <ReviewRows
            empty="No additional analysis."
            items={draft.analysis.map((item) => ({
              eyebrow: `${labelize(item.category)} · ${labelize(item.signal)}`,
              title: item.subject,
              detail: item.analysis,
              evidence: item.evidence,
              tone: item.signal,
            }))}
            title="Analysis"
          />

          <div className={styles.actionGrid}>
            <section>
              <header>Draft internal actions</header>
              {draft.draft_actions.map((item) => (
                <div key={`${item.workspace}-${item.action}`}>
                  <span>{item.owner} · {labelize(item.workspace)}</span>
                  <strong>{item.action}</strong>
                  <p>{item.reason}</p>
                  <Link href={workspacePaths[item.workspace] ?? "/os"}>
                    Open workspace
                  </Link>
                </div>
              ))}
              {!draft.draft_actions.length ? <p>No action proposed.</p> : null}
            </section>
            <section>
              <header>Human decisions</header>
              {draft.decision_requests.map((item) => (
                <div key={item.decision}>
                  <span>Decision required</span>
                  <strong>{item.decision}</strong>
                  <p>{item.why_now}</p>
                  <small>{item.options.join(" · ")}</small>
                </div>
              ))}
              {!draft.decision_requests.length ? <p>No decision requested.</p> : null}
            </section>
          </div>

          <div className={styles.evidenceBand}>
            <div><strong>Uncertainties</strong><span>{draft.uncertainties.join(" · ") || "None stated."}</span></div>
            <div><strong>Evidence</strong><span>{draft.evidence.join(" · ") || "None stated."}</span></div>
          </div>

          {selected.status === "draft" ? (
            <div className={styles.reviewActions}>
              <button disabled={busy} onClick={() => void review(selected, "accepted")} type="button">
                <Check size={15} />Accept
              </button>
              <button
                disabled={busy || correctedBrief === draft.brief}
                onClick={() =>
                  void review(selected, "edited", {
                    ...draft,
                    brief: correctedBrief,
                  })
                }
                type="button"
              >
                <FileSearch size={15} />Save correction
              </button>
              <button disabled={busy} onClick={() => void review(selected, "rejected")} type="button">
                <X size={15} />Reject
              </button>
            </div>
          ) : (
            <p className={styles.reviewed}>Draft {labelize(selected.status).toLowerCase()}.</p>
          )}
        </div>
      ) : (
        <p className={styles.empty}>
          Deterministic health and exception monitoring is active.
        </p>
      )}
    </section>
  );
}

function ReviewRows({
  empty,
  items,
  title,
}: {
  empty: string;
  items: Array<{
    eyebrow: string;
    title: string;
    detail: string;
    evidence: string[];
    tone: string;
  }>;
  title: string;
}) {
  return (
    <section className={styles.rows}>
      <header>{title}</header>
      {items.map((item) => (
        <div data-tone={item.tone} key={`${item.eyebrow}-${item.title}`}>
          <span>{item.eyebrow}</span>
          <strong>{item.title}</strong>
          <p>{item.detail}</p>
          <small>{item.evidence.join(" · ")}</small>
        </div>
      ))}
      {!items.length ? <p>{empty}</p> : null}
    </section>
  );
}
