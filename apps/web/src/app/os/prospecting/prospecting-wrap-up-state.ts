import type { ProspectingEntry, ProspectingSellerOutcome } from "../../lib/api";

export type ProspectingOutcomeOption = {
  key: ProspectingSellerOutcome;
  label: string;
  description: string;
  automation: string;
  group: "unreached" | "continue" | "close";
};

export const PROSPECTING_OUTCOME_OPTIONS: readonly ProspectingOutcomeOption[] = [
  {
    key: "no_answer",
    label: "No answer",
    description: "The seller did not answer.",
    automation: "Stonegate schedules the campaign's next no-answer attempt.",
    group: "unreached",
  },
  {
    key: "left_voicemail",
    label: "Left voicemail",
    description: "A voicemail was left successfully.",
    automation: "Stonegate schedules the campaign's voicemail retry delay.",
    group: "unreached",
  },
  {
    key: "callback_requested",
    label: "Callback requested",
    description: "The seller asked for a specific callback.",
    automation: "A future callback is required and will move to the top when due.",
    group: "continue",
  },
  {
    key: "follow_up",
    label: "Follow up later",
    description: "Continue the conversation at a specific time.",
    automation: "A future follow-up is required and will return when due.",
    group: "continue",
  },
  {
    key: "interested",
    label: "Interested seller",
    description: "The seller is qualified for acquisitions review.",
    automation: "Stonegate creates or reuses one warm lead and one reviewable handoff.",
    group: "continue",
  },
  {
    key: "appointment_set",
    label: "Appointment set",
    description: "The seller agreed to a scheduled meeting.",
    automation: "Stonegate creates or reuses one warm lead, handoff, and appointment.",
    group: "continue",
  },
  {
    key: "not_interested",
    label: "Not interested",
    description: "The seller declined further routine prospecting.",
    automation: "This prospect leaves the routine calling queue.",
    group: "close",
  },
  {
    key: "wrong_number",
    label: "Wrong number",
    description: "The dialed number does not reach this seller.",
    automation: "Stonegate blocks that exact number and uses another eligible ranked number only.",
    group: "close",
  },
  {
    key: "do_not_call",
    label: "Do not call",
    description: "The person asked Stonegate to stop calling.",
    automation: "Stonegate suppresses the exact number immediately and stops future dialing.",
    group: "close",
  },
] as const;

export const PROSPECTING_OUTCOME_GROUPS = [
  { key: "unreached", label: "Could not reach seller" },
  { key: "continue", label: "Continue with seller" },
  { key: "close", label: "Stop or correct dialing" },
] as const;

export type ProspectingWrapUpValidation = {
  outcome: ProspectingSellerOutcome;
  callbackAt: string;
  handoffUserId: string;
  appointmentStartAt: string;
  appointmentLocationType: string;
  appointmentLocation: string;
  propertyAddress: string | null;
  qualificationSaveBlocked: boolean;
  missingWarmHandoffCount: number;
  nativeDialer: boolean;
  nativeWrapUpReady: boolean;
  technicalFailure: boolean;
  now?: Date;
};

export type ProspectingWrapUpReceipt = {
  attemptId: string;
  outcome: ProspectingSellerOutcome | "technical_failure";
  sellerName: string;
  title: string;
  detail: string;
  nextAction: string;
  tone: "scheduled" | "warm" | "closed" | "suppressed" | "technical";
  savedStatus: string;
  nextAttemptAt: string | null;
};

export function prospectingOutcomeOption(outcome: ProspectingSellerOutcome) {
  return PROSPECTING_OUTCOME_OPTIONS.find((option) => option.key === outcome)!;
}

function validFutureDate(value: string, now: Date) {
  if (!value) return false;
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) && parsed.getTime() > now.getTime();
}

export function validateProspectingWrapUp(
  input: ProspectingWrapUpValidation,
): string | null {
  if (input.qualificationSaveBlocked) {
    return "Finish saving or reconcile the highlighted qualification answer first.";
  }
  if (input.technicalFailure) {
    return "This was a technical call failure, not a seller outcome. Record the technical failure instead.";
  }
  if (input.nativeDialer && !input.nativeWrapUpReady) {
    return "Wait until the seller call reaches wrap-up before saving its outcome.";
  }

  const now = input.now ?? new Date();
  if (["callback_requested", "follow_up"].includes(input.outcome)) {
    if (!validFutureDate(input.callbackAt, now)) {
      return "Choose a future callback date and time.";
    }
  }
  if (["interested", "appointment_set"].includes(input.outcome)) {
    if (input.missingWarmHandoffCount > 0) {
      return "Complete every required warm-handoff question first.";
    }
    if (!input.handoffUserId) {
      return "Choose the acquisitions owner who will receive this seller.";
    }
  }
  if (input.outcome === "appointment_set") {
    if (!validFutureDate(input.appointmentStartAt, now)) {
      return "Choose a future appointment date and time.";
    }
    if (!input.appointmentLocationType) {
      return "Choose the appointment meeting type.";
    }
    const hasExplicitLocation = Boolean(input.appointmentLocation.trim());
    const canUsePropertyFallback =
      input.appointmentLocationType === "seller_property" &&
      Boolean(input.propertyAddress?.trim());
    if (!hasExplicitLocation && !canUsePropertyFallback) {
      return "Enter where the appointment will happen.";
    }
  }
  return null;
}

