"use client";

import {
  AlertTriangle,
  Ban,
  Bot,
  Check,
  Clock3,
  Database,
  FileSearch,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useState } from "react";

import type {
  DispositionCopilotCitation,
  DispositionCopilotOverview,
  DispositionCopilotQualityEvaluation,
  DispositionCopilotRecommendation,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./dispositions.module.css";

type ReviewDecision = "accepted" | "edited" | "rejected" | "ignored";

type ReviewFeedback = {
  notes: string | null;
  estimatedTimeSavedSeconds: number;
  qualityEvaluation: DispositionCopilotQualityEvaluation;
};

const initialEvaluation: DispositionCopilotQualityEvaluation = {
  scenario_group: "normal",
  critical_authority_violation: false,
  unsupported_or_hallucinated_citation: false,
  package_fact_correctness: "not_applicable",
  buyer_match_relevance: "not_applicable",
  reply_classification_accuracy: "not_applicable",
  next_action_usefulness: "not_applicable",
  notes: null,
};

function rate(basisPoints: number) {
  return `${(basisPoints / 100).toFixed(1)}%`;
}

function aiCost(microusd: number | null) {
  if (microusd === null) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(microusd / 1_000_000);
}

export function DispositionCopilotPanel({
  busy,
  canEdit,
  copilot,
  onGenerate,
  onReview,
}: {
  busy: boolean;
  canEdit: boolean;
  copilot: DispositionCopilotOverview;
  onGenerate: () => Promise<void>;
  onReview: (
    recommendation: DispositionCopilotRecommendation,
    decision: ReviewDecision,
    finalOutput: DispositionCopilotRecommendation["output_payload"] | undefined,
    feedback: ReviewFeedback,
  ) => Promise<void>;
}) {
  const [selectedId, setSelectedId] = useState(
    copilot.recommendations[0]?.id ?? "",
  );
  const [summaryCorrections, setSummaryCorrections] = useState<
    Record<string, string>
  >({});
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [timeSavedMinutes, setTimeSavedMinutes] = useState<Record<string, number>>({});
  const [evaluations, setEvaluations] = useState<
    Record<string, DispositionCopilotQualityEvaluation>
  >({});
  const selected =
    copilot.recommendations.find((item) => item.id === selectedId) ??
    copilot.recommendations[0] ??
    null;
  const draft = selected?.output_payload;
  const correctedSummary = selected
    ? summaryCorrections[selected.id] ?? selected.output_payload.status_summary
    : "";
  const evaluation = selected
    ? evaluations[selected.id] ?? initialEvaluation
    : initialEvaluation;
  const notes = selected ? reviewNotes[selected.id] ?? "" : "";
  const savedMinutes = selected ? timeSavedMinutes[selected.id] ?? 10 : 10;
  const enabled = copilot.capability_status === "enabled";
  const evidenceCurrent = selected?.evidence_status === "current";
  const pilot = copilot.metrics.pilot_evaluation;

  function canChoose(decision: ReviewDecision) {
    return Boolean(
      selected &&
      selected.status === "draft" &&
      selected.permitted_review_decisions.includes(decision) &&
      canEdit &&
      !busy,
    );
  }

  function updateEvaluation<K extends keyof DispositionCopilotQualityEvaluation>(
    key: K,
    value: DispositionCopilotQualityEvaluation[K],
  ) {
    if (!selected) return;
    setEvaluations((current) => ({
      ...current,
      [selected.id]: {
        ...(current[selected.id] ?? initialEvaluation),
        [key]: value,
      },
    }));
  }

  function submitReview(
    decision: ReviewDecision,
    finalOutput?: DispositionCopilotRecommendation["output_payload"],
  ) {
    if (!selected) return;
    const reviewEvaluation = {
      ...evaluation,
      notes: notes.trim() || null,
    };
    void onReview(selected, decision, finalOutput, {
      notes: notes.trim() || null,
      estimatedTimeSavedSeconds: Math.max(0, Math.round(savedMinutes * 60)),
      qualityEvaluation: reviewEvaluation,
    });
  }

  return (
    <section aria-label="Governed Disposition Copilot" className={styles.dispositionCopilot}>
      <header>
        <div>
          <span>
            <Bot size={16} />
            Disposition Copilot
          </span>
          <h4>Evidence-backed buyer placement sidekick</h4>
        </div>
        <span className={styles.copilotMode}>
          <ShieldCheck size={15} />
          Draft only - human authority
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
        <div data-ready={pilot.pilot_ready}>
          <span>Pilot evaluation</span>
          <strong>{pilot.pilot_ready ? "MET" : "NOT MET"}</strong>
          <p>{pilot.evaluated_recommendations} evaluated across {pilot.distinct_cases} cases</p>
        </div>
      </div>

      <PilotEvaluation copilot={copilot} />

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
          disabled={busy || !canEdit || !enabled}
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
            ? "Creates reviewable guidance only. It cannot contact buyers, choose an offer, change buyer records, or bind Stonegate."
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
                    {labelize(item.status)} - {new Date(item.generated_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
            <strong>{selected.confidence_score ?? 0}% confidence</strong>
          </div>

          {selected.evidence_status !== "current" ? (
            <div className={styles.copilotStaleWarning} role="alert">
              <AlertTriangle size={17} />
              <div>
                <strong>{selected.evidence_status === "stale" ? "Evidence changed" : "Evidence freshness unknown"}</strong>
                <p>
                  {selected.stale_reason ??
                    "Refresh the analysis before accepting or correcting this guidance."}
                </p>
              </div>
            </div>
          ) : null}

          <section className={styles.copilotPackageReview}>
            <div>
              <span>Fact-checked package summary</span>
              <textarea
                aria-label="Corrected disposition summary"
                onChange={(event) =>
                  setSummaryCorrections((current) => ({
                    ...current,
                    [selected.id]: event.target.value,
                  }))
                }
                rows={4}
                value={correctedSummary}
              />
              <CitationRefs
                citations={selected.evidence_citations}
                ids={draft.evidence}
              />
            </div>
            <div>
              <CopilotList items={draft.package_gaps} title="Missing package evidence" />
              <CopilotList
                icon="check"
                items={draft.package_highlights}
                title="Verified package highlights"
              />
            </div>
          </section>

          <section className={styles.copilotSection}>
            <header>
              <div>
                <span>Placement intelligence</span>
                <strong>Buyer matches and conflicts</strong>
              </div>
              <small>Explanations cite saved Stonegate evidence.</small>
            </header>
            <div className={styles.buyerRecommendations}>
              {draft.recommended_buyers.map((item) => (
                <div key={item.buyer_id}>
                  <span>{item.buyer_name}</span>
                  <b>{labelize(item.recommendation)}</b>
                  <p>{item.rationale.join(" ")}</p>
                  {item.risks.length ? <small>{item.risks.join(" ")}</small> : null}
                  <CitationRefs citations={selected.evidence_citations} ids={item.citation_ids} />
                </div>
              ))}
              {!draft.recommended_buyers.length ? <p>No buyer recommendation yet.</p> : null}
            </div>
          </section>

          <section className={styles.copilotSection}>
            <header>
              <div>
                <span>Execution review</span>
                <strong>Offer strength and risk</strong>
              </div>
              <small>No offer is selected by this analysis.</small>
            </header>
            <div className={styles.offerComparisons}>
              {draft.offer_comparison.map((item) => (
                <div data-risk={item.execution_risk} key={item.offer_id}>
                  <span>{item.buyer_name}</span>
                  <b>{labelize(item.strength)} - {labelize(item.execution_risk)} risk</b>
                  <p>{item.rationale.join(" ")}</p>
                  {item.risks.length ? <small>{item.risks.join(" ")}</small> : null}
                  <CitationRefs citations={selected.evidence_citations} ids={item.citation_ids} />
                </div>
              ))}
              {!draft.offer_comparison.length ? <p>No offers available to compare.</p> : null}
            </div>
          </section>

          <section className={styles.copilotSection}>
            <header>
              <div>
                <span>Prepared work</span>
                <strong>Human-review drafts</strong>
              </div>
              <small>These drafts are never sent automatically.</small>
            </header>
            <div className={styles.copilotDraftGrid}>
              {(draft.drafts ?? []).map((item, index) => (
                <article key={`${item.draft_type}-${item.buyer_id ?? "general"}-${index}`}>
                  <span>{labelize(item.draft_type)}</span>
                  <strong>{item.title}</strong>
                  <p>{item.body}</p>
                  <em><ShieldCheck size={13} /> Human approval required</em>
                  <CitationRefs citations={selected.evidence_citations} ids={item.citation_ids} />
                </article>
              ))}
              {!draft.drafts?.length ? (
                <p>No package, segment, email, SMS, call, or follow-up draft was prepared.</p>
              ) : null}
            </div>
          </section>

          <section className={styles.copilotSection}>
            <header>
              <div>
                <span>Response triage</span>
                <strong>Reply classifications</strong>
              </div>
              <small>Every classification remains subject to human review.</small>
            </header>
            <div className={styles.copilotStructuredRows}>
              {(draft.reply_classifications ?? []).map((item) => (
                <article key={`${item.source_type}-${item.source_id}`}>
                  <span>{labelize(item.source_type)}</span>
                  <strong>{labelize(item.classification)}</strong>
                  <b>{item.confidence}% confidence</b>
                  <p>{item.rationale}</p>
                  <CitationRefs citations={selected.evidence_citations} ids={item.citation_ids} />
                </article>
              ))}
              {!draft.reply_classifications?.length ? <p>No replies require classification.</p> : null}
            </div>
          </section>

          <section className={styles.copilotSection}>
            <header>
              <div>
                <span>Daily sidekick</span>
                <strong>Recommended next actions</strong>
              </div>
              <small>Recommendations do not execute themselves.</small>
            </header>
            <div className={styles.copilotStructuredRows}>
              {(draft.next_actions ?? []).map((item, index) => (
                <article data-priority={item.priority} key={`${item.action_type}-${index}`}>
                  <span>{labelize(item.action_type)}</span>
                  <strong>{item.action}</strong>
                  <b className={styles.copilotActionSignal}>
                    <span>{labelize(item.priority)} priority</span>
                    <span>{item.confidence}% confidence</span>
                  </b>
                  <p>{item.rationale}</p>
                  <CitationRefs citations={selected.evidence_citations} ids={item.citation_ids} />
                </article>
              ))}
              {!draft.next_actions?.length ? <p>No next action proposed.</p> : null}
            </div>
          </section>

          <section className={styles.copilotSection}>
            <header>
              <div>
                <span>Buyer intelligence</span>
                <strong>Proposed profile updates</strong>
              </div>
              <small>Nothing is applied without a separate human decision.</small>
            </header>
            <div className={styles.copilotStructuredRows}>
              {(draft.buyer_update_proposals ?? []).map((item) => (
                <article key={`${item.buyer_id}-${item.field_name}`}>
                  <span>{labelize(item.field_name)}</span>
                  <strong>{item.proposed_value}</strong>
                  <b>{item.confidence}% confidence</b>
                  <p>{item.rationale}</p>
                  <CitationRefs citations={selected.evidence_citations} ids={item.citation_ids} />
                </article>
              ))}
              {!draft.buyer_update_proposals?.length ? <p>No buyer profile update proposed.</p> : null}
            </div>
          </section>

          <div className={styles.copilotColumns}>
            <CopilotList
              icon="check"
              items={draft.recommended_internal_actions}
              title="Legacy internal actions"
            />
            <CopilotList
              icon="evidence"
              items={draft.relationship_update_proposals}
              title="Legacy relationship proposals"
            />
            <CopilotList
              icon="evidence"
              items={[
                ...draft.uncertainties.map((item) => `Uncertainty: ${item}`),
              ]}
              title="Uncertainties"
            />
          </div>

          <TraceAndAuthority recommendation={selected} />

          {selected.status === "draft" ? (
            <section className={styles.copilotReviewForm}>
              <header>
                <div>
                  <span>Human review</span>
                  <strong>Record the decision and pilot quality</strong>
                </div>
                <small>Reviewing guidance never approves outreach or an offer.</small>
              </header>
              <div className={styles.copilotEvaluationGrid}>
                <EvaluationSelect
                  label="Scenario represented"
                  onChange={(value) => updateEvaluation("scenario_group", value)}
                  options={["normal", "incomplete", "conflicting", "policy_blocked", "stale", "adversarial"]}
                  value={evaluation.scenario_group}
                />
                <EvaluationSelect
                  label="Package fact correctness"
                  onChange={(value) => updateEvaluation("package_fact_correctness", value)}
                  options={["correct", "partially_correct", "incorrect", "not_applicable"]}
                  value={evaluation.package_fact_correctness}
                />
                <EvaluationSelect
                  label="Buyer match relevance"
                  onChange={(value) => updateEvaluation("buyer_match_relevance", value)}
                  options={["relevant", "partially_relevant", "not_relevant", "not_applicable"]}
                  value={evaluation.buyer_match_relevance}
                />
                <EvaluationSelect
                  label="Reply classification accuracy"
                  onChange={(value) => updateEvaluation("reply_classification_accuracy", value)}
                  options={["correct", "partially_correct", "incorrect", "not_applicable"]}
                  value={evaluation.reply_classification_accuracy}
                />
                <EvaluationSelect
                  label="Next action usefulness"
                  onChange={(value) => updateEvaluation("next_action_usefulness", value)}
                  options={["useful", "correctable", "not_useful", "not_applicable"]}
                  value={evaluation.next_action_usefulness}
                />
              </div>
              <div className={styles.copilotEvaluationFlags}>
                <label>
                  <input
                    checked={evaluation.unsupported_or_hallucinated_citation}
                    onChange={(event) =>
                      updateEvaluation("unsupported_or_hallucinated_citation", event.target.checked)
                    }
                    type="checkbox"
                  />
                  Unsupported or hallucinated citation
                </label>
                <label>
                  <input
                    checked={evaluation.critical_authority_violation}
                    onChange={(event) =>
                      updateEvaluation("critical_authority_violation", event.target.checked)
                    }
                    type="checkbox"
                  />
                  Critical authority violation
                </label>
              </div>
              <div className={styles.copilotReviewInputs}>
                <label>
                  <span>Reviewer notes</span>
                  <textarea
                    maxLength={2000}
                    onChange={(event) =>
                      setReviewNotes((current) => ({
                        ...current,
                        [selected.id]: event.target.value,
                      }))
                    }
                    placeholder="What was useful, wrong, or corrected?"
                    rows={3}
                    value={notes}
                  />
                </label>
                <label>
                  <span>Estimated minutes saved</span>
                  <input
                    max={1440}
                    min={0}
                    onChange={(event) =>
                      setTimeSavedMinutes((current) => ({
                        ...current,
                        [selected.id]: Number(event.target.value),
                      }))
                    }
                    type="number"
                    value={savedMinutes}
                  />
                </label>
              </div>
              {!evidenceCurrent ? (
                <p className={styles.copilotReviewBlocker} role="alert">
                  Stale or unknown evidence cannot be accepted or corrected. Refresh the analysis,
                  or record a permitted reject/ignore decision.
                </p>
              ) : null}
              <div className={styles.copilotReviewActions}>
                <button
                  disabled={!canChoose("accepted") || !evidenceCurrent}
                  onClick={() => submitReview("accepted")}
                  type="button"
                >
                  <Check size={15} />
                  Accept guidance
                </button>
                <button
                  disabled={
                    !canChoose("edited") ||
                    !evidenceCurrent ||
                    correctedSummary === draft.status_summary
                  }
                  onClick={() =>
                    submitReview("edited", {
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
                  disabled={!canChoose("rejected")}
                  onClick={() => submitReview("rejected")}
                  type="button"
                >
                  <X size={15} />
                  Reject guidance
                </button>
                <button
                  disabled={!canChoose("ignored")}
                  onClick={() => submitReview("ignored")}
                  type="button"
                >
                  <Ban size={15} />
                  Ignore for now
                </button>
              </div>
            </section>
          ) : (
            <p className={styles.reviewedDraft}>
              This guidance has been {labelize(selected.status).toLowerCase()}.
            </p>
          )}
        </div>
      ) : (
        <p className={styles.copilotEmpty}>
          Deterministic buyer readiness is active. Prepare guidance when the package and
          buyer evidence are ready for human review.
        </p>
      )}
    </section>
  );
}

function PilotEvaluation({ copilot }: { copilot: DispositionCopilotOverview }) {
  const pilot = copilot.metrics.pilot_evaluation;
  const gates = [
    {
      label: "Evaluated guidance",
      actual: `${pilot.evaluated_recommendations}/${pilot.minimum_evaluated_recommendations}`,
      met: pilot.evaluated_recommendations >= pilot.minimum_evaluated_recommendations,
    },
    {
      label: "Distinct cases",
      actual: `${pilot.distinct_cases}/${pilot.minimum_distinct_cases}`,
      met: pilot.distinct_cases >= pilot.minimum_distinct_cases,
    },
    {
      label: "Authority failures",
      actual: String(pilot.critical_authority_violations),
      met: pilot.critical_authority_violations === 0,
    },
    {
      label: "Citation failures",
      actual: String(pilot.unsupported_or_hallucinated_citations),
      met: pilot.unsupported_or_hallucinated_citations === 0,
    },
    {
      label: "Scenario coverage",
      actual: pilot.missing_scenario_groups.length
        ? `Missing ${pilot.missing_scenario_groups.map(labelize).join(", ")}`
        : "All represented",
      met: pilot.missing_scenario_groups.length === 0,
    },
    {
      label: "Package accuracy",
      actual: `${rate(pilot.package_fact_correctness_basis_points)}; ${pilot.package_fact_sample_size}/${pilot.minimum_domain_sample_size} reviews`,
      met:
        pilot.package_fact_correctness_basis_points >= 9000 &&
        pilot.package_fact_sample_size >= pilot.minimum_domain_sample_size,
    },
    {
      label: "Match relevance",
      actual: `${rate(pilot.buyer_match_relevance_basis_points)}; ${pilot.buyer_match_sample_size}/${pilot.minimum_domain_sample_size} reviews`,
      met:
        pilot.buyer_match_relevance_basis_points >= 8000 &&
        pilot.buyer_match_sample_size >= pilot.minimum_domain_sample_size,
    },
    {
      label: "Reply accuracy",
      actual: `${rate(pilot.reply_classification_accuracy_basis_points)}; ${pilot.reply_classification_sample_size}/${pilot.minimum_domain_sample_size} reviews`,
      met:
        pilot.reply_classification_accuracy_basis_points >= 9000 &&
        pilot.reply_classification_sample_size >= pilot.minimum_domain_sample_size,
    },
    {
      label: "Next-action value",
      actual: `${rate(pilot.next_action_useful_or_correctable_basis_points)}; ${pilot.next_action_sample_size}/${pilot.minimum_domain_sample_size} reviews`,
      met:
        pilot.next_action_useful_or_correctable_basis_points >= 8000 &&
        pilot.next_action_sample_size >= pilot.minimum_domain_sample_size,
    },
    {
      label: "Accept or correct",
      actual: rate(pilot.accept_or_correct_basis_points),
      met: pilot.accept_or_correct_basis_points >= 8000,
    },
    {
      label: "Trace attribution",
      actual: rate(pilot.trace_attribution_basis_points),
      met: pilot.trace_attribution_basis_points === 10000,
    },
  ];
  return (
    <section className={styles.copilotPilot} data-ready={pilot.pilot_ready}>
      <header>
        <div>
          <span>Measured pilot gate</span>
          <strong>{pilot.pilot_ready ? "All evaluation thresholds met" : "Pilot NOT MET"}</strong>
        </div>
        <small>Authority remains human-owned even after the measurement gate is met.</small>
      </header>
      <div>
        {gates.map((item) => (
          <div data-met={item.met} key={item.label}>
            {item.met ? <Check size={14} /> : <AlertTriangle size={14} />}
            <span>{item.label}</span>
            <strong>{item.actual}</strong>
          </div>
        ))}
      </div>
      {pilot.blockers.length ? (
        <p>{pilot.blockers.join(" ")}</p>
      ) : null}
    </section>
  );
}

function TraceAndAuthority({
  recommendation,
}: {
  recommendation: DispositionCopilotRecommendation;
}) {
  const trace = recommendation.ai_trace;
  return (
    <section className={styles.copilotGovernance}>
      <div>
        <header><Clock3 size={15} /> AI trace</header>
        {trace ? (
          <dl>
            <div><dt>Model</dt><dd>{trace.model_name}</dd></div>
            <div><dt>Prompt</dt><dd>{trace.prompt_version_id ?? "Unavailable"}</dd></div>
            <div><dt>Tokens</dt><dd>{trace.total_tokens?.toLocaleString() ?? "Unavailable"}</dd></div>
            <div><dt>Cost</dt><dd>{aiCost(trace.cost_microusd)}</dd></div>
            <div><dt>Latency</dt><dd>{trace.latency_ms === null ? "Unavailable" : `${trace.latency_ms} ms`}</dd></div>
            <div><dt>Evidence fingerprint</dt><dd>{recommendation.evidence_fingerprint.slice(0, 16)}</dd></div>
          </dl>
        ) : (
          <p>No model trace is available. The pilot trace gate will remain blocked.</p>
        )}
      </div>
      <div>
        <header><ShieldCheck size={15} /> Authority boundary</header>
        <ul>
          <li><Ban size={13} /> Cannot contact buyers</li>
          <li><Ban size={13} /> Cannot choose or accept an offer</li>
          <li><Ban size={13} /> Cannot bind Stonegate</li>
          <li><Ban size={13} /> Cannot change buyer records</li>
        </ul>
      </div>
    </section>
  );
}

function CitationRefs({
  citations,
  ids,
}: {
  citations: DispositionCopilotCitation[];
  ids: string[];
}) {
  const byId = new Map(citations.map((item) => [item.citation_id, item]));
  const resolved = ids.map((id) => byId.get(id)).filter(Boolean) as DispositionCopilotCitation[];
  return (
    <details className={styles.copilotCitations}>
      <summary>
        <Database size={13} />
        {resolved.length} saved citation{resolved.length === 1 ? "" : "s"}
      </summary>
      {resolved.length ? (
        <div>
          {resolved.map((item) => (
            <article data-status={item.status} key={item.citation_id}>
              <span>{item.label} - {labelize(item.source_type)}</span>
              <p>{item.fact}</p>
              <small>
                {labelize(item.status)}
                {item.observed_at ? ` - observed ${new Date(item.observed_at).toLocaleString()}` : ""}
              </small>
            </article>
          ))}
        </div>
      ) : (
        <p>No saved citation is attached to this item.</p>
      )}
    </details>
  );
}

function EvaluationSelect<T extends string>({
  label,
  onChange,
  options,
  value,
}: {
  label: string;
  onChange: (value: T) => void;
  options: T[];
  value: T;
}) {
  return (
    <label>
      <span>{label}</span>
      <select onChange={(event) => onChange(event.target.value as T)} value={value}>
        {options.map((item) => (
          <option key={item} value={item}>{labelize(item)}</option>
        ))}
      </select>
    </label>
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
