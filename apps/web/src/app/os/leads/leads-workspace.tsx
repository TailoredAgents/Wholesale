"use client";

import {
  ArrowRight,
  CalendarDays,
  Columns3,
  ExternalLink,
  Inbox,
  Search,
  Table2,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import type { LeadListItem, SpeedToLeadTask } from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import {
  formatDateTime,
  getFilteredLeads,
  getLeadOperatingStatus,
  getPipelineStage,
  getSavedLeadViewCounts,
  labelize,
  pipelineStages,
  qualificationFieldCount,
  qualificationFieldTarget,
  type SavedLeadViewKey,
} from "../os-utils";
import styles from "./leads-workspace.module.css";

function ownerLabel(email: string | null) {
  if (!email) return "Unassigned";
  return email.split("@")[0]?.replace(/[._-]+/g, " ") || email;
}

function operatingTone(status: string): "danger" | "warning" | "info" | "success" | "neutral" {
  if (status === "Overdue follow-up") return "danger";
  if (["Needs qualification", "Needs follow-up"].includes(status)) return "warning";
  if (["Appointment work", "Offer prep", "Negotiation"].includes(status)) return "info";
  if (status === "Under contract") return "success";
  return "neutral";
}

function nextAction(lead: LeadListItem, tasks: SpeedToLeadTask[]) {
  const status = getLeadOperatingStatus(lead, tasks);
  if (status === "Overdue follow-up") {
    return { href: `/os/inbox?lead=${lead.id}`, label: "Continue conversation" };
  }
  if (status === "Needs qualification") {
    return { href: `/os/leads?view=queue&lead=${lead.id}`, label: "Open qualification queue" };
  }
  if (status === "Appointment work") {
    return { href: `/os/field-operations?view=dispatch&lead=${lead.id}`, label: "Open dispatch" };
  }
  if (status === "Offer prep") {
    return { href: `/os/leads/${lead.id}?tab=valuation`, label: "Prepare offer" };
  }
  if (status === "Negotiation") {
    return { href: `/os/leads/${lead.id}?tab=contract#negotiation`, label: "Continue negotiation" };
  }
  if (status === "Nurture") {
    return { href: `/os/inbox?lead=${lead.id}`, label: "Open follow-up" };
  }
  return { href: `/os/leads/${lead.id}`, label: "Open seller record" };
}

export function LeadsWorkspace({
  initialDisplay,
  initialLeadId,
  initialOwner,
  initialQuery,
  initialStage,
  initialView,
  leads,
  newPaidLeadCount,
  tasks,
}: {
  initialDisplay: "table" | "board";
  initialLeadId: string;
  initialOwner: string;
  initialQuery: string;
  initialStage: string;
  initialView: SavedLeadViewKey;
  leads: LeadListItem[];
  newPaidLeadCount: number;
  tasks: SpeedToLeadTask[];
}) {
  const [view, setView] = useState<SavedLeadViewKey>(initialView);
  const [display, setDisplay] = useState<"table" | "board">(initialDisplay);
  const [query, setQuery] = useState(initialQuery);
  const [owner, setOwner] = useState(initialOwner);
  const [stage, setStage] = useState(initialStage);
  const [selectedLeadId, setSelectedLeadId] = useState(initialLeadId);
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const viewCounts = useMemo(() => getSavedLeadViewCounts(leads, tasks), [leads, tasks]);
  const owners = useMemo(
    () =>
      Array.from(
        new Set(leads.map((lead) => lead.assigned_user_email).filter((email): email is string => Boolean(email))),
      ).sort(),
    [leads],
  );
  const baseLeads = useMemo(() => getFilteredLeads(leads, tasks, view), [leads, tasks, view]);
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
      return matchesQuery && matchesOwner && matchesStage;
    });
  }, [baseLeads, owner, query, stage]);
  const selectedLead =
    visibleLeads.find((lead) => lead.id === selectedLeadId) ?? visibleLeads[0] ?? null;
  const selectedStatus = selectedLead ? getLeadOperatingStatus(selectedLead, tasks) : null;
  const selectedAction = selectedLead ? nextAction(selectedLead, tasks) : null;
  const visibleStages =
    stage === "all"
      ? pipelineStages
      : pipelineStages.filter((item) => item.key === stage);
  const newLeadCount = leads.filter((lead) => lead.stage_key === "new").length;
  const qualifiedCount = leads.filter((lead) =>
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
  const unassignedCount = leads.filter((lead) => !lead.assigned_user_email).length;
  const withoutFollowUpCount = leads.filter(
    (lead) => !lead.next_follow_up_at && !["dead", "disqualified", "under_contract"].includes(lead.stage_key),
  ).length;

  function replaceLocation(overrides: {
    display?: "table" | "board";
    leadId?: string;
    owner?: string;
    query?: string;
    stage?: string;
    view?: SavedLeadViewKey;
  } = {}) {
    const next = {
      display: overrides.display ?? display,
      leadId: overrides.leadId ?? selectedLeadId,
      owner: overrides.owner ?? owner,
      query: overrides.query ?? query,
      stage: overrides.stage ?? stage,
      view: overrides.view ?? view,
    };
    const params = new URLSearchParams();
    if (next.view !== "all") params.set("view", next.view);
    if (next.display === "board") params.set("display", "board");
    if (next.query.trim()) params.set("q", next.query.trim());
    if (next.owner !== "all") params.set("owner", next.owner);
    if (next.stage !== "all") params.set("stage", next.stage);
    if (next.leadId) params.set("lead", next.leadId);
    const suffix = params.toString();
    window.history.replaceState(null, "", suffix ? `/os/leads?${suffix}` : "/os/leads");
  }

  function chooseView(nextView: SavedLeadViewKey) {
    setView(nextView);
    replaceLocation({ view: nextView });
  }

  function chooseDisplay(nextDisplay: "table" | "board") {
    setDisplay(nextDisplay);
    replaceLocation({ display: nextDisplay });
  }

  function selectLead(leadId: string) {
    setSelectedLeadId(leadId);
    setMobileDetailOpen(true);
    replaceLocation({ leadId });
  }

  return (
    <div className={styles.workspace}>
      <section className={styles.metrics} aria-label="Lead database summary" tabIndex={0}>
        <div><span>New</span><strong>{newLeadCount}</strong><small>First-contact records</small></div>
        <div><span>Qualified+</span><strong>{qualifiedCount}</strong><small>Appointment or offer work</small></div>
        <div><span>Unassigned</span><strong>{unassignedCount}</strong><small>Needs an owner</small></div>
        <div><span>No follow-up</span><strong>{withoutFollowUpCount}</strong><small>No dated next action</small></div>
        <div><span>Paid leads</span><strong>{newPaidLeadCount}</strong><small>New paid-source records</small></div>
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
            <select onChange={(event) => {
              setStage(event.target.value);
              replaceLocation({ stage: event.target.value });
            }} value={stage}>
              <option value="all">All stages</option>
              {pipelineStages.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
            </select>
          </label>
          <div aria-label="Lead display" className={styles.displayControl}>
            <button aria-pressed={display === "table"} onClick={() => chooseDisplay("table")} title="Table view" type="button"><Table2 aria-hidden="true" size={15} /><span>Table</span></button>
            <button aria-pressed={display === "board"} onClick={() => chooseDisplay("board")} title="Board view" type="button"><Columns3 aria-hidden="true" size={15} /><span>Board</span></button>
          </div>
          <strong>{visibleLeads.length} shown</strong>
        </div>

        <div className={`${styles.content} ${display === "board" ? styles.boardContent : ""}`}>
          {display === "table" ? <div className={styles.list}>
            <div className={styles.listHeader}>
              <span>Seller</span><span>Status</span><span>Owner</span><span>Next action</span>
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
                    <em>{labelize(lead.source)} · {labelize(lead.stage_key)}</em>
                  </span>
                  <StatusBadge tone={operatingTone(status)}>{status}</StatusBadge>
                  <span className={styles.owner}><UserRound aria-hidden="true" size={14} />{ownerLabel(lead.assigned_user_email)}</span>
                  <span className={styles.next}>
                    <strong>{action.label}</strong><small>{formatDateTime(lead.next_follow_up_at)}</small>
                  </span>
                </button>
              );
            })}
            {!visibleLeads.length ? (
              <div className={styles.empty}><strong>No leads match this view</strong><span>Change the view, owner, stage, or search.</span></div>
            ) : null}
          </div> : (
            <div className={styles.board}>
              {visibleStages.map((pipelineStage) => {
                const stageLeads = visibleLeads.filter(
                  (lead) => getPipelineStage(lead.stage_key)?.key === pipelineStage.key,
                );
                return (
                  <section className={styles.boardColumn} key={pipelineStage.key}>
                    <header><h2>{pipelineStage.label}</h2><strong>{stageLeads.length}</strong></header>
                    <div>
                      {stageLeads.map((lead) => {
                        const operatingStatus = getLeadOperatingStatus(lead, tasks);
                        const action = nextAction(lead, tasks);
                        return (
                          <button
                            aria-current={selectedLead?.id === lead.id ? "true" : undefined}
                            className={selectedLead?.id === lead.id ? styles.selectedCard : undefined}
                            key={lead.id}
                            onClick={() => selectLead(lead.id)}
                            type="button"
                          >
                            <span className={styles.cardTop}><strong>{lead.seller_name}</strong><em>{labelize(lead.lead_temperature)}</em></span>
                            <span className={styles.cardAddress}>{lead.property_address}</span>
                            <StatusBadge tone={operatingTone(operatingStatus)}>{operatingStatus}</StatusBadge>
                            <span className={styles.cardMeta}><span><UserRound size={13} />{ownerLabel(lead.assigned_user_email)}</span><span>{formatDateTime(lead.next_follow_up_at)}</span></span>
                            <span className={styles.cardAction}>{action.label}<ArrowRight size={13} /></span>
                          </button>
                        );
                      })}
                      {!stageLeads.length ? <p>No leads</p> : null}
                    </div>
                  </section>
                );
              })}
            </div>
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
                  <span>{labelize(selectedLead.stage_key)}</span>
                </div>
                <dl>
                  <div><dt>Owner</dt><dd>{ownerLabel(selectedLead.assigned_user_email)}</dd></div>
                  <div><dt>Source</dt><dd>{labelize(selectedLead.source)}</dd></div>
                  <div><dt>Created</dt><dd>{formatDateTime(selectedLead.created_at)}</dd></div>
                  <div><dt>Next follow-up</dt><dd>{formatDateTime(selectedLead.next_follow_up_at)}</dd></div>
                  <div><dt>Qualification</dt><dd>{qualificationFieldCount(selectedLead)}/{qualificationFieldTarget}</dd></div>
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
                  <Link href={`/os/inbox?lead=${selectedLead.id}`}><Inbox size={15} />Conversation</Link>
                  <Link href={`/os/leads/${selectedLead.id}`}><ExternalLink size={15} />Full record</Link>
                  {selectedLead.appointment_status ? <Link href={`/os/calendar`}><CalendarDays size={15} />Calendar</Link> : null}
                </div>
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
