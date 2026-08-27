import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const page = readFileSync(resolve(appRoot, "os/buyers/page.tsx"), "utf8");
const workspace = readFileSync(resolve(appRoot, "os/buyers/buyers-workspace.tsx"), "utf8");
const form = readFileSync(resolve(appRoot, "os/buyers/buyer-form.tsx"), "utf8");
const styles = readFileSync(resolve(appRoot, "os/buyers/buyers.module.css"), "utf8");

test("buyer search and pagination stay server-backed and truthful", () => {
  assert.match(page, /getBuyers\(\{[\s\S]*ownerUserId:[\s\S]*page:[\s\S]*q:[\s\S]*sourceKey:[\s\S]*status:/);
  assert.match(api, /params\.set\("owner_id"/);
  assert.match(api, /params\.set\("source_key"/);
  assert.match(api, /total: payload\.total/);
  assert.match(api, /hasMore: payload\.has_more/);
  assert.match(workspace, /role="search"/);
  assert.match(workspace, /aria-label="Buyer result pages"/);
  assert.match(workspace, /\{total\} matching buyer/);
  assert.doesNotMatch(workspace, /buyers\.filter\(\(buyer\) => \[buyer\.name/);
});

test("manual buyer intake is review-first, duplicate-safe, and contactable", () => {
  assert.match(form, /value="needs_review"/);
  assert.match(form, /Enter at least one way to reach this buyer/);
  assert.match(form, /\/api\/v1\/buyers\/duplicates\/preflight/);
  assert.match(form, /Use existing buyer/);
  assert.match(form, /Reason for a separate record/);
  assert.match(form, /allow_separate_record: allowSeparate/);
  assert.match(form, /separateReason\.trim\(\)\.length < 3/);
  assert.match(form, /Enter a phone number before recording call or text permission as granted/);
  assert.match(form, /Record permission not granted/);
  assert.match(form, /must be a non-negative dollar amount/);
  assert.match(form, /const invalidMoney = \[maxPurchasePrice, minPrice, maxPrice\]\.find/);
  assert.match(form, /if \(invalidMoney\?\.error\)/);
  assert.doesNotMatch(form, /Number\.isFinite\(amount\) && amount >= 0 \? Math\.round\(amount \* 100\) : null/);
  assert.match(form, /relationship_owner_user_id/);
  assert.match(form, /source_external_key/);
  assert.match(form, /permission_evidence_source/);
  assert.match(form, /<option value="verified">Verified<\/option>/);
  assert.match(workspace, /status === "received" \|\| status === "verified"/);
});

test("buyer lifecycle controls are explicit, permission-gated, and audited by API", () => {
  assert.match(workspace, /canEdit && selected\.status !== "archived"/);
  assert.match(workspace, /\/archive`/);
  assert.match(workspace, /JSON\.stringify\(\{ reason: archiveReason\.trim\(\) \}\)/);
  assert.match(workspace, /\/restore`/);
  assert.match(workspace, /Restore \$\{selected\.name\} for review\? Do-not-contact restrictions remain in place when applicable/);
  assert.match(form, /Mark this buyer Do not contact/);
  assert.match(workspace, /created_by_name/);
  assert.match(workspace, /phone_permission\.recorded_at/);
  assert.match(api, /permission_history: BuyerPermissionHistoryEntry\[\]/);
  assert.match(workspace, /aria-label="Contact permission history"/);
  assert.match(workspace, /No permission history has been recorded for this buyer/);
  assert.match(workspace, /entry\.normalized_address/);
  assert.match(workspace, /criteria\.version_number/);
});

test("operator errors, loading, and mobile controls remain accessible", () => {
  assert.match(form, /aria-live="polite"/);
  assert.match(form, /Stonegate could not save this buyer/);
  assert.match(workspace, /role="alert"/);
  assert.match(workspace, />Retry<\/button>/);
  assert.match(workspace, /disabled=\{navigating\}/);
  assert.match(styles, /min-height: 44px/);
  assert.match(styles, /@media \(max-width: 520px\)/);
  assert.match(styles, /\.formActions \{ flex-direction: column-reverse/);
});
