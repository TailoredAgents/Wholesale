import { getAiControlOverview, getDashboardData } from "../../lib/api";
import { labelize } from "../os-utils";
import { AiForms } from "./ai-forms";
import { AiOrchestratorWorkspace } from "./ai-orchestrator-workspace";
import { LeadSummaryRunner } from "./lead-summary-runner";
import aiStyles from "./ai-orchestrator.module.css";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

function formatMicroUsd(value: number | null) {
  if (value === null) {
    return "N/A";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: value < 10_000 ? 4 : 2,
  }).format(value / 1_000_000);
}

function formatPercent(value: number | null) {
  return value === null ? "N/A" : `${value}%`;
}

function formatLatency(value: number | null) {
  return value === null ? "N/A" : `${value} ms`;
}

export default async function AiControlPage() {
  const [{ ai, apiConnected }, dashboard] = await Promise.all([
    getAiControlOverview(),
    getDashboardData(),
  ]);

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>AI Control</p>
          <h2>AI Control</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Control plane</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Live controls" : "API fallback"}
          </strong>
        </div>
      </header>

      <section className={styles.metrics}>
        <article className={styles.metric}>
          <span>Agents</span>
          <strong>{ai.summary.agent_count}</strong>
          <small>{ai.summary.active_agent_count} active</small>
        </article>
        <article className={styles.metric}>
          <span>Prompt versions</span>
          <strong>{ai.summary.prompt_version_count}</strong>
          <small>Versioned instructions</small>
        </article>
        <article className={styles.metric}>
          <span>Runs logged</span>
          <strong>{ai.summary.run_count}</strong>
          <small>{formatLatency(ai.summary.average_latency_ms)} avg latency</small>
        </article>
        <article className={styles.metric}>
          <span>Pending approvals</span>
          <strong>{ai.summary.pending_approval_count}</strong>
          <small>Human review required</small>
        </article>
        <article className={styles.metric}>
          <span>AI cost</span>
          <strong>{formatMicroUsd(ai.summary.total_cost_microusd)}</strong>
          <small>
            {ai.summary.unpriced_run_count
              ? `${ai.summary.unpriced_run_count} unpriced runs`
              : "All completed usage priced"}
          </small>
        </article>
      </section>

      <AiOrchestratorWorkspace ai={ai} />

      <section className={styles.qualityBand}>
        <div className={styles.panelHeader}>
          <div>
            <h3>Call intelligence quality</h3>
            <small>{labelize(ai.call_intelligence_quality.autonomy_status)}</small>
          </div>
          <span>
            {ai.call_intelligence_quality.reviewed_calls}/
            {ai.call_intelligence_quality.minimum_review_sample} reviewed
          </span>
        </div>
        <dl className={styles.qualityGrid}>
          <div>
            <dt>Field agreement</dt>
            <dd>{formatPercent(ai.call_intelligence_quality.average_field_agreement)}</dd>
          </div>
          <div>
            <dt>Evidence coverage</dt>
            <dd>{formatPercent(ai.call_intelligence_quality.average_evidence_coverage)}</dd>
          </div>
          <div>
            <dt>AI confidence</dt>
            <dd>{formatPercent(ai.call_intelligence_quality.average_confidence)}</dd>
          </div>
          <div>
            <dt>Approved</dt>
            <dd>{ai.call_intelligence_quality.approved_calls}</dd>
          </div>
          <div>
            <dt>Rejected</dt>
            <dd>{ai.call_intelligence_quality.rejected_calls}</dd>
          </div>
          <div>
            <dt>Needs review</dt>
            <dd>{ai.call_intelligence_quality.pending_review_calls}</dd>
          </div>
          <div>
            <dt>Failures</dt>
            <dd>{ai.call_intelligence_quality.failed_calls}</dd>
          </div>
          <div>
            <dt>High correction</dt>
            <dd>{ai.call_intelligence_quality.high_correction_calls}</dd>
          </div>
        </dl>
        {ai.call_intelligence_quality.autonomy_blockers.length ? (
          <div className={styles.qualityBlockers}>
            {ai.call_intelligence_quality.autonomy_blockers.map((blocker) => (
              <span key={blocker}>{blocker}</span>
            ))}
          </div>
        ) : (
          <p className={styles.qualityReady}>
            Quality thresholds support a controlled low-risk pilot. Human approval remains active.
          </p>
        )}
      </section>

      <details className={aiStyles.legacyTools}>
        <summary>Manual testing utilities</summary>
        <section className={styles.contentGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Control Entry</h3>
            <span>Definitions and logs</span>
          </div>
          <LeadSummaryRunner leads={dashboard.leads} />
          <AiForms ai={ai} />
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Agent Registry</h3>
            <span>{ai.agents.length} agents</span>
          </div>
          <div className={styles.buyerList}>
            {ai.agents.length === 0 ? <p>No agents defined yet.</p> : null}
            {ai.agents.map((agent) => (
              <article key={agent.id}>
                <div>
                  <strong>{agent.name}</strong>
                  <span>{labelize(agent.status)}</span>
                </div>
                <dl>
                  <div>
                    <dt>Risk</dt>
                    <dd>{labelize(agent.risk_level)}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>{agent.model_name}</dd>
                  </div>
                  <div>
                    <dt>Tools</dt>
                    <dd>{agent.tool_permissions.length}</dd>
                  </div>
                  <div>
                    <dt>Approval</dt>
                    <dd>{agent.requires_human_approval ? "Required" : "Not required"}</dd>
                  </div>
                </dl>
                <small>{agent.description}</small>
              </article>
            ))}
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Run Logs</h3>
            <span>{ai.runs.length} recent runs</span>
          </div>
          <div className={styles.buyerList}>
            {ai.runs.length === 0 ? <p>No AI runs logged yet.</p> : null}
            {ai.runs.map((run) => (
              <article key={run.id}>
                <div>
                  <strong>{labelize(run.status)}</strong>
                  <span>{run.model_name}</span>
                </div>
                <dl>
                  <div>
                    <dt>Input / output</dt>
                    <dd>
                      {run.input_tokens ?? "N/A"} / {run.output_tokens ?? "N/A"}
                    </dd>
                  </div>
                  <div>
                    <dt>Cost</dt>
                    <dd>{formatMicroUsd(run.cost_microusd)}</dd>
                  </div>
                  <div>
                    <dt>Latency</dt>
                    <dd>{formatLatency(run.latency_ms)}</dd>
                  </div>
                  <div>
                    <dt>Tools</dt>
                    <dd>{run.tool_calls.length}</dd>
                  </div>
                </dl>
                <small>{run.output_summary ?? run.input_summary}</small>
                {run.tool_calls.map((toolCall) => (
                  <p key={toolCall.id}>
                    <strong>{toolCall.tool_key}</strong>
                    <span>{labelize(toolCall.status)}</span>
                  </p>
                ))}
              </article>
            ))}
          </div>
        </article>
        </section>
      </details>
    </>
  );
}
