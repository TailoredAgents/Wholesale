import type { LeadListItem, SpeedToLeadTask } from "../lib/api";

export const pipelineStages = [
  {
    key: "new",
    label: "New",
    dropStageKey: "new",
    stageKeys: ["new", "contact_attempt_due", "reopened"],
  },
  {
    key: "contacting",
    label: "Contacting",
    dropStageKey: "attempting_contact",
    stageKeys: ["attempting_contact"],
  },
  {
    key: "contacted",
    label: "Contacted",
    dropStageKey: "contacted",
    stageKeys: ["contacted"],
  },
  {
    key: "qualifying",
    label: "Qualifying",
    dropStageKey: "qualification_in_progress",
    stageKeys: ["qualification_in_progress"],
  },
  {
    key: "qualified",
    label: "Qualified",
    dropStageKey: "qualified",
    stageKeys: ["qualified", "qualification_complete"],
  },
  {
    key: "appointment",
    label: "Appointment",
    dropStageKey: "appointment_scheduling",
    stageKeys: ["appointment_scheduling", "appointment_set", "appointment_scheduled"],
  },
  {
    key: "underwriting",
    label: "Underwriting",
    dropStageKey: "underwriting",
    stageKeys: ["underwriting"],
  },
  {
    key: "offer",
    label: "Offer",
    dropStageKey: "offer_pending_approval",
    stageKeys: ["offer_pending_approval", "offer_ready", "offer_presented", "negotiating"],
  },
  {
    key: "nurture",
    label: "Nurture",
    dropStageKey: "long_term_follow_up",
    stageKeys: ["long_term_follow_up"],
  },
  {
    key: "under_contract",
    label: "Under contract",
    dropStageKey: "under_contract",
    stageKeys: ["under_contract"],
  },
] as const;

export type PipelineStage = (typeof pipelineStages)[number];

export function leadCanEnterPipelineStage(
  lead: Pick<LeadListItem, "asset_class" | "stage_key">,
  stage: PipelineStage,
) {
  return pipelineStageMoveBlockReason(lead, stage) === null;
}

export function pipelineStageMoveBlockReason(
  lead: Pick<LeadListItem, "asset_class" | "stage_key">,
  stage: PipelineStage,
) {
  if (getPipelineStage(lead.stage_key)?.key === "under_contract") {
    return "Under-contract leads move through the Contract & Deal workflow.";
  }
  if (stage.key === "offer") {
    return "Offer stages move through the Valuation & Offer workflow.";
  }
  if (stage.key === "under_contract") {
    return "Under-contract status requires the signed-contract workflow.";
  }
  return null;
}

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
    key: "address_only",
    label: "Address Only",
    description: "Incomplete website forms ready for owner research and skip tracing.",
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

export const leadSortOptions = [
  { key: "newest", label: "Newest" },
  { key: "oldest", label: "Oldest" },
  { key: "priority", label: "Highest priority" },
] as const;

export type LeadSortKey = (typeof leadSortOptions)[number]["key"];

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

export function internalCode(value: string) {
  const normalized = value
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 80);
  return normalized.length >= 2 ? normalized : `${normalized || "area"}-market`;
}

export function apiErrorMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const error = item as { loc?: unknown; msg?: unknown };
        if (typeof error.msg !== "string") return null;
        const location = Array.isArray(error.loc) ? error.loc.at(-1) : null;
        const field = typeof location === "string" ? labelize(location) : null;
        return field ? `${field}: ${error.msg}` : error.msg;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length) return messages.join(" ");
  }
  return fallback;
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
  const operationalLeads = leads.filter((lead) => !isAddressOnlyLead(lead));
  return {
    overdueTasks: openTasks.filter((task) => task.due_status === "overdue"),
    dueTasks: openTasks.filter((task) => task.due_status === "due"),
    needsQualification: operationalLeads.filter(
      (lead) =>
        ["new", "contacted", "qualification_in_progress"].includes(lead.stage_key) &&
        qualificationFieldCount(lead) < qualificationFieldTarget,
    ),
    appointmentQueue: operationalLeads.filter(
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
    offerQueue: operationalLeads.filter((lead) =>
      ["underwriting", "offer_pending_approval", "offer_ready"].includes(lead.stage_key),
    ),
  };
}

export function getTaskCountsByLead(openTasks: SpeedToLeadTask[]) {
  return openTasks.reduce((counts, task) => {
    if (!task.lead_id) return counts;
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

export function defaultLeadSortKey(viewKey: SavedLeadViewKey): LeadSortKey {
  return ["all", "address_only"].includes(viewKey) ? "newest" : "priority";
}

export function normalizeLeadSortKey(
  value: string | string[] | null | undefined,
  viewKey: SavedLeadViewKey,
): LeadSortKey {
  const sortKey = Array.isArray(value) ? value[0] : value;
  return leadSortOptions.some((option) => option.key === sortKey)
    ? (sortKey as LeadSortKey)
    : defaultLeadSortKey(viewKey);
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
  sortKey: LeadSortKey = defaultLeadSortKey(viewKey),
) {
  return sortLeads(
    leads.filter((lead) => leadMatchesView(lead, openTasks, viewKey)),
    openTasks,
    sortKey,
  );
}

export function getLeadOperatingStatus(lead: LeadListItem, openTasks: SpeedToLeadTask[]) {
  if (isAddressOnlyLead(lead)) {
    return "Skip trace needed";
  }
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
  if (viewKey === "address_only") {
    return isAddressOnlyLead(lead);
  }
  if (isAddressOnlyLead(lead)) {
    return false;
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

function sortLeads(
  leads: LeadListItem[],
  openTasks: SpeedToLeadTask[],
  sortKey: LeadSortKey,
) {
  return [...leads].sort((first, second) => {
    const firstCreatedAt = Date.parse(first.created_at);
    const secondCreatedAt = Date.parse(second.created_at);
    const createdDifference =
      (Number.isNaN(secondCreatedAt) ? 0 : secondCreatedAt) -
      (Number.isNaN(firstCreatedAt) ? 0 : firstCreatedAt);
    if (sortKey === "newest") {
      return createdDifference || first.id.localeCompare(second.id);
    }
    if (sortKey === "oldest") {
      return -createdDifference || first.id.localeCompare(second.id);
    }
    return (
      leadWorkRank(second, openTasks) - leadWorkRank(first, openTasks) ||
      createdDifference ||
      first.id.localeCompare(second.id)
    );
  });
}

function leadWorkRank(lead: LeadListItem, openTasks: SpeedToLeadTask[]) {
  if (isAddressOnlyLead(lead)) {
    return 0;
  }
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

export function isAddressOnlyLead(
  lead: Pick<LeadListItem, "qualification_context">,
) {
  return lead.qualification_context?.website_intake_status === "address_only";
}

function hasUrgentTimeline(lead: Pick<LeadListItem, "desired_timeline">) {
  const timeline = (lead.desired_timeline ?? "").toLowerCase();
  return urgentTimelineSignals.some((signal) => timeline.includes(signal));
}
