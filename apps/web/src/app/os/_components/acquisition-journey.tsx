import Link from "next/link";

import { getWorkspaceProfile } from "../../lib/api";
import { canSeeNavItem, osNavGroups } from "../os-navigation";
import styles from "./acquisition-journey.module.css";

const routeByKey = {
  operations: "/os/operations",
  campaigns: "/os/campaigns",
  prospecting: "/os/prospecting",
  "lead-manager": "/os/lead-manager",
  leads: "/os/leads",
  pipeline: "/os/pipeline",
  "field-operations": "/os/field-operations",
} as const;

export type AcquisitionRouteKey = keyof typeof routeByKey;

export async function AcquisitionJourney({ active }: { active: AcquisitionRouteKey }) {
  const profile = await getWorkspaceProfile();
  const acquisitionItems = osNavGroups.find((group) => group.label === "Acquisitions")?.items ?? [];
  const visibleItems = profile
    ? acquisitionItems.filter((item) => canSeeNavItem(profile, item))
    : process.env.NODE_ENV === "development"
      ? acquisitionItems
      : acquisitionItems.filter((item) => item.href === routeByKey[active]);

  return (
    <nav aria-label="Seller acquisition workspaces" className={styles.journey}>
      {visibleItems.map((item) => {
        const Icon = item.icon;
        const isActive = item.href === routeByKey[active];
        return (
          <Link
            aria-current={isActive ? "page" : undefined}
            className={isActive ? styles.active : undefined}
            href={item.href}
            key={item.href}
          >
            <Icon aria-hidden="true" size={15} />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
