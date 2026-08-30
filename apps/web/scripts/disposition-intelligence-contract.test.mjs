import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const page = readFileSync(resolve(appRoot, "os/deals/page.tsx"), "utf8");
const desk = readFileSync(resolve(appRoot, "os/deals/disposition-desk-workspace.tsx"), "utf8");
const workspace = readFileSync(
  resolve(appRoot, "os/deals/disposition-intelligence-workspace.tsx"),
  "utf8",
);
const styles = readFileSync(
  resolve(appRoot, "os/deals/disposition-intelligence.module.css"),
  "utf8",
);

test("DS10 is a URL-backed server report under the canonical disposition desk", () => {
  assert.match(page, /params\.desk === "performance"/);
  assert.match(page, /await getDispositionIntelligence\(intelligenceFilters\)/);
  assert.match(page, /<DispositionIntelligenceWorkspace/);
  assert.match(desk, /href="\/os\/deals\?view=disposition&desk=performance"/);
  assert.match(workspace, /aria-current="page"/);
  assert.match(workspace, /Disposition performance/);
  assert.doesNotMatch(workspace, /useEffect|useState|useRouter/);
});

test("all seven filter categories and the time range reach the backend contract", () => {
  for (const key of [
    "deal_id",
    "buyer_id",
    "agent_user_id",
    "source",
    "market",
    "asset_class",
    "start_at",
    "end_at",
  ]) {
    assert.match(api, new RegExp(`${key}\\?: string`));
    assert.match(page, new RegExp(`${key}\\?: string`));
    assert.match(workspace, new RegExp(`name=\\"${key}\\"|name=\\{\\"${key}\\"\\}`));
  }
  assert.match(api, /\/api\/v1\/dispositions\/intelligence/);
  assert.match(api, /cache: "no-store"/);
  assert.match(api, /dispositionIntelligenceTimestamp/);
  assert.match(api, /export type DispositionIntelligenceFilterOption = \{[\s\S]*value: string;[\s\S]*label: string;[\s\S]*count: number;/);
  assert.match(api, /activity: \{[\s\S]*cases: number;/);
  assert.match(api, /economics: \{[\s\S]*reconciled_completed_assignments: number;[\s\S]*detail: string;/);
  assert.match(api, /reliability_score_basis_points: number \| null/);
  assert.match(workspace, /Clear filters/);
  assert.match(workspace, /Apply filters/);
});

test("outcomes lead activity and private economics stay permission-gated", () => {
  const outcomes = workspace.indexOf("Outcome evidence");
  const activity = workspace.indexOf("Workflow activity");
  assert.ok(outcomes > -1 && activity > outcomes, "outcomes must appear before activity volume");
  assert.match(workspace, /private_economics_visible/);
  assert.match(workspace, /Revenue, spread, profit, and cost details are restricted/);
  assert.match(workspace, /Completed assignments/);
  assert.match(workspace, /Collected revenue/);
  assert.match(workspace, /Approved company profit/);
  assert.match(workspace, /Cost per completed assignment/);
  assert.match(workspace, /Activity explains throughput; it is not presented as business success by itself/);
});

test("unknown and partial evidence can never silently become zero", () => {
  assert.match(api, /"known"[\s\S]*"partial"[\s\S]*"unavailable"/);
  assert.match(workspace, /if \(state === "unavailable" \|\| value === null\) return "Unavailable"/);
  assert.match(workspace, /Some outcome evidence is incomplete/);
  assert.match(workspace, /missing evidence is never treated as zero/);
  assert.match(workspace, /No milestone evidence is available/);
  assert.match(workspace, /No source evidence is available/);
  assert.match(workspace, /No buyer outcome evidence is available/);
  assert.match(workspace, /No agent workflow evidence is available/);
  assert.doesNotMatch(workspace, /\|\|\s*0|\?\?\s*0/);
});

test("cycle, source, buyer, and agent evidence remain explainable", () => {
  for (const label of [
    "Where deals move or stall",
    "Which buyer channels produce outcomes",
    "Reliability backed by recorded outcomes",
    "Human work tied to disposition outcomes",
    "Definitions and provenance",
    "Canonical sources:",
  ]) assert.match(workspace, new RegExp(label));
  assert.match(workspace, /data\.milestones/);
  assert.match(workspace, /data\.rates/);
  assert.match(workspace, /data\.sources/);
  assert.match(workspace, /data\.buyers/);
  assert.match(workspace, /data\.agents/);
  assert.match(workspace, /data\.provenance/);
  assert.match(workspace, /reliability_score_basis_points/);
});

test("learning is descriptive and correction history remains auditable", () => {
  assert.match(workspace, /Human-led and AI-assisted counts are descriptive cohorts/);
  assert.match(workspace, /They do not prove that assistance caused an outcome/);
  assert.match(workspace, /Minimum comparison sample/);
  assert.match(workspace, /comparison_allowed/);
  for (const field of [
    "package_revisions",
    "match_overrides",
    "ai_corrections",
    "backup_buyer_saves",
  ]) assert.match(workspace, new RegExp(field));
  assert.match(workspace, /immutable revision, override, and outcome ledgers/);
  assert.doesNotMatch(workspace, /AI (?:caused|improved|increased|decreased)/i);
});

test("DS10 remains responsive, keyboard-readable, and free of local shadow state", () => {
  assert.match(workspace, /role="region"/);
  assert.match(workspace, /tabIndex=\{0\}/);
  assert.match(workspace, /scope="col"/);
  assert.match(workspace, /scope="row"/);
  assert.match(styles, /min-height: 44px/);
  assert.match(styles, /@media \(max-width: 700px\)/);
  assert.match(styles, /@media \(max-width: 520px\)/);
  assert.doesNotMatch(workspace, /localStorage|sessionStorage|console\./);
  assert.doesNotMatch(workspace, /[\u00b7\u00c2\u00c3\ufffd]/);
});
