import styles from "./marin-calls.module.css";

export default function LoadingMarinCalls() {
  return (
    <div className={styles.loadingPage} aria-label="Loading Marin calls">
      <div className={styles.loadingHeader} />
      <div className={styles.loadingStats} />
      <div className={styles.loadingWorkspace} />
    </div>
  );
}
