import {
  ArrowRight,
  CalendarDays,
  Check,
  ChevronDown,
  Circle,
  FileSignature,
  FileText,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";

import { CompleteTaskButton } from "../../complete-task-button";
import { getBuyers, getLeadDetail, getWorkspaceProfile, type LeadDetail } from "../../lib/api";
import { LeadLifecycleActions } from "../../os/leads/lead-lifecycle-actions";
import { RecordTimeline } from "../../os/_components/record-timeline";
import { AppointmentForm } from "./appointment-form";
import { AppointmentOutcomeForm } from "./appointment-outcome-form";
import { BuyerOfferForm } from "./buyer-offer-form";
import { CommunicationLogForm } from "./communication-log-form";
import { LeadActionForm } from "./lead-action-form";
import { LeadCallButton } from "./lead-call-button";
import { LeadEditForm } from "./lead-edit-form";
import { LandValuationWorkspace } from "./land-valuation-workspace";
import { MarketValuePreview } from "./market-value-preview";
import { NegotiationGovernance } from "./negotiation-governance";
import { OfferApprovalControl } from "./offer-approval-control";
import { PropertyValidationControl } from "./property-validation-control";
import { PropertyIntelligencePanel } from "./property-intelligence-panel";
import { StageUpdateForm } from "./stage-update-form";
import { TransactionForm } from "./transaction-form";
import { UnderwritingForm } from "./underwriting-form";
import { UnderwritingVersionComparison } from "./underwriting-version-comparison";
import styles from "./page.module.css";

const tabs = [
  ["summary", "Summary"],
  ["activity", "Activity"],
  ["property", "Property"],
  ["valuation", "Valuation & Offer"],
  ["appointments", "Appointments"],
  ["contract", "Contract & Deal"],
  ["files", "Files"],
] as const;

type LeadTab = (typeof tabs)[number][0];

type LeadPageProps = {
  params: Promise<{ leadId: string }>;
  searchParams?: Promise<{
    edit?: string | string[];
    returnTo?: string | string[];
    tab?: string | string[];
  }>;
};

function internalReturnPath(value: string | string[] | undefined) {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate?.startsWith("/os/") && !candidate.startsWith("//") ? candidate : "/os/leads";
}

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
  const aliases: Record<string, LeadTab> = {
    overview: "summary",
    communications: "activity",
    history: "activity",
    underwriting: "valuation",
    deal: "contract",
  };
  const normalized = candidate ? aliases[candidate] ?? candidate : "summary";
  return tabs.some(([key]) => key === normalized) ? (normalized as LeadTab) : "summary";
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
        <div><dt>Lead type</dt><dd>{labelize(lead.asset_class)}</dd></div>
        <div><dt>Motivation</dt><dd>{lead.motivation ?? "Unknown"}</dd></div>
        <div><dt>Timeline</dt><dd>{labelize(lead.desired_timeline)}</dd></div>
        <div><dt>Condition</dt><dd>{labelize(lead.property_condition)}</dd></div>
        <div><dt>Occupancy</dt><dd>{labelize(lead.occupancy_status)}</dd></div>
        <div><dt>Asking price</dt><dd>{lead.asking_price ?? "Unknown"}</dd></div>
        <div><dt>Mortgage</dt><dd>{lead.mortgage_balance ?? "Unknown"}</dd></div>
        <div><dt>Property type</dt><dd>{labelize(lead.property_type)}</dd></div>
        <div><dt>Parcel / APN</dt><dd>{lead.property_parcel_id ?? "Unknown"}</dd></div>
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
            {task.work_kind === "primary_next_action" ? (
              <Link href={`/os/tasks?item=task:${task.id}`}>Record outcome</Link>
            ) : (
              <CompleteTaskButton taskId={task.id} />
            )}
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
      <Link
        className={styles.inlineEditLink}
        href={`/os/leads/${lead.id}?tab=property&edit=lead#edit-lead`}
      >
        Edit qualification
      </Link>
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
      <RecordTimeline items={activity.map((item) => ({
        description: item.summary,
        id: `${item.event_type}-${item.created_at}`,
        meta: formatDate(item.created_at),
        title: labelize(item.event_type),
      }))} />
    </section>
  );
}

function InternalNotesPanel({ lead }: { lead: LeadDetail }) {
  const allNotes = lead.communications.filter(
    (item) => item.channel === "note" && item.direction === "internal",
  );
  const notes = allNotes.slice(0, 6);
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader title="Internal seller notes" meta={countLabel(allNotes.length, "note")} />
      <div className={styles.communicationTimeline}>
        {notes.length === 0 ? (
          <p className={styles.emptyState}>No internal seller notes yet.</p>
        ) : null}
        {notes.map((note) => (
          <article key={note.id}>
            <div>
              <strong>{note.subject ?? "Seller note"}</strong>
              <span>{labelize(note.provider)}</span>
            </div>
            <p>{note.body}</p>
            <small>{formatDate(note.occurred_at)}</small>
          </article>
        ))}
      </div>
      <Link className={styles.inlineEditLink} href={`/os/leads/${lead.id}?tab=activity`}>
        View complete seller timeline
      </Link>
    </section>
  );
}

