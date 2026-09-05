import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const runtime = readFileSync(
  resolve(webRoot, "src/app/os/_components/web-phone-runtime.ts"),
  "utf8",
);
const provider = readFileSync(
  resolve(webRoot, "src/app/os/_components/web-phone-provider.tsx"),
  "utf8",
);
const shell = readFileSync(resolve(webRoot, "src/app/os/os-shell.tsx"), "utf8");
const quickDial = readFileSync(
  resolve(webRoot, "src/app/os/_components/quick-dial-dialog.tsx"),
  "utf8",
);
const quickDialStyles = readFileSync(
  resolve(webRoot, "src/app/os/_components/quick-dial-dialog.module.css"),
  "utf8",
);
const inbox = readFileSync(
  resolve(webRoot, "src/app/os/inbox/inbox-workspace.tsx"),
  "utf8",
);
const inboxPage = readFileSync(resolve(webRoot, "src/app/os/inbox/page.tsx"), "utf8");
const leadCall = readFileSync(
  resolve(webRoot, "src/app/leads/[leadId]/lead-call-button.tsx"),
  "utf8",
);

test("the shared phone lazily initializes Twilio from an ephemeral session", () => {
  assert.match(runtime, /\(\) => import\("@twilio\/voice-sdk"\)/);
  assert.match(provider, /\/api\/v1\/voice\/session/);
  assert.match(provider, /getToken\(\{ skipCache: true \}\)/);
  assert.match(provider, /safeSession\(voiceSession\)/);
  assert.doesNotMatch(provider, /localStorage|sessionStorage/);
  assert.doesNotMatch(provider, /console\./);
});

