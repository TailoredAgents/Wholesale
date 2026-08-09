import { Archive, ArrowLeft } from "lucide-react";
import Link from "next/link";

import { getClosedLeads, getWorkspaceProfile } from "../../../lib/api";
import { PageHeader, WorkspacePage } from "../../_components/page-contracts";
import { formatDateTime, labelize } from "../../os-utils";
import styles from "../../page.module.css";
import { LeadReopenControl } from "../lead-lifecycle-actions";

export const dynamic = "force-dynamic";

type SearchValue = string | string[] | undefined;

function first(value: SearchValue) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function normalizePage(value: string) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function pageHref(page: number, q: string) {
  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (page > 1) query.set("page", String(page));
  const suffix = query.toString();
  return suffix ? `/os/leads/closed?${suffix}` : "/os/leads/closed";
}

function closedTime(lead: Awaited<ReturnType<typeof getClosedLeads>>["leads"][number]) {
  return lead.closed_out_at ?? lead.archived_at;
}

export default async function ClosedLeadsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, SearchValue>>;
}) {
  const params = (await searchParams) ?? {};
  const q = first(params.q).trim().slice(0, 200);
  const page = normalizePage(first(params.page));
  const pageSize = 100;
  const offset = (page - 1) * pageSize;
  const [{ leads, apiConnected }, profile] = await Promise.all([
    getClosedLeads({ limit: pageSize + 1, offset, q }),
    getWorkspaceProfile(),
  ]);
  const canEditLead = Boolean(profile?.permissions.includes("leads:edit"));
  const filteredLeads = leads.filter(
    (lead) =>
      Boolean(lead.archived_at)
      && ["dead", "disqualified"].includes(lead.stage_key)
      && Boolean(lead.close_out_disposition)
      && Boolean(lead.closed_out_at),
  ).sort((first, second) => {
    const firstTime = Date.parse(closedTime(first) ?? "") || 0;
    const secondTime = Date.parse(closedTime(second) ?? "") || 0;
    return secondTime - firstTime || first.id.localeCompare(second.id);
  });
  const hasNextPage = filteredLeads.length > pageSize;
  const closedLeads = filteredLeads.slice(0, pageSize);
  const rangeStart = closedLeads.length ? offset + 1 : 0;
  const rangeEnd = offset + closedLeads.length;
  const resultSummary = closedLeads.length
    ? hasNextPage
      ? `Showing ${rangeStart}-${rangeEnd} of at least ${rangeEnd + 1}`
      : `Showing ${rangeStart}-${rangeEnd} of ${rangeEnd}`
    : q
      ? "0 matching closed leads"
      : "0 closed leads";

  return (
    <WorkspacePage>
      <PageHeader
        actions={
          <>
            <Link href="/os/leads">
              <ArrowLeft aria-hidden="true" size={15} />
              Active leads
            </Link>
            <Link href="/os/leads/archived">
              <Archive aria-hidden="true" size={15} />
              Administrative archive
            </Link>
          </>
        }
        description="Dead and disqualified leads keep their full read-only seller, property, communication, appointment, valuation, transaction, and buyer-offer history here while routine follow-up stays stopped."
        eyebrow="Seller operations"
        meta={resultSummary}
        title="Closed Leads"
      />

      <section aria-label="Search closed leads" className={styles.closedControls}>
        <form action="/os/leads/closed" className={styles.closedSearch} method="get">
          <label htmlFor="closed-lead-search">Search closed leads</label>
          <div>
            <input
              defaultValue={q}
              id="closed-lead-search"
              maxLength={200}
              name="q"
              placeholder="Seller, address, disposition, or reason"
              type="search"
            />
            <button type="submit">Search</button>
            {q ? <Link href="/os/leads/closed">Clear</Link> : null}
          </div>
        </form>
      </section>

      <section className={styles.panel}>
        <div className={`${styles.panelHeader} ${styles.archivePanelHeader}`}>
          <div>
            <h3>Closed seller records</h3>
            <small>
              {canEditLead
                ? "Reopen a lead only when there is a real reason to resume work and a scheduled next action."
                : "Closed seller records are read only for your role."}
            </small>
          </div>
          <span>{resultSummary}</span>
        </div>
        {!apiConnected ? <p className={styles.panelMessage}>Closed leads are unavailable.</p> : null}
        <div className={`${styles.tableWrap} ${styles.archiveTable} ${styles.closedTable}`}>
          <table>
            <thead>
              <tr>
                <th>Seller</th>
                <th>Property</th>
                <th>Disposition</th>
                <th>Closed</th>
                <th>Reason</th>
                <th>Closed by</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {apiConnected && closedLeads.length === 0 ? (
                <tr>
                  <td colSpan={7}>No closed leads</td>
                </tr>
              ) : null}
              {closedLeads.map((lead) => (
                <tr key={lead.id}>
                  <td data-label="Seller">
                    <Link
                      className={styles.tableLink}
                      href={`/os/leads/${lead.id}?returnTo=${encodeURIComponent("/os/leads/closed")}`}
                    >
                      {lead.seller_name}
                    </Link>
                  </td>
                  <td data-label="Property">{lead.property_address}</td>
                  <td data-label="Disposition">
                    <span className={styles.closedDisposition}>
                      {labelize(lead.close_out_disposition ?? lead.stage_key)}
                    </span>
                  </td>
                  <td data-label="Closed">
                    <time dateTime={closedTime(lead) ?? undefined}>{formatDateTime(closedTime(lead))}</time>
                  </td>
                  <td className={styles.closedReason} data-label="Reason">
                    {lead.close_out_reason ?? "No close-out reason recorded"}
                  </td>
                  <td className={styles.closedActor} data-label="Closed by">
                    {lead.closed_out_by_user_email ?? "Unknown user"}
                  </td>
                  <td data-label="Actions">
                    <LeadReopenControl canEditLead={canEditLead} compact leadId={lead.id} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <nav aria-label="Closed leads pages" className={styles.closedPagination}>
          <span>{resultSummary}</span>
          <div>
            {page > 1 ? (
              <Link href={pageHref(page - 1, q)}>Previous</Link>
            ) : (
              <span aria-disabled="true">Previous</span>
            )}
            <strong>Page {page}</strong>
            {hasNextPage ? (
              <Link href={pageHref(page + 1, q)}>Next</Link>
            ) : (
              <span aria-disabled="true">Next</span>
            )}
          </div>
        </nav>
      </section>
    </WorkspacePage>
  );
}
