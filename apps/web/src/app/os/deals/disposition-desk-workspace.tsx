"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Plus,
  PhoneCall,
  RefreshCw,
  ShieldCheck,
  UserRound,
  UsersRound,
  WalletCards,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type {
  DispositionDeskCategory,
  DispositionDeskItem,
  DispositionDeskOverview,
  DispositionDeskScope,
} from "../../lib/api";
import { EmptyState, StatusBadge } from "../_components/design-system";
import styles from "./disposition-desk.module.css";

type DeskView = DispositionDeskCategory;

const primaryDeskViews: Array<{
  key: DeskView;
  label: string;
  description: string;
  emptyTitle: string;
  emptyMessage: string;
}> = [
  {
    key: "active_deals",
    label: "Deals to Market",
    description: "Contracted deals that are ready for investor outreach, even while packet or readiness details are still being completed.",
    emptyTitle: "No deals to market",
    emptyMessage: "New Under Contract deals will appear here automatically for investor outreach.",
  },
  {
    key: "buyer_follow_ups",
    label: "Investor Relationships",
    description: "Due follow-ups and relationship work across the buyer network.",
    emptyTitle: "No investor follow-ups waiting",
    emptyMessage: "No investor relationship follow-ups are due in this scope.",
  },
];

const secondaryDeskViews: Array<{
  key: Exclude<DeskView, "today" | "active_deals" | "buyer_follow_ups">;
  label: string;
  description: string;
  emptyTitle: string;
  emptyMessage: string;
}> = [
  {
    key: "replies",
    label: "Replies",
    description: "Buyer conversations that need a human response.",
    emptyTitle: "No buyer replies waiting",
    emptyMessage: "The buyer inbox has no unread or reply-due conversations in this scope.",
  },
  {
    key: "offers",
    label: "Offers",
    description: "Received buyer offers awaiting evidence review or selection.",
    emptyTitle: "No offers need review",
    emptyMessage: "Received offers will appear here until a human completes the review.",
  },
  {
    key: "deadlines",
    label: "Deadlines",
    description: "Contract, closing, deposit, and buyer-evidence dates that can affect execution.",
    emptyTitle: "No active deadlines",
    emptyMessage: "No incomplete disposition-related deadline is currently recorded in this scope.",
  },
];

const deskViews = [...primaryDeskViews, ...secondaryDeskViews];

const metricKeys: Record<DeskView, keyof DispositionDeskOverview["metrics"]> = {
  today: "today",
  active_deals: "active_deals",
  buyer_follow_ups: "buyer_follow_ups",
  replies: "replies",
  offers: "offers",
  deadlines: "deadlines",
};

function hrefFor(view: DeskView, scope: DispositionDeskScope, page = 1) {
  const query = new URLSearchParams({ desk: view, scope, view: "disposition" });
  if (page > 1) query.set("deskPage", String(page));
  return `/os/deals?${query.toString()}`;
}

function validView(value: string | undefined): DeskView {
  return deskViews.some((item) => item.key === value) ? value as DeskView : "active_deals";
}

