"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import styles from "./page.module.css";

const navGroups = [
  {
    label: "Command",
    items: [
      { href: "/os", label: "Dashboard" },
      { href: "/os/inbox", label: "Inbox" },
      { href: "/os/tasks", label: "Work Queue" },
      { href: "/os/operations", label: "Acquisition Ops" },
      { href: "/os/pipeline", label: "Pipeline" },
      { href: "/os/leads", label: "Leads" },
    ],
  },
  {
    label: "Deal Flow",
    items: [
      { href: "/os/underwriting", label: "Underwriting" },
      { href: "/os/approvals", label: "Approvals" },
      { href: "/os/buyers", label: "Buyers" },
    ],
  },
  {
    label: "Systems",
    items: [
      { href: "/os/finance", label: "Finance" },
      { href: "/os/marketing", label: "Marketing" },
      { href: "/os/ai", label: "AI Control" },
    ],
  },
];

export function OsNav() {
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const nav = navRef.current;
    const activeLink = nav?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!nav || !activeLink || nav.scrollWidth <= nav.clientWidth) return;

    const centeredLeft = activeLink.offsetLeft - (nav.clientWidth - activeLink.offsetWidth) / 2;
    nav.scrollTo({ left: Math.max(0, centeredLeft), behavior: "auto" });
  }, [pathname]);

  return (
    <nav className={styles.nav} ref={navRef}>
      {navGroups.map((group) => (
        <div className={styles.navGroup} key={group.label}>
          <p className={styles.navLabel}>{group.label}</p>
          {group.items.map((item) => {
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
        </div>
      ))}
    </nav>
  );
}
