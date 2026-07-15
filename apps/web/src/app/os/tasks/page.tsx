import Link from "next/link";

import { CompleteTaskButton } from "../../complete-task-button";
import { getDashboardData } from "../../lib/api";
import { formatDateTime, labelize } from "../os-utils";
import styles from "../page.module.css";

export const dynamic = "force-dynamic";

export default async function TasksPage() {
  const dashboard = await getDashboardData();
  const openTasks = dashboard.openTaskQueue;
  const overdueTasks = openTasks.filter((task) => task.due_status === "overdue");
  const dueTasks = openTasks.filter((task) => task.due_status === "due");
  const upcomingTasks = openTasks.filter((task) => task.due_status === "unscheduled");

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Work queue</p>
          <h2>Open acquisition tasks</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Open tasks</span>
          <strong className={overdueTasks.length > 0 ? styles.warning : styles.ready}>
            {openTasks.length} total / {overdueTasks.length} overdue
          </strong>
        </div>
      </header>

      <section className={styles.metrics} aria-label="Task queue metrics">
        <article className={styles.metric}>
          <span>Overdue</span>
          <strong>{overdueTasks.length}</strong>
          <small>Needs attention now</small>
        </article>
        <article className={styles.metric}>
          <span>Due</span>
          <strong>{dueTasks.length}</strong>
          <small>Scheduled follow-up</small>
        </article>
        <article className={styles.metric}>
          <span>Unscheduled</span>
          <strong>{upcomingTasks.length}</strong>
          <small>Needs a due date</small>
        </article>
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <h3>All Open Tasks</h3>
          <span>{openTasks.length} active</span>
        </div>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Seller</th>
                <th>Stage</th>
                <th>Due</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {openTasks.length === 0 ? (
                <tr>
                  <td>No open tasks</td>
                  <td>Clear</td>
                  <td>Clear</td>
                  <td>Clear</td>
                  <td>Ready</td>
                  <td></td>
                </tr>
              ) : null}
              {openTasks.map((task) => (
                <tr key={task.task_id}>
                  <td>
                    <strong>{task.title}</strong>
                    <small className={styles.tableSubtext}>{labelize(task.task_type)}</small>
                  </td>
                  <td>
                    <Link className={styles.tableLink} href={`/leads/${task.lead_id}`}>
                      {task.seller_name}
                    </Link>
                    <small className={styles.tableSubtext}>{task.property_address}</small>
                  </td>
                  <td>{labelize(task.stage_key)}</td>
                  <td>{formatDateTime(task.due_at)}</td>
                  <td>
                    <span className={styles[task.due_status]}>{labelize(task.due_status)}</span>
                  </td>
                  <td>
                    <CompleteTaskButton taskId={task.task_id} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
