import { getAiControlOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import { AiForms } from "./ai-forms";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

function formatMoney(cents: number | null) {
  if (cents === null) {
    return "N/A";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

function formatLatency(value: number | null) {
  return value === null ? "N/A" : `${value} ms`;
}

export default async function AiControlPage() {
  const { ai, apiConnected } = await getAiControlOverview();

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>AI Control</p>
          <h2>Agent governance</h2>
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
          <strong>{formatMoney(ai.summary.total_cost_cents)}</strong>
          <small>Logged run cost</small>
        </article>
      </section>

      <section className={styles.contentGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Control Entry</h3>
            <span>Definitions and logs</span>
          </div>
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
                    <dt>Tokens</dt>
                    <dd>{run.total_tokens ?? "N/A"}</dd>
                  </div>
                  <div>
                    <dt>Cost</dt>
                    <dd>{formatMoney(run.cost_cents)}</dd>
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
    </>
  );
}