function formatDue(value: string | null) {
  if (!value) return "No due date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Due date unavailable";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function dueLabel(value: string | null) {
  if (!value) return "Unscheduled";
  const due = new Date(value);
  if (Number.isNaN(due.getTime())) return "Date unavailable";
  const now = new Date();
  if (due < now) return "Overdue";
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (due < tomorrow) return "Due today";
  return "Upcoming";
}

function toneForSeverity(severity: DispositionDeskItem["severity"]) {
  if (severity === "danger") return "danger" as const;
  if (severity === "warning") return "warning" as const;
  return "info" as const;
}

function dealWorkbenchHref(caseId: string, dispositionTab: string) {
  return `/os/dispositions/${encodeURIComponent(caseId)}?tab=${encodeURIComponent(dispositionTab)}`;
}

function dispositionActionHref(item: DispositionDeskItem, href: string) {
  if (!item.disposition_case_id || !href.startsWith("/os/deals?")) return href;
  const target = new URL(href, "https://stonegate.internal");
  if (target.searchParams.get("tab") !== "disposition") return href;
  const dispositionTab = target.searchParams.get("dispositionTab") ?? "execution";
  const anchor = target.hash;
  return `${dealWorkbenchHref(item.disposition_case_id, dispositionTab)}${anchor}`;
}

function WorkItem({ item }: { item: DispositionDeskItem }) {
  const isActiveDeal = item.category === "active_deals" && Boolean(item.disposition_case_id);
  const caseWorkbench = item.category === "active_deals" && item.checklist
    ? item.checklist
    : null;
  const checklistIssues = caseWorkbench?.issues?.length
    ? caseWorkbench.issues
    : item.blocker
      ? [{ key: `${item.key}-legacy`, label: "Recorded checklist item", blocker_class: null, detail: item.blocker, href: null }]
      : [];
  const parallelActions = item.secondary_action ? [item.secondary_action] : [];
  const primaryHref = isActiveDeal && item.disposition_case_id
    ? dealWorkbenchHref(item.disposition_case_id, "execution")
    : dispositionActionHref(item, item.primary_action.href);
  return (
    <article className={styles.workCard} data-severity={item.severity}>
      <header className={styles.workHeader}>
        <div>
          <StatusBadge tone={item.needs_setup ? "warning" : toneForSeverity(item.severity)}>
            {item.needs_setup ? "Needs setup" : dueLabel(item.due_at)}
          </StatusBadge>
          <h3>{item.title}</h3>
          <p>{item.context}</p>
        </div>
        <div className={styles.owner}>
          <UserRound aria-hidden="true" size={15} />
          <span>Owner</span>
          <strong>{item.owner_name}</strong>
        </div>
      </header>

      <dl className={styles.workFacts}>
        <div>
          <dt>Due</dt>
          <dd>{item.due_at ? <time dateTime={item.due_at}>{formatDue(item.due_at)}</time> : "Not scheduled"}</dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{item.reason}</dd>
        </div>
        <div>
          <dt>Readiness</dt>
          <dd>{caseWorkbench ? `${caseWorkbench.completed_count} of ${caseWorkbench.total_count} actions complete - ${caseWorkbench.warning_count} need attention` : item.blocker ?? "No issue recorded"}</dd>
        </div>
      </dl>

      {caseWorkbench ? (
        <details className={styles.cardChecklist}>
          <summary><span>Deal details &amp; readiness</span><strong>{caseWorkbench.warning_count}</strong></summary>
          <div>
            {checklistIssues.map((issue) => (
              <article data-tone={issue.blocker_class ?? "warning"} key={issue.key}>
                <AlertTriangle aria-hidden="true" size={14} />
                <div><strong>{issue.label}</strong><span>{issue.detail}</span></div>
                {issue.href ? <Link href={issue.href}>Open<ArrowRight aria-hidden="true" size={13} /></Link> : null}
              </article>
            ))}
            {!checklistIssues.length ? <p>{caseWorkbench.warning_count ? <AlertTriangle aria-hidden="true" size={14} /> : <CheckCircle2 aria-hidden="true" size={14} />}{caseWorkbench.warning_count ? "Open the deal workspace for the current issue details; outreach remains usable." : "No open checklist issues. Outreach and the other deal tools remain available."}</p> : null}
          </div>
        </details>
      ) : null}

      {item.needs_setup ? (
        <p className={styles.setupNotice}>
          Setup is incomplete, but outreach and every other authorized disposition action remain available.
        </p>
      ) : null}

      {isActiveDeal && item.disposition_case_id ? (
        <footer className={styles.dealActions}>
          <Link className={styles.primaryAction} href={primaryHref}>
            <PhoneCall aria-hidden="true" size={16} />
            Start / continue outreach
            <ArrowRight aria-hidden="true" size={15} />
          </Link>
          <nav aria-label={`More ways to work ${item.title}`} className={styles.secondaryDealActions}>
            <Link href={dealWorkbenchHref(item.disposition_case_id, "package")}>Deal &amp; packet</Link>
            {item.asset_class !== "land" ? <Link href={dealWorkbenchHref(item.disposition_case_id, "offers")}>Offers &amp; closing</Link> : null}
          </nav>
        </footer>
      ) : (
        <footer className={styles.workActions}>
          <Link className={styles.primaryAction} href={primaryHref}>
            {item.primary_action.label}
            <ArrowRight aria-hidden="true" size={15} />
          </Link>
          {parallelActions.length ? <div className={styles.parallelActionGroup}><span>Related action</span><div>{parallelActions.slice(0, 3).map((action) => <Link className={styles.secondaryAction} href={dispositionActionHref(item, action.href)} key={`${action.href}-${action.label}`}>{action.label}</Link>)}</div></div> : null}
        </footer>
      )}
    </article>
  );
}

export function DispositionDeskWorkspace({
  apiConnected,
  data,
  errorMessage,
  initialDesk,
  initialPage = 1,
  isStale,
}: {
  apiConnected: boolean;
  data: DispositionDeskOverview | null;
  errorMessage: string | null;
  initialDesk?: string;
  initialPage?: number;
  isStale: boolean;
}) {
  const router = useRouter();
  const view = validView(initialDesk);
  const page = Math.max(1, Math.floor(initialPage));
  const [stalenessNow, setStalenessNow] = useState<number | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setStalenessNow(Date.now());
    }, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  if (!data) {
    return (
      <section className={styles.unavailable} role="alert">
        <AlertTriangle aria-hidden="true" size={28} />
        <h2>Disposition desk unavailable</h2>
        <p>{errorMessage ?? "Stonegate could not load the daily disposition read model."}</p>
        <button className={styles.retryButton} onClick={() => router.refresh()} type="button">
          <RefreshCw aria-hidden="true" size={15} />
          Retry
        </button>
      </section>
    );
  }

  const scope = data.effective_scope;
  const generatedAt = new Date(data.source_health.generated_at).getTime();
  const snapshotIsStale = isStale || (
    stalenessNow !== null
    && (Number.isNaN(generatedAt) || stalenessNow - generatedAt > 5 * 60 * 1000)
  );
  const selectedView = deskViews.find((item) => item.key === view) ?? deskViews[0];
  const items = data[view];
  const sectionState = data.sections?.[view] ?? {
    total: data.metrics[metricKeys[view]],
    returned: items.length,
    has_more: false,
    offset: 0,
  };
  const returnTo = hrefFor(view, scope, page);
  const providerTone = data.source_health.external_provider_status === "available"
    ? "success"
    : data.source_health.external_provider_status === "unavailable"
      ? "danger"
      : "warning";
  return (
    <section aria-label="Disposition desk" className={styles.workspace}>
      <header className={styles.hero}>
        <div>
          <span>Dispositions</span>
          <h2>Market deals. Build investor relationships.</h2>
          <p>Open a contracted deal, work the next investor, and pick up where you left off.</p>
        </div>
        <div className={styles.quickActions}>
          {data.can_edit_buyers ? (
            <Link className={styles.quickPrimary} href={`/os/buyers?create=1&returnTo=${encodeURIComponent(returnTo)}`}>
              <Plus aria-hidden="true" size={15} />
              Add buyer
            </Link>
          ) : null}
          <Link className={styles.quickLink} href="/os/buyers">
            <UsersRound aria-hidden="true" size={15} />
            Buyer network
          </Link>
          <Link className={styles.quickLink} href="/os/deals?view=all">
            Deal queue
          </Link>
        </div>
      </header>

      <div className={styles.controlRow}>
        <nav aria-label="Disposition ownership scope" className={styles.scopeControl}>
          <Link aria-current={scope === "mine" ? "page" : undefined} className={scope === "mine" ? styles.activeScope : styles.scopeLink} href={hrefFor(view, "mine")}>
            My work
          </Link>
          {data.can_view_team ? (
            <Link aria-current={scope === "team" ? "page" : undefined} className={scope === "team" ? styles.activeScope : styles.scopeLink} href={hrefFor(view, "team")}>
              Team
            </Link>
          ) : null}
        </nav>
        <p>
          Updated <time dateTime={data.source_health.generated_at}>{formatDue(data.source_health.generated_at)}</time>
        </p>
      </div>

      {data.scope_notice ? <div className={styles.notice} role="status">{data.scope_notice}</div> : null}

      {snapshotIsStale ? (
        <div className={styles.staleNotice} role="status">
          <div>
            <AlertTriangle aria-hidden="true" size={17} />
            <span>This desk snapshot is more than five minutes old. Refresh before acting on time-sensitive work.</span>
          </div>
          <button onClick={() => router.refresh()} type="button">
            <RefreshCw aria-hidden="true" size={15} />
            Retry
          </button>
        </div>
      ) : null}

      <nav aria-label="Disposition desk views" className={styles.viewTabs}>
        {primaryDeskViews.map((item) => (
          <Link aria-current={view === item.key ? "page" : undefined} className={view === item.key ? styles.activeView : styles.viewTab} href={hrefFor(item.key, scope)} key={item.key}>
            <span>{item.label}</span>
            <strong>{data.metrics[metricKeys[item.key]]}</strong>
          </Link>
        ))}
      </nav>

      <nav aria-label="Secondary disposition queues" className={styles.secondaryQueues}>
        <span>Also available</span>
        {secondaryDeskViews.map((item) => (
          <Link aria-current={view === item.key ? "page" : undefined} href={hrefFor(item.key, scope)} key={item.key}>
            {item.label}<strong>{data.metrics[metricKeys[item.key]]}</strong>
          </Link>
        ))}
        <Link href="/os/deals?view=disposition&desk=performance">Performance</Link>
      </nav>

      <div className={styles.dashboardGrid}>
        <section aria-label={`${selectedView.label} disposition work`} className={styles.workstream}>
          <header className={styles.sectionHeader}>
            <div>
              <span>Current queue</span>
              <h2>{selectedView.label}</h2>
              <p>{selectedView.description}</p>
            </div>
            <strong>{sectionState.total}</strong>
          </header>
          {sectionState.offset > 0 || sectionState.has_more ? (
            <div className={styles.sectionLimitNotice} role="status">
              <span>
                {sectionState.returned ? (
                  <>Showing {sectionState.offset + 1}–{sectionState.offset + sectionState.returned} of {sectionState.total} {selectedView.label.toLowerCase()} items.</>
                ) : (
                  <>No {selectedView.label.toLowerCase()} items are on this page; {sectionState.total} exist in this scope.</>
                )}
              </span>
              <div>
                {sectionState.offset > 0 ? (
                  <Link href={hrefFor(view, scope, Math.max(1, page - 1))}>Previous</Link>
                ) : null}
                {sectionState.has_more ? (
                  <Link href={hrefFor(view, scope, page + 1)}>Next <ArrowRight aria-hidden="true" size={14} /></Link>
                ) : null}
              </div>
            </div>
          ) : null}
          {items.length ? (
            <div className={styles.workList}>{items.map((item) => <WorkItem item={item} key={item.key} />)}</div>
          ) : (
            <EmptyState
              action={<Link className={styles.emptyAction} href={view === "active_deals" ? "/os/deals?view=all" : hrefFor("active_deals", scope)}>Review active deals</Link>}
              icon={<CheckCircle2 aria-hidden="true" size={24} />}
              message={selectedView.emptyMessage}
              title={selectedView.emptyTitle}
            />
          )}
        </section>

      </div>

      <details className={styles.deskDetails}>
        <summary>
          <span><ChevronDown aria-hidden="true" size={16} />Desk status &amp; readiness</span>
          <small>Data health, buyer network health, and deal coverage</small>
        </summary>
        <div className={styles.deskDetailsBody}>
          <section aria-label="Disposition data health" className={styles.healthBanner}>
            <div>
              <CheckCircle2 aria-hidden="true" size={18} />
              <span>Stonegate records</span>
              <strong>{apiConnected && data.source_health.canonical_data_status === "current" && !snapshotIsStale ? "Current" : "Needs review"}</strong>
            </div>
            <div>
              <ShieldCheck aria-hidden="true" size={18} />
              <span>External discovery</span>
              <StatusBadge tone={providerTone}>{data.source_health.external_provider_status.replaceAll("_", " ")}</StatusBadge>
            </div>
            <p>{data.source_health.message}</p>
          </section>

          <aside className={styles.sideRail}>
            <section className={styles.networkPanel}>
              <header>
                <div>
                  <span>Owned relationships</span>
                  <h2>Buyer network health</h2>
                </div>
                <WalletCards aria-hidden="true" size={20} />
              </header>
              <dl>
                <div><dt>Total buyers</dt><dd>{data.buyer_network.total}</dd></div>
                <div><dt>Active</dt><dd>{data.buyer_network.active}</dd></div>
                <div><dt>Needs review</dt><dd>{data.buyer_network.needs_review}</dd></div>
                <div><dt>Missing proof</dt><dd>{data.buyer_network.missing_proof}</dd></div>
                <div><dt>Proof expiring</dt><dd>{data.buyer_network.expiring_proof}</dd></div>
                <div><dt>Missing criteria</dt><dd>{data.buyer_network.missing_criteria}</dd></div>
                <div><dt>Unassigned</dt><dd>{data.buyer_network.unassigned}</dd></div>
              </dl>
              <Link href="/os/buyers">Review buyer network <ArrowRight aria-hidden="true" size={14} /></Link>
            </section>

            <section className={styles.coveragePanel}>
              <header>
                <div>
                  <span>Deal readiness</span>
                  <h2>Coverage warnings</h2>
                </div>
                <AlertTriangle aria-hidden="true" size={20} />
              </header>
              {data.coverage_warnings.length ? (
                <div className={styles.coverageList}>
                  {data.coverage_warnings.slice(0, 5).map((warning) => (
                    <article key={warning.key}>
                      <div>
                        <strong>{warning.title}</strong>
                        <span>{warning.blocker ?? warning.reason}</span>
                      </div>
                      <Link aria-label={`Open ${warning.title}`} href={warning.primary_action.href}><ArrowRight aria-hidden="true" size={15} /></Link>
                    </article>
                  ))}
                </div>
              ) : (
                <p className={styles.clearCoverage}><CheckCircle2 aria-hidden="true" size={16} /> No weak buyer-coverage warnings.</p>
              )}
              {data.coverage_warnings.length > 5 ? (
                <Link href={hrefFor("active_deals", scope)}>
                  Showing 5 of {data.sections.coverage_warnings.total}; open active deals
                </Link>
              ) : null}
            </section>

          </aside>
        </div>
      </details>
    </section>
  );
}
