"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

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
  const searchParams = useSearchParams();
  const navGroups = visibleNavGroups(profile);
  const queryMatchedPath = navGroups
    .flatMap((group) => group.items)
    .some((item) => {
      const [itemPath, itemQuery] = item.href.split("?");
      if (!itemQuery || itemPath !== pathname) return false;
      const expected = new URLSearchParams(itemQuery);
      return Array.from(expected.entries()).every(
        ([key, value]) => searchParams.get(key) === value,
      );
    });

  return (
    <nav aria-label="Stonegate workspaces" className={styles.nav}>
      {navGroups.map((group) => (
        <div
          className={`${styles.navGroup} ${group.label === "Management" ? styles.managementNavGroup : ""}`}
          key={group.label}
        >
          <p className={styles.navLabel}>{group.label}</p>
          {group.items.map((item) => {
            const [itemPath, itemQuery] = item.href.split("?");
            const queryMatches = itemQuery
              ? Array.from(new URLSearchParams(itemQuery).entries()).every(
                  ([key, value]) => searchParams.get(key) === value,
                )
              : !queryMatchedPath;
            const isActive =
              (itemPath === "/os" ? pathname === "/os" : pathname.startsWith(itemPath)) &&
              queryMatches;
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
