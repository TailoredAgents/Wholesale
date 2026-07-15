import type { ReactNode } from "react";

import { AuthControls } from "./auth-controls";
import { OsNav } from "./os-nav";
import styles from "./page.module.css";

export const metadata = {
  title: "Oakwell Operating System",
  description: "Internal acquisitions workspace for Oakwell Home Buyers.",
};

export default function OsLayout({ children }: { children: ReactNode }) {
  return (
    <main className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Primary navigation">
        <div>
          <p className={styles.eyebrow}>Oakwell Home Buyers</p>
          <h1>Operating System</h1>
        </div>
        <OsNav />
        <AuthControls />
      </aside>

      <section className={styles.workspace}>{children}</section>
    </main>
  );
}
