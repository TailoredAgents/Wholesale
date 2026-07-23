import Link from "next/link";

import { getWorkspaceProfile } from "../../lib/api";
import { canSeeNavItem, osNavGroups } from "../os-navigation";
import styles from "./deal-journey.module.css";

const routeByKey = {
  underwriting: "/os/underwriting",
  approvals: "/os/approvals",
  transactions: "/os/transactions",
  dispositions: "/os/dispositions",
  buyers: "/os/buyers",
} as const;

export type DealRouteKey = keyof typeof routeByKey;

export async function DealJourney({ active }: { active: DealRouteKey }) {
  const profile = await getWorkspaceProfile();
  const dealItems = osNavGroups.find((group) => group.label === "Deal Flow")?.items ?? [];
  const visibleItems = profile
    ? dealItems.filter((item) => canSeeNavItem(profile, item))
    : process.env.NODE_ENV === "development"
      ? dealItems
      : dealItems.filter((item) => item.href === routeByKey[active]);

  return (
    <nav aria-label="Deal execution workspaces" className={styles.journey}>
      {visibleItems.map((item, index) => {
        const Icon = item.icon;
        const isActive = item.href === routeByKey[active];
        return (
          <Link
            aria-current={isActive ? "step" : undefined}
            className={isActive ? styles.active : undefined}
            href={item.href}
            key={item.href}
          >
            <span className={styles.step}>{index + 1}</span>
            <Icon aria-hidden="true" size={15} />
            <span className={styles.label}>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
