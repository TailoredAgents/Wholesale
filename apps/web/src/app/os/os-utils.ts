import type { LeadListItem, SpeedToLeadTask } from "../lib/api";

export const pipelineStages = [
  { key: "new", label: "New" },
  { key: "attempting_contact", label: "Attempting contact" },
  { key: "contacted", label: "Contacted" },
  { key: "qualification_in_progress", label: "Qualifying" },
  { key: "qualified", label: "Qualified" },
  { key: "appointment_scheduled", label: "Appointment" },
  { key: "underwriting", label: "Underwriting" },
  { key: "offer_ready", label: "Offer ready" },
  { key: "under_contract", label: "Under contract" },
];

export const boardStages = pipelineStages.slice(0, 6);

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
  lead: Pick<LeadListItem, "motivation" | "desired_timeline" | "property_condition">,
) {
  return [lead.motivation, lead.desired_timeline, lead.property_condition].filter(Boolean).length;
}

export function getWorkspaceQueues(leads: LeadListItem[], openTasks: SpeedToLeadTask[]) {
  return {
    overdueTasks: openTasks.filter((task) => task.due_status === "overdue"),
    dueTasks: openTasks.filter((task) => task.due_status === "due"),
    needsQualification: leads.filter(
      (lead) =>
        ["new", "contacted", "qualification_in_progress"].includes(lead.stage_key) &&
        qualificationFieldCount(lead) < 3,
    ),
    appointmentQueue: leads.filter(
      (lead) =>
        ["qualified", "appointment_scheduled"].includes(lead.stage_key) ||
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
