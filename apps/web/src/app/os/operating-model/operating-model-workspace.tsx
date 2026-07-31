"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { LeadListItem, OperatingModelOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./operating-model.module.css";

export type OperatingModelTab = "setup" | "active" | "history" | "credits" | "launches";
type RequestStatus = "idle" | "saving" | "saved" | "error";

const tabs: Array<{ key: OperatingModelTab; label: string }> = [
  { key: "setup", label: "Company setup" },
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
  initialTab = "setup",
  allowedTabs,
  showTabs = true,
}: {
  operatingModel: OperatingModelOverview;
  leads: LeadListItem[];
  initialTab?: OperatingModelTab;
  allowedTabs?: OperatingModelTab[];
  showTabs?: boolean;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [activeTab, setActiveTab] = useState<OperatingModelTab>(initialTab);
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

  async function installSetup() {
    await mutate("/api/v1/operating-model/setup/install", "POST", {});
  }

  async function updateSeat(event: FormEvent<HTMLFormElement>, seatId: string) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await mutate(`/api/v1/operating-model/setup/seats/${seatId}`, "PATCH", {
      status: formValue(data, "status"),
      primary_user_id: formValue(data, "primary_user_id") || null,
      backup_user_id: formValue(data, "backup_user_id") || null,
      notes: formValue(data, "notes") || null,
    });
  }

  async function submitCounterparty(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await mutate("/api/v1/operating-model/setup/counterparties", "POST", {
      market_id: formValue(data, "market_id") || null,
      counterparty_type: formValue(data, "counterparty_type"),
      name: formValue(data, "name"),
      company_name: formValue(data, "company_name") || null,
      email: formValue(data, "email") || null,
      phone: formValue(data, "phone") || null,
      notes: formValue(data, "notes") || null,
    });
    if (saved) form.reset();
  }

  async function decideCounterparty(
    counterpartyId: string,
    decision: "verify" | "deactivate",
  ) {
    const reason = window.prompt(`Document why this counterparty should be ${decision}d.`);
    if (!reason) return;
    await mutate(
      `/api/v1/operating-model/setup/counterparties/${counterpartyId}/decision`,
      "POST",
      { decision, reason },
    );
  }

  async function assignAcceptance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const roleKey = formValue(data, "role_key");
    const manualByRole: Record<string, string> = {
      acquisition_manager: "lead_manager",
      acquisition_rep: "closer",
      prospecting_caller: "va_caller",
      disposition_manager: "dispositions",
      disposition_rep: "dispositions",
      transaction_coordinator: "transaction_coordinator",
      finance_accounting: "finance",
      marketing_manager: "marketing",
      owner: "owner",
    };
    const saved = await mutate(
      "/api/v1/operating-model/setup/role-acceptances",
      "POST",
      {
        user_id: formValue(data, "user_id"),
        role_key: roleKey,
        manual_key: manualByRole[roleKey],
        manual_version: formValue(data, "manual_version"),
      },
    );
    if (saved) form.reset();
  }

  async function decideAcceptance(
    acceptanceId: string,
    decision: "approve" | "needs_changes" | "revoke",
  ) {
    const managerNotes = window.prompt("Document the manager review decision.");
    if (!managerNotes) return;
    await mutate(
      `/api/v1/operating-model/setup/role-acceptances/${acceptanceId}/decision`,
      "POST",
      { decision, manager_notes: managerNotes },
    );
  }

  return (
    <section className={styles.workspace}>
      <div className={styles.metrics}>
        <div><span>Active plan</span><strong>{activePlan ? `v${activePlan.version_number}` : "None"}</strong></div>
        <div><span>Company target</span><strong>{activePlan ? formatPercent(activePlan.target_company_margin_basis_points) : "-"}</strong></div>
        <div><span>Credits awaiting review</span><strong>{proposedCredits.length}</strong></div>
        <div><span>Company setup</span><strong>{operatingModel.company_setup.completed_check_count}/{operatingModel.company_setup.total_check_count}</strong></div>
      </div>

      {showTabs ? <div className={styles.tabBar} role="tablist" aria-label="Operating model views">
        {tabs.filter((tab) => !allowedTabs || allowedTabs.includes(tab.key)).map((tab) => (
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
      </div> : null}

      {status !== "idle" ? (
        <p className={`${styles.feedback} ${styles[status]}`} role="status">{status === "saving" ? "Saving..." : message}</p>
      ) : null}

      {activeTab === "setup" ? (
        <div className={styles.setupGrid}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div><span>Readiness</span><h3>Company configuration</h3></div>
              {!operatingModel.company_setup.seats.length ? (
                <button onClick={installSetup} type="button">Install standard setup</button>
              ) : (
                <strong>{operatingModel.company_setup.completed_check_count}/{operatingModel.company_setup.total_check_count}</strong>
              )}
            </div>
            <div className={styles.setupChecks}>
              {operatingModel.company_setup.checks.map((check) => (
                <div key={check.key}>
                  <span data-status={check.status}>{labelize(check.status)}</span>
                  <div><strong>{check.label}</strong><p>{check.detail}</p></div>
                </div>
              ))}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div><span>Accountability</span><h3>Operating seats</h3></div>
              <strong>{operatingModel.company_setup.seats.filter((seat) => seat.status === "covered").length}</strong>
            </div>
            <div className={styles.seatRows}>
              {operatingModel.company_setup.seats.map((seat) => (
                <form key={seat.id} onSubmit={(event) => updateSeat(event, seat.id)}>
                  <div><strong>{seat.label}</strong><span>{labelize(seat.role_key)}</span></div>
                  <select defaultValue={seat.status} name="status">
                    <option value="planned">Planned</option>
                    <option value="hiring">Hiring</option>
                    <option value="covered">Covered</option>
                    <option value="paused">Paused</option>
                  </select>
                  <select defaultValue={seat.primary_user_id ?? ""} name="primary_user_id">
                    <option value="">Primary owner</option>
                    {activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}
                  </select>
                  <select defaultValue={seat.backup_user_id ?? ""} name="backup_user_id">
                    <option value="">No backup</option>
                    {activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}
                  </select>
                  <input defaultValue={seat.notes ?? ""} name="notes" placeholder="Coverage notes" />
                  <button type="submit">Save</button>
                </form>
              ))}
              {!operatingModel.company_setup.seats.length ? <p className={styles.empty}>Install the standard setup to create Stonegate&apos;s operating seats.</p> : null}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div><span>External partners</span><h3>Verified counterparties</h3></div>
              <strong>{operatingModel.company_setup.counterparties.filter((item) => item.status === "verified").length}</strong>
            </div>
            <div className={styles.rows}>
              {operatingModel.company_setup.counterparties.map((item) => (
                <div className={styles.creditRow} key={item.id}>
                  <div><strong>{item.name}</strong><span>{labelize(item.counterparty_type)} · {item.company_name ?? item.market_name ?? "Company-wide"}</span></div>
                  <div className={styles.rowActions}>
                    <span className={styles.badge}>{labelize(item.status)}</span>
                    {item.status !== "verified" ? <button onClick={() => decideCounterparty(item.id, "verify")} type="button">Verify</button> : null}
                    {item.status !== "inactive" ? <button className={styles.secondary} onClick={() => decideCounterparty(item.id, "deactivate")} type="button">Deactivate</button> : null}
                  </div>
                </div>
              ))}
            </div>
            <form className={styles.planForm} onSubmit={submitCounterparty}>
              <label><span>Type</span><select name="counterparty_type" required><option value="closing_attorney">Closing attorney</option><option value="title_company">Title company</option><option value="funding_partner">Funding partner</option><option value="inspector">Inspector</option><option value="other">Other</option></select></label>
              <label><span>Market</span><select name="market_id"><option value="">Company-wide</option>{operatingModel.markets.map((market) => <option key={market.id} value={market.id}>{market.name}, {market.state_code}</option>)}</select></label>
              <label><span>Contact name</span><input name="name" required /></label>
              <label><span>Company</span><input name="company_name" /></label>
              <label><span>Email</span><input name="email" type="email" /></label>
              <label><span>Phone</span><input name="phone" type="tel" /></label>
              <label className={styles.full}><span>Verification notes</span><textarea name="notes" rows={2} /></label>
              <button type="submit">Add for verification</button>
            </form>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <div><span>Role readiness</span><h3>Manual and workspace acceptance</h3></div>
              <strong>{operatingModel.company_setup.role_acceptances.filter((item) => item.status === "approved").length}</strong>
            </div>
            <div className={styles.rows}>
              {operatingModel.company_setup.role_acceptances.map((item) => (
                <div className={styles.acceptanceRow} key={item.id}>
                  <div><strong>{item.user_name}</strong><span>{labelize(item.role_key)} · {labelize(item.manual_key)} v{item.manual_version}</span>{item.workspace_test_evidence ? <p>{item.workspace_test_evidence}</p> : null}</div>
                  <div className={styles.rowActions}>
                    <span className={styles.badge}>{labelize(item.status)}</span>
                    {item.status === "submitted" ? <><button className={styles.secondary} onClick={() => decideAcceptance(item.id, "needs_changes")} type="button">Return</button><button onClick={() => decideAcceptance(item.id, "approve")} type="button">Approve</button></> : null}
                    {item.status === "approved" ? <button className={styles.secondary} onClick={() => decideAcceptance(item.id, "revoke")} type="button">Revoke</button> : null}
                  </div>
                </div>
              ))}
            </div>
            <form className={styles.planForm} onSubmit={assignAcceptance}>
              <label><span>Team member</span><select name="user_id" required><option value="">Select person</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label>
              <label><span>Assigned role</span><select name="role_key" required><option value="acquisition_manager">Lead manager</option><option value="acquisition_rep">Acquisitions closer</option><option value="prospecting_caller">VA caller</option><option value="disposition_manager">Disposition manager</option><option value="disposition_rep">Disposition representative</option><option value="transaction_coordinator">Transaction coordinator</option><option value="finance_accounting">Finance and accounting</option><option value="marketing_manager">Marketing manager</option><option value="owner">Owner</option></select></label>
              <label><span>Manual version</span><input defaultValue="2026.07" name="manual_version" required /></label>
              <button type="submit">Assign role setup</button>
            </form>
          </section>
        </div>
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
              <label><span>Human dispositions (%)</span><input defaultValue="20" min="0" name="dispositions" step="0.25" type="number" /></label>
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
