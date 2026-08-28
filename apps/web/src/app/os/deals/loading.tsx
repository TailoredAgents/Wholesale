import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { StatusBadge } from "../_components/design-system";
import styles from "./deals.module.css";

export default function DealsLoading() {
  return (
    <WorkspacePage>
      <PageHeader
        description="Preparing contract, closing, buyer-placement, and financial work."
        eyebrow="Operations / contract to funding"
        meta={<StatusBadge tone="info">Loading deal data</StatusBadge>}
        title="Deals"
      />
      <section
        aria-busy="true"
        aria-live="polite"
        className={styles.loadingState}
        role="status"
      >
        <p>Loading deals and disposition work queues.</p>
        <div aria-hidden="true" className={styles.loadingMetrics}>
          {Array.from({ length: 5 }, (_, index) => <span key={index} />)}
        </div>
        <div aria-hidden="true" className={styles.loadingQueue}>
          {Array.from({ length: 4 }, (_, index) => <span key={index} />)}
        </div>
      </section>
    </WorkspacePage>
  );
}
