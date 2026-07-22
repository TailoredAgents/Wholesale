"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { WorkspaceProfile } from "../lib/api";
import { visibleNavGroups } from "./os-navigation";
import styles from "./page.module.css";

export function OsNav({
  onNavigate,
  profile,
}: {
  onNavigate?: () => void;
  profile: WorkspaceProfile;
}) {
  const pathname = usePathname();
  const navGroups = visibleNavGroups(profile);

  return (
    <nav aria-label="Stonegate workspaces" className={styles.nav}>
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
                onClick={onNavigate}
              >
                <item.icon aria-hidden="true" size={17} strokeWidth={1.8} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
