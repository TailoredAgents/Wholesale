import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const panel = readFileSync(
  resolve(appRoot, "os/dispositions/disposition-copilot-panel.tsx"),
  "utf8",
);
const workspace = readFileSync(
  resolve(appRoot, "os/dispositions/disposition-workspace.tsx"),
  "utf8",
);
const styles = readFileSync(
  resolve(appRoot, "os/dispositions/dispositions.module.css"),
  "utf8",
);

test("DS9 keeps Copilot draft-only with explicit human authority", () => {
  for (const text of [
    "Draft only - human authority",
    "cannot contact buyers",
    "choose an offer",
    "change buyer records",
    "bind Stonegate",
    "Human approval required",
    "never sent automatically",
  ]) assert.match(panel, new RegExp(text, "i"));
  assert.match(api, /can_send_outreach: false/);
  assert.match(api, /can_select_buyer: false/);
  assert.match(api, /can_bind_stonegate: false/);
  assert.match(api, /can_update_buyer: false/);
  assert.doesNotMatch(panel, /on(?:Send|Publish|Release|SelectBuyer|AcceptOffer|ApplyUpdate)=/);
});

test("measured pilot cannot pass before every stated DS9 threshold", () => {
  assert.match(panel, /Pilot NOT MET/);
  assert.match(panel, /minimum_evaluated_recommendations/);
  assert.match(panel, /minimum_distinct_cases/);
  assert.match(panel, /package_fact_correctness_basis_points >= 9000/);
  assert.match(panel, /package_fact_sample_size >= pilot\.minimum_domain_sample_size/);
  assert.match(panel, /buyer_match_relevance_basis_points >= 8000/);
  assert.match(panel, /buyer_match_sample_size >= pilot\.minimum_domain_sample_size/);
  assert.match(panel, /reply_classification_accuracy_basis_points >= 9000/);
  assert.match(panel, /reply_classification_sample_size >= pilot\.minimum_domain_sample_size/);
  assert.match(panel, /next_action_useful_or_correctable_basis_points >= 8000/);
  assert.match(panel, /next_action_sample_size >= pilot\.minimum_domain_sample_size/);
  assert.match(panel, /accept_or_correct_basis_points >= 8000/);
  assert.match(panel, /trace_attribution_basis_points === 10000/);
  assert.match(panel, /critical_authority_violations === 0/);
  assert.match(panel, /unsupported_or_hallucinated_citations === 0/);
  assert.match(panel, /missing_scenario_groups\.length === 0/);
  assert.match(api, /pilot_evaluation:/);
  assert.match(api, /minimum_domain_sample_size: number/);
  assert.match(api, /pilot_ready: boolean/);
  assert.match(api, /blockers: string\[\]/);
});

test("every structured recommendation surface resolves saved citation IDs", () => {
  assert.match(api, /export type DispositionCopilotCitation/);
  assert.match(api, /"buyer_contact_status"/);
  assert.match(api, /evidence_fingerprint: string/);
  assert.match(api, /evidence_citations: DispositionCopilotCitation\[\]/);
  assert.match(panel, /function CitationRefs/);
  assert.match(panel, /new Map\(citations\.map/);
  assert.match(panel, /ids=\{draft\.evidence\}/);
  assert.ok((panel.match(/ids=\{item\.citation_ids\}/g)?.length ?? 0) >= 6);
  assert.match(panel, /No saved citation is attached to this item/);
});

test("the daily sidekick exposes every governed DS9 work product", () => {
  for (const field of [
    "drafts",
    "reply_classifications",
    "next_actions",
    "buyer_update_proposals",
    "execution_risk",
  ]) assert.match(panel, new RegExp(`draft\\.${field}|item\\.${field}`));
  for (const draftType of [
    "package_summary",
    "recipient_segment",
    "email",
    "sms",
    "call_brief",
    "follow_up",
  ]) assert.match(api, new RegExp(draftType));
  assert.match(panel, /Fact-checked package summary/);
  assert.match(panel, /Missing package evidence/);
  assert.match(panel, /Buyer matches and conflicts/);
  assert.match(panel, /Reply classifications/);
  assert.match(panel, /Recommended next actions/);
  assert.match(api, /next_actions:[\s\S]*?confidence: number/);
  assert.match(panel, /item\.confidence.*confidence/);
  assert.match(styles, /\.copilotActionSignal/);
  assert.match(panel, /Proposed profile updates/);
  assert.match(panel, /Offer strength and risk/);
});

test("freshness and permission gates protect all review choices", () => {
  assert.match(api, /evidence_status: "current" \| "stale" \| "unknown"/);
  assert.match(api, /permitted_review_decisions:/);
  assert.match(panel, /selected\.evidence_status !== "current"/);
  assert.match(panel, /selected\.permitted_review_decisions\.includes\(decision\)/);
  assert.match(panel, /!canEdit/);
  assert.match(panel, /!evidenceCurrent/);
  for (const decision of ["accepted", "edited", "rejected", "ignored"])
    assert.match(panel, new RegExp(`canChoose\\("${decision}"\\)`));
});

test("human review records decision, notes, time saved, and quality evaluation", () => {
  for (const label of [
    "Accept guidance",
    "Save correction",
    "Reject guidance",
    "Ignore for now",
    "Reviewer notes",
    "Estimated minutes saved",
    "Package fact correctness",
    "Buyer match relevance",
    "Reply classification accuracy",
    "Next action usefulness",
    "Unsupported or hallucinated citation",
    "Critical authority violation",
    "Scenario represented",
  ]) assert.match(panel, new RegExp(label));
  assert.match(workspace, /quality_evaluation: feedback\?\.qualityEvaluation/);
  assert.match(workspace, /estimated_time_saved_seconds: feedback\?\.estimatedTimeSavedSeconds/);
  assert.match(workspace, /notes: feedback\?\.notes/);
});

test("model trace and responsive review remain visible and auditable", () => {
  for (const field of [
    "model_name",
    "prompt_version_id",
    "total_tokens",
    "cost_microusd",
    "latency_ms",
  ]) assert.match(panel, new RegExp(`trace\\.${field}`));
  assert.match(panel, /No model trace is available/);
  assert.match(styles, /@media \(max-width: 760px\)/);
  assert.match(styles, /min-height: 44px/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(panel, /[\u00b7\u00c2\u00c3\ufffd]/);
});
