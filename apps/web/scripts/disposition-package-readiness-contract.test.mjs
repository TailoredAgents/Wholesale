import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const dealsWorkspace = readFileSync(resolve(appRoot, "os/deals/deals-workspace.tsx"), "utf8");
const dispositionWorkspace = readFileSync(resolve(appRoot, "os/dispositions/disposition-workspace.tsx"), "utf8");
const packageWorkspace = readFileSync(resolve(appRoot, "os/dispositions/disposition-package-readiness.tsx"), "utf8");
const packageStyles = readFileSync(resolve(appRoot, "os/dispositions/disposition-package-readiness.module.css"), "utf8");
const setup = readFileSync(resolve(appRoot, "os/dispositions/disposition-setup-workspace.tsx"), "utf8");
const setupPage = readFileSync(resolve(appRoot, "os/dispositions/page.tsx"), "utf8");

test("DS5 remains inside the canonical deal package tab", () => {
  assert.match(dealsWorkspace, /dealId=\{selected\.id\}/);
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
  assert.match(packageWorkspace, /hasApprovalBlockers/);
});

test("Land cases use exact external packets and hide residential-only disposition tools", () => {
  assert.match(api, /asset_class: "house" \| "land"/);
  assert.match(dispositionWorkspace, /selected\.asset_class === "land"/);
  assert.match(dispositionWorkspace, /houseOnlyTabs/);
  assert.match(dispositionWorkspace, /Land uses the same Package, Buyer pool, and closing record/);
  assert.match(dispositionWorkspace, /assetClass=\{selected\.asset_class\}/);
  assert.match(packageWorkspace, /assetClass === "land"/);
  assert.match(packageWorkspace, /Upload the completed Land investor packet/);
  assert.match(packageWorkspace, /use the Buyer pool tab for asset-aware matching/);
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
  assert.match(setup, /if \(!canViewPrivateEconomics\)/);
  assert.match(setup, /Private deal economics are restricted/);
});

test("approval and release controls are accessible and version-gated", () => {
  assert.match(packageWorkspace, /<dialog aria-labelledby="approve-package-title"/);
  assert.match(packageWorkspace, /onCancel=/);
  assert.match(packageWorkspace, /approvalReasonRef\.current\?\.focus/);
  assert.match(packageWorkspace, /checklistRef\.current\?\.focus/);
  assert.match(packageWorkspace, /data\.can_approve/);
  assert.match(packageWorkspace, /!latestVersion\?\.is_current/);
  assert.doesNotMatch(packageWorkspace, /readiness\?\.status === "stale"/);
  assert.match(packageWorkspace, /Draft - approval required/);
  assert.match(packageWorkspace, /disabled=\{!currentApprovedVersion\}/);
  assert.match(packageWorkspace, /Prepare recipient pool/);
  assert.doesNotMatch(packageWorkspace, /Approve simulated release/);
  assert.match(packageWorkspace, /currentApprovedVersion/);
  assert.match(packageWorkspace, /version\.pdf_file_name \|\| version\.pdf_sha256/);
  assert.match(packageWorkspace, /version\.status === "approved" \|\| canEditDeals \|\| data\.can_approve/);
  assert.match(packageWorkspace, /Draft PDF restricted/);
  assert.match(packageWorkspace, /Buyer ranking and recipient preparation require/);
  assert.match(packageWorkspace, /No buyer communication is sent/);
  assert.match(packageStyles, /min-height: 44px/);
  assert.match(packageStyles, /@media \(max-width: 520px\)/);
  assert.match(packageStyles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("DS5 disposition surfaces contain no mojibake separators", () => {
  for (const source of [dealsWorkspace, dispositionWorkspace, packageWorkspace, setup]) {
    assert.doesNotMatch(source, /[\u00b7\u00c2\u00c3\ufffd]/);
  }
});
