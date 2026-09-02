import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const page = readFileSync(resolve(appRoot, "os/dispositions/[caseId]/page.tsx"), "utf8");
const deals = readFileSync(resolve(appRoot, "os/deals/deals-workspace.tsx"), "utf8");
const disposition = readFileSync(resolve(appRoot, "os/dispositions/disposition-workspace.tsx"), "utf8");
const outreach = readFileSync(resolve(appRoot, "os/dispositions/disposition-outreach-workspace.tsx"), "utf8");
const outreachStyles = readFileSync(resolve(appRoot, "os/dispositions/disposition-outreach-workspace.module.css"), "utf8");
const rbac = readFileSync(resolve(process.cwd(), "../api/app/domain/rbac.py"), "utf8");

test("DS6 outreach lives between the canonical buyer pool and offers tabs", () => {
  assert.match(deals, /"package" \| "buyers" \| "execution" \| "outreach" \| "offers" \| "provider" \| "reconciliation"/);
  assert.match(disposition, /primaryWorkspaceTabs: Tab\[\] = \["package", "buyers", "execution", "outreach", "offers"\]/);
  assert.match(disposition, /workspaceTabs: Tab\[\] = \["overview", \.\.\.primaryWorkspaceTabs, "provider", "reconciliation"\]/);
  assert.match(disposition, /<DispositionOutreachWorkspace/);
  assert.match(disposition, /tab === "buyers"\) return "Find buyers"/);
  assert.match(disposition, /tab === "offers"\) return "Offers & closing"/);
  assert.match(disposition, />More<\/summary>/);
  assert.match(disposition, /External distribution/);
  assert.match(disposition, /Finance reconciliation/);
  assert.match(disposition, /aria-label="Disposition deal sections"/);
});

test("recipient preparation is available where bulk outreach work happens", () => {
  assert.match(outreach, /canEditDeals: boolean/);
  assert.match(outreach, /prepareRecipientPool/);
  assert.match(outreach, /\/api\/v1\/dispositions\/cases\/\$\{caseId\}\/campaigns\/release/);
  assert.match(outreach, /Prepare recipient pool/);
  assert.match(outreach, /No buyer messages were sent/);
  assert.match(disposition, /canEditDeals=\{canEditDeals\}/);
});

test("workspace enforces supervised preparation, exact approval, and a hard cap", () => {
  assert.match(api, /export type DispositionOutreachWorkspace/);
  assert.match(api, /hard_recipient_cap: number/);
  assert.match(outreach, /selectedDeliveryCount > 0/);
  assert.match(outreach, /selectedDeliveryCount <= cap/);
  assert.match(outreach, /Create immutable draft/);
  assert.match(outreach, /expected_approval_hash: latest\.approval_hash/);
  assert.match(outreach, /expected_lock_version: latest\.lock_version/);
  assert.match(outreach, /Approve exact revision/);
  assert.match(outreach, /I reviewed every recipient, destination, sender, rendered message/);
  assert.match(outreach, /Private seller economics are never available here/);
  assert.match(outreach, /workspace\.package_is_preliminary/);
  assert.match(outreach, /workspace\.package_status !== "approved"/);
  assert.match(outreach, /Checklist gaps do not stop drafting or shopping/);
  assert.match(outreach, /This revision permanently records Preliminary source provenance/);
  assert.match(outreach, /<dt>Package PDF<\/dt>/);
  assert.match(outreach, /property package/);
  assert.doesNotMatch(outreach, /approved package and reply|Approved PDF/);
});

