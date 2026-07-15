"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "./page.module.css";

const navItems = [
  { href: "/os", label: "Dashboard" },
  { href: "/os/tasks", label: "Work Queue" },
  { href: "/os/pipeline", label: "Pipeline" },
  { href: "/os/leads", label: "Leads" },
  { href: "/os/underwriting", label: "Underwriting" },
  { href: "/os/approvals", label: "Approvals" },
  { href: "/os/buyers", label: "Buyers" },
  { href: "/os/finance", label: "Finance" },
  { href: "/os/marketing", label: "Marketing" },
  { href: "/os/ai", label: "AI Control" },
];

export function OsNav() {
  const pathname = usePathname();

  return (
    <nav className={styles.nav}>
      {navItems.map((item) => {
        const isActive =
          item.href === "/os" ? pathname === "/os" : pathname.startsWith(item.href);
        return (
          <Link
            aria-current={isActive ? "page" : undefined}
            className={isActive ? styles.activeNav : undefined}
            href={item.href}
            key={item.href}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
