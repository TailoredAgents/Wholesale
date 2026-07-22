"use client";

import { Bell, History, Menu, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { WorkspaceProfile } from "../lib/api";
import { AuthControls } from "./auth-controls";
import {
  defaultRouteForProfile,
  navigationContext,
  primaryRoleLabel,
  visibleNavGroups,
} from "./os-navigation";
import { OsNav } from "./os-nav";
import styles from "./page.module.css";
import theme from "./os-theme.module.css";

type RecentDestination = {
  group: string;
  href: string;
  label: string;
};

const recentStorageKey = "stonegate:recent-destinations";

const developmentProfile: WorkspaceProfile = {
  user_id: "development-owner",
  organization_id: "development-workspace",
  email: "local@stonegate.test",
  display_name: "Local Owner",
  role_keys: ["owner"],
  permissions: [],
  unread_notification_count: 0,
};

export function OsShell({
  children,
  profile,
}: {
  children: ReactNode;
  profile: WorkspaceProfile | null;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const searchRef = useRef<HTMLInputElement>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [recentOpen, setRecentOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<RecentDestination[]>([]);
  const effectiveProfile =
    profile ?? (process.env.NODE_ENV === "development" ? developmentProfile : null);
  const context = navigationContext(pathname);
  const navGroups = useMemo(
    () => (effectiveProfile ? visibleNavGroups(effectiveProfile) : []),
    [effectiveProfile],
  );
  const destinations = useMemo(() => navGroups.flatMap((group) => group.items), [navGroups]);
  const searchResults = destinations.filter((item) =>
    `${item.label} ${item.href}`.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const canOpenOperations = destinations.some((item) => item.href === "/os/operations");

  useEffect(() => {
    if (!effectiveProfile || pathname !== "/os") return;
    const defaultRoute = defaultRouteForProfile(effectiveProfile);
    if (defaultRoute !== "/os") router.replace(defaultRoute);
  }, [effectiveProfile, pathname, router]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setDrawerOpen(false);
      setSearchOpen(false);
      setRecentOpen(false);
      setQuery("");

      const current = navigationContext(pathname);
      const nextEntry = { href: pathname, label: current.label, group: current.group };
      let existing: RecentDestination[] = [];
      try {
        existing = JSON.parse(
          window.localStorage.getItem(recentStorageKey) ?? "[]",
        ) as RecentDestination[];
      } catch {
        existing = [];
      }
      const next = [nextEntry, ...existing.filter((item) => item.href !== pathname)].slice(0, 5);
      setRecent(next);
      window.localStorage.setItem(recentStorageKey, JSON.stringify(next));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pathname]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDrawerOpen(false);
        setSearchOpen(false);
        setRecentOpen(false);
      }
      if (
        event.key === "/" &&
        !event.metaKey &&
        !event.ctrlKey &&
        !(event.target instanceof HTMLInputElement) &&
        !(event.target instanceof HTMLTextAreaElement)
      ) {
        event.preventDefault();
        setSearchOpen(true);
        window.requestAnimationFrame(() => searchRef.current?.focus());
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  function closeTransientUi() {
    setDrawerOpen(false);
    setSearchOpen(false);
    setRecentOpen(false);
  }

  return (
    <main className={`${theme.theme} ${styles.shell}`}>
      {drawerOpen ? (
        <button
          aria-label="Close navigation"
          className={styles.mobileBackdrop}
          onClick={() => setDrawerOpen(false)}
          type="button"
        />
      ) : null}

      <aside
        aria-label="Primary navigation"
        className={`${styles.sidebar} ${drawerOpen ? styles.sidebarOpen : ""}`}
      >
        <div className={styles.sidebarTop}>
          <div className={styles.brandBlock}>
            <span className={styles.brandMark} aria-hidden="true" />
            <div className={styles.brandCopy}>
              <p className={styles.eyebrow}>Stonegate Home Buyers</p>
              <h1>Operating System</h1>
              <span>Acquisitions and deal execution.</span>
            </div>
          </div>
          <button
            aria-label="Close navigation"
            className={styles.mobileClose}
            onClick={() => setDrawerOpen(false)}
            type="button"
          >
            <X aria-hidden="true" size={20} />
          </button>
        </div>

        {effectiveProfile ? (
          <OsNav onNavigate={closeTransientUi} profile={effectiveProfile} />
        ) : (
          <div className={styles.navUnavailable} role="status">
            Workspace navigation is unavailable while account access is being verified.
          </div>
        )}

        <div className={styles.sidebarStatus} aria-label="Current workspace role">
          <span>Signed in as</span>
          <strong>{effectiveProfile ? primaryRoleLabel(effectiveProfile) : "Verifying access"}</strong>
          {effectiveProfile ? <small>{effectiveProfile.display_name}</small> : null}
        </div>
      </aside>

      <section className={styles.workspaceArea}>
        <header className={styles.globalHeader}>
          <div className={styles.globalContext}>
            <button
              aria-expanded={drawerOpen}
              aria-label="Open navigation"
              className={styles.mobileMenu}
              onClick={() => setDrawerOpen(true)}
              type="button"
            >
              <Menu aria-hidden="true" size={20} />
            </button>
            <div>
              <span>{context.group}</span>
              <strong>{context.label}</strong>
            </div>
          </div>

          <div className={styles.globalActions}>
            <div
              className={styles.globalSearch}
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) setSearchOpen(false);
              }}
            >
              <label className={styles.globalSearchField}>
                <Search aria-hidden="true" size={17} />
                <input
                  aria-label="Search Stonegate workspaces"
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setSearchOpen(true);
                    setRecentOpen(false);
                  }}
                  onFocus={() => {
                    setSearchOpen(true);
                    setRecentOpen(false);
                  }}
                  placeholder="Search workspaces"
                  ref={searchRef}
                  value={query}
                />
              </label>
              {searchOpen ? (
                <div className={styles.commandMenu}>
                  <span>{query ? "Matching workspaces" : "Available workspaces"}</span>
                  {searchResults.map((item) => (
                    <Link href={item.href} key={item.href} onClick={closeTransientUi}>
                      <item.icon aria-hidden="true" size={16} />
                      <strong>{item.label}</strong>
                    </Link>
                  ))}
                  {!searchResults.length ? <p>No matching workspace.</p> : null}
                </div>
              ) : null}
            </div>

            <div className={styles.headerMenuWrap}>
              <button
                aria-expanded={recentOpen}
                aria-label="Recent destinations"
                className={styles.headerIconButton}
                onClick={() => {
                  setRecentOpen((current) => !current);
                  setSearchOpen(false);
                }}
                type="button"
              >
                <History aria-hidden="true" size={18} />
              </button>
              {recentOpen ? (
                <div className={styles.recentMenu}>
                  <span>Recent destinations</span>
                  {recent.map((item) => (
                    <Link href={item.href} key={item.href} onClick={closeTransientUi}>
                      <small>{item.group}</small>
                      <strong>{item.label}</strong>
                    </Link>
                  ))}
                </div>
              ) : null}
            </div>

            {canOpenOperations ? (
              <Link
                aria-label={`${effectiveProfile?.unread_notification_count ?? 0} unread notifications`}
                className={styles.headerIconButton}
                href="/os/operations?view=notifications"
                title="Notifications"
              >
                <Bell aria-hidden="true" size={18} />
                {effectiveProfile?.unread_notification_count ? (
                  <span>{Math.min(effectiveProfile.unread_notification_count, 99)}</span>
                ) : null}
              </Link>
            ) : null}

            <AuthControls compact />
          </div>
        </header>

        <section className={styles.workspace}>{children}</section>
      </section>
    </main>
  );
}
