import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const page = readFileSync(resolve(webRoot, "src/app/os/prospecting/page.tsx"), "utf8");
const pilot = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-pilot-acceptance.tsx"),
  "utf8",
);
const styles = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting.module.css"),
  "utf8",
);
const api = readFileSync(resolve(webRoot, "src/app/lib/api.ts"), "utf8");
const packageJson = JSON.parse(readFileSync(resolve(webRoot, "package.json"), "utf8"));
const pilotOverviewType = api.slice(
  api.indexOf("export type ProspectingDialerPilotOverview"),
  api.indexOf("export type ProspectingDialerAnalyticsCoverage"),
);

test("D10 is a manager-only Prospecting view backed by fresh pilot evidence", () => {
  assert.match(page, /requestedView === "pilot"/);
  assert.match(page, /canManage && view === "pilot"[\s\S]*getProspectingDialerPilot/);
  assert.match(page, /href="\/os\/prospecting\?view=pilot"/);
  assert.match(page, /view === "pilot" && canManage/);
  assert.match(api, /\/api\/v1\/prospecting\/dialer\/pilot/);
  assert.match(api, /cache: "no-store"/);
  assert.match(pilot, /export function ProspectingPilotAcceptance/);
});

test("technical readiness, controlled shifts, and owner acceptance remain separate", () => {
  assert.match(pilot, /1\. Technical readiness/);
  assert.match(pilot, /2\. Controlled shifts/);
  assert.match(pilot, /3\. Owner acceptance/);
  assert.match(pilot, /Technical readiness permits a test/);
  assert.match(pilot, /Only verified shifts and an explicit owner decision/);
  assert.match(pilot, /Never inferred from technical readiness/);
  assert.match(pilot, /allGatesPass/);
  assert.match(pilot, /ownerAuthorized && allGatesPass/);
  assert.doesNotMatch(pilot, /controlled_pilot_ready\s*\?/);
});

test("pilot scope uses authoritative campaign and dialer configuration with fixed caps", () => {
  assert.match(page, /campaignManagement=\{campaignManagement\}/);
  assert.match(page, /dialerOperations=\{dialerOperations\}/);
  assert.match(pilot, /Non-overlapping cohort/);
  assert.match(pilot, /Calling batch/);
  assert.match(pilot, /Dedicated line/);
  assert.match(pilot, /Safety caps are policy-controlled/);
  assert.match(pilot, /75-250 record batch/);
  assert.doesNotMatch(pilot, /setDailyDialLimit|setDailySpendLimit/);
});

test("drafts enter a controlled-number smoke stage before live pilot calling", () => {
  assert.match(api, /"draft" \| "smoke_testing" \| "running"/);
  assert.match(api, /call_record_ids: string\[\]/);
  assert.match(api, /placed_call: boolean/);
  assert.match(api, /smoke_test_eligible: boolean/);
  assert.match(api, /counts_toward_production_shift: boolean/);
  assert.match(api, /acceptance_stage: "smoke_testing" \| "running" \| "accepted" \| null/);
  assert.match(api, /start_attestation: Record<string, unknown>/);
  assert.match(pilot, /controlled_phone_numbers: controlledPhoneNumbers/);
  assert.match(pilot, /controlledPhoneNumbers\.length <= 10/);
  assert.ok(pilot.includes("/^\\+(?:1\\d{10}|[2-9]\\d{10,14})$/"));
  assert.match(pilot, /must already exist as a test record in this selected calling batch/);
  assert.match(pilot, /Begin controlled-number smoke test/);
  assert.match(pilot, /Only saved test numbers are callable/);
  assert.match(pilot, /Valid evidence promotes the pilot to running/);
  assert.match(pilot, /smokeCallCandidates=\{smokeCallCandidates\}/);
  assert.match(pilot, /smokeProviderCallIds=\{smokeProviderCallIds\}/);
  assert.match(pilot, /attempt\.acceptance_stage !== "smoke_testing"/);
  assert.match(pilot, /!attempt\.smoke_test_eligible/);
  assert.match(pilot, /attempt\.call_record_ids\.length !== 1/);
  assert.match(pilot, /attempt\.provider_call_ids\.length < 2/);
  assert.match(pilot, /Completed controlled call records/);
  assert.doesNotMatch(pilot, /Paste one or more UUIDs/);
});

