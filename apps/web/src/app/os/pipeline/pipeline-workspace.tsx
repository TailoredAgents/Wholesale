"use client";

import { ArrowRight, ExternalLink, Inbox, Search, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import type { LeadListItem, SpeedToLeadTask } from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import {
  formatDateTime,
  getLeadOperatingStatus,
  getPipelineStage,
  labelize,
  pipelineStages,
  qualificationFieldCount,
  qualificationFieldTarget,
} from "../os-utils";
import styles from "./pipeline-workspace.module.css";

function ownerLabel(email: string | null) {
  if (!email) return "Unassigned";
  return email.split("@")[0]?.replace(/[._-]+/g, " ") || email;
}

function statusTone(status: string): "danger" | "warning" | "info" | "success" | "neutral" {
  if (status === "Overdue follow-up") return "danger";
  if (["Needs qualification", "Needs follow-up"].includes(status)) return "warning";
  if (["Appointment work", "Offer prep", "Negotiation"].includes(status)) return "info";
  if (status === "Under contract") return "success";
  return "neutral";
}

function nextAction(lead: LeadListItem, tasks: SpeedToLeadTask[]) {
  const status = getLeadOperatingStatus(lead, tasks);
  if (status === "Overdue follow-up") return { href: `/os/inbox?lead=${lead.id}`, label: "Reply now" };
  if (status === "Needs qualification") return { href: `/os/lead-manager?lead=${lead.id}`, label: "Qualify" };
  if (status === "Appointment work") return { href: `/os/field-operations?view=dispatch&lead=${lead.id}`, label: "Schedule" };
  if (status === "Offer prep") return { href: `/os/leads/${lead.id}#underwriting`, label: "Prepare offer" };
  if (status === "Negotiation") return { href: `/os/leads/${lead.id}#negotiation`, label: "Negotiate" };
  if (status === "Nurture") return { href: `/os/inbox?lead=${lead.id}`, label: "Follow up" };
  return { href: `/os/leads/${lead.id}`, label: "Open record" };
}

export function PipelineWorkspace({
  initialStage,
  leads,
  tasks,
}: {
  initialStage: string;
  leads: LeadListItem[];
  tasks: SpeedToLeadTask[];
}) {
  const router = useRouter();
  const [stage, setStage] = useState(initialStage);
  const [owner, setOwner] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const owners = useMemo(
    () => Array.from(new Set(leads.map((lead) => lead.assigned_user_email).filter((item): item is string => Boolean(item)))).sort(),
    [leads],
  );
  const filteredLeads = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return leads.filter((lead) => {
      const matchesSearch = !normalizedQuery || `${lead.seller_name} ${lead.property_address} ${lead.source}`.toLowerCase().includes(normalizedQuery);
      const matchesOwner = owner === "all" || (owner === "unassigned" && !lead.assigned_user_email) || lead.assigned_user_email === owner;
      const matchesStage = stage === "all" || getPipelineStage(lead.stage_key)?.key === stage;
      return matchesSearch && matchesOwner && matchesStage;
    });
  }, [leads, owner, query, stage]);
  const visibleStages = stage === "all" ? pipelineStages : pipelineStages.filter((item) => item.key === stage);
  const selectedLead = filteredLeads.find((lead) => lead.id === selectedId) ?? filteredLeads[0] ?? null;

  function chooseStage(value: string) {
    setStage(value);
    setSelectedId("");
    router.replace(value === "all" ? "/os/pipeline" : `/os/pipeline?stage=${value}`, { scroll: false });
  }

  return (
    <section className={styles.workspace}>
      <div className={styles.toolbar}>
        <label className={styles.search}>
          <Search aria-hidden="true" size={16} />
          <input aria-label="Search seller pipeline" onChange={(event) => setQuery(event.target.value)} placeholder="Search seller or property" type="search" value={query} />
        </label>
        <label><span>Owner</span><select onChange={(event) => setOwner(event.target.value)} value={owner}><option value="all">All owners</option><option value="unassigned">Unassigned</option>{owners.map((email) => <option key={email} value={email}>{ownerLabel(email)}</option>)}</select></label>
        <label><span>Stage</span><select onChange={(event) => chooseStage(event.target.value)} value={stage}><option value="all">All stages</option>{pipelineStages.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
        <strong>{filteredLeads.length} shown</strong>
      </div>

      <div className={styles.body}>
        <div className={styles.board}>
          {visibleStages.map((pipelineStage) => {
            const stageLeads = filteredLeads.filter((lead) => getPipelineStage(lead.stage_key)?.key === pipelineStage.key);
            return (
              <section className={styles.column} key={pipelineStage.key}>
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
                        onClick={() => { setSelectedId(lead.id); setMobileDetailOpen(true); }}
                        type="button"
                      >
                        <span className={styles.cardTop}><strong>{lead.seller_name}</strong><em>{labelize(lead.lead_temperature)}</em></span>
                        <span className={styles.address}>{lead.property_address}</span>
                        <StatusBadge tone={statusTone(operatingStatus)}>{operatingStatus}</StatusBadge>
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

        <aside className={`${styles.inspector} ${mobileDetailOpen ? styles.inspectorOpen : ""}`}>
          {selectedLead ? (
            <>
              <header><div><span>Pipeline context</span><h2>{selectedLead.seller_name}</h2><p>{selectedLead.property_address}</p></div><button aria-label="Close pipeline context" onClick={() => setMobileDetailOpen(false)} type="button"><X size={17} /></button></header>
              <div className={styles.inspectorStatus}><StatusBadge tone={statusTone(getLeadOperatingStatus(selectedLead, tasks))}>{getLeadOperatingStatus(selectedLead, tasks)}</StatusBadge><span>{getPipelineStage(selectedLead.stage_key)?.label ?? labelize(selectedLead.stage_key)}</span></div>
              <dl>
                <div><dt>Owner</dt><dd>{ownerLabel(selectedLead.assigned_user_email)}</dd></div>
                <div><dt>Source</dt><dd>{labelize(selectedLead.source)}</dd></div>
                <div><dt>Qualification</dt><dd>{qualificationFieldCount(selectedLead)}/{qualificationFieldTarget}</dd></div>
                <div><dt>Next action</dt><dd>{formatDateTime(selectedLead.next_follow_up_at)}</dd></div>
              </dl>
              <section><p><strong>Motivation</strong>{selectedLead.motivation ?? "Not confirmed"}</p><p><strong>Timeline</strong>{selectedLead.desired_timeline ?? "Not confirmed"}</p><p><strong>Condition</strong>{selectedLead.property_condition ?? "Not confirmed"}</p></section>
              <div className={styles.actions}>
                <Link className={styles.primary} href={nextAction(selectedLead, tasks).href}>{nextAction(selectedLead, tasks).label}<ArrowRight size={15} /></Link>
                <Link href={`/os/inbox?lead=${selectedLead.id}`}><Inbox size={15} />Conversation</Link>
                <Link href={`/os/leads/${selectedLead.id}`}><ExternalLink size={15} />Full record</Link>
              </div>
            </>
          ) : <div className={styles.empty}><strong>No lead selected</strong><span>Choose a pipeline card to inspect it.</span></div>}
        </aside>
        {mobileDetailOpen ? <button aria-label="Close pipeline context" className={styles.backdrop} onClick={() => setMobileDetailOpen(false)} type="button" /> : null}
      </div>
    </section>
  );
}
