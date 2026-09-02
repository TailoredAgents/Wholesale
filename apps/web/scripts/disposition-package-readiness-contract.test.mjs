import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const dealsWorkspace = readFileSync(resolve(appRoot, "os/deals/deals-workspace.tsx"), "utf8");
const dispositionWorkspace = readFileSync(resolve(appRoot, "os/dispositions/disposition-workspace.tsx"), "utf8");
const dispositionDealPage = readFileSync(resolve(appRoot, "os/dispositions/[caseId]/page.tsx"), "utf8");
const packageWorkspace = readFileSync(resolve(appRoot, "os/dispositions/disposition-package-readiness.tsx"), "utf8");
const buyerPool = readFileSync(resolve(appRoot, "os/dispositions/disposition-buyer-pool.tsx"), "utf8");
const outreach = readFileSync(resolve(appRoot, "os/dispositions/disposition-outreach-workspace.tsx"), "utf8");
const packageStyles = readFileSync(resolve(appRoot, "os/dispositions/disposition-package-readiness.module.css"), "utf8");
const setup = readFileSync(resolve(appRoot, "os/dispositions/disposition-setup-workspace.tsx"), "utf8");
const setupPage = readFileSync(resolve(appRoot, "os/dispositions/page.tsx"), "utf8");

test("DS5 remains inside the canonical deal package tab", () => {
  assert.match(dispositionDealPage, /dealId=\{deal\.id\}/);
  assert.match(dealsWorkspace, /Disposition has its own full-width outreach desk/);
  assert.match(dispositionWorkspace, /<DispositionPackageReadiness/);
  assert.match(dispositionWorkspace, /activeTab === "package"/);
  assert.doesNotMatch(dispositionWorkspace, /\/package\/approve/);
  assert.doesNotMatch(dispositionWorkspace, /\/package\.pdf/);
});

test("package reads and mutations use the immutable version contract", () => {
  assert.match(packageWorkspace, /\/api\/v1\/dispositions\/cases\/\$\{caseId\}\/package`/);
  assert.match(packageWorkspace, /cache: "no-store"/);
  assert.match(packageWorkspace, /expected_latest_version: data\.latest_version\?\.version_number \?\? 0/);
  assert.match(packageWorkspace, /\/package\/versions`/);
  assert.match(packageWorkspace, /\/package\/versions\/\$\{latestVersion\.id\}\/approval/);
  assert.match(packageWorkspace, /expected_version: latestVersion\.lock_version/);
  assert.match(packageWorkspace, /attestation: true/);
  assert.match(packageWorkspace, /\/package\/versions\/\$\{approvedVersion\.id\}\/package\.pdf/);
  assert.match(dispositionWorkspace, /Content-Disposition/);
  assert.match(packageWorkspace, /loadSequenceRef/);
});

test("externally prepared packet PDFs remain exact governed package versions", () => {
  assert.match(api, /artifact_source: "stonegate_generated" \| "external_upload"/);
  assert.match(packageWorkspace, /uploadExternalPackage/);
  assert.match(packageWorkspace, /package\/versions\/external/);
  assert.match(packageWorkspace, /"Content-Type": "application\/pdf"/);
  assert.match(packageWorkspace, /Use existing PDF/);
  assert.match(packageWorkspace, /exact externally prepared PDF that was uploaded/);
  assert.match(packageWorkspace, /version\.artifact_source === "external_upload"/);
  assert.match(api, /malware_scan_status: string/);
  assert.match(packageWorkspace, /acceptableArtifactScanStatuses/);
  assert.match(packageWorkspace, /externalArtifactScanIssue/);
  assert.match(packageWorkspace, /latestArtifactScanIssue/);
  assert.match(packageWorkspace, /PDF scan:/);
  assert.doesNotMatch(packageWorkspace, /hasApprovalBlockers/);
  assert.match(packageWorkspace, /shoppingArtifactIssue/);
  assert.match(packageWorkspace, /shoppingArtifactAvailable/);
});

