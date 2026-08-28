import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const page = readFileSync(resolve(appRoot, "os/buyers/page.tsx"), "utf8");
const workspace = readFileSync(resolve(appRoot, "os/buyers/buyers-workspace.tsx"), "utf8");

test("selected buyer profile loads separately from the paginated list", () => {
  assert.match(api, /getBuyerProfile\(buyerId: string\)/);
  assert.match(api, /\/api\/v1\/buyers\/\$\{encodeURIComponent\(buyerId\)\}\/profile/);
  assert.match(page, /getBuyerProfile\(selectedBuyerId\)/);
  assert.match(page, /selectedProfile=\{buyerProfile\}/);
});

test("proof files are separately permissioned and never auto-verified", () => {
  assert.match(page, /buyers:view_proof/);
  assert.match(page, /buyers:manage_proof/);
  assert.match(workspace, /\/api\/v1\/dispositions\/buyers\/\$\{selected\.id\}\/proof/);
  assert.match(workspace, /\/api\/v1\/dispositions\/proof-documents\/\$\{proofReviewId\}\/verification/);
  assert.match(workspace, /Upload for review/);
  assert.match(workspace, /Uploading a file never verifies it automatically/);
  assert.match(workspace, /status !== "verified"/);
  assert.match(workspace, /expiry > new Date\(\)/);
  assert.doesNotMatch(workspace, /status === "received" \|\| status === "verified"/);
});

test("relationship activity and profile review use governed endpoints", () => {
  assert.match(workspace, /\/relationship-activities`/);
  assert.match(workspace, /\/relationship-activities\/\$\{item\.id\}/);
  assert.match(workspace, /engagement_type: activityType/);
  assert.match(workspace, /\/verification`/);
  assert.match(workspace, /Permission-aware history/);
});

test("legacy criteria and immature reliability are represented truthfully", () => {
  assert.match(workspace, /Insufficient history/);
  assert.match(workspace, /Unverified legacy information/);
  assert.match(workspace, /It is not used for matching/);
  assert.match(api, /legacy_criteria:/);
  assert.match(api, /criteria_versions: BuyerBuyBoxVersion\[\]/);
});
