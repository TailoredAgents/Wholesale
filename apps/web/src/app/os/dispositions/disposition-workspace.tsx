"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Check,
  CircleDollarSign,
  Download,
  FileText,
  Gavel,
  LoaderCircle,
  PhoneCall,
  Send,
  UsersRound,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import type {
  BuyerListItem,
  BuyerListResponse,
  DispositionBuyerPoolEntry,
  DispositionBuyerPoolPage,
  DispositionCopilotOverview,
  DispositionCopilotQualityEvaluation,
  DispositionCopilotRecommendation,
  DispositionCaseReadiness,
  DispositionOverview,
} from "../../lib/api";
import { CopilotLauncher } from "../_components/copilot-launcher";
import { labelize } from "../os-utils";
import { DispositionBuyerPool } from "./disposition-buyer-pool";
import { DispositionCopilotPanel } from "./disposition-copilot-panel";
import { DispositionExecutionWorkspace } from "./disposition-execution-workspace";
import { DispositionOfferRoom } from "./disposition-offer-room";
import { DispositionPackageReadiness } from "./disposition-package-readiness";
import { DispositionProviderWorkspace } from "./disposition-provider-workspace";
import {
  DispositionReadinessPanel,
  type DispositionReadinessTarget,
} from "./disposition-readiness-panel";
import { DispositionOutreachWorkspace } from "./disposition-outreach-workspace";
import styles from "./dispositions.module.css";

export type DispositionWorkspaceTab = "overview" | "package" | "buyers" | "execution" | "outreach" | "offers" | "provider" | "reconciliation";
type Tab = DispositionWorkspaceTab;
type LegacyBuyerMatch = DispositionOverview["cases"][number]["matches"][number];
type WorkspaceBuyerChoice = {
  buyer_id: string;
  buyer_name: string;
  latest_proof_document_id: string | null;
};
const primaryWorkspaceTabs: Tab[] = ["package", "buyers", "execution", "outreach", "offers"];
const workspaceTabs: Tab[] = ["overview", ...primaryWorkspaceTabs, "provider", "reconciliation"];
const tabRootAnchors: Record<Tab, string> = {
  overview: "disposition-overview",
  package: "package-versions",
  buyers: "buyer-pool",
  execution: "call-queue",
  outreach: "campaigns",
  offers: "offer-room",
  provider: "provider-handoff",
  reconciliation: "deal-reconciliation",
};
const landUnavailableTabs = new Set<Tab>(["offers", "provider", "reconciliation"]);

function isWorkspaceTab(value: string | null): value is Tab {
  return Boolean(value && workspaceTabs.includes(value as Tab));
}

function tabLabel(tab: Tab) {
  if (tab === "overview") return "Overview";
  if (tab === "package") return "Packet";
  if (tab === "buyers") return "Find buyers";
  if (tab === "execution") return "Outreach desk";
  if (tab === "outreach") return "Bulk outreach";
  if (tab === "offers") return "Offers & closing";
  if (tab === "provider") return "External distribution";
  if (tab === "reconciliation") return "Finance reconciliation";
  return labelize(tab);
}

function money(cents: number | null) {
  return cents == null
    ? "Not set"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(cents / 100);
}

function cents(value: FormDataEntryValue | null) {
  return Math.round(Number(String(value ?? "").replace(/[$,]/g, "")) * 100);
}

function mergeBuyerChoices(
  networkBuyers: BuyerListItem[],
  poolEntries: DispositionBuyerPoolEntry[],
  legacyMatches: LegacyBuyerMatch[],
) {
  const legacyByBuyerId = new Map(
    legacyMatches.map((match) => [match.buyer_id, match]),
  );
  const choices = new Map<string, WorkspaceBuyerChoice>();
  for (const buyer of networkBuyers) {
    const legacyMatch = legacyByBuyerId.get(buyer.id);
    choices.set(buyer.id, {
      buyer_id: buyer.id,
      buyer_name: buyer.name,
      latest_proof_document_id: legacyMatch?.latest_proof_document_id ?? null,
    });
  }
  for (const entry of poolEntries) {
    if (!entry.buyer_id || choices.has(entry.buyer_id)) continue;
    const legacyMatch = legacyByBuyerId.get(entry.buyer_id);
    choices.set(entry.buyer_id, {
      buyer_id: entry.buyer_id,
      buyer_name: entry.name || legacyMatch?.buyer_name || "Buyer",
      latest_proof_document_id: legacyMatch?.latest_proof_document_id ?? null,
    });
  }
  for (const match of legacyMatches) {
    if (choices.has(match.buyer_id)) continue;
    choices.set(match.buyer_id, {
      buyer_id: match.buyer_id,
      buyer_name: match.buyer_name,
      latest_proof_document_id: match.latest_proof_document_id,
    });
  }
  return [...choices.values()];
}

