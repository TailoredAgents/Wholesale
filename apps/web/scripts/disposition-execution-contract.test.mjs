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
const workspaceStylesPath = new URL(
  "../src/app/os/dispositions/disposition-execution-workspace.module.css",
  import.meta.url,
);
const dispositionStylesPath = new URL(
  "../src/app/os/dispositions/dispositions.module.css",
  import.meta.url,
);
const queueBuilderStylesPath = new URL(
  "../src/app/os/dispositions/disposition-queue-builder.module.css",
  import.meta.url,
);

test("the outreach desk uses compact, professional workspace controls", async () => {
  const [workspaceStyles, dispositionStyles, queueBuilderStyles] = await Promise.all([
    readFile(workspaceStylesPath, "utf8"),
    readFile(dispositionStylesPath, "utf8"),
    readFile(queueBuilderStylesPath, "utf8"),
  ]);

  assert.match(workspaceStyles, /\.hero, \.panel \{[^}]*border-radius: 4px/);
  assert.match(workspaceStyles, /\.panel button, \.hero button \{[^}]*min-height: 30px/);
  assert.match(workspaceStyles, /\.queuePanel \{[^}]*border-radius: 4px/);
  assert.match(workspaceStyles, /\.queueSearch \{[^}]*display: flex/);
  assert.match(workspaceStyles, /\.queueRowMenu > div \{[^}]*position: absolute/);
  assert.match(workspaceStyles, /\.queueRowActions \.queueContactAction \{[^}]*background: #17633d/);
  assert.match(workspaceStyles, /\.outreachConsole \{[^}]*padding: 0/);
  assert.match(workspaceStyles, /\.channelTabs \{[^}]*grid-template-columns: repeat\(3/);
  assert.match(workspaceStyles, /\.conversationTimeline \{[^}]*min-height: 230px/);
  assert.match(workspaceStyles, /\.resultDock \{[^}]*border-top/);
  assert.doesNotMatch(workspaceStyles, /\.outcomePanel \{/);
  assert.match(dispositionStyles, /\.workspacePrimaryNav > button \{[^}]*min-height: 50px/);
  assert.match(dispositionStyles, /\.workspaceSecondaryNav button \{[^}]*border-radius: 3px/);
  assert.match(queueBuilderStyles, /\.builder \{[^}]*border-radius: 4px/);
});

test("the disposition workspace mounts a permission-aware one-to-one call queue", async () => {
  const [workspace, parent] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(parentPath, "utf8"),
  ]);

  assert.match(parent, /DispositionExecutionWorkspace/);
  assert.match(parent, /tab === "execution"\) return "Outreach desk"/);
  assert.match(workspace, /execution\/sms/);
  assert.match(workspace, /!candidate\.sms\.allowed/);
  assert.match(workspace, /Message \{candidate\.name\}/);
  assert.match(workspace, /Nothing sends until you choose Send text/);
  assert.match(workspace, /aria-label="Introduction SMS draft"/);
  assert.match(workspace, /workspace\.property_address/);
  assert.match(workspace, /Send text/);
  assert.match(workspace, /execution\/calls/);
  assert.match(workspace, /!candidate\.voice\.allowed/);
  assert.match(workspace, /useWebPhone/);
  assert.match(workspace, /webPhone\.startCall/);
  assert.match(workspace, /callIntentId: intent\.id/);
  assert.match(workspace, /fromNumber: intent\.from_number/);
  assert.match(workspace, /A call begins only when you choose one of these options/);
  assert.doesNotMatch(workspace, /callCountdown|beginCallCountdown|cancelPreparedCall/);
  assert.doesNotMatch(workspace, /initializeHeadset/);
  const sendSmsFunction = workspace.match(/async function sendSms\(\)[\s\S]*?(?=\n  async function startBrowserCall)/)?.[0] ?? "";
  assert.ok(sendSmsFunction);
  assert.doesNotMatch(sendSmsFunction, /setActiveChannel|startBrowserCall/);
  assert.match(workspace, /Use my cellphone/);
  assert.match(workspace, /execution\/forwarded-calls/);
  assert.doesNotMatch(workspace, /voice\/conversations\/\$\{conversationId\}\/forwarded-calls/);
  assert.match(workspace, /Open \{packageLabel\} packet/);
  assert.match(workspace, /Text \$\{packageLabel\} packet/);
  assert.match(workspace, /className=\{styles\.packetQuickBar\}/);
  assert.match(workspace, /Investor asks for the packet\?/);
  assert.match(workspace, /async function copyPacketLink\(\)/);
  assert.match(workspace, /navigator\.clipboard\.writeText\(issued\.share_url\)/);
  assert.match(workspace, /Copy link/);
  assert.match(workspace, /Send by text/);
  assert.match(workspace, /Send by email/);
  assert.match(workspace, /async function emailInvestorPacket\(\)/);
  assert.match(workspace, /idempotency\("dispo-packet-email"\)/);
  assert.match(workspace, /packetEmailUnavailable/);
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
  assert.match(workspace, /makeCandidateNext\(item\.buyer_id\)/);
  assert.match(workspace, /moveCandidateToTop\(item\.buyer_id\)/);
  assert.match(workspace, /moveCandidateBefore\(draggedBuyerId, item\.buyer_id\)/);
  assert.match(workspace, /aria-label="Search investor queue"/);
  assert.match(workspace, /draggable=\{busy === null\}/);
  assert.match(workspace, /chooseCandidate\(item\.buyer_id, true\)/);
  assert.match(workspace, /data-tone="current">Current/);
  assert.match(workspace, /data-tone="next">Next/);
  assert.match(workspace, /selectedQueueItemRef\.current\?\.scrollIntoView/);
  assert.doesNotMatch(workspace, /serverRecommendedCandidate/);
  assert.doesNotMatch(workspace, /disabled=\{busy !== null \|\| sessionPaused\} onClick=\{\(\) => void chooseCandidate/);
  assert.match(workspace, /Ranking details/);
  assert.doesNotMatch(workspace, />Unranked</);
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
  assert.match(listBuilder, /Select CSV file/);
  assert.match(listBuilder, /contacts read from/);
  assert.match(listBuilder, /then click Save to QuickDial/);
  assert.match(listBuilder, /primary_contact_name/);
  assert.match(listBuilder, /buyer_entity_names/);
  assert.match(listBuilder, /phone_1/);
  assert.match(listBuilder, /outreach_rank/);
  assert.match(listBuilder, /outreach_contact_key/);
  assert.match(listBuilder, /DealMachine investor research export/);
  assert.match(listBuilder, /source_external_key: contact\.sourceExternalKey/);
  assert.match(listBuilder, /Alternate phones/);
  assert.match(listBuilder, /Alternate emails/);
  assert.match(listBuilder, /paste rows from a spreadsheet/);
  assert.match(listBuilder, /Preview pasted contacts/);
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
  assert.match(workspace, /styles\.conversationTimeline/);
  assert.match(workspace, /styles\.conversationHeader/);
  assert.match(workspace, /styles\.conversationMeta/);
  assert.match(workspace, /slice\(0, 12\)\.reverse\(\)/);
  assert.match(workspace, /data-direction=\{item\.direction \?\? "activity"\}/);
  assert.match(workspace, /Shared with the canonical buyer relationship and Inbox history/);
  assert.match(workspace, /element\.scrollTop = element\.scrollHeight/);
  assert.match(workspace, /<ol aria-live="polite" ref=\{timelineRef\}>/);
  assert.match(workspace, /document\.visibilityState === "visible"/);
  assert.match(workspace, /30_000/);
  assert.match(workspace, /loadBuyerTimeline\(activeTimelineBuyerId\)/);
  assert.match(workspace, /className=\{styles\.channelTabs\} role="tablist"/);
  assert.match(workspace, /aria-selected=\{activeChannel === "sms"\}/);
  assert.match(workspace, /aria-selected=\{activeChannel === "call"\}/);
  assert.match(workspace, /aria-selected=\{activeChannel === "email"\}/);
  assert.match(workspace, /activeChannel === "sms" \? <div/);
  assert.match(workspace, /activeChannel === "call" \? <div/);
  assert.match(workspace, /activeChannel === "email" \? <div/);
  assert.doesNotMatch(workspace, /styles\.cadenceSteps/);
  assert.doesNotMatch(workspace, /styles\.quickContactBar/);
  assert.match(workspace, /Current investor/);
  assert.match(workspace, /<dt>Position<\/dt>/);
  assert.match(workspace, /workspace\.remaining_candidate_count/);
  assert.match(workspace, /Open and update full relationship/);
  assert.doesNotMatch(workspace, /Open relationship profile/);
  assert.match(workspace, /aria-label="Investor follow-up email subject"/);
  assert.doesNotMatch(workspace, /smsComposerOpen|emailComposerOpen/);
  assert.match(workspace, /className=\{styles\.resultDock\}/);
  assert.match(workspace, /Finished an interaction\?/);
  assert.match(workspace, /setResultComposerOpen\(true\)/);
  assert.match(workspace, /async function recordOutcome\(outcome: Outcome, advance: "next" \| "stay"\)/);
  assert.match(workspace, /setSelectedOutcome\(outcome\.value\); void saveCurrentBuyerState/);
  assert.match(workspace, /Save & stay/);
  assert.match(workspace, /Save & next/);
  assert.match(workspace, /selectedOutcome === "callback" \? <label/);
  assert.match(workspace, /Skip for now/);
  assert.doesNotMatch(workspace, /Pause session|Resume session|Session paused/);
  assert.match(workspace, /advance === "next"[\s\S]*advance_to_next: true/);
  assert.match(workspace, /async function continueToNextBuyer\(\)[\s\S]*advance_to_next: true/);
  assert.match(workspace, /setWorkspace\(result\);[\s\S]*setSavedOutcome/);
  assert.match(workspace, /No buyer outcome was changed/);
  assert.match(workspace, /queue order and drafts remain saved/);
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
  assert.doesNotMatch(workspace, /state: "paused"/);
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
  assert.match(workspace, /Delivery and replies will appear in the conversation/);
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
