import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const read = (path) => readFileSync(resolve(webRoot, path), "utf8");

const api = read("src/app/lib/api.ts");
const detail = read("src/app/leads/[leadId]/lead-detail-view.tsx");
const edit = read("src/app/leads/[leadId]/lead-edit-form.tsx");
const profile = read("src/app/leads/[leadId]/land-acquisition-profile.tsx");
const state = read("src/app/leads/[leadId]/land-acquisition-state.ts");
const propertyIntelligence = read(
  "src/app/leads/[leadId]/property-intelligence-panel.tsx",
);
const leadStyles = read("src/app/leads/[leadId]/page.module.css");
const questions = read("src/app/os/land-qualification-questions.ts");
const leadManager = read("src/app/os/lead-manager/lead-manager-workspace.tsx");
const prospecting = read("src/app/os/prospecting/prospecting-workspace.tsx");

function sourceSlice(source, start, end) {
  const startIndex = source.indexOf(start);
  const endIndex = source.indexOf(end, startIndex + start.length);
  assert.ok(startIndex >= 0, `Missing source boundary: ${start}`);
  assert.ok(endIndex > startIndex, `Missing source boundary: ${end}`);
  return source.slice(startIndex, endIndex);
}

test("LeadDetail exposes the normalized Land-only acquisition contract", () => {
  for (const field of [
    "land_acquisition_profile: LandAcquisitionProfile | null",
    'version: "land_acquisition_v1"',
    'status: "known" | "unknown" | "conflict"',
    'source_type: "seller_reported" | "provider_sourced" | "crm_record" | "unknown"',
    '"ready_for_valuation_review"',
    "seller_reported_fields",
    "provider_sourced_fields",
    "unanswered_fields",
    "open_questions",
    "remote_review_ready",
    "in_person_review_recommended",
  ]) {
    assert.ok(api.includes(field), `Missing Land profile contract field: ${field}`);
  }
  assert.doesNotMatch(api, /seller_confirmed/);
  assert.doesNotMatch(api, /ready_for_offer_review/);
});

test("Land detail branches to its profile while House property and qualification behavior remains", () => {
  assert.match(
    detail,
    /lead\.asset_class === "land"\)[\s\S]*<LandAcquisitionSummary lead=\{lead\} \/>[\s\S]*<LandAcquisitionProfile lead=\{lead\} \/>/,
  );
  assert.match(
    detail,
    /lead\.asset_class === "land"\) return <LandQualificationPanel lead=\{lead\} \/>/,
  );
  const houseProperty = sourceSlice(detail, "function PropertyPanel", "function TasksPanel");
  for (const label of ["Condition", "Occupancy", "Mortgage", "Property type"]) {
    assert.match(houseProperty, new RegExp(`>${label}<`));
  }
  assert.match(edit, /const conditionOptions/);
  assert.match(edit, /const occupancyOptions/);
  assert.match(edit, /property_condition: optionalFormString/);
  assert.match(edit, /occupancy_status: optionalFormString/);
  assert.match(detail, /<PropertyPanel compact lead=\{lead\} \/>/);
  assert.match(detail, /<PropertyPanel lead=\{lead\} \/>/);
  assert.match(profile, /Land property snapshot/);
  assert.match(profile, /Open full Land profile/);
});

test("Land readiness covers the acquisition facts with explicit unknown prompts", () => {
  for (const label of [
    "Acreage",
    "Zoning and use",
    "Access and frontage",
    "Utilities",
    "Flood and wetlands",
    "Taxes and restrictions",
    "Survey and boundaries",
    "Septic / perc",
    "Terrain and environmental",
    "Testing and improvements",
    "Known concerns",
    "Title / probate / heirs",
  ]) {
    assert.match(profile, new RegExp(`label: "${label.replace("/", "\\/")}"`));
  }
  assert.match(profile, /<strong>Unknown\.<\/strong> \{group\.prompt\}/);
  assert.match(profile, /Seller answer recorded as unknown/);
  assert.match(profile, /unansweredFields\.has\(key\)/);
  assert.match(profile, /No provider or CRM evidence is captured/);
  assert.match(profile, /Sources disagree\. Resolve the conflict/);
  assert.match(profile, /readiness\.open_questions/);
  assert.match(profile, /readiness\s+\?\s+readiness\.open_questions/);
  assert.match(profile, /seller interview is complete enough for remote research/i);
  assert.match(profile, /index >= readiness\.unanswered_fields\.length/);
  assert.match(profile, /\^Research or verify\\b\|\^Resolve conflicting evidence\\b/);
  assert.match(profile, /data-kind="seller"/);
  assert.match(profile, /<strong>Ask the seller<\/strong>/);
  assert.match(profile, /data-kind="diligence"/);
  assert.match(profile, /<strong>Research \/ verify<\/strong>/);
  assert.match(profile, /Unknown - ask seller/);
  assert.match(profile, /Unknown - research \/ verify/);
  assert.match(profile, /sellerQuestionUnanswered=\{unansweredFields\.has\("utilities"\)\}/);
  assert.doesNotMatch(profile, /openPrompts\.map[\s\S]{0,300}<strong>Ask the seller/);
});

