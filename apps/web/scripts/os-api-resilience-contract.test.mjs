import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const apiPath = new URL("../src/app/lib/api.ts", import.meta.url);
const shellPath = new URL("../src/app/os/os-shell.tsx", import.meta.url);
const layoutPath = new URL("../src/app/os/layout.tsx", import.meta.url);
const recoveryPath = new URL(
  "../src/app/os/_components/workspace-recovery.tsx",
  import.meta.url,
);
const dispositionPagePath = new URL(
  "../src/app/os/dispositions/[caseId]/page.tsx",
  import.meta.url,
);
const dispositionDeskPagePath = new URL(
  "../src/app/os/deals/page.tsx",
  import.meta.url,
);
const executionPath = new URL(
  "../src/app/os/dispositions/disposition-execution-workspace.tsx",
  import.meta.url,
);

test("safe server reads retry temporary gateway failures without retrying mutations", async () => {
  const api = await readFile(apiPath, "utf8");
  const readHelper = api.match(
    /async function fetchServerApiRead[\s\S]*?(?=\nexport async function getWorkspaceProfileResult)/,
  )?.[0] ?? "";

  assert.match(api, /transientApiStatuses = new Set\(\[408, 425, 429, 502, 503, 504\]\)/);
  assert.match(readHelper, /cache: "no-store"/);
  assert.match(readHelper, /serverReadRetryDelays/);
  assert.match(readHelper, /attempt > 0 \? \{ signal: new AbortController\(\)\.signal \}/);
  assert.doesNotMatch(readHelper, /method:\s*"POST"|method:\s*"PATCH"|method:\s*"DELETE"/);
  assert.match(api, /getWorkspaceProfileResult/);
  assert.match(api, /connectionState: apiConnectionState\(error\)/);
  assert.match(api, /fetchServerApiRead\("\/api\/v1\/dispositions"\)/);
  assert.match(api, /fetchServerApiRead\(\s*`\/api\/v1\/dispositions\/desk/);
});

test("the OS preserves verified navigation and keeps retrying its current route", async () => {
  const [shell, layout, recovery] = await Promise.all([
    readFile(shellPath, "utf8"),
    readFile(layoutPath, "utf8"),
    readFile(recoveryPath, "utf8"),
  ]);

  assert.match(layout, /getWorkspaceProfileResult\(\)/);
  assert.match(layout, /initialConnectionState=\{profileResult\.connectionState\}/);
  assert.match(shell, /stonegate:last-verified-workspace-profile/);
  assert.match(shell, /window\.sessionStorage\.setItem/);
  assert.match(shell, /workspaceProfileCacheLifetime/);
  assert.match(shell, /Stonegate is reconnecting/);
  assert.match(shell, /Navigation is preserved and this page will retry automatically/);
  assert.match(recovery, /router\.refresh\(\)/);
  assert.match(recovery, /scheduleRetry\(\)/);
  assert.doesNotMatch(recovery, /router\.(?:push|replace)\(/);
});

test("temporary disposition failures never pretend that the deal disappeared", async () => {
  const [dealPage, deskPage] = await Promise.all([
    readFile(dispositionPagePath, "utf8"),
    readFile(dispositionDeskPagePath, "utf8"),
  ]);

  const connectionGuard = dealPage.indexOf("if (!dispositionResult.dispositionCase || !dispositionResult.apiConnected)");
  const missingDealGuard = dealPage.indexOf("if (!dispositionCase)");
  assert.ok(connectionGuard >= 0 && connectionGuard < missingDealGuard);
  assert.match(dealPage, /<WorkspaceRecovery/);
  assert.match(dealPage, /getWorkspaceProfileResult\(\)/);
  assert.match(dealPage, /getDispositionCase\(caseId\)/);
  assert.doesNotMatch(dealPage, /getDispositionOverview\(\)/);
  assert.match(deskPage, /<WorkspaceRecovery/);
  assert.match(deskPage, /dispositionDeskResult\.connectionState === "unavailable"/);
});

test("overlapping buyer timeline refreshes share one in-flight request", async () => {
  const execution = await readFile(executionPath, "utf8");

  assert.match(execution, /buyerTimelineRequestRef/);
  assert.match(execution, /if \(inFlight\?\.buyerId === buyerId\) return inFlight\.promise/);
  assert.match(execution, /buyerTimelineRequestRef\.current = \{ buyerId, promise, requestId \}/);
});
