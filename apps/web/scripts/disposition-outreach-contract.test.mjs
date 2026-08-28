import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const page = readFileSync(resolve(appRoot, "os/deals/page.tsx"), "utf8");
const deals = readFileSync(resolve(appRoot, "os/deals/deals-workspace.tsx"), "utf8");
const disposition = readFileSync(resolve(appRoot, "os/dispositions/disposition-workspace.tsx"), "utf8");
const outreach = readFileSync(resolve(appRoot, "os/dispositions/disposition-outreach-workspace.tsx"), "utf8");
const outreachStyles = readFileSync(resolve(appRoot, "os/dispositions/disposition-outreach-workspace.module.css"), "utf8");
const rbac = readFileSync(resolve(process.cwd(), "../api/app/domain/rbac.py"), "utf8");

test("DS6 outreach lives between the canonical buyer pool and offers tabs", () => {
  assert.match(deals, /"package" \| "buyers" \| "outreach" \| "offers" \| "reconciliation"/);
  assert.match(disposition, /\["package", "buyers", "outreach", "offers", "reconciliation"\]/);
  assert.match(disposition, /<DispositionOutreachWorkspace/);
  assert.match(disposition, /item === "buyers" \? "Buyer pool"/);
  assert.match(disposition, /item === "offers" \? "Offer Room"/);
  assert.match(disposition, /aria-label="Disposition deal sections"/);
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
});

test("live controls require scoped outreach and bulk communication permissions", () => {
  assert.match(page, /dispositions:manage_outreach/);
  assert.match(page, /dispositions:approve_outreach/);
  assert.match(page, /communications:send_bulk/);
  assert.match(outreach, /!canApprove \|\| !canSendBulk/);
  for (const label of [
    "Release approved outreach",
    "Pause unsent",
    "Resume approved outreach",
    "Cancel unsent",
    "Retry safe failures",
    "Refresh status",
  ]) assert.match(outreach, new RegExp(label));
  assert.match(outreach, /bulk-communications permission/);
});

test("buyer and outreach authority both gate the tab, forced URL, and workspace mount", () => {
  assert.match(page, /profile\?\.permissions\.includes\("buyers:view"\)/);
  assert.match(page, /canManageOutreach \|\| canApproveOutreach/);
  assert.match(page, /canViewOutreach=\{canViewOutreach\}/);
  assert.match(deals, /requestedDispositionTab === "outreach" && !canViewOutreach/);
  assert.match(disposition, /item !== "outreach" \|\| canViewOutreach/);
  assert.match(disposition, /tab === "outreach" && canViewOutreach/);
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