export function DispositionWorkspace({
  canApproveBuyerSelection,
  canEditBuyers,
  canEditDeals,
  canManageOutreach,
  canApproveOutreach,
  canSendBulk,
  canViewOutreach,
  dealId,
  initialCaseId,
  initialData,
  initialTab = "execution",
  variant = "embedded",
}: {
  canApproveBuyerSelection: boolean;
  canEditBuyers: boolean;
  canEditDeals: boolean;
  canManageOutreach: boolean;
  canApproveOutreach: boolean;
  canSendBulk: boolean;
  canViewOutreach: boolean;
  dealId: string;
  initialCaseId?: string;
  initialData: DispositionOverview;
  initialTab?: Tab;
  variant?: "embedded" | "dedicated";
}) {
  const { getToken } = useAuth();
  const [data, setData] = useState(initialData);
  const initialSelectedCase = initialData.cases.find((item) => item.id === initialCaseId)
    ?? initialData.cases[0]
    ?? null;
  const [selectedId, setSelectedId] = useState(
    initialSelectedCase?.id ?? null,
  );
  const [tab, setTab] = useState<Tab>(
    (initialTab === "outreach" && !canViewOutreach) ||
      (initialTab === "offers" && !initialData.can_view_private_economics) ||
      (initialSelectedCase?.asset_class === "land" && landUnavailableTabs.has(initialTab))
      ? "package"
      : initialTab,
  );
  const [copilot, setCopilot] = useState<DispositionCopilotOverview | null>(null);
  const [copilotCaseId, setCopilotCaseId] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<DispositionCaseReadiness | null>(null);
  const [readinessCaseId, setReadinessCaseId] = useState<string | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(Boolean(initialSelectedCase));
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [buyerNetworkEntries, setBuyerNetworkEntries] = useState<BuyerListItem[]>([]);
  const [buyerNetworkCaseId, setBuyerNetworkCaseId] = useState<string | null>(null);
  const [buyerPoolEntries, setBuyerPoolEntries] = useState<DispositionBuyerPoolEntry[]>([]);
  const [buyerPoolCaseId, setBuyerPoolCaseId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const readinessSequenceRef = useRef(0);
  const buyerNetworkSequenceRef = useRef(0);
  const buyerPoolSequenceRef = useRef(0);
  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );
  const selected = data.cases.find((item) => item.id === selectedId) ?? null;
  const activeTab =
    selected?.asset_class === "land" && landUnavailableTabs.has(tab) ? "package" : tab;
  const buyerChoices = useMemo(
    () => mergeBuyerChoices(
      buyerNetworkCaseId === selected?.id ? buyerNetworkEntries : [],
      buyerPoolCaseId === selected?.id ? buyerPoolEntries : [],
      selected?.matches ?? [],
    ),
    [buyerNetworkCaseId, buyerNetworkEntries, buyerPoolCaseId, buyerPoolEntries, selected],
  );
  const financeHref = `/os/deals?view=all&display=queue&deal=${encodeURIComponent(dealId)}&tab=finance`;
  const dispositionHref = `/os/deals?view=all&display=queue&deal=${encodeURIComponent(dealId)}&tab=disposition`;

  useEffect(() => {
    if (!selectedId || selected?.asset_class === "land") {
      return;
    }
    let active = true;
    void request<DispositionCopilotOverview>(
      `/api/v1/dispositions/cases/${selectedId}/copilot`,
    )
      .then((result) => {
        if (active) {
          setCopilot(result);
          setCopilotCaseId(selectedId);
        }
      })
      .catch(() => {
        if (active) {
          setCopilot(null);
          setCopilotCaseId(selectedId);
        }
      });
    return () => {
      active = false;
    };
  // The request helper intentionally follows the selected case and current Clerk session.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, selected?.asset_class]);

  useEffect(() => {
    if (!selectedId) return;
    void loadReadiness(selectedId);
    return () => {
      readinessSequenceRef.current += 1;
    };
  // The request helper intentionally follows the selected case and current Clerk session.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    void loadBuyerNetworkChoices(selectedId);
    void loadBuyerPoolChoices(selectedId);
    return () => {
      buyerNetworkSequenceRef.current += 1;
      buyerPoolSequenceRef.current += 1;
    };
  // Buyer-choice hydration follows the selected case and authenticated request helper.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  async function headers(json = true) {
    const token = await getToken().catch(() => null);
    const value: Record<string, string> = {};
    if (json) value["Content-Type"] = "application/json";
    if (token) value.Authorization = `Bearer ${token}`;
    else value["X-Dev-User-Email"] = devEmail;
    return value;
  }

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: { ...(await headers(!(options.body instanceof Blob))), ...(options.headers ?? {}) },
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new Error(payload.detail ?? "Request failed.");
    }
    return response.json() as Promise<T>;
  }

  async function loadReadiness(caseId = selectedId) {
    if (!caseId) return null;
    const sequence = ++readinessSequenceRef.current;
    setReadinessLoading(true);
    setReadinessError(null);
    try {
      const result = await request<DispositionCaseReadiness>(
        `/api/v1/dispositions/cases/${caseId}/readiness`,
        { cache: "no-store" },
      );
      if (sequence !== readinessSequenceRef.current) return null;
      setReadiness(result);
      setReadinessCaseId(caseId);
      return result;
    } catch (error) {
      if (sequence !== readinessSequenceRef.current) return null;
      setReadinessError(error instanceof Error ? error.message : "Deal readiness could not be loaded.");
      return null;
    } finally {
      if (sequence === readinessSequenceRef.current) setReadinessLoading(false);
    }
  }

  async function loadBuyerNetworkChoices(caseId = selectedId) {
    if (!caseId) return null;
    const sequence = ++buyerNetworkSequenceRef.current;
    const buyers: BuyerListItem[] = [];
    let offset = 0;
    let total = 1;
    try {
      while (offset < total) {
        const query = new URLSearchParams({
          limit: "200",
          offset: String(offset),
        });
        const result = await request<BuyerListResponse>(
          `/api/v1/buyers?${query.toString()}`,
          { cache: "no-store" },
        );
        buyers.push(...result.items.filter(
          (buyer) => buyer.archived_at === null && buyer.status !== "archived",
        ));
        total = result.total;
        if (!result.items.length) break;
        offset = result.offset + result.items.length;
      }
      if (sequence !== buyerNetworkSequenceRef.current) return null;
      setBuyerNetworkEntries(buyers);
      setBuyerNetworkCaseId(caseId);
      return buyers;
    } catch {
      if (sequence !== buyerNetworkSequenceRef.current) return null;
      // Pool and legacy choices remain usable when the canonical Buyer Network is unavailable.
      setBuyerNetworkEntries([]);
      setBuyerNetworkCaseId(caseId);
      return null;
    }
  }

  async function loadBuyerPoolChoices(caseId = selectedId) {
    if (!caseId) return null;
    const sequence = ++buyerPoolSequenceRef.current;
    const entries: DispositionBuyerPoolEntry[] = [];
    let page = 1;
    let total = 1;
    try {
      while (entries.length < total) {
        const query = new URLSearchParams({
          page: String(page),
          page_size: "100",
          source: "all",
          stage: "all",
        });
        const result = await request<DispositionBuyerPoolPage>(
          `/api/v1/dispositions/cases/${caseId}/buyer-pool?${query.toString()}`,
          { cache: "no-store" },
        );
        entries.push(...result.entries);
        total = result.total;
        if (!result.entries.length) break;
        page += 1;
      }
      if (sequence !== buyerPoolSequenceRef.current) return null;
      setBuyerPoolEntries(entries.filter((entry) => entry.buyer_id !== null));
      setBuyerPoolCaseId(caseId);
      return entries;
    } catch {
      if (sequence !== buyerPoolSequenceRef.current) return null;
      // Buyer Network and legacy choices remain usable when the ranked pool is unavailable.
      setBuyerPoolEntries([]);
      setBuyerPoolCaseId(caseId);
      return null;
    }
  }

  async function reload(preferredId = selectedId) {
    const next = await request<DispositionOverview>("/api/v1/dispositions");
    setData(next);
    const nextId = preferredId ?? next.cases[0]?.id ?? null;
    setSelectedId(nextId);
    if (nextId) {
      await Promise.all([
        loadReadiness(nextId),
        loadBuyerNetworkChoices(nextId),
        loadBuyerPoolChoices(nextId),
      ]);
    }
  }

  async function action(
    work: () => Promise<unknown>,
    success: string,
    allowed = canEditDeals,
  ) {
    if (!allowed) {
      setMessage("Your role can view this disposition record but cannot change it.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await work();
      await reload();
      if (selectedId && selected?.asset_class === "house") {
        setCopilot(
          await request<DispositionCopilotOverview>(
            `/api/v1/dispositions/cases/${selectedId}/copilot`,
          ),
        );
        setCopilotCaseId(selectedId);
      }
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save.");
    } finally {
      setBusy(false);
    }
  }

  async function engagement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canEditDeals) {
      setMessage("Your role can view this disposition record but cannot change it.");
      return;
    }
    if (!selected) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const engagementType = String(values.get("engagement_type") ?? "inquiry");
    const scheduledValue = String(values.get("scheduled_at") ?? "").trim();
    const scheduledAt = engagementType === "follow_up" && scheduledValue
      ? new Date(scheduledValue).toISOString()
      : null;
    await action(
      () =>
        request(`/api/v1/dispositions/cases/${selected.id}/engagements`, {
          method: "POST",
          body: JSON.stringify({
            buyer_id: values.get("buyer_id"),
            engagement_type: engagementType,
            status: scheduledAt ? "scheduled" : "logged",
            scheduled_at: scheduledAt,
            notes: values.get("notes") || null,
          }),
        }),
      "Buyer activity logged.",
    );
    form.reset();
  }

  async function generateCopilot() {
    if (!selected) return;
    await action(
      () =>
        request(`/api/v1/dispositions/cases/${selected.id}/copilot/analyze`, {
          method: "POST",
          body: JSON.stringify({}),
        }),
      "Disposition guidance prepared for review.",
    );
  }

  async function reviewCopilot(
    recommendation: DispositionCopilotRecommendation,
    decision: "accepted" | "edited" | "rejected" | "ignored",
    finalOutput?: DispositionCopilotRecommendation["output_payload"],
    feedback?: {
      notes: string | null;
      estimatedTimeSavedSeconds: number;
      qualityEvaluation: DispositionCopilotQualityEvaluation;
    },
  ) {
    await action(
      () =>
        request(
          `/api/v1/dispositions/copilot/recommendations/${recommendation.id}/review`,
          {
            method: "POST",
            body: JSON.stringify({
              decision,
              final_output: finalOutput ?? null,
              notes: feedback?.notes ?? null,
              estimated_time_saved_seconds: feedback?.estimatedTimeSavedSeconds ?? 0,
              quality_evaluation: feedback?.qualityEvaluation ?? null,
            }),
          },
        ),
      `Disposition guidance ${labelize(decision).toLowerCase()}.`,
    );
  }

  async function uploadProof(event: FormEvent<HTMLFormElement>, buyerId: string) {
    event.preventDefault();
    if (!canEditBuyers) {
      setMessage("Your role can view buyer evidence but cannot change it.");
      return;
    }
    const form = event.currentTarget;
    const values = new FormData(form);
    const file = values.get("file") as File;
    if (!file?.size) return;
    const params = new URLSearchParams({
      file_name: file.name,
      content_type: file.type || "application/octet-stream",
      institution_name: String(values.get("institution") || ""),
      verified_amount_cents: String(cents(values.get("verified_amount"))),
      expires_at: new Date(String(values.get("expires_at"))).toISOString(),
    });
    await action(
      () =>
        request(`/api/v1/dispositions/buyers/${buyerId}/proof?${params}`, {
          method: "POST",
          headers: { "Content-Type": file.type || "application/octet-stream" },
          body: file,
        }),
      "Proof of funds verified.",
      canEditBuyers,
    );
    form.reset();
  }

  async function download(path: string, fileName: string) {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiBase}${path}`, {
        cache: "no-store",
        headers: await headers(false),
      });
      if (!response.ok) throw new Error("Export is not ready.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      const contentDisposition = response.headers.get("Content-Disposition") ?? "";
      const encodedName = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      const quotedName = contentDisposition.match(/filename="([^"]+)"/i)?.[1];
      link.download = encodedName ? decodeURIComponent(encodedName) : quotedName ?? fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to export.");
    } finally {
      setBusy(false);
    }
  }

  const post = (path: string) => request(path, { method: "POST", body: "{}" });

  function selectWorkspaceTab(nextTab: Tab, anchor: string | null = null) {
    const allowedTab =
      (nextTab === "outreach" && !canViewOutreach) ||
      (nextTab === "offers" && !data.can_view_private_economics) ||
      (selected?.asset_class === "land" && landUnavailableTabs.has(nextTab))
        ? "package"
        : nextTab;
    setTab(allowedTab);
    const url = new URL(window.location.href);
    if (variant === "dedicated") {
      url.searchParams.set("tab", allowedTab);
      url.searchParams.delete("dispositionTab");
    } else {
      url.searchParams.set("dispositionTab", allowedTab);
    }
    if (anchor) url.hash = anchor.startsWith("#") ? anchor : `#${anchor}`;
    window.history.replaceState(null, "", `${url.pathname}?${url.searchParams.toString()}${url.hash}`);
    if (anchor) {
      const targetId = anchor.replace(/^#/, "");
      window.setTimeout(() => {
        const target = document.getElementById(targetId)
          ?? document.getElementById(tabRootAnchors[allowedTab])
          ?? document.getElementById("disposition-workbench");
        const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
        target?.scrollIntoView({ behavior, block: "start" });
        if (target instanceof HTMLElement) target.focus({ preventScroll: true });
      }, 0);
    }
  }

  function openReadinessTarget(target: DispositionReadinessTarget) {
    if (isWorkspaceTab(target.tab)) {
      selectWorkspaceTab(target.tab, target.anchor);
      return;
    }
    if (target.href) {
      window.location.assign(target.href);
      return;
    }
    if (target.anchor) {
      const targetId = target.anchor.replace(/^#/, "");
      const element = document.getElementById(targetId);
      const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
      element?.scrollIntoView({ behavior, block: "start" });
      if (element instanceof HTMLElement) element.focus({ preventScroll: true });
    }
  }

  const activeReadiness = readinessCaseId === selected?.id ? readiness : null;
  const dedicatedSection = ["overview", "package"].includes(activeTab)
    ? "deal"
    : ["buyers", "execution", "outreach", "provider"].includes(activeTab)
      ? "outreach"
      : "closing";

  function tabAttention(tabKey: Tab) {
    const actions = (activeReadiness?.actions ?? []).filter(
      (item) => item.target_tab === tabKey && item.state !== "not_applicable",
    );
    const issueKeys = new Set(
      actions.flatMap((item) => item.checks)
        .filter((check) => check.status === "warning" || check.status === "blocked")
        .map((check) => check.key),
    );
    if (issueKeys.size) {
      return {
        label: String(issueKeys.size),
        title: `${issueKeys.size} checklist item${issueKeys.size === 1 ? "" : "s"} need attention`,
        tone: actions.some((action) => action.blocker_class === "hard_stop") ? "hard" : "warning",
      };
    }
    if (actions.length && actions.every((item) => item.state === "complete")) {
      return { label: "Done", title: "Checklist complete", tone: "complete" };
    }
    if (actions.some((item) => item.state === "ready" || item.state === "available")) {
      return { label: "Ready", title: "Work available", tone: "available" };
    }
    return null;
  }

  const messageIsError = Boolean(
    message && /(unable|failed|could not|unavailable|error|missing|required|must |cannot|can't|not found|stale|blocked)/i.test(message),
  );

  return (
    <section aria-label="Disposition management" className={`${styles.workspace} ${variant === "dedicated" ? styles.dedicatedWorkspace : styles.embeddedWorkspace}`} id="disposition-workbench" tabIndex={-1}>
      {message ? <p aria-live="polite" className={messageIsError ? styles.notice : styles.success} role={messageIsError ? "alert" : "status"}>{message}</p> : null}
      {!canEditDeals ? <p className={styles.notice} role="status">Read-only access: disposition actions are disabled for your role.</p> : null}

      <section className={`${styles.body} ${styles.embeddedBody}`}>
        <div className={styles.detail}>
          {!selected ? <div className={styles.empty}><UsersRound size={30} /><h3>No disposition cases</h3><p>Executed House and Land transactions appear here for disposition work, even while setup is incomplete.</p></div> : (
            <>
              {(variant === "embedded" || dedicatedSection === "deal") && selected.asset_class === "land" ? <p className={styles.landMarketNotice} role="status">Land marketing is active. Use the investor packet, asset-aware buyer matching, one-to-one dialer, and supervised bulk outreach in any order. Residential Offer Room, finance reconciliation, and InvestorLift handoff remain separate workflows.</p> : null}
              {(variant === "embedded" || dedicatedSection === "deal") && selected.asset_class === "house" && copilot && copilotCaseId === selected.id ? (
                <CopilotLauncher
                  attentionCount={copilot.readiness_gaps.length + copilot.risk_alerts.length}
                  description="Reviews buyer fit, package evidence, offers, and placement risks without contacting buyers or selecting an offer."
                  name="Disposition Copilot"
                  score={copilot.readiness_score}
                  summary={copilot.risk_alerts[0]?.reason ?? copilot.readiness_gaps[0] ?? "Buyer placement evidence is ready for review."}
                >
                  <DispositionCopilotPanel
                    busy={busy}
                    canEdit={canEditDeals}
                    copilot={copilot}
                    onGenerate={generateCopilot}
                    onReview={reviewCopilot}
                  />
                </CopilotLauncher>
              ) : null}
              {variant === "embedded" ? <DispositionReadinessPanel
                error={readinessError}
                loading={readinessLoading}
                onNavigate={openReadinessTarget}
                onRetry={() => void loadReadiness(selected.id)}
                readiness={activeReadiness}
              /> : null}
              {variant === "dedicated" ? (
                <nav aria-label="Disposition deal workspace" className={styles.workspaceNavigation}>
                  <header className={styles.workspaceDealStrip}>
                    <div>
                      <span>{selected.asset_class === "land" ? "Land" : "House"} deal</span>
                      <strong>{selected.property_address}</strong>
                      <small>Seller: {selected.seller_name}</small>
                    </div>
                    <dl>
                      <div><dt>Asking</dt><dd>{money(selected.asking_price_cents)}</dd></div>
                      <div><dt>Packet</dt><dd>{labelize(selected.package_status)}</dd></div>
                      <div><dt>Investors</dt><dd>{selected.matches.length}</dd></div>
                    </dl>
                  </header>
                  <div className={styles.workspacePrimaryNav}>
                    <button aria-current={dedicatedSection === "outreach" ? "page" : undefined} className={dedicatedSection === "outreach" ? styles.activeWorkspaceSection : ""} onClick={() => selectWorkspaceTab(["buyers", "execution", "outreach", "provider"].includes(activeTab) ? activeTab : "execution")} type="button"><PhoneCall aria-hidden="true" size={17} /><span><strong>Outreach Desk</strong><small>Work the ranked investor queue</small></span></button>
                    <button aria-current={dedicatedSection === "deal" ? "page" : undefined} className={dedicatedSection === "deal" ? styles.activeWorkspaceSection : ""} onClick={() => selectWorkspaceTab(["overview", "package"].includes(activeTab) ? activeTab : "package")} type="button"><FileText aria-hidden="true" size={17} /><span><strong>Deal &amp; Packet</strong><small>Facts, uploads, and checklist</small></span></button>
                    {selected.asset_class === "house" && data.can_view_private_economics ? <button aria-current={dedicatedSection === "closing" ? "page" : undefined} className={dedicatedSection === "closing" ? styles.activeWorkspaceSection : ""} onClick={() => selectWorkspaceTab(["offers", "reconciliation"].includes(activeTab) ? activeTab : "offers")} type="button"><Gavel aria-hidden="true" size={17} /><span><strong>Offers & Closing</strong><small>Compare, select, and close</small></span></button> : null}
                  </div>
                  {dedicatedSection === "outreach" ? <div className={styles.workspaceSecondaryNav}>
                    <button aria-current={activeTab === "execution" ? "page" : undefined} onClick={() => selectWorkspaceTab("execution")} type="button"><PhoneCall aria-hidden="true" size={15} />Outreach queue</button>
                    <button aria-current={activeTab === "buyers" ? "page" : undefined} onClick={() => selectWorkspaceTab("buyers")} type="button"><UsersRound aria-hidden="true" size={15} />Find / pull investors</button>
                    {(canViewOutreach || selected.asset_class === "house") ? <details className={styles.workspaceMoreTools}>
                      <summary>More tools</summary>
                      <div>
                        {canViewOutreach ? <button aria-current={activeTab === "outreach" ? "page" : undefined} onClick={(event) => { event.currentTarget.closest("details")?.removeAttribute("open"); selectWorkspaceTab("outreach"); }} type="button"><Send aria-hidden="true" size={15} />Bulk campaigns</button> : null}
                        {selected.asset_class === "house" ? <button aria-current={activeTab === "provider" ? "page" : undefined} onClick={(event) => { event.currentTarget.closest("details")?.removeAttribute("open"); selectWorkspaceTab("provider"); }} type="button">External distribution</button> : null}
                      </div>
                    </details> : null}
                  </div> : null}
                  {dedicatedSection === "deal" ? <div className={styles.workspaceSecondaryNav}>
                    <button aria-current={activeTab === "overview" ? "page" : undefined} onClick={() => selectWorkspaceTab("overview")} type="button">Deal summary</button>
                    <button aria-current={activeTab === "package" ? "page" : undefined} onClick={() => selectWorkspaceTab("package")} type="button"><FileText aria-hidden="true" size={15} />Packet &amp; uploads</button>
                  </div> : null}
                  {dedicatedSection === "closing" ? <div className={styles.workspaceSecondaryNav}>
                    <button aria-current={activeTab === "offers" ? "page" : undefined} onClick={() => selectWorkspaceTab("offers")} type="button">Offers & closing</button>
                    <button aria-current={activeTab === "reconciliation" ? "page" : undefined} onClick={() => selectWorkspaceTab("reconciliation")} type="button"><CircleDollarSign aria-hidden="true" size={15} />Finance reconciliation</button>
                  </div> : null}
                </nav>
              ) : activeTab === "reconciliation" ? (
                <nav aria-label="Disposition and finance sections" className={styles.financeContextNav}>
                  <Link href={dispositionHref}>Back to Dispositions</Link>
                  <span>Finance reconciliation</span>
                </nav>
              ) : (
                <nav aria-label="Disposition deal sections" className={styles.tabs}>
                  {primaryWorkspaceTabs.filter((item) => (selected.asset_class !== "land" || !landUnavailableTabs.has(item)) && (item !== "outreach" || canViewOutreach) && (item !== "offers" || data.can_view_private_economics)).map((item) => {
                    const attention = tabAttention(item);
                    return (
                      <button aria-current={activeTab === item ? "page" : undefined} className={activeTab === item ? styles.activeTab : ""} key={item} onClick={() => selectWorkspaceTab(item)} type="button">
                        <span>{tabLabel(item)}</span>
                        {attention ? <small aria-label={`${tabLabel(item)}: ${attention.title}`} className={styles.tabBadge} data-tone={attention.tone}>{attention.label}</small> : null}
                      </button>
                    );
                  })}
                  {selected.asset_class === "house" ? (
                    <details className={styles.moreTabs}>
                      <summary className={activeTab === "provider" ? styles.activeTab : ""}>More</summary>
                      <div>
                        <button
                          aria-current={activeTab === "provider" ? "page" : undefined}
                          onClick={(event) => {
                            event.currentTarget.closest("details")?.removeAttribute("open");
                            selectWorkspaceTab("provider");
                          }}
                          type="button"
                        >
                          <span><strong>External distribution</strong><small>Manual InvestorLift handoff</small></span>
                          {tabAttention("provider") ? <small className={styles.tabBadge} data-tone={tabAttention("provider")?.tone}>{tabAttention("provider")?.label}</small> : null}
                        </button>
                        <Link href={financeHref}><strong>Finance reconciliation</strong><small>Closing statement and payouts</small></Link>
                      </div>
                    </details>
                  ) : null}
                </nav>
              )}

              {variant === "dedicated" && dedicatedSection === "deal" ? <DispositionReadinessPanel
                compact
                error={readinessError}
                loading={readinessLoading}
                onNavigate={openReadinessTarget}
                onRetry={() => void loadReadiness(selected.id)}
                readiness={activeReadiness}
              /> : null}

              {activeTab === "overview" ? <section className={styles.dispositionOverview} id="disposition-overview" tabIndex={-1}>
                <header>
                  <div><span>Deal marketing command center</span><h3>Choose the work that moves this deal</h3><p>Nothing here requires a fixed sequence. Start with the packet, find buyers, dial them individually, or prepare supervised outreach.</p></div>
                  <strong data-status={selected.status}>{labelize(selected.status)}</strong>
                </header>
                <dl className={styles.overviewFacts}>
                  <div><dt>Asset</dt><dd>{selected.asset_class === "land" ? "Land" : "House"}</dd></div>
                  <div><dt>Asking price</dt><dd>{money(selected.asking_price_cents)}</dd></div>
                  <div><dt>Packet</dt><dd>{labelize(selected.package_status)}</dd></div>
                  <div><dt>Buyer pool</dt><dd>{selected.matches.length} matched</dd></div>
                  <div><dt>Offers</dt><dd>{selected.offers.length}</dd></div>
                </dl>
                <div className={styles.overviewActions}>
                  <button onClick={() => selectWorkspaceTab("package")} type="button"><FileText aria-hidden="true" size={19} /><span><strong>Work on packet</strong><small>Upload, build, preview, or share the investor packet.</small></span></button>
                  <button onClick={() => selectWorkspaceTab("buyers")} type="button"><UsersRound aria-hidden="true" size={19} /><span><strong>Find buyers</strong><small>Search and rank the best investor matches.</small></span></button>
                  <button onClick={() => selectWorkspaceTab("execution")} type="button"><PhoneCall aria-hidden="true" size={19} /><span><strong>Dial buyers</strong><small>Work the ranked list one buyer at a time.</small></span></button>
                  {canViewOutreach ? <button onClick={() => selectWorkspaceTab("outreach")} type="button"><Send aria-hidden="true" size={19} /><span><strong>Bulk outreach</strong><small>Prepare exact recipients and supervised delivery.</small></span></button> : null}
                  {selected.asset_class === "house" && data.can_view_private_economics ? <button onClick={() => selectWorkspaceTab("offers")} type="button"><Gavel aria-hidden="true" size={19} /><span><strong>Offers & closing</strong><small>Compare offers, select coverage, and protect closing.</small></span></button> : null}
                </div>
              </section> : null}

              {activeTab === "package" ? (
                <DispositionPackageReadiness
                  assetClass={selected.asset_class}
                  canEditDeals={canEditDeals}
                  caseId={selected.id}
                  dealId={dealId}
                  download={download}
                  key={selected.id}
                  leadId={selected.lead_id}
                  onCaseChanged={() => reload(selected.id)}
                  onMessage={setMessage}
                  request={request}
                />
              ) : null}

              {activeTab === "buyers" ? (
                <DispositionBuyerPool
                  activityPanel={<form className={styles.form} onSubmit={engagement}><div className={styles.sectionTitle}><div><span>Buyer activity</span><h4>Log inquiry, showing, or follow-up</h4></div></div><label><span>Buyer</span><select name="buyer_id" required>{buyerChoices.map((item) => <option key={item.buyer_id} value={item.buyer_id}>{item.buyer_name}</option>)}</select></label><label><span>Activity</span><select name="engagement_type"><option value="inquiry">Inquiry</option><option value="showing">Showing</option><option value="follow_up">Follow-up</option><option value="deposit">Deposit</option></select></label><label><span>Follow-up date and time</span><input name="scheduled_at" type="datetime-local" /><small>Used when the activity is a follow-up.</small></label><label><span>Notes</span><textarea name="notes" required rows={4} /></label><button disabled={busy || !canEditDeals || !buyerChoices.length} type="submit">Log buyer activity</button><div className={styles.activityList}>{selected.engagements.slice(0, 5).map((item) => <p key={item.id}><strong>{item.buyer_name}</strong><span>{labelize(item.engagement_type)} - {item.scheduled_at ? "Scheduled " + new Date(item.scheduled_at).toLocaleString() + " - " : ""}{item.notes}</span></p>)}</div></form>}
                  canEditBuyers={canEditBuyers}
                  canEditDeals={canEditDeals}
                  caseId={selected.id}
                  key={selected.id}
                  legacyMatches={selected.matches}
                  onLegacyReload={() => reload(selected.id)}
                  onMessage={setMessage}
                  onUploadProof={uploadProof}
                  parentBusy={busy}
                  request={request}
                />
              ) : null}

              {activeTab === "execution" ? (
                <DispositionExecutionWorkspace
                  canEditDeals={canEditDeals}
                  caseId={selected.id}
                  downloadPackage={(path) =>
                    download(path, `Stonegate-${selected.id}-investor-packet.pdf`)
                  }
                  key={selected.id}
                  onMessage={setMessage}
                  onWorkspaceChanged={() => reload(selected.id)}
                  request={request}
                />
              ) : null}

              {activeTab === "outreach" && canViewOutreach ? (
                <DispositionOutreachWorkspace
                  canApprove={canApproveOutreach}
                  canEditDeals={canEditDeals}
                  canManage={canManageOutreach}
                  canSendBulk={canSendBulk}
                  caseId={selected.id}
                  key={selected.id}
                  onMessage={setMessage}
                  onWorkspaceChanged={() => reload(selected.id)}
                  request={request}
                />
              ) : null}

              {activeTab === "offers" && data.can_view_private_economics ? (
                <DispositionOfferRoom
                  buyers={buyerChoices}
                  canApproveBuyerSelection={canApproveBuyerSelection}
                  canEditDeals={canEditDeals}
                  canViewPrivateEconomics={data.can_view_private_economics}
                  caseId={selected.id}
                  key={selected.id}
                  onCaseChanged={() => reload(selected.id)}
                  onMessage={setMessage}
                  request={request}
                />
              ) : null}

              {activeTab === "provider" ? (
                <DispositionProviderWorkspace
                  canApprove={canApproveOutreach}
                  canEditDeals={canEditDeals}
                  canManage={canManageOutreach}
                  caseId={selected.id}
                  download={download}
                  key={selected.id}
                  onMessage={setMessage}
                  onWorkspaceChanged={() => reload(selected.id)}
                  request={request}
                />
              ) : null}

              {activeTab === "reconciliation" ? <div className={styles.sectionGrid} id="deal-reconciliation" tabIndex={-1}>
                <section className={styles.section}><div className={styles.sectionTitle}><div><span>Closing statement</span><h4>Deal reconciliation</h4></div><strong>{selected.reconciliation ? labelize(selected.reconciliation.status) : "Not calculated"}</strong></div>{selected.reconciliation ? <><dl className={styles.facts}><div><dt>Collected deal revenue</dt><dd>{money(selected.reconciliation.gross_revenue_cents)}</dd></div><div><dt>Acquisition reserve</dt><dd>-{money(selected.reconciliation.acquisition_reserve_cents)}</dd></div><div><dt>Deal-specific costs</dt><dd>-{money(selected.reconciliation.deal_deductions_cents)}</dd></div><div><dt>Adjusted deal margin</dt><dd>{money(selected.reconciliation.adjusted_deal_margin_cents)}</dd></div><div><dt>Commission payouts</dt><dd>{money(selected.reconciliation.total_compensation_cents)}</dd></div><div><dt>Company profit</dt><dd>{money(selected.reconciliation.company_profit_cents)}</dd></div><div><dt>Company share</dt><dd>{(selected.reconciliation.company_margin_basis_points / 100).toFixed(1)}% / {(selected.reconciliation.target_margin_basis_points / 100).toFixed(0)}% target</dd></div></dl><div className={styles.payouts}>{selected.reconciliation.payouts.map((item) => <div key={item.id}><span>{labelize(item.role_key)} - {item.user_name ?? "Unassigned"}</span><strong>{money(item.amount_cents)}</strong></div>)}</div></> : <p className={styles.emptyRow}>Fund the transaction and record collected revenue in Finance before calculating.</p>}</section>
                <section className={styles.actionPanel}><div className={styles.sectionTitle}><div><span>Owner control</span><h4>Close the books</h4></div></div><button disabled={busy || !canEditDeals || !selected.selected_buyer_id} onClick={() => action(() => post(`/api/v1/dispositions/cases/${selected.id}/reconciliation`), "Closing statement calculated from collected revenue and the frozen plan." )} type="button"><CircleDollarSign size={15} />Calculate statement</button><button disabled={busy || !canEditDeals || selected.reconciliation?.status !== "draft"} onClick={() => action(() => request(`/api/v1/dispositions/cases/${selected.id}/reconciliation/decision`, { method: "POST", body: JSON.stringify({ decision: "approved", notes: "Owner reviewed closing statement and payout allocation.", approve_below_target: false }) }), "Closing statement and commission payouts approved." )} type="button"><Check size={15} />Approve payouts</button><button disabled={busy || selected.reconciliation?.status !== "approved"} onClick={() => download(`/api/v1/dispositions/cases/${selected.id}/accounting.csv`, "stonegate-accounting-export.csv")} type="button"><Download size={15} />Accounting CSV</button><p>Approval is blocked when commission credit is unassigned or company profit falls below the active plan target.</p></section>
              </div> : null}
            </>
          )}
        </div>
      </section>
      {busy ? <div className={styles.busy}><LoaderCircle className={styles.spin} size={16} />Working</div> : null}
    </section>
  );
}
