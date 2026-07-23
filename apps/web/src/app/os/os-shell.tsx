"use client";

import { useAuth } from "@clerk/nextjs";
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

type AccessState = "verifying" | "resolved" | "error";

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
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const searchRef = useRef<HTMLInputElement>(null);
  const mobileMenuRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [recentOpen, setRecentOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<RecentDestination[]>([]);
  const [resolvedProfile, setResolvedProfile] = useState<WorkspaceProfile | null>(profile);
  const [accessState, setAccessState] = useState<AccessState>(
    profile ? "resolved" : "verifying",
  );
  const [accessError, setAccessError] = useState<string | null>(null);
  const [accessRetry, setAccessRetry] = useState(0);
  const effectiveProfile =
    isSignedIn === false
      ? null
      : profile ??
        resolvedProfile ??
        (process.env.NODE_ENV === "development" ? developmentProfile : null);
  const visibleAccessState =
    isLoaded && !isSignedIn ? "error" : effectiveProfile ? "resolved" : accessState;
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
    if (profile || resolvedProfile || !isLoaded || !isSignedIn) return;

    const controller = new AbortController();
    let cancelled = false;

    async function verifyAccess() {
      setAccessState("verifying");
      setAccessError(null);
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
      let lastError: Error | null = null;

      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const token = await getToken({ skipCache: attempt > 0 });
          if (!token) throw new Error("Clerk did not provide an active session token.");
          const response = await fetch(`${apiBaseUrl}/api/v1/me`, {
            headers: { Authorization: `Bearer ${token}` },
            cache: "no-store",
            signal: controller.signal,
          });
          if (!response.ok) {
            const payload = (await response.json().catch(() => null)) as {
              detail?: unknown;
            } | null;
            const detail =
              typeof payload?.detail === "string"
                ? payload.detail
                : "The Stonegate API rejected the account session.";
            throw new Error(detail);
          }
          const candidate = (await response.json()) as Partial<WorkspaceProfile>;
          if (!isWorkspaceProfile(candidate)) {
            throw new Error("The Stonegate API returned an incomplete workspace profile.");
          }
          if (cancelled) return;
          setResolvedProfile(candidate);
          setAccessState("resolved");
          router.refresh();
          return;
        } catch (error) {
          if (controller.signal.aborted) return;
          lastError = error instanceof Error ? error : new Error("Access verification failed.");
          if (attempt < 2) {
            await new Promise((resolve) => window.setTimeout(resolve, 500 * (attempt + 1)));
          }
        }
      }

      if (!cancelled) {
        console.error("Stonegate browser access verification failed.", lastError);
        setAccessError(friendlyAccessError(lastError));
        setAccessState("error");
      }
    }

    void verifyAccess();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [accessRetry, getToken, isLoaded, isSignedIn, profile, resolvedProfile, router]);

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

  useEffect(() => {
    if (!drawerOpen) return;
    const sidebar = sidebarRef.current;
    if (!sidebar) return;
    const returnTarget = mobileMenuRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusableSelector =
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const focusables = Array.from(sidebar.querySelectorAll<HTMLElement>(focusableSelector));
    focusables[0]?.focus();
    const focusFrame = window.requestAnimationFrame(() => {
      if (!sidebar.contains(document.activeElement)) focusables[0]?.focus();
    });

    function trapFocus(event: KeyboardEvent) {
      if (event.key !== "Tab" || !focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    sidebar.addEventListener("keydown", trapFocus);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      sidebar.removeEventListener("keydown", trapFocus);
      document.body.style.overflow = previousOverflow;
      returnTarget?.focus();
    };
  }, [drawerOpen]);

  function closeTransientUi() {
    setDrawerOpen(false);
    setSearchOpen(false);
    setRecentOpen(false);
  }

  return (
    <div className={`${theme.theme} ${styles.shell}`}>
      <a className={styles.skipLink} href="#main-content">
        Skip to main content
      </a>
      {drawerOpen ? (
        <button
          aria-label="Close navigation"
          className={styles.mobileBackdrop}
          onClick={() => setDrawerOpen(false)}
          type="button"
        />
      ) : null}

      <aside
        aria-labelledby="stonegate-workspace-title"
        aria-modal={drawerOpen ? true : undefined}
        aria-label="Primary navigation"
        className={`${styles.sidebar} ${drawerOpen ? styles.sidebarOpen : ""}`}
        ref={sidebarRef}
        role={drawerOpen ? "dialog" : undefined}
      >
        <div className={styles.sidebarTop}>
          <div className={styles.brandBlock}>
            <span className={styles.brandMark} aria-hidden="true" />
            <div className={styles.brandCopy}>
              <p className={styles.eyebrow}>Stonegate Home Buyers</p>
              <strong className={styles.brandTitle} id="stonegate-workspace-title">Operating System</strong>
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
            <strong>
              {visibleAccessState === "error" ? "Account access could not be verified." : "Verifying account access..."}
            </strong>
            <span>
              {visibleAccessState === "error"
                ? accessError ?? "Sign in again or retry with the current session."
                : "Workspace navigation will appear automatically."}
            </span>
            {visibleAccessState === "error" ? (
              <button
                onClick={() => {
                  setAccessState("verifying");
                  setAccessError(null);
                  setAccessRetry((current) => current + 1);
                }}
                type="button"
              >
                Retry access
              </button>
            ) : null}
          </div>
        )}

        <div className={styles.sidebarStatus} aria-label="Current workspace role">
          <span>Signed in as</span>
          <strong>{effectiveProfile ? primaryRoleLabel(effectiveProfile) : "Verifying access"}</strong>
          {effectiveProfile ? <small>{effectiveProfile.display_name}</small> : null}
        </div>
      </aside>

      <div className={styles.workspaceArea}>
        <header className={styles.globalHeader}>
          <div className={styles.globalContext}>
            <button
              aria-expanded={drawerOpen}
              aria-label="Open navigation"
              className={styles.mobileMenu}
              onClick={() => setDrawerOpen(true)}
              ref={mobileMenuRef}
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

        <main className={styles.workspace} id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

function isWorkspaceProfile(
  profile: Partial<WorkspaceProfile>,
): profile is WorkspaceProfile {
  return (
    typeof profile.user_id === "string" &&
    typeof profile.organization_id === "string" &&
    typeof profile.email === "string" &&
    typeof profile.display_name === "string" &&
    Array.isArray(profile.role_keys) &&
    Array.isArray(profile.permissions) &&
    typeof profile.unread_notification_count === "number"
  );
}

function friendlyAccessError(error: Error | null) {
  const detail = error?.message.toLowerCase() ?? "";
  if (detail.includes("unknown user") || detail.includes("not mapped")) {
    return "This sign-in is not linked to an active Stonegate user.";
  }
  if (detail.includes("authorized party") || detail.includes("invalid clerk")) {
    return "Stonegate rejected this Clerk session. The authentication settings need review.";
  }
  if (detail.includes("session token") || detail.includes("missing bearer")) {
    return "Clerk did not finish creating the signed-in session. Retry access.";
  }
  return "Stonegate could not verify the current session. Retry access.";
}