test("seller reports and independent evidence are never presented as the same provenance", () => {
  assert.match(profile, /sourceType === "seller_reported"/);
  assert.match(profile, /Seller reported - unverified/);
  assert.match(profile, /Provider screening evidence/);
  assert.match(profile, /CRM record/);
  assert.match(profile, /verification required/);
  assert.match(profile, /not proof\s+of buildability, legal access, utility availability/);
  assert.match(propertyIntelligence, /Saved screening facts/);
  assert.match(propertyIntelligence, /screening evidence - not legal opinions or guarantees/);
  assert.doesNotMatch(profile, /guaranteed buildable/i);
});

test("the Land editor preserves context and submits only explicit canonical state changes", () => {
  const builder = sourceSlice(
    state,
    "export function buildLandQualificationContext",
    "export function fallbackLandOpenQuestions",
  );
  assert.match(builder, /const nextContext = \{ \.\.\.currentContext \}/);
  assert.match(builder, /state === "seller_reported" && detail/);
  assert.match(builder, /nextContext\[field\.key\] = detail/);
  assert.match(builder, /state === "not_applicable"/);
  assert.match(builder, /nextContext\[field\.key\] = "Not applicable"/);
  assert.match(builder, /formData\.get\(`land_\$\{field\.key\}_initial_state`\)/);
  assert.match(builder, /state === "unknown" && initialState !== "unknown"/);
  assert.match(builder, /nextContext\[field\.key\] = "Unknown"/);
  assert.doesNotMatch(builder, /state === "unknown"\) \{/);
  assert.doesNotMatch(state, /key: "parcel_id"/);
  assert.doesNotMatch(state, /key: "county"/);
  assert.doesNotMatch(state, /key: "state"/);
  assert.match(edit, /qualification_context: buildLandQualificationContext/);
  assert.match(edit, /Record only what the seller reports/);
  assert.match(edit, /Unknown \/ not yet asked/);
  assert.match(edit, /name=\{`land_\$\{field\.key\}_initial_state`\}/);
  assert.match(edit, /Seller-reported details/);
});

test("both governed script publishers show and save the canonical Land checklist", () => {
  for (const key of [
    "ownership_decision_makers",
    "acreage",
    "access_frontage",
    "utilities",
    "survey_boundaries",
    "zoning_use",
    "septic_perc",
    "taxes_hoa",
    "restrictions",
    "flood_wetlands",
    "terrain_environmental",
    "prior_testing_improvements",
    "known_concerns",
    "title_probate_heirship",
  ]) {
    assert.match(questions, new RegExp(`"${key}"`));
  }
  assert.doesNotMatch(questions, /"property_condition"/);
  assert.doesNotMatch(questions, /"occupancy"/);
  for (const surface of [leadManager, prospecting]) {
    assert.match(surface, /import \{ landStandardQuestions \}/);
    assert.match(surface, /=== "land" \? landStandardQuestions/);
    assert.match(surface, /Land seller checklist/);
    assert.match(surface, /aria-live="polite"/);
  }
  assert.match(leadManager, /A manager must approve it before the team can use it/);
  assert.match(prospecting, /remains a draft until a manager approves it/);

  const leadManagerCreate = sourceSlice(
    leadManager,
    "async function createScript",
    "return (",
  );
  const prospectingCreate = sourceSlice(
    prospecting,
    "async function createScript",
    "async function approveScript",
  );
  assert.doesNotMatch(leadManagerCreate, /\/approve/);
  assert.doesNotMatch(prospectingCreate, /\/approve/);
  assert.match(leadManager, /script\.status === "draft"/);
  assert.match(prospecting, /script\.status === "draft"/);
});

test("Land profile and editor remain keyboard-accessible and responsive", () => {
  assert.match(profile, /aria-labelledby="land-acquisition-profile-heading"/);
  assert.match(profile, /aria-labelledby=\{headingId\}/);
  assert.match(edit, /<fieldset/);
  assert.match(edit, /<legend>Land seller qualification<\/legend>/);
  assert.match(edit, /aria-describedby=\{helpId\}/);
  assert.match(leadManager, /aria-label="Draft qualification questions" tabIndex=\{0\}/);
  assert.match(leadStyles, /\.landAdditionalProfile > summary:focus-visible/);
  assert.match(leadStyles, /\.landQualificationEditorGrid/);
  assert.match(leadStyles, /@media \(max-width: 820px\)[\s\S]*\.landProfileGrid/);
  assert.match(leadStyles, /@media \(max-width: 820px\)[\s\S]*\.landQualificationEditorGrid/);
  assert.match(leadStyles, /@media \(max-width: 820px\)[\s\S]*\.landQualificationField > div/);
});
