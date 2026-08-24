import Link from "next/link";

import type {
  LandAcquisitionEvidence,
  LandAcquisitionFact,
  LandAcquisitionProfile as LandAcquisitionProfileRead,
  LeadDetail,
} from "../../lib/api";
import { PropertyValidationControl } from "./property-validation-control";
import { fallbackLandOpenQuestions } from "./land-acquisition-state";
import styles from "./page.module.css";

type FactKey =
  | "ownership_decision_makers"
  | "parcel_id"
  | "county"
  | "state"
  | "acreage"
  | "lot_area_square_feet"
  | "current_use"
  | "zoning_use"
  | "access_frontage"
  | "utilities"
  | "survey_boundaries"
  | "septic_perc"
  | "taxes_hoa"
  | "tax_delinquency"
  | "hoa_poa"
  | "restrictions"
  | "flood_wetlands"
  | "terrain_environmental"
  | "prior_testing_improvements"
  | "known_concerns"
  | "title_probate_heirship";

type ProfileGroup = {
  key: string;
  label: string;
  factKeys: readonly FactKey[];
  prompt: string;
};

type EvidenceEntry = LandAcquisitionEvidence & {
  factKey: FactKey;
  requiresVerification: boolean;
};

const FACT_LABELS: Record<FactKey, string> = {
  ownership_decision_makers: "Ownership / decision makers",
  parcel_id: "Parcel / APN",
  county: "County",
  state: "State",
  acreage: "Acreage",
  lot_area_square_feet: "Lot area",
  current_use: "Current use",
  zoning_use: "Zoning / use",
  access_frontage: "Access / frontage",
  utilities: "Utilities",
  survey_boundaries: "Survey / boundaries",
  septic_perc: "Septic / perc",
  taxes_hoa: "Taxes / HOA / road fees",
  tax_delinquency: "Tax delinquency",
  hoa_poa: "HOA / POA",
  restrictions: "Restrictions",
  flood_wetlands: "Flood / wetlands",
  terrain_environmental: "Terrain / environmental",
  prior_testing_improvements: "Testing / improvements",
  known_concerns: "Known concerns",
  title_probate_heirship: "Title / probate / heirs",
};

const CORE_GROUPS: readonly ProfileGroup[] = [
  {
    key: "acreage",
    label: "Acreage",
    factKeys: ["acreage", "lot_area_square_feet"],
    prompt: "Ask for approximate acreage, then verify it against the parcel record.",
  },
  {
    key: "zoning-use",
    label: "Zoning and use",
    factKeys: ["zoning_use", "current_use"],
    prompt: "Ask what the seller has been told about zoning and use; verify with the jurisdiction.",
  },
  {
    key: "access-frontage",
    label: "Access and frontage",
    factKeys: ["access_frontage"],
    prompt: "Ask about frontage, easements, and deeded access; do not infer legal access.",
  },
  {
    key: "utilities",
    label: "Utilities",
    factKeys: ["utilities"],
    prompt: "Ask what is connected, at the road, nearby, or unknown; availability still needs verification.",
  },
  {
    key: "flood-wetlands",
    label: "Flood and wetlands",
    factKeys: ["flood_wetlands"],
    prompt: "Ask about known flooding, wetlands, drainage, or standing water and verify separately.",
  },
  {
    key: "taxes-restrictions",
    label: "Taxes and restrictions",
    factKeys: ["taxes_hoa", "tax_delinquency", "hoa_poa", "restrictions"],
    prompt: "Ask about taxes, delinquencies, dues, assessments, covenants, easements, and use limits.",
  },
];