export function createProspectingWrapUpReceipt(
  entry: ProspectingEntry,
  outcome: ProspectingSellerOutcome,
  attemptId: string,
  dialedNumber: string | null = null,
): ProspectingWrapUpReceipt {
  const nextAttemptAt = entry.next_attempt_at;
  if (outcome === "no_answer" || outcome === "left_voicemail") {
    return {
      attemptId,
      outcome,
      sellerName: entry.legal_name,
      title: nextAttemptAt ? "Retry scheduled" : "Call attempt saved",
      detail:
        outcome === "left_voicemail"
          ? "The voicemail result was saved without treating it as a seller rejection."
          : "The unanswered call was saved without treating it as a seller rejection.",
      nextAction: nextAttemptAt
        ? `This prospect returns to the cadence at ${nextAttemptAt}.`
        : "Stonegate saved the server's final queue state.",
      tone: "scheduled",
      savedStatus: entry.status,
      nextAttemptAt,
    };
  }
  if (outcome === "callback_requested" || outcome === "follow_up") {
    return {
      attemptId,
      outcome,
      sellerName: entry.legal_name,
      title: outcome === "callback_requested" ? "Callback scheduled" : "Follow-up scheduled",
      detail: "The seller remains in Prospecting and will be prioritized when the commitment is due.",
      nextAction: nextAttemptAt
        ? `Due at ${nextAttemptAt}.`
        : "The server accepted the commitment and returned its current queue state.",
      tone: "scheduled",
      savedStatus: entry.status,
      nextAttemptAt,
    };
  }
  if (outcome === "interested" || outcome === "appointment_set") {
    return {
      attemptId,
      outcome,
      sellerName: entry.legal_name,
      title: outcome === "appointment_set" ? "Lead and appointment saved" : "Warm lead handoff saved",
      detail:
        outcome === "appointment_set"
          ? "Stonegate accepted the seller handoff and appointment as one idempotent wrap-up."
          : "Stonegate accepted one reviewable warm-lead handoff for acquisitions.",
      nextAction: "The record is now waiting in the acquisitions handoff workflow.",
      tone: "warm",
      savedStatus: entry.status,
      nextAttemptAt,
    };
  }
  if (outcome === "do_not_call") {
    return {
      attemptId,
      outcome,
      sellerName: entry.legal_name,
      title: "Do-not-call request saved",
      detail: dialedNumber
        ? `The server suppressed exactly ${dialedNumber} and removed it from routine dialing.`
        : "The server accepted the exact dialed-number suppression and removed it from routine dialing.",
      nextAction: "No future prospecting call will be started for the suppressed number.",
      tone: "suppressed",
      savedStatus: entry.status,
      nextAttemptAt,
    };
  }
  return {
    attemptId,
    outcome,
    sellerName: entry.legal_name,
    title: outcome === "wrong_number" ? "Number marked wrong" : "Prospect closed",
    detail:
      outcome === "wrong_number"
        ? "Stonegate accepted the number correction and will use another eligible ranked number only if one remains."
        : "The seller's response was saved and routine prospecting stopped.",
    nextAction: nextAttemptAt
      ? `Another eligible number is due at ${nextAttemptAt}.`
      : "No further routine attempt is scheduled.",
    tone: "closed",
    savedStatus: entry.status,
    nextAttemptAt,
  };
}

export function createTechnicalFailureReceipt(
  entry: ProspectingEntry,
  attemptId: string,
): ProspectingWrapUpReceipt {
  return {
    attemptId,
    outcome: "technical_failure",
    sellerName: entry.legal_name,
    title: "Technical call failure saved",
    detail: "The provider problem was preserved separately and was not counted as a seller disposition.",
    nextAction: entry.next_attempt_at
      ? `The prospect can be retried at ${entry.next_attempt_at}.`
      : "Stonegate returned the prospect to its safe server-controlled queue state.",
    tone: "technical",
    savedStatus: entry.status,
    nextAttemptAt: entry.next_attempt_at,
  };
}
