import type { ReactNode } from "react";

import styles from "./page-contracts.module.css";

function classes(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function WorkspacePage({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={classes(styles.workspacePage, className)}>{children}</div>;
}

export function PageHeader({
  actions,
  description,
  eyebrow,
  meta,
  title,
}: {
  actions?: ReactNode;
  description?: string;
  eyebrow?: string;
  meta?: ReactNode;
  title: string;
}) {
  return (
    <header className={styles.pageHeader}>
      <div className={styles.pageHeaderCopy}>
        {eyebrow ? <p>{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <span>{description}</span> : null}
      </div>
      {meta || actions ? (
        <div className={styles.pageHeaderRight}>
          {meta ? <div className={styles.headerMeta}>{meta}</div> : null}
          {actions ? <div className={styles.headerActions}>{actions}</div> : null}
        </div>
      ) : null}
    </header>
  );
}

export function SectionPanel({
  actions,
  children,
  description,
  eyebrow,
  title,
}: {
  actions?: ReactNode;
  children: ReactNode;
  description?: string;
  eyebrow?: string;
  title: string;
}) {
  return (
    <section className={styles.sectionPanel}>
      <header className={styles.sectionHeader}>
        <div>
          {eyebrow ? <p>{eyebrow}</p> : null}
          <h2>{title}</h2>
          {description ? <span>{description}</span> : null}
        </div>
        {actions ? <div className={styles.sectionActions}>{actions}</div> : null}
      </header>
      <div className={styles.sectionBody}>{children}</div>
    </section>
  );
}

export function RecordSummaryHeader({
  actions,
  eyebrow,
  facts,
  subtitle,
  title,
}: {
  actions?: ReactNode;
  eyebrow?: string;
  facts: Array<{ label: string; value: ReactNode }>;
  subtitle?: string;
  title: string;
}) {
  return (
    <section className={styles.recordSummary}>
      <div className={styles.recordIdentity}>
        {eyebrow ? <p>{eyebrow}</p> : null}
        <h1>{title}</h1>
        {subtitle ? <span>{subtitle}</span> : null}
      </div>
      <dl className={styles.recordFacts}>
        {facts.map((fact) => (
          <div key={fact.label}>
            <dt>{fact.label}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
      {actions ? <div className={styles.recordActions}>{actions}</div> : null}
    </section>
  );
}

export function StickyActionBar({
  actions,
  children,
}: {
  actions: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={styles.stickyActionBar}>
      <div>{children}</div>
      <div className={styles.stickyActions}>{actions}</div>
    </div>
  );
}

export function QueuePageContract({
  context,
  detail,
  queue,
  toolbar,
}: {
  context?: ReactNode;
  detail: ReactNode;
  queue: ReactNode;
  toolbar?: ReactNode;
}) {
  return (
    <div className={styles.contractFrame}>
      {toolbar ? <div className={styles.contractToolbar}>{toolbar}</div> : null}
      <div className={classes(styles.queueContract, !context && styles.queueContractCompact)}>
        <aside aria-label="Queue">{queue}</aside>
        <main>{detail}</main>
        {context ? <aside aria-label="Context">{context}</aside> : null}
      </div>
    </div>
  );
}

export function RecordPageContract({
  aside,
  children,
  navigation,
}: {
  aside?: ReactNode;
  children: ReactNode;
  navigation?: ReactNode;
}) {
  return (
    <div className={styles.contractFrame}>
      {navigation ? <div className={styles.contractToolbar}>{navigation}</div> : null}
      <div className={classes(styles.recordContract, !aside && styles.recordContractFull)}>
        <main>{children}</main>
        {aside ? <aside aria-label="Record context">{aside}</aside> : null}
      </div>
    </div>
  );
}

export function PipelinePageContract({ children, toolbar }: { children: ReactNode; toolbar?: ReactNode }) {
  return (
    <div className={styles.contractFrame}>
      {toolbar ? <div className={styles.contractToolbar}>{toolbar}</div> : null}
      <div className={styles.pipelineContract}>{children}</div>
    </div>
  );
}

export function CalendarPageContract({
  calendar,
  sidebar,
  toolbar,
}: {
  calendar: ReactNode;
  sidebar: ReactNode;
  toolbar?: ReactNode;
}) {
  return (
    <div className={styles.contractFrame}>
      {toolbar ? <div className={styles.contractToolbar}>{toolbar}</div> : null}
      <div className={styles.calendarContract}>
        <aside aria-label="Calendar filters">{sidebar}</aside>
        <main>{calendar}</main>
      </div>
    </div>
  );
}

export function ManagementPageContract({
  children,
  navigation,
}: {
  children: ReactNode;
  navigation: ReactNode;
}) {
  return (
    <div className={styles.managementContract}>
      <aside aria-label="Management sections">{navigation}</aside>
      <main>{children}</main>
    </div>
  );
}
