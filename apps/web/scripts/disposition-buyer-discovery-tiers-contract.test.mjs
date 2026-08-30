import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const buyerPool = readFileSync(
  resolve(appRoot, "os/dispositions/disposition-buyer-pool.tsx"),
  "utf8",
);

test("buyer discovery uses the three governed sequential tiers", () => {
  for (const tier of ["best_fit", "expanded", "regional"]) {
    assert.match(buyerPool, new RegExp(`value: "${tier}"`));
  }
  for (const candidateCount of [10, 20, 40]) {
    assert.match(buyerPool, new RegExp(`targetCandidates: ${candidateCount}`));
  }
  for (const creditCap of [30, 60, 120]) {
    assert.match(buyerPool, new RegExp(`creditCap: ${creditCap}`));
  }
  assert.match(buyerPool, /discoverySummary\?\.unlocked_tiers\.includes\(searchTier\)/);
  assert.match(buyerPool, /const unlocked = status\?\.unlocked \?\? false/);
  assert.match(buyerPool, /Complete or reuse Tier/);
});

test("the browser sends the selected tier and reloads authoritative progress", () => {
  assert.match(api, /export type BuyerDiscoverySearchTier = "best_fit" \| "expanded" \| "regional"/);
  assert.match(api, /export type BuyerDiscoverySummary/);
  assert.match(buyerPool, /\/api\/v1\/buyers\/discovery-summary\?case_id=/);
  assert.match(buyerPool, /search_tier: searchTier/);
  assert.match(buyerPool, /max_candidates: tier\.targetCandidates/);
  assert.match(buyerPool, /confirmed_estimated_credits: estimate\.estimated_credits/);
  assert.match(buyerPool, /confirmed_request_fingerprint: estimate\.request_fingerprint/);
  assert.match(buyerPool, /loadDiscoverySummary\(\)\.catch/);
  assert.match(buyerPool, /activeDiscoveryRequest !== null/);
  assert.match(buyerPool, /Credit reconciliation required/);
  assert.match(buyerPool, /latestRun\.status === "running"/);
  assert.match(buyerPool, /Actual credits pending reconciliation/);
});

test("cost and safety language remain explicit before provider spending", () => {
  assert.match(buyerPool, /0\.0075/);
  assert.match(buyerPool, /Preview search estimate/);
  assert.match(buyerPool, /preview costs \$0\.00/);
  assert.match(buyerPool, /additional net-new buyers/);
  assert.match(buyerPool, /Human review and approval required/);
  assert.match(buyerPool, /No automatic calls, texts, or emails/);
  assert.match(buyerPool, /Stonegate never contacts discovered buyers automatically/);
});
