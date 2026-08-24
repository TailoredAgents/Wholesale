export type LandQualificationState = "unknown" | "seller_reported" | "not_applicable";

export type LandSellerProfileField = {
  key: string;
  label: string;
  prompt: string;
  aliases: readonly string[];
  combineAliases?: boolean;
};

export const LAND_SELLER_PROFILE_FIELDS: readonly LandSellerProfileField[] = [
  {
    key: "ownership_decision_makers",
    label: "Ownership and decision makers",
    prompt: "Confirm the owners, how title is held, and everyone who must approve a sale.",
    aliases: ["ownership", "decision_makers"],
    combineAliases: true,
  },
  {
    key: "acreage",
    label: "Acreage",
    prompt: "Ask for the seller's approximate acreage; verify it against parcel records later.",
    aliases: ["lot_size_acres"],
  },
  {
    key: "access_frontage",
    label: "Access and frontage",
    prompt: "Ask about road frontage, deeded access, easements, and shared-road arrangements.",
    aliases: ["access_or_frontage"],
  },
  {
    key: "utilities",
    label: "Utilities",
    prompt: "Ask what is connected, at the road, nearby, or not known.",
    aliases: [],
  },
  {
    key: "survey_boundaries",
    label: "Survey and boundaries",
    prompt: "Ask whether a current survey exists and whether corners or boundaries are marked.",
    aliases: ["survey", "boundaries"],
  },
  {
    key: "zoning_use",
    label: "Zoning and known use",
    prompt: "Ask what the seller has been told about zoning, current use, or permitted uses.",
    aliases: ["zoning_or_use"],
  },
  {
    key: "septic_perc",
    label: "Septic / perc",
    prompt: "Ask about soil, perc, septic, well, sewer, or related testing.",
    aliases: ["septic_or_perc"],
  },
  {
    key: "taxes_hoa",
    label: "Taxes / HOA / road fees",
    prompt: "Ask about taxes, delinquencies, assessments, HOA or POA dues, and road fees.",
    aliases: ["taxes_or_hoa"],
  },
  {
    key: "restrictions",
    label: "Restrictions",
    prompt: "Ask about covenants, easements, leases, shared access, or other use limits.",
    aliases: ["covenants_restrictions"],
  },
  {
    key: "flood_wetlands",
    label: "Flood and wetlands",
    prompt: "Ask about known floodplain, wetlands, drainage, or standing water; verify separately.",
    aliases: ["flood_or_wetlands"],
  },
  {
    key: "terrain_environmental",
    label: "Terrain and environmental",
    prompt: "Ask about slope, drainage, dumping, contamination, timber, or other concerns.",
    aliases: ["terrain_or_environmental_concerns"],
  },
  {
    key: "prior_testing_improvements",
    label: "Testing and improvements",
    prompt: "Ask about surveys, studies, permits, clearing, roads, wells, or other work completed.",
    aliases: ["prior_testing", "improvements"],
  },
  {
    key: "known_concerns",
    label: "Other known concerns",
    prompt: "Ask what else could affect access, use, value, title, or a future buyer's review.",
    aliases: ["seller_known_concerns"],
  },
  {
    key: "title_probate_heirship",
    label: "Title / probate / heirs",
    prompt: "Ask about title, probate, heirship, lien, or payoff issues that may delay a sale.",
    aliases: ["title_concerns", "probate_heirship"],
  },
] as const;

const UNKNOWN_VALUES = new Set([
  "",
  "unknown",
  "not known",
  "not provided",
  "not asked",
  "not yet asked",
  "unavailable",
]);

const NOT_APPLICABLE_VALUES = new Set(["n/a", "na", "not applicable"]);

function contextText(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value
      .map((item) => contextText(item))
      .filter(Boolean)
      .join(", ");
  }
  return "";
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nestedLandFactValue(context: Record<string, unknown>, key: string) {
  const namespace = objectRecord(context.land_acquisition_v1);
  const facts = objectRecord(namespace?.facts);
  const fact = objectRecord(facts?.[key]);
  return contextText(fact?.value);
}

export function landSellerFieldValue(
  context: Record<string, unknown>,
  field: LandSellerProfileField,
) {
  const nestedValue = nestedLandFactValue(context, field.key);
  if (nestedValue) return nestedValue;
  const canonicalValue = contextText(context[field.key]);
  if (canonicalValue) return canonicalValue;

  const aliasValues = field.aliases
    .map((alias) => ({ alias, value: contextText(context[alias]) }))
    .filter((entry) => entry.value);
  if (!aliasValues.length) return "";
  if (!field.combineAliases) return aliasValues[0].value;
  return aliasValues
    .map((entry) => `${entry.alias === "decision_makers" ? "Decision makers" : "Ownership"}: ${entry.value}`)
    .join("; ");
}

export function landSellerFieldState(value: string): LandQualificationState {
  const normalized = value.trim().toLowerCase();
  if (NOT_APPLICABLE_VALUES.has(normalized)) return "not_applicable";
  if (!normalized || UNKNOWN_VALUES.has(normalized)) return "unknown";
  return "seller_reported";
}

export function buildLandQualificationContext(
  formData: FormData,
  currentContext: Record<string, unknown>,
) {
  const nextContext = { ...currentContext };
  for (const field of LAND_SELLER_PROFILE_FIELDS) {
    const state = String(formData.get(`land_${field.key}_state`) ?? "unknown")
      .trim()
      .toLowerCase() as LandQualificationState;
    const initialState = String(
      formData.get(`land_${field.key}_initial_state`) ?? "unknown",
    )
      .trim()
      .toLowerCase() as LandQualificationState;
    const detail = String(formData.get(`land_${field.key}_value`) ?? "").trim();
    if (state === "seller_reported" && detail) {
      nextContext[field.key] = detail;
    } else if (state === "not_applicable") {
      nextContext[field.key] = "Not applicable";
    } else if (state === "unknown" && initialState !== "unknown") {
      nextContext[field.key] = "Unknown";
    }
  }
  return nextContext;
}

export function fallbackLandOpenQuestions(context: Record<string, unknown>) {
  return LAND_SELLER_PROFILE_FIELDS.filter(
    (field) => landSellerFieldState(landSellerFieldValue(context, field)) === "unknown",
  ).map((field) => field.prompt);
}
