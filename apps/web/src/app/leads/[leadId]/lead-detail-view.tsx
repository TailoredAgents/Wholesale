import Link from "next/link";

import { CompleteTaskButton } from "../../complete-task-button";
import { getLeadDetail } from "../../lib/api";
import { AppointmentForm } from "./appointment-form";
import { CommunicationLogForm } from "./communication-log-form";
import { LeadActionForm } from "./lead-action-form";
import { LeadEditForm } from "./lead-edit-form";
import { StageUpdateForm } from "./stage-update-form";
import { TransactionForm } from "./transaction-form";
import { UnderwritingForm } from "./underwriting-form";
import styles from "./page.module.css";

type LeadPageProps = {
  params: Promise<{ leadId: string }>;
};

function labelize(value: string | null) {
  if (!value) {
    return "None";
  }
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatOptionalDate(value: string | null) {
  return value ? formatDate(value) : "Not scheduled";
}

function formatMoney(cents: number | null) {
  if (cents === null) {
    return "Unknown";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

export async function LeadDetailView({ params }: LeadPageProps) {
  const { leadId } = await params;
  const { lead, apiConnected } = await getLeadDetail(leadId);

  if (!lead) {
    return (
      <main className={styles.page}>
        <Link className={styles.backLink} href="/os">
          Back to dashboard
        </Link>
        <section className={styles.empty}>
          <p>{apiConnected ? "Lead not found." : "API unavailable."}</p>
        </section>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <Link className={styles.backLink} href="/os">
        Back to dashboard
      </Link>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Seller lead</p>
          <h1>{lead.seller_name}</h1>
          <p>{lead.property_address}</p>
        </div>
        <div className={styles.statusBox}>
          <span>Current stage</span>
          <strong>{labelize(lead.stage_key)}</strong>
          <small>Next follow-up: {formatOptionalDate(lead.next_follow_up_at)}</small>
        </div>
      </header>

      <section className={styles.grid}>
        <article className={styles.panelWide}>
          <div className={styles.panelHeader}>
            <h2>Acquisition Snapshot</h2>
          </div>
          <dl className={styles.snapshot}>
            <div>
              <dt>Motivation</dt>
              <dd>{lead.motivation ?? "Unknown"}</dd>
            </div>
            <div>
              <dt>Timeline</dt>
              <dd>{lead.desired_timeline ?? "Unknown"}</dd>
            </div>
            <div>
              <dt>Condition</dt>
              <dd>{labelize(lead.property_condition)}</dd>
            </div>
            <div>
              <dt>Occupancy</dt>
              <dd>{labelize(lead.occupancy_status)}</dd>
            </div>
            <div>
              <dt>Asking price</dt>
              <dd>{lead.asking_price ?? "Unknown"}</dd>
            </div>
            <div>
              <dt>Mortgage balance</dt>
              <dd>{lead.mortgage_balance ?? "Unknown"}</dd>
            </div>
            <div>
              <dt>Appointment</dt>
              <dd>{labelize(lead.appointment_status)}</dd>
            </div>
            <div>
              <dt>Next follow-up</dt>
              <dd>{formatOptionalDate(lead.next_follow_up_at)}</dd>
            </div>
          </dl>
        </article>

        <article className={styles.panelWide}>
          <div className={styles.panelHeader}>
            <h2>AI-Ready Lead Intelligence</h2>
          </div>
          <div className={styles.intelligenceGrid}>
            <div className={styles.scoreCard}>
              <span>Lead quality</span>
              <strong>{lead.intelligence.quality_score}</strong>
              <small>Qualification completeness</small>
            </div>
            <div className={styles.scoreCard}>
              <span>Urgency</span>
              <strong>{lead.intelligence.urgency_score}</strong>
              <small>{labelize(lead.intelligence.priority_label)} priority</small>
            </div>
            <div className={styles.actionCallout}>
              <span>Next best action</span>
              <strong>{lead.intelligence.next_best_action.label}</strong>
              <p>{lead.intelligence.next_best_action.description}</p>
            </div>
          </div>
          <div className={styles.intelligenceColumns}>
            <section>
              <h3>Missing Questions</h3>
              <div className={styles.missingList}>
                {lead.intelligence.missing_fields.length === 0 ? (
                  <p>No required qualification gaps.</p>
                ) : null}
                {lead.intelligence.missing_fields.slice(0, 6).map((field) => (
                  <p key={field.field_key}>
                    <strong>{field.label}</strong>
                    <span>{field.question}</span>
                  </p>
                ))}
              </div>
            </section>
            <section>
              <h3>Agent Summary</h3>
              <div className={styles.summaryBlock}>
                <p>{lead.intelligence.ai_ready_summary.situation}</p>
                <strong>{lead.intelligence.ai_ready_summary.urgency}</strong>
                <ul>
                  {lead.intelligence.ai_ready_summary.known_facts.slice(0, 6).map((fact) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
              </div>
            </section>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Lead Controls</h2>
          </div>
          <LeadEditForm lead={lead} />
          <div className={styles.formDivider} />
          <StageUpdateForm leadId={lead.id} currentStage={lead.stage_key} />
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Notes And Follow-Up</h2>
          </div>
          <LeadActionForm leadId={lead.id} />
        </article>

        <article className={styles.panelWide}>
          <div className={styles.panelHeader}>
            <h2>Open Tasks</h2>
          </div>
          <div className={styles.taskList}>
            {lead.open_tasks.length === 0 ? <p>No open tasks for this lead.</p> : null}
            {lead.open_tasks.map((task) => (
              <div key={task.id} className={styles.taskItem}>
                <div>
                  <strong>{task.title}</strong>
                  <span>
                    {labelize(task.task_type)} / {labelize(task.priority)} /{" "}
                    {task.due_at ? formatDate(task.due_at) : "No due date"}
                  </span>
                </div>
                <CompleteTaskButton taskId={task.id} />
              </div>
            ))}
          </div>
        </article>

        <article className={styles.panelWide}>
          <div className={styles.panelHeader}>
            <h2>Appointments</h2>
          </div>
          <div className={styles.appointmentGrid}>
            <AppointmentForm leadId={lead.id} />
            <div className={styles.appointmentList}>
              {lead.appointments.length === 0 ? <p>No appointments scheduled yet.</p> : null}
              {lead.appointments.map((appointment) => (
                <article key={appointment.id}>
                  <div>
                    <strong>{labelize(appointment.appointment_type)}</strong>
                    <span>{labelize(appointment.status)}</span>
                  </div>
                  <p>
                    {formatDate(appointment.scheduled_start_at)}
                    {appointment.scheduled_end_at
                      ? ` to ${formatDate(appointment.scheduled_end_at)}`
                      : ""}
                  </p>
                  <small>
                    {labelize(appointment.location_type)}
                    {appointment.location ? ` / ${appointment.location}` : ""}
                  </small>
                  {appointment.notes ? <p>{appointment.notes}</p> : null}
                </article>
              ))}
            </div>
          </div>
        </article>

        <article className={styles.panelWide}>
          <div className={styles.panelHeader}>
            <h2>Underwriting</h2>
          </div>
          <div className={styles.underwritingGrid}>
            <UnderwritingForm leadId={lead.id} />
            <div className={styles.underwritingList}>
              {lead.underwriting_versions.length === 0 ? (
                <p>No underwriting versions saved yet.</p>
              ) : null}
              {lead.underwriting_versions.map((version) => (
                <article key={version.id}>
                  <div>
                    <strong>Version {version.version_number}</strong>
                    <span>{labelize(version.status)}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>ARV</dt>
                      <dd>
                        {formatMoney(version.arv_low_cents)} to{" "}
                        {formatMoney(version.arv_high_cents)}
                      </dd>
                    </div>
                    <div>
                      <dt>Repairs</dt>
                      <dd>
                        {formatMoney(version.repair_low_cents)} to{" "}
                        {formatMoney(version.repair_high_cents)}
                      </dd>
                    </div>
                    <div>
                      <dt>MAO</dt>
                      <dd>{formatMoney(version.max_offer_cents)}</dd>
                    </div>
                    <div>
                      <dt>Recommended</dt>
                      <dd>{formatMoney(version.recommended_offer_cents)}</dd>
                    </div>
                  </dl>
                  <small>{labelize(version.offer_strategy)} / Manual</small>
                  {version.notes ? <p>{version.notes}</p> : null}
                </article>
              ))}
            </div>
          </div>
        </article>

        <article className={styles.panelWide}>
          <div className={styles.panelHeader}>
            <h2>Contract And Transaction</h2>
          </div>
          <div className={styles.transactionGrid}>
            <TransactionForm leadId={lead.id} />
            <div className={styles.transactionList}>
              {lead.transactions.length === 0 ? <p>No transaction opened yet.</p> : null}
              {lead.transactions.map((transaction) => (
                <article key={transaction.id}>
                  <div>
                    <strong>{labelize(transaction.contract_type)}</strong>
                    <span>{labelize(transaction.status)}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>Purchase</dt>
                      <dd>{formatMoney(transaction.purchase_price_cents)}</dd>
                    </div>
                    <div>
                      <dt>Assignment fee</dt>
                      <dd>{formatMoney(transaction.assignment_fee_cents)}</dd>
                    </div>
                    <div>
                      <dt>Earnest money</dt>
                      <dd>{formatMoney(transaction.earnest_money_cents)}</dd>
                    </div>
                    <div>
                      <dt>Closing</dt>
                      <dd>{formatOptionalDate(transaction.closing_date)}</dd>
                    </div>
                  </dl>
                  <small>{transaction.title_company ?? "No title company recorded"}</small>
                  {transaction.notes ? <p>{transaction.notes}</p> : null}
                  <div className={styles.checklist}>
                    {transaction.checklist_items.map((item) => (
                      <p key={item.id}>
                        <strong>{item.title}</strong>
                        <span>{labelize(item.status)}</span>
                      </p>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </div>
        </article>

        <article className={styles.panelWide}>
          <div className={styles.panelHeader}>
            <h2>Communications</h2>
          </div>
          <div className={styles.communicationGrid}>
            <CommunicationLogForm leadId={lead.id} />
            <div className={styles.communicationList}>
              {lead.communications.length === 0 ? <p>No communications logged yet.</p> : null}
              {lead.communications.map((communication) => (
                <article key={communication.id}>
                  <div>
                    <strong>
                      {labelize(communication.direction)} {labelize(communication.channel)}
                    </strong>
                    <span>
                      {labelize(communication.status)} via {labelize(communication.provider)}
                    </span>
                  </div>
                  {communication.subject ? <h3>{communication.subject}</h3> : null}
                  <p>{communication.body}</p>
                  <small>{formatDate(communication.occurred_at)}</small>
                </article>
              ))}
            </div>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Contact</h2>
          </div>
          <dl className={styles.details}>
            <div>
              <dt>Source</dt>
              <dd>{labelize(lead.source)}</dd>
            </div>
            <div>
              <dt>Temperature</dt>
              <dd>{labelize(lead.lead_temperature)}</dd>
            </div>
            <div>
              <dt>Assigned</dt>
              <dd>{lead.assigned_user_email ?? "Unassigned"}</dd>
            </div>
          </dl>
          <div className={styles.list}>
            {lead.contact_methods.length === 0 ? <p>No contact methods recorded.</p> : null}
            {lead.contact_methods.map((method) => (
              <p key={`${method.method_type}-${method.value}`}>
                <strong>{labelize(method.method_type)}</strong>
                <span>{method.value}</span>
              </p>
            ))}
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Consent Evidence</h2>
          </div>
          <div className={styles.list}>
            {lead.consent_records.length === 0 ? <p>No consent records found.</p> : null}
            {lead.consent_records.map((record) => (
              <p key={`${record.wording_version}-${record.created_at}`}>
                <strong>{labelize(record.status)} consent</strong>
                <span>
                  {labelize(record.channel)} via {labelize(record.source)} on{" "}
                  {formatDate(record.created_at)}
                </span>
              </p>
            ))}
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h2>Attribution</h2>
          </div>
          <div className={styles.list}>
            {lead.attribution_touches.length === 0 ? <p>No attribution touches found.</p> : null}
            {lead.attribution_touches.map((touch) => (
              <p key={`${touch.touch_type}-${touch.created_at}`}>
                <strong>{labelize(touch.touch_type)}</strong>
                <span>
                  {touch.source ?? "unknown"} / {touch.medium ?? "none"}
                  {touch.campaign ? ` / ${touch.campaign}` : ""}
                </span>
              </p>
            ))}
          </div>
        </article>

        <article className={styles.panelWide}>
          <div className={styles.panelHeader}>
            <h2>Recent Activity</h2>
          </div>
          <div className={styles.timeline}>
            {lead.recent_activity.map((activity) => (
              <p key={`${activity.event_type}-${activity.created_at}`}>
                <strong>{labelize(activity.event_type)}</strong>
                <span>{activity.summary}</span>
                <small>{formatDate(activity.created_at)}</small>
              </p>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
