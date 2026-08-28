"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Archive,
  ArchiveRestore,
  BadgeDollarSign,
  Building2,
  ChevronLeft,
  ChevronRight,
  Download,
  FileCheck2,
  History,
  MessageSquare,
  NotebookPen,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  Upload,
  UsersRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useRef, useState, useTransition } from "react";

import type {
  BuyerBuyBoxAsset,
  BuyerBuyBoxCriteria,
  BuyerBuyBoxSummary,
  BuyerListItem,
  BuyerProfile,
  BuyerProofDocument,
  BuyerRelationshipOwner,
  BuyerTimelineItem,
  LeadListItem,
} from "../../lib/api";
import { DealControlStrip } from "../_components/deal-control-strip";
import { Drawer, StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import { BuyerBuyBoxForm } from "./buyer-buy-box-form";
import { BuyerForm } from "./buyer-form";
import styles from "./buyers.module.css";

function money(cents: number | null | undefined) {
  if (cents === null || cents === undefined) return "Not set";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(cents / 100);
}

function reliability(buyer: BuyerListItem) {
  if (buyer.completed_deals + buyer.failed_deals === 0) return "Insufficient history";
  return `${(buyer.reliability_score_basis_points / 100).toFixed(0)}%`;
}

function proofVerified(status: string, expiresAt: string | null | undefined) {
  if (status !== "verified" || !expiresAt) return false;
  const expiry = new Date(expiresAt);
  return !Number.isNaN(expiry.getTime()) && expiry > new Date();
}

function documentIsVerified(document: BuyerProofDocument) {
  return Boolean(
    proofVerified(document.status, document.expires_at)
    && document.verified_by_user_id
    && document.verified_at
    && document.verified_amount_cents
    && document.verified_amount_cents > 0
    && ["clean", "not_configured"].includes(document.malware_scan_status),
  );
}

function displayDate(value: string | null | undefined, includeTime = false) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return includeTime ? date.toLocaleString() : date.toLocaleDateString();
}

