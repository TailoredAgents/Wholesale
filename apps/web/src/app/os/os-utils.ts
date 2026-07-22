import type { LeadListItem, SpeedToLeadTask } from "../lib/api";

export const pipelineStages = [
  { key: "new", label: "New", stageKeys: ["new", "contact_attempt_due", "reopened"] },
  { key: "contacting", label: "Contacting", stageKeys: ["attempting_contact"] },
  { key: "contacted", label: "Contacted", stageKeys: ["contacted"] },
  { key: "qualifying", label: "Qualifying", stageKeys: ["qualification_in_progress"] },
  {
    key: "qualified",
    label: "Qualified",
    stageKeys: ["qualified", "qualification_complete"],
  },
  {
    key: "appointment",
    label: "Appointment",
    stageKeys: ["appointment_scheduling", "appointment_set", "appointment_scheduled"],
  },
  { key: "underwriting", label: "Underwriting", stageKeys: ["underwriting"] },
  {
    key: "offer",
    label: "Offer",
    stageKeys: ["offer_pending_approval", "offer_ready", "offer_presented", "negotiating"],
  },
  { key: "nurture", label: "Nurture", stageKeys: ["long_term_follow_up"] },
  { key: "under_contract", label: "Under contract", stageKeys: ["under_contract"] },
] as const;

export const boardStages = pipelineStages.slice(0, 6);
const terminalStages = new Set(["dead", "disqualified", "under_contract"]);
const paidLeadSources = new Set([
  "google_ppc",
  "meta_ads",
  "facebook_ads",
  "instagram_ads",
  "website",
]);
const urgentTimelineSignals = ["asap", "now", "immediately", "30"];

export const qualificationFieldTarget = 7;

export const savedLeadViews = [
  {
    key: "all",
    label: "All Leads",
    description: "Every seller record in the active database.",
  },
  {
    key: "urgent",
    label: "Urgent",
    description: "Hot, fast-timeline, or overdue leads.",
  },
  {
    key: "needs_qualification",
    label: "Needs Qualification",
    description: "Missing facts required before underwriting.",
  },
  {
    key: "no_follow_up",
    label: "No Follow-Up",
    description: "Active leads without the next dated task.",
  },
  {
    key: "appointments",
    label: "Appointments",
    description: "Qualified leads that need appointment work.",
  },
  {
    key: "offers",
    label: "Offer Prep",
    description: "Leads ready for underwriting or offer approval.",
  },
  {
    key: "paid",
    label: "Paid Sources",
    description: "Leads from paid or public website channels.",
  },
  {
    key: "nurture",
    label: "Nurture",
    description: "Long-term follow-up and negotiation leads.",
  },
] as const;

export type SavedLeadViewKey = (typeof savedLeadViews)[number]["key"];

