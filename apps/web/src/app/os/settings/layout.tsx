import type { ReactNode } from "react";

import { getWorkspaceProfile } from "../../lib/api";
import { SettingsNavigation } from "./settings-navigation";
import { visibleSettingsSections } from "./settings-sections";
import styles from "./settings.module.css";

export default async function SettingsLayout({ children }: { children: ReactNode }) {
  const profile = await getWorkspaceProfile();
  const sections = visibleSettingsSections(profile);

  return (
    <div className={styles.shell}>
      <SettingsNavigation sections={sections} />
      <main className={styles.content}>{children}</main>
    </div>
  );
}