test("Land cases use exact external packets and share the buyer marketing tools", () => {
  assert.match(api, /asset_class: "house" \| "land"/);
  assert.match(dispositionWorkspace, /selected\.asset_class === "land"/);
  assert.match(dispositionWorkspace, /landUnavailableTabs/);
  assert.match(dispositionWorkspace, /\["offers", "provider", "reconciliation"\]/);
  assert.doesNotMatch(dispositionWorkspace, /landUnavailableTabs = new Set<Tab>\(\[[^\]]*"execution"/);
  assert.doesNotMatch(dispositionWorkspace, /landUnavailableTabs = new Set<Tab>\(\[[^\]]*"outreach"/);
  assert.match(dispositionWorkspace, /Land marketing is active/);
  assert.match(dispositionWorkspace, /one-to-one dialer/);
  assert.match(dispositionWorkspace, /supervised bulk outreach/);
  assert.match(dispositionWorkspace, /assetClass=\{selected\.asset_class\}/);
  assert.match(packageWorkspace, /assetClass === "land"/);
  assert.match(packageWorkspace, /Upload the completed Land investor packet/);
  assert.match(packageWorkspace, /Find buyers, the one-to-one dialer, and supervised bulk outreach remain available independently of package approval/);
  assert.doesNotMatch(packageWorkspace, /Approve the exact uploaded Land packet, then use the Buyer pool/);
});

test("share-link history describes any source drift without inventing a newer package", () => {
  assert.match(packageWorkspace, /link\.is_preliminary === true \|\| link\.is_current_now === false/);
  assert.match(packageWorkspace, /shareLinkIsPreliminary\(issued\)/);
  assert.match(packageWorkspace, /shareLinkIsPreliminary\(issuedLink\)/);
  assert.match(packageWorkspace, /shareLinkIsPreliminary\(link\)/);
  assert.match(packageWorkspace, /package or source facts changed since issue/);
  assert.doesNotMatch(packageWorkspace, /newer package available/);
});

test("package starts with equal Stonegate-build and exact-PDF choices", () => {
  assert.match(packageWorkspace, /Choose your packet path/);
  assert.match(packageWorkspace, /Build with Stonegate/);
  assert.match(packageWorkspace, /Use existing PDF/);
  assert.match(packageWorkspace, /href="#build-with-stonegate"/);
  assert.match(packageWorkspace, /href="#use-existing-pdf"/);
  assert.match(packageWorkspace, /id="build-with-stonegate"/);
  assert.match(packageWorkspace, /id="use-existing-pdf"/);
  assert.match(packageWorkspace, /preserves that exact file/);
  assert.match(packageWorkspace, /CRM[\s\S]*readiness[\s\S]*buyer matching[\s\S]*private economics[\s\S]*outreach-summary controls/);
  assert.match(packageStyles, /\.packagePathChooser/);
});

test("readiness, evidence provenance, and deterministic summaries are visible", () => {
  assert.match(api, /export type DispositionPackageReadinessCheck/);
  assert.match(api, /can_view_internal_economics: boolean/);
  assert.match(api, /can_approve: boolean/);
  assert.match(packageWorkspace, /Launch readiness/);
  assert.match(packageWorkspace, /Classified evidence/);
  assert.match(packageWorkspace, /classificationLabels/);
  assert.match(packageWorkspace, /sourceLabel\(item\)/);
  assert.match(packageWorkspace, /Deterministic buyer summaries/);
  assert.match(packageWorkspace, /data\.email_summary/);
  assert.match(packageWorkspace, /data\.sms_summary/);
  assert.match(packageWorkspace, /Version history/);
});

test("private economics stay visibly and structurally separated", () => {
  assert.match(api, /contract_purchase_price_cents\?: number \| null/);
  assert.match(api, /buyer_asking_price_cents\?: number \| null/);
  assert.match(packageWorkspace, /data\.can_view_internal_economics && data\.private_economics/);
  assert.match(packageWorkspace, /data\.private_economics\.buyer_asking_price_cents/);
  assert.match(packageWorkspace, /Internal only/);
  assert.match(packageWorkspace, /Economics never shared/);
  assert.match(packageWorkspace, /excluded from every investor preview, PDF, email, and SMS/);
  assert.doesNotMatch(packageWorkspace, /preview\.minimum_acceptable/);
  assert.match(setup, /desired_assignment_fee_cents/);
  assert.match(setup, /Internal target only/);
  assert.match(api, /can_view_private_economics: boolean/);
  assert.match(setupPage, /canViewPrivateEconomics=\{dispositionResult\.dispositions\.can_view_private_economics\}/);
  assert.doesNotMatch(setup, /if \(!canViewPrivateEconomics\)/);
  assert.match(setup, /canViewPrivateEconomics \? \{/);
  assert.match(setup, /Private economics stay hidden for your role/);
  assert.match(setup, /contract-derived starting point/);
  assert.doesNotMatch(setup, /name="asking_price"[^>]*required/);
  assert.doesNotMatch(setup, /name="minimum_price"[^>]*required/);
});

test("approval is version-governed while shopping and preparation remain advisory", () => {
  assert.match(packageWorkspace, /<dialog aria-labelledby="approve-package-title"/);
  assert.match(packageWorkspace, /onCancel=/);
  assert.match(packageWorkspace, /approvalReasonRef\.current\?\.focus/);
  assert.match(packageWorkspace, /checklistRef\.current\?\.focus/);
  assert.match(packageWorkspace, /data\.can_approve/);
  assert.doesNotMatch(packageWorkspace, /!latestVersion\?\.is_current/);
  assert.doesNotMatch(packageWorkspace, /readiness\?\.status === "stale"/);
  assert.match(packageWorkspace, /shoppingVersion = currentApprovedVersion \? approvedVersion : latestVersion/);
  assert.match(packageWorkspace, /Preliminary - checklist incomplete/);
  assert.doesNotMatch(packageWorkspace, /disabled=\{!currentApprovedVersion\}/);
  assert.doesNotMatch(packageWorkspace, /Approve simulated release/);
  assert.match(packageWorkspace, /currentApprovedVersion/);
  assert.match(packageWorkspace, /version\.pdf_file_name \|\| version\.pdf_sha256/);
  assert.match(packageWorkspace, /version\.status === "approved" \|\| canEditDeals \|\| data\.can_approve/);
  assert.match(packageWorkspace, /Draft PDF restricted/);
  assert.match(packageWorkspace, /Find and rank investors in/);
  assert.match(packageWorkspace, /Prepare exact bulk recipients in/);
  assert.doesNotMatch(packageWorkspace, /\/matches`/);
  assert.doesNotMatch(packageWorkspace, /\/campaigns\/release`/);
  assert.match(buyerPool, /Refresh buyer ranking/);
  assert.match(buyerPool, /method: "POST"/);
  assert.match(buyerPool, /\/api\/v1\/dispositions\/cases\/\$\{caseId\}\/matches/);
  assert.match(buyerPool, /Promise\.all\(\[loadPool\(1\), onLegacyReload\(\)\]\)/);
  assert.match(outreach, /Prepare recipient pool/);
  assert.match(outreach, /\/api\/v1\/dispositions\/cases\/\$\{caseId\}\/campaigns\/release/);
  assert.match(outreach, /No buyer messages were sent/);
  assert.match(packageWorkspace, /Review or approve it when useful; shopping and outreach may continue with its Preliminary label/);
  assert.match(packageStyles, /min-height: 44px/);
  assert.match(packageStyles, /@media \(max-width: 520px\)/);
  assert.match(packageStyles, /@container disposition-detail \(max-width: 900px\)/);
  assert.match(packageStyles, /@container disposition-detail \(max-width: 700px\)/);
  assert.match(packageStyles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("DS5 disposition surfaces contain no mojibake separators", () => {
  for (const source of [dealsWorkspace, dispositionWorkspace, packageWorkspace, setup]) {
    assert.doesNotMatch(source, /[\u00b7\u00c2\u00c3\ufffd]/);
  }
});
