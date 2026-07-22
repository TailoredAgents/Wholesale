import Link from "next/link";

import { CompleteTaskButton } from "../../complete-task-button";
import { getBuyers, getLeadDetail, type LeadDetail } from "../../lib/api";
import { LeadLifecycleActions } from "../../os/leads/lead-lifecycle-actions";
import { AppointmentForm } from "./appointment-form";
import { AppointmentOutcomeForm } from "./appointment-outcome-form";
import { BuyerOfferForm } from "./buyer-offer-form";
import { CommunicationLogForm } from "./communication-log-form";
import { LeadActionForm } from "./lead-action-form";
import { LeadEditForm } from "./lead-edit-form";
import { MarketValuePreview } from "./market-value-preview";
import { NegotiationGovernance } from "./negotiation-governance";
import { OfferApprovalControl } from "./offer-approval-control";
import { PropertyValidationControl } from "./property-validation-control";
import { StageUpdateForm } from "./stage-update-form";
import { TransactionForm } from "./transaction-form";
import { UnderwritingForm } from "./underwriting-form";
import { UnderwritingVersionComparison } from "./underwriting-version-comparison";
import styles from "./page.module.css";

const tabs = [
  ["overview", "Overview"],
  ["communications", "Communications"],
  ["underwriting", "Underwriting"],
  ["deal", "Deal"],
  ["history", "History"],
] as const;

type LeadTab = (typeof tabs)[number][0];

type LeadPageProps = {
  params: Promise<{ leadId: string }>;
  searchParams?: Promise<{ tab?: string | string[] }>;
};

function labelize(value: string | null) {
  if (!value) return "Unknown";
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
  if (cents === null) return "Unknown";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function countLabel(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function normalizeTab(value: string | string[] | undefined): LeadTab {
  const candidate = Array.isArray(value) ? value[0] : value;
  return tabs.some(([key]) => key === candidate) ? (candidate as LeadTab) : "overview";
}

function uniqueBy<T>(items: T[], keyFor: (item: T) => string) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = keyFor(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function ActionDisclosure({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <details className={styles.actionDisclosure}>
      <summary>{label}</summary>
      <div className={styles.disclosureBody}>{children}</div>
    </details>
  );
}

function SectionHeader({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className={styles.sectionHeader}>
      <h2>{title}</h2>
      {meta ? <span>{meta}</span> : null}
    </div>
  );
}

function ContactPanel({ lead }: { lead: LeadDetail }) {
  const methods = uniqueBy(
    lead.contact_methods,
    (method) => `${method.method_type}:${method.value.toLowerCase()}`,
  );
  return (
    <section className={styles.sectionPanel} id="contact">
      <SectionHeader title="Seller contact" />
      <div className={styles.contactList}>
        {methods.length === 0 ? <p className={styles.emptyState}>No contact method recorded.</p> : null}
        {methods.map((method) => (
          <div key={`${method.method_type}-${method.value}`}>
            <span>{labelize(method.method_type)}</span>
            <strong>{method.value}</strong>
            {method.is_primary ? <small>Primary</small> : null}
          </div>
        ))}
      </div>
      <dl className={styles.compactFacts}>
        <div><dt>Owner</dt><dd>{lead.assigned_user_email ?? "Unassigned"}</dd></div>
        <div><dt>Source</dt><dd>{labelize(lead.source)}</dd></div>
        <div><dt>Temperature</dt><dd>{labelize(lead.lead_temperature)}</dd></div>
      </dl>
    </section>
  );
}

function PropertyPanel({ lead }: { lead: LeadDetail }) {
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader title="Property and seller situation" />
      <PropertyValidationControl
        initialValidation={lead.property_validation}
        leadId={lead.id}
      />
      <dl className={styles.factGrid}>
        <div><dt>Motivation</dt><dd>{lead.motivation ?? "Unknown"}</dd></div>
        <div><dt>Timeline</dt><dd>{labelize(lead.desired_timeline)}</dd></div>
        <div><dt>Condition</dt><dd>{labelize(lead.property_condition)}</dd></div>
        <div><dt>Occupancy</dt><dd>{labelize(lead.occupancy_status)}</dd></div>
        <div><dt>Asking price</dt><dd>{lead.asking_price ?? "Unknown"}</dd></div>
        <div><dt>Mortgage</dt><dd>{lead.mortgage_balance ?? "Unknown"}</dd></div>
        <div><dt>Property type</dt><dd>{labelize(lead.property_type)}</dd></div>
        <div><dt>County</dt><dd>{lead.property_county ?? "Unknown"}</dd></div>
      </dl>
    </section>
  );
}

function TasksPanel({ lead }: { lead: LeadDetail }) {
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader title="Open tasks" meta={`${lead.open_tasks.length} open`} />
      <div className={styles.taskList}>
        {lead.open_tasks.length === 0 ? (
          <p className={styles.emptyState}>No open tasks. Create the next dated action.</p>
        ) : null}
        {lead.open_tasks.map((task) => (
          <div key={task.id} className={styles.taskItem}>
            <div>
              <strong>{task.title}</strong>
              <span>{labelize(task.priority)} / {formatOptionalDate(task.due_at)}</span>
            </div>
            <CompleteTaskButton taskId={task.id} />
          </div>
        ))}
      </div>
      <ActionDisclosure label="Add note or follow-up task">
        <LeadActionForm leadId={lead.id} />
      </ActionDisclosure>
    </section>
  );
}

function QualificationPanel({ lead }: { lead: LeadDetail }) {
  const missing = lead.intelligence.missing_fields.slice(0, 6);
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader title="Qualification" meta={`${lead.intelligence.quality_score}% complete`} />
      <div className={styles.qualificationSummary}>
        <div>
          <span>Urgency</span>
          <strong>{lead.intelligence.urgency_score}</strong>
          <small>{labelize(lead.intelligence.priority_label)} priority</small>
        </div>
        <p>{lead.intelligence.ai_ready_summary.situation}</p>
      </div>
      <div className={styles.questionList}>
        {missing.length === 0 ? <p className={styles.emptyState}>Qualification is complete.</p> : null}
        {missing.map((field) => (
          <div key={field.field_key}>
            <strong>{field.label}</strong>
            <span>{field.question}</span>
          </div>
        ))}
      </div>
      <ActionDisclosure label="Answer qualification questions">
        <LeadEditForm lead={lead} />
      </ActionDisclosure>
    </section>
  );
}

