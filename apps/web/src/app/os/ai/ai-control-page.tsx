import { Activity, Bot, CircleDollarSign, Clock3, ShieldAlert } from "lucide-react";

import { getAiControlOverview, getDashboardData, getWorkspaceProfile } from "../../lib/api";
import { ManagementJourney } from "../_components/management-journey";
import { ManagementSummaryStrip } from "../_components/management-summary-strip";
import managementStyles from "../_components/management-workspaces.module.css";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
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
  const [{ ai, apiConnected }, dashboard, profile] = await Promise.all([
    getAiControlOverview(),
    getDashboardData(),
    getWorkspaceProfile(),
  ]);
  const metrics = ai.orchestrator.metrics;
  const canManage = Boolean(profile?.permissions.includes("ai:change_prompts"));
  const openExceptions =
    ai.summary.pending_approval_count +
    metrics.unreviewed_trace_count +
    metrics.budget_blocked_run_count +
    ai.call_intelligence_quality.autonomy_blockers.length;
  const nextAction = metrics.unreviewed_trace_count
    ? "Review unverified traces"
    : ai.summary.pending_approval_count
      ? "Review AI approvals"
      : metrics.pending_promotion_count
        ? "Review promotion evidence"
        : "Run controlled evaluations";
  const primaryException = metrics.budget_blocked_run_count
    ? `${metrics.budget_blocked_run_count} budget-blocked run${metrics.budget_blocked_run_count === 1 ? "" : "s"}`
    : ai.call_intelligence_quality.autonomy_blockers[0] ?? "No control exception";

  return (
    <WorkspacePage>
      <PageHeader
        description="Observe agent behavior, test changes, review evidence, control cost, and roll back promoted capabilities."
        eyebrow="Control / governed automation"
        meta={<StatusBadge tone={apiConnected ? "success" : "danger"}>{apiConnected ? "Live controls" : "AI controls unavailable"}</StatusBadge>}
        title="AI Control"
      />
      <ManagementJourney active="ai" />
      <ManagementSummaryStrip
        authority={{ label: "External authority", value: "Execution blocked", detail: canManage ? "You may test and request promotion" : "Control policy is view only", tone: "success" }}
        comparison={{ label: "Copilot coverage", value: `${metrics.active_copilot_count} of ${metrics.copilot_count} approved`, detail: `${metrics.portfolio_agent_count} specialist engines`, tone: metrics.active_copilot_count ? "info" : "warning" }}
        exception={{ label: "Primary exception", value: primaryException, detail: `${openExceptions} open control signals`, tone: openExceptions || ai.call_intelligence_quality.autonomy_blockers.length ? "warning" : "success" }}
        nextAction={{ label: "Management next step", value: nextAction, detail: "Human approval remains mandatory", tone: "info" }}
        period={{ label: "Reporting basis", value: "Lifetime governed usage", detail: `${metrics.governed_run_count} orchestrated runs`, tone: "neutral" }}
      />

      <section className={managementStyles.metricGrid} aria-label="AI control performance">
        <div><Bot size={17} /><span>Role copilots</span><strong>{metrics.copilot_count}</strong><small>{metrics.active_copilot_count} owner-approved</small></div>
        <div><Activity size={17} /><span>Runs logged</span><strong>{ai.summary.run_count}</strong><small>{formatLatency(ai.summary.average_latency_ms)} average latency</small></div>
        <div><ShieldAlert size={17} /><span>Pending approvals</span><strong>{ai.summary.pending_approval_count}</strong><small>{metrics.unreviewed_trace_count} traces need review</small></div>
        <div><CircleDollarSign size={17} /><span>Recorded cost</span><strong>{formatMicroUsd(ai.summary.total_cost_microusd)}</strong><small>{ai.summary.unpriced_run_count ? `${ai.summary.unpriced_run_count} unpriced runs` : "Completed usage priced"}</small></div>
        <div><Clock3 size={17} /><span>Promotions</span><strong>{metrics.active_promotion_count}</strong><small>{metrics.pending_promotion_count} pending · rollback available</small></div>
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
    </WorkspacePage>
  );
}
