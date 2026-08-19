import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const page = readFileSync(resolve(webRoot, "src/app/os/prospecting/page.tsx"), "utf8");
const control = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-dialer-control.tsx"),
  "utf8",
);
const workspace = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-workspace.tsx"),
  "utf8",
);
const styles = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting.module.css"),
  "utf8",
);
const api = readFileSync(resolve(webRoot, "src/app/lib/api.ts"), "utf8");
const voiceLineSettings = readFileSync(
  resolve(
    webRoot,
    "src/app/os/settings/communications/voice-line-settings.tsx",
  ),
  "utf8",
);

test("dialer control is a manager-only prospecting view backed by the operations endpoint", () => {
  assert.match(page, /type ProspectingView = "campaigns" \| "dialer-control" \| "my-calls"/);
  assert.match(page, /canManage && view === "dialer-control"[\s\S]*getProspectingDialerOperations/);
  assert.match(page, /\{canManage \? \([\s\S]*href="\/os\/prospecting\?view=dialer-control"/);
  assert.match(api, /\/api\/v1\/prospecting\/dialer\/operations/);
  assert.match(control, /export function ProspectingDialerControl/);
});

test("activation switches are explicit, audited, and campaign scoped", () => {
  assert.match(control, /\/api\/v1\/prospecting\/dialer\/switches\/company/);
  assert.match(control, /\/api\/v1\/prospecting\/dialer\/switches\/campaigns\/\$\{campaign\.id\}/);
  assert.match(control, /\{ enabled, reason \}/);
  assert.match(control, /Reason for change/);
  assert.match(control, /Deployment \{data\.feature_enabled \? "enabled" : "disabled"\}/);
});

test("caller setup requires a dedicated line and preserves the one-line launch boundary", () => {
  assert.match(control, /Dedicated outbound line/);
  assert.match(control, /required=\{status === "active"\}/);
  assert.match(control, /default_line_count: 1/);
  assert.match(control, /max_line_count: 1/);
  assert.match(control, /recording_policy: "company_policy"/);
  assert.match(control, /daily_dial_limit/);
  assert.match(control, /daily_spend_limit_cents/);
  assert.match(control, /One live line · Company recording policy/);
});

test("manager stop and recovery commands are deliberate and idempotent", () => {
  assert.match(control, /"safe_drain" \| "cancel_unanswered"/);
  assert.match(control, /"reconcile" \| "release_orphan" \| "mark_failed"/);
  assert.match(control, /operations\/sessions\/\$\{session\.id\}\/stop/);
  assert.match(control, /operations\/sessions\/\$\{session\.id\}\/recover/);
  assert.match(control, /idempotency_key: operationKey\("manager-stop"/);
  assert.match(control, /idempotency_key: operationKey\("manager-recovery"/);
  assert.match(control, /window\.confirm/);
  assert.match(control, /Required recovery reason/);
});

test("calling hours and approved scripts can be bound as a campaign policy", () => {
  assert.match(control, /Create calling hours \+ script policy/);
  assert.match(control, /\/api\/v1\/campaign-management\/cohorts/);
  assert.match(control, /script_version_id: selectedScriptId/);
  assert.match(control, /call_window_start_hour: start/);
  assert.match(control, /call_window_end_hour: end/);
  assert.match(control, /timezone/);
  assert.match(control, /dialer_mode: "one_line_power"/);
  assert.match(control, /script\.status === "approved"/);
  assert.match(control, /list_type: "outbound prospecting"/);
  assert.match(control, /useState\(\(\) => localDateValue\(\)\)/);
  assert.doesNotMatch(control, /startsOn[\s\S]{0,80}toISOString/);
});

test("health polling is visibility aware and cleans up its listeners", () => {
  assert.match(control, /window\.setInterval\(\(\) => void refresh\(\), 15_000\)/);
  assert.match(control, /document\.visibilityState === "hidden"/);
  assert.match(control, /window\.clearInterval\(interval\)/);
  assert.match(control, /removeEventListener\("visibilitychange", onVisibilityChange\)/);
  assert.doesNotMatch(control, /localStorage|sessionStorage|console\./);
  assert.match(control, /refreshSequenceRef/);
  assert.match(control, /refreshControllerRef/);
  assert.match(control, /signal: controller\.signal/);
  assert.match(control, /controller\.abort\(\)/);
  assert.match(control, /Live dialer health is temporarily unavailable/);
});

test("callbacks poll independently and only open a prospect after an explicit click", () => {
  assert.match(api, /\/api\/v1\/prospecting\/dialer\/callbacks/);
  assert.match(workspace, /window\.setInterval\(\(\) => void refreshCallbacks\(\), 20_000\)/);
  assert.match(workspace, /onClick=\{\(\) => void openCallback\(callback\)\}/);
  assert.match(workspace, /"Opening\.\.\." : "Open prospect"/);
  assert.match(workspace, /callbacks\/\$\{callback\.id\}\/prospect/);
  assert.match(workspace, /Callback status is temporarily unavailable/);
  assert.match(workspace, /Finish the current call before opening another prospect/);
  assert.match(workspace, /callbackOpenSequenceRef/);
  assert.match(workspace, /callbackRefreshControllerRef/);
  assert.match(workspace, /dialerLease \|\| \(activeAttempt && entryAssignedToCurrentUser\)/);
  assert.match(workspace, /Boolean\(openingCallbackId\)/);
  assert.doesNotMatch(workspace, /useEffect\(\(\) => \{[^}]*openCallback/s);
  assert.doesNotMatch(workspace, /callback[\s\S]{0,120}\.focus\(/);
});

test("policy creation fails closed when authoritative cohort data is unavailable", () => {
  assert.match(page, /cohortsAvailable=\{campaignResult\.apiConnected && campaignManagement !== null\}/);
  assert.match(control, /disabled=\{busy \|\| !cohortsAvailable\}/);
  assert.match(control, /policy creation is paused to prevent duplicates/);
});

test("mobile controls remain touch sized and collapse to one column", () => {
  assert.match(styles, /@media \(max-width: 760px\)[\s\S]*\.dialerHealthGrid[\s\S]*grid-template-columns: 1fr/);
  assert.match(styles, /\.dialerPolicyGrid input,[\s\S]*min-height: 44px/);
  assert.match(styles, /\.dialerSessionActions button,[\s\S]*min-height: 44px/);
});

test("communications settings preserve an explicit prospecting outbound purpose", () => {
  assert.match(voiceLineSettings, /prospecting_outbound/);
  assert.match(voiceLineSettings, /purpose_key/);
  assert.match(voiceLineSettings, /Prospecting outbound/);
  assert.match(voiceLineSettings, /PURPOSES_BY_DEPARTMENT/);
  assert.match(voiceLineSettings, /VoiceLineRoutingFields/);
  assert.match(control, /aria-label=\{label\}/);
});
