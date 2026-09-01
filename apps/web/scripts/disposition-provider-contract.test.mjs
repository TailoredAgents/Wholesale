import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const deals = readFileSync(resolve(appRoot, "os/deals/deals-workspace.tsx"), "utf8");
const disposition = readFileSync(resolve(appRoot, "os/dispositions/disposition-workspace.tsx"), "utf8");
const provider = readFileSync(resolve(appRoot, "os/dispositions/disposition-provider-workspace.tsx"), "utf8");
const providerStyles = readFileSync(resolve(appRoot, "os/dispositions/disposition-provider-workspace.module.css"), "utf8");

test("DS8 keeps the InvestorLift handoff inside the canonical disposition workspace", () => {
  assert.match(disposition, /<DispositionProviderWorkspace/);
  assert.match(disposition, /tab === "provider"\) return "InvestorLift"/);
  assert.match(disposition, /activeTab === "provider"/);
  assert.match(deals, /"provider"/);
  assert.match(api, /export type DispositionProviderWorkspace/);
  assert.match(provider, /\/api\/v1\/dispositions\/cases\/\$\{caseId\}\/provider`/);
});

test("the UI states the manual-only unverified provider boundary", () => {
  for (const text of [
    "Manual-only",
    "No live sync",
    "The direct InvestorLift API contract is unverified.",
    "Every handoff preserves whether its source package was approved or Preliminary.",
    "Private Stonegate economics are never included in the provider bundle.",
    "Inquiries, engagement, and offers stay staged until a person reviews them.",
  ]) assert.match(provider, new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

  assert.doesNotMatch(provider, /INVESTORLIFT_(?:API|ACCESS|SECRET|TOKEN|KEY)/i);
  assert.doesNotMatch(provider, /https:\/\/(?:api\.)?investorlift/i);
  assert.match(api, /api_contract_verified: boolean/);
  assert.match(api, /live_transport_enabled: boolean/);
  assert.match(api, /credential_required: boolean/);
});

test("manual publication accepts the latest usable package and preserves its exact provenance", () => {
  for (const step of [
    "Prepare",
    "Approve exact handoff",
    "Download",
    "Publish manually",
    "Record and review",
  ]) assert.match(provider, new RegExp(step));

  assert.match(provider, /expected_latest_revision: latestRevisionNumber\(data\)/);
  assert.match(provider, /listing-revisions\/\$\{revision\.id\}\/approve/);
  assert.match(provider, /expected_lock_version: revision\.lock_version/);
  assert.match(provider, /attestation: values\.get\("attestation"\) === "on"/);
  assert.match(provider, /listing-revisions\/\$\{revision\.id\}\/bundle/);
  assert.match(provider, /data\?\.available_package \?\? data\?\.approved_package/);
  assert.match(provider, /shoppingPackageStatus/);
  assert.match(provider, /shoppingIsPreliminary/);
  assert.match(provider, /shoppingPackage\.is_current === false/);
  assert.doesNotMatch(provider, /!data\.approved_package\?\.is_current/);
  assert.match(provider, /Package checklist gaps do not disable preparation/);
  assert.match(api, /available_package\?: DispositionProviderAvailablePackage \| null/);
  assert.match(api, /package_is_preliminary\?: boolean/);
  assert.match(api, /package_was_current_at_prepare\?: boolean/);
  assert.match(api, /package_is_current_now\?: boolean/);
  assert.match(provider, /Current handoff label: \{revisionIsPreliminary\(revision\) \? "Preliminary" : "Approved"\}/);
  assert.match(provider, /Frozen source \{labelize\(revision\.package_status \?\? "approved"\)\}/);
  assert.match(provider, /Package or source facts changed since preparation/);
  assert.match(provider, /Current handoff label: Preliminary\. Its frozen source was preliminary or the package or source facts changed/);
  assert.match(provider, /Nothing will be published/);
});

test("provider activity remains staged and separate from buyer selection", () => {
  assert.match(provider, /\/provider\/manual-events`/);
  assert.match(provider, /\/provider\/manual-events\/\$\{evidence\.id\}/);
  assert.match(provider, /It will not select a buyer or send a response/);
  assert.match(provider, /Buyer selection remains a separate human decision/);
  assert.match(provider, /These records are evidence only\. They cannot select a buyer or accept an offer\./);
  assert.match(api, /selection_eligible: false/);
  assert.match(api, /review_status: "staged" \| "reviewed" \| "dismissed"/);
  assert.doesNotMatch(provider, /auto.?select/i);
});

test("manual link, refresh, export, and disconnect remain observable and resilient", () => {
  assert.match(provider, /\/provider\/manual-link/);
  assert.match(provider, /expected_listing_version: data\.listing\?\.lock_version/);
  assert.match(provider, /\/provider\/manual-refresh/);
  assert.match(provider, /No provider API was called/);
  assert.match(provider, /\/provider\/export\?format=json/);
  assert.match(provider, /\/provider\/export\?format=csv/);
  assert.match(provider, /\/provider\/disconnect/);
  assert.match(provider, /Stonegate history and owned buyer operations remain intact/);
  assert.match(provider, /Recent manual operations/);
  assert.equal((provider.match(/<span>Audit trail<\/span><h5>Recent manual operations<\/h5>/g) ?? []).length, 1);
  assert.match(provider, /request_sha256/);
});

test("the provider workspace is permission-aware, accessible, responsive, and free of mojibake", () => {
  assert.match(provider, /data\.permissions\.can_prepare/);
  assert.match(provider, /data\.permissions\.can_approve/);
  assert.match(provider, /data\.permissions\.can_record_manual/);
  assert.match(provider, /data\?\.permissions\.can_disconnect/);
  assert.match(provider, /data\?\.permissions\.can_export/);
  assert.match(provider, /role="alert"/);
  assert.match(provider, /aria-live="polite"/);
  assert.match(provider, /aria-label="InvestorLift manual handoff"/);
  assert.match(provider, /Retry/);
  assert.match(providerStyles, /min-height: 44px/);
  assert.match(providerStyles, /@media \(max-width:/);
  assert.match(providerStyles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.equal((provider.match(/className=\{styles\.revisionEvidence\}/g) ?? []).length, 1);
  assert.doesNotMatch(provider, /[\u00b7\u00c2\u00c3\ufffd]/);
});
