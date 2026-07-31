import { ChartNoAxesCombined, ContactRound, List, Route } from "lucide-react";
import Link from "next/link";

import styles from "./seller-leads-nav.module.css";

export type SellerLeadsView = "database" | "queue" | "underwriting";

const views = [
  { href: "/os/leads?view=queue", key: "queue", label: "Lead Queue", icon: ContactRound },
  { href: "/os/leads", key: "database", label: "All Leads", icon: List },
  { href: "/os/leads?display=board", key: "pipeline", label: "Pipeline", icon: Route },
  {
    href: "/os/leads?view=underwriting",
    key: "underwriting",
    label: "Underwriting",
    icon: ChartNoAxesCombined,
  },
] as const;

export function SellerLeadsNav({
  active,
  display,
}: {
  active: SellerLeadsView;
  display: "table" | "board";
}) {
  return (
    <nav aria-label="Seller lead views" className={styles.nav}>
      {views.map((item) => {
        const isActive =
          item.key === active ||
          (item.key === "pipeline" && active === "database" && display === "board") ||
          (item.key === "database" && active === "database" && display === "table");
        const Icon = item.icon;
        return (
          <Link
            aria-current={isActive ? "page" : undefined}
            className={isActive ? styles.active : undefined}
            href={item.href}
            key={item.key}
          >
            <Icon aria-hidden="true" size={15} />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
