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
import { useState } from "react";

import type {
  DispositionCopilotOverview,
  DispositionCopilotRecommendation,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./dispositions.module.css";

type ReviewDecision = "accepted" | "edited" | "rejected";

export function DispositionCopilotPanel({
  busy,
  copilot,
  onGenerate,
  onReview,
}: {
  busy: boolean;
  copilot: DispositionCopilotOverview;
  onGenerate: () => Promise<void>;
  onReview: (
    recommendation: DispositionCopilotRecommendation,
    decision: ReviewDecision,
    finalOutput?: DispositionCopilotRecommendation["output_payload"],
  ) => Promise<void>;
}) {
  const [selectedId, setSelectedId] = useState(
    copilot.recommendations[0]?.id ?? "",
  );
  const selected =
    copilot.recommendations.find((item) => item.id === selectedId) ??
    copilot.recommendations[0] ??
    null;
  const [summaryCorrections, setSummaryCorrections] = useState<
    Record<string, string>
  >({});
  const draft = selected?.output_payload;
  const correctedSummary = selected
    ? summaryCorrections[selected.id] ?? selected.output_payload.status_summary
    : "";
  const enabled = copilot.capability_status === "enabled";

  return (
    <section className={styles.dispositionCopilot}>
      <header>
        <div>
          <span>
            <Bot size={16} />
            Disposition Copilot
          </span>
          <h4>Buyer intelligence and placement guidance</h4>
        </div>
        <span className={styles.copilotMode}>
          <ShieldCheck size={15} />
          Draft only
        </span>
      </header>

      <div className={styles.copilotReadiness}>
        <div>
          <span>Placement readiness</span>
          <strong>
            {copilot.readiness_score}
            <small>/100</small>
          </strong>
          <em>{labelize(copilot.readiness_band)}</em>
        </div>
        <div>
          <span>Qualified buyers</span>
          <strong>{copilot.qualified_buyer_count}</strong>
          <p>{copilot.verified_buyer_count} with current proof</p>
        </div>
        <div>
          <span>Offers</span>
          <strong>{copilot.offer_count}</strong>
          <p>{copilot.backup_coverage ? "Backup recorded" : "No backup selected"}</p>
        </div>
        <div>
          <span>Active risks</span>
          <strong>{copilot.risk_alerts.length}</strong>
          <p>{copilot.risk_alerts[0]?.reason ?? "No active risk detected"}</p>
        </div>
      </div>

      {copilot.readiness_gaps.length || copilot.risk_alerts.length ? (
        <div className={styles.copilotRiskGrid}>
          <div>
            <strong>Readiness gaps</strong>
            {copilot.readiness_gaps.slice(0, 5).map((item) => (
              <span key={item}>
                <AlertTriangle size={14} />
                {item}
              </span>
            ))}
            {!copilot.readiness_gaps.length ? <span>None identified.</span> : null}
          </div>
          <div>
            <strong>Placement risks</strong>
            {copilot.risk_alerts.slice(0, 5).map((item) => (
              <span data-severity={item.severity} key={`${item.item}-${item.reason}`}>
                <AlertTriangle size={14} />
                {item.item}: {item.reason}
              </span>
            ))}
            {!copilot.risk_alerts.length ? <span>None identified.</span> : null}
          </div>
        </div>
      ) : null}

      <div className={styles.copilotCommand}>
        <button
          disabled={busy || !enabled}
          onClick={() => void onGenerate()}
          type="button"
        >
          <RefreshCw size={16} />
          {copilot.recommendations.length
            ? "Analyze current evidence"
            : "Prepare disposition guidance"}
        </button>
        <small>
          {enabled
            ? "Creates drafts only. It cannot release campaigns, contact buyers, or select an offer."
            : "Disposition guidance is currently disabled in AI Controls."}
        </small>
      </div>

      {draft && selected ? (
        <div className={styles.copilotDraft}>
          <div className={styles.copilotDraftPicker}>
            <label>
              <span>Governed draft</span>
              <select
                onChange={(event) => setSelectedId(event.target.value)}
                value={selected.id}
              >
                {copilot.recommendations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {labelize(item.status)} ·{" "}
                    {new Date(item.generated_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
            <strong>{selected.confidence_score ?? 0}% confidence</strong>
          </div>

          <textarea
            aria-label="Corrected disposition summary"
            onChange={(event) =>
              setSummaryCorrections((current) => ({
                ...current,
                [selected.id]: event.target.value,
              }))
            }
            rows={3}
            value={correctedSummary}
          />

          <div className={styles.copilotColumns}>
            <CopilotList items={draft.package_gaps} title="Package gaps" />
            <CopilotList
              icon="check"
              items={draft.package_highlights}
              title="Package highlights"
            />
            <CopilotList items={draft.risk_alerts} title="Risk alerts" />
          </div>

          <div className={styles.copilotColumns}>
            <CopilotList
              icon="check"
              items={draft.recommended_internal_actions}
              title="Internal actions"
            />
            <CopilotList
              icon="evidence"
              items={draft.relationship_update_proposals}
              title="Relationship updates"
            />
            <CopilotList
              icon="evidence"
              items={[
                ...draft.uncertainties.map((item) => `Uncertainty: ${item}`),
                ...draft.evidence.map((item) => `Evidence: ${item}`),
              ]}
              title="Evidence and limits"
            />
          </div>

          <div className={styles.buyerRecommendations}>
            <strong>Buyer recommendations</strong>
            {draft.recommended_buyers.map((item) => (
              <div key={item.buyer_id}>
                <span>{item.buyer_name}</span>
                <b>{labelize(item.recommendation)}</b>
                <p>{item.rationale.join(" ")}</p>
                {item.risks.length ? <small>{item.risks.join(" ")}</small> : null}
                {item.evidence.length ? (
                  <em>Evidence: {item.evidence.join(" ")}</em>
                ) : null}
              </div>
            ))}
            {!draft.recommended_buyers.length ? <span>No buyer recommended yet.</span> : null}
          </div>

          <div className={styles.offerComparisons}>
            <strong>Offer comparison</strong>
            {draft.offer_comparison.map((item) => (
              <div key={item.offer_id}>
                <span>{item.buyer_name}</span>
                <b>{labelize(item.strength)}</b>
                <p>{item.rationale.join(" ")}</p>
                {item.risks.length ? <small>{item.risks.join(" ")}</small> : null}
              </div>
            ))}
            {!draft.offer_comparison.length ? <span>No offers available to compare.</span> : null}
          </div>

          <div className={styles.outreachDraft}>
            <span>Buyer outreach draft</span>
            <strong>{draft.buyer_outreach_subject || "No subject drafted"}</strong>
            <p>{draft.buyer_outreach_body || "No outreach draft required."}</p>
            <small>This is not sent until a human approves a future campaign.</small>
          </div>

          {selected.status === "draft" ? (
            <div className={styles.copilotReviewActions}>
              <button
                disabled={busy}
                onClick={() => void onReview(selected, "accepted")}
                type="button"
              >
                <Check size={15} />
                Accept
              </button>
              <button
                disabled={busy || correctedSummary === draft.status_summary}
                onClick={() =>
                  void onReview(selected, "edited", {
                    ...draft,
                    status_summary: correctedSummary,
                  })
                }
                type="button"
              >
                <FileSearch size={15} />
                Save correction
              </button>
              <button
                disabled={busy}
                onClick={() => void onReview(selected, "rejected")}
                type="button"
              >
                <X size={15} />
                Reject
              </button>
            </div>
          ) : (
            <p className={styles.reviewedDraft}>
              This draft has been {labelize(selected.status)}.
            </p>
          )}
        </div>
      ) : (
        <p className={styles.copilotEmpty}>
          Deterministic buyer readiness is active. Generate guidance when the available
          package and buyer evidence are ready for review.
        </p>
      )}
    </section>
  );
}

function CopilotList({
  icon = "alert",
  items,
  title,
}: {
  icon?: "alert" | "check" | "evidence";
  items: string[];
  title: string;
}) {
  const Icon = icon === "check" ? Check : icon === "evidence" ? FileSearch : AlertTriangle;
  return (
    <div>
      <strong>{title}</strong>
      {items.length ? (
        items.map((item) => (
          <span key={item}>
            <Icon size={14} />
            {item}
          </span>
        ))
      ) : (
        <span>None identified.</span>
      )}
    </div>
  );
}
