import { getMarketingOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import { OfflineExportButton } from "./offline-export-button";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

function formatMoney(cents: number | null) {
  if (cents === null) {
    return "N/A";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatRoas(basisPoints: number | null) {
  if (basisPoints === null) {
    return "N/A";
  }
  return `${(basisPoints / 10000).toFixed(2)}x`;
}

function maskClickId(value: string) {
  if (value.length <= 10) {
    return value;
  }
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
}

export default async function MarketingPage() {
  const { marketing, apiConnected } = await getMarketingOverview();

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Marketing</p>
          <h2>Marketing</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Tracking data</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Live attribution" : "API fallback"}
          </strong>
        </div>
      </header>

      <section className={styles.metrics}>
        <article className={styles.metric}>
          <span>Marketing spend</span>
          <strong>{formatMoney(marketing.summary.total_spend_cents)}</strong>
          <small>{marketing.summary.leads_created} leads created</small>
        </article>
        <article className={styles.metric}>
          <span>Attributed revenue</span>
          <strong>{formatMoney(marketing.summary.collected_revenue_cents)}</strong>
          <small>{marketing.summary.contracted_leads} contracted leads</small>
        </article>
        <article className={styles.metric}>
          <span>Cost per lead</span>
          <strong>{formatMoney(marketing.summary.cost_per_lead_cents)}</strong>
          <small>All tracked sources</small>
        </article>
        <article className={styles.metric}>
          <span>Cost per contract</span>
          <strong>{formatMoney(marketing.summary.cost_per_contract_cents)}</strong>
          <small>Under contract or closed</small>
        </article>
        <article className={styles.metric}>
          <span>ROAS</span>
          <strong>{formatRoas(marketing.summary.return_on_ad_spend_basis_points)}</strong>
          <small>{marketing.summary.pending_offline_exports} pending exports</small>
        </article>
      </section>

      <section className={styles.contentGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Campaign Performance</h3>
            <span>{marketing.campaigns.length} tracked rows</span>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Campaign</th>
                  <th>Views</th>
                  <th>Starts</th>
                  <th>Submits</th>
                  <th>Calls</th>
                  <th>Leads</th>
                  <th>Revenue</th>
                  <th>Spend</th>
                  <th>CPL</th>
                  <th>ROAS</th>
                </tr>
              </thead>
              <tbody>
                {marketing.campaigns.length === 0 ? (
                  <tr>
                    <td>No campaign data yet</td>
                    <td>0</td>
                    <td>0</td>
                    <td>0</td>
                    <td>0</td>
                    <td>0</td>
                    <td>$0</td>
                    <td>$0</td>
                    <td>N/A</td>
                    <td>N/A</td>
                  </tr>
                ) : null}
                {marketing.campaigns.map((campaign) => (
                  <tr key={`${campaign.source}-${campaign.medium}-${campaign.campaign}`}>
                    <td>
                      {labelize(campaign.source)}
                      <small className={styles.tableSubtext}>
                        {[campaign.medium, campaign.campaign]
                          .filter((value) => !["unknown", "uncategorized"].includes(value))
                          .map(labelize)
                          .join(" / ") || "No campaign"}
                      </small>
                    </td>
                    <td>{campaign.page_views}</td>
                    <td>{campaign.form_starts}</td>
                    <td>{campaign.form_submits}</td>
                    <td>{campaign.call_clicks}</td>
                    <td>{campaign.leads_created}</td>
                    <td>{formatMoney(campaign.collected_revenue_cents)}</td>
                    <td>{formatMoney(campaign.marketing_spend_cents)}</td>
                    <td>{formatMoney(campaign.cost_per_lead_cents)}</td>
                    <td>{formatRoas(campaign.return_on_ad_spend_basis_points)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Offline Conversion Queue</h3>
            <span>{marketing.offline_exports.length} exports</span>
          </div>
          <OfflineExportButton />
          <div className={styles.buyerList}>
            {marketing.offline_exports.length === 0 ? (
              <p>No offline conversion exports generated yet.</p>
            ) : null}
            {marketing.offline_exports.map((exportRecord) => (
              <article key={exportRecord.id}>
                <div>
                  <strong>{labelize(exportRecord.platform)}</strong>
                  <span>{labelize(exportRecord.status)}</span>
                </div>
                <dl>
                  <div>
                    <dt>Event</dt>
                    <dd>{labelize(exportRecord.event_name)}</dd>
                  </div>
                  <div>
                    <dt>Click ID</dt>
                    <dd>{maskClickId(exportRecord.click_id)}</dd>
                  </div>
                  <div>
                    <dt>Value</dt>
                    <dd>{formatMoney(exportRecord.value_cents)}</dd>
                  </div>
                  <div>
                    <dt>Attempts</dt>
                    <dd>{exportRecord.attempt_count}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </article>
      </section>
    </>
  );
}