function OverviewTab({
  activeAppointment,
  lead,
}: {
  activeAppointment: LeadDetail["appointments"][number] | undefined;
  lead: LeadDetail;
}) {
  const appointmentWorkspaceHref = activeAppointment
    ? `/os/calendar?view=appointment&appointment=${encodeURIComponent(activeAppointment.id)}`
    : `/os/calendar?view=appointment&schedule=1&lead=${encodeURIComponent(lead.id)}`;
  return (
    <div className={styles.overviewGrid}>
      <div className={styles.mainColumn}>
        <TasksPanel lead={lead} />
        <QualificationPanel lead={lead} />
        <InternalNotesPanel lead={lead} />
        <RecentActivityPanel lead={lead} />
      </div>
      <aside className={styles.sideColumn}>
        <ContactPanel lead={lead} />
        <PropertyPanel lead={lead} />
        <section className={styles.sectionPanel}>
          <SectionHeader title="Record controls" />
          <dl className={styles.compactFacts}>
            <div><dt>Stage</dt><dd>{labelize(lead.stage_key)}</dd></div>
            <div><dt>Primary action</dt><dd>{lead.primary_next_action?.title ?? "Not set"}</dd></div>
            <div><dt>Action owner</dt><dd>{lead.primary_next_action?.responsible_user_email ?? "Unassigned"}</dd></div>
            <div><dt>Due</dt><dd>{formatOptionalDate(lead.primary_next_action?.due_at ?? lead.next_follow_up_at)}</dd></div>
            <div><dt>Appointment</dt><dd>{labelize(lead.appointment_status)}</dd></div>
          </dl>
          <ActionDisclosure label="Change pipeline stage">
            <StageUpdateForm
              assetClass={lead.asset_class}
              currentStage={lead.stage_key}
              leadId={lead.id}
            />
          </ActionDisclosure>
          <div className={styles.appointmentPreparation}>
            <span>{activeAppointment ? "Next seller appointment" : "Appointment preparation"}</span>
            <strong>
              {activeAppointment
                ? formatDate(activeAppointment.scheduled_start_at)
                : "No active appointment"}
            </strong>
            <p>
              {activeAppointment
                ? `${labelize(activeAppointment.location_type)} meeting`
                : "Schedule the seller before preparing the meeting workspace."}
            </p>
            <Link href={appointmentWorkspaceHref}>
              {activeAppointment ? "Prepare appointment" : "Schedule appointment"}
            </Link>
          </div>
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

function valuationStageState(
  complete: boolean,
  priorComplete: boolean,
): "complete" | "current" | "upcoming" {
  if (complete) return "complete";
  return priorComplete ? "current" : "upcoming";
}

function UnderwritingTab({ lead }: { lead: LeadDetail }) {
  const latestVersion = lead.underwriting_versions[0];
  const quickCompComplete = Boolean(latestVersion);
  const deskReviewComplete = Boolean(
    latestVersion
    && ["pre_meeting_reviewed", "walkthrough_verified"].includes(
      latestVersion.report_stage ?? "",
    ),
  );
  const walkthroughComplete = Boolean(
    latestVersion?.report_stage === "walkthrough_verified"
    || latestVersion?.source === "field_inspection",
  );
  const offerDecisionComplete = [
    "offer_ready",
    "offer_presented",
    "negotiating",
    "under_contract",
  ].includes(lead.stage_key);
  const activeAppointment = lead.appointments.find(
    (appointment) =>
      ["scheduled", "rescheduled"].includes(appointment.status)
      && !appointment.outcome,
  );
  const appointmentHref = activeAppointment
    ? `/os/calendar?view=appointment&appointment=${encodeURIComponent(activeAppointment.id)}`
    : `/os/leads/${lead.id}?tab=appointments`;
  const missingFacts = lead.intelligence.missing_fields.slice(0, 3);
  const stages = [
    {
      key: "quick",
      label: "Quick Comp",
      meta: quickCompComplete ? `Version ${latestVersion?.version_number}` : "Not prepared",
      href: "#valuation-analysis",
      state: valuationStageState(quickCompComplete, true),
    },
    {
      key: "desk",
      label: "Desk Review",
      meta: deskReviewComplete ? "Evidence reviewed" : "Needs review",
      href: "#valuation-analysis",
      state: valuationStageState(deskReviewComplete, quickCompComplete),
    },
    {
      key: "walkthrough",
      label: "Walkthrough",
      meta: walkthroughComplete
        ? "Field evidence transferred"
        : activeAppointment
          ? "Appointment ready"
          : "Not scheduled",
      href: appointmentHref,
      state: valuationStageState(walkthroughComplete, deskReviewComplete),
    },
    {
      key: "offer",
      label: "Offer Decision",
      meta: offerDecisionComplete ? "Authority ready" : "Not approved",
      href: "#offer-decision",
      state: valuationStageState(offerDecisionComplete, walkthroughComplete),
    },
  ];

  return (
    <div className={styles.valuationWorkspace}>
      <section className={styles.valuationProgress} aria-label="Valuation and offer progress">
        <header>
          <div>
            <span>Decision workflow</span>
            <h2>Valuation and offer</h2>
          </div>
          <strong>{stages.filter((stage) => stage.state === "complete").length}/4 complete</strong>
        </header>
        <nav>
          {stages.map((stage, index) => (
            <Link data-state={stage.state} href={stage.href} key={stage.key}>
              <span>{stage.state === "complete" ? <Check size={15} /> : <Circle size={13} />}</span>
              <div><strong>{index + 1}. {stage.label}</strong><small>{stage.meta}</small></div>
            </Link>
          ))}
        </nav>
      </section>

      {missingFacts.length ? (
        <section className={styles.valuationMissingFacts}>
          <div>
            <span>Highest-value missing facts</span>
            <strong>{missingFacts.map((item) => item.label).join(" / ")}</strong>
          </div>
          <Link href={`/os/leads/${lead.id}?tab=property`}>Update property facts <ArrowRight size={14} /></Link>
        </section>
      ) : null}

      <div className={styles.valuationGrid}>
        <div className={styles.mainColumn}>
          <div id="valuation-analysis"><MarketValuePreview leadId={lead.id} /></div>
          <details className={styles.valuationAdvanced}>
            <summary>
              <span>Advanced records</span>
              <strong>{lead.underwriting_versions.length} underwriting versions</strong>
            </summary>
            <div>
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
            </div>
          </details>
          <section className={styles.sectionPanel} id="offer-decision">
            <SectionHeader title="Offer approval and negotiation" />
            <OfferApprovalControl
              askingPrice={lead.asking_price}
              leadId={lead.id}
              versions={lead.underwriting_versions}
            />
            <NegotiationGovernance leadId={lead.id} />
          </section>
        </div>
        <aside className={styles.valuationSummary}>
          <header><span>Current decision</span><strong>{latestVersion ? `Version ${latestVersion.version_number}` : "Not prepared"}</strong></header>
          <dl>
            <div><dt>ARV range</dt><dd>{formatMoney(latestVersion?.arv_low_cents ?? null)} to {formatMoney(latestVersion?.arv_high_cents ?? null)}</dd></div>
            <div><dt>Repair range</dt><dd>{formatMoney(latestVersion?.repair_low_cents ?? null)} to {formatMoney(latestVersion?.repair_high_cents ?? null)}</dd></div>
            <div><dt>Buyer target</dt><dd>{formatMoney(latestVersion?.recommended_disposition_cents ?? null)}</dd></div>
            <div><dt>Opening</dt><dd>{formatMoney(latestVersion?.recommended_offer_cents ?? null)}</dd></div>
            <div><dt>Seller ceiling</dt><dd>{formatMoney(latestVersion?.seller_contract_ceiling_cents ?? latestVersion?.max_offer_cents ?? null)}</dd></div>
          </dl>
          <nav>
            <a href={latestVersion ? "#valuation-reports" : "#valuation-analysis"}>
              <FileText size={15} />{latestVersion ? "Reports" : "Run valuation"}
            </a>
            <Link href={appointmentHref}><CalendarDays size={15} />{activeAppointment ? "Appointment" : "Schedule"}</Link>
            <a href="#offer-decision"><ShieldCheck size={15} />Offer approval</a>
            <Link href={`/os/leads/${lead.id}?tab=contract`}><FileSignature size={15} />Contract & signing</Link>
          </nav>
          <PropertyPanel lead={lead} />
        </aside>
      </div>
    </div>
  );
}

function LandValuationTab({ lead }: { lead: LeadDetail }) {
  return <LandValuationWorkspace leadId={lead.id} />;
}

function DealTab({ lead, buyers }: { lead: LeadDetail; buyers: Awaited<ReturnType<typeof getBuyers>>["buyers"] }) {
  if (lead.asset_class === "land") {
    return (
      <div className={styles.tabGrid}>
        <section className={styles.sectionPanel}>
          <SectionHeader title="Land contract and deal workflow" meta="Intentionally blocked" />
          <div className={styles.sectionBody}>
            <p className={styles.emptyState}>
              Stonegate will not open a residential transaction, create a House purchase package,
              send a House agreement for signature, or start residential buyer disposition for a
              Land lead. This workspace will unlock only after a counsel-approved Georgia Land
              agreement, parcel diligence checklist, Land valuation and Land buyer package are
              implemented and verified.
            </p>
            <Link className={styles.inlineEditLink} href={`/os/leads/${lead.id}?tab=property`}>
              Continue Land research <ArrowRight size={14} />
            </Link>
          </div>
        </section>
      </div>
    );
  }
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
                <Link className={styles.transactionWorkspaceLink} href={`/os/transactions?transaction=${transaction.id}`}>
                  Open transaction coordination
                </Link>
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

function ActivityTab({ lead }: { lead: LeadDetail }) {
  return (
    <div className={styles.activityWorkspace}>
      <CommunicationsTab lead={lead} />
      <HistoryTab lead={lead} />
    </div>
  );
}

function PropertyTab({
  lead,
  editLeadOpen,
}: {
  lead: LeadDetail;
  editLeadOpen: boolean;
}) {
  return (
    <div className={styles.tabGrid}>
      <div className={styles.mainColumn}>
        <PropertyIntelligencePanel lead={lead} />
        <PropertyPanel lead={lead} />
        <details
          className={`${styles.sectionPanel} ${styles.editAnchor} ${styles.editLeadDisclosure}`}
          id="edit-lead"
          open={editLeadOpen}
        >
          <summary className={styles.editLeadSummary}>
            <span className={styles.editLeadSummaryCopy}>
              <strong>Edit lead</strong>
              <span>Update seller, property, qualification, and ownership details.</span>
            </span>
            <span className={styles.editLeadSummaryAction}>
              <span className={styles.editLeadOpenLabel}>Open editor</span>
              <span className={styles.editLeadCloseLabel}>Close editor</span>
              <ChevronDown aria-hidden="true" size={18} />
            </span>
          </summary>
          <div className={styles.sectionBody}><LeadEditForm lead={lead} /></div>
        </details>
      </div>
      <aside className={styles.sideColumn}>
        <ContactPanel lead={lead} />
        <QualificationPanel lead={lead} />
      </aside>
    </div>
  );
}

function AppointmentsTab({ lead }: { lead: LeadDetail }) {
  return (
    <div className={styles.tabGrid}>
      <section className={styles.sectionPanel}>
        <SectionHeader title="Seller appointments" meta={countLabel(lead.appointments.length, "appointment")} />
        <div className={styles.recordList}>
          {!lead.appointments.length ? <p className={styles.emptyState}>No appointment scheduled.</p> : null}
          {lead.appointments.map((appointment) => (
            <article key={appointment.id}>
              <div className={styles.recordTitle}>
                <strong>{labelize(appointment.appointment_type)}</strong>
                <span>{labelize(appointment.status)}</span>
              </div>
              <p>{formatDate(appointment.scheduled_start_at)} / {labelize(appointment.location_type)}</p>
              <small>{appointment.outcome ? `Outcome: ${labelize(appointment.outcome)}` : appointment.notes ?? "No outcome recorded"}</small>
            </article>
          ))}
        </div>
      </section>
      <aside className={styles.sideColumn}>
        <section className={styles.sectionPanel}>
          <SectionHeader title="Appointment actions" />
          <ActionDisclosure label="Schedule appointment">
            <AppointmentForm leadId={lead.id} />
          </ActionDisclosure>
          <ActionDisclosure label="Record appointment outcome">
            <AppointmentOutcomeForm appointments={lead.appointments} leadId={lead.id} />
          </ActionDisclosure>
        </section>
        <TasksPanel lead={lead} />
      </aside>
    </div>
  );
}

function FilesTab({ lead }: { lead: LeadDetail }) {
  return (
    <div className={styles.tabGrid}>
      <section className={styles.sectionPanel}>
        <SectionHeader title="Reports and deal documents" />
        <div className={styles.recordList}>
          {lead.underwriting_versions.map((version) => (
            <article key={version.id}>
              {lead.asset_class === "land" ? (
                <>
                  <div className={styles.recordTitle}>
                    <strong>Legacy residential valuation version {version.version_number}</strong>
                    <span>Incompatible with Land</span>
                  </div>
                  <p>
                    Retained for audit history after reclassification. Do not use its ARV, repair,
                    comp or offer figures for this Land opportunity.
                  </p>
                  <Link className={styles.transactionWorkspaceLink} href={`/os/leads/${lead.id}?tab=property`}>
                    Review current Land evidence
                  </Link>
                </>
              ) : (
                <>
                  <div className={styles.recordTitle}>
                    <strong>Valuation report version {version.version_number}</strong>
                    <span>{labelize(version.report_stage)}</span>
                  </div>
                  <p>{formatMoney(version.arv_low_cents)} to {formatMoney(version.arv_high_cents)} ARV</p>
                  <Link className={styles.transactionWorkspaceLink} href={`/os/leads/${lead.id}?tab=valuation`}>
                    Open report and PDF controls
                  </Link>
                </>
              )}
            </article>
          ))}
          {lead.transactions.map((transaction) => (
            <article key={transaction.id}>
              <div className={styles.recordTitle}>
                <strong>
                  {lead.asset_class === "land"
                    ? `Legacy residential ${labelize(transaction.contract_type)}`
                    : labelize(transaction.contract_type)}
                </strong>
                <span>{lead.asset_class === "land" ? "Incompatible with Land" : labelize(transaction.status)}</span>
              </div>
              <p>
                {lead.asset_class === "land"
                  ? "Retained for audit after reclassification; residential execution is locked."
                  : transaction.title_company ?? "Title company not assigned"}
              </p>
              {lead.asset_class === "house" ? (
                <Link className={styles.transactionWorkspaceLink} href={`/os/transactions?transaction=${transaction.id}`}>
                  Open contracts and closing files
                </Link>
              ) : null}
            </article>
          ))}
          {!lead.underwriting_versions.length && !lead.transactions.length ? (
            <p className={styles.emptyState}>Reports and transaction documents will appear here after they are created.</p>
          ) : null}
        </div>
      </section>
      <aside className={styles.sideColumn}>
        <section className={styles.sectionPanel}>
          <SectionHeader title="Where files are created" />
          <div className={styles.sectionBody}>
            <p className={styles.emptyState}>
              {lead.asset_class === "land"
                ? "Land valuation reports and contract packages remain unavailable until their dedicated workflows are verified. Legacy House files are audit history only."
                : "Investor and client PDFs are generated in Valuation & Offer. Contracts, signatures, title files, and closing documents are managed in the transaction workspace."}
            </p>
          </div>
        </section>
      </aside>
    </div>
  );
}

function formatSavedFact(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Unknown";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map(formatSavedFact).join(", ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${labelize(key)}: ${formatSavedFact(item)}`)
      .join("; ");
  }
  return String(value);
}

function ReadOnlyPropertyPanel({ lead }: { lead: LeadDetail }) {
  const savedFacts = Object.entries(lead.property_intelligence.facts)
    .filter(([, fact]) => fact.value !== undefined && fact.value !== null)
    .sort(([left], [right]) => left.localeCompare(right));
  return (
    <>
      <section className={styles.sectionPanel}>
        <SectionHeader title="Property and seller situation" meta="Read only" />
        <dl className={styles.factGrid}>
          <div><dt>Address</dt><dd>{lead.property_address}</dd></div>
          <div><dt>Address status</dt><dd>{labelize(lead.property_validation.status)}</dd></div>
          <div><dt>Validated address</dt><dd>{lead.property_validation.validated_address ?? "Unknown"}</dd></div>
          <div><dt>Validation provider</dt><dd>{labelize(lead.property_validation.provider)}</dd></div>
          <div><dt>Lead type</dt><dd>{labelize(lead.asset_class)}</dd></div>
          <div><dt>Property type</dt><dd>{labelize(lead.property_type)}</dd></div>
          <div><dt>Parcel / APN</dt><dd>{lead.property_parcel_id ?? "Unknown"}</dd></div>
          <div><dt>County</dt><dd>{lead.property_county ?? "Unknown"}</dd></div>
          <div><dt>Motivation</dt><dd>{lead.motivation ?? "Unknown"}</dd></div>
          <div><dt>Timeline</dt><dd>{labelize(lead.desired_timeline)}</dd></div>
          <div><dt>Condition</dt><dd>{labelize(lead.property_condition)}</dd></div>
          <div><dt>Occupancy</dt><dd>{labelize(lead.occupancy_status)}</dd></div>
          <div><dt>Asking price</dt><dd>{lead.asking_price ?? "Unknown"}</dd></div>
          <div><dt>Mortgage</dt><dd>{lead.mortgage_balance ?? "Unknown"}</dd></div>
        </dl>
      </section>
      <section className={styles.sectionPanel}>
        <SectionHeader title="Saved property research" meta={countLabel(savedFacts.length, "fact")} />
        {savedFacts.length ? (
          <dl className={styles.factGrid}>
            {savedFacts.map(([key, fact]) => (
              <div key={key}>
                <dt>{labelize(key)}</dt>
                <dd>{formatSavedFact(fact.value)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className={styles.emptyState}>No saved property research facts are on this record.</p>
        )}
      </section>
    </>
  );
}

function ReadOnlyCommunicationPanel({ lead }: { lead: LeadDetail }) {
  const communications = [...lead.communications].sort(
    (left, right) => new Date(right.occurred_at).getTime() - new Date(left.occurred_at).getTime(),
  );
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader
        title="Calls, messages, and internal notes"
        meta={countLabel(communications.length, "record")}
      />
      <div className={styles.communicationTimeline}>
        {communications.length === 0 ? (
          <p className={styles.emptyState}>No communication history is saved.</p>
        ) : null}
        {communications.map((item) => (
          <article key={item.id}>
            <div>
              <strong>
                {item.channel === "note" && item.direction === "internal"
                  ? item.subject ?? "Internal seller note"
                  : `${labelize(item.direction)} ${labelize(item.channel)}`}
              </strong>
              <span>{labelize(item.status)} via {labelize(item.provider)}</span>
            </div>
            {item.subject && item.channel !== "note" ? <strong>{item.subject}</strong> : null}
            <p>{item.body}</p>
            <small>{formatDate(item.occurred_at)}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function ReadOnlyActivityPanel({ lead }: { lead: LeadDetail }) {
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader
        title="Recent activity history"
        meta={countLabel(lead.recent_activity.length, "event")}
      />
      <RecordTimeline items={lead.recent_activity.map((item, index) => ({
        description: item.summary,
        id: `${item.event_type}-${item.created_at}-${index}`,
        meta: formatDate(item.created_at),
        title: labelize(item.event_type),
      }))} />
    </section>
  );
}

function ReadOnlyAppointmentsPanel({ lead }: { lead: LeadDetail }) {
  const appointments = [...lead.appointments].sort(
    (left, right) => (
      new Date(right.scheduled_start_at).getTime() - new Date(left.scheduled_start_at).getTime()
    ),
  );
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader title="Appointments" meta={countLabel(appointments.length, "appointment")} />
      <div className={styles.recordList}>
        {appointments.length === 0 ? (
          <p className={styles.emptyState}>No appointments were saved.</p>
        ) : null}
        {appointments.map((appointment) => (
          <article key={appointment.id}>
            <div className={styles.recordTitle}>
              <strong>{labelize(appointment.appointment_type)}</strong>
              <span>{labelize(appointment.status)}</span>
            </div>
            <p>
              {formatDate(appointment.scheduled_start_at)}
              {appointment.scheduled_end_at
                ? ` to ${formatDate(appointment.scheduled_end_at)}`
                : ""}
            </p>
            <p>{appointment.location ?? `${labelize(appointment.location_type)} appointment`}</p>
            {appointment.notes ? <p>{appointment.notes}</p> : null}
            <small>{appointment.outcome ? `Outcome: ${labelize(appointment.outcome)}` : "No outcome recorded"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function ReadOnlyValuationPanel({ lead }: { lead: LeadDetail }) {
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader
        title="Valuation history"
        meta={countLabel(lead.underwriting_versions.length, "version")}
      />
      <div className={styles.recordList}>
        {lead.underwriting_versions.length === 0 ? (
          <p className={styles.emptyState}>No valuation version was saved.</p>
        ) : null}
        {lead.underwriting_versions.map((version) => (
          <article key={version.id}>
            <div className={styles.recordTitle}>
              <strong>Version {version.version_number}</strong>
              <span>{labelize(version.status)}</span>
            </div>
            <p>
              ARV {formatMoney(version.arv_low_cents)} to {formatMoney(version.arv_high_cents)};
              recommended offer {formatMoney(version.recommended_offer_cents)}
            </p>
            <p>
              Repairs {formatMoney(version.repair_low_cents)} to {formatMoney(version.repair_high_cents)};
              ceiling {formatMoney(version.seller_contract_ceiling_cents ?? version.max_offer_cents)}
            </p>
            {version.notes ? <p>{version.notes}</p> : null}
            <small>{labelize(version.source)} / {formatDate(version.created_at)}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function ReadOnlyTransactionsPanel({ lead }: { lead: LeadDetail }) {
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader title="Transaction history" meta={countLabel(lead.transactions.length, "transaction")} />
      <div className={styles.recordList}>
        {lead.transactions.length === 0 ? (
          <p className={styles.emptyState}>No transaction was opened.</p>
        ) : null}
        {lead.transactions.map((transaction) => {
          const completedChecklistItems = transaction.checklist_items.filter(
            (item) => ["complete", "not_applicable"].includes(item.status),
          ).length;
          return (
            <article key={transaction.id}>
              <div className={styles.recordTitle}>
                <strong>{labelize(transaction.contract_type)}</strong>
                <span>{labelize(transaction.status)}</span>
              </div>
              <p>
                Purchase {formatMoney(transaction.purchase_price_cents)};
                assignment fee {formatMoney(transaction.assignment_fee_cents)}
              </p>
              <p>
                Closing {formatOptionalDate(transaction.closing_date)};
                checklist {completedChecklistItems}/{transaction.checklist_items.length} complete
              </p>
              <p>
                Sent {formatOptionalDate(transaction.contract_sent_at)};
                executed {formatOptionalDate(transaction.contract_executed_at)}
              </p>
              {transaction.notes ? <p>{transaction.notes}</p> : null}
              <small>Opened {formatDate(transaction.created_at)}</small>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ReadOnlyBuyerOffersPanel({ lead }: { lead: LeadDetail }) {
  const offers = [...lead.buyer_offers].sort(
    (left, right) => new Date(right.received_at).getTime() - new Date(left.received_at).getTime(),
  );
  return (
    <section className={styles.sectionPanel}>
      <SectionHeader title="Buyer offer history" meta={countLabel(offers.length, "offer")} />
      <div className={styles.recordList}>
        {offers.length === 0 ? (
          <p className={styles.emptyState}>No buyer offers were saved.</p>
        ) : null}
        {offers.map((offer) => (
          <article key={offer.id}>
            <div className={styles.recordTitle}>
              <strong>{offer.buyer_name}</strong>
              <span>{labelize(offer.status)}</span>
            </div>
            <p>
              Offer {formatMoney(offer.amount_cents)};
              earnest money {formatMoney(offer.earnest_money_cents)}
            </p>
            <p>
              {labelize(offer.financing_type)} financing;
              proof of funds {offer.proof_of_funds_received ? "received" : "not received"}
            </p>
            {offer.notes ? <p>{offer.notes}</p> : null}
            <small>Received {formatDate(offer.received_at)}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function ArchivedLeadRecord({ lead }: { lead: LeadDetail }) {
  return (
    <section className={styles.archivedRecord} aria-label="Read-only archived lead record">
      <header className={styles.readOnlyRecordHeader}>
        <div>
          <span>Read-only history</span>
          <h2>Saved lead record</h2>
        </div>
        <p>
          The facts and history below remain available for reference. Reopen or restore the lead
          before changing seller, property, appointment, valuation, or transaction data.
        </p>
      </header>
      <div className={styles.overviewGrid}>
        <div className={styles.mainColumn}>
          <ReadOnlyCommunicationPanel lead={lead} />
          <ReadOnlyActivityPanel lead={lead} />
          <ReadOnlyAppointmentsPanel lead={lead} />
          <ReadOnlyValuationPanel lead={lead} />
          <ReadOnlyTransactionsPanel lead={lead} />
          <ReadOnlyBuyerOffersPanel lead={lead} />
        </div>
        <aside className={styles.sideColumn}>
          <ContactPanel lead={lead} />
          <ReadOnlyPropertyPanel lead={lead} />
          <section className={styles.sectionPanel}>
            <SectionHeader title="Record history" meta="Read only" />
            <dl className={styles.compactFacts}>
              <div><dt>Stage</dt><dd>{labelize(lead.stage_key)}</dd></div>
              <div><dt>Disposition</dt><dd>{labelize(lead.close_out_disposition)}</dd></div>
              <div><dt>Closed at</dt><dd>{formatOptionalDate(lead.closed_out_at)}</dd></div>
              <div><dt>Closed by</dt><dd>{lead.closed_out_by_user_email ?? "Unknown"}</dd></div>
              <div><dt>Archived at</dt><dd>{formatOptionalDate(lead.archived_at)}</dd></div>
              <div><dt>Created at</dt><dd>{formatDate(lead.created_at)}</dd></div>
              <div><dt>Close-out reason</dt><dd>{lead.close_out_reason ?? "Duplicate or test archive"}</dd></div>
            </dl>
          </section>
        </aside>
      </div>
    </section>
  );
}

export async function LeadDetailView({ params, searchParams }: LeadPageProps) {
  const [{ leadId }, query] = await Promise.all([params, searchParams]);
  const activeTab = normalizeTab(query?.tab);
  const requestedEditor = Array.isArray(query?.edit) ? query.edit[0] : query?.edit;
  const editLeadOpen = requestedEditor === "lead";
  const returnTo = internalReturnPath(query?.returnTo);
  const [{ lead, apiConnected }, buyerResult, profile] = await Promise.all([
    getLeadDetail(leadId),
    activeTab === "contract"
      ? getBuyers()
      : Promise.resolve({ buyers: [], apiConnected: true }),
    getWorkspaceProfile(),
  ]);
  const buyers = buyerResult.buyers;

  if (!lead) {
    return (
      <div className={styles.page}>
        <Link className={styles.backLink} href={returnTo}>Back to previous view</Link>
        <section className={styles.empty}><p>{apiConnected ? "Lead not found." : "API unavailable."}</p></section>
      </div>
    );
  }

  const phone = lead.contact_methods.find((method) => method.method_type === "phone")?.value;
  const email = lead.contact_methods.find((method) => method.method_type === "email")?.value;
  const lastContact = lead.communications[0]?.occurred_at ?? null;
  const tabHref = (tab: LeadTab, options?: { editLead?: boolean }) => {
    const values = new URLSearchParams({ tab });
    if (returnTo !== "/os/leads") values.set("returnTo", returnTo);
    if (options?.editLead) values.set("edit", "lead");
    return `/os/leads/${lead.id}?${values.toString()}`;
  };
  const activeAppointment = lead.appointments.find(
    (appointment) =>
      ["scheduled", "rescheduled"].includes(appointment.status)
      && !appointment.outcome,
  );
  const appointmentWorkspaceHref = activeAppointment
    ? `/os/calendar?view=appointment&appointment=${encodeURIComponent(activeAppointment.id)}`
    : `/os/calendar?view=appointment&schedule=1&lead=${encodeURIComponent(lead.id)}`;

  return (
    <div className={styles.page}>
      <div className={styles.breadcrumb}><Link href={returnTo}>Back</Link><span>/</span><span>{lead.seller_name}</span></div>
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
          {!lead.archived_at ? (
            <>
              {phone ? <LeadCallButton leadId={lead.id} /> : null}
              {phone ? <Link href={`/os/inbox?lead=${lead.id}&channel=sms`}>Text</Link> : null}
              {email ? <Link href={`/os/inbox?lead=${lead.id}&channel=email`}>Email</Link> : null}
              <Link href={tabHref("property", { editLead: true }) + "#edit-lead"}>Edit lead</Link>
              <Link href={tabHref("activity")}>Log contact</Link>
              <Link href={tabHref("valuation")}>
                {lead.asset_class === "land" ? "Run Land valuation" : "Run comps"}
              </Link>
              <Link className={styles.appointmentCommand} href={appointmentWorkspaceHref}>
                {activeAppointment ? "Prepare appointment" : "Schedule appointment"}
              </Link>
            </>
          ) : null}
          <LeadLifecycleActions
            archived={Boolean(lead.archived_at)}
            canArchiveRecords={Boolean(
              profile?.permissions.includes("records:delete_or_archive"),
            )}
            canEditLead={Boolean(profile?.permissions.includes("leads:edit"))}
            leadId={lead.id}
            stageKey={lead.stage_key}
          />
        </div>
      </header>

      {lead.archived_at ? (
        <>
          <section className={styles.archiveNotice}>
            {lead.close_out_disposition ? (
              <>
                <strong>This lead is closed as {labelize(lead.close_out_disposition)}.</strong>
                <p>Active follow-ups and warnings are stopped. Reopen it to return it to the pipeline with a new next action.</p>
                {lead.close_out_reason ? <p><strong>Reason:</strong> {lead.close_out_reason}</p> : null}
              </>
            ) : (
              <>
                <strong>This lead is administratively archived.</strong>
                <p>Restore it before editing, contacting the seller, or creating new deal activity.</p>
              </>
            )}
          </section>
          <ArchivedLeadRecord lead={lead} />
        </>
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
            {tabs.map(([key, label]) => {
              const visibleLabel = lead.asset_class === "land"
                ? key === "valuation"
                  ? "Land Valuation"
                  : key === "contract"
                    ? "Land Contract"
                    : label
                : label;
              return (
                <Link aria-current={activeTab === key ? "page" : undefined} className={activeTab === key ? styles.activeTab : undefined} href={tabHref(key)} key={key}>{visibleLabel}</Link>
              );
            })}
          </nav>

          <section className={styles.tabContent}>
            {activeTab === "summary" ? (
              <OverviewTab activeAppointment={activeAppointment} lead={lead} />
            ) : null}
            {activeTab === "activity" ? <ActivityTab lead={lead} /> : null}
            {activeTab === "property" ? (
              <PropertyTab editLeadOpen={editLeadOpen} lead={lead} />
            ) : null}
            {activeTab === "valuation" ? (
              lead.asset_class === "land"
                ? <LandValuationTab lead={lead} />
                : <UnderwritingTab lead={lead} />
            ) : null}
            {activeTab === "appointments" ? <AppointmentsTab lead={lead} /> : null}
            {activeTab === "contract" ? <DealTab buyers={buyers} lead={lead} /> : null}
            {activeTab === "files" ? <FilesTab lead={lead} /> : null}
          </section>
        </>
      )}
    </div>
  );
}
