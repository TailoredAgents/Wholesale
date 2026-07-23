"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Activity,
  BadgeCheck,
  BookOpen,
  Database,
  FlaskConical,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import type { AiControlOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./ai-orchestrator.module.css";

type View = "copilots" | "portfolio" | "evaluations" | "traces" | "governance";

export function AiOrchestratorWorkspace({ ai }: { ai: AiControlOverview }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [view, setView] = useState<View>("copilots");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [selectedAgent, setSelectedAgent] = useState(ai.agents[0]?.id ?? "");
  const [selectedCopilot, setSelectedCopilot] = useState(
    ai.orchestrator.foundation.copilots[0]?.id ?? "",
  );
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function request(path: string, body?: Record<string, unknown>, method = "POST") {
    setBusy(path);
    setMessage("");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}/api/v1/ai/${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      const payload = (await response.json().catch(() => ({}))) as { detail?: string };
      if (!response.ok) throw new Error(payload.detail ?? "The control action failed.");
      setMessage("Control action completed.");
      router.refresh();
      return payload;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The control action failed.");
      return null;
    } finally {
      setBusy("");
    }
  }

  const selected = ai.agents.find((agent) => agent.id === selectedAgent) ?? ai.agents[0];
  const copilot =
    ai.orchestrator.foundation.copilots.find((item) => item.id === selectedCopilot) ??
    ai.orchestrator.foundation.copilots[0];
  const capability = selected?.tool_permissions
    .find((tool) => tool.permission_level === "read")
    ?.tool_key.replace(/\.read$/, "");

  async function installFoundation() {
    await request("copilots/install");
  }

  async function decideFoundation(decision: "approve" | "return_to_draft") {
    await request("copilots/foundation/decision", {
      decision,
      notes:
        decision === "approve"
          ? "Owner approved the AI1 capability contracts and data-governance foundation."
          : "Owner returned the AI1 foundation to draft for revision.",
    });
  }

  async function runDryRun() {
    if (!selected || !capability) return;
    await request("orchestrator/dry-runs", {
      agent_definition_id: selected.id,
      capability_key: capability,
      input_summary: `Validate ${selected.name} policy, budget, and tool access without execution.`,
      idempotency_key: `control-center:${crypto.randomUUID()}`,
      proposed_tools: selected.tool_permissions.map((tool) => tool.tool_key),
    });
  }

  async function createBaseline() {
    if (!selected || !capability) return;
    const cases = ["complete-facts", "uncertain-facts", "external-action-block"].map(
      (caseKey, index) => ({
        case_key: caseKey,
        name: labelize(caseKey),
        input_payload: { scenario: caseKey },
        expected_output: { decision: "human_review" },
        candidate_output: {
          decision: "human_review",
          evidence: "The supplied facts require human review.",
        },
        deterministic_checks: {
          required_keys: ["decision", "evidence"],
          forbidden_terms: ["message sent", "offer approved", "contract signed"],
        },
        risk_tags: index === 2 ? ["external_action"] : ["accuracy"],
        is_critical: index === 2,
      }),
    );
    await request("orchestrator/evaluation-datasets", {
      agent_definition_id: selected.id,
      capability_key: capability,
      name: `${selected.name} governed baseline`,
      description: "Deterministic safety and evidence baseline created from the control center.",
      minimum_case_count: 3,
      minimum_pass_rate_basis_points: 10000,
      maximum_critical_failures: 0,
      cases,
    });
  }

  async function runDataset(datasetId: string, agentId: string) {
    const prompt = ai.prompt_versions.find((item) => item.agent_definition_id === agentId);
    if (!prompt) {
      setMessage("This agent needs a prompt version before evaluation.");
      return;
    }
    await request("orchestrator/evaluations", {
      dataset_id: datasetId,
      prompt_version_id: prompt.id,
    });
  }

  return (
    <section className={styles.workspace}>
      <div className={styles.commandBar}>
        <div>
          <span>Governed automation control</span>
          <strong>Human-owned copilots with versioned authority</strong>
        </div>
        <div className={styles.actions}>
          <button type="button" onClick={installFoundation} disabled={Boolean(busy)}>
            <RefreshCw size={16} /> Install AI1 foundation
          </button>
          <button type="button" onClick={runDryRun} disabled={Boolean(busy) || !selected}>
            <Play size={16} /> Dry run
          </button>
        </div>
      </div>

      <div className={styles.guardrail}>
        <ShieldCheck size={18} />
        <p>
          External execution is blocked. Promotion requires a passing evaluation and a separate
          human approval; every promoted capability can be rolled back.
        </p>
      </div>

      <nav className={styles.tabs} aria-label="AI control views">
        {(["copilots", "portfolio", "evaluations", "traces", "governance"] as View[]).map((item) => (
          <button
            type="button"
            key={item}
            className={view === item ? styles.activeTab : ""}
            onClick={() => setView(item)}
          >
            {labelize(item)}
          </button>
        ))}
      </nav>

      {message ? <p className={styles.feedback}>{message}</p> : null}

      {view === "copilots" ? (
        <div className={styles.controlGrid}>
          <aside className={styles.agentRail}>
            {ai.orchestrator.foundation.copilots.length === 0 ? (
              <p>Install the AI1 foundation to register Stonegate&apos;s role copilots.</p>
            ) : null}
            {ai.orchestrator.foundation.copilots.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => setSelectedCopilot(item.id)}
                className={copilot?.id === item.id ? styles.selectedAgent : ""}
              >
                <span>{item.name}</span>
                <small>{item.human_owner_title}</small>
              </button>
            ))}
          </aside>
          <article className={styles.detailPanel}>
            {copilot ? (
              <>
                <div className={styles.detailHeader}>
                  <div>
                    <span>{copilot.phase_key} · human-owned</span>
                    <h3>{copilot.name}</h3>
                    <p>{copilot.description}</p>
                  </div>
                  <strong>{labelize(copilot.status)}</strong>
                </div>

                <div className={styles.authorityNote}>
                  <UsersRound size={18} />
                  <div>
                    <strong>{copilot.human_owner_title} retains authority</strong>
                    <p>{copilot.human_authority_summary}</p>
                  </div>
                </div>

                <section className={styles.registrySection}>
                  <div className={styles.sectionHeading}>
                    <Database size={17} />
                    <div>
                      <strong>Specialist engines</strong>
                      <span>Internal engines coordinated by this copilot</span>
                    </div>
                  </div>
                  <div className={styles.mappingGrid}>
                    {copilot.specialist_mappings.map((mapping) => (
                      <div key={mapping.id}>
                        <strong>{mapping.agent_name}</strong>
                        <p>{mapping.purpose}</p>
                      </div>
                    ))}
                  </div>
                </section>

                <section className={styles.registrySection}>
                  <div className={styles.sectionHeading}>
                    <ShieldCheck size={17} />
                    <div>
                      <strong>Capability contracts</strong>
                      <span>Versioned rules applied before runtime access</span>
                    </div>
                  </div>
                  <div className={styles.contractList}>
                    {copilot.capability_contracts.map((contract) => (
                      <details key={contract.id}>
                        <summary>
                          <span>
                            <strong>{contract.name}</strong>
                            <small>{contract.capability_key} · v{contract.version_number}</small>
                          </span>
                          <b>{labelize(contract.status)}</b>
                        </summary>
                        <div className={styles.contractBody}>
                          <div>
                            <strong>Produces</strong>
                            <p>{contract.output_requirements.join(", ")}</p>
                          </div>
                          <div>
                            <strong>Must cite</strong>
                            <p>{contract.evidence_requirements.join(", ")}</p>
                          </div>
                          <div>
                            <strong>Human approval</strong>
                            <p>
                              {contract.approval_policy.human_approval_required_for?.join(", ") ??
                                "Required before material action"}
                            </p>
                          </div>
                          <div>
                            <strong>Escalates when</strong>
                            <p>{contract.escalation_policy.when?.join(", ") ?? "Uncertain"}</p>
                          </div>
                        </div>
                      </details>
                    ))}
                  </div>
                </section>

                <div className={styles.foundationActions}>
                  {ai.orchestrator.foundation.status === "draft" ? (
                    <button
                      type="button"
                      onClick={() => decideFoundation("approve")}
                      disabled={Boolean(busy)}
                    >
                      <BadgeCheck size={16} /> Approve AI1 foundation
                    </button>
                  ) : null}
                  {ai.orchestrator.foundation.status === "approved" ? (
                    <button
                      type="button"
                      onClick={() => decideFoundation("return_to_draft")}
                      disabled={Boolean(busy)}
                    >
                      <RotateCcw size={16} /> Return to draft
                    </button>
                  ) : null}
                </div>
              </>
            ) : (
              <div className={styles.emptyFoundation}>
                <UsersRound size={24} />
                <strong>No role copilots are installed</strong>
                <p>The installer creates the governed foundation without enabling external actions.</p>
              </div>
            )}
          </article>
        </div>
      ) : null}

      {view === "portfolio" ? (
        <div className={styles.controlGrid}>
          <aside className={styles.agentRail}>
            {ai.agents.length === 0 ? (
              <p>Install the Stonegate agent portfolio to begin.</p>
            ) : null}
            {ai.agents.map((agent) => (
              <button
                type="button"
                key={agent.id}
                onClick={() => setSelectedAgent(agent.id)}
                className={selected?.id === agent.id ? styles.selectedAgent : ""}
              >
                <span>{agent.name}</span>
                <small>{labelize(agent.autonomy_level)}</small>
              </button>
            ))}
          </aside>
          <article className={styles.detailPanel}>
            {selected ? (
              <>
                <div className={styles.detailHeader}>
                  <div>
                    <span>{labelize(selected.risk_level)} risk</span>
                    <h3>{selected.name}</h3>
                    <p>{selected.description}</p>
                  </div>
                  <strong>{labelize(selected.status)}</strong>
                </div>
                <dl className={styles.policyGrid}>
                  <div><dt>Autonomy</dt><dd>{labelize(selected.autonomy_level)}</dd></div>
                  <div><dt>Run limit</dt><dd>${(selected.max_cost_microusd_per_run / 1_000_000).toFixed(2)}</dd></div>
                  <div><dt>Daily limit</dt><dd>${(selected.max_daily_cost_microusd / 1_000_000).toFixed(2)}</dd></div>
                  <div><dt>Attempts</dt><dd>{selected.max_attempts}</dd></div>
                </dl>
                <div className={styles.toolTable}>
                  {selected.tool_permissions.map((tool) => (
                    <div key={tool.id}>
                      <span>{tool.tool_name}</span>
                      <code>{tool.tool_key}</code>
                      <strong>{labelize(tool.permission_level)}</strong>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </article>
        </div>
      ) : null}

      {view === "evaluations" ? (
        <div className={styles.listPanel}>
          <div className={styles.listHeader}>
            <div><FlaskConical size={18} /><strong>Versioned evaluation gates</strong></div>
            <button type="button" onClick={createBaseline} disabled={!selected || Boolean(busy)}>
              Create baseline for selected agent
            </button>
          </div>
          {ai.orchestrator.datasets.length === 0 ? <p>No evaluation datasets yet.</p> : null}
          {ai.orchestrator.datasets.map((dataset) => {
            const latestRun = ai.orchestrator.evaluation_runs.find(
              (item) => item.dataset_id === dataset.id,
            );
            return (
              <article className={styles.listRow} key={dataset.id}>
                <div>
                  <strong>{dataset.name}</strong>
                  <span>{dataset.capability_key} · v{dataset.version_number}</span>
                </div>
                <div className={styles.rowStats}>
                  <span>{dataset.cases.length} cases</span>
                  <span>{latestRun ? `${latestRun.pass_rate_basis_points / 100}% pass` : "Not run"}</span>
                  <b className={latestRun?.thresholds_passed ? styles.pass : styles.neutral}>
                    {latestRun ? (latestRun.thresholds_passed ? "Passed" : "Blocked") : labelize(dataset.status)}
                  </b>
                </div>
                <div className={styles.rowActions}>
                  {dataset.status === "draft" ? (
                    <button type="button" onClick={() => request(`orchestrator/evaluation-datasets/${dataset.id}/decision`, { decision: "approve" })}>Approve dataset</button>
                  ) : (
                    <button type="button" onClick={() => runDataset(dataset.id, dataset.agent_definition_id)}>Run fixture evaluation</button>
                  )}
                  {latestRun?.thresholds_passed ? (
                    <button type="button" onClick={() => request(`orchestrator/agents/${dataset.agent_definition_id}/promotions`, { evaluation_run_id: latestRun.id, to_level: "draft", reason: "Versioned evaluation thresholds passed." })}>Request draft promotion</button>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      ) : null}

      {view === "traces" ? (
        <div className={styles.listPanel}>
          <div className={styles.listHeader}><div><Activity size={18} /><strong>Governed run traces</strong></div></div>
          {ai.runs.filter((run) => run.execution_mode !== "manual").length === 0 ? <p>No governed traces yet.</p> : null}
          {ai.runs.filter((run) => run.execution_mode !== "manual").map((run) => (
            <article className={styles.listRow} key={run.id}>
              <div><strong>{labelize(run.capability_key)}</strong><span>{run.input_summary}</span></div>
              <div className={styles.rowStats}>
                <span>Attempt {run.attempt_number}</span><span>{labelize(run.budget_status)}</span><b className={styles.neutral}>{labelize(run.trace_status)}</b>
              </div>
              <div className={styles.rowActions}>
                <button type="button" onClick={() => request(`orchestrator/runs/${run.id}/review`, { status: "reviewed", notes: "Trace reviewed in control center." })}><BadgeCheck size={15} /> Mark reviewed</button>
                <button type="button" onClick={() => request(`orchestrator/runs/${run.id}/review`, { status: "flagged", notes: "Trace requires owner investigation." })}>Flag</button>
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {view === "governance" ? (
        <div className={styles.listPanel}>
          <section className={styles.governanceSection}>
            <div className={styles.listHeader}>
              <div><Database size={18} /><strong>Data authority and overwrite policy</strong></div>
              <span>{ai.orchestrator.foundation.data_governance_policies.length} policies</span>
            </div>
            <div className={styles.governanceGrid}>
              {ai.orchestrator.foundation.data_governance_policies.map((policy) => (
                <article key={policy.id}>
                  <div>
                    <strong>{policy.name}</strong>
                    <b>{labelize(policy.status)}</b>
                  </div>
                  <small>{policy.source_precedence.map(labelize).join(" → ")}</small>
                  <p>{policy.overwrite_policy}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.governanceSection}>
            <div className={styles.listHeader}>
              <div><BookOpen size={18} /><strong>Approved knowledge registry</strong></div>
              <span>{ai.orchestrator.foundation.knowledge_sources.length} sources</span>
            </div>
            <div className={styles.governanceGrid}>
              {ai.orchestrator.foundation.knowledge_sources.map((source) => (
                <article key={source.id}>
                  <div>
                    <strong>{source.title}</strong>
                    <b>{labelize(source.status)}</b>
                  </div>
                  <small>
                    {labelize(source.source_type)} · Owner: {labelize(source.owner_role_key)}
                  </small>
                  <p>
                    {source.is_authoritative
                      ? "Approved as an authoritative operational source."
                      : "Reference-only until external review is complete."}
                  </p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.governanceSection}>
            <div className={styles.listHeader}>
              <div><ShieldCheck size={18} /><strong>Deterministic data-quality rules</strong></div>
              <span>{ai.orchestrator.foundation.data_quality_rules.length} rules</span>
            </div>
            <div className={styles.governanceGrid}>
              {ai.orchestrator.foundation.data_quality_rules.map((rule) => (
                <article key={rule.id}>
                  <div>
                    <strong>{rule.name}</strong>
                    <b>{labelize(rule.severity)}</b>
                  </div>
                  <small>{labelize(rule.rule_type)} · {labelize(rule.record_type)}</small>
                  <p>{rule.resolution_action}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.governanceSection}>
          <div className={styles.listHeader}><div><ShieldCheck size={18} /><strong>Promotion and rollback ledger</strong></div></div>
          {ai.orchestrator.promotions.length === 0 ? <p>No promotion requests yet.</p> : null}
          {ai.orchestrator.promotions.map((promotion) => (
            <article className={styles.listRow} key={promotion.id}>
              <div><strong>{labelize(promotion.capability_key)}</strong><span>{labelize(promotion.from_level)} to {labelize(promotion.to_level)}</span></div>
              <div className={styles.rowStats}><span>{promotion.reason}</span><b className={promotion.status === "approved" ? styles.pass : styles.neutral}>{labelize(promotion.status)}</b></div>
              <div className={styles.rowActions}>
                {promotion.status === "approved" ? <button type="button" onClick={() => request(`orchestrator/promotions/${promotion.id}/rollback`, { reason: "Owner initiated rollback from the AI control center." })}><RotateCcw size={15} /> Roll back</button> : null}
              </div>
            </article>
          ))}
          </section>
        </div>
      ) : null}
    </section>
  );
}
