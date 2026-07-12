import Link from "next/link";

import { getLeadDetail } from "../../lib/api";
import { LeadEditForm } from "./lead-edit-form";
import { StageUpdateForm } from "./stage-update-form";
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

export default async function LeadDetailPage({ params }: LeadPageProps) {
  const { leadId } = await params;
  const { lead, apiConnected } = await getLeadDetail(leadId);

  if (!lead) {
    return (
      <main className={styles.page}>
        <Link className={styles.backLink} href="/">
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
      <Link className={styles.backLink} href="/">
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
        </div>
      </header>

      <section className={styles.grid}>
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
