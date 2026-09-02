import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workspacePath = new URL(
  "../src/app/os/dispositions/disposition-execution-workspace.tsx",
  import.meta.url,
);
const parentPath = new URL(
  "../src/app/os/dispositions/disposition-workspace.tsx",
  import.meta.url,
);
const queueBuilderPath = new URL(
  "../src/app/os/dispositions/disposition-queue-builder.tsx",
  import.meta.url,
);
const listBuilderPath = new URL(
  "../src/app/os/dispositions/disposition-list-builder.tsx",
  import.meta.url,
);
const apiPath = new URL("../src/app/lib/api.ts", import.meta.url);

test("the disposition workspace mounts a permission-aware one-to-one call queue", async () => {
  const [workspace, parent] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(parentPath, "utf8"),
  ]);

  assert.match(parent, /DispositionExecutionWorkspace/);
  assert.match(parent, /tab === "execution"\) return "Outreach desk"/);
  assert.match(workspace, /execution\/sms/);
  assert.match(workspace, /!candidate\.sms\.allowed/);
  assert.match(workspace, /Review the introduction SMS/);
  assert.match(workspace, /Nothing sends automatically/);
  assert.match(workspace, /aria-label="Introduction SMS draft"/);
  assert.match(workspace, /Recipient/);
  assert.match(workspace, /workspace\.property_address/);
  assert.match(workspace, /Send SMS and prepare call/);
  assert.match(workspace, /execution\/calls/);
  assert.match(workspace, /!candidate\.voice\.allowed/);
  assert.match(workspace, /useWebPhone/);
  assert.match(workspace, /webPhone\.startCall/);
  assert.match(workspace, /callIntentId: intent\.id/);
  assert.match(workspace, /fromNumber: intent\.from_number/);
  assert.match(workspace, /let remaining = 10/);
  assert.match(workspace, /startBrowserCall\(buyerId\)/);
  assert.match(workspace, /Call now/);
  assert.match(workspace, /cancelPreparedCall/);
  assert.match(
    workspace,
    /async function startCellphoneCall\(\)[\s\S]*window\.clearInterval\(callCountdownTimer\.current\)/,
  );
  assert.match(workspace, /Use my cellphone/);
  assert.match(workspace, /execution\/forwarded-calls/);
  assert.doesNotMatch(workspace, /voice\/conversations\/\$\{conversationId\}\/forwarded-calls/);
  assert.match(workspace, /Open \{packageLabel\} packet/);
  assert.match(workspace, /Text \$\{packageLabel\} packet/);
  assert.match(workspace, /workspace\.package_is_preliminary/);
  assert.match(workspace, /workspace\.package_status !== "approved"/);
  assert.match(workspace, /issuedPackageLabel = issued\.is_preliminary \? "preliminary" : "approved"/);
  assert.match(workspace, /here is the \$\{issuedPackageLabel\} property package/);
  assert.match(workspace, /package\/share-links/);
  assert.match(workspace, /expires_in_hours: 72/);
  assert.doesNotMatch(workspace, /share-links\/\$\{issued\.id\}\/revoke/);
  assert.match(workspace, /check the buyer conversation before retrying/);
  assert.match(workspace, /idempotency_key: outcomeIdempotencyKey/);
  assert.match(workspace, /setOutcomeIdempotencyKey\(idempotency\("dispo-outcome"\)\)/);
  assert.match(workspace, /idempotency_key: `dispo-showing-/);
  assert.match(workspace, /outcome === "callback"/);
  assert.match(workspace, /No answer creates a 4-hour retry/);
  assert.doesNotMatch(workspace, /setTimeout\([^)]*sendSms/);
  assert.doesNotMatch(workspace, /here is the \$\{packageLabel\} property package/);
});

test("the canonical Buyer Network stays selectable before or after ranking", async () => {
  const [workspace, api] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(apiPath, "utf8"),
  ]);

  assert.match(api, /candidate_id: string \| null/);
  assert.match(api, /ranking_status: "ranked" \| "unranked"/);
  assert.match(api, /rank: number \| null/);
  assert.match(api, /score_basis_points: number \| null/);
  assert.match(workspace, /workspace\.candidates\.length/);
  assert.match(workspace, /canonical Buyer Network record/);
  assert.match(workspace, /Investor queue/);
  assert.match(workspace, /Choose who to contact/);
  assert.match(workspace, /candidates\.map\(\(item\) =>/);
  assert.match(workspace, /key=\{item\.buyer_id\}/);
  assert.match(workspace, /chooseCandidate\(item\.buyer_id\)/);
  assert.match(workspace, /moveCandidate\(item\.buyer_id, -1\)/);
  assert.match(workspace, /moveCandidate\(item\.buyer_id, 1\)/);
  assert.match(workspace, /removeCandidate\(item\.buyer_id\)/);
  assert.match(workspace, /Ranking is guidance\. Choose any investor/);
  assert.match(workspace, /Buyer Network \/ Unranked/);
  assert.match(workspace, /hasRankedFit\(candidate\)/);
  assert.match(workspace, /No rank or fit score is implied/);
  assert.doesNotMatch(workspace, /Math\.round\(item\.score_basis_points \/ 100\)/);
  assert.match(workspace, /candidate\.sms\.allowed/);
  assert.match(workspace, /candidate\.voice\.allowed/);
  assert.match(workspace, /disabled=\{roleOrBusyDisabled\}/);
  assert.doesNotMatch(workspace, /packageApproved|qualifiedBuyerCount/);
});

test("investors can be selected, imported, discovered, and pinned inside Outreach", async () => {
  const [workspace, parent, queueBuilder, listBuilder] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(parentPath, "utf8"),
    readFile(queueBuilderPath, "utf8"),
    readFile(listBuilderPath, "utf8"),
  ]);

  assert.match(parent, /canEditBuyers=\{canEditBuyers\}/);
  assert.match(parent, /const request = useCallback\(async function request<T>/);
  assert.doesNotMatch(parent, /async function request<T>\(path/);
  assert.match(workspace, /<DispositionQueueBuilder/);
  assert.match(workspace, /assetClass=\{workspace\.asset_class\}/);
  assert.match(workspace, /quickDialQueueCount=\{candidates\.length\}/);
  assert.match(queueBuilder, /Find and rank investors/);
  assert.match(queueBuilder, /Pull DealMachine results, add known buyers, and build the outreach list here/);
  assert.match(queueBuilder, /setBuilderOpen\(\(current\) => current \|\| result\.entries\.some/);
  assert.match(queueBuilder, /entry\.source_type === "external" && !entry\.buyer_id/);
  assert.match(queueBuilder, /Quick add investor/);
  assert.match(queueBuilder, /<BuyerForm compact/);
  assert.match(queueBuilder, /QuickDial is empty/);
  assert.match(queueBuilder, /Refresh will stay at zero until a real investor is added/);
  assert.match(queueBuilder, /Build investor list/);
  assert.match(queueBuilder, /Quick add one/);
  assert.match(queueBuilder, /<DispositionListBuilder/);
  assert.match(listBuilder, /Buyer Network/);
  assert.match(listBuilder, /Upload or paste/);
  assert.match(listBuilder, /Choose CSV file/);
  assert.match(listBuilder, /paste rows from a spreadsheet/);
  assert.match(listBuilder, /Preview contacts/);
  assert.match(listBuilder, /queue_buyer_ids: queueIds/);
  assert.match(listBuilder, /Save \$\{totalSelected\} to QuickDial/);
  assert.match(queueBuilder, /\/api\/v1\/buyers\/discovery-runs\/estimate/);
  assert.match(queueBuilder, /confirmed_estimated_credits: estimate\.estimated_credits/);
  assert.match(queueBuilder, /confirmed_request_fingerprint: estimate\.request_fingerprint/);
  assert.match(queueBuilder, /buyer-pool\/candidates\/\$\{entry\.candidate_id\}\/conversion/);
  assert.match(queueBuilder, /<BuyerForm/);
  assert.match(queueBuilder, /queue_buyer_ids: nextQueueBuyerIds/);
  assert.match(queueBuilder, /current_buyer_id: buyerId/);
  assert.match(queueBuilder, /Pin for outreach/);
  assert.match(queueBuilder, /Land-safe queue building is active/);
  assert.match(queueBuilder, /current search is residential/);
  assert.match(queueBuilder, /Never sends outreach automatically/);
});

test("the outreach session keeps result recording operator-led", async () => {
  const workspace = await readFile(workspacePath, "utf8");

  assert.match(workspace, /Investor QuickDial/);
  assert.match(workspace, /Contact an investor, then move to the next/);
  assert.match(workspace, /styles\.currentInvestor/);
  assert.match(workspace, /styles\.queuePanel/);
  assert.match(workspace, /styles\.relationshipPanel/);
  assert.match(workspace, /styles\.quickContactBar/);
  assert.match(workspace, /Current investor/);
  assert.match(workspace, /<dt>Position<\/dt>/);
  assert.match(workspace, /workspace\.remaining_candidate_count/);
  assert.match(workspace, /Open relationship profile/);
  assert.match(workspace, /Review follow-up email/);
  assert.match(workspace, /async function recordOutcome\(outcome: Outcome, advance: "next" \| "stay"\)/);
  assert.match(workspace, /setSelectedOutcome\(outcome\.value\); void saveCurrentBuyerState/);
  assert.match(workspace, /Save & stay/);
  assert.match(workspace, /Save & next/);
  assert.match(workspace, /Schedule follow-up/);
  assert.match(workspace, /Skip for now/);
  assert.match(workspace, /Pause session/);
  assert.match(workspace, /advance === "next"[\s\S]*advance_to_next: true/);
  assert.match(workspace, /async function continueToNextBuyer\(\)[\s\S]*advance_to_next: true/);
  assert.match(workspace, /setWorkspace\(result\);[\s\S]*setSavedOutcome/);
  assert.match(workspace, /No buyer outcome was changed/);
  assert.match(workspace, /saved across visits/);
  assert.doesNotMatch(workspace, /onClick=\{\(\) => void recordOutcome\(outcome\.value\)\}/);
});

test("the execution desk durably restores operator session state", async () => {
  const [workspace, api] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(apiPath, "utf8"),
  ]);

  assert.match(api, /export type DispositionExecutionSession/);
  assert.match(api, /buyer_states: Record<string, DispositionExecutionBuyerState>/);
  assert.match(api, /session: DispositionExecutionSession/);
  assert.match(workspace, /execution\/session/);
  assert.match(workspace, /method: "PATCH"/);
  assert.match(workspace, /result\.session\.current_buyer_id/);
  assert.match(workspace, /result\.session\.skipped_buyer_ids/);
  assert.match(workspace, /result\.session\.buyer_states/);
  assert.match(workspace, /sms_draft: smsDraft/);
  assert.match(workspace, /email_subject: emailSubject/);
  assert.match(workspace, /email_draft: emailDraft/);
  assert.match(workspace, /email_sender_alias_id: emailSenderId \|\| null/);
  assert.match(workspace, /notes_draft: notes/);
  assert.match(workspace, /selected_outcome: selectedOutcome/);
  assert.match(workspace, /state: "paused"/);
  assert.match(workspace, /advance_to_next: true/);
  assert.match(workspace, /This exact position will resume until you continue/);
  assert.doesNotMatch(workspace, /browser session|while this screen stays open/i);
});

test("one-to-one email is editable, permission-aware, durable, and relationship-linked", async () => {
  const [workspace, api] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(apiPath, "utf8"),
  ]);

  assert.match(api, /email_subject: string/);
  assert.match(api, /email_draft: string/);
  assert.match(api, /email_sender_alias_id: string \| null/);
  assert.match(workspace, /\/api\/v1\/email\/aliases/);
  assert.match(workspace, /execution\/email/);
  assert.match(workspace, /aria-label="Investor follow-up email draft"/);
  assert.match(workspace, /Nothing sends until you approve it/);
  assert.match(workspace, /Insert \$\{packageLabel\} packet link/);
  assert.match(workspace, /expires_in_hours: 72/);
  assert.match(workspace, /emailIdempotencyKeyRef/);
  assert.match(workspace, /Email sender unavailable/);
  assert.match(workspace, /relationship activity/i);
  assert.match(workspace, /\/api\/v1\/buyers\/\$\{buyerId\}\/profile/);
  assert.match(workspace, /item\.direction === "inbound"/);
  assert.match(workspace, /Open and update full relationship/);
  assert.doesNotMatch(workspace, /composer arrives in Phase 4/i);
});

test("one-to-one actions use a stable buyer reference and passed buyers remain recoverable", async () => {
  const [workspace, api] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(apiPath, "utf8"),
  ]);

  assert.match(api, /decision_status: string/);
  assert.match(api, /lock_version: number \| null/);
  assert.match(api, /actionable: boolean/);
  assert.match(api, /action_blockers: string\[\]/);
  assert.match(workspace, /function executionBuyerReference/);
  assert.match(workspace, /buyer_id: candidate\.buyer_id/);
  assert.match(workspace, /candidate\.candidate_id \? \{ candidate_id: candidate\.candidate_id \} : \{\}/);
  assert.ok(
    [...workspace.matchAll(/\.\.\.executionBuyerReference\(candidate\)/g)].length >= 6,
    "every one-to-one action must include the canonical buyer reference",
  );
  assert.doesNotMatch(workspace, /candidate_id: candidate\.candidate_id,/);
  assert.match(workspace, /candidate\.buyer_id === buyerIdRef\.current && candidate\.actionable/);
  assert.match(workspace, /!candidate\?\.actionable/);
  assert.match(workspace, /candidateAvailabilityLabel/);
  assert.match(workspace, /"Clear pass"/);
  assert.match(workspace, /buyer-pool\/candidates\/\$\{candidate\.candidate_id\}/);
  assert.match(workspace, /expected_version: candidate\.lock_version/);
  assert.match(workspace, /decision_status: "undecided"/);
  assert.match(workspace, /isPassedCandidate\(candidate\) && !isDoNotContact\(candidate\)/);
});

test("showing controls persist state without exposing access secrets", async () => {
  const workspace = await readFile(workspacePath, "utf8");

  assert.match(workspace, /access_status/);
  assert.match(workspace, /Shared privately/);
  assert.match(workspace, /24-hour follow-up/);
  assert.match(workspace, /const finished = \["completed", "cancelled", "no_show"\]/);
  assert.doesNotMatch(workspace, /name="(?:lockbox|alarm|access)_code"/i);
});
