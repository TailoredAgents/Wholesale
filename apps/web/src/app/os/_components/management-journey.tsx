import Link from "next/link";

import { getWorkspaceProfile } from "../../lib/api";
import { canSeeNavItem, osNavGroups } from "../os-navigation";
import styles from "./management-journey.module.css";

const routeByKey = {
  finance: "/os/finance",
  marketing: "/os/marketing",
  "operating-model": "/os/operating-model",
  ai: "/os/ai",
} as const;

export type ManagementRouteKey = keyof typeof routeByKey;

export async function ManagementJourney({ active }: { active: ManagementRouteKey }) {
  const profile = await getWorkspaceProfile();
  const managementItems = osNavGroups
    .filter((group) => ["Business", "Control"].includes(group.label))
    .flatMap((group) => group.items);
  const visibleItems = profile
    ? managementItems.filter((item) => canSeeNavItem(profile, item))
    : process.env.NODE_ENV === "development"
      ? managementItems
      : managementItems.filter((item) => item.href === routeByKey[active]);

  return (
    <nav aria-label="Business and control workspaces" className={styles.journey}>
      {visibleItems.map((item) => {
        const Icon = item.icon;
        const isActive = item.href === routeByKey[active];
        return (
          <Link aria-current={isActive ? "page" : undefined} className={isActive ? styles.active : undefined} href={item.href} key={item.href}>
            <Icon aria-hidden="true" size={15} />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
