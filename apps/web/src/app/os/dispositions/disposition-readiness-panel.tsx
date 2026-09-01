"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  RefreshCw,
  ShieldAlert,
  UserRound,
} from "lucide-react";

import type {
  DispositionCaseReadiness,
  DispositionReadinessAction,
  DispositionReadinessBlockerClass,
  DispositionReadinessCheck,
} from "../../lib/api";
import styles from "./disposition-readiness-panel.module.css";

export type DispositionReadinessTarget = {
  tab: string | null;
  anchor: string | null;
  href: string | null;
};

function actionTarget(action: DispositionReadinessAction): DispositionReadinessTarget {
  return {
    tab: action.target_tab,
    anchor: action.target_anchor,
    href: action.href,
  };
}

function blockerLabel(blockerClass: DispositionReadinessBlockerClass | null) {
  if (blockerClass === "hard_stop") return "Concrete requirement";
  if (blockerClass === "release_gate") return "Release attention";
  if (blockerClass === "warning") return "Warning";
  return "Checklist";
}

function ActionStatus({ action }: { action: DispositionReadinessAction }) {
  if (action.state === "complete") {
    return <span className={styles.actionStatus} data-tone="complete"><CheckCircle2 aria-hidden="true" size={13} />Complete</span>;
  }
  if (action.blocker_class === "hard_stop") {
    return <span className={styles.actionStatus} data-tone="hard"><ShieldAlert aria-hidden="true" size={13} />Requirement missing</span>;
  }
  if (action.state === "blocked" || action.blocker_class) {
    return <span className={styles.actionStatus} data-tone="warning"><AlertTriangle aria-hidden="true" size={13} />Attention</span>;
  }
  return <span className={styles.actionStatus} data-tone="available"><ArrowRight aria-hidden="true" size={13} />Available</span>;
}

function CheckRow({
  check,
  onNavigate,
}: {
  check: DispositionReadinessCheck;
  onNavigate: (target: DispositionReadinessTarget) => void;
}) {
  const resolved = check.status === "ready" || check.status === "complete";
  return (
    <li data-state={resolved ? "complete" : check.blocker_class ?? "warning"}>
      {resolved
        ? <CheckCircle2 aria-hidden="true" size={15} />
        : check.blocker_class === "hard_stop"
          ? <ShieldAlert aria-hidden="true" size={15} />
          : <AlertTriangle aria-hidden="true" size={15} />}
      <div>
        <strong>{check.label}</strong>
        <span>{check.detail}</span>
        {!resolved ? <small>{blockerLabel(check.blocker_class)} · Advisory checklist item</small> : null}
      </div>
      {check.remediation ? (
        <button
          onClick={() => onNavigate({
            tab: check.remediation?.tab ?? null,
            anchor: check.remediation?.anchor ?? null,
            href: check.remediation?.href ?? null,
          })}
          type="button"
        >
          {check.remediation.label}<ArrowRight aria-hidden="true" size={13} />
        </button>
      ) : null}
    </li>
  );
}

