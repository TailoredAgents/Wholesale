import type {
  ProspectingAttemptEvidenceStatus,
  ProspectingAttemptEvidenceSuggestion,
  ProspectingStructuredCallNotes,
} from "../../lib/api";

export type EvidenceTone = "neutral" | "progress" | "ready" | "warning" | "error";

export type EvidenceStatusPresentation = {
  label: string;
  detail: string;
  tone: EvidenceTone;
};

export const INITIAL_EVIDENCE_PRESENTATION: EvidenceStatusPresentation = {
  label: "Call evidence",
  detail: "Open this attempt to check its recording and AI notes.",
  tone: "neutral",
};

const STATUS_PRESENTATIONS: Record<
  ProspectingAttemptEvidenceStatus,
  EvidenceStatusPresentation
> = {
  unavailable: {
    label: "No call evidence",
    detail: "No retained recording or transcript is available for this attempt.",
    tone: "neutral",
  },
  recording_ready: {
    label: "Recording ready",
    detail: "The recording is ready. AI notes have not finished yet.",
    tone: "ready",
  },
  processing: {
    label: "AI notes processing",
    detail: "Stonegate is transcribing this call and preparing its notes.",
    tone: "progress",
  },
  ready: {
    label: "Call evidence ready",
    detail: "The recording, transcript, and AI notes are ready.",
    tone: "ready",
  },
  failed: {
    label: "AI retrying",
    detail: "Call intelligence hit a temporary problem and will retry automatically.",
    tone: "warning",
  },
  exhausted: {
    label: "AI notes need retry",
    detail: "Automatic retries stopped. An authorized user can queue another attempt.",
    tone: "error",
  },
};

export function evidenceStatusPresentation(
  status: ProspectingAttemptEvidenceStatus,
): EvidenceStatusPresentation {
  return STATUS_PRESENTATIONS[status];
}

type FactDefinition = {
  key: keyof ProspectingStructuredCallNotes;
  label: string;
};

const HOUSE_FACTS: FactDefinition[] = [
  { key: "motivation", label: "Motivation" },
  { key: "timeline", label: "Timeline" },
  { key: "property_condition", label: "Property condition" },
  { key: "occupancy_status", label: "Occupancy" },
  { key: "asking_price", label: "Asking price" },
  { key: "mortgage_balance", label: "Mortgage balance" },
  { key: "mortgage_or_title", label: "Mortgage / title" },
  { key: "next_action", label: "Next action" },
  { key: "appointment_details", label: "Appointment" },
];

const LAND_FACTS: FactDefinition[] = [
  { key: "parcel_id", label: "Parcel ID" },
  { key: "acreage", label: "Acreage" },
  { key: "legal_description", label: "Legal description" },
  { key: "access_or_frontage", label: "Access / frontage" },
  { key: "utilities", label: "Utilities" },
  { key: "zoning_or_use", label: "Zoning / use" },
  { key: "septic_or_perc", label: "Septic / perc" },
  { key: "taxes_or_hoa", label: "Taxes / HOA" },
  { key: "terrain_or_environmental_concerns", label: "Terrain / environmental" },
];

export type EvidenceFact = {
  key: string;
  label: string;
  value: string;
};

function readableValue(value: unknown): string | null {
  if (typeof value === "string") return value.trim() || null;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const values = value.map(readableValue).filter((item): item is string => Boolean(item));
    return values.length ? values.join("; ") : null;
  }
  return null;
}

export function buildEvidenceFacts(
  notes: ProspectingStructuredCallNotes,
): EvidenceFact[] {
  const facts = [...HOUSE_FACTS, ...LAND_FACTS]
    .map(({ key, label }) => ({
      key: String(key),
      label,
      value: readableValue(notes[key]),
    }))
    .filter((fact): fact is EvidenceFact => Boolean(fact.value));

  return [
    ...facts,
    ...(["repairs", "objections", "commitments"] as const).flatMap((key) => {
      const value = readableValue(notes[key]);
      return value
        ? [{ key, label: key[0].toUpperCase() + key.slice(1), value }]
        : [];
    }),
  ];
}

export function suggestionPresentation(
  suggestion: ProspectingAttemptEvidenceSuggestion,
): { label: string; tone: "ready" | "warning" | "error" } {
  if (suggestion.state === "conflict") {
    return { label: "Conflict to review", tone: "error" };
  }
  if (suggestion.state === "corroborated") {
    return { label: "Confirmed by call", tone: "ready" };
  }
  return { label: "AI suggestion", tone: "warning" };
}

export function formatSuggestionValue(value: unknown): string {
  return readableValue(value) ?? "Not captured";
}

export function formatEvidenceTimestamp(seconds: number): string {
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}