const ADDITIONAL_GROUPS: readonly ProfileGroup[] = [
  {
    key: "survey-boundaries",
    label: "Survey and boundaries",
    factKeys: ["survey_boundaries"],
    prompt: "Ask whether a current survey exists and whether boundaries or corners are marked.",
  },
  {
    key: "septic-perc",
    label: "Septic / perc",
    factKeys: ["septic_perc"],
    prompt: "Ask about soil, perc, septic, well, sewer, and related test results.",
  },
  {
    key: "terrain-environmental",
    label: "Terrain and environmental",
    factKeys: ["terrain_environmental"],
    prompt: "Ask about slope, drainage, dumping, contamination, timber, or other concerns.",
  },
  {
    key: "testing-improvements",
    label: "Testing and improvements",
    factKeys: ["prior_testing_improvements"],
    prompt: "Ask about surveys, studies, permits, clearing, roads, wells, or other completed work.",
  },
  {
    key: "known-concerns",
    label: "Known concerns",
    factKeys: ["known_concerns"],
    prompt: "Ask what else could affect access, use, title, value, or a future buyer's review.",
  },
  {
    key: "title-probate",
    label: "Title / probate / heirs",
    factKeys: ["title_probate_heirship"],
    prompt: "Ask about title, probate, heirs, liens, or payoff issues that may delay a sale.",
  },
];

function labelize(value: string) {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatEvidenceValue(value: unknown, depth = 0): string {
  if (value === null || value === undefined || value === "") return "Unknown";
  if (typeof value === "string") return value;
  if (typeof value === "number") return new Intl.NumberFormat("en-US").format(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) {
    const items = value.map((item) => formatEvidenceValue(item, depth + 1)).filter(Boolean);
    return items.length ? items.join(", ") : "Unknown";
  }
  if (typeof value === "object" && depth < 2) {
    const entries = Object.entries(value)
      .slice(0, 8)
      .map(([key, item]) => `${labelize(key)}: ${formatEvidenceValue(item, depth + 1)}`);
    return entries.length ? entries.join("; ") : "Unknown";
  }
  return String(value);
}

function formatObservedAt(value: string | null) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(parsed);
}

function factStatus(
  facts: Record<string, LandAcquisitionFact> | undefined,
  factKeys: readonly FactKey[],
) {
  const statuses = factKeys.map((key) => facts?.[key]?.status ?? "unknown");
  if (statuses.includes("conflict")) return "conflict";
  if (statuses.includes("known")) return "known";
  return "unknown";
}

