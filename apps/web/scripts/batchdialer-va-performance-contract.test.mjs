import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const page = readFileSync(resolve(webRoot, "src/app/os/prospecting/page.tsx"), "utf8");
const component = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/batchdialer-va-performance.tsx"),
  "utf8",
);
const styles = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/batchdialer-va-performance.module.css"),
  "utf8",
);
const api = readFileSync(resolve(webRoot, "src/app/lib/api.ts"), "utf8");

test("manager analytics loads BatchDialer performance and identity mappings independently", () => {
  assert.match(page, /getBatchDialerVaPerformance\(\)/);
  assert.match(page, /getBatchDialerAgentMappings\(\)/);
  assert.match(page, /BatchDialerVaPerformanceSection/);
  assert.match(api, /\/api\/v1\/prospecting\/batchdialer\/va-performance/);
  assert.match(api, /\/api\/v1\/prospecting\/batchdialer\/agent-mappings/);
  assert.match(api, /cache: "no-store"/);
});

test("historical ranges disclose the rolling provider archive boundary", () => {
  assert.match(api, /earliest_archived_call_at/);
  assert.match(api, /archive_history_status/);
  assert.match(api, /provider_scan_window_days/);
  assert.match(component, /older dates may be incomplete rather than zero/i);
});

test("provider CDR freshness is visible without exposing provider error text", () => {
  assert.match(api, /provider_sync_status/);
  assert.match(api, /provider_sync_freshness/);
  assert.match(api, /provider_sync_last_success_at/);
  assert.match(api, /provider_sync_error_present/);
  assert.match(api, /provider_sync_poll_interval_seconds/);
  assert.match(component, /Provider CDR sync:/);
  assert.match(component, /Last successful completion:/);
  assert.match(component, /provider error is recorded; its text is restricted to service logs/i);
  assert.doesNotMatch(api, /provider_sync_last_error/);
});

test("Today, 7-day, 30-day, and agent filters preserve the provider timezone", () => {
  assert.match(component, /type RangeKey = "today" \| "7" \| "30"/);
  assert.match(component, /rangeDates\(nextRange, timeZone\)/);
  assert.match(component, /date_from: dates\.dateFrom/);
  assert.match(component, /date_to: dates\.dateTo/);
  assert.match(component, /All agents/);
  assert.match(component, /setSelectedAgentId/);
  assert.match(component, /row\.provider_agent_id === selectedAgentId/);
});

test("unavailable metrics remain unavailable and are never fabricated as zero", () => {
  assert.match(api, /calls: number \| null/);
  assert.match(api, /inferred_calling_minutes: number \| null/);
  assert.match(api, /qualification_false_positives: number \| null/);
  assert.match(api, /recorded_duration_coverage_basis_points: number \| null/);
  assert.match(api, /identified_contact_coverage_basis_points: number \| null/);
  assert.match(component, /value === null \? "Unavailable"/);
  assert.match(component, /bucket\.calls = \(bucket\.calls \?\? 0\) \+ row\.calls/);
  assert.doesNotMatch(component, /metrics\[[^\]]+\] \?\? 0/);
  assert.doesNotMatch(component, /displayedMetrics\.[a-z_]+ \|\| 0/);
});

test("the manager report covers activity, quality, disposition, appointments, and outcomes", () => {
  for (const label of [
    "Manager scorecard",
    "Candidate to verified",
    "Evidence accepted",
    "New verified handoffs",
    "False positives",
    "Set to entered to held",
    "Do not call",
    "Not interested",
    "Voicemail",
    "No answer",
    "Hourly activity",
    "Daily activity",
    "Campaign performance",
    "Signed contracts",
    "Closed transactions",
  ]) {
    assert.match(component, new RegExp(label));
  }
  assert.match(component, /Call-derived activity - Not a timeclock/);
  assert.match(component, /does not prove paid hours, continuous work, login time/);
});

test("mapping controls make attribution explicit and persist only on Save", () => {
  assert.match(component, /Connect BatchDialer agents to Stonegate users/);
  assert.match(component, /Unassigned/);
  assert.match(component, /Save mapping/);
  assert.match(component, /method: "PATCH"/);
  assert.match(component, /body: JSON\.stringify\(\{ user_id: selectedUserId \|\| null \}\)/);
  assert.match(component, /agent\.mapping_id === mapping\.id/);
  assert.match(component, /Mapping saved/);
});