test("exact preview and history separate frozen package provenance from current facts", () => {
  assert.match(api, /package_was_current_at_prepare\?: boolean/);
  assert.match(api, /package_is_current_now\?: boolean/);
  assert.match(outreach, /revision\.package_is_preliminary === true/);
  assert.match(outreach, /revision\.package_was_current_at_prepare === false/);
  assert.match(outreach, /revision\.package_is_current_now === false/);
  assert.match(outreach, /<dt>Frozen package status<\/dt>/);
  assert.match(outreach, /<dt>Revision label<\/dt><dd>\{revisionIsPreliminary\(latest\)/);
  assert.equal((outreach.match(/<dt>Revision label<\/dt>/g) ?? []).length, 1);
  assert.match(outreach, /<dt>At preparation<\/dt><dd>\{currentAtPrepareLabel\(latest\)/);
  assert.match(outreach, /<dt>Current now<\/dt><dd>\{currentNowLabel\(latest\)/);
  assert.match(outreach, /Frozen package \{labelize\(revision\.package_status \?\? "approved"\)\}/);
  assert.match(outreach, /\{currentAtPrepareLabel\(revision\)\} - \{currentNowLabel\(revision\)\}/);
  assert.match(outreach, /Package or source facts changed since preparation/);
});

test("recipient attachment history preserves the conservative Preliminary delivery label", () => {
  assert.match(api, /export type DispositionOutreachPackageAttachment/);
  assert.match(api, /recipient_label_policy: string/);
  assert.match(api, /package_attachment\?: DispositionOutreachPackageAttachment/);
  assert.match(api, /sender_snapshot: DispositionOutreachSenderSnapshot/);
  assert.match(outreach, /attachment\.recipient_label_policy === "conservative_preliminary_v1"/);
  assert.match(outreach, /attachment\.file_name\.toUpperCase\(\)\.startsWith\("PRELIMINARY-"\)/);
  assert.match(outreach, /attachment\.is_preliminary \|\| usesConservativeAttachmentLabel\(attachment\)/);
  assert.match(outreach, /<dt>Recipient attachment<\/dt>/);
  assert.match(outreach, /<dt>Attachment label<\/dt>/);
  assert.match(outreach, /Recipient policy: Conservative Preliminary/);
  assert.match(outreach, /even when its frozen source was approved and current at preparation/);
  assert.match(outreach, /Recipient attachment \{attachment\.file_name\} - \{usesConservativeAttachmentLabel\(attachment\) \? "Conservative Preliminary policy"/);
  assert.doesNotMatch(outreach, /Approved attachment/i);
});

test("live controls require scoped outreach and bulk communication permissions", () => {
  assert.match(page, /dispositions:manage_outreach/);
  assert.match(page, /dispositions:approve_outreach/);
  assert.match(page, /dispositions:send_bulk_outreach/);
  assert.match(page, /communications:send_bulk/);
  assert.match(page, /permissions\.includes\("dispositions:send_bulk_outreach"\)[\s\S]*\|\| profile\?\.permissions\.includes\("communications:send_bulk"\)/);
  assert.match(outreach, /!canApprove \|\| !canSendBulk/);
  for (const label of [
    "Release approved outreach",
    "Pause unsent",
    "Resume approved outreach",
    "Cancel unsent",
    "Retry safe failures",
    "Refresh status",
  ]) assert.match(outreach, new RegExp(label));
  assert.match(outreach, /Disposition bulk-release permission/);
});

test("buyer and outreach authority both gate the tab, forced URL, and workspace mount", () => {
  assert.match(page, /profile\?\.permissions\.includes\("buyers:view"\)/);
  assert.match(page, /canManageOutreach \|\| canApproveOutreach/);
  assert.match(page, /canViewOutreach=\{canViewOutreach\}/);
  assert.match(disposition, /initialTab === "outreach" && !canViewOutreach/);
  assert.match(disposition, /item !== "outreach" \|\| canViewOutreach/);
  assert.match(disposition, /activeTab === "outreach" && canViewOutreach/);
  assert.match(outreach, /captured_email/);
  assert.match(outreach, /captured_phone/);
  assert.match(outreach, /delivery\.provider/);
  assert.match(api, /provider_message_id: string \| null/);
});

test("acquisition and external deal-view roles cannot satisfy the frontend outreach gate", () => {
  const acquisitionKeys = rbac.match(/ACQUISITION_KEYS = \(([\s\S]*?)\n\)/)?.[1] ?? "";
  assert.doesNotMatch(acquisitionKeys, /VIEW_BUYERS/);
  assert.doesNotMatch(acquisitionKeys, /MANAGE_DISPOSITION_OUTREACH/);
  assert.doesNotMatch(acquisitionKeys, /APPROVE_DISPOSITION_OUTREACH/);
  assert.match(rbac, /"acquisition_rep",[\s\S]*?\*ACQUISITION_KEYS/);
  assert.match(
    rbac,
    /RoleDefinition\("read_only_partner", "Read-only partner", \(PermissionKeys\.VIEW_DEALS,\)\)/,
  );
  assert.match(
    rbac,
    /RoleDefinition\("restricted_vendor", "Restricted attorney\/vendor", \(PermissionKeys\.VIEW_DEALS,\)\)/,
  );
});

test("delivery monitoring links to the canonical Buyer Inbox when available", () => {
  assert.match(api, /conversation_id: string \| null/);
  assert.match(outreach, /\/os\/inbox\?conversation=/);
  assert.match(outreach, /\/os\/buyers\?buyer=/);
  assert.match(outreach, /Open Buyer Inbox/);
  assert.match(outreach, /delivery_counts/);
  assert.match(outreach, /Revision history/);
});

test("outreach remains responsive and accessible", () => {
  assert.match(outreach, /role="alert"/);
  assert.match(outreach, /aria-labelledby="exact-preview"/);
  assert.match(outreach, /aria-labelledby="delivery-monitor"/);
  assert.match(disposition, /aria-current=/);
  assert.match(outreachStyles, /min-height: 44px/);
  assert.match(outreachStyles, /@media \(max-width: 760px\)/);
  assert.match(outreachStyles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("DS6 disposition outreach sources contain no mojibake separators", () => {
  for (const source of [outreach, disposition, deals]) {
    assert.doesNotMatch(source, /[\u00b7\u00c2\u00c3\ufffd]/);
  }
});