test("incoming browser calls are explicitly enabled and remain a first-answer-wins option", () => {
  assert.match(runtime, /device\.on\("incoming"/);
  assert.match(runtime, /await device\.register\(\)/);
  assert.match(runtime, /await device\.unregister\(\)/);
  assert.match(runtime, /acceptIncomingCall\(\)/);
  assert.match(runtime, /declineIncomingCall\(\)/);
  assert.match(runtime, /call\.ignore\(\)/);
  assert.doesNotMatch(runtime, /call\.reject\(\)/);
  assert.match(provider, /Answer incoming call/);
  assert.match(provider, /Decline incoming call/);
  assert.match(quickDial, /Enable incoming/);
  assert.match(quickDial, /First answer wins/);
  assert.match(quickDial, /stonegate:incoming-phone-call/);
});

test("outbound call endings reconcile to the provider result", () => {
  assert.match(provider, /\/api\/v1\/voice\/call-intents\/\$\{encodeURIComponent\(callIntentId\)\}\/status/);
  assert.match(provider, /The recipient did not answer/);
  assert.match(provider, /The recipient's line was busy/);
  assert.match(provider, /Call completed/);
  assert.doesNotMatch(runtime, /Browser audio ended\./);
});

test("active calls surface and clear Twilio call-quality warnings", () => {
  assert.match(runtime, /call\.on\("warning"/);
  assert.match(runtime, /call\.on\("warning-cleared"/);
  assert.match(runtime, /Call quality is degraded/);
  assert.match(runtime, /Call quality restored/);
});

test("the provider offers one reusable intent-driven call surface", () => {
  assert.match(provider, /export function WebPhoneProvider/);
  assert.match(provider, /export function useWebPhone/);
  assert.match(provider, /startCall: \(target: WebPhoneCallTarget\)/);
  assert.match(runtime, /Only one browser call can be active at a time/);
  assert.match(runtime, /params: \{ CallIntentId: callIntentId \}/);
  assert.match(runtime, /navigator\.locks/);
  assert.match(runtime, /stonegate:browser-phone:active-call/);
  assert.match(runtime, /reserveCallOwnership\(\)/);
  assert.match(runtime, /releaseCallReservation\(\)/);
});

test("the persistent phone panel exposes safe active call controls", () => {
  assert.match(provider, /Stonegate browser phone/);
  assert.doesNotMatch(provider, /retryCall|Retry browser call/);
  assert.match(provider, /Mute browser call/);
  assert.match(provider, /End browser call/);
  assert.match(provider, /Open call keypad/);
  assert.match(provider, /sendDigits\(key\)/);
  assert.match(runtime, /\^\[0-9\*#\]\+\$/);
  assert.match(runtime, /Wait for browser audio to connect before using the keypad/);
  assert.match(runtime, /unsupported tone/);
  assert.match(runtime, /this\.call\.sendDigits\(digits\)/);
  assert.match(provider, /Browser audio connected/);
  assert.match(provider, /activeCall\?\.fromNumber \?\? session\?\.line\?\.phone_number/);
  assert.match(provider, /<span aria-live="polite">\{audioStateLabel\(status\)\}<\/span>/);
  assert.match(provider, /<span aria-live="off"> · \{elapsedLabel\(elapsedSeconds\)\}<\/span>/);
  assert.doesNotMatch(provider, /<small aria-live="polite">/);
});

test("the OS exposes governed Quick Dial without creating a seller lead", () => {
  assert.match(shell, /<WebPhoneProvider>/);
  assert.match(shell, /communications:place_calls/);
  assert.match(shell, /<QuickDialLauncher/);
  assert.match(shell, /buttonRef=\{quickDialLauncherRef\}/);
  assert.match(shell, /expanded=\{quickDialOpen\}/);
  assert.match(shell, /onOpen=\{openQuickDial\}/);
  assert.match(shell, /<QuickDialDialog/);
  assert.match(shell, /onSubmittingChange=\{setQuickDialSubmitting\}/);
  assert.match(shell, /phoneOccupied \|\| quickDialSubmitting/);
  assert.match(shell, /setQuickDialOpen\(false\);\s+setHelpOpen\(false\)/);
  assert.match(shell, /stonegate-active-phone/);
  assert.match(quickDial, /\/api\/v1\/voice\/quick-dial/);
  assert.match(quickDial, /company_name:/);
  assert.match(quickDial, /purpose,/);
  assert.match(quickDial, /callIntentId: payload\.intent\.id/);
  assert.match(quickDial, /fromNumber: payload\.intent\.from_number/);
  assert.match(quickDial, /business contact is created and the call is saved in Inbox/);
  assert.match(quickDial, /useRef<string \| null>\(null\)/);
  assert.match(quickDial, /new AbortController\(\)/);
  assert.match(quickDial, /signal: controller\.signal/);
  assert.match(quickDial, /requestControllerRef\.current\?\.abort\(\)/);
  assert.match(quickDial, /mountedRef\.current = false/);
  assert.match(quickDial, /webPhone\.prepareAndStartCall/);
  assert.match(quickDial, /<fieldset className=\{styles\.dialingFields\} disabled=\{submitting\}>/);
  assert.match(quickDial, /aria-label="Open Stonegate phone"/);
  assert.match(quickDial, /aria-haspopup="dialog"/);
  assert.match(quickDial, /aria-modal="false"/);
  assert.match(quickDial, /role="dialog"/);
  assert.doesNotMatch(quickDial, /element\.inert = true|document\.body\.style\.overflow/);
  assert.doesNotMatch(quickDial, /new WebPhoneRuntime|@twilio\/voice-sdk|\/api\/v1\/voice\/session/);
  assert.doesNotMatch(quickDial, /localStorage|sessionStorage/);
  assert.doesNotMatch(quickDial, /\/api\/v1\/leads/);
  assert.match(quickDialStyles, /min-height: 44px/);
  assert.match(quickDialStyles, /100dvh/);
  assert.match(quickDialStyles, /env\(safe-area-inset-bottom\)/);
});

test("seller and Inbox calls use browser audio first with an explicit cellphone fallback", () => {
  assert.match(inbox, /\/call-intents/);
  assert.match(inbox, /Call in browser/);
  assert.match(inbox, /Call through my cellphone/);
  assert.match(inbox, /fromNumber: intent\.from_number/);
  assert.match(inbox, /webPhone\.status\.callActive/);
  assert.match(inboxPage, /params\.conversation \?\? "no-conversation"/);
  assert.match(inboxPage, /params\.lead \?\? "no-lead"/);
  assert.match(inboxPage, /key=\{workspaceKey\}/);
  assert.match(leadCall, /\/call-intents/);
  assert.match(leadCall, /\/forwarded-calls/);
  assert.match(leadCall, /useWebPhone/);
  assert.match(leadCall, /fromNumber: intent\.from_number/);
  assert.match(leadCall, /disabled=\{starting \|\| webPhone\.busy \|\| webPhone\.status\.callActive\}/);
});
