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
const apiPath = new URL("../src/app/lib/api.ts", import.meta.url);

test("the disposition workspace mounts a permission-aware one-to-one call queue", async () => {
  const [workspace, parent] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(parentPath, "utf8"),
  ]);

  assert.match(parent, /DispositionExecutionWorkspace/);
  assert.match(parent, /tab === "execution"\) return "One-to-one"/);
  assert.match(workspace, /execution\/sms/);
  assert.match(workspace, /!candidate\.sms\.allowed/);
  assert.match(workspace, /Review introduction text/);
  assert.match(workspace, /Nothing sends automatically/);
  assert.match(workspace, /aria-label="Introduction SMS draft"/);
  assert.match(workspace, /Recipient/);
  assert.match(workspace, /workspace\.property_address/);
  assert.match(workspace, /Send text and prepare call/);
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
  assert.match(workspace, /Call through my cellphone/);
  assert.match(workspace, /execution\/forwarded-calls/);
  assert.doesNotMatch(workspace, /voice\/conversations\/\$\{conversationId\}\/forwarded-calls/);
  assert.match(workspace, /Open \{packageLabel\} investor packet/);
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
  assert.match(workspace, /No-answer gets a 4-hour retry task/);
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
  assert.match(workspace, />Buyer Network</);
  assert.match(workspace, /Choose a buyer from Buyer Network/);
  assert.match(workspace, /candidates\.map\(\(item\) =>/);
  assert.match(workspace, /key=\{item\.buyer_id\}/);
  assert.match(workspace, /chooseCandidate\(item\.buyer_id\)/);
  assert.match(workspace, /value=\{candidate\?\.buyer_id \?\? ""\}/);
  assert.match(workspace, /Ranked fit is guidance, not a queue gate/);
  assert.match(workspace, /Buyer Network \/ Unranked/);
  assert.match(workspace, /hasRankedFit\(candidate\)/);
  assert.match(workspace, /No rank or fit score is implied/);
  assert.doesNotMatch(workspace, /Math\.round\(item\.score_basis_points \/ 100\)/);
  assert.match(workspace, /item\.sms\.allowed/);
  assert.match(workspace, /item\.voice\.allowed/);
  assert.match(workspace, /disabled=\{roleOrBusyDisabled\}/);
  assert.doesNotMatch(workspace, /packageApproved|qualifiedBuyerCount/);
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
