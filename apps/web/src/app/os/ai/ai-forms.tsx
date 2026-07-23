"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { AiControlOverview } from "../../lib/api";
import styles from "../page.module.css";

type Status = "idle" | "saving" | "saved" | "error";

function formString(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

function optionalFormString(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value || null;
}

function optionalInteger(formData: FormData, key: string) {
  const value = formString(formData, key);
  return value ? Number(value) : null;
}

export function AiForms({ ai }: { ai: AiControlOverview }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [agentStatus, setAgentStatus] = useState<Status>("idle");
  const [promptStatus, setPromptStatus] = useState<Status>("idle");
  const [runStatus, setRunStatus] = useState<Status>("idle");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function getHeaders() {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      headers["X-Dev-User-Email"] = devUserEmail;
    }
    return headers;
  }

  async function submit(
    event: FormEvent<HTMLFormElement>,
    endpoint: string,
    body: Record<string, unknown>,
    setStatus: (status: Status) => void,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    setStatus("saving");

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/ai/${endpoint}`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error("Unable to save AI control record.");
      }
      form.reset();
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className={styles.financeForms}>
      <form
        className={styles.financeForm}
        onSubmit={(event) => {
          const formData = new FormData(event.currentTarget);
          void submit(
            event,
            "agents",
            {
              key: formString(formData, "key"),
              name: formString(formData, "name"),
              description: formString(formData, "description"),
              status: formString(formData, "status"),
              model_name: formString(formData, "model_name"),
              risk_level: formString(formData, "risk_level"),
              requires_human_approval: true,
              tool_permissions: [
                {
                  tool_key: formString(formData, "tool_key"),
                  tool_name: formString(formData, "tool_name"),
                  permission_level: formString(formData, "permission_level"),
                  is_enabled: true,
                  requires_approval: true,
                },
              ],
            },
            setAgentStatus,
          );
        }}
      >
        <h3>Agent Definition</h3>
        <div className={styles.formGrid}>
          <label>
            <span>Key</span>
            <input name="key" maxLength={120} placeholder="follow_up_drafter" required />
          </label>
          <label>
            <span>Name</span>
            <input name="name" maxLength={255} placeholder="Follow-up drafter" required />
          </label>
        </div>
        <label>
          <span>Description</span>
          <textarea name="description" maxLength={1000} required rows={3} />
        </label>
        <div className={styles.formGrid}>
          <label>
            <span>Status</span>
            <select name="status" defaultValue="draft">
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="retired">Retired</option>
            </select>
          </label>
          <label>
            <span>Risk</span>
            <select name="risk_level" defaultValue="medium">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </label>
        </div>
        <label>
          <span>Model</span>
          <input name="model_name" defaultValue="gpt-5.6-sol" maxLength={120} required />
        </label>
        <div className={styles.formGrid}>
          <label>
            <span>Tool key</span>
            <input name="tool_key" maxLength={160} placeholder="communications.draft_sms" required />
          </label>
          <label>
            <span>Tool name</span>
            <input name="tool_name" maxLength={255} placeholder="Draft SMS" required />
          </label>
        </div>
        <label>
          <span>Permission</span>
          <select name="permission_level" defaultValue="draft">
            <option value="read">Read</option>
            <option value="draft">Draft</option>
            <option value="propose">Propose</option>
            <option value="write_blocked">Write blocked</option>
          </select>
        </label>
        <button disabled={agentStatus === "saving"} type="submit">
          Add agent
        </button>
        {agentStatus !== "idle" ? <p className={styles[agentStatus]}>{agentStatus}</p> : null}
      </form>

      <form
        className={styles.financeForm}
        onSubmit={(event) => {
          const formData = new FormData(event.currentTarget);
          const agentId = formString(formData, "agent_id");
          void submit(
            event,
            `agents/${agentId}/prompts`,
            {
              status: formString(formData, "status"),
              prompt_text: formString(formData, "prompt_text"),
              change_notes: optionalFormString(formData, "change_notes"),
            },
            setPromptStatus,
          );
        }}
      >
        <h3>Prompt Version</h3>
        <label>
          <span>Agent</span>
          <select name="agent_id" required>
            <option value="">Select agent</option>
            {ai.agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Status</span>
          <select name="status" defaultValue="draft">
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="retired">Retired</option>
          </select>
        </label>
        <label>
          <span>Prompt</span>
          <textarea name="prompt_text" maxLength={8000} required rows={5} />
        </label>
        <label>
          <span>Change notes</span>
          <textarea name="change_notes" maxLength={2000} rows={3} />
        </label>
        <button disabled={promptStatus === "saving" || ai.agents.length === 0} type="submit">
          Add prompt version
        </button>
        {promptStatus !== "idle" ? <p className={styles[promptStatus]}>{promptStatus}</p> : null}
      </form>

      <form
        className={styles.financeForm}
        onSubmit={(event) => {
          const formData = new FormData(event.currentTarget);
          const toolKey = optionalFormString(formData, "tool_key");
          void submit(
            event,
            "runs",
            {
              agent_definition_id: formString(formData, "agent_definition_id"),
              prompt_version_id: optionalFormString(formData, "prompt_version_id"),
              status: formString(formData, "status"),
              input_summary: formString(formData, "input_summary"),
              output_summary: optionalFormString(formData, "output_summary"),
              total_tokens: optionalInteger(formData, "total_tokens"),
              cost_cents: optionalInteger(formData, "cost_cents"),
              latency_ms: optionalInteger(formData, "latency_ms"),
              tool_calls: toolKey
                ? [
                    {
                      tool_key: toolKey,
                      status: "proposed",
                      requires_approval: true,
                    },
                  ]
                : [],
            },
            setRunStatus,
          );
        }}
      >
        <h3>Run Log</h3>
        <label>
          <span>Agent</span>
          <select name="agent_definition_id" required>
            <option value="">Select agent</option>
            {ai.agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Prompt</span>
          <select name="prompt_version_id">
            <option value="">No prompt version</option>
            {ai.prompt_versions.map((prompt) => (
              <option key={prompt.id} value={prompt.id}>
                Version {prompt.version_number}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Status</span>
          <select name="status" defaultValue="needs_review">
            <option value="completed">Completed</option>
            <option value="needs_review">Needs review</option>
            <option value="failed">Failed</option>
          </select>
        </label>
        <label>
          <span>Input summary</span>
          <textarea name="input_summary" maxLength={4000} required rows={3} />
        </label>
        <label>
          <span>Output summary</span>
          <textarea name="output_summary" maxLength={4000} rows={3} />
        </label>
        <div className={styles.formGrid}>
          <label>
            <span>Tokens</span>
            <input name="total_tokens" inputMode="numeric" />
          </label>
          <label>
            <span>Cost cents</span>
            <input name="cost_cents" inputMode="numeric" />
          </label>
        </div>
        <div className={styles.formGrid}>
          <label>
            <span>Latency ms</span>
            <input name="latency_ms" inputMode="numeric" />
          </label>
          <label>
            <span>Proposed tool</span>
            <input name="tool_key" maxLength={160} placeholder="communications.draft_sms" />
          </label>
        </div>
        <button disabled={runStatus === "saving" || ai.agents.length === 0} type="submit">
          Log run
        </button>
        {runStatus !== "idle" ? <p className={styles[runStatus]}>{runStatus}</p> : null}
      </form>
    </div>
  );
}