function RecentActivityPanel({ lead, limit = 6 }: { lead: LeadDetail; limit?: number }) {
  const activity = uniqueBy(
    lead.recent_activity,
    (item) => `${item.event_type}:${item.summary}`,
  ).slice(0, limit);
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader title="Recent activity" />
      <div className={styles.activityTimeline}>
        {activity.length === 0 ? <p className={styles.emptyState}>No activity recorded.</p> : null}
        {activity.map((item) => (
          <div key={`${item.event_type}-${item.created_at}`}>
            <span className={styles.timelineMarker} aria-hidden="true" />
            <div>
              <strong>{labelize(item.event_type)}</strong>
              <p>{item.summary}</p>
              <small>{formatDate(item.created_at)}</small>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function OverviewTab({ lead }: { lead: LeadDetail }) {
  return (
    <div className={styles.overviewGrid}>
      <div className={styles.mainColumn}>
        <TasksPanel lead={lead} />
        <QualificationPanel lead={lead} />
        <RecentActivityPanel lead={lead} />
      </div>
      <aside className={styles.sideColumn}>
        <ContactPanel lead={lead} />
        <PropertyPanel lead={lead} />
        <section className={styles.sectionPanel}>
          <SectionHeader title="Record controls" />
          <dl className={styles.compactFacts}>
            <div><dt>Stage</dt><dd>{labelize(lead.stage_key)}</dd></div>
            <div><dt>Next follow-up</dt><dd>{formatOptionalDate(lead.next_follow_up_at)}</dd></div>
            <div><dt>Appointment</dt><dd>{labelize(lead.appointment_status)}</dd></div>
          </dl>
          <ActionDisclosure label="Change pipeline stage">
            <StageUpdateForm currentStage={lead.stage_key} leadId={lead.id} />
          </ActionDisclosure>
        </section>
      </aside>
    </div>
  );
}

function CommunicationsTab({ lead }: { lead: LeadDetail }) {
  const timeline = [
    ...lead.communications.map((item) => ({
      id: `communication-${item.id}`,
      occurredAt: item.occurred_at,
      title: `${labelize(item.direction)} ${labelize(item.channel)}`,
      meta: `${labelize(item.status)} via ${labelize(item.provider)}`,
      body: item.body,
    })),
    ...lead.appointments.map((item) => ({
      id: `appointment-${item.id}`,
      occurredAt: item.scheduled_start_at,
      title: labelize(item.appointment_type),
      meta: `${labelize(item.status)} / ${labelize(item.location_type)}`,
      body: item.notes ?? item.location ?? "Appointment scheduled.",
    })),
  ].sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime());

  return (
    <div className={styles.tabGrid}>
      <section className={styles.sectionPanel}>
        <SectionHeader title="Seller timeline" meta={countLabel(timeline.length, "record")} />
        <div className={styles.communicationTimeline}>
          {timeline.length === 0 ? <p className={styles.emptyState}>No seller contact logged yet.</p> : null}
          {timeline.map((item) => (
            <article key={item.id}>
              <div><strong>{item.title}</strong><span>{item.meta}</span></div>
              <p>{item.body}</p>
              <small>{formatDate(item.occurredAt)}</small>
            </article>
          ))}
        </div>
      </section>
      <aside className={styles.sideColumn}>
        <ContactPanel lead={lead} />
        <section className={styles.sectionPanel}>
          <SectionHeader title="Communication actions" />
          <ActionDisclosure label="Log call, text, or email">
            <CommunicationLogForm leadId={lead.id} />
          </ActionDisclosure>
          <ActionDisclosure label="Schedule appointment">
            <AppointmentForm leadId={lead.id} />
          </ActionDisclosure>
          <ActionDisclosure label="Record appointment outcome">
            <AppointmentOutcomeForm appointments={lead.appointments} leadId={lead.id} />
          </ActionDisclosure>
          <ActionDisclosure label="Add note or task">
            <LeadActionForm leadId={lead.id} />
          </ActionDisclosure>
        </section>
      </aside>
    </div>
  );
}

function UnderwritingTab({ lead }: { lead: LeadDetail }) {
  return (
    <div className={styles.tabGrid}>
      <div className={styles.mainColumn}>
        <section className={styles.sectionPanel}>
          <SectionHeader title="Comp analysis and offer range" />
          <div className={styles.sectionBody}><MarketValuePreview leadId={lead.id} /></div>
        </section>
        <section className={styles.sectionPanel}>
          <SectionHeader title="Underwriting versions" meta={`${lead.underwriting_versions.length} saved`} />
          <UnderwritingVersionComparison versions={lead.underwriting_versions} />
          <div className={styles.recordList}>
            {lead.underwriting_versions.length === 0 ? <p className={styles.emptyState}>No underwriting version saved.</p> : null}
            {lead.underwriting_versions.map((version) => (
              <article key={version.id}>
                <div className={styles.recordTitle}><strong>Version {version.version_number}</strong><span>{labelize(version.status)}</span></div>
                <dl className={styles.moneyGrid}>
                  <div><dt>ARV</dt><dd>{formatMoney(version.arv_low_cents)} to {formatMoney(version.arv_high_cents)}</dd></div>
                  <div><dt>Repairs</dt><dd>{formatMoney(version.repair_low_cents)} to {formatMoney(version.repair_high_cents)}</dd></div>
                  <div><dt>MAO</dt><dd>{formatMoney(version.max_offer_cents)}</dd></div>
                  <div><dt>Recommended</dt><dd>{formatMoney(version.recommended_offer_cents)}</dd></div>
                </dl>
                {version.notes ? <p>{version.notes}</p> : null}
              </article>
            ))}
          </div>
          <ActionDisclosure label="Create manual underwriting version">
            <UnderwritingForm leadId={lead.id} />
          </ActionDisclosure>
        </section>
        <section className={styles.sectionPanel} id="offer-approval">
          <SectionHeader title="Offer approval and negotiation" />
          <OfferApprovalControl
            askingPrice={lead.asking_price}
            leadId={lead.id}
            versions={lead.underwriting_versions}
          />
          <NegotiationGovernance leadId={lead.id} />
        </section>
      </div>
      <aside className={styles.sideColumn}><PropertyPanel lead={lead} /></aside>
    </div>
  );
}

function DealTab({ lead, buyers }: { lead: LeadDetail; buyers: Awaited<ReturnType<typeof getBuyers>>["buyers"] }) {
  return (
    <div className={styles.tabGrid}>
      <div className={styles.mainColumn}>
        <section className={styles.sectionPanel}>
          <SectionHeader
            title="Contracts and transactions"
            meta={countLabel(lead.transactions.length, "record")}
          />
          <div className={styles.recordList}>
            {lead.transactions.length === 0 ? <p className={styles.emptyState}>No transaction opened.</p> : null}
            {lead.transactions.map((transaction) => (
              <article key={transaction.id}>
                <div className={styles.recordTitle}><strong>{labelize(transaction.contract_type)}</strong><span>{labelize(transaction.status)}</span></div>
                <dl className={styles.moneyGrid}>
                  <div><dt>Purchase</dt><dd>{formatMoney(transaction.purchase_price_cents)}</dd></div>
                  <div><dt>Assignment fee</dt><dd>{formatMoney(transaction.assignment_fee_cents)}</dd></div>
                  <div><dt>Earnest money</dt><dd>{formatMoney(transaction.earnest_money_cents)}</dd></div>
                  <div><dt>Closing</dt><dd>{formatOptionalDate(transaction.closing_date)}</dd></div>
                </dl>
                <small>{transaction.title_company ?? "No title company recorded"}</small>
                <div className={styles.checklist}>
                  {transaction.checklist_items.map((item) => <p key={item.id}><strong>{item.title}</strong><span>{labelize(item.status)}</span></p>)}
                </div>
              </article>
            ))}
          </div>
          <ActionDisclosure label="Open transaction">
            <TransactionForm leadId={lead.id} />
          </ActionDisclosure>
        </section>
      </div>
      <aside className={styles.sideColumn}>
        <section className={styles.sectionPanel}>
          <SectionHeader title="Buyer offers" meta={`${lead.buyer_offers.length} received`} />
          <div className={styles.recordList}>
            {lead.buyer_offers.length === 0 ? <p className={styles.emptyState}>No buyer offers recorded.</p> : null}
            {lead.buyer_offers.map((offer) => (
              <article key={offer.id}>
                <div className={styles.recordTitle}><strong>{offer.buyer_name}</strong><span>{labelize(offer.status)}</span></div>
                <dl className={styles.compactFacts}>
                  <div><dt>Offer</dt><dd>{formatMoney(offer.amount_cents)}</dd></div>
                  <div><dt>Financing</dt><dd>{labelize(offer.financing_type)}</dd></div>
                  <div><dt>POF</dt><dd>{offer.proof_of_funds_received ? "Received" : "Missing"}</dd></div>
                </dl>
              </article>
            ))}
          </div>
          <ActionDisclosure label="Record buyer offer">
            <BuyerOfferForm buyers={buyers} leadId={lead.id} />
          </ActionDisclosure>
        </section>
      </aside>
    </div>
  );
}

function HistoryTab({ lead }: { lead: LeadDetail }) {
  const consents = uniqueBy(lead.consent_records, (item) => `${item.channel}:${item.status}:${item.source}:${item.wording_version}`);
  const touches = uniqueBy(lead.attribution_touches, (item) => `${item.touch_type}:${item.source}:${item.medium}:${item.campaign}`);
  return (
    <div className={styles.historyGrid}>
      <section className={styles.sectionPanel}>
        <SectionHeader
          title="Consent evidence"
          meta={countLabel(consents.length, "unique record")}
        />
        <div className={styles.recordList}>
          {consents.map((record) => (
            <article
              key={`${record.channel}-${record.status}-${record.source}-${record.wording_version}-${record.created_at}`}
            >
              <div className={styles.recordTitle}><strong>{labelize(record.status)} consent</strong><span>{labelize(record.channel)}</span></div>
              <p>{labelize(record.source)} / wording {record.wording_version}</p>
              <small>{formatDate(record.created_at)}</small>
            </article>
          ))}
        </div>
      </section>
      <section className={styles.sectionPanel}>
        <SectionHeader
          title="Attribution"
          meta={countLabel(touches.length, "unique touch", "unique touches")}
        />
        <div className={styles.recordList}>
          {touches.map((touch) => (
            <article
              key={`${touch.touch_type}-${touch.source}-${touch.medium}-${touch.campaign}-${touch.created_at}`}
            >
              <div className={styles.recordTitle}><strong>{labelize(touch.touch_type)}</strong><span>{touch.source ?? "Unknown"}</span></div>
              <p>{touch.medium ?? "No medium"}{touch.campaign ? ` / ${touch.campaign}` : ""}</p>
              <small>{formatDate(touch.created_at)}</small>
            </article>
          ))}
        </div>
      </section>
      <div className={styles.historyWide}><RecentActivityPanel lead={lead} limit={20} /></div>
    </div>
  );
}

export async function LeadDetailView({ params, searchParams }: LeadPageProps) {
  const [{ leadId }, query] = await Promise.all([params, searchParams]);
  const activeTab = normalizeTab(query?.tab);
  const [{ lead, apiConnected }, { buyers }] = await Promise.all([getLeadDetail(leadId), getBuyers()]);

  if (!lead) {
    return (
      <main className={styles.page}>
        <Link className={styles.backLink} href="/os/leads">Back to leads</Link>
        <section className={styles.empty}><p>{apiConnected ? "Lead not found." : "API unavailable."}</p></section>
      </main>
    );
  }

  const phone = lead.contact_methods.find((method) => method.method_type === "phone")?.value;
  const email = lead.contact_methods.find((method) => method.method_type === "email")?.value;
  const lastContact = lead.communications[0]?.occurred_at ?? null;
  const tabHref = (tab: LeadTab) => `/os/leads/${lead.id}?tab=${tab}`;

  return (
    <main className={styles.page}>
      <div className={styles.breadcrumb}><Link href="/os/leads">Leads</Link><span>/</span><span>{lead.seller_name}</span></div>
      <header className={styles.commandHeader}>
        <div className={styles.identity}>
          <p className={styles.eyebrow}>Seller lead</p>
          <h1>{lead.seller_name}</h1>
          <p>{lead.property_address}</p>
          <div className={styles.identityBadges}>
            <span>{labelize(lead.stage_key)}</span>
            <span>{labelize(lead.lead_temperature)} lead</span>
            <span>{labelize(lead.source)}</span>
          </div>
        </div>
        <div className={styles.quickActions}>
          {phone ? <a className={styles.primaryCommand} href={`tel:${phone}`}>Call seller</a> : null}
          {phone ? <a href={`sms:${phone}`}>Text</a> : null}
          {email ? <a href={`mailto:${email}`}>Email</a> : null}
          <Link href={tabHref("communications")}>Log contact</Link>
          <Link href={tabHref("underwriting")}>Run comps</Link>
          <LeadLifecycleActions archived={Boolean(lead.archived_at)} leadId={lead.id} />
        </div>
      </header>

      {lead.archived_at ? (
        <section className={styles.archiveNotice}>
          <strong>This lead is archived.</strong>
          <p>Restore it before editing, contacting the seller, or creating new deal activity.</p>
        </section>
      ) : (
        <>
          <section className={styles.commandStrip}>
            <div className={styles.nextAction}>
              <span>Next best action</span>
              <strong>{lead.intelligence.next_best_action.label}</strong>
              <p>{lead.intelligence.next_best_action.description}</p>
            </div>
            <dl className={styles.signalGrid}>
              <div><dt>Quality</dt><dd>{lead.intelligence.quality_score}</dd></div>
              <div><dt>Urgency</dt><dd>{lead.intelligence.urgency_score}</dd></div>
              <div><dt>Open tasks</dt><dd>{lead.open_tasks.length}</dd></div>
              <div><dt>Last contact</dt><dd>{lastContact ? formatDate(lastContact) : "Never"}</dd></div>
              <div><dt>Next follow-up</dt><dd>{formatOptionalDate(lead.next_follow_up_at)}</dd></div>
            </dl>
          </section>

          <nav className={styles.tabs} aria-label="Lead workspace views">
            {tabs.map(([key, label]) => (
              <Link aria-current={activeTab === key ? "page" : undefined} className={activeTab === key ? styles.activeTab : undefined} href={tabHref(key)} key={key}>{label}</Link>
            ))}
          </nav>

          <section className={styles.tabContent}>
            {activeTab === "overview" ? <OverviewTab lead={lead} /> : null}
            {activeTab === "communications" ? <CommunicationsTab lead={lead} /> : null}
            {activeTab === "underwriting" ? <UnderwritingTab lead={lead} /> : null}
            {activeTab === "deal" ? <DealTab buyers={buyers} lead={lead} /> : null}
            {activeTab === "history" ? <HistoryTab lead={lead} /> : null}
          </section>
        </>
      )}
    </main>
  );
}