function normalizedEvidence(
  facts: Record<string, LandAcquisitionFact> | undefined,
  factKeys: readonly FactKey[],
) {
  const entries: EvidenceEntry[] = [];
  for (const factKey of factKeys) {
    const fact = facts?.[factKey];
    if (!fact) continue;
    const evidence = fact.evidence.length
      ? fact.evidence
      : fact.status !== "unknown" && fact.source_type !== "unknown" && fact.source_name
        ? [{
            value: fact.value,
            source_type: fact.source_type,
            source_name: fact.source_name,
            observed_at: fact.observed_at,
          }]
        : [];
    for (const item of evidence) {
      entries.push({
        ...item,
        factKey,
        requiresVerification: fact.requires_verification,
      });
    }
  }
  const seen = new Set<string>();
  return entries.filter((entry) => {
    const key = [
      entry.factKey,
      entry.source_type,
      entry.source_name,
      formatEvidenceValue(entry.value),
    ].join(":");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function sourceTypeLabel(sourceType: EvidenceEntry["source_type"]) {
  if (sourceType === "seller_reported") return "Seller reported - unverified";
  if (sourceType === "provider_sourced") return "Provider screening evidence";
  return "CRM record";
}

function EvidenceList({ entries }: { entries: EvidenceEntry[] }) {
  return (
    <ul className={styles.landEvidenceList}>
      {entries.map((entry, index) => {
        const observedAt = formatObservedAt(entry.observed_at);
        return (
          <li key={`${entry.factKey}-${entry.source_type}-${entry.source_name}-${index}`}>
            <span>{FACT_LABELS[entry.factKey]}</span>
            <strong>{formatEvidenceValue(entry.value)}</strong>
            <small>
              {sourceTypeLabel(entry.source_type)} / {entry.source_name}
              {observedAt ? ` / observed ${observedAt}` : ""}
              {entry.requiresVerification ? " / verification required" : ""}
            </small>
          </li>
        );
      })}
    </ul>
  );
}

function ProfileGroupCard({
  facts,
  group,
  unansweredFields,
}: {
  facts: Record<string, LandAcquisitionFact> | undefined;
  group: ProfileGroup;
  unansweredFields: ReadonlySet<string>;
}) {
  const status = factStatus(facts, group.factKeys);
  const evidence = normalizedEvidence(facts, group.factKeys);
  const sellerEvidence = evidence.filter((item) => item.source_type === "seller_reported");
  const screeningEvidence = evidence.filter((item) => item.source_type !== "seller_reported");
  const sellerQuestionUnanswered = group.factKeys.some((key) => unansweredFields.has(key));
  const headingId = `land-profile-${group.key}`;
  return (
    <article
      aria-labelledby={headingId}
      className={styles.landProfileCard}
      data-status={status}
    >
      <header>
        <h3 id={headingId}>{group.label}</h3>
        <span>{status === "known" ? "Recorded" : status === "conflict" ? "Resolve conflict" : "Unknown"}</span>
      </header>
      {status === "conflict" ? (
        <p className={styles.landConflictNotice} role="status">
          Sources disagree. Resolve the conflict before relying on this fact.
        </p>
      ) : null}
      <div className={styles.landEvidenceColumns}>
        <section>
          <h4>Seller report</h4>
          {sellerEvidence.length ? (
            <EvidenceList entries={sellerEvidence} />
          ) : sellerQuestionUnanswered ? (
            <p className={styles.landUnknownPrompt}>
              <strong>Unknown.</strong> {group.prompt}
            </p>
          ) : (
            <p className={styles.landUnknownPrompt}>
              <strong>Seller answer recorded as unknown.</strong> Continue remote research and
              independent diligence without assuming a positive result.
            </p>
          )}
        </section>
        <section>
          <h4>Property evidence</h4>
          {screeningEvidence.length ? (
            <EvidenceList entries={screeningEvidence} />
          ) : (
            <p className={styles.landNoEvidence}>No provider or CRM evidence is captured.</p>
          )}
        </section>
      </div>
    </article>
  );
}

function IdentityFact({
  fallback,
  fact,
  label,
}: {
  fallback?: string | null;
  fact: LandAcquisitionFact | undefined;
  label: string;
}) {
  const hasNormalizedValue = fact && fact.status === "known" && fact.value !== null;
  const value = hasNormalizedValue ? formatEvidenceValue(fact.value) : fallback || "Unknown";
  const provenance = hasNormalizedValue
    ? fact.source_type === "seller_reported"
      ? "Seller reported - unverified"
      : fact.source_type === "provider_sourced"
        ? "Provider screening evidence"
        : fact.source_type === "crm_record"
          ? "CRM record"
          : "Unknown source"
    : "CRM record or not yet known";
  return (
    <div>
      <dt>{label}</dt>
      <dd>{fact?.status === "conflict" ? "Conflicting evidence - review" : value}</dd>
      <small>{provenance}</small>
    </div>
  );
}

function SnapshotFact({
  fact,
  label,
  sellerQuestionUnanswered,
}: {
  fact: LandAcquisitionFact | undefined;
  label: string;
  sellerQuestionUnanswered: boolean;
}) {
  const value =
    fact?.status === "conflict"
      ? "Conflicting evidence - review"
      : fact?.status === "known"
        ? formatEvidenceValue(fact.value)
        : sellerQuestionUnanswered
          ? "Unknown - ask seller"
          : "Unknown - research / verify";
  const source =
    fact?.source_type === "seller_reported"
      ? "Seller reported - unverified"
      : fact?.source_type === "provider_sourced"
        ? "Provider screening evidence"
        : fact?.source_type === "crm_record"
          ? "CRM record"
          : "No source recorded";
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
      <small>{source}</small>
    </div>
  );
}

function readinessCopy(status: LandAcquisitionProfileRead["readiness"]["status"]) {
  if (status === "ready_for_valuation_review") {
    return "Seller and parcel evidence is sufficient to begin a governed valuation review. Due diligence is still required.";
  }
  if (status === "needs_due_diligence_review") {
    return "The seller interview is complete enough for remote research, but unknown or conflicting facts require independent diligence.";
  }
  return "Collect the unanswered seller facts before treating this parcel as ready for remote research.";
}

export function LandAcquisitionProfile({ lead }: { lead: LeadDetail }) {
  const profile = lead.land_acquisition_profile;
  const facts = profile?.facts;
  const readiness = profile?.readiness;
  const readinessStatus = readiness?.status ?? "needs_seller_information";
  const unansweredFields = new Set(
    readiness?.unanswered_fields ??
      readiness?.unknown_fields ??
      [...CORE_GROUPS, ...ADDITIONAL_GROUPS].flatMap((group) => group.factKeys),
  );
  return (
    <section aria-labelledby="land-acquisition-profile-heading" className={styles.sectionPanel}>
      <div className={styles.sectionHeader}>
        <h2 id="land-acquisition-profile-heading">Land acquisition profile</h2>
        <span>{readiness?.completion_score ?? 0}% seller interview</span>
      </div>
      <PropertyValidationControl initialValidation={lead.property_validation} leadId={lead.id} />
      <div className={styles.landReadiness} data-status={readinessStatus}>
        <div>
          <span>Valuation readiness</span>
          <strong>{labelize(readinessStatus)}</strong>
        </div>
        <p>{readinessCopy(readinessStatus)}</p>
        <small>
          {readiness?.remote_review_ready
            ? "The seller interview is complete enough to begin remote research."
            : "Unanswered seller questions remain before remote research."}
          {readiness?.in_person_review_recommended
            ? " An in-person review is recommended after remote screening."
            : ""}
        </small>
      </div>
      <dl className={styles.landIdentityFacts}>
        <IdentityFact
          fact={facts?.ownership_decision_makers}
          label="Ownership / decision makers"
        />
        <IdentityFact
          fact={facts?.parcel_id}
          fallback={lead.property_parcel_id}
          label="Parcel / APN"
        />
        <IdentityFact fact={facts?.county} fallback={lead.property_county} label="County" />
        <IdentityFact fact={facts?.state} fallback={lead.property_state} label="State" />
      </dl>
      <div className={styles.landProvenanceNote}>
        <strong>Screening boundary</strong>
        <p>
          Seller statements are unverified. Provider and CRM facts are screening evidence, not proof
          of buildability, legal access, utility availability, boundaries, or permitted use.
        </p>
      </div>
      <div className={styles.landProfileGrid}>
        {CORE_GROUPS.map((group) => (
          <ProfileGroupCard
            facts={facts}
            group={group}
            key={group.key}
            unansweredFields={unansweredFields}
          />
        ))}
      </div>
      <details className={styles.landAdditionalProfile}>
        <summary>Additional Land seller and diligence facts</summary>
        <div className={styles.landProfileGrid}>
          {ADDITIONAL_GROUPS.map((group) => (
            <ProfileGroupCard
              facts={facts}
              group={group}
              key={group.key}
              unansweredFields={unansweredFields}
            />
          ))}
        </div>
      </details>
      <Link
        className={styles.inlineEditLink}
        href={`/os/leads/${lead.id}?tab=property&edit=lead#edit-lead`}
      >
        Edit seller-reported Land facts
      </Link>
    </section>
  );
}

export function LandAcquisitionSummary({ lead }: { lead: LeadDetail }) {
  const profile = lead.land_acquisition_profile;
  const facts = profile?.facts;
  const unansweredFields = new Set(profile?.readiness.unanswered_fields ?? []);
  const readinessStatus = profile?.readiness.status ?? "needs_seller_information";
  return (
    <section aria-labelledby="land-property-snapshot-heading" className={styles.sectionPanel}>
      <div className={styles.sectionHeader}>
        <h2 id="land-property-snapshot-heading">Land property snapshot</h2>
        <span>{labelize(readinessStatus)}</span>
      </div>
      <PropertyValidationControl initialValidation={lead.property_validation} leadId={lead.id} />
      <dl className={styles.landSnapshotFacts}>
        <IdentityFact fact={facts?.parcel_id} fallback={lead.property_parcel_id} label="Parcel / APN" />
        <SnapshotFact
          fact={facts?.acreage}
          label="Acreage"
          sellerQuestionUnanswered={unansweredFields.has("acreage")}
        />
        <SnapshotFact
          fact={facts?.zoning_use}
          label="Zoning / use"
          sellerQuestionUnanswered={unansweredFields.has("zoning_use")}
        />
        <SnapshotFact
          fact={facts?.access_frontage}
          label="Access / frontage"
          sellerQuestionUnanswered={unansweredFields.has("access_frontage")}
        />
        <SnapshotFact
          fact={facts?.utilities}
          label="Utilities"
          sellerQuestionUnanswered={unansweredFields.has("utilities")}
        />
        <SnapshotFact
          fact={facts?.flood_wetlands}
          label="Flood / wetlands"
          sellerQuestionUnanswered={unansweredFields.has("flood_wetlands")}
        />
        <SnapshotFact
          fact={facts?.taxes_hoa}
          label="Taxes / HOA / road fees"
          sellerQuestionUnanswered={unansweredFields.has("taxes_hoa")}
        />
        <SnapshotFact
          fact={facts?.restrictions}
          label="Restrictions"
          sellerQuestionUnanswered={unansweredFields.has("restrictions")}
        />
      </dl>
      <p className={styles.landSnapshotBoundary}>
        Seller reports are unverified; provider facts are screening evidence only.
      </p>
      <Link className={styles.inlineEditLink} href={`/os/leads/${lead.id}?tab=property`}>
        Open full Land profile
      </Link>
    </section>
  );
}

export function LandQualificationPanel({ lead }: { lead: LeadDetail }) {
  const readiness = lead.land_acquisition_profile?.readiness;
  const openPrompts = (
    readiness
      ? readiness.open_questions
      : fallbackLandOpenQuestions(lead.qualification_context)
  ).map((question, index) => ({
    question,
    kind:
      /^Research or verify\b|^Resolve conflicting evidence\b/i.test(question) ||
      (readiness !== undefined && index >= readiness.unanswered_fields.length)
        ? "diligence" as const
        : "seller" as const,
  }));
  const sellerPrompts = openPrompts.filter((prompt) => prompt.kind === "seller").slice(0, 6);
  const diligencePrompts = openPrompts
    .filter((prompt) => prompt.kind === "diligence")
    .slice(0, Math.max(0, 6 - sellerPrompts.length));
  const visiblePromptCount = sellerPrompts.length + diligencePrompts.length;
  const readinessStatus = readiness?.status ?? "needs_seller_information";
  return (
    <section className={styles.sectionPanel}>
      <div className={styles.sectionHeader}>
        <h2>Land qualification</h2>
        <span>{visiblePromptCount ? `${visiblePromptCount} open actions` : "Seller facts recorded"}</span>
      </div>
      <div className={styles.landQualificationSummary} data-status={readinessStatus}>
        <span>Valuation readiness</span>
        <strong>{labelize(readinessStatus)}</strong>
        <small>{readiness?.completion_score ?? 0}% seller interview coverage</small>
        <p>{readinessCopy(readinessStatus)}</p>
      </div>
      <div className={styles.questionList}>
        {visiblePromptCount ? (
          <>
            {sellerPrompts.map(({ question }, index) => (
              <div data-kind="seller" key={`${question}-${index}`}>
              <strong>Ask the seller</strong>
              <span>{question}</span>
              </div>
            ))}
            {diligencePrompts.map(({ question }, index) => (
              <div data-kind="diligence" key={`${question}-${index}`}>
                <strong>Research / verify</strong>
                <span>{question}</span>
              </div>
            ))}
          </>
        ) : (
          <p className={styles.emptyState}>
            Core seller questions are recorded. Continue independent diligence before relying on the
            parcel&apos;s use, access, utilities, or buildability.
          </p>
        )}
      </div>
      <Link
        className={styles.inlineEditLink}
        href={`/os/leads/${lead.id}?tab=property&edit=lead#edit-lead`}
      >
        Edit Land qualification
      </Link>
    </section>
  );
}
