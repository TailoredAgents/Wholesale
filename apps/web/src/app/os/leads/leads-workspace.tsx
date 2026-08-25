"use client";

import { useAuth } from "@clerk/nextjs";
import {
  DndContext,
  DragOverlay,
  MouseSensor,
  pointerWithin,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  ArrowRight,
  CalendarDays,
  Columns3,
  ExternalLink,
  GripVertical,
  Inbox,
  Search,
  Table2,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { LeadCloseOutResponse, LeadListItem, SpeedToLeadTask } from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import {
  defaultLeadSortKey,
  apiErrorMessage,
  formatDateTime,
  getFilteredLeads,
  getLeadOperatingStatus,
  getPipelineStage,
  getSavedLeadViewCounts,
  isAddressOnlyLead,
  leadCanEnterPipelineStage,
  leadSortOptions,
  labelize,
  pipelineStages,
  pipelineStageMoveBlockReason,
  qualificationFieldCount,
  qualificationFieldTarget,
  type PipelineStage,
  type LeadSortKey,
  type SavedLeadViewKey,
} from "../os-utils";
import styles from "./leads-workspace.module.css";
import { LeadLifecycleActions } from "./lead-lifecycle-actions";

function ownerLabel(email: string | null) {
  if (!email) return "Unassigned";
  return email.split("@")[0]?.replace(/[._-]+/g, " ") || email;
}

function operatingTone(status: string): "danger" | "warning" | "info" | "success" | "neutral" {
  if (status === "Overdue follow-up") return "danger";
  if (["Needs qualification", "Needs follow-up"].includes(status)) return "warning";
  if (status === "Skip trace needed") return "info";
  if (["Appointment work", "Offer prep", "Negotiation"].includes(status)) return "info";
  if (status === "Under contract") return "success";
  return "neutral";
}

function nextAction(lead: LeadListItem, tasks: SpeedToLeadTask[]) {
  if (isAddressOnlyLead(lead)) {
    return { href: `/os/leads/${lead.id}`, label: "Review address-only lead" };
  }
  if (lead.primary_next_action) {
    return {
      href: `/os/tasks?item=task:${lead.primary_next_action.task_id}`,
      label: lead.primary_next_action.title,
    };
  }
  const status = getLeadOperatingStatus(lead, tasks);
  if (status === "Overdue follow-up") {
    return { href: `/os/inbox?lead=${lead.id}`, label: "Continue conversation" };
  }
  if (status === "Needs qualification") {
    return { href: `/os/leads?view=queue&lead=${lead.id}`, label: "Open qualification queue" };
  }
  if (status === "Appointment work") {
    return { href: `/os/calendar?view=dispatch&lead=${lead.id}`, label: "Open dispatch" };
  }
  if (status === "Offer prep") {
    if (lead.asset_class === "land") {
      return { href: `/os/leads/${lead.id}?tab=property`, label: "Review Land evidence" };
    }
    return { href: `/os/leads/${lead.id}?tab=valuation`, label: "Prepare offer" };
  }
  if (status === "Negotiation") {
    if (lead.asset_class === "land") {
      return { href: `/os/leads/${lead.id}?tab=property`, label: "Review Land evidence" };
    }
    return { href: `/os/leads/${lead.id}?tab=contract#negotiation`, label: "Continue negotiation" };
  }
  if (status === "Nurture") {
    return { href: `/os/inbox?lead=${lead.id}`, label: "Open follow-up" };
  }
  return { href: `/os/leads/${lead.id}`, label: "Open seller record" };
}

function LeadBoardCard({
  canEditLead,
  isPending,
  isSelected,
  lead,
  onSelect,
  tasks,
}: {
  canEditLead: boolean;
  isPending: boolean;
  isSelected: boolean;
  lead: LeadListItem;
  onSelect: () => void;
  tasks: SpeedToLeadTask[];
}) {
  const operatingStatus = getLeadOperatingStatus(lead, tasks);
  const action = nextAction(lead, tasks);
  const canMoveLead = canEditLead && getPipelineStage(lead.stage_key)?.key !== "under_contract";
  const { attributes, isDragging, listeners, setNodeRef } = useDraggable({
    id: `lead:${lead.id}`,
    data: { leadId: lead.id },
    disabled: !canMoveLead || isPending,
  });

  return (
    <article
      aria-busy={isPending || undefined}
      className={`${styles.boardCard} ${isSelected ? styles.selectedCard : ""} ${isDragging ? styles.draggingCard : ""}`}
      ref={setNodeRef}
    >
      <button
        aria-current={isSelected ? "true" : undefined}
        className={styles.cardSelect}
        onClick={onSelect}
        type="button"
      >
        <span className={styles.cardTop}><strong>{lead.seller_name}</strong><em>{labelize(lead.asset_class)} · {labelize(lead.lead_temperature)}</em></span>
        <span className={styles.cardAddress}>{lead.property_address}</span>
        <time className={styles.cardReceived} dateTime={lead.created_at}>Received {formatDateTime(lead.created_at)}</time>
        <StatusBadge tone={operatingTone(operatingStatus)}>{operatingStatus}</StatusBadge>
        <span className={styles.cardMeta}><span><UserRound size={13} />{ownerLabel(lead.assigned_user_email)}</span><span>{formatDateTime(lead.primary_next_action?.due_at ?? lead.next_follow_up_at)}</span></span>
        <span className={styles.cardAction}>{action.label}<ArrowRight size={13} /></span>
      </button>
      {canMoveLead ? (
        <button
          {...attributes}
          {...listeners}
          aria-label={`Move ${lead.seller_name} to another pipeline stage`}
          className={styles.dragHandle}
          disabled={isPending}
          onClick={(event) => {
            event.stopPropagation();
            onSelect();
          }}
          title="Drag to another stage"
          type="button"
        >
          <GripVertical aria-hidden="true" size={16} />
        </button>
      ) : null}
      {isPending ? <span className={styles.savingBadge}>Saving</span> : null}
    </article>
  );
}

function LeadBoardColumn({
  blockedReason,
  children,
  disabled,
  leadCount,
  stage,
}: {
  blockedReason?: string;
  children: ReactNode;
  disabled: boolean;
  leadCount: number;
  stage: PipelineStage;
}) {
  const { isOver, setNodeRef } = useDroppable({
    id: `pipeline-stage:${stage.key}`,
    data: { stageKey: stage.key },
    disabled,
  });

  return (
    <section
      aria-label={`${stage.label} pipeline stage${blockedReason ? `, move unavailable: ${blockedReason}` : ""}`}
      className={`${styles.boardColumn} ${isOver ? (blockedReason ? styles.blockedDropTarget : styles.dropTarget) : ""} ${disabled || blockedReason ? styles.disabledDropTarget : ""}`}
      data-drop-disabled={disabled || Boolean(blockedReason) || undefined}
      ref={setNodeRef}
      title={blockedReason}
    >
      <header><h2>{stage.label}</h2><strong>{leadCount}</strong></header>
      <div>{children}</div>
    </section>
  );
}

function LeadDragOverlay({ lead, tasks }: { lead: LeadListItem; tasks: SpeedToLeadTask[] }) {
  const operatingStatus = getLeadOperatingStatus(lead, tasks);
  return (
    <div aria-hidden="true" className={`${styles.boardCard} ${styles.dragOverlay}`}>
      <div className={styles.cardSelect}>
        <span className={styles.cardTop}><strong>{lead.seller_name}</strong><em>{labelize(lead.asset_class)}</em></span>
        <span className={styles.cardAddress}>{lead.property_address}</span>
        <StatusBadge tone={operatingTone(operatingStatus)}>{operatingStatus}</StatusBadge>
      </div>
    </div>
  );
}

export function LeadsWorkspace({
  canEditLead,
  initialAsset,
  initialDisplay,
  initialLeadId,
  initialOwner,
  initialQuery,
  initialSort,
  initialStage,
  initialView,
  leads,
  newPaidLeadCount,
  tasks,
}: {
  canEditLead: boolean;
  initialAsset: "all" | "house" | "land";
  initialDisplay: "table" | "board";
  initialLeadId: string;
  initialOwner: string;
  initialQuery: string;
  initialSort: LeadSortKey;
  initialStage: string;
  initialView: SavedLeadViewKey;
  leads: LeadListItem[];
  newPaidLeadCount: number;
  tasks: SpeedToLeadTask[];
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const [view, setView] = useState<SavedLeadViewKey>(initialView);
  const [asset, setAsset] = useState<"all" | "house" | "land">(initialAsset);
  const [display, setDisplay] = useState<"table" | "board">(initialDisplay);
  const [query, setQuery] = useState(initialQuery);
  const [owner, setOwner] = useState(initialOwner);
  const [sort, setSort] = useState<LeadSortKey>(initialSort);
  const [stage, setStage] = useState(initialDisplay === "board" ? "all" : initialStage);
  const [selectedLeadId, setSelectedLeadId] = useState(initialLeadId);
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [workingLeads, setWorkingLeads] = useState(leads);
  const [activeLeadId, setActiveLeadId] = useState<string | null>(null);
  const [pendingLeadIds, setPendingLeadIds] = useState<Set<string>>(() => new Set());
  const [stageNotice, setStageNotice] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const pendingLeadIdsRef = useRef(new Set<string>());
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 8 } }),
  );

  useEffect(() => {
    setWorkingLeads((current) =>
      leads.map(
        (lead) =>
          (pendingLeadIdsRef.current.has(lead.id)
            ? current.find((currentLead) => currentLead.id === lead.id)
            : null) ?? lead,
      ),
    );
  }, [leads]);

  useEffect(() => {
    if (initialDisplay !== "board" || initialStage === "all") return;
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.delete("stage");
    window.history.replaceState(
      null,
      "",
      `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`,
    );
  }, [initialDisplay, initialStage]);

  const viewCounts = useMemo(
    () => getSavedLeadViewCounts(workingLeads, tasks),
    [tasks, workingLeads],
  );
  const owners = useMemo(
    () =>
      Array.from(
        new Set(workingLeads.map((lead) => lead.assigned_user_email).filter((email): email is string => Boolean(email))),
      ).sort(),
    [workingLeads],
  );
  const baseLeads = useMemo(
    () => getFilteredLeads(workingLeads, tasks, view, sort),
    [sort, tasks, view, workingLeads],
  );
  const visibleLeads = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return baseLeads.filter((lead) => {
      const matchesQuery =
        !normalizedQuery ||
        `${lead.seller_name} ${lead.property_address} ${lead.source} ${lead.assigned_user_email ?? ""}`
          .toLowerCase()
          .includes(normalizedQuery);
      const matchesOwner =
        owner === "all" ||
        (owner === "unassigned" && !lead.assigned_user_email) ||
        lead.assigned_user_email === owner;
      const matchesStage = stage === "all" || getPipelineStage(lead.stage_key)?.key === stage;
      const matchesAsset = asset === "all" || lead.asset_class === asset;
      return matchesQuery && matchesOwner && matchesStage && matchesAsset;
    });
  }, [asset, baseLeads, owner, query, stage]);
  const selectedLead =
    visibleLeads.find((lead) => lead.id === selectedLeadId) ?? visibleLeads[0] ?? null;
  const selectedStatus = selectedLead ? getLeadOperatingStatus(selectedLead, tasks) : null;
  const selectedAction = selectedLead ? nextAction(selectedLead, tasks) : null;
  const activeLead = workingLeads.find((lead) => lead.id === activeLeadId) ?? null;
  const contactReadyLeads = workingLeads.filter((lead) => !isAddressOnlyLead(lead));
  const newLeadCount = contactReadyLeads.filter((lead) => lead.stage_key === "new").length;
  const qualifiedCount = contactReadyLeads.filter((lead) =>
    [
      "qualified",
      "qualification_complete",
      "appointment_scheduling",
      "appointment_set",
      "appointment_scheduled",
      "underwriting",
      "offer_pending_approval",
      "offer_ready",
    ].includes(lead.stage_key),
  ).length;
  const unassignedCount = contactReadyLeads.filter((lead) => !lead.assigned_user_email).length;
  const withoutFollowUpCount = contactReadyLeads.filter(
    (lead) =>
      !lead.next_follow_up_at &&
      !["dead", "disqualified", "under_contract"].includes(lead.stage_key),
  ).length;

  function replaceLocation(overrides: {
    asset?: "all" | "house" | "land";
    display?: "table" | "board";
    leadId?: string;
    owner?: string;
    query?: string;
    sort?: LeadSortKey;
    stage?: string;
    view?: SavedLeadViewKey;
  } = {}) {
    const next = {
      asset: overrides.asset ?? asset,
      display: overrides.display ?? display,
      leadId: overrides.leadId ?? selectedLeadId,
      owner: overrides.owner ?? owner,
      query: overrides.query ?? query,
      sort: overrides.sort ?? sort,
      stage: overrides.stage ?? stage,
      view: overrides.view ?? view,
    };
    const params = new URLSearchParams();
    if (next.view !== "all") params.set("view", next.view);
    if (next.asset !== "all") params.set("asset", next.asset);
    if (next.display === "board") params.set("display", "board");
    if (next.query.trim()) params.set("q", next.query.trim());
    if (next.owner !== "all") params.set("owner", next.owner);
    if (next.sort !== defaultLeadSortKey(next.view)) params.set("sort", next.sort);
    if (next.stage !== "all") params.set("stage", next.stage);
    if (next.leadId) params.set("lead", next.leadId);
    const suffix = params.toString();
    window.history.replaceState(null, "", suffix ? `/os/leads?${suffix}` : "/os/leads");
  }

  function chooseView(nextView: SavedLeadViewKey) {
    const nextSort = defaultLeadSortKey(nextView);
    setView(nextView);
    setSort(nextSort);
    replaceLocation({ sort: nextSort, view: nextView });
  }

  function chooseDisplay(nextDisplay: "table" | "board") {
    setDisplay(nextDisplay);
    if (nextDisplay === "board") {
      setStage("all");
      replaceLocation({ display: nextDisplay, stage: "all" });
      return;
    }
    replaceLocation({ display: nextDisplay });
  }

  function selectLead(leadId: string) {
    setSelectedLeadId(leadId);
    setMobileDetailOpen(true);
    replaceLocation({ leadId });
  }

  function fullRecordHref(leadId: string) {
    const values = new URLSearchParams({ asset, display, lead: leadId, owner, sort, stage, view });
    if (query) values.set("q", query);
    return `/os/leads/${leadId}?returnTo=${encodeURIComponent(`/os/leads?${values.toString()}`)}`;
  }

  async function moveLeadToStage(leadId: string, targetStage: PipelineStage) {
    const lead = workingLeads.find((item) => item.id === leadId);
    if (!lead || !canEditLead || pendingLeadIdsRef.current.has(leadId)) return;

    const currentPipelineStage = getPipelineStage(lead.stage_key);
    if (currentPipelineStage?.key === targetStage.key) {
      setStageNotice({
        message: `${lead.seller_name} is already in ${targetStage.label}.`,
        tone: "success",
      });
      return;
    }
    const moveBlockReason = pipelineStageMoveBlockReason(lead, targetStage);
    if (moveBlockReason) {
      setStageNotice({
        message: moveBlockReason,
        tone: "error",
      });
      return;
    }

    const previousStageKey = lead.stage_key;
    pendingLeadIdsRef.current.add(leadId);
    setPendingLeadIds(new Set(pendingLeadIdsRef.current));
    setStageNotice(null);
    setWorkingLeads((current) =>
      current.map((item) =>
        item.id === leadId ? { ...item, stage_key: targetStage.dropStageKey } : item,
      ),
    );

    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;

      const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}/stage`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({
          expected_stage_key: previousStageKey,
          reason: `Moved on Leads board from ${currentPipelineStage?.label ?? labelize(previousStageKey)} to ${targetStage.label}.`,
          stage_key: targetStage.dropStageKey,
        }),
      });
      const responseBody = await response.json().catch(() => null) as {
        detail?: unknown;
        stage_key?: string;
      } | null;
      if (!response.ok) {
        throw new Error(
          apiErrorMessage(responseBody?.detail, "Unable to move this lead. Its original stage was restored."),
        );
      }

      setWorkingLeads((current) =>
        current.map((item) =>
          item.id === leadId
            ? { ...item, stage_key: responseBody?.stage_key ?? targetStage.dropStageKey }
            : item,
        ),
      );
      setStageNotice({
        message: `${lead.seller_name} moved to ${targetStage.label}.`,
        tone: "success",
      });
    } catch (error) {
      setWorkingLeads((current) =>
        current.map((item) =>
          item.id === leadId ? { ...item, stage_key: previousStageKey } : item,
        ),
      );
      setStageNotice({
        message: error instanceof Error ? error.message : "Unable to move this lead. Its original stage was restored.",
        tone: "error",
      });
    } finally {
      pendingLeadIdsRef.current.delete(leadId);
      setPendingLeadIds(new Set(pendingLeadIdsRef.current));
      router.refresh();
    }
  }

  function handleLeadClosed(result: LeadCloseOutResponse) {
    const closedLeadId = result.lead.id;
    const closedLeadIndex = visibleLeads.findIndex((lead) => lead.id === closedLeadId);
    const nextLead =
      visibleLeads[closedLeadIndex + 1] ??
      visibleLeads[closedLeadIndex - 1] ??
      visibleLeads.find((lead) => lead.id !== closedLeadId) ??
      null;

    pendingLeadIdsRef.current.delete(closedLeadId);
    setPendingLeadIds(new Set(pendingLeadIdsRef.current));
    setWorkingLeads((current) => current.filter((lead) => lead.id !== closedLeadId));
    setSelectedLeadId(nextLead?.id ?? "");
    setMobileDetailOpen(false);
    replaceLocation({ leadId: nextLead?.id ?? "" });
    setStageNotice({
      message: `${result.lead.seller_name} was closed and removed from the active Leads board.`,
      tone: "success",
    });
  }

  function handleDragStart(event: DragStartEvent) {
    const leadId = event.active.data.current?.leadId;
    setActiveLeadId(typeof leadId === "string" ? leadId : null);
  }

  function handleDragEnd(event: DragEndEvent) {
    const leadId = event.active.data.current?.leadId;
    const targetStageKey = event.over?.data.current?.stageKey;
    setActiveLeadId(null);
    if (typeof leadId !== "string" || typeof targetStageKey !== "string") return;
    const targetStage = pipelineStages.find((item) => item.key === targetStageKey);
    if (targetStage) void moveLeadToStage(leadId, targetStage);
  }

  const dragAnnouncements: Announcements = {
    onDragStart({ active }) {
      const leadId = active.data.current?.leadId;
      const lead = workingLeads.find((item) => item.id === leadId);
      return lead ? `Picked up ${lead.seller_name}.` : "Picked up lead.";
    },
    onDragOver({ active, over }) {
      const leadId = active.data.current?.leadId;
      const lead = workingLeads.find((item) => item.id === leadId);
      const targetStageKey = over?.data.current?.stageKey;
      const targetStage = pipelineStages.find((item) => item.key === targetStageKey);
      const blockedReason = lead && targetStage
        ? pipelineStageMoveBlockReason(lead, targetStage)
        : null;
      if (blockedReason) return `${targetStage?.label ?? "That stage"} is unavailable. ${blockedReason}`;
      return targetStage ? `Over ${targetStage.label}.` : "Not over a pipeline stage.";
    },
    onDragEnd({ active, over }) {
      const leadId = active.data.current?.leadId;
      const lead = workingLeads.find((item) => item.id === leadId);
      const targetStageKey = over?.data.current?.stageKey;
      const targetStage = pipelineStages.find((item) => item.key === targetStageKey);
      const blockedReason = lead && targetStage
        ? pipelineStageMoveBlockReason(lead, targetStage)
        : null;
      if (blockedReason) return `Move blocked. ${blockedReason}`;
      return lead && targetStage
        ? `${lead.seller_name} dropped in ${targetStage.label}. Saving the change.`
        : "Move cancelled.";
    },
    onDragCancel() {
      return "Move cancelled.";
    },
  };

  return (
    <div className={styles.workspace}>
      <section className={styles.metrics} aria-label="Lead database summary" tabIndex={0}>
        <div><span>New</span><strong>{newLeadCount}</strong><small>First-contact records</small></div>
        <div><span>Qualified+</span><strong>{qualifiedCount}</strong><small>Appointment or offer work</small></div>
        <div><span>Unassigned</span><strong>{unassignedCount}</strong><small>Needs an owner</small></div>
        <div><span>No follow-up</span><strong>{withoutFollowUpCount}</strong><small>No dated next action</small></div>
        <div><span>Paid prospects</span><strong>{newPaidLeadCount}</strong><small>Includes address-only captures</small></div>
      </section>

      <section className={styles.views} aria-label="Saved lead views">
        {viewCounts.map((item) => (
          <button
            aria-pressed={view === item.key}
            className={view === item.key ? styles.activeView : undefined}
            key={item.key}
            onClick={() => chooseView(item.key)}
            type="button"
          >
            <span>{item.label}</span><strong>{item.count}</strong>
          </button>
        ))}
      </section>

      <section className={styles.leadDesk}>
        <div className={styles.toolbar}>
          <label className={styles.search}>
            <Search aria-hidden="true" size={16} />
            <input
              aria-label="Search active leads"
              onChange={(event) => {
                setQuery(event.target.value);
                replaceLocation({ query: event.target.value });
              }}
              placeholder="Search seller, property, source, or owner"
              type="search"
              value={query}
            />
          </label>
          <label>
            <span>Type</span>
            <select onChange={(event) => {
              const nextAsset = event.target.value as "all" | "house" | "land";
              setAsset(nextAsset);
              replaceLocation({ asset: nextAsset });
            }} value={asset}>
              <option value="all">House &amp; land</option>
              <option value="house">House</option>
              <option value="land">Land</option>
            </select>
          </label>
          <label>
            <span>Owner</span>
            <select onChange={(event) => {
              setOwner(event.target.value);
              replaceLocation({ owner: event.target.value });
            }} value={owner}>
              <option value="all">All owners</option>
              <option value="unassigned">Unassigned</option>
              {owners.map((email) => <option key={email} value={email}>{ownerLabel(email)}</option>)}
            </select>
          </label>
          <label>
            <span>Stage</span>
            <select
              aria-label={display === "board" ? "All stages shown in Board view" : "Filter leads by stage"}
              disabled={display === "board"}
              onChange={(event) => {
                setStage(event.target.value);
                replaceLocation({ stage: event.target.value });
              }}
              title={display === "board" ? "Board view shows every pipeline stage so leads can be moved between columns." : undefined}
              value={stage}
            >
              <option value="all">All stages</option>
              {pipelineStages.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
            </select>
          </label>
          <label>
            <span>Sort</span>
            <select onChange={(event) => {
              const nextSort = event.target.value as LeadSortKey;
              setSort(nextSort);
              replaceLocation({ sort: nextSort });
            }} value={sort}>
              {leadSortOptions.map((option) => (
                <option key={option.key} value={option.key}>{option.label}</option>
              ))}
            </select>
          </label>
          <div aria-label="Lead display" className={styles.displayControl}>
            <button aria-pressed={display === "table"} onClick={() => chooseDisplay("table")} title="Table view" type="button"><Table2 aria-hidden="true" size={15} /><span>Table</span></button>
            <button aria-pressed={display === "board"} onClick={() => chooseDisplay("board")} title="Board view" type="button"><Columns3 aria-hidden="true" size={15} /><span>Board</span></button>
          </div>
          <strong>{visibleLeads.length} shown</strong>
        </div>
        {stageNotice ? (
          <p
            aria-live={stageNotice.tone === "error" ? "assertive" : "polite"}
            className={stageNotice.tone === "error" ? styles.stageError : styles.stageSuccess}
            role={stageNotice.tone === "error" ? "alert" : "status"}
          >
            {stageNotice.message}
          </p>
        ) : null}

        <div className={`${styles.content} ${display === "board" ? styles.boardContent : ""}`}>
          {display === "table" ? <div className={styles.list}>
            <div className={styles.listHeader}>
              <span>Seller</span><span>Received</span><span>Status</span><span>Owner</span><span>Next action</span>
            </div>
            {visibleLeads.map((lead) => {
              const status = getLeadOperatingStatus(lead, tasks);
              const action = nextAction(lead, tasks);
              return (
                <button
                  aria-current={selectedLead?.id === lead.id ? "true" : undefined}
                  className={selectedLead?.id === lead.id ? styles.selectedRow : undefined}
                  key={lead.id}
                  onClick={() => selectLead(lead.id)}
                  type="button"
                >
                  <span className={styles.identity}>
                    <strong>{lead.seller_name}</strong><small>{lead.property_address}</small>
                    <em>{labelize(lead.asset_class)} · {labelize(lead.source)} · {labelize(lead.stage_key)}</em>
                  </span>
                  <time className={styles.received} dateTime={lead.created_at}>{formatDateTime(lead.created_at)}</time>
                  <span className={styles.status}><StatusBadge tone={operatingTone(status)}>{status}</StatusBadge></span>
                  <span className={styles.owner}><UserRound aria-hidden="true" size={14} />{ownerLabel(lead.assigned_user_email)}</span>
                  <span className={styles.next}>
                    <strong>{action.label}</strong><small>{formatDateTime(lead.primary_next_action?.due_at ?? lead.next_follow_up_at)}</small>
                  </span>
                </button>
              );
            })}
            {!visibleLeads.length ? (
              <div className={styles.empty}><strong>No leads match this view</strong><span>Change the view, owner, stage, or search.</span></div>
            ) : null}
          </div> : (
            <DndContext
              accessibility={{
                announcements: dragAnnouncements,
                screenReaderInstructions: {
                  draggable: "Press Enter on the move handle to open the seller preview, then use the Move to stage selector. Mouse and touch users can drag the handle between columns.",
                },
              }}
              collisionDetection={pointerWithin}
              onDragCancel={() => setActiveLeadId(null)}
              onDragEnd={handleDragEnd}
              onDragStart={handleDragStart}
              sensors={sensors}
            >
              <div className={styles.board}>
                {pipelineStages.map((pipelineStage) => {
                  const stageLeads = visibleLeads.filter(
                    (lead) => getPipelineStage(lead.stage_key)?.key === pipelineStage.key,
                  );
                  const dropBlockedReason = activeLead
                    ? pipelineStageMoveBlockReason(activeLead, pipelineStage) ?? undefined
                    : undefined;
                  return (
                    <LeadBoardColumn
                      blockedReason={dropBlockedReason}
                      disabled={!canEditLead}
                      key={pipelineStage.key}
                      leadCount={stageLeads.length}
                      stage={pipelineStage}
                    >
                      {stageLeads.map((lead) => (
                        <LeadBoardCard
                          canEditLead={canEditLead}
                          isPending={pendingLeadIds.has(lead.id)}
                          isSelected={selectedLead?.id === lead.id}
                          key={lead.id}
                          lead={lead}
                          onSelect={() => selectLead(lead.id)}
                          tasks={tasks}
                        />
                      ))}
                      {!stageLeads.length ? <p>No leads</p> : null}
                    </LeadBoardColumn>
                  );
                })}
              </div>
              <DragOverlay>
                {activeLead ? <LeadDragOverlay lead={activeLead} tasks={tasks} /> : null}
              </DragOverlay>
            </DndContext>
          )}

          <aside className={`${styles.preview} ${mobileDetailOpen ? styles.previewOpen : ""}`}>
            {selectedLead && selectedStatus && selectedAction ? (
              <>
                <header>
                  <div><span>Seller preview</span><h2>{selectedLead.seller_name}</h2><p>{selectedLead.property_address}</p></div>
                  <button aria-label="Close seller preview" onClick={() => setMobileDetailOpen(false)} type="button"><X size={17} /></button>
                </header>
                <div className={styles.previewStatus}>
                  <StatusBadge tone={operatingTone(selectedStatus)}>{selectedStatus}</StatusBadge>
                  <span>{labelize(selectedLead.asset_class)} · {labelize(selectedLead.stage_key)}</span>
                </div>
                {canEditLead ? (
                  <label className={styles.moveControl}>
                    <span>Move to stage</span>
                    <select
                      aria-label={`Move ${selectedLead.seller_name} to pipeline stage`}
                      disabled={
                        pendingLeadIds.has(selectedLead.id) ||
                        getPipelineStage(selectedLead.stage_key)?.key === "under_contract"
                      }
                      onChange={(event) => {
                        const targetStage = pipelineStages.find((item) => item.key === event.target.value);
                        if (targetStage) void moveLeadToStage(selectedLead.id, targetStage);
                      }}
                      value={getPipelineStage(selectedLead.stage_key)?.key ?? ""}
                    >
                      {pipelineStages.map((pipelineStage) => (
                        <option
                          disabled={!leadCanEnterPipelineStage(selectedLead, pipelineStage)}
                          key={pipelineStage.key}
                          title={pipelineStageMoveBlockReason(selectedLead, pipelineStage) ?? undefined}
                          value={pipelineStage.key}
                        >
                          {pipelineStage.label}
                        </option>
                      ))}
                    </select>
                    <small>
                      {pendingLeadIds.has(selectedLead.id)
                        ? "Saving stage…"
                        : getPipelineStage(selectedLead.stage_key)?.key === "under_contract"
                          ? "Under-contract stages move through Contract & Deal."
                          : "Available on keyboard and mobile. Offer and contract stages use their controlled workflows."}
                    </small>
                  </label>
                ) : null}
                <dl>
                  <div><dt>Owner</dt><dd>{ownerLabel(selectedLead.assigned_user_email)}</dd></div>
                  <div><dt>Source</dt><dd>{labelize(selectedLead.source)}</dd></div>
                  <div><dt>Lead type</dt><dd>{labelize(selectedLead.asset_class)}</dd></div>
                  <div><dt>Parcel / APN</dt><dd>{selectedLead.property_parcel_id ?? "Not captured"}</dd></div>
                  <div><dt>Created</dt><dd>{formatDateTime(selectedLead.created_at)}</dd></div>
                  <div><dt>Primary action</dt><dd>{selectedLead.primary_next_action?.title ?? "Not set"}</dd></div>
                  <div><dt>Action owner</dt><dd>{ownerLabel(selectedLead.primary_next_action?.responsible_user_email ?? null)}</dd></div>
                  <div><dt>Due</dt><dd>{formatDateTime(selectedLead.primary_next_action?.due_at ?? selectedLead.next_follow_up_at)}</dd></div>
                  <div><dt>Qualification</dt><dd>{isAddressOnlyLead(selectedLead) ? "Contact pending" : `${qualificationFieldCount(selectedLead)}/${qualificationFieldTarget}`}</dd></div>
                  <div><dt>Appointment</dt><dd>{labelize(selectedLead.appointment_status)}</dd></div>
                </dl>
                <section>
                  <h3>Seller context</h3>
                  <p><strong>Motivation</strong>{selectedLead.motivation ?? "Not confirmed"}</p>
                  <p><strong>Timeline</strong>{selectedLead.desired_timeline ?? "Not confirmed"}</p>
                  <p><strong>Condition</strong>{selectedLead.property_condition ?? "Not confirmed"}</p>
                </section>
                <div className={styles.previewActions}>
                  <Link className={styles.primaryAction} href={selectedAction.href}>{selectedAction.label}<ArrowRight size={15} /></Link>
                  {!isAddressOnlyLead(selectedLead) ? <Link href={`/os/inbox?lead=${selectedLead.id}`}><Inbox size={15} />Conversation</Link> : null}
                  <Link href={fullRecordHref(selectedLead.id)}><ExternalLink size={15} />Full record</Link>
                  {selectedLead.appointment_status ? <Link href={`/os/calendar`}><CalendarDays size={15} />Calendar</Link> : null}
                </div>
                {canEditLead ? (
                  <div className={styles.previewLifecycle}>
                    <LeadLifecycleActions
                      archived={false}
                      canArchiveRecords={false}
                      canEditLead={canEditLead}
                      leadId={selectedLead.id}
                      onCloseOutComplete={handleLeadClosed}
                      stageKey={selectedLead.stage_key}
                    />
                  </div>
                ) : null}
              </>
            ) : (
              <div className={styles.empty}><strong>No seller selected</strong><span>Select a lead to inspect its current context.</span></div>
            )}
          </aside>
          {mobileDetailOpen ? <button aria-label="Close seller preview" className={styles.backdrop} onClick={() => setMobileDetailOpen(false)} type="button" /> : null}
        </div>
      </section>
    </div>
  );
}
