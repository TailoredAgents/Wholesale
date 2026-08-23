import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const page = readFileSync(resolve(webRoot, "src/app/os/prospecting/page.tsx"), "utf8");
const analytics = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-analytics.tsx"),
  "utf8",
);
const styles = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting.module.css"),
  "utf8",
);
const api = readFileSync(resolve(webRoot, "src/app/lib/api.ts"), "utf8");

test("analytics is a manager-only Prospecting view backed by the private endpoint", () => {
  assert.match(page, /requestedView === "analytics"/);
  assert.match(page, /canManage && view === "analytics"[\s\S]*getProspectingDialerAnalytics/);
  assert.match(page, /href="\/os\/prospecting\?view=analytics"/);
  assert.match(page, /view === "analytics" && canManage/);
  assert.match(page, /\{dialerAnalytics \? \(/);
  assert.match(api, /\/api\/v1\/prospecting\/dialer\/analytics/);
  assert.match(api, /cache: "no-store"/);
  assert.match(analytics, /export function ProspectingAnalytics/);
});

test("date and operating-dimension filters are sent using the D9 contract", () => {
  for (const key of [
    "date_from",
    "date_to",
    "cohort_id",
    "source",
    "campaign_id",
    "caller_user_id",
    "dial_mode",
  ]) {
    assert.match(analytics, new RegExp(`query\\.set\\(\\"${key}\\"|${key}:`));
  }
  assert.match(analytics, /Inclusive UTC dates/);
  assert.match(analytics, /Start date must be on or before end date/);
  assert.match(analytics, /All sources/);
  assert.match(analytics, /All callers/);
  assert.match(analytics, /All dial modes/);
});

test("nullable and partial metrics never become fake zeroes", () => {
  assert.match(api, /entered_leads: number/);
  assert.match(api, /attempts: number \| null/);
  assert.match(api, /contribution_profit_cents: number \| null/);
  assert.match(api, /number_reputation_score: number \| null/);
  assert.match(api, /"known" \| "partial" \| "unknown" \| "not_applicable"/);
  assert.match(analytics, /status === "not_applicable"[\s\S]*Not applicable/);
  assert.match(analytics, /status === "unknown"[\s\S]*Unavailable/);
  assert.match(analytics, /status === "partial"[\s\S]*Partial/);
  assert.match(analytics, /Partial evidence/);
  assert.match(analytics, /value === null[\s\S]*Unavailable/);
  assert.doesNotMatch(analytics, /value \?\? 0/);
  assert.doesNotMatch(analytics, /\|\| 0/);
});

test("management compares downstream outcomes across native, BatchDialer, and paid sources", () => {
  assert.match(analytics, /Native vs BatchDialer vs paid acquisition/);
  assert.match(analytics, /Native Stonegate/);
  assert.match(analytics, /BatchDialer/);
  assert.match(analytics, /Paid ads/);
  assert.doesNotMatch(analytics, /Paid ads \/ CRM/);
  assert.match(analytics, /Entered leads[\s\S]*Attempts/);
  assert.match(analytics, /metricKey="entered_leads"/);
  assert.match(analytics, /Accepted handoffs/);
  assert.match(analytics, /Contribution profit/);
  assert.match(analytics, /Cost \/ qualified/);
  assert.match(analytics, /Compare business outcomes, not raw dial volume/);
  assert.match(analytics, /Source rows can overlap/);
  assert.match(analytics, /do not add the rows together/);
  assert.match(analytics, /source scorecards/);
  assert.match(analytics, /Available in period/);
  assert.doesNotMatch(analytics, /measured scorecards/);
});

test("scorecards expose every required management breakdown", () => {
  assert.match(analytics, /data\.by_va/);
  assert.match(analytics, /data\.by_campaign/);
  assert.match(analytics, /data\.by_cohort/);
  assert.match(analytics, /data\.by_list/);
  assert.match(analytics, /data\.by_dial_mode/);
  assert.match(analytics, /Scorecard breakdown/);
  assert.match(analytics, /VA \/ caller/);
  assert.match(analytics, /Campaign/);
  assert.match(analytics, /Cohort/);
  assert.match(analytics, /Dial mode/);
});

test("financial, quality, coverage, and definition provenance remain explicit", () => {
  assert.match(analytics, /VA labor cost/);
  assert.match(analytics, /Provider cost/);
  assert.match(analytics, /List cost/);
  assert.match(analytics, /Other \/ marketing cost/);
  assert.match(analytics, /Profit \/ paid VA hour/);
  assert.match(analytics, /Seller complaints/);
  assert.match(analytics, /Silent \/ dead air/);
  assert.match(analytics, /Number reputation/);
  assert.match(analytics, /financials_visible === false/);
  assert.match(analytics, /Some comparisons are incomplete/);
  assert.match(analytics, /coverage\.warnings/);
  assert.match(analytics, /value < 7500/);
  assert.match(analytics, /Below the 75% evidence target/);
  assert.match(analytics, /How these metrics are calculated/);
  assert.match(analytics, /attribution_model_version/);
  assert.match(analytics, /profit_formula_version/);
  assert.match(analytics, /No additional unavailability rule/);
});

test("readiness is technical controlled-pilot readiness and never D10 production acceptance", () => {
  assert.match(analytics, /Controlled-pilot measurement/);
  assert.match(analytics, /Eligible for a controlled pilot only/);
  assert.match(analytics, /D10 operating acceptance is still required/);
  assert.match(analytics, /D10 acceptance required/);
  assert.match(analytics, /technical readiness only/);
  assert.match(analytics, /Do not treat the dialer as pilot ready/);
  assert.match(analytics, /data\.readiness\.status === "ready_for_controlled_pilot" \? styles\.statusGood/);
  assert.match(analytics, /data\.readiness\.status === "blocked" \? styles\.analyticsStatusBlocked : styles\.statusWarning/);
  assert.doesNotMatch(analytics, /controlled_pilot_ready \? styles\.statusGood/);
  assert.doesNotMatch(analytics, /production (?:is )?ready/i);
  assert.doesNotMatch(analytics, /approved for production/i);
});

test("refreshes are authenticated, bounded, abortable, and preserve the prior snapshot", () => {
  assert.match(analytics, /useAuth/);
  assert.match(analytics, /getToken/);
  assert.match(analytics, /requestSequenceRef/);
  assert.match(analytics, /requestControllerRef/);
  assert.match(analytics, /controller\.abort\(\)/);
  assert.match(analytics, /signal: controller\.signal/);
  assert.match(analytics, /12_000/);
  assert.match(analytics, /prior confirmed snapshot remains visible/);
  assert.match(analytics, /response\.status === 401 \|\| response\.status === 403/);
  assert.match(analytics, /setData\(null\)/);
  assert.match(analytics, /prior snapshot, including financial data, has been cleared/);
  assert.match(analytics, /No prior analytics or financial values are retained/);
  assert.match(analytics, /aria-busy=\{loading\}/);
  assert.doesNotMatch(analytics, /localStorage|sessionStorage|console\./);
});

test("tables, controls, and mobile layouts remain accessible", () => {
  assert.match(analytics, /aria-label="Prospecting scorecards"/);
  assert.match(analytics, /scope="col"/);
  assert.match(analytics, /scope="row"/);
  assert.match(analytics, /tabIndex=\{0\}/);
  assert.match(styles, /\.analyticsTableWrap:focus-visible/);
  assert.match(styles, /@media \(max-width: 760px\)[\s\S]*\.analyticsFilters[\s\S]*grid-template-columns: 1fr/);
  assert.match(styles, /\.analyticsFilters input,[\s\S]*min-height: 44px/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.analyticsSpinner/);
});
