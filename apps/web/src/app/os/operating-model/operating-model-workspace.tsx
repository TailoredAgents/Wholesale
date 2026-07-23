"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { LeadListItem, OperatingModelOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./operating-model.module.css";

type Tab = "active" | "history" | "credits" | "launches";
type RequestStatus = "idle" | "saving" | "saved" | "error";

const tabs: Array<{ key: Tab; label: string }> = [
  { key: "active", label: "Active policy" },
  { key: "credits", label: "Pending decisions" },
  { key: "history", label: "Policy history" },
  { key: "launches", label: "Market launches" },
];

function formValue(data: FormData, key: string) {
  return String(data.get(key) ?? "").trim();
}

function dollarsToCents(value: string) {
  return Math.round(Number(value || 0) * 100);
}

function percentToBasisPoints(value: string) {
  return Math.round(Number(value || 0) * 100);
}

function formatMoney(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatPercent(basisPoints: number) {
  return `${(basisPoints / 100).toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
}

function modeShare(minimum: number, maximum: number) {
  return minimum === maximum
    ? formatPercent(minimum)
    : `${formatPercent(minimum)}-${formatPercent(maximum)}`;
}

export function OperatingModelWorkspace({
  operatingModel,
  leads,
}: {
  operatingModel: OperatingModelOverview;
  leads: LeadListItem[];
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("active");
  const [status, setStatus] = useState<RequestStatus>("idle");
  const [message, setMessage] = useState("");
  const [selectedChecklistId, setSelectedChecklistId] = useState(
    operatingModel.launch_checklists[0]?.id ?? "",
  );
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const activePlan = operatingModel.compensation_plans.find((plan) => plan.status === "active");
  const activeUsers = operatingModel.users.filter((user) => user.is_active);
  const proposedCredits = operatingModel.role_credits.filter((credit) => credit.status === "proposed");
  const selectedChecklist = operatingModel.launch_checklists.find(
    (checklist) => checklist.id === selectedChecklistId,
  );

  async function headers() {
    const token = await getToken().catch(() => null);
    const result: Record<string, string> = { "Content-Type": "application/json" };
    if (token) result.Authorization = `Bearer ${token}`;
    else result["X-Dev-User-Email"] = devUserEmail;
    return result;
  }

  async function mutate(path: string, method: "POST" | "PATCH", body: object) {
    setStatus("saving");
    setMessage("");
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers: await headers(),
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "The operation could not be completed.");
      }
      setStatus("saved");
      setMessage("Saved.");
      router.refresh();
      return true;
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The operation could not be completed.");
      return false;
    }
  }

  async function submitPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await mutate("/api/v1/operating-model/compensation-plans", "POST", {
      name: formValue(data, "name"),
      acquisition_reserve_cents: dollarsToCents(formValue(data, "acquisition_reserve")),
      target_company_margin_basis_points: percentToBasisPoints(formValue(data, "target_margin")),
      lead_manager_basis_points: percentToBasisPoints(formValue(data, "lead_manager")),
      acquisitions_closer_basis_points: percentToBasisPoints(formValue(data, "acquisitions_closer")),
      ceo_management_basis_points: percentToBasisPoints(formValue(data, "ceo_management")),
      dispositions_basis_points: percentToBasisPoints(formValue(data, "dispositions")),
      transaction_coordinator_basis_points: percentToBasisPoints(formValue(data, "transaction_coordinator")),
      transaction_coordinator_cap_cents: dollarsToCents(formValue(data, "transaction_coordinator_cap")),
      ai_managed_disposition_basis_points: percentToBasisPoints(formValue(data, "ai_managed")),
      ai_oversight_disposition_min_basis_points: percentToBasisPoints(formValue(data, "ai_oversight_min")),
      ai_oversight_disposition_max_basis_points: percentToBasisPoints(formValue(data, "ai_oversight_max")),
      notes: formValue(data, "notes") || null,
    });
    if (saved) form.reset();
  }

  async function activatePlan(planId: string) {
    const reason = window.prompt("Document why this compensation version is being activated.");
    if (!reason) return;
    await mutate(`/api/v1/operating-model/compensation-plans/${planId}/activate`, "POST", {
      reason,
    });
  }

  async function submitCredit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activePlan) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await mutate("/api/v1/operating-model/role-credits", "POST", {
      compensation_plan_version_id: activePlan.id,
      lead_id: formValue(data, "lead_id"),
      user_id: formValue(data, "user_id"),
      role_key: formValue(data, "role_key"),
      credit_basis_points: percentToBasisPoints(formValue(data, "credit_share")),
      notes: formValue(data, "notes") || null,
    });
    if (saved) form.reset();
  }

  async function decideCredit(creditId: string, decision: "approve" | "reject") {
    const reason = window.prompt(`Document why this role credit should be ${decision}d.`);
    if (!reason) return;
    await mutate(`/api/v1/operating-model/role-credits/${creditId}/decision`, "POST", {
      decision,
      reason,
    });
  }

  async function submitChecklist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const marketId = formValue(data, "market_id");
    const saved = await mutate(
      `/api/v1/operating-model/markets/${marketId}/launch-checklists`,
      "POST",
      {
        owner_user_id: formValue(data, "owner_user_id"),
        notes: formValue(data, "notes") || null,
      },
    );
    if (saved) form.reset();
  }

  async function updateChecklistItem(event: FormEvent<HTMLFormElement>, itemId: string) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await mutate(`/api/v1/operating-model/launch-checklist-items/${itemId}`, "PATCH", {
      status: formValue(data, "status"),
      responsible_user_id: formValue(data, "responsible_user_id") || null,
      evidence_notes: formValue(data, "evidence_notes") || null,
    });
  }

  async function approveChecklist(checklistId: string) {
    const reason = window.prompt("Document the final launch approval decision.");
    if (!reason) return;
    await mutate(`/api/v1/operating-model/launch-checklists/${checklistId}/approve`, "POST", {
      reason,
    });
  }

  return (
    <section className={styles.workspace}>
      <div className={styles.metrics}>
        <div><span>Active plan</span><strong>{activePlan ? `v${activePlan.version_number}` : "None"}</strong></div>
        <div><span>Company target</span><strong>{activePlan ? formatPercent(activePlan.target_company_margin_basis_points) : "-"}</strong></div>
        <div><span>Credits awaiting review</span><strong>{proposedCredits.length}</strong></div>
        <div><span>Markets launch-ready</span><strong>{operatingModel.launch_checklists.filter((item) => ["ready", "approved"].includes(item.status)).length}</strong></div>
      </div>

      <div className={styles.tabBar} role="tablist" aria-label="Operating model views">
        {tabs.map((tab) => (
          <button
            aria-selected={activeTab === tab.key}
            className={activeTab === tab.key ? styles.activeTab : undefined}
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {status !== "idle" ? (
        <p className={`${styles.feedback} ${styles[status]}`} role="status">{status === "saving" ? "Saving..." : message}</p>
      ) : null}

      {activeTab === "active" ? (
        <div className={styles.twoColumn}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div><span>Current authority</span><h3>Active compensation policy</h3></div>
              <strong>{activePlan ? `v${activePlan.version_number}` : "None"}</strong>
            </div>
            {activePlan ? <article className={styles.plan}>
              <div className={styles.rowHeading}><div><strong>{activePlan.name} v{activePlan.version_number}</strong><span>Approved by {activePlan.approved_by_name ?? "System owner"}</span></div><span className={styles.badge}>{labelize(activePlan.status)}</span></div>
              <div className={styles.roleGrid}>{activePlan.roles.map((role) => <div key={role.id}><span>{labelize(role.role_key)}</span><strong>{formatPercent(role.basis_points)}</strong><small>{role.cap_cents ? `${formatMoney(role.cap_cents)} cap` : "Uncapped"}</small></div>)}</div>
              <div className={styles.modeTable}>{activePlan.disposition_modes.map((mode) => <div key={mode.id}><div><strong>{mode.name}</strong><span>{labelize(mode.ai_authority_level)}</span></div><div><span>Human share</span><strong>{modeShare(mode.human_share_min_basis_points, mode.human_share_max_basis_points)}</strong></div><div><span>Company share</span><strong>{modeShare(mode.expected_company_share_min_basis_points, mode.expected_company_share_max_basis_points)}</strong></div><span className={mode.status === "available" ? styles.available : styles.locked}>{labelize(mode.status)}</span></div>)}</div>
            </article> : <p className={styles.empty}>No compensation policy is active. Activate a reviewed draft from Pending decisions.</p>}
          </section>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Policy effect</span><h3>Active guardrails</h3></div></div>
            <dl className={styles.activeFacts}>
              <div><dt>Acquisition reserve</dt><dd>{activePlan ? formatMoney(activePlan.acquisition_reserve_cents) : "Not set"}</dd></div>
              <div><dt>Company margin target</dt><dd>{activePlan ? formatPercent(activePlan.target_company_margin_basis_points) : "Not set"}</dd></div>
              <div><dt>Effective date</dt><dd>{activePlan?.effective_start_at ? new Date(activePlan.effective_start_at).toLocaleDateString() : "Not active"}</dd></div>
              <div><dt>Pending role credits</dt><dd>{proposedCredits.length}</dd></div>
              <div><dt>Markets governed</dt><dd>{operatingModel.markets.filter((market) => market.status === "active").length}</dd></div>
            </dl>
          </section>
        </div>
      ) : null}

      {activeTab === "history" ? (
        <div className={styles.twoColumn}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div><span>Policy history</span><h3>Compensation plan versions</h3></div>
              <strong>{operatingModel.compensation_plans.length}</strong>
            </div>
            <div className={styles.rows}>
              {operatingModel.compensation_plans.map((plan) => (
                <article className={styles.plan} key={plan.id}>
                  <div className={styles.rowHeading}>
                    <div><strong>{plan.name} v{plan.version_number}</strong><span>Created by {plan.created_by_name}</span></div>
                    <div className={styles.rowActions}><span className={styles.badge}>{labelize(plan.status)}</span>{plan.status === "draft" ? <button onClick={() => activatePlan(plan.id)} type="button">Activate</button> : null}</div>
                  </div>
                  <div className={styles.roleGrid}>
                    {plan.roles.map((role) => <div key={role.id}><span>{labelize(role.role_key)}</span><strong>{formatPercent(role.basis_points)}</strong><small>{role.cap_cents ? `${formatMoney(role.cap_cents)} cap` : "Uncapped"}</small></div>)}
                  </div>
                  <div className={styles.modeTable}>
                    {plan.disposition_modes.map((mode) => (
                      <div key={mode.id}>
                        <div><strong>{mode.name}</strong><span>{labelize(mode.ai_authority_level)}</span></div>
                        <div><span>Human share</span><strong>{modeShare(mode.human_share_min_basis_points, mode.human_share_max_basis_points)}</strong></div>
                        <div><span>Company share</span><strong>{modeShare(mode.expected_company_share_min_basis_points, mode.expected_company_share_max_basis_points)}</strong></div>
                        <span className={mode.status === "available" ? styles.available : styles.locked}>{labelize(mode.status)}</span>
                      </div>
                    ))}
                  </div>
                </article>
              ))}
              {!operatingModel.compensation_plans.length ? <p className={styles.empty}>No compensation policy has been recorded.</p> : null}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>New policy</span><h3>Create a draft version</h3></div></div>
            <form className={styles.planForm} onSubmit={submitPlan}>
              <label className={styles.full}><span>Plan name</span><input defaultValue="Stonegate Standard" name="name" required /></label>
              <label><span>Acquisition reserve ($)</span><input defaultValue="2500" min="0" name="acquisition_reserve" step="1" type="number" /></label>
              <label><span>Target company margin (%)</span><input defaultValue="30" min="0" name="target_margin" step="0.25" type="number" /></label>
              <label><span>Lead manager (%)</span><input defaultValue="10" min="0" name="lead_manager" step="0.25" type="number" /></label>
              <label><span>Acquisitions closer (%)</span><input defaultValue="10" min="0" name="acquisitions_closer" step="0.25" type="number" /></label>
              <label><span>CEO management (%)</span><input defaultValue="10" min="0" name="ceo_management" step="0.25" type="number" /></label>
              <label><span>Human dispositions (%)</span><input defaultValue="15" min="0" name="dispositions" step="0.25" type="number" /></label>
              <label><span>Transaction coordinator (%)</span><input defaultValue="5" min="0" name="transaction_coordinator" step="0.25" type="number" /></label>
              <label><span>TC cap ($)</span><input defaultValue="1000" min="0" name="transaction_coordinator_cap" step="1" type="number" /></label>
              <label><span>AI-managed dispositions (%)</span><input defaultValue="10" min="0" name="ai_managed" step="0.25" type="number" /></label>
              <label><span>AI oversight minimum (%)</span><input defaultValue="5" min="0" name="ai_oversight_min" step="0.25" type="number" /></label>
              <label><span>AI oversight maximum (%)</span><input defaultValue="7.5" min="0" name="ai_oversight_max" step="0.25" type="number" /></label>
              <label className={styles.full}><span>Policy notes</span><textarea name="notes" placeholder="Reason for this version and any exceptions" rows={3} /></label>
              <button type="submit">Create draft version</button>
            </form>
          </section>
        </div>
      ) : null}

      {activeTab === "credits" ? (
        <div className={styles.twoColumn}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Contribution decisions</span><h3>Role credits awaiting approval</h3></div><strong>{proposedCredits.length}</strong></div>
            <div className={styles.rows}>
              {proposedCredits.map((credit) => (
                <div className={styles.creditRow} key={credit.id}>
                  <div><Link href={`/leads/${credit.lead_id}`}>{credit.seller_name}</Link><span>{labelize(credit.role_key)} · {credit.user_name} · {formatPercent(credit.credit_basis_points)}</span></div>
                  <div className={styles.rowActions}><span className={styles.badge}>{labelize(credit.status)}</span>{credit.status === "proposed" ? <><button className={styles.secondary} onClick={() => decideCredit(credit.id, "reject")} type="button">Reject</button><button onClick={() => decideCredit(credit.id, "approve")} type="button">Approve</button></> : null}</div>
                </div>
              ))}
              {!proposedCredits.length ? <p className={styles.empty}>No role-credit decisions are pending.</p> : null}
            </div>
          </section>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Before compensation</span><h3>Propose a role credit</h3></div></div>
            {activePlan ? (
              <form className={styles.stackForm} onSubmit={submitCredit}>
                <p className={styles.formContext}>Using {activePlan.name} v{activePlan.version_number}. Approval records who earned each role without changing lead ownership.</p>
                <label><span>Lead</span><select name="lead_id" required><option value="">Select lead</option>{leads.map((lead) => <option key={lead.id} value={lead.id}>{lead.seller_name} · {lead.property_address}</option>)}</select></label>
                <label><span>Team member</span><select name="user_id" required><option value="">Select person</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label>
                <label><span>Role</span><select name="role_key" required>{activePlan.roles.map((role) => <option key={role.id} value={role.role_key}>{labelize(role.role_key)}</option>)}</select></label>
                <label><span>Credit share (%)</span><input defaultValue="100" max="100" min="0.01" name="credit_share" step="0.01" type="number" /></label>
                <label className={styles.full}><span>Contribution evidence</span><textarea name="notes" placeholder="What this person did and when" required rows={4} /></label>
                <button type="submit">Submit for approval</button>
              </form>
            ) : <p className={styles.empty}>Activate a compensation plan before assigning credits.</p>}
          </section>
        </div>
      ) : null}

      {activeTab === "launches" ? (
        <div className={styles.launchLayout}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Market controls</span><h3>Launch records</h3></div></div>
            <div className={styles.checklistPicker}>
              {operatingModel.launch_checklists.map((checklist) => (
                <button className={selectedChecklistId === checklist.id ? styles.selectedChecklist : undefined} key={checklist.id} onClick={() => setSelectedChecklistId(checklist.id)} type="button"><strong>{checklist.market_name} v{checklist.version_number}</strong><span>{checklist.completed_items}/{checklist.total_items} · {labelize(checklist.status)}</span></button>
              ))}
              {!operatingModel.launch_checklists.length ? <p className={styles.empty}>No launch checklist exists yet.</p> : null}
            </div>
            <form className={styles.stackForm} onSubmit={submitChecklist}>
              <label><span>Market</span><select name="market_id" required><option value="">Select market</option>{operatingModel.markets.map((market) => <option key={market.id} value={market.id}>{market.name}, {market.state_code}</option>)}</select></label>
              <label><span>Accountable owner</span><select name="owner_user_id" required><option value="">Select owner</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label>
              <label className={styles.full}><span>Launch notes</span><textarea name="notes" rows={3} /></label>
              <button type="submit">Create launch checklist</button>
            </form>
          </section>

          <section className={styles.section}>
            {selectedChecklist ? (
              <>
                <div className={styles.sectionHeader}>
                  <div><span>{selectedChecklist.owner_name} accountable</span><h3>{selectedChecklist.market_name} launch evidence</h3></div>
                  {selectedChecklist.status === "ready" ? <button onClick={() => approveChecklist(selectedChecklist.id)} type="button">Approve launch</button> : <strong>{selectedChecklist.completed_items}/{selectedChecklist.total_items}</strong>}
                </div>
                <div className={styles.checklistItems}>
                  {selectedChecklist.items.map((item) => (
                    <form className={styles.checklistItem} key={item.id} onSubmit={(event) => updateChecklistItem(event, item.id)}>
                      <div><span>{labelize(item.category)}</span><strong>{item.label}</strong></div>
                      <select defaultValue={item.status} disabled={selectedChecklist.status === "approved"} name="status"><option value="pending">Pending</option><option value="in_progress">In progress</option><option value="blocked">Blocked</option><option value="complete">Complete</option></select>
                      <select defaultValue={item.responsible_user_id ?? ""} disabled={selectedChecklist.status === "approved"} name="responsible_user_id"><option value="">Unassigned</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select>
                      <input defaultValue={item.evidence_notes ?? ""} disabled={selectedChecklist.status === "approved"} name="evidence_notes" placeholder="Evidence, reference, or decision notes" />
                      {selectedChecklist.status !== "approved" ? <button type="submit">Save</button> : <span className={styles.approvedBy}>Approved</span>}
                    </form>
                  ))}
                </div>
              </>
            ) : <p className={styles.empty}>Select or create a market launch checklist.</p>}
          </section>
        </div>
      ) : null}
    </section>
  );
}