test("smoke evidence binds answered records and the complete smoke billing universe", () => {
  assert.match(pilot, /type SmokeCallCandidate/);
  assert.match(pilot, /callRecordId: attempt\.call_record_ids\[0\]/);
  assert.match(pilot, /providerCallIds: attempt\.provider_call_ids/);
  assert.match(pilot, /attempt\.acceptance_stage === "smoke_testing"/);
  assert.match(pilot, /\.flatMap\(\(attempt\) => attempt\.provider_call_ids/);
  assert.match(pilot, /selectedProviderCallIds/);
  assert.match(pilot, /providerCostsAreComplete\([\s\S]*selectedProviderCallIds[\s\S]*100/);
  assert.match(pilot, /provider_cost_items: smokeProviderCostItems/);
  assert.match(pilot, /Actual cost \(USD\)/);
  assert.match(pilot, /Provider reference/);
  assert.match(pilot, /No provider-started smoke IDs are available yet/);
  assert.match(pilot, /50-reservation \/ 100-provider-ID safety boundary/);
});

test("every mutation is revision checked and idempotent", () => {
  assert.match(pilot, /\/api\/v1\/prospecting\/dialer\/pilots/);
  assert.match(pilot, /expected_revision: pilot\.revision/);
  assert.match(pilot, /expected_revision: 0/);
  assert.match(pilot, /idempotency_key: operationKey/);
  assert.match(pilot, /"PUT"/);
  assert.match(pilot, /attempts\/\$\{attempt\.attempt_id\}\/review/);
  assert.match(pilot, /shifts\/\$\{sessionId\}\/review/);
  assert.match(pilot, /"submit"/);
  assert.match(pilot, /"rollback"/);
  assert.match(pilot, /"decision"/);
});

test("reviews capture facts while the API owns pass or fail", () => {
  assert.match(pilot, /Record observed facts/);
  assert.match(pilot, /recording_reviewed/);
  assert.match(pilot, /provider_cost_verified/);
  assert.match(pilot, /no_duplicate_calls/);
  assert.match(pilot, /no_lost_answers/);
  assert.match(pilot, /provider_billing_verified/);
  assert.match(pilot, /calculates pass or fail from these facts/);
  assert.doesNotMatch(pilot, /setDecision\(/);
});

test("shift billing reconciles every server-provided call ID to an actual provider cost", () => {
  assert.match(api, /provider_call_ids: string\[\]/);
  assert.match(pilot, /attempt\.provider_call_ids/);
  assert.match(pilot, /providerCallIds=\{candidate\.provider_call_ids\}/);
  assert.match(pilot, /Provider cost reconciliation/);
  assert.match(pilot, /actual_cost_cents: centsFromDollarInput/);
  assert.match(pilot, /currency: "USD"/);
  assert.match(pilot, /provider_reference:/);
  assert.match(pilot, /provider_cost_items: providerCostItems/);
  assert.match(pilot, /Stonegate verifies one-to-one coverage and owns the billing decision/);
  assert.match(pilot, /A documented \$0 charge is valid/);
  assert.doesNotMatch(pilot, /providerCostItems\.reduce\([\s\S]{0,240}> 0/);
  assert.match(pilot, /No provider call IDs were returned/);
  assert.match(styles, /\.pilotProviderCostRow/);
});

test("shift review aggregates every session and call on one pilot-local date", () => {
  assert.match(pilot, /new Intl\.DateTimeFormat\("en-CA"/);
  assert.match(pilot, /dateKeyInTimeZone\(attempt\.started_at, pilot\.timezone\)/);
  assert.match(pilot, /reviewedShiftDates/);
  assert.match(pilot, /session_ids: \[\.\.\.new Set\(candidate\.session_ids\)\]/);
  assert.match(pilot, /call_record_ids: \[\.\.\.new Set\(candidate\.call_record_ids\)\]/);
  assert.doesNotMatch(pilot, /provider_call_ids: \[\.\.\.new Set\(candidate\.provider_call_ids\)\]/);
  assert.match(pilot, /if \(!attempt\.counts_toward_production_shift\) continue/);
  assert.match(pilot, /current\.placed_call_count \+= 1/);
  assert.match(pilot, /candidate\.placed_call_count >= pilot\.minimum_attempts_per_shift/);
  assert.match(pilot, /reviewShift\(candidate\.representative_session_id, candidate\.shift_date, facts\)/);
  assert.match(pilot, /\{ \.\.\.facts, shift_date: shiftDate \}/);
  assert.match(pilot, /aggregates the entire local date/);
});

test("evidence timestamps retain seconds so just-completed calls are not excluded", () => {
  assert.match(pilot, /toISOString\(\)\.slice\(0, 19\)/);
  assert.match(pilot, /required step="1" type="datetime-local"/);
});

test("pilot creation fails closed against the exact one-line profile and low caps", () => {
  assert.match(pilot, /selectedCallerId/);
  assert.match(pilot, /dialerOperations\?\.profiles/);
  assert.match(pilot, /configured_line_cap !== 1/);
  assert.match(pilot, /selectedProfile\.default_line_count !== 1/);
  assert.match(pilot, /selectedProfile\.max_line_count !== 1/);
  assert.match(pilot, /selectedProfile\.effective_line_count !== 1/);
  assert.match(pilot, /selectedProfile\.daily_dial_limit < 25/);
  assert.match(pilot, /selectedProfile\.daily_dial_limit > 50/);
  assert.match(pilot, /selectedProfile\.daily_spend_limit_cents < 1/);
  assert.match(pilot, /selectedProfile\.daily_spend_limit_cents > 1_000/);
  assert.match(pilot, /selectedProfile\.recording_policy !== "company_policy"/);
  assert.match(pilot, /selectedCampaign\.max_concurrent_legs !== 1/);
  assert.match(pilot, /selectedBatch\.total_entries < 75/);
  assert.match(pilot, /selectedBatch\.total_entries > 250/);
  assert.match(pilot, /selectedLine\.id !== selectedProfile\?\.voice_line_id/);
  assert.match(pilot, /createPreflightBlockers\.length === 0/);
  assert.match(pilot, /Pilot creation is blocked until/);
  assert.match(pilot, /caller_user_id: selectedCallerId/);
});

test("switch evidence explains and submits server-observed drills", () => {
  assert.match(pilot, /low_dial_cap_block_tested/);
  assert.match(pilot, /Perform both off\/on switch drills and the low-cap block first/);
  assert.match(pilot, /durable server audit events, stopped sessions, and dial-leg counts/);
  assert.match(pilot, /these checkboxes cannot make the gate pass by themselves/);
});

test("busy, offline, and terminal evidence forms disable every editable control", () => {
  assert.match(pilot, /Actual cost \(USD\)/);
  assert.match(pilot, /<input\s+disabled=\{disabled\}\s+inputMode="decimal"/);
  assert.match(pilot, /<input disabled=\{disabled\} maxLength=\{1000\}/);
  assert.match(pilot, /<textarea disabled=\{disabled\} maxLength=\{2000\}/);
  assert.match(pilot, /<input disabled=\{disabled\} onChange=\{\(event\) => setObservedAt/);
  assert.match(pilot, /<input disabled=\{disabled\} maxLength=\{500\} onChange=\{\(event\) => setReference/);
  assert.match(pilot, /<textarea disabled=\{disabled\} maxLength=\{2000\} minLength=\{8\}/);
});

test("rollback and owner decisions require exact typed phrases", () => {
  assert.match(pilot, /rollbackPhrase === rollbackPhraseRequired/);
  assert.match(pilot, /confirmation_phrase: rollbackPhrase/);
  assert.match(pilot, /acceptPhrase === acceptancePhrase/);
  assert.match(pilot, /rejectPhrase === rejectionPhrase/);
  assert.match(pilot, /revokePhrase === revokePhraseRequired/);
  assert.match(pilot, /confirmation_phrase/);
  assert.match(pilot, /return_unworked_cohort_to_batchdialer: true/);
  assert.match(pilot, /preserve_native_evidence_read_only: true/);
  assert.match(pilot, /ownerCanAccept/);
  assert.match(pilot, /Every authoritative gate must pass/);
  assert.match(pilot, /owner must sign in/);
  assert.doesNotMatch(pilot, /window\.confirm/);
});

test("an accepted pilot has a distinct owner revoke flow", () => {
  assert.match(pilot, /pilot\.status === "accepted"/);
  assert.match(pilot, /Production acceptance was recorded/);
  assert.match(pilot, /hasAction\("revoke", false\)/);
  assert.match(pilot, /"REVOKE SINGLE-LINE DIALER"/);
  assert.match(pilot, /mutatePilot\("revoke", "revoke"/);
  assert.match(pilot, /Revoke native dialer authorization/);
  assert.match(pilot, /pilot\.revoked_at/);
  assert.match(api, /revoked_at: string \| null/);
  assert.match(api, /revocation_reason: string \| null/);
});

test("a rolled-back draft is displayed as cancelled rather than revoked", () => {
  assert.match(api, /\| "cancelled"/);
  assert.match(pilot, /terminalPilotStatuses[\s\S]*"cancelled"/);
  assert.match(pilot, /pilot\.status === "cancelled"/);
  assert.match(pilot, /pilot\.cancelled_at/);
  assert.match(api, /cancelled_at: string \| null/);
  assert.match(api, /cancellation_reason: string \| null/);
});

test("terminal pilot history remains visible while the next controlled pilot can be drafted", () => {
  assert.match(pilot, /!pilot \|\| hasAction\("create", false\) \? \(/);
  assert.match(pilot, /\{pilot \? \(/);
  assert.match(pilot, /hasAction\("create", true\)/);
  assert.match(pilot, /Draft one small native-dialer pilot/);
  assert.match(pilot, /Immutable scope/);
});

test("frontend data and mutation fields mirror the flat D10 API schema", () => {
  assert.match(pilotOverviewType, /attempt_review_queue: ProspectingDialerPilotAttempt\[\]/);
  assert.match(pilotOverviewType, /attempt_reviews: ProspectingDialerPilotAttemptReview\[\]/);
  assert.match(pilotOverviewType, /shift_reviews: ProspectingDialerPilotShift\[\]/);
  assert.match(pilotOverviewType, /total_reviewed_attempts: number/);
  assert.match(pilotOverviewType, /passed_shift_count: number/);
  assert.match(pilotOverviewType, /allowed_actions: string\[\]/);
  assert.doesNotMatch(pilotOverviewType, /owner_authorized|status_label|progress|options/);
  assert.doesNotMatch(pilot, /data\?\.owner_authorized|data\?\.status_label|data\?\.progress|data\?\.options/);
  assert.match(pilot, /controlled_numbers_only: true/);
  assert.match(pilot, /batchdialer_cohort_is_separate: true/);
  assert.match(pilot, /overlapping_record_count: 0/);
  assert.match(pilot, /billing_evidence_reference/);
  assert.match(pilot, /decision: "accept", confirmation_phrase: acceptPhrase, reason:/);
  assert.match(pilot, /decision: "reject", confirmation_phrase: rejectPhrase, reason:/);
  assert.doesNotMatch(pilot, /decision: "(?:accept|reject)"[^\n]*notes:/);
});

test("authorization failures clear sensitive pilot state while outages preserve confirmed evidence", () => {
  assert.match(pilot, /response\.status === 401 \|\| response\.status === 403/);
  assert.match(pilot, /setData\(null\)/);
  assert.match(pilot, /prior pilot snapshot was cleared/);
  assert.match(pilot, /prior confirmed snapshot remains visible/);
  assert.match(pilot, /AbortController/);
  assert.match(pilot, /signal: controller\.signal/);
  assert.match(pilot, /12_000/);
  assert.doesNotMatch(pilot, /localStorage|sessionStorage|console\./);
});

test("Strict Mode remounts stay live and failed saves retain typed evidence", () => {
  assert.match(pilot, /useEffect\(\(\) => \{\s*mountedRef\.current = true;\s*return \(\) => \{/);
  assert.match(pilot, /onSave: \(facts: ReviewPayload\) => Promise<boolean>/);
  assert.match(pilot, /onSave: \(kind: EvidenceKind, evidence: Record<string, unknown>\) => Promise<boolean>/);
  assert.match(pilot, /const saved = await onSave\(\{/);
  assert.match(pilot, /if \(saved\) setNotes\(""\)/);
  assert.match(pilot, /const saved = await onSave\(kind, evidence\);\s*if \(saved\) \{/);
  assert.match(pilot, /async function saveEvidence[\s\S]*return mutatePilot\(/);
  assert.match(pilot, /async function reviewAttempt[\s\S]*return mutatePilot\(/);
  assert.match(pilot, /async function reviewShift[\s\S]*return mutatePilot\(/);
});

test("attempt evidence and mobile controls remain accessible", () => {
  assert.match(pilot, /aria-label="Controlled pilot attempts"/);
  assert.match(pilot, /className=\{styles\.pilotTableWrap\} role="region" tabIndex=\{0\}/);
  assert.match(pilot, /role="radiogroup"/);
  assert.match(pilot, /aria-labelledby=\{`\$\{reviewId\}-\$\{key\}`\}/);
  assert.match(pilot, /scope="col"/);
  assert.match(pilot, /scope="row"/);
  assert.match(pilot, /tabIndex=\{0\}/);
  assert.match(pilot, /aria-busy=\{Boolean\(busyAction\)\}/);
  assert.match(styles, /\.pilotTableWrap:focus-visible/);
  assert.match(styles, /@media \(max-width: 760px\)[\s\S]*\.pilotStageGrid[\s\S]*grid-template-columns: 1fr/);
  assert.match(styles, /\.pilotDecisionGrid input,[\s\S]*min-height: 44px/);
});

test("the D10 audit is exposed as a package script", () => {
  assert.equal(
    packageJson.scripts["audit:prospecting-pilot"],
    "node --test scripts/prospecting-pilot-acceptance-contract.test.mjs",
  );
});
