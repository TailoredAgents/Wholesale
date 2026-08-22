import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const page = readFileSync(resolve(webRoot, "src/app/os/prospecting/page.tsx"), "utf8");
const policy = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-dialer-policy.ts"),
  "utf8",
);
const workspace = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-workspace.tsx"),
  "utf8",
);
const api = readFileSync(resolve(webRoot, "src/app/lib/api.ts"), "utf8");
const render = readFileSync(resolve(webRoot, "../../render.yaml"), "utf8");

async function importPolicyForBehavior() {
  const javascript = ts.transpileModule(policy, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`);
}

test("manual prospecting is granted only by an authoritative disabled context", async () => {
  const { isManualProspectingMode } = await importPolicyForBehavior();
  assert.equal(isManualProspectingMode({ feature_enabled: false }), true);
  assert.equal(isManualProspectingMode({ feature_enabled: true }), false);
  assert.equal(isManualProspectingMode(null), false);
});

test("the server page fails closed and hides native management views while dormant", () => {
  assert.match(api, /export async function getProspectingDialerContext/);
  assert.match(api, /\/api\/v1\/prospecting\/dialer\/context/);
  assert.match(page, /const nativeDialerEnabled = dialerContext\?\.feature_enabled === true/);
  assert.match(
    page,
    /nativeDialerEnabled &&\s*\(requestedView === "dialer-control" \|\| requestedView === "pilot"\)/,
  );
  assert.match(page, /\{nativeDialerEnabled \? \([\s\S]*view=dialer-control/);
  assert.match(page, /\{nativeDialerEnabled \? \([\s\S]*view=pilot/);
  assert.match(page, /view === "my-calls" && nativeDialerEnabled[\s\S]*getProspectingInboundCallbacks/);
});

test("dormant My Calls excludes the native softphone chunk and callback polling", () => {
  assert.match(workspace, /import type \{[\s\S]*\} from "\.\/prospecting-dialer"/);
  assert.match(
    workspace,
    /dynamic\([\s\S]*import\("\.\/prospecting-dialer"\)[\s\S]*ssr: false/,
  );
  assert.doesNotMatch(workspace, /import \{\s*ProspectingDialer,/);
  assert.match(workspace, /\{nativeDialerEnabled \? \(\s*<ProspectingDialer/);
  assert.match(workspace, /if \(!nativeDialerEnabled\) return;[\s\S]*setInterval\(\(\) => void refreshCallbacks/);
  assert.match(workspace, /\{nativeDialerEnabled \? \(\s*<section aria-labelledby="callback-heading"/);
});

test("manual attempt authority remains assignment-bound and unknown mode cannot start", () => {
  assert.match(workspace, /const manualAttemptAuthority = isManualProspectingMode\(dialerContext\)/);
  assert.match(
    workspace,
    /entryAssignedToCurrentUser &&\s*\(manualAttemptAuthority \|\|\s*\(nativeDialerEnabled/,
  );
  assert.match(workspace, /const attemptAuthorityKnown = dialerContext !== null/);
  assert.match(workspace, /Calling mode could not be confirmed\. Refresh before starting this prospect\./);
  assert.match(workspace, /manualAttemptAuthority \? \([\s\S]*>Start prospect<\/button>/);
});

test("both deployed services declare the native prospecting dialer dormant", () => {
  const matches = render.match(
    /key: PROSPECTING_NATIVE_DIALER_ENABLED\s+value: false/g,
  );
  assert.equal(matches?.length, 2);
});