export function formatMoney(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

export function labelize(value: string | null) {
  if (!value) {
    return "None";
  }
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function formatTime(value: string | null) {
  if (!value) {
    return "Unscheduled";
  }
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDateTime(value: string | null) {
  if (!value) {
    return "Unscheduled";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function qualificationFieldCount(
  lead: Pick<
    LeadListItem,
    | "motivation"
    | "desired_timeline"
    | "property_condition"
    | "occupancy_status"
    | "asking_price"
    | "mortgage_balance"
    | "appointment_status"
  >,
) {
  return [
    lead.motivation,
    lead.desired_timeline,
    lead.property_condition,
    lead.occupancy_status,
    lead.asking_price,
    lead.mortgage_balance,
    lead.appointment_status,
  ].filter(Boolean).length;
}

export function getWorkspaceQueues(leads: LeadListItem[], openTasks: SpeedToLeadTask[]) {
  return {
    overdueTasks: openTasks.filter((task) => task.due_status === "overdue"),
    dueTasks: openTasks.filter((task) => task.due_status === "due"),
    needsQualification: leads.filter(
      (lead) =>
        ["new", "contacted", "qualification_in_progress"].includes(lead.stage_key) &&
        qualificationFieldCount(lead) < qualificationFieldTarget,
    ),
    appointmentQueue: leads.filter(
      (lead) =>
        [
          "qualified",
          "qualification_complete",
          "appointment_scheduling",
          "appointment_set",
          "appointment_scheduled",
        ].includes(lead.stage_key) ||
        ["appointment_requested", "not_scheduled"].includes(lead.appointment_status ?? ""),
    ),
    offerQueue: leads.filter((lead) =>
      ["underwriting", "offer_pending_approval", "offer_ready"].includes(lead.stage_key),
    ),
  };
}

export function getTaskCountsByLead(openTasks: SpeedToLeadTask[]) {
  return openTasks.reduce((counts, task) => {
    counts.set(task.lead_id, (counts.get(task.lead_id) ?? 0) + 1);
    return counts;
  }, new Map<string, number>());
}

export function normalizeLeadViewKey(value: string | string[] | null | undefined) {
  const viewKey = Array.isArray(value) ? value[0] : value;
  return savedLeadViews.some((view) => view.key === viewKey)
    ? (viewKey as SavedLeadViewKey)
    : "all";
}

export function getSavedLeadViewCounts(leads: LeadListItem[], openTasks: SpeedToLeadTask[]) {
  return savedLeadViews.map((view) => ({
    ...view,
    count: getFilteredLeads(leads, openTasks, view.key).length,
  }));
}

export function getFilteredLeads(
  leads: LeadListItem[],
  openTasks: SpeedToLeadTask[],
  viewKey: SavedLeadViewKey,
) {
  return sortLeadsForWork(
    leads.filter((lead) => leadMatchesView(lead, openTasks, viewKey)),
    openTasks,
  );
}

export function getLeadOperatingStatus(lead: LeadListItem, openTasks: SpeedToLeadTask[]) {
  if (lead.stage_key === "under_contract") {
    return "Under contract";
  }
  if (["dead", "disqualified"].includes(lead.stage_key)) {
    return "Closed out";
  }
  const leadTasks = openTasks.filter((task) => task.lead_id === lead.id);
  if (leadTasks.some((task) => task.due_status === "overdue")) {
    return "Overdue follow-up";
  }
  if (
    ["new", "contact_attempt_due", "attempting_contact", "contacted", "qualification_in_progress"].includes(
      lead.stage_key,
    ) && qualificationFieldCount(lead) < qualificationFieldTarget
  ) {
    return "Needs qualification";
  }
  if (
    [
      "qualified",
      "qualification_complete",
      "appointment_scheduling",
      "appointment_set",
      "appointment_scheduled",
    ].includes(lead.stage_key)
  ) {
    return "Appointment work";
  }
  if (["underwriting", "offer_pending_approval", "offer_ready"].includes(lead.stage_key)) {
    return "Offer prep";
  }
  if (["offer_presented", "negotiating"].includes(lead.stage_key)) {
    return "Negotiation";
  }
  if (lead.stage_key === "long_term_follow_up") {
    return "Nurture";
  }
  if (!lead.next_follow_up_at && !terminalStages.has(lead.stage_key)) {
    return "Needs follow-up";
  }
  return "On track";
}

export function getPipelineStage(stageKey: string) {
  return pipelineStages.find((stage) => (stage.stageKeys as readonly string[]).includes(stageKey));
}

export function getPipelineStageCount(
  stage: (typeof pipelineStages)[number],
  counts: Map<string, number>,
) {
  return stage.stageKeys.reduce((total, stageKey) => total + (counts.get(stageKey) ?? 0), 0);
}

function leadMatchesView(
  lead: LeadListItem,
  openTasks: SpeedToLeadTask[],
  viewKey: SavedLeadViewKey,
) {
  if (viewKey === "all") {
    return true;
  }
  if (viewKey === "urgent") {
    return (
      lead.lead_temperature === "hot" ||
      hasUrgentTimeline(lead) ||
      openTasks.some((task) => task.lead_id === lead.id && task.due_status === "overdue")
    );
  }
  if (viewKey === "needs_qualification") {
    return (
      ["new", "contacted", "qualification_in_progress"].includes(lead.stage_key) &&
      qualificationFieldCount(lead) < qualificationFieldTarget
    );
  }
  if (viewKey === "no_follow_up") {
    return !lead.next_follow_up_at && !terminalStages.has(lead.stage_key);
  }
  if (viewKey === "appointments") {
    return (
      [
        "qualified",
        "qualification_complete",
        "appointment_scheduling",
        "appointment_set",
        "appointment_scheduled",
      ].includes(lead.stage_key) ||
      ["appointment_requested", "not_scheduled"].includes(lead.appointment_status ?? "")
    );
  }
  if (viewKey === "offers") {
    return ["underwriting", "offer_pending_approval", "offer_ready"].includes(lead.stage_key);
  }
  if (viewKey === "paid") {
    return paidLeadSources.has(lead.source);
  }
  return ["long_term_follow_up", "negotiating", "offer_presented"].includes(lead.stage_key);
}

function sortLeadsForWork(leads: LeadListItem[], openTasks: SpeedToLeadTask[]) {
  return [...leads].sort(
    (first, second) => leadWorkRank(second, openTasks) - leadWorkRank(first, openTasks),
  );
}

function leadWorkRank(lead: LeadListItem, openTasks: SpeedToLeadTask[]) {
  let rank = 0;
  if (lead.lead_temperature === "hot") {
    rank += 40;
  }
  if (hasUrgentTimeline(lead)) {
    rank += 30;
  }
  if (openTasks.some((task) => task.lead_id === lead.id && task.due_status === "overdue")) {
    rank += 35;
  }
  if (qualificationFieldCount(lead) < qualificationFieldTarget) {
    rank += 15;
  }
  if (paidLeadSources.has(lead.source)) {
    rank += 10;
  }
  return rank;
}

function hasUrgentTimeline(lead: Pick<LeadListItem, "desired_timeline">) {
  const timeline = (lead.desired_timeline ?? "").toLowerCase();
  return urgentTimelineSignals.some((signal) => timeline.includes(signal));
}