export function DispositionReadinessPanel({
  error,
  loading,
  onNavigate,
  onRetry,
  readiness,
}: {
  error: string | null;
  loading: boolean;
  onNavigate: (target: DispositionReadinessTarget) => void;
  onRetry: () => void;
  readiness: DispositionCaseReadiness | null;
}) {
  if (loading && !readiness) {
    return (
      <section aria-busy="true" aria-live="polite" className={styles.loading} role="status">
        <RefreshCw aria-hidden="true" className={styles.spin} size={16} />
        Loading deal readiness checklist
      </section>
    );
  }

  if (!readiness) {
    return (
      <section className={styles.loadError} role="status">
        <ShieldAlert aria-hidden="true" size={18} />
        <div><strong>Readiness checklist unavailable</strong><span>{error ?? "The deal workspace remains available."}</span></div>
        <button onClick={onRetry} type="button"><RefreshCw aria-hidden="true" size={14} />Retry</button>
      </section>
    );
  }

  const actionsByKey = new Map(readiness.actions.map((action) => [action.key, action]));
  const bestAction = readiness.best_action_key
    ? actionsByKey.get(readiness.best_action_key) ?? null
    : null;
  const parallelActions = readiness.parallel_action_keys
    .map((key) => actionsByKey.get(key))
    .filter((action): action is DispositionReadinessAction => Boolean(action))
    .slice(0, 3);
  const applicableActions = readiness.actions.filter((action) => action.state !== "not_applicable");
  const progress = readiness.total_count > 0
    ? Math.round((readiness.completed_count / readiness.total_count) * 100)
    : 100;

  return (
    <section aria-labelledby="disposition-readiness-heading" className={styles.panel}>
      <header className={styles.header}>
        <div>
          <span><ClipboardCheck aria-hidden="true" size={15} />Advisory workbench</span>
          <h4 id="disposition-readiness-heading">Deal readiness and available work</h4>
          <p>The checklist keeps risks visible. It never forces a tab order or disables an otherwise applicable workflow action.</p>
        </div>
        <div className={styles.progress}>
          <strong>{readiness.completed_count} of {readiness.total_count}</strong>
          <span>actions complete · {progress}%</span>
          <small>{readiness.warning_count} item{readiness.warning_count === 1 ? "" : "s"} need attention</small>
        </div>
      </header>

      {error ? <p className={styles.refreshWarning} role="status"><AlertTriangle aria-hidden="true" size={14} />{error} Showing the last checklist for this deal.<button onClick={onRetry} type="button">Retry</button></p> : null}

      <div className={styles.actionSummary}>
        <div className={styles.bestAction}>
          <span>Suggested action (optional)</span>
          {bestAction ? (
            <>
              <strong>{bestAction.label}</strong>
              <p>{bestAction.detail}</p>
              <ActionStatus action={bestAction} />
              <button onClick={() => onNavigate(actionTarget(bestAction))} type="button">Open action<ArrowRight aria-hidden="true" size={14} /></button>
            </>
          ) : (
            <><strong>Choose the work that moves this deal</strong><p>No single next action is required. Every applicable tab remains available.</p></>
          )}
        </div>

        <div className={styles.parallelActions}>
          <span>Also available now</span>
          {parallelActions.length ? parallelActions.map((action) => (
            <button key={action.key} onClick={() => onNavigate(actionTarget(action))} type="button">
              <span><strong>{action.label}</strong><small>{action.detail}</small></span>
              <ArrowRight aria-hidden="true" size={14} />
            </button>
          )) : <p>Open any applicable tab below to continue working.</p>}
        </div>
      </div>

      <details className={styles.checklist} open>
        <summary>
          <span>All action-specific checks</span>
          <strong>{readiness.warning_count} attention · {readiness.completed_count} complete</strong>
        </summary>
        <div>
          {applicableActions.map((action) => {
            const checks = action.checks.filter((check) => check.status !== "not_applicable");
            return (
              <section aria-labelledby={`readiness-action-${action.key}`} key={action.key}>
                <header>
                  <div><h5 id={`readiness-action-${action.key}`}>{action.label}</h5><p>{action.detail}</p></div>
                  <ActionStatus action={action} />
                </header>
                {checks.length ? <ul>{checks.map((check) => <CheckRow check={check} key={check.key} onNavigate={onNavigate} />)}</ul> : <p className={styles.noChecks}>No additional checks for this action.</p>}
                <button className={styles.openAction} onClick={() => onNavigate(actionTarget(action))} type="button">Open {action.label}<ArrowRight aria-hidden="true" size={13} /></button>
              </section>
            );
          })}
        </div>
      </details>

      <footer className={styles.footer}>
        {readiness.owner ? <span><UserRound aria-hidden="true" size={13} />Owner: {readiness.owner.label}</span> : <span>Owner not assigned</span>}
        <span>Updated <time dateTime={readiness.generated_at}>{new Date(readiness.generated_at).toLocaleString()}</time></span>
        {loading ? <span aria-live="polite"><RefreshCw aria-hidden="true" className={styles.spin} size={12} />Refreshing</span> : null}
      </footer>
    </section>
  );
}
