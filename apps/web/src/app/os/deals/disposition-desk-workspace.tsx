"use client";

import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Inbox,
  MessageSquareReply,
  Plus,
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

const deskViews: Array<{
  key: DeskView;
  label: string;
  description: string;
  emptyTitle: string;
  emptyMessage: string;
}> = [
  {
    key: "today",
    label: "Today",
    description: "A recommended starting point for due and high-attention work; other deal work remains available.",
    emptyTitle: "Today is clear",
    emptyMessage: "No disposition work is due today. Review active deals or buyer coverage next.",
  },
  {
    key: "active_deals",
    label: "Active Deals",
    description: "Every open buyer-placement case and its next controlled action.",
    emptyTitle: "No active disposition deals",
    emptyMessage: "Open a disposition case from an executed deal when buyer placement is ready.",
  },
  {
    key: "buyer_follow_ups",
    label: "Buyer Follow-ups",
    description: "Scheduled relationship work tied to a buyer and an active deal.",
    emptyTitle: "No buyer follow-ups waiting",
    emptyMessage: "Schedule the next buyer touch from the Deal record after a real conversation.",
  },
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
  return deskViews.some((item) => item.key === value) ? value as DeskView : "today";
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

function dealWorkbenchHref(dealId: string, dispositionTab: string) {
  const query = new URLSearchParams({
    deal: dealId,
    display: "queue",
    dispositionTab,
    tab: "disposition",
    view: "all",
  });
  return `/os/deals?${query.toString()}`;
}

function directDealActions(item: DispositionDeskItem) {
  if (!item.deal_id || !item.disposition_case_id) return [];
  const actions = [
    { label: "Packet", href: dealWorkbenchHref(item.deal_id, "package") },
    { label: "Find buyers", href: dealWorkbenchHref(item.deal_id, "buyers") },
  ];
  if (item.asset_class !== "land") {
    actions.push(
      { label: "Reach out", href: dealWorkbenchHref(item.deal_id, "execution") },
      { label: "Offers", href: dealWorkbenchHref(item.deal_id, "offers") },
    );
  }
  return actions;
}

function WorkItem({ item }: { item: DispositionDeskItem }) {
  const caseWorkbench = item.category === "active_deals" && item.checklist
    ? item.checklist
    : null;
  const checklistIssues = caseWorkbench?.issues?.length
    ? caseWorkbench.issues
    : item.blocker
      ? [{ key: `${item.key}-legacy`, label: "Recorded checklist item", blocker_class: null, detail: item.blocker, href: null }]
      : [];
  const parallelActions = caseWorkbench?.parallel_actions?.length
    ? caseWorkbench.parallel_actions
    : item.secondary_action
      ? [item.secondary_action]
      : [];
  const workbenchActions = caseWorkbench ? directDealActions(item) : [];
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
          <dt>Checklist</dt>
          <dd>{caseWorkbench ? `${caseWorkbench.completed_count} of ${caseWorkbench.total_count} actions complete - ${caseWorkbench.warning_count} need attention` : item.blocker ?? "No issue recorded"}</dd>
        </div>
      </dl>

      {caseWorkbench ? (
        <details className={styles.cardChecklist}>
          <summary><span>All checklist issues</span><strong>{caseWorkbench.warning_count}</strong></summary>
          <div>
            {checklistIssues.map((issue) => (
              <article data-tone={issue.blocker_class ?? "warning"} key={issue.key}>
                <AlertTriangle aria-hidden="true" size={14} />
                <div><strong>{issue.label}</strong><span>{issue.detail}</span></div>
                {issue.href ? <Link href={issue.href}>Open<ArrowRight aria-hidden="true" size={13} /></Link> : null}
              </article>
            ))}
            {!checklistIssues.length ? <p>{caseWorkbench.warning_count ? <AlertTriangle aria-hidden="true" size={14} /> : <CheckCircle2 aria-hidden="true" size={14} />}{caseWorkbench.warning_count ? "Open the deal workbench for the current issue details; other available actions remain usable." : "No open checklist issues. You can still choose any available parallel action."}</p> : null}
          </div>
        </details>
      ) : null}

      {item.needs_setup ? (
        <p className={styles.setupNotice}>
          The executed transaction is safely recorded and visible here. Complete the listed setup
          item when practical; it is advisory guidance, not a required first step. Use any
          disposition actions available on this card while setup remains incomplete.
        </p>
      ) : null}

      {workbenchActions.length ? (
        <nav aria-label={`Work ${item.title}`} className={styles.directActions}>
          <span>Work this deal</span>
          <div>
            {workbenchActions.map((action) => (
              <Link href={action.href} key={action.label}>{action.label}</Link>
            ))}
          </div>
        </nav>
      ) : null}

      <footer className={styles.workActions}>
        <div className={styles.bestActionGroup}>
          {caseWorkbench ? <span>Suggested action (optional)</span> : null}
          <Link className={styles.primaryAction} href={caseWorkbench?.best_action_href ?? item.primary_action.href}>
            {caseWorkbench?.best_action_label ?? item.primary_action.label}
            <ArrowRight aria-hidden="true" size={15} />
          </Link>
        </div>
        {parallelActions.length ? <div className={styles.parallelActionGroup}><span>{caseWorkbench ? "Also available now" : "Related action"}</span><div>{parallelActions.slice(0, 3).map((action) => <Link className={styles.secondaryAction} href={action.href} key={`${action.href}-${action.label}`}>{action.label}</Link>)}</div></div> : null}
        {caseWorkbench && caseWorkbench.parallel_action_keys.length > parallelActions.length ? <small className={styles.moreActions}>{caseWorkbench.parallel_action_keys.length - parallelActions.length} more available action{caseWorkbench.parallel_action_keys.length - parallelActions.length === 1 ? "" : "s"} are shown inside the deal workbench.</small> : null}
      </footer>
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
          <span>Buyer placement command center</span>
          <h2>Disposition desk</h2>
          <p>{data.scope_label} | {data.scope_member_count} owner{data.scope_member_count === 1 ? "" : "s"} represented</p>
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

      <nav aria-label="Disposition desk views" className={styles.viewTabs}>
        {deskViews.map((item) => (
          <Link aria-current={view === item.key ? "page" : undefined} className={view === item.key ? styles.activeView : styles.viewTab} href={hrefFor(item.key, scope)} key={item.key}>
            <span>{item.label}</span>
            <strong>{data.metrics[metricKeys[item.key]]}</strong>
          </Link>
        ))}
        <Link className={styles.viewTab} href="/os/deals?view=disposition&desk=performance">
          <span>Performance</span>
          <strong>View</strong>
        </Link>
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

          <section className={styles.legendPanel}>
            <h2>What gets prioritized</h2>
            <p><Clock3 aria-hidden="true" size={15} /> Due and overdue work</p>
            <p><MessageSquareReply aria-hidden="true" size={15} /> Buyer replies and received offers</p>
            <p><CalendarClock aria-hidden="true" size={15} /> Contract and closing deadlines</p>
            <p><Inbox aria-hidden="true" size={15} /> Recorded next actions, not duplicate tasks</p>
          </section>
        </aside>
      </div>
    </section>
  );
}
