"use client";

import { useAuth } from "@clerk/nextjs";
import { Check, Clock3, ExternalLink, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { LeadManagerCase, LeadManagerOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./lead-manager.module.css";

type View = "today" | "qualification" | "performance" | "standards";

const standardQuestions = [
  ["ownership", "Ownership", "Please confirm who owns the property and how title is held.", true],
  ["decision_makers", "Decision makers", "Who must agree before the property can be sold?", true],
  ["motivation", "Reason for selling", "What has you considering a sale now?", true],
  ["timeline", "Timeline", "When would you ideally like to have this completed?", true],
  ["property_condition", "Property condition", "What repairs or updates does the property need?", true],
  ["occupancy", "Occupancy", "Who currently occupies the property?", true],
  ["asking_price", "Price expectation", "Do you have a price in mind?", false],
  ["mortgage_balance", "Mortgage or liens", "Is there a mortgage, lien, or other balance?", false],
  ["access", "Property access", "How and when can the property be viewed?", true],
] as const;

function formatDateTime(value: string | null) {
  if (!value) return "Not scheduled";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function percent(basisPoints: number) {
  return `${(basisPoints / 100).toFixed(0)}%`;
}

function CaseRow({ item, action }: { item: LeadManagerCase; action?: React.ReactNode }) {
  return (
    <article className={styles.caseRow}>
      <div className={styles.caseIdentity}>
        <strong>{item.seller_name}</strong>
        <span>{item.property_address}</span>
      </div>
      <div className={styles.caseMeta}>
        <span>{labelize(item.source)}</span>
        <span>{item.assigned_user_name}</span>
        <span className={item.is_acceptance_overdue || item.is_next_action_overdue ? styles.late : ""}>
          {item.accepted_at
            ? item.next_action_due_at
              ? `Next ${formatDateTime(item.next_action_due_at)}`
              : `${item.age_hours}h old`
            : `Accept by ${formatDateTime(item.acceptance_due_at)}`}
        </span>
      </div>
      <div className={styles.rowActions}>
        {action}
        <Link aria-label={`Open ${item.seller_name}`} href={item.lead_url} title="Open lead">
          <ExternalLink size={16} />
        </Link>
      </div>
    </article>
  );
}

export function LeadManagerWorkspace({ data }: { data: LeadManagerOverview }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [view, setView] = useState<View>("today");
  const [selectedCaseId, setSelectedCaseId] = useState(data.qualification_queue[0]?.id ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const selectedCase = data.qualification_queue.find((item) => item.id === selectedCaseId) ?? null;

  async function request(path: string, body?: object) {
    setSaving(true);
    setMessage("");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method: "POST",
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "The operation could not be completed.");
      }
      setMessage("Saved.");
      router.refresh();
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The operation could not be completed.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function acceptCase(caseId: string) {
    await request(`/api/v1/lead-manager/cases/${caseId}/accept`, {});
  }

  async function submitQualification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCase || !data.active_script) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    const answers = Object.fromEntries(
      data.active_script.questions
        .map((question) => [question.key, String(formData.get(question.key) ?? "").trim()])
        .filter(([, answer]) => Boolean(answer)),
    );
    const nextActionDue = String(formData.get("next_action_due_at") ?? "");
    const saved = await request(
      `/api/v1/lead-manager/cases/${selectedCase.id}/qualification`,
      {
        answers,
        next_action_type: String(formData.get("next_action_type") ?? "call"),
        next_action_due_at: nextActionDue ? new Date(nextActionDue).toISOString() : null,
      },
    );
    if (saved) form.reset();
  }

  async function createScript(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const saved = await request("/api/v1/lead-manager/scripts", {
      title: String(formData.get("title") ?? "").trim(),
      introduction: String(formData.get("introduction") ?? "").trim(),
      questions: standardQuestions.map(([key, label, prompt, required]) => ({
        key,
        label,
        prompt,
        answer_type: "text",
        choices: [],
        required,
      })),
    });
    if (saved) form.reset();
  }

  return (
    <div className={styles.workspace}>
      <section className={styles.metrics} aria-label="Lead Manager queue summary">
        <div><span>Awaiting acceptance</span><strong>{data.metrics.awaiting_acceptance}</strong></div>
        <div className={data.metrics.overdue_acceptance ? styles.riskMetric : ""}><span>Overdue SLA</span><strong>{data.metrics.overdue_acceptance}</strong></div>
        <div><span>Qualification due</span><strong>{data.metrics.qualification_due}</strong></div>
        <div><span>Follow-ups due</span><strong>{data.metrics.follow_up_due}</strong></div>
        <div><span>Appointments today</span><strong>{data.metrics.appointments_today}</strong></div>
        <div className={data.metrics.neglected_leads ? styles.riskMetric : ""}><span>Neglected</span><strong>{data.metrics.neglected_leads}</strong></div>
      </section>

      <nav className={styles.tabs} aria-label="Lead Manager views">
        {([
          ["today", "Daily queue"],
          ["qualification", "Qualification"],
          ["performance", "Performance"],
          ...(data.can_manage ? [["standards", "Standards"]] : []),
        ] as Array<[View, string]>).map(([key, label]) => (
          <button className={view === key ? styles.activeTab : ""} key={key} onClick={() => setView(key)} type="button">{label}</button>
        ))}
      </nav>

      {message ? <p className={message === "Saved." ? styles.notice : styles.error}>{message}</p> : null}

      {view === "today" ? (
        <div className={styles.queueGrid}>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeader}><div><span>First priority</span><h3>Accept warm handoffs</h3></div><Clock3 size={19} /></div>
            {data.awaiting_acceptance.length ? data.awaiting_acceptance.map((item) => (
              <CaseRow action={<button disabled={saving} onClick={() => acceptCase(item.id)} type="button"><Check size={15} />Accept</button>} item={item} key={item.id} />
            )) : <p className={styles.empty}>No warm handoffs are waiting.</p>}
          </section>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeader}><div><span>Due now</span><h3>Seller follow-up</h3></div><Clock3 size={19} /></div>
            {data.follow_up_queue.length ? data.follow_up_queue.map((item) => <CaseRow item={item} key={item.id} />) : <p className={styles.empty}>No follow-ups are currently overdue.</p>}
          </section>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeader}><div><span>Calendar</span><h3>Today&apos;s appointments</h3></div><Check size={19} /></div>
            {data.appointments_today.length ? data.appointments_today.map((item) => <CaseRow item={item} key={item.id} />) : <p className={styles.empty}>No seller appointments today.</p>}
          </section>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeader}><div><span>Exception queue</span><h3>Neglected leads</h3></div><ShieldAlert size={19} /></div>
            {data.neglected_queue.length ? data.neglected_queue.map((item) => <CaseRow item={item} key={item.id} />) : <p className={styles.empty}>Every active seller has a protected next action.</p>}
          </section>
        </div>
      ) : null}

      {view === "qualification" ? (
        <div className={styles.qualificationLayout}>
          <aside className={styles.qualificationList}>
            <div className={styles.sectionHeader}><div><span>Assigned queue</span><h3>Needs qualification</h3></div></div>
            {data.qualification_queue.map((item) => (
              <button className={selectedCaseId === item.id ? styles.selectedCase : ""} key={item.id} onClick={() => setSelectedCaseId(item.id)} type="button"><strong>{item.seller_name}</strong><span>{item.property_address}</span></button>
            ))}
            {!data.qualification_queue.length ? <p className={styles.empty}>Qualification queue is clear.</p> : null}
          </aside>
          <section className={styles.qualificationForm}>
            {selectedCase && data.active_script ? (
              <form onSubmit={submitQualification}>
                <div className={styles.scriptHeader}><div><span>Script v{data.active_script.version_number}</span><h3>{selectedCase.seller_name}</h3><p>{data.active_script.introduction}</p></div><Link href={selectedCase.lead_url}>Open full lead</Link></div>
                <div className={styles.questionGrid}>
                  {data.active_script.questions.map((question) => (
                    <label key={question.key}><span>{question.label}{question.required ? " *" : ""}</span><small>{question.prompt}</small><textarea name={question.key} required={question.required} rows={2} /></label>
                  ))}
                </div>
                <div className={styles.nextAction}><label><span>Next action</span><select name="next_action_type"><option value="call">Call</option><option value="sms">Text</option><option value="email">Email</option><option value="appointment">Seller appointment</option><option value="nurture">Nurture follow-up</option><option value="disqualify">Disqualify</option></select></label><label><span>Due date and time</span><input name="next_action_due_at" type="datetime-local" /></label><button disabled={saving} type="submit"><Check size={16} />Complete qualification</button></div>
              </form>
            ) : <p className={styles.empty}>{data.active_script ? "Select a seller to begin." : "A manager must approve a qualification standard before this queue can be worked."}</p>}
          </section>
        </div>
      ) : null}

      {view === "performance" ? (
        <section className={styles.performance}>
          <div className={styles.sectionHeader}><div><span>Trailing 30 days</span><h3>Lead Manager scorecard</h3></div></div>
          <div className={styles.tableWrap}><table><thead><tr><th>Manager</th><th>Accepted</th><th>Within SLA</th><th>Avg response</th><th>Qualified</th><th>Set</th><th>Held</th><th>No-show</th><th>Contracts</th><th>Follow-up quality</th></tr></thead><tbody>{data.scorecards.map((item) => <tr key={item.user_id}><td>{item.user_name}</td><td>{item.handoffs_accepted}/{item.handoffs_received}</td><td>{item.accepted_within_sla}</td><td>{item.average_acceptance_minutes === null ? "-" : `${item.average_acceptance_minutes}m`}</td><td>{item.qualifications_completed}</td><td>{item.appointments_set}</td><td>{item.appointments_held}</td><td>{item.appointment_no_shows}</td><td>{item.contracts_created}</td><td>{percent(item.follow_up_quality_basis_points)}</td></tr>)}</tbody></table></div>
        </section>
      ) : null}

      {view === "standards" && data.can_manage ? (
        <div className={styles.standardsGrid}>
          <section className={styles.standardForm}><div className={styles.sectionHeader}><div><span>Controlled process</span><h3>Create qualification version</h3></div></div><form onSubmit={createScript}><label><span>Version name</span><input defaultValue="Stonegate Seller Qualification" name="title" required /></label><label><span>Opening guidance</span><textarea defaultValue="Confirm the seller's situation carefully. Explain that these questions help Stonegate determine whether a direct sale is a reasonable fit." name="introduction" required rows={4} /></label><p>{standardQuestions.length} standardized questions will be included.</p><button disabled={saving} type="submit">Create draft</button></form></section>
          <section className={styles.versionList}><div className={styles.sectionHeader}><div><span>Version history</span><h3>Qualification standards</h3></div></div>{data.scripts.map((script) => <div className={styles.versionRow} key={script.id}><div><strong>v{script.version_number} · {script.title}</strong><span>{labelize(script.status)} · {script.questions.length} questions</span></div>{script.status === "draft" ? <button disabled={saving} onClick={() => request(`/api/v1/lead-manager/scripts/${script.id}/approve`)} type="button">Approve</button> : <span className={styles.approved}>Approved</span>}</div>)}</section>
        </div>
      ) : null}
    </div>
  );
}
