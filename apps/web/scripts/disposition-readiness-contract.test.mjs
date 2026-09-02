import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const workspace = readFileSync(resolve(appRoot, "os/dispositions/disposition-workspace.tsx"), "utf8");
const workspaceStyles = readFileSync(resolve(appRoot, "os/dispositions/dispositions.module.css"), "utf8");
const panel = readFileSync(resolve(appRoot, "os/dispositions/disposition-readiness-panel.tsx"), "utf8");
const panelStyles = readFileSync(resolve(appRoot, "os/dispositions/disposition-readiness-panel.module.css"), "utf8");
const packageWorkspace = readFileSync(resolve(appRoot, "os/dispositions/disposition-package-readiness.tsx"), "utf8");
const buyerPool = readFileSync(resolve(appRoot, "os/dispositions/disposition-buyer-pool.tsx"), "utf8");
const execution = readFileSync(resolve(appRoot, "os/dispositions/disposition-execution-workspace.tsx"), "utf8");
const outreach = readFileSync(resolve(appRoot, "os/dispositions/disposition-outreach-workspace.tsx"), "utf8");
const offers = readFileSync(resolve(appRoot, "os/dispositions/disposition-offer-room.tsx"), "utf8");
const provider = readFileSync(resolve(appRoot, "os/dispositions/disposition-provider-workspace.tsx"), "utf8");
const desk = readFileSync(resolve(appRoot, "os/deals/disposition-desk-workspace.tsx"), "utf8");
const setup = readFileSync(resolve(appRoot, "os/dispositions/disposition-setup-workspace.tsx"), "utf8");

test("the web client models the additive advisory readiness contract", () => {
  assert.match(api, /export type DispositionCaseReadiness/);
  assert.match(api, /is_advisory: true/);
  assert.match(api, /"available"[\s\S]*"ready"[\s\S]*"blocked"[\s\S]*"complete"[\s\S]*"not_applicable"/);
  assert.match(api, /"hard_stop"[\s\S]*"release_gate"[\s\S]*"warning"/);
  assert.match(api, /best_action_key: string \| null/);
  assert.match(api, /parallel_action_keys: string\[\]/);
  assert.match(api, /source_fingerprint: string/);
  assert.match(api, /remediation: DispositionReadinessRemediation \| null/);
  assert.match(api, /checklist\?: DispositionDeskChecklist \| null/);
});

test("the persistent panel offers guidance and every action-specific check without imposing an order", () => {
  assert.match(workspace, /<DispositionReadinessPanel/);
  assert.match(workspace, /\/api\/v1\/dispositions\/cases\/\$\{caseId\}\/readiness/);
  assert.match(panel, /Advisory workbench/);
  assert.match(panel, /never forces a tab order or disables an otherwise applicable workflow action/);
  assert.match(panel, /Suggested action \(optional\)/);
  assert.match(panel, /Also available now/);
  assert.match(panel, /<details className=\{styles\.checklist\}>/);
  assert.match(panel, /All action-specific checks/);
  assert.match(panel, /readiness\.actions\.filter/);
  assert.match(panel, /actions complete/);
  assert.match(panel, /The deal workspace remains available/);
  assert.match(panel, /Showing the last checklist for this deal/);
  assert.doesNotMatch(panel, /disabled=/);
});

test("attention badges and remediation links navigate to stable workbench anchors", () => {
  assert.match(workspace, /tabAttention\(item\)/);
  assert.match(workspace, /className=\{styles\.tabBadge\}/);
  assert.match(workspace, /tabRootAnchors/);
  assert.match(workspace, /document\.getElementById\(tabRootAnchors\[allowedTab\]\)/);
  for (const [source, anchor] of [
    [packageWorkspace, "package-versions"],
    [buyerPool, "buyer-pool"],
    [execution, "call-queue"],
    [outreach, "campaigns"],
    [offers, "offer-room"],
    [offers, "buyer-selection"],
    [offers, "funding"],
    [provider, "provider-handoff"],
    [workspace, "deal-reconciliation"],
  ]) assert.match(source, new RegExp(`id="${anchor}"`));
});

test("package, pool, call, and outreach work remain usable while checklist evidence is incomplete", () => {
  assert.doesNotMatch(workspace, /packageApproved=|qualifiedBuyerCount=/);
  assert.match(packageWorkspace, /shoppingVersion = currentApprovedVersion \? approvedVersion : latestVersion/);
  assert.match(packageWorkspace, /Find and rank investors in/);
  assert.match(buyerPool, /Refresh buyer ranking/);
  assert.match(buyerPool, /\/api\/v1\/dispositions\/cases\/\$\{caseId\}\/matches/);
  assert.match(outreach, /Prepare recipient pool/);
  assert.match(outreach, /\/api\/v1\/dispositions\/cases\/\$\{caseId\}\/campaigns\/release/);
  assert.match(buyerPool, /Package, proof-of-funds, and match-readiness gaps remain visible warnings while you shop/);
  assert.match(execution, /These items do not prevent logging work/);
  assert.match(execution, /Contact controls still follow the buyer/);
  assert.match(outreach, /Checklist gaps do not stop drafting or shopping/);
  assert.match(provider, /Package checklist gaps do not disable preparation/);
});

