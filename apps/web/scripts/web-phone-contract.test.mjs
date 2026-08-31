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

test("the provider offers one reusable intent-driven call surface", () => {
  assert.match(provider, /export function WebPhoneProvider/);
  assert.match(provider, /export function useWebPhone/);
  assert.match(provider, /startCall: \(target: WebPhoneCallTarget\)/);
  assert.match(runtime, /Only one browser call can be active at a time/);
  assert.match(runtime, /params: \{ CallIntentId: callIntentId \}/);
  assert.match(runtime, /navigator\.locks/);
  assert.match(runtime, /stonegate:browser-phone:active-call/);
});

test("the persistent phone panel exposes safe active call controls", () => {
  assert.match(provider, /Stonegate browser phone/);
  assert.doesNotMatch(provider, /retryCall|Retry browser call/);
  assert.match(provider, /Mute browser call/);
  assert.match(provider, /End browser call/);
  assert.match(provider, /Browser audio connected/);
  assert.match(provider, /activeCall\?\.fromNumber \?\? session\?\.line\?\.phone_number/);
  assert.match(provider, /<span aria-live="polite">\{audioStateLabel\(status\)\}<\/span>/);
  assert.match(provider, /<span aria-live="off"> · \{elapsedLabel\(elapsedSeconds\)\}<\/span>/);
  assert.doesNotMatch(provider, /<small aria-live="polite">/);
});

test("the OS exposes governed Quick Dial without creating a seller lead", () => {
  assert.match(shell, /<WebPhoneProvider>/);
  assert.match(shell, /communications:place_calls/);
  assert.match(shell, /<QuickDialDialog/);
  assert.match(quickDial, /\/api\/v1\/voice\/quick-dial/);
  assert.match(quickDial, /company_name:/);
  assert.match(quickDial, /purpose,/);
  assert.match(quickDial, /callIntentId: payload\.intent\.id/);
  assert.match(quickDial, /fromNumber: payload\.intent\.from_number/);
  assert.match(quickDial, /creates a company contact and saves the call in Inbox/);
  assert.match(quickDial, /useRef<string \| null>\(null\)/);
  assert.match(quickDial, /element\.inert = true/);
  assert.doesNotMatch(quickDial, /\/api\/v1\/leads/);
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
