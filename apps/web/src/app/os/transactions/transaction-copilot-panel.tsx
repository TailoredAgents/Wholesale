"use client";

import {
  AlertTriangle,
  Bot,
  Check,
  FileSearch,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import type {
  TransactionCopilotOverview,
  TransactionCopilotRecommendation,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./transactions.module.css";

type ReviewDecision = "accepted" | "edited" | "rejected";

export function TransactionCopilotPanel({
  busy,
  copilot,
  onGenerate,
  onReview,
}: {
  busy: boolean;
  copilot: TransactionCopilotOverview;
  onGenerate: () => Promise<void>;
  onReview: (
    recommendation: TransactionCopilotRecommendation,
    decision: ReviewDecision,
    finalOutput?: TransactionCopilotRecommendation["output_payload"],
  ) => Promise<void>;
}) {
  const [selectedId, setSelectedId] = useState(
    copilot.recommendations[0]?.id ?? "",
  );
  const selected = copilot.recommendations.find(
    (item) => item.id === selectedId,
  ) ?? copilot.recommendations[0] ?? null;
  const [summaryCorrections, setSummaryCorrections] = useState<Record<string, string>>({});
  const correctedSummary = selected
    ? summaryCorrections[selected.id] ?? selected.output_payload.status_summary
    : "";

  const enabled = copilot.capability_status === "enabled";
  const draft = selected?.output_payload;

  return (
    <section className={styles.transactionCopilot}>
      <header>
        <div>
          <span><Bot size={16} />Transaction Copilot</span>
          <h4>Closing readiness and document intelligence</h4>
        </div>
        <span className={styles.draftBadge}>
          <ShieldCheck size={15} />Draft only
        </span>
      </header>

      <div className={styles.copilotReadiness}>
        <div>
          <span>Readiness</span>
          <strong>{copilot.readiness_score}<small>/100</small></strong>
          <em>{labelize(copilot.readiness_band)}</em>
        </div>
        <div>
          <span>Deadline risks</span>
          <strong>{copilot.deadline_risks.length}</strong>
          <p>{copilot.deadline_risks[0]?.reason ?? "No seven-day risk detected"}</p>
        </div>
        <div>
          <span>Confirmed evidence</span>
          <strong>{copilot.confirmed_document_fact_count}</strong>
          <p>Document facts with human-confirmed sources</p>
        </div>
      </div>

      {(copilot.readiness_gaps.length || copilot.deadline_risks.length) ? (
        <div className={styles.copilotRiskGrid}>
          <div>
            <strong>Readiness gaps</strong>
            {copilot.readiness_gaps.slice(0, 6).map((item) => (
              <span key={item}><AlertTriangle size={14} />{item}</span>
            ))}
          </div>
          <div>
            <strong>Active deadlines</strong>
            {copilot.deadline_risks.slice(0, 6).map((item) => (
              <span data-severity={item.severity} key={`${item.item}-${item.due_at}`}>
                <AlertTriangle size={14} />
                {item.item}: {new Date(item.due_at).toLocaleDateString()}
              </span>
            ))}
            {!copilot.deadline_risks.length ? <span>No seven-day deadline risks.</span> : null}
          </div>
        </div>
      ) : null}

      <div className={styles.copilotCommand}>
        <button disabled={busy || !enabled} onClick={() => void onGenerate()} type="button">
          <RefreshCw size={16} />
          {copilot.recommendations.length ? "Refresh coordination draft" : "Analyze transaction"}
        </button>
        {!enabled ? (
          <small>Transaction guidance is currently disabled in AI Controls.</small>
        ) : (
          <small>Creates guidance only. It cannot change records or contact anyone.</small>
        )}
      </div>

      {copilot.recommendations.length ? (
        <div className={styles.copilotDraft}>
          <div className={styles.copilotDraftPicker}>
            <label>
              <span>Governed draft</span>
              <select onChange={(event) => setSelectedId(event.target.value)} value={selected?.id ?? ""}>
                {copilot.recommendations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {labelize(item.status)} · {new Date(item.generated_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
            <strong>{selected?.confidence_score ?? 0}% confidence</strong>
          </div>
          {draft ? (
            <>
              <textarea
                aria-label="Corrected transaction summary"
                onChange={(event) => setSummaryCorrections((current) => ({
                  ...current,
                  [selected?.id ?? ""]: event.target.value,
                }))}
                rows={3}
                value={correctedSummary}
              />
              <div className={styles.copilotColumns}>
                <CopilotList icon={<AlertTriangle size={14} />} items={draft.missing_items} title="Missing items" />
                <CopilotList icon={<Check size={14} />} items={draft.recommended_internal_actions} title="Internal actions" />
                <CopilotList icon={<FileSearch size={14} />} items={draft.document_findings.map((item) => `${item.finding}${item.source_page ? ` (page ${item.source_page})` : ""}`)} title="Document findings" />
              </div>
              <div className={styles.emailDrafts}>
                <div><span>Closing attorney draft</span><p>{draft.closing_attorney_email_draft || "No draft required."}</p></div>
                <div><span>Seller draft</span><p>{draft.seller_email_draft || "No draft required."}</p></div>
              </div>
              {selected?.status === "draft" ? (
                <div className={styles.copilotReviewActions}>
                  <button disabled={busy} onClick={() => void onReview(selected, "accepted")} type="button"><Check size={15} />Accept</button>
                  <button disabled={busy || correctedSummary === draft.status_summary} onClick={() => void onReview(selected, "edited", { ...draft, status_summary: correctedSummary })} type="button"><FileSearch size={15} />Save correction</button>
                  <button disabled={busy} onClick={() => void onReview(selected, "rejected")} type="button"><X size={15} />Reject</button>
                </div>
              ) : <p className={styles.reviewedDraft}>This draft has been {labelize(selected?.status ?? "reviewed")}.</p>}
            </>
          ) : null}
        </div>
      ) : (
        <p className={styles.copilotEmpty}>
          The deterministic readiness check is active. Generate an AI coordination draft after confirming the available evidence.
        </p>
      )}
    </section>
  );
}

function CopilotList({
  icon,
  items,
  title,
}: {
  icon: ReactNode;
  items: string[];
  title: string;
}) {
  return (
    <div>
      <strong>{title}</strong>
      {items.length ? items.map((item) => <span key={item}>{icon}{item}</span>) : <span>None identified.</span>}
    </div>
  );
}