test("legacy case recovery opens without private economics or required pricing fields", () => {
  assert.doesNotMatch(setup, /if \(!canViewPrivateEconomics\)/);
  assert.match(setup, /\.\.\.\(canViewPrivateEconomics \? \{/);
  assert.match(setup, /asking_price_cents: optionalCents/);
  assert.match(setup, /minimum_acceptable_cents: optionalCents/);
  assert.match(setup, /\} : \{\}\)/);
  assert.doesNotMatch(setup, /name="asking_price"[^>]*required/);
  assert.doesNotMatch(setup, /name="minimum_price"[^>]*required/);
  assert.match(setup, /no asking-price, minimum, owner, plan, or mode entry is required first/i);
  assert.match(setup, /checklist will keep unfinished setup visible/i);
});

test("activity and offer controls hydrate the full Buyer Network independently of ranking", () => {
  assert.match(api, /export type BuyerListResponse/);
  assert.match(workspace, /request<BuyerListResponse>/);
  const networkFlow = workspace.slice(
    workspace.indexOf("async function loadBuyerNetworkChoices"),
    workspace.indexOf("async function loadBuyerPoolChoices"),
  );
  assert.match(networkFlow, /\/api\/v1\/buyers\?\$\{query\.toString\(\)\}/);
  assert.match(networkFlow, /limit: "200"/);
  assert.match(networkFlow, /offset: String\(offset\)/);
  assert.match(networkFlow, /while \(offset < total\)/);
  assert.doesNotMatch(networkFlow, /status: "/);
  assert.match(networkFlow, /buyer\.archived_at === null && buyer\.status !== "archived"/);
  assert.match(workspace, /request<DispositionBuyerPoolPage>/);
  assert.match(workspace, /page_size: "100"/);
  assert.match(workspace, /source: "all"/);
  assert.match(workspace, /stage: "all"/);
  assert.match(workspace, /while \(entries\.length < total\)/);
  assert.match(workspace, /entries\.filter\(\(entry\) => entry\.buyer_id !== null\)/);
  assert.match(workspace, /if \(!entry\.buyer_id \|\| choices\.has\(entry\.buyer_id\)\) continue/);
  assert.match(workspace, /latest_proof_document_id: legacyMatch\?\.latest_proof_document_id \?\? null/);
  assert.match(workspace, /mergeBuyerChoices[\s\S]*buyerNetworkCaseId === selected\?\.id[\s\S]*buyerPoolCaseId === selected\?\.id[\s\S]*selected\?\.matches \?\? \[\]/);
  assert.match(workspace, /buyerChoices\.map\(\(item\) => <option/);
  assert.match(workspace, /disabled=\{busy \|\| !canEditDeals \|\| !buyerChoices\.length\}/);
  assert.match(workspace, /buyers=\{buyerChoices\}/);
  assert.doesNotMatch(workspace, /buyers=\{selected\.matches\.map/);
  assert.doesNotMatch(workspace, /selected\.matches\.map\(\(item\) => <option/);
  assert.match(workspace, /Pool and legacy choices remain usable when the canonical Buyer Network is unavailable/);
  assert.match(workspace, /Buyer Network and legacy choices remain usable when the ranked pool is unavailable/);
  assert.match(workspace, /Promise\.all\(\[[\s\S]*loadBuyerNetworkChoices\(nextId\)[\s\S]*loadBuyerPoolChoices\(nextId\)/);
});

test("buyer decisions permit primary-only coverage and warning-bearing replacement options", () => {
  assert.match(offers, /backupOffer \? \[backupOffer\.id\] : \[\]/);
  assert.match(offers, /Continue without a backup/);
  assert.match(offers, /Missing backup coverage remains visible as a warning/);
  assert.match(offers, /selectableReplacementOptions = data\.replacement_options\.filter\(\(item\) => item\.eligible\)/);
  assert.match(offers, /selectableReplacementOptions\.map\(\(item\) => <option/);
  assert.match(offers, /expected_replacement_offer_lock_version: replacementOption\?\.offer_lock_version \?\? null/);
  assert.match(offers, /replacement_offer_id: replacementOption\?\.offer_id \?\? null/);
  assert.match(offers, /No replacement now - record outcome and reopen shopping/);
  assert.match(offers, /Record outcome and reopen shopping/);
  assert.doesNotMatch(offers, /!data\.current_selection \|\| !selectableReplacementOptions\.length/);
  assert.doesNotMatch(offers, /acknowledge_no_backup|approved minimum price cannot be overridden/i);
  assert.match(api, /backup_coverage_state: "covered" \| "missing"/);
  assert.match(api, /advisory_snapshot: Record<string, unknown>/);
  assert.match(api, /offer_lock_version: number/);
  assert.match(api, /package_is_preliminary\?: boolean/);
});

test("desk guidance and readiness UI are responsive and preserve explicit role restrictions", () => {
  assert.match(desk, /best_action_href \?\? item\.primary_action\.href/);
  assert.match(desk, /Suggested action \(optional\)/);
  assert.match(desk, /<details className=\{styles\.cardChecklist\}>/);
  assert.match(desk, /All checklist issues/);
  assert.match(desk, /Also available now/);
  assert.match(panelStyles, /@media \(max-width: 760px\)/);
  assert.match(panelStyles, /@media \(max-width: 520px\)/);
  assert.match(workspaceStyles, /container: disposition-detail \/ inline-size/);
  assert.match(panelStyles, /@container disposition-detail \(max-width: 980px\)/);
  assert.match(panelStyles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(workspace, /Read-only access: disposition actions are disabled for your role/);
  assert.match(workspace, /Executed House and Land transactions appear here for disposition work, even while setup is incomplete/);
});
