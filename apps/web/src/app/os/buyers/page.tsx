import Link from "next/link";

import { getBuyers, getDashboardData } from "../../lib/api";
import { BuyerForm } from "./buyer-form";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

function labelize(value: string | null) {
  if (!value) {
    return "None";
  }
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatMoney(cents: number | null) {
  if (cents === null) {
    return "Not set";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

export default async function BuyersPage() {
  const [dashboard, buyerData] = await Promise.all([getDashboardData(), getBuyers()]);
  const buyers = buyerData.buyers;
  const contractLeads = dashboard.leads.filter((lead) =>
    ["under_contract", "closed"].includes(lead.stage_key),
  );
  const activeBuyers = buyers.filter((buyer) => buyer.status === "active");
  const pofReceived = buyers.filter((buyer) => buyer.proof_of_funds_status === "received");

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Buyers</p>
          <h2>Disposition workspace</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Deals needing buyers</span>
          <strong className={styles.ready}>{contractLeads.length}</strong>
        </div>
      </header>

      <section className={styles.metrics}>
        <article className={styles.metric}>
          <span>Active buyers</span>
          <strong>{activeBuyers.length}</strong>
          <small>{buyers.length} total buyer records</small>
        </article>
        <article className={styles.metric}>
          <span>POF received</span>
          <strong>{pofReceived.length}</strong>
          <small>Proof of funds ready</small>
        </article>
        <article className={styles.metric}>
          <span>Deal room</span>
          <strong>{contractLeads.length}</strong>
          <small>Under contract or closed</small>
        </article>
        <article className={styles.metric}>
          <span>Revenue</span>
          <strong>{formatMoney(dashboard.summary.collected_revenue_cents)}</strong>
          <small>Collected assignment fees</small>
        </article>
        <article className={styles.metric}>
          <span>Offers pending</span>
          <strong>{dashboard.summary.offers_pending}</strong>
          <small>Acquisition offers awaiting decision</small>
        </article>
      </section>

      <section className={styles.contentGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Deal Room Queue</h3>
            <span>{contractLeads.length} deals</span>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Property</th>
                  <th>Seller</th>
                  <th>Stage</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {contractLeads.length === 0 ? (
                  <tr>
                    <td>No contracted deals yet</td>
                    <td>Waiting</td>
                    <td>Clear</td>
                    <td>OS</td>
                  </tr>
                ) : null}
                {contractLeads.map((lead) => (
                  <tr key={lead.id}>
                    <td>
                      <Link className={styles.tableLink} href={`/os/leads/${lead.id}`}>
                        {lead.property_address}
                      </Link>
                    </td>
                    <td>{lead.seller_name}</td>
                    <td>
                      <span className={styles.leadStatus}>{labelize(lead.stage_key)}</span>
                    </td>
                    <td>{labelize(lead.source)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Add Buyer</h3>
            <span>CRM entry</span>
          </div>
          <BuyerForm />
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Buyer CRM</h3>
            <span>{buyers.length} buyers</span>
          </div>
          <div className={styles.buyerList}>
            {buyers.length === 0 ? <p>No buyers added yet.</p> : null}
            {buyers.map((buyer) => (
              <article key={buyer.id}>
                <div>
                  <strong>{buyer.name}</strong>
                  <span>{buyer.company_name ?? labelize(buyer.buyer_type)}</span>
                </div>
                <dl>
                  <div>
                    <dt>Status</dt>
                    <dd>{labelize(buyer.status)}</dd>
                  </div>
                  <div>
                    <dt>POF</dt>
                    <dd>{labelize(buyer.proof_of_funds_status)}</dd>
                  </div>
                  <div>
                    <dt>Max</dt>
                    <dd>{formatMoney(buyer.max_purchase_price_cents)}</dd>
                  </div>
                  <div>
                    <dt>Markets</dt>
                    <dd>{buyer.criteria?.markets || "Not set"}</dd>
                  </div>
                </dl>
                <small>
                  {buyer.email ?? "No email"} / {buyer.phone ?? "No phone"}
                </small>
              </article>
            ))}
          </div>
        </article>
      </section>
    </>
  );
}