test("AI coaching remains evidence-backed, draft-only manager guidance", () => {
  assert.match(api, /BatchDialerVaCoachReport/);
  assert.match(api, /draft_only: true/);
  assert.match(component, /\/api\/v1\/prospecting\/batchdialer\/va-coach\/latest/);
  assert.match(component, /\/api\/v1\/prospecting\/batchdialer\/va-coach/);
  assert.match(component, /provider_agent_id: selectedAgent\.provider_agent_id/);
  assert.match(component, /date_from: data\.date_from/);
  assert.match(component, /date_to: data\.date_to/);
  assert.match(component, /query\.set\("date_from", dateFrom\)/);
  assert.match(component, /query\.set\("date_to", dateTo\)/);
  assert.match(component, /loadLatestCoach\(selectedAgentId, data\?\.date_from, data\?\.date_to\)/);
  assert.match(component, /setCoachGenerating\(false\)/);
  assert.match(component, /response\.status === 404/);
  assert.match(component, /Draft only/);
  assert.match(component, /Strengths/);
  assert.match(component, /Concerns to review/);
  assert.match(component, /Next-shift actions/);
  assert.match(component, /Calls to review/);
  assert.match(component, /Caveats/);
  assert.match(component, /Confidence/);
  assert.match(component, /format="duration" label="Average recorded duration"/);
  assert.match(component, /Average duration excludes calls where the provider supplied no duration/);
  assert.match(component, /Contact ID coverage/);
  assert.match(component, /Handoffs with appointment/);
  assert.match(component, /data \? `\$\{data\.date_from\} - \$\{data\.date_to\}`/);
  assert.match(component, /never determines discipline, pay, employment status, or work hours/);
});

test("stale coaching is reconciled after refresh and never presented as current", () => {
  assert.match(api, /output: BatchDialerVaCoachOutput \| null/);
  assert.match(api, /is_stale: boolean/);
  assert.match(api, /refresh_required: boolean/);
  assert.match(api, /stale_reasons: Array<"evidence_changed" \| "generation_contract_changed">/);
  assert.match(api, /current_evidence_as_of: string/);
  assert.match(component, /loadLatestCoach\(\s*retainedAgentId,\s*performancePayload\.date_from,\s*performancePayload\.date_to/);
  assert.match(component, /coachReport\.is_stale \|\| coachReport\.refresh_required \|\| coachReport\.output === null/);
  assert.match(component, /coachReport && coachRefreshRequired/);
  assert.match(component, /Coaching refresh required/);
  assert.match(component, /is out of date and is not shown as current guidance/);
  assert.match(component, /Prepare current coaching draft/);
  assert.match(component, /coachReport && coachOutput/);
  assert.doesNotMatch(component, /coachReport\.output\.(summary|strengths|concerns|next_shift_actions|calls_to_review|comparison_caveats|confidence)/);
  assert.match(styles, /\.coachStaleNotice/);
});

test("refreshes are authenticated, abortable, bounded, and revoke stale snapshots", () => {
  assert.match(component, /useAuth/);
  assert.match(component, /getToken/);
  assert.match(component, /AbortController/);
  assert.match(component, /12_000/);
  assert.match(component, /signal: controller\.signal/);
  assert.match(component, /setData\(null\)/);
  assert.match(component, /setMappings\(null\)/);
  assert.match(component, /prior confirmed snapshot remains visible/);
  assert.doesNotMatch(component, /localStorage|sessionStorage|console\./);
});

test("tables and controls remain accessible and responsive", () => {
  assert.match(component, /aria-label="BatchDialer agent performance scorecard"/);
  assert.match(component, /aria-label="Calls by hour"/);
  assert.match(component, /scope="col"/);
  assert.match(component, /scope="row"/);
  assert.match(component, /tabIndex=\{0\}/);
  assert.match(component, /aria-pressed=\{range === option\}/);
  assert.match(styles, /\.tableWrap:focus-visible/);
  assert.match(styles, /min-height: 44px/);
  assert.match(styles, /@media \(max-width: 700px\)/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
});
