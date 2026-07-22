import type { ReactNode } from "react";

import { AuthControls } from "./auth-controls";
import { OsNav } from "./os-nav";
import styles from "./page.module.css";
import theme from "./os-theme.module.css";

export const metadata = {
  title: "Stonegate Operating System",
  description: "Internal acquisitions workspace for Stonegate Home Buyers.",
};

export default function OsLayout({ children }: { children: ReactNode }) {
  return (
    <main className={`${theme.theme} ${styles.shell}`}>
      <aside className={styles.sidebar} aria-label="Primary navigation">
        <div className={styles.brandBlock}>
          <span className={styles.brandMark} aria-hidden="true" />
          <div className={styles.brandCopy}>
            <p className={styles.eyebrow}>Stonegate Home Buyers</p>
            <h1>Operating System</h1>
            <span>Acquisitions, finance, buyers, marketing, and AI control.</span>
          </div>
        </div>
        <OsNav />
        <div className={styles.sidebarStatus} aria-label="Workspace status">
          <span>System mode</span>
          <strong>Command workspace</strong>
        </div>
        <AuthControls />
      </aside>

      <section className={styles.workspace}>{children}</section>
    </main>
  );
}