function dateTimeInput(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function permissionLabel(buyer: BuyerListItem, channel: "phone" | "sms") {
  const permission = channel === "phone" ? buyer.phone_permission : buyer.sms_permission;
  return permission.status === "granted" ? "Permission recorded" : labelize(permission.status || "not recorded");
}

function listLabel(values: string[] | undefined) {
  return values?.length ? values.map(labelize).join(", ") : "Not set";
}

function geographyLabel(criteria: BuyerBuyBoxCriteria) {
  if (!criteria.geographies.length) return "Not set";
  return criteria.geographies.map((item) => {
    if (item.jurisdiction === "radius") return `${item.value} · ${item.radius_miles} mi radius`;
    if (item.state && item.jurisdiction !== "state") return `${item.value}, ${item.state}`;
    return item.value;
  }).join(" · ");
}

function BuyBoxCard({ box, canEdit, onEdit }: { box: BuyerBuyBoxSummary; canEdit: boolean; onEdit: () => void }) {
  const criteria = box.criteria;
  return (
    <article className={styles.buyBoxCard}>
      <header>
        <div><span>{labelize(box.asset_class)} buy box</span><h3>Version {box.current_version}</h3></div>
        <div className={styles.cardActions}><StatusBadge tone={box.verification_status === "verified" ? "success" : box.verification_status === "rejected" ? "danger" : "warning"}>{labelize(box.verification_status)}</StatusBadge>{canEdit ? <button onClick={onEdit} type="button"><Pencil size={14} />Edit</button> : null}</div>
      </header>
      <dl>
        <div><dt>Markets</dt><dd>{geographyLabel(criteria)}</dd></div>
        <div><dt>Excluded markets</dt><dd>{criteria.excluded_geographies.length ? criteria.excluded_geographies.map((item) => `${item.value}${item.state ? `, ${item.state}` : ""}`).join(" · ") : "None recorded"}</dd></div>
        <div><dt>Price range</dt><dd>{money(criteria.min_price_cents)} – {money(criteria.max_price_cents)}</dd></div>
        <div><dt>Strategies</dt><dd>{listLabel(criteria.strategies)}</dd></div>
        <div><dt>Funding</dt><dd>{listLabel(criteria.funding_methods)}</dd></div>
        <div><dt>Capacity</dt><dd>{criteria.capacity.target_purchases_per_month === null ? "Not set" : `${criteria.capacity.target_purchases_per_month} target / month`}{criteria.capacity.available_capital_cents !== null ? ` · ${money(criteria.capacity.available_capital_cents)} available` : ""}</dd></div>
        {criteria.asset_class === "house" ? <>
          <div><dt>Property types</dt><dd>{listLabel(criteria.property_types)}</dd></div>
          <div><dt>Rehab tolerance</dt><dd>{listLabel(criteria.rehab_tolerance)}</dd></div>
          <div><dt>Occupancy</dt><dd>{listLabel(criteria.occupancy_preferences)}</dd></div>
        </> : <>
          <div><dt>Acreage</dt><dd>{criteria.min_acres ?? "Any"} – {criteria.max_acres ?? "Any"} acres</dd></div>
          <div><dt>Intended uses</dt><dd>{listLabel(criteria.intended_uses)}</dd></div>
          <div><dt>Access</dt><dd>{listLabel(criteria.access_preferences)}</dd></div>
          <div><dt>Utilities</dt><dd>{listLabel(criteria.utility_preferences)}</dd></div>
        </>}
        <div><dt>Hard exclusions</dt><dd>{criteria.exclusions.length ? criteria.exclusions.join(" · ") : "None recorded"}</dd></div>
        <div><dt>Verified</dt><dd>{displayDate(box.verified_at, true)}</dd></div>
      </dl>
    </article>
  );
}

type BuyerTab = "summary" | "criteria" | "activity" | "evidence" | "deals";

const buyerTabs: Array<{ key: BuyerTab; label: string }> = [
  { key: "summary", label: "Summary" },
  { key: "criteria", label: "Buy boxes" },
  { key: "activity", label: "Activity" },
  { key: "evidence", label: "Proof & capacity" },
  { key: "deals", label: "Active deals" },
];

type BuyerFilters = { asset: "" | "house" | "land" | "both"; owner: string; q: string; source: string; status: string };

export function BuyersWorkspace({
  apiError,
  buyers,
  canEdit,
  canManageProof,
  canViewProof,
  contractLeads,
  initialBuyerId,
  initialCreate,
  initialFilters,
  initialTab,
  page,
  pageSize,
  profileError,
  relationshipOwners,
  returnTo,
  selectedBuyer,
  selectedProfile,
  sourceOptions,
  total,
}: {
  apiError: string | null;
  buyers: BuyerListItem[];
  canEdit: boolean;
  canManageProof: boolean;
  canViewProof: boolean;
  contractLeads: LeadListItem[];
  initialBuyerId?: string;
  initialCreate?: boolean;
  initialFilters: BuyerFilters;
  initialTab?: string;
  page: number;
  pageSize: number;
  profileError: string | null;
  relationshipOwners: BuyerRelationshipOwner[];
  returnTo?: string;
  selectedBuyer: BuyerListItem | null;
  selectedProfile: BuyerProfile | null;
  sourceOptions: string[];
  total: number;
}) {
  const detailBuyers = selectedBuyer && !buyers.some((buyer) => buyer.id === selectedBuyer.id) ? [selectedBuyer, ...buyers] : buyers;
  const [selectedId, setSelectedId] = useState(detailBuyers.some((buyer) => buyer.id === initialBuyerId) ? initialBuyerId! : detailBuyers[0]?.id ?? null);
  const [activeTab, setActiveTab] = useState<BuyerTab>(buyerTabs.some((tab) => tab.key === initialTab) ? initialTab as BuyerTab : "summary");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(Boolean(initialBuyerId));
  const [showCreate, setShowCreate] = useState(Boolean(initialCreate && canEdit));
  const [showEdit, setShowEdit] = useState(false);
  const [showArchive, setShowArchive] = useState(false);
  const [showBuyBox, setShowBuyBox] = useState<BuyerBuyBoxAsset | null>(null);
  const [showVerification, setShowVerification] = useState(false);
  const [proofReviewId, setProofReviewId] = useState<string | null>(null);
  const [archiveReason, setArchiveReason] = useState("");
  const [activityType, setActivityType] = useState<"note" | "follow_up">("note");
  const [activityNotes, setActivityNotes] = useState("");
  const [activitySchedule, setActivitySchedule] = useState("");
  const [proofDocuments, setProofDocuments] = useState<BuyerProofDocument[]>([]);
  const [proofLoading, setProofLoading] = useState(false);
  const [actionStatus, setActionStatus] = useState<"idle" | "opening" | "saving" | "error">("idle");
  const [actionError, setActionError] = useState<string | null>(null);
  const [navigating, startNavigation] = useTransition();
  const detailRef = useRef<HTMLElement>(null);
  const { getToken } = useAuth();
  const router = useRouter();
  const apiBaseUrl = useMemo(() => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000", []);
  const selected = detailBuyers.find((buyer) => buyer.id === selectedId) ?? detailBuyers[0] ?? null;
  const profile = selectedProfile?.buyer.id === selected?.id ? selectedProfile : null;
  const activeOnPage = buyers.filter((buyer) => buyer.status === "active").length;
  const verifiedOnPage = buyers.filter((buyer) => proofVerified(buyer.proof_of_funds_status, buyer.proof_of_funds_expires_at)).length;
  const expiredOnPage = buyers.filter((buyer) => buyer.proof_of_funds_status === "expired" || (buyer.proof_of_funds_expires_at && new Date(buyer.proof_of_funds_expires_at) <= new Date())).length;
  const selectedProofVerified = selected ? proofVerified(selected.proof_of_funds_status, selected.proof_of_funds_expires_at) : false;
  const blocker = !selected ? "No buyer selected" : selected.status === "archived" ? "Archived relationship" : !selectedProofVerified ? "Proof of funds" : !selected.email && !selected.phone ? "Contact method" : !selected.buy_boxes.some((box) => box.verification_status === "verified") ? "Verified buy box" : "No active blocker";
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));

  function locationFor(overrides: Partial<BuyerFilters> & { buyer?: string | null; page?: number; tab?: BuyerTab } = {}) {
    const values = new URLSearchParams();
    const merged = { ...initialFilters, ...overrides };
    if (merged.q) values.set("q", merged.q);
    if (merged.status) values.set("status", merged.status);
    if (merged.owner) values.set("owner", merged.owner);
    if (merged.source) values.set("source", merged.source);
    if (merged.asset) values.set("asset", merged.asset);
    const nextPage = overrides.page ?? page;
    if (nextPage > 1) values.set("page", String(nextPage));
    const buyerId = overrides.buyer === undefined ? selected?.id : overrides.buyer;
    if (buyerId) values.set("buyer", buyerId);
    values.set("tab", overrides.tab ?? activeTab);
    return `/os/buyers?${values.toString()}`;
  }

  function selectBuyer(buyerId: string) {
    setSelectedId(buyerId);
    setMobileDetailOpen(true);
    startNavigation(() => router.replace(locationFor({ buyer: buyerId }), { scroll: false }));
    requestAnimationFrame(() => detailRef.current?.focus());
  }

  function selectTab(tab: BuyerTab) {
    setActiveTab(tab);
    startNavigation(() => router.replace(locationFor({ tab }), { scroll: false }));
  }

  useEffect(() => {
    if (!mobileDetailOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setMobileDetailOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [mobileDetailOpen]);

  async function getHeaders(json = true) {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = json ? { "Content-Type": "application/json" } : {};
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com";
    return headers;
  }

  async function mutationError(response: Response) {
    try {
      const payload = await response.json() as { detail?: string | { message?: string } | Array<{ msg?: string }> };
      if (typeof payload.detail === "string") return payload.detail;
      if (Array.isArray(payload.detail)) return payload.detail.map((item) => item.msg).filter(Boolean).join(" ");
      if (payload.detail?.message) return payload.detail.message;
    } catch {
      // Use the status fallback below.
    }
    return `Stonegate could not complete this action (HTTP ${response.status}).`;
  }

  function reportUnexpectedFailure(failure: unknown) {
    setActionError(
      failure instanceof Error
        ? failure.message
        : "Stonegate could not reach the server. Please try again.",
    );
    setActionStatus("error");
  }

  useEffect(() => {
    let active = true;
    if (!canViewProof || !selected?.id) return;
    void (async () => {
      setProofLoading(true);
      try {
        const headers = await getHeaders(false);
        const response = await fetch(`${apiBaseUrl}/api/v1/dispositions/buyers/${selected.id}/proof`, { headers, cache: "no-store" });
        if (!active) return;
        if (response.ok) setProofDocuments(await response.json() as BuyerProofDocument[]);
        else setActionError(await mutationError(response));
      } catch (failure) {
        if (active) {
          setActionError(
            failure instanceof Error
              ? failure.message
              : "Proof-of-funds evidence is temporarily unavailable.",
          );
        }
      } finally {
        if (active) setProofLoading(false);
      }
    })();
    return () => { active = false; };
    // getToken is stable within the active Clerk session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, canViewProof, selected?.id]);

  async function openConversation() {
    if (!selected) return;
    setActionStatus("opening");
    setActionError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${selected.id}/conversation`, { method: "POST", headers: await getHeaders() });
      if (!response.ok) { setActionError(await mutationError(response)); setActionStatus("error"); return; }
      const payload = await response.json() as { conversation_id: string };
      router.push(`/os/inbox?conversation=${payload.conversation_id}`);
    } catch (failure) {
      reportUnexpectedFailure(failure);
    }
  }

  async function archiveBuyer() {
    if (!selected || archiveReason.trim().length < 2 || actionStatus === "saving") return;
    setActionStatus("saving"); setActionError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${selected.id}/archive`, { method: "POST", headers: await getHeaders(), body: JSON.stringify({ reason: archiveReason.trim() }) });
      if (!response.ok) { setActionError(await mutationError(response)); setActionStatus("error"); return; }
      setActionStatus("idle"); setShowArchive(false); setArchiveReason(""); router.refresh();
    } catch (failure) {
      reportUnexpectedFailure(failure);
    }
  }

  async function restoreBuyer() {
    if (!selected || actionStatus === "saving" || !window.confirm(`Restore ${selected.name} for review? Do-not-contact restrictions remain in place when applicable.`)) return;
    setActionStatus("saving"); setActionError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${selected.id}/restore`, { method: "POST", headers: await getHeaders() });
      if (!response.ok) { setActionError(await mutationError(response)); setActionStatus("error"); return; }
      setActionStatus("idle"); router.refresh();
    } catch (failure) {
      reportUnexpectedFailure(failure);
    }
  }

  async function addActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !activityNotes.trim() || (activityType === "follow_up" && !activitySchedule)) return;
    setActionStatus("saving"); setActionError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${selected.id}/relationship-activities`, {
        method: "POST", headers: await getHeaders(), body: JSON.stringify({ engagement_type: activityType, notes: activityNotes.trim(), scheduled_at: activityType === "follow_up" ? new Date(activitySchedule).toISOString() : null }),
      });
      if (!response.ok) { setActionError(await mutationError(response)); setActionStatus("error"); return; }
      setActivityNotes(""); setActivitySchedule(""); setActionStatus("idle"); router.refresh();
    } catch (failure) {
      reportUnexpectedFailure(failure);
    }
  }

  async function updateActivity(item: BuyerTimelineItem, status: "completed" | "cancelled") {
    if (!selected) return;
    setActionStatus("saving"); setActionError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${selected.id}/relationship-activities/${item.id}`, { method: "PATCH", headers: await getHeaders(), body: JSON.stringify({ status }) });
      if (!response.ok) { setActionError(await mutationError(response)); setActionStatus("error"); return; }
      setActionStatus("idle"); router.refresh();
    } catch (failure) {
      reportUnexpectedFailure(failure);
    }
  }

  async function verifyRelationship(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    setActionStatus("saving"); setActionError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${selected.id}/verification`, { method: "POST", headers: await getHeaders(), body: JSON.stringify({ verification_status: String(form.get("verification_status")), reason: String(form.get("reason") ?? "").trim() || null }) });
      if (!response.ok) { setActionError(await mutationError(response)); setActionStatus("error"); return; }
      setActionStatus("idle"); setShowVerification(false); router.refresh();
    } catch (failure) {
      reportUnexpectedFailure(failure);
    }
  }

  async function uploadProof(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const file = form.get("proof_file");
    if (!(file instanceof File) || !file.size) { setActionError("Choose a proof-of-funds file."); return; }
    const query = new URLSearchParams({ file_name: file.name, content_type: file.type || "application/octet-stream" });
    const institution = String(form.get("institution_name") ?? "").trim();
    const amount = String(form.get("verified_amount") ?? "").trim();
    const expires = String(form.get("expires_at") ?? "").trim();
    if (institution) query.set("institution_name", institution);
    if (amount) query.set("verified_amount_cents", String(Math.round(Number(amount) * 100)));
    if (expires) query.set("expires_at", new Date(expires).toISOString());
    setActionStatus("saving"); setActionError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/dispositions/buyers/${selected.id}/proof?${query}`, { method: "POST", headers: await getHeaders(false), body: file });
      if (!response.ok) { setActionError(await mutationError(response)); setActionStatus("error"); return; }
      const uploaded = await response.json() as BuyerProofDocument;
      setProofDocuments((items) => [uploaded, ...items]);
      setActionStatus("idle"); formElement.reset(); router.refresh();
    } catch (failure) {
      reportUnexpectedFailure(failure);
    }
  }

  async function reviewProof(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!proofReviewId) return;
    const form = new FormData(event.currentTarget);
    const decision = String(form.get("decision"));
    const expires = String(form.get("expires_at") ?? "").trim();
    const amount = String(form.get("verified_amount") ?? "").trim();
    setActionStatus("saving"); setActionError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/dispositions/proof-documents/${proofReviewId}/verification`, { method: "POST", headers: await getHeaders(), body: JSON.stringify({ decision, verification_source: "buyer_profile_human_review", institution_name: String(form.get("institution_name") ?? "").trim() || null, verified_amount_cents: amount ? Math.round(Number(amount) * 100) : null, expires_at: expires ? new Date(expires).toISOString() : null, notes: String(form.get("notes") ?? "").trim() }) });
      if (!response.ok) { setActionError(await mutationError(response)); setActionStatus("error"); return; }
      const updated = await response.json() as BuyerProofDocument;
      setProofDocuments((items) => items.map((item) => item.id === updated.id ? updated : item));
      setProofReviewId(null); setActionStatus("idle"); router.refresh();
    } catch (failure) {
      reportUnexpectedFailure(failure);
    }
  }

  async function downloadProof(document: BuyerProofDocument) {
    setActionError(null);
    try {
      const response = await fetch(`${apiBaseUrl}${document.content_url}`, { headers: await getHeaders(false), cache: "no-store" });
      if (!response.ok) { setActionError(await mutationError(response)); return; }
      const href = URL.createObjectURL(await response.blob());
      const anchor = window.document.createElement("a"); anchor.href = href; anchor.download = document.file_name; anchor.click(); URL.revokeObjectURL(href);
    } catch (failure) {
      setActionError(
        failure instanceof Error ? failure.message : "Proof-of-funds download failed.",
      );
    }
  }

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const href = locationFor({ asset: String(data.get("asset") ?? "") as BuyerFilters["asset"], buyer: null, owner: String(data.get("owner") ?? ""), page: 1, q: String(data.get("q") ?? "").trim(), source: String(data.get("source") ?? ""), status: String(data.get("status") ?? "") });
    startNavigation(() => router.push(href));
  }

  function useExisting(buyerId: string) {
    setShowCreate(false); setShowEdit(false); setSelectedId(buyerId); setMobileDetailOpen(true); router.push(`/os/buyers?buyer=${encodeURIComponent(buyerId)}&tab=summary`);
  }

  const selectedBox = showBuyBox ? selected?.buy_boxes.find((box) => box.asset_class === showBuyBox) : null;
  const visibleProofDocuments = canViewProof && selected ? proofDocuments.filter((item) => item.buyer_id === selected.id) : [];
  const selectedProof = visibleProofDocuments.find((item) => item.id === proofReviewId) ?? null;
  const timelineItems = profile?.timeline.items ?? [];

  return (
    <section aria-label="Buyer management" className={styles.workspace}>
      <DealControlStrip
        authority={{ label: "Authority", value: canEdit ? "Buyer CRM editor" : "View only", detail: canEdit ? "Changes remain audited" : "No edit permission", tone: canEdit ? "success" : "warning" }}
        blocker={{ label: "Primary blocker", value: blocker, detail: selected?.name ?? "No buyer evidence", tone: blocker === "No active blocker" ? "success" : "warning" }}
        deadline={{ label: "Evidence expiry", value: selected?.proof_of_funds_expires_at ? displayDate(selected.proof_of_funds_expires_at) : "Not recorded", detail: `${expiredOnPage} expired on this page`, tone: expiredOnPage ? "danger" : "neutral" }}
        evidence={{ label: "Proof of funds", value: selectedProofVerified ? "Verified and current" : selected ? labelize(selected.proof_of_funds_status) : "No buyer selected", detail: selected ? reliability(selected) : `${verifiedOnPage} verified on page`, tone: selectedProofVerified ? "success" : "warning" }}
        nextAction={{ label: "Authorized next step", value: blocker === "Proof of funds" ? "Review buyer funds" : blocker === "Verified buy box" ? "Verify a buy box" : contractLeads.length ? "Compare active deals" : "Maintain buyer record", detail: `${contractLeads.length} deals need buyer coverage`, tone: "info" }}
      />

      <section className={styles.metrics} aria-label="Buyer network summary"><div><UsersRound size={17} /><span>Matching buyers</span><strong>{total}</strong></div><div><ShieldCheck size={17} /><span>Active on page</span><strong>{activeOnPage}</strong></div><div><Building2 size={17} /><span>Deals needing buyers</span><strong>{contractLeads.length}</strong></div><div><BadgeDollarSign size={17} /><span>Expired POF on page</span><strong>{expiredOnPage}</strong></div></section>

      <form className={styles.toolbar} onSubmit={submitFilters} role="search">
        <label className={styles.searchField}><Search size={15} /><span className={styles.srOnly}>Search buyers</span><input defaultValue={initialFilters.q} name="q" placeholder="Search name, company, phone, or email" type="search" /></label>
        <label><span className={styles.filterLabel}>Asset</span><select defaultValue={initialFilters.asset} name="asset"><option value="">All assets</option><option value="house">House buyers</option><option value="land">Land buyers</option><option value="both">House and Land buyers</option></select></label>
        <label><span className={styles.filterLabel}>Status</span><select defaultValue={initialFilters.status} name="status"><option value="">All statuses</option><option value="needs_review">Needs review</option><option value="active">Active</option><option value="paused">Paused</option><option value="do_not_contact">Do not contact</option><option value="archived">Archived</option></select></label>
        <label><span className={styles.filterLabel}>Owner</span><select defaultValue={initialFilters.owner} name="owner"><option value="">All owners</option>{relationshipOwners.map((owner) => <option key={owner.user_id} value={owner.user_id}>{owner.display_name}</option>)}</select></label>
        <label><span className={styles.filterLabel}>Source</span><select defaultValue={initialFilters.source} name="source"><option value="">All sources</option>{sourceOptions.map((source) => <option key={source} value={source}>{labelize(source)}</option>)}</select></label>
        <button disabled={navigating} type="submit">{navigating ? "Loading..." : "Apply"}</button>
        {Object.values(initialFilters).some(Boolean) ? <Link className={styles.clearFilters} href="/os/buyers">Clear</Link> : null}
        {canEdit ? <button className={styles.addButton} onClick={() => setShowCreate(true)} type="button"><Plus size={15} />Add buyer</button> : null}
      </form>
      <p aria-live="polite" className={styles.resultSummary}>{apiError ? "Buyer search failed." : `${total} matching buyer${total === 1 ? "" : "s"}. Page ${page} of ${totalPages}.`}</p>
      {apiError ? <div className={styles.loadError} role="alert"><strong>Buyer CRM could not load.</strong><span>{apiError}</span><button onClick={() => router.refresh()} type="button">Retry</button></div> : null}

      <section className={styles.split}>
        <aside className={styles.queue} aria-label="Buyer records"><header><span>Buyer CRM</span><strong>{buyers.length} on this page</strong></header>{buyers.length === 0 ? <p className={styles.empty}>No buyers match these filters.</p> : buyers.map((buyer) => <button className={buyer.id === selected?.id ? styles.selectedBuyer : styles.buyerRow} key={buyer.id} onClick={() => selectBuyer(buyer.id)} type="button"><div><strong>{buyer.name}</strong><StatusBadge tone={buyer.status === "active" ? "success" : buyer.status === "do_not_contact" || buyer.status === "archived" ? "danger" : "neutral"}>{labelize(buyer.status)}</StatusBadge></div><span>{buyer.company_name ?? labelize(buyer.buyer_type)}</span><div className={styles.rowBadges}><span>{buyer.asset_focus ? labelize(buyer.asset_focus) : "No buy box"}</span><span>Tier {buyer.tier === "unclassified" ? "—" : buyer.tier.toUpperCase()}</span><span>{labelize(buyer.temperature)}</span></div><dl><div><dt>Owner</dt><dd>{buyer.relationship_owner_name ?? "Unassigned"}</dd></div><div><dt>Follow-up</dt><dd>{displayDate(buyer.next_follow_up_at)}</dd></div></dl></button>)}</aside>

        <section aria-label={selected ? `${selected.name} buyer profile` : "Buyer profile"} className={`${styles.detail} ${mobileDetailOpen ? styles.detailOpen : ""}`} ref={detailRef} tabIndex={-1}>
          {selected ? <>
            <header className={styles.buyerHeader}><div><span>{selected.asset_focus ? `${labelize(selected.asset_focus)} buyer` : labelize(selected.buyer_type)}</span><h2>{selected.name}</h2><p>{selected.company_name ?? "Independent buyer"}</p><div className={styles.rowBadges}><span>{labelize(selected.relationship_status)}</span><span>Tier {selected.tier === "unclassified" ? "—" : selected.tier.toUpperCase()}</span><span>{labelize(selected.temperature)}</span><span>{labelize(selected.verification_status)}</span></div></div><div className={styles.headerStatus}>
              {canEdit && selected.status !== "archived" ? <button className={styles.headerAction} onClick={() => setShowEdit(true)} type="button"><Pencil size={15} />Edit</button> : null}
              {canEdit ? selected.status === "archived" ? <button className={styles.headerAction} disabled={actionStatus === "saving"} onClick={() => void restoreBuyer()} type="button"><ArchiveRestore size={15} />Restore</button> : <button className={styles.headerAction} onClick={() => setShowArchive(true)} type="button"><Archive size={15} />Archive</button> : null}
              {canEdit ? <button className={styles.conversationButton} disabled={actionStatus === "opening"} onClick={() => void openConversation()} type="button"><MessageSquare size={15} />{actionStatus === "opening" ? "Opening" : "Conversation"}</button> : null}
              <StatusBadge tone={selectedProofVerified ? "success" : "warning"}>POF {selectedProofVerified ? "verified" : labelize(selected.proof_of_funds_status)}</StatusBadge>
              <button aria-label="Close buyer details" className={styles.mobileClose} onClick={() => setMobileDetailOpen(false)} type="button"><X size={17} /></button>
            </div></header>
            {actionError ? <p className={styles.actionError} role="alert">{actionError}</p> : null}
            <div aria-label="Buyer record sections" className={styles.localTabs} role="tablist">{buyerTabs.map((tab) => <button aria-controls={`buyer-panel-${tab.key}`} aria-selected={activeTab === tab.key} className={activeTab === tab.key ? styles.activeTab : ""} id={`buyer-tab-${tab.key}`} key={tab.key} onClick={() => selectTab(tab.key)} role="tab" type="button">{tab.label}</button>)}</div>

            <section aria-labelledby={`buyer-tab-${activeTab}`} id={`buyer-panel-${activeTab}`} role="tabpanel">
              {profileError ? <div className={styles.loadError} role="alert"><strong>Buyer history could not load.</strong><span>{profileError}</span><button onClick={() => router.refresh()} type="button">Retry</button></div> : null}
              {activeTab === "summary" ? <div className={styles.detailGrid}>
                <section className={styles.panel}><header><div><span>Relationship</span><h3>Buyer snapshot</h3></div>{canEdit ? <button className={styles.inlineAction} onClick={() => setShowVerification(true)} type="button"><ShieldCheck size={14} />Review</button> : null}</header><dl><div><dt>Status</dt><dd>{labelize(selected.status)}</dd></div><div><dt>Relationship</dt><dd>{labelize(selected.relationship_status)}</dd></div><div><dt>Profile verification</dt><dd>{labelize(selected.verification_status)}{selected.verified_at ? ` · ${displayDate(selected.verified_at)}` : ""}</dd></div><div><dt>Owner</dt><dd>{selected.relationship_owner_name ?? "Unassigned"}</dd></div><div><dt>Source</dt><dd>{labelize(selected.source_key)}{selected.source_detail ? ` · ${selected.source_detail}` : ""}</dd></div><div><dt>Asset focus</dt><dd>{selected.asset_focus ? labelize(selected.asset_focus) : "No structured buy box"}</dd></div><div><dt>Last contact</dt><dd>{displayDate(selected.last_contact_at, true)}</dd></div><div><dt>Next follow-up</dt><dd>{displayDate(selected.next_follow_up_at, true)}</dd></div><div><dt>Last reviewed</dt><dd>{displayDate(selected.last_verified_at, true)}</dd></div></dl>{selected.tags.length ? <div className={styles.tagList}>{selected.tags.map((tag) => <span key={tag}>{tag}</span>)}</div> : null}</section>
                <section className={styles.panel}><header><div><span>Contactability</span><h3>Permission and contact</h3></div></header><dl><div><dt>Call</dt><dd>{permissionLabel(selected, "phone")} · {displayDate(selected.phone_permission.recorded_at, true)}</dd></div><div><dt>SMS</dt><dd>{permissionLabel(selected, "sms")} · {displayDate(selected.sms_permission.recorded_at, true)}</dd></div><div><dt>Permission source</dt><dd>{selected.phone_permission.source ?? selected.sms_permission.source ?? "Not recorded"}</dd></div><div><dt>Email</dt><dd>{selected.email ?? "Missing"}</dd></div><div><dt>Phone</dt><dd>{selected.phone ?? "Missing"}</dd></div><div><dt>Reliability</dt><dd>{reliability(selected)}</dd></div></dl></section>
                <section className={`${styles.panel} ${styles.permissionPanel}`}><header><div><span>Append-only record</span><h3>Permission history</h3></div></header>{selected.permission_history.length ? <ol aria-label="Contact permission history" className={styles.permissionHistory}>{selected.permission_history.map((entry, index) => <li key={`${entry.channel}-${entry.recorded_at ?? "unknown"}-${index}`}><div><strong>{labelize(entry.channel)} · {labelize(entry.status)}</strong>{entry.recorded_at ? <time dateTime={entry.recorded_at}>{displayDate(entry.recorded_at, true)}</time> : <span>Time not recorded</span>}</div><p>Source: {entry.source ? labelize(entry.source) : "Not recorded"}</p><small>{entry.normalized_address ? `Contact: ${entry.normalized_address}` : "Contact value not recorded"}{entry.wording_version ? ` · Wording ${entry.wording_version}` : ""}</small></li>)}</ol> : <p className={styles.permissionHistoryEmpty}>No permission history has been recorded for this buyer.</p>}</section>
              </div> : null}

              {activeTab === "criteria" ? <div className={styles.criteriaWorkspace}>
                <header className={styles.sectionHeading}><div><span>Asset-specific purchasing rules</span><h3>Structured buy boxes</h3><p>House and Land criteria are saved and verified independently.</p></div>{canEdit ? <div><button onClick={() => setShowBuyBox("house")} type="button"><Plus size={14} />{selected.buy_boxes.some((box) => box.asset_class === "house") ? "Edit House" : "Add House"}</button><button onClick={() => setShowBuyBox("land")} type="button"><Plus size={14} />{selected.buy_boxes.some((box) => box.asset_class === "land") ? "Edit Land" : "Add Land"}</button></div> : null}</header>
                <div className={styles.buyBoxGrid}>{selected.buy_boxes.length ? selected.buy_boxes.map((box) => <BuyBoxCard box={box} canEdit={canEdit} key={box.buy_box_id} onEdit={() => setShowBuyBox(box.asset_class)} />) : <div className={styles.emptyCard}><Building2 size={22} /><strong>No structured buy boxes</strong><p>Add House or Land criteria before treating this buyer as eligible for matching.</p></div>}</div>
                {profile?.legacy_criteria ? <section className={styles.legacyCriteria}><header><History size={17} /><div><strong>Unverified legacy information</strong><p>Preserved for review only. It is not used for matching.</p></div></header><dl><div><dt>Markets</dt><dd>{profile.legacy_criteria.criteria.markets ?? "Not set"}</dd></div><div><dt>Property types</dt><dd>{profile.legacy_criteria.criteria.property_types ?? "Not set"}</dd></div><div><dt>Price</dt><dd>{money(profile.legacy_criteria.criteria.min_price_cents)} – {money(profile.legacy_criteria.criteria.max_price_cents)}</dd></div><div><dt>Rehab</dt><dd>{profile.legacy_criteria.criteria.rehab_levels ?? "Not set"}</dd></div><div><dt>Notes</dt><dd>{profile.legacy_criteria.criteria.notes ?? "None"}</dd></div></dl></section> : null}
                {profile?.criteria_versions.length ? <details className={styles.versionHistory}><summary>View buy-box version history ({profile.criteria_versions.length})</summary><ol>{profile.criteria_versions.map((version) => <li key={version.id}><div><strong>{labelize(version.asset_class)} · Version {version.version_number}</strong><StatusBadge tone={version.verification_status === "verified" ? "success" : "neutral"}>{labelize(version.verification_status)}</StatusBadge></div><p>{version.change_reason}</p><small>{labelize(version.source)} · {displayDate(version.created_at, true)}{version.is_current ? " · Current" : ` · Superseded ${displayDate(version.superseded_at, true)}`}</small></li>)}</ol></details> : null}
              </div> : null}

              {activeTab === "activity" ? <div className={styles.activityWorkspace}>
                {canEdit ? <form className={styles.activityComposer} onSubmit={addActivity}><div><NotebookPen size={17} /><div><strong>Add relationship activity</strong><p>Notes and follow-ups become part of the buyer’s shared timeline.</p></div></div><div className={styles.activityControls}><label><span>Type</span><select onChange={(event) => setActivityType(event.target.value as "note" | "follow_up")} value={activityType}><option value="note">Note</option><option value="follow_up">Follow-up</option></select></label>{activityType === "follow_up" ? <label><span>When</span><input min={dateTimeInput(new Date().toISOString())} onChange={(event) => setActivitySchedule(event.target.value)} required type="datetime-local" value={activitySchedule} /></label> : null}</div><label><span>Details</span><textarea maxLength={1000} onChange={(event) => setActivityNotes(event.target.value)} placeholder="Record buyer feedback, relationship context, or the next follow-up reason." required rows={3} value={activityNotes} /></label><button disabled={actionStatus === "saving" || !activityNotes.trim()} type="submit">{activityType === "follow_up" ? "Schedule follow-up" : "Add note"}</button></form> : null}
                <section className={styles.timelinePanel}><header><div><span>Permission-aware history</span><h3>Buyer activity</h3></div><strong>{profile?.timeline.total ?? 0}</strong></header>{timelineItems.length ? <ol className={styles.buyerTimeline}>{timelineItems.map((item) => <li key={item.id}><span aria-hidden="true" /><article><div><strong>{item.summary}</strong>{item.status ? <StatusBadge tone={item.status === "completed" ? "success" : item.status === "cancelled" ? "danger" : "neutral"}>{labelize(item.status)}</StatusBadge> : null}</div>{item.body ? <p>{item.body}</p> : null}<small>{labelize(item.category)}{item.channel ? ` · ${labelize(item.channel)}` : ""}{item.direction ? ` · ${labelize(item.direction)}` : ""} · {displayDate(item.occurred_at, true)}</small>{canEdit && item.status === "open" && item.event_type.includes("follow") ? <div className={styles.timelineActions}><button onClick={() => void updateActivity(item, "completed")} type="button">Complete</button><button onClick={() => void updateActivity(item, "cancelled")} type="button">Cancel</button></div> : null}</article></li>)}</ol> : <p className={styles.empty}>{profileError ? "Buyer activity is unavailable until the history request succeeds." : "No buyer activity has been recorded yet."}</p>}{profile?.timeline.has_more ? <p className={styles.timelineMore}>Showing the newest {profile.timeline.items.length} of {profile.timeline.total} records.</p> : null}</section>
              </div> : null}

              {activeTab === "evidence" ? <div className={styles.evidenceWorkspace}>
                <section className={styles.panel}><header><div><span>Qualification</span><h3>Capacity summary</h3></div></header><dl><div><dt>Proof of funds</dt><dd>{selectedProofVerified ? "Verified and current" : labelize(selected.proof_of_funds_status)}</dd></div><div><dt>Evidence expires</dt><dd>{displayDate(selected.proof_of_funds_expires_at)}</dd></div><div><dt>Legacy max purchase</dt><dd>{money(selected.max_purchase_price_cents)} · not POF capacity</dd></div><div><dt>Reliability</dt><dd>{reliability(selected)}</dd></div><div><dt>Deal history</dt><dd>{selected.completed_deals} completed / {selected.failed_deals} failed</dd></div></dl></section>
                {!canViewProof ? <section className={styles.restrictedEvidence}><ShieldCheck size={22} /><strong>Restricted financial evidence</strong><p>Your role can see the buyer’s summary status, but not private proof-of-funds files.</p></section> : <section className={styles.proofPanel}><header><div><span>Reusable evidence</span><h3>Proof-of-funds documents</h3><p>Upload means received for review. Only verified, unexpired evidence is treated as verified.</p></div><strong>{visibleProofDocuments.filter(documentIsVerified).length} current</strong></header>{canManageProof ? <form className={styles.proofUpload} onSubmit={uploadProof}><label><span>File</span><input accept=".pdf,.png,.jpg,.jpeg" name="proof_file" required type="file" /></label><label><span>Institution</span><input name="institution_name" placeholder="Bank or funding source" /></label><label><span>Stated amount</span><input min="0" name="verified_amount" placeholder="250000" step="1" type="number" /></label><label><span>Stated expiry</span><input name="expires_at" type="date" /></label><button disabled={actionStatus === "saving"} type="submit"><Upload size={14} />Upload for review</button></form> : null}{proofLoading ? <p className={styles.empty}>Loading proof evidence…</p> : visibleProofDocuments.length ? <div className={styles.proofList}>{visibleProofDocuments.map((document) => <article key={document.id}><div><FileCheck2 size={18} /><div><strong>{document.file_name}</strong><small>{document.institution_name ?? "Institution not recorded"} · {money(document.verified_amount_cents)}</small></div><StatusBadge tone={documentIsVerified(document) ? "success" : document.status === "rejected" ? "danger" : "warning"}>{documentIsVerified(document) ? "Verified" : labelize(document.status)}</StatusBadge></div><dl><div><dt>Uploaded</dt><dd>{displayDate(document.created_at, true)}</dd></div><div><dt>Expires</dt><dd>{displayDate(document.expires_at)}</dd></div><div><dt>Safety review</dt><dd>{labelize(document.malware_scan_status)}</dd></div><div><dt>Reviewed</dt><dd>{displayDate(document.verified_at, true)}</dd></div></dl><div className={styles.proofActions}><button onClick={() => void downloadProof(document)} type="button"><Download size={14} />Download</button>{canManageProof ? <button onClick={() => setProofReviewId(document.id)} type="button"><ShieldCheck size={14} />Review</button> : null}</div></article>)}</div> : <p className={styles.empty}>No proof-of-funds documents have been uploaded.</p>}</section>}
              </div> : null}

              {activeTab === "deals" ? <section className={styles.dealPool}><header><div><span>Available inventory</span><h3>Active deals to compare</h3></div><strong>{contractLeads.length}</strong></header>{contractLeads.length ? contractLeads.map((lead) => <Link href={`/os/leads/${lead.id}?returnTo=${encodeURIComponent(locationFor())}`} key={lead.id}><div><strong>{lead.property_address}</strong><span>{labelize(lead.property_type)}</span></div><small>{lead.seller_name} · {labelize(lead.stage_key)} · {lead.property_city}, {lead.property_state}</small></Link>) : <p className={styles.empty}>No contracted deals need buyer placement.</p>}</section> : null}
            </section>
          </> : <div className={styles.emptyState}><UsersRound size={24} /><h2>No buyer selected</h2><p>Search the buyer network or add the first qualified buyer.</p></div>}
        </section>
        {mobileDetailOpen ? <button aria-label="Close buyer details" className={styles.mobileBackdrop} onClick={() => setMobileDetailOpen(false)} type="button" /> : null}
      </section>

      <nav aria-label="Buyer result pages" className={styles.pagination}>{page > 1 ? <Link href={locationFor({ buyer: null, page: page - 1 })}><ChevronLeft size={16} />Previous</Link> : <span aria-disabled="true"><ChevronLeft size={16} />Previous</span>}<strong>Page {page} of {totalPages}</strong>{page < totalPages ? <Link href={locationFor({ buyer: null, page: page + 1 })}>Next<ChevronRight size={16} /></Link> : <span aria-disabled="true">Next<ChevronRight size={16} /></span>}</nav>

      <section className={styles.comparison}><header><div><span>Current result page</span><h3>Relationship readiness</h3></div></header><div><table><thead><tr><th>Buyer</th><th>Asset</th><th>Status</th><th>Tier</th><th>Owner</th><th>POF</th><th>Next follow-up</th></tr></thead><tbody>{buyers.map((buyer) => <tr key={buyer.id}><td><button onClick={() => selectBuyer(buyer.id)} type="button">{buyer.name}</button><small>{buyer.company_name}</small></td><td>{buyer.asset_focus ? labelize(buyer.asset_focus) : "None"}</td><td>{labelize(buyer.relationship_status)}</td><td>{buyer.tier === "unclassified" ? "—" : buyer.tier.toUpperCase()}</td><td>{buyer.relationship_owner_name ?? "Unassigned"}</td><td>{proofVerified(buyer.proof_of_funds_status, buyer.proof_of_funds_expires_at) ? "Verified" : labelize(buyer.proof_of_funds_status)}</td><td>{displayDate(buyer.next_follow_up_at)}</td></tr>)}</tbody></table></div></section>

      <Drawer description="Create a buyer in Needs review. Add and verify House or Land criteria from the buyer profile." onClose={() => setShowCreate(false)} open={showCreate} title="Add buyer"><BuyerForm onCancel={() => setShowCreate(false)} onSaved={(saved) => { setShowCreate(false); setSelectedId(saved.id); router.push(returnTo ?? `/os/buyers?buyer=${saved.id}&tab=summary`); }} onUseExisting={useExisting} relationshipOwners={relationshipOwners} sourceOptions={sourceOptions} /></Drawer>
      <Drawer description="Update identity, relationship ownership, follow-up, and contact permission. Buy boxes stay independently versioned." onClose={() => setShowEdit(false)} open={showEdit} title={`Edit ${selected?.name ?? "buyer"}`}>{selected ? <BuyerForm buyer={selected} onCancel={() => setShowEdit(false)} onSaved={(saved) => { setShowEdit(false); setSelectedId(saved.id); router.refresh(); }} onUseExisting={useExisting} relationshipOwners={relationshipOwners} sourceOptions={sourceOptions} /> : null}</Drawer>
      <Drawer description="Save separate, versioned purchasing rules for this asset." onClose={() => setShowBuyBox(null)} open={Boolean(showBuyBox)} size="wide" title={`${showBuyBox ? labelize(showBuyBox) : "Buyer"} buy box`}>{selected && showBuyBox ? <BuyerBuyBoxForm asset={showBuyBox} buyerId={selected.id} current={selectedBox} onCancel={() => setShowBuyBox(null)} onSaved={() => { setShowBuyBox(null); router.refresh(); }} /> : null}</Drawer>
      <Drawer description="Relationship verification is separate from proof-of-funds and buy-box verification." onClose={() => setShowVerification(false)} open={showVerification} title={`Review ${selected?.name ?? "buyer"}`}><form className={styles.archiveForm} onSubmit={verifyRelationship}><label><span>Decision</span><select defaultValue={selected?.verification_status === "unverified" ? "needs_review" : selected?.verification_status} name="verification_status"><option value="verified">Verified relationship</option><option value="needs_review">Needs review</option><option value="rejected">Rejected</option></select></label><label><span>Reason or evidence</span><textarea maxLength={500} minLength={2} name="reason" placeholder="What was reviewed or still needs attention?" required /></label>{actionError ? <p className={styles.formError} role="alert">{actionError}</p> : null}<div className={styles.formActions}><button className={styles.secondaryAction} onClick={() => setShowVerification(false)} type="button">Cancel</button><button disabled={actionStatus === "saving"} type="submit">Save review</button></div></form></Drawer>
      <Drawer description="Archived buyers leave active matching and outreach but keep their audit history." onClose={() => setShowArchive(false)} open={showArchive} title={`Archive ${selected?.name ?? "buyer"}`}><div className={styles.archiveForm}><label><span>Reason</span><textarea autoFocus maxLength={500} onChange={(event) => setArchiveReason(event.target.value)} placeholder="Why should this buyer leave the active network?" value={archiveReason} /></label><p>This does not delete the relationship. You can restore it later.</p>{actionError ? <p className={styles.formError} role="alert">{actionError}</p> : null}<div className={styles.formActions}><button className={styles.secondaryAction} onClick={() => setShowArchive(false)} type="button">Cancel</button><button disabled={archiveReason.trim().length < 2 || actionStatus === "saving"} onClick={() => void archiveBuyer()} type="button">{actionStatus === "saving" ? "Archiving..." : "Archive buyer"}</button></div></div></Drawer>
      <Drawer description="A human review is required. Uploading a file never verifies it automatically." onClose={() => setProofReviewId(null)} open={Boolean(proofReviewId)} title={`Review ${selectedProof?.file_name ?? "proof of funds"}`}><form className={styles.archiveForm} onSubmit={reviewProof}><label><span>Decision</span><select defaultValue="verified" name="decision"><option value="verified">Verify</option><option value="rejected">Reject</option></select></label><label><span>Institution</span><input defaultValue={selectedProof?.institution_name ?? ""} name="institution_name" /></label><label><span>Confirmed amount</span><input defaultValue={selectedProof?.verified_amount_cents ? selectedProof.verified_amount_cents / 100 : ""} min="1" name="verified_amount" step="1" type="number" /></label><label><span>Future expiration date</span><input defaultValue={selectedProof?.expires_at?.slice(0, 10) ?? ""} name="expires_at" type="date" /></label><label><span>Review notes</span><textarea defaultValue={selectedProof?.notes ?? ""} minLength={2} name="notes" required /></label>{actionError ? <p className={styles.formError} role="alert">{actionError}</p> : null}<div className={styles.formActions}><button className={styles.secondaryAction} onClick={() => setProofReviewId(null)} type="button">Cancel</button><button disabled={actionStatus === "saving"} type="submit">Save decision</button></div></form></Drawer>
    </section>
  );
}
