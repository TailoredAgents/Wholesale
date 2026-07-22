import { getTransactionOverview } from "../../lib/api";
import styles from "../page.module.css";
import { TransactionWorkspace } from "./transaction-workspace";

export const dynamic = "force-dynamic";

export default async function TransactionsPage({
  searchParams,
}: {
  searchParams: Promise<{ transaction?: string }>;
}) {
  const [{ transactions, apiConnected }, params] = await Promise.all([
    getTransactionOverview(),
    searchParams,
  ]);
  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Contract to funding</p>
          <h2>Transaction Coordination</h2>
        </div>
        <div className={styles.statusGroup}>
          <span>Closing control</span>
          <strong className={apiConnected ? styles.ready : styles.warning}>
            {apiConnected ? "Queue current" : "API unavailable"}
          </strong>
        </div>
      </header>
      {transactions ? (
        <TransactionWorkspace initialData={transactions} initialTransactionId={params.transaction} />
      ) : (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <h3>Transaction workspace unavailable</h3>
            <span>A deal-access role is required.</span>
          </div>
        </section>
      )}
    </>
  );
}
