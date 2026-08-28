import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const page = readFileSync(resolve(appRoot, "os/buyers/page.tsx"), "utf8");
const workspace = readFileSync(resolve(appRoot, "os/buyers/buyers-workspace.tsx"), "utf8");
const form = readFileSync(resolve(appRoot, "os/buyers/buyer-form.tsx"), "utf8");
const buyBoxForm = readFileSync(resolve(appRoot, "os/buyers/buyer-buy-box-form.tsx"), "utf8");
const styles = readFileSync(resolve(appRoot, "os/buyers/buyers.module.css"), "utf8");

test("buyer search, asset focus, and pagination stay server-backed", () => {
  assert.match(page, /getBuyers\(\{[\s\S]*assetClass:[\s\S]*ownerUserId:[\s\S]*page:[\s\S]*q:[\s\S]*sourceKey:[\s\S]*status:/);
  assert.match(api, /params\.set\("asset_class"/);
  assert.doesNotMatch(api, /params\.set\("asset_focus"/);
  assert.match(api, /params\.set\("owner_id"/);
  assert.match(api, /params\.set\("source_key"/);
  assert.match(workspace, /name="asset"/);
  assert.match(workspace, /aria-label="Buyer result pages"/);
  assert.match(workspace, /router\.replace\(locationFor\(/);
  assert.doesNotMatch(workspace, /window\.history\.replaceState/);
});

test("manual intake is review-first, duplicate-safe, and relationship-only", () => {
  assert.match(form, /value="needs_review"/);
  assert.match(form, /Enter at least one way to reach this buyer/);
  assert.match(form, /\/api\/v1\/buyers\/duplicates\/preflight/);
  assert.match(form, /Use existing buyer/);
  assert.match(form, /Reason for a separate record/);
  assert.match(form, /relationship_owner_user_id/);
  assert.match(form, /next_follow_up_at/);
  assert.match(form, /permission_evidence_source/);
  assert.doesNotMatch(form, /proof_of_funds_status/);
  assert.doesNotMatch(form, /max_purchase_price_cents/);
  assert.doesNotMatch(form, /name="asset_focus"/);
  assert.doesNotMatch(form, /\bcriteria:/);
});

test("House and Land buy boxes are distinct, typed, and version-safe", () => {
  assert.match(buyBoxForm, /asset === "house"/);
  assert.match(buyBoxForm, /asset_class: "house"/);
  assert.match(buyBoxForm, /asset_class: "land"/);
  assert.match(buyBoxForm, /property_types/);
  assert.match(buyBoxForm, /rehab_tolerance/);
  assert.match(buyBoxForm, /intended_uses/);
  assert.match(buyBoxForm, /flood_zone_tolerance/);
  assert.match(buyBoxForm, /expected_version: current\?\.current_version \?\? 0/);
  assert.match(buyBoxForm, /\/buy-boxes\/\$\{asset\}/);
  assert.match(buyBoxForm, /response\.status === 409/);
  assert.doesNotMatch(buyBoxForm, /preferred.margin/i);
  assert.match(buyBoxForm, /Automated Land deal matching begins in DS4/i);
});

test("buyer lifecycle controls remain explicit and audited by API", () => {
  assert.match(workspace, /canEdit && selected\.status !== "archived"/);
  assert.match(workspace, /\/archive`/);
  assert.match(workspace, /JSON\.stringify\(\{ reason: archiveReason\.trim\(\) \}\)/);
  assert.match(workspace, /\/restore`/);
  assert.match(form, /Mark this buyer Do not contact/);
  assert.match(workspace, /aria-label="Contact permission history"/);
  assert.match(workspace, /No permission history has been recorded for this buyer/);
  assert.match(api, /permission_history: BuyerPermissionHistoryEntry\[\]/);
});

test("operator states and mobile controls remain accessible", () => {
  assert.match(form, /aria-live="polite"/);
  assert.match(workspace, /role="alert"/);
  assert.match(workspace, /role="tablist"/);
  assert.match(workspace, /role="tabpanel"/);
  assert.match(workspace, /aria-selected=\{activeTab === tab\.key\}/);
  assert.match(workspace, /event\.key === "Escape"/);
  assert.match(styles, /min-height: 44px/);
  assert.match(styles, /@media \(max-width: 520px\)/);
});
