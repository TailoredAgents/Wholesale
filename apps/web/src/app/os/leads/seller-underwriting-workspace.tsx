import { ArrowRight, FileSearch } from "lucide-react";
import Link from "next/link";

import type { LeadListItem, UnderwritingCalibration } from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import styles from "../_components/deal-workspaces.module.css";

const underwritingStages = [
  "underwriting",
  "offer_pending_approval",
  "offer_ready",
  "offer_presented",
];

function readiness(value: string) {
  if (value === "formula_review_ready") return "Review ready";
  if (value === "building_evidence") return "Building evidence";
  return "Insufficient sample";
}

export function SellerUnderwritingWorkspace({
  calibration,
  initialLeadId,
  leads,
}: {
  calibration: UnderwritingCalibration | null;
  initialLeadId: string;
  leads: LeadListItem[];
}) {
  const underwritingLeads = leads.filter(
    (lead) => lead.asset_class === "house" && underwritingStages.includes(lead.stage_key),
  );
  const selected =
    underwritingLeads.find((lead) => lead.id === initialLeadId) ?? underwritingLeads[0] ?? null;
  const sampleCount = calibration?.overall.sample_count ?? 0;
  const minimum = calibration?.minimum_sample_for_formula_review ?? 50;
  const missingEvidence = selected
    ? [selected.property_condition, selected.asking_price, selected.mortgage_balance].filter(
        (value) => !value || value.toLowerCase() === "unknown",
      ).length
    : 0;

  return (
    <section className={styles.splitWorkspace}>
      <aside className={styles.queue} aria-label="Underwriting queue">
        <header>
          <div><span>Analysis queue</span><strong>{underwritingLeads.length} deals</strong></div>
        </header>
        {!underwritingLeads.length ? (
          <p className={styles.empty}>No deals are waiting for underwriting.</p>
        ) : null}
        {underwritingLeads.map((lead) => (
          <Link
            className={selected?.id === lead.id ? styles.selectedRow : styles.queueRow}
            href={`/os/leads?view=underwriting&lead=${lead.id}`}
            key={lead.id}
          >
            <div>
              <strong>{lead.seller_name}</strong>
              <StatusBadge tone={lead.stage_key === "offer_pending_approval" ? "warning" : "info"}>
                {labelize(lead.stage_key)}
              </StatusBadge>
            </div>
            <span>{lead.property_address}</span>
            <dl>
              <div><dt>Condition</dt><dd>{labelize(lead.property_condition)}</dd></div>
              <div><dt>Asking</dt><dd>{lead.asking_price ?? "Unknown"}</dd></div>
            </dl>
          </Link>
        ))}
      </aside>

      <section aria-label="Underwriting detail" className={styles.detail}>
        {selected ? (
          <>
            <header className={styles.detailHeader}>
              <div>
                <span>{labelize(selected.stage_key)}</span>
                <h2>{selected.seller_name}</h2>
                <p>{selected.property_address}</p>
              </div>
              <Link className={styles.primaryLink} href={`/os/leads/${selected.id}?tab=valuation`}>
                Analyze comps <ArrowRight size={15} />
              </Link>
            </header>
            <div className={styles.detailGrid}>
              <section className={styles.section}>
                <header>
                  <div><span>Decision inputs</span><h3>Seller and property evidence</h3></div>
                  <StatusBadge tone={missingEvidence ? "warning" : "success"}>
                    {missingEvidence ? `${missingEvidence} missing` : "Ready"}
                  </StatusBadge>
                </header>
                <dl className={styles.factList}>
                  <div><dt>Property condition</dt><dd>{labelize(selected.property_condition)}</dd></div>
                  <div><dt>Seller asking price</dt><dd>{selected.asking_price ?? "Missing"}</dd></div>
                  <div><dt>Mortgage balance</dt><dd>{selected.mortgage_balance ?? "Missing"}</dd></div>
                  <div><dt>Motivation</dt><dd>{selected.motivation ?? "Missing"}</dd></div>
                  <div><dt>Timeline</dt><dd>{selected.desired_timeline ?? "Missing"}</dd></div>
                  <div><dt>Lead source</dt><dd>{labelize(selected.source)}</dd></div>
                </dl>
              </section>
              <section className={styles.section}>
                <header>
                  <div><span>Calibration</span><h3>How much trust is earned</h3></div>
                  <StatusBadge tone={sampleCount >= minimum ? "success" : "warning"}>
                    {readiness(calibration?.overall.readiness ?? "insufficient_sample")}
                  </StatusBadge>
                </header>
                <div className={styles.explanation}>
                  <strong>{sampleCount} verified outcomes</strong>
                  <p>
                    Stonegate compares saved predictions with later verified values. Formula changes
                    remain manual until the evidence is strong enough for review.
                  </p>
                </div>
                <Link className={styles.secondaryLink} href="/os/settings/data-quality">
                  Open valuation quality settings
                </Link>
              </section>
            </div>
          </>
        ) : (
          <div className={styles.emptyState}>
            <FileSearch size={24} />
            <h2>No underwriting work</h2>
            <p>Qualified deals appear here when they are ready for value analysis.</p>
          </div>
        )}
      </section>
    </section>
  );
}
