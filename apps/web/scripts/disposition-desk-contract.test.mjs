import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const page = readFileSync(resolve(appRoot, "os/deals/page.tsx"), "utf8");
const dealsWorkspace = readFileSync(resolve(appRoot, "os/deals/deals-workspace.tsx"), "utf8");
const dealsLoading = readFileSync(resolve(appRoot, "os/deals/loading.tsx"), "utf8");
const dealsStyles = readFileSync(resolve(appRoot, "os/deals/deals.module.css"), "utf8");
const desk = readFileSync(resolve(appRoot, "os/deals/disposition-desk-workspace.tsx"), "utf8");
const deskStyles = readFileSync(resolve(appRoot, "os/deals/disposition-desk.module.css"), "utf8");
const buyersPage = readFileSync(resolve(appRoot, "os/buyers/page.tsx"), "utf8");
const buyersWorkspace = readFileSync(resolve(appRoot, "os/buyers/buyers-workspace.tsx"), "utf8");
const dispositionWorkspace = readFileSync(resolve(appRoot, "os/dispositions/disposition-workspace.tsx"), "utf8");
const buyerPool = readFileSync(resolve(appRoot, "os/dispositions/disposition-buyer-pool.tsx"), "utf8");
const navigation = readFileSync(resolve(appRoot, "os/os-navigation.tsx"), "utf8");
const iaContract = readFileSync(resolve(process.cwd(), "scripts/os-ia-contract.mjs"), "utf8");

test("the canonical disposition desk is URL-backed and server-loaded", () => {
  assert.match(api, /export type DispositionDeskScope = "mine" \| "team"/);
  assert.match(api, /export async function getDispositionDesk/);
  assert.match(api, /new URLSearchParams\(\{ scope \}\)/);
  assert.match(api, /if \(section\) query\.set\("section", section\)/);
  assert.match(api, /if \(section && offset > 0\) query\.set\("offset", String\(offset\)\)/);
  assert.match(api, /\/api\/v1\/dispositions\/desk\?\$\{query\.toString\(\)\}/);
  assert.match(api, /cache: "no-store"/);
  assert.match(api, /sections: Record<DispositionDeskSectionKey, DispositionDeskSectionState>/);
  assert.match(api, /transaction_id\?: string \| null/);
  assert.match(api, /needs_setup\?: boolean/);
  assert.match(api, /checklist\?: DispositionDeskChecklist \| null/);
  assert.match(api, /best_action_href\?: string \| null/);

  for (const queryKey of ["desk", "deskPage", "scope", "dispositionTab", "view"]) {
    assert.match(page, new RegExp(`${queryKey}\\?: string`));
  }
  assert.match(page, /params\.view === "disposition"/);
  assert.match(iaContract, /\{ name: "deskPage", status: "consumed" \}/);
  assert.match(page, /getDispositionDesk\(\s*dispositionScope,\s*selectedDesk,/);
  assert.match(page, /<DispositionDeskWorkspace/);
  const dispositionBranch = page.slice(
    page.indexOf('if (params.view === "disposition")'),
    page.indexOf("const transactionTabs"),
  );
  assert.match(dispositionBranch, /await getDispositionDesk\(\s*dispositionScope,\s*selectedDesk,/);
  assert.doesNotMatch(dispositionBranch, /getDealOverview|getTransactionOverview|getDispositionOverview|getWorkspaceProfile/);
  assert.doesNotMatch(dealsWorkspace, /DispositionDeskWorkspace/);
});

test("normal Deals keeps access health explicit and uses the full disposition permission pair", () => {
  assert.match(
    page,
    /profile\?\.permissions\.includes\("deals:view"\) &&\s*profile\.permissions\.includes\("buyers:view"\)/,
  );
  assert.match(page, /Access profile unavailable/);
  assert.match(page, /Workspace access could not be verified/);
  assert.match(page, /className=\{styles\.profileWarning\} role="alert"/);
  assert.match(page, /canViewDisposition=\{canViewDisposition\}/);
});

test("Deals provides an accessible route-level loading state", () => {
  assert.match(dealsLoading, /aria-busy="true"/);
  assert.match(dealsLoading, /aria-live="polite"/);
  assert.match(dealsLoading, /role="status"/);
  assert.match(dealsLoading, /Loading deals and disposition work queues/);
  assert.match(dealsStyles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("the desk exposes six operational queues with truthful scoped work context", () => {
  for (const label of ["Today", "Active Deals", "Buyer Follow-ups", "Replies", "Offers", "Deadlines"]) {
    assert.match(desk, new RegExp(`label: "${label}"`));
  }
  assert.match(desk, /new URLSearchParams\(\{ desk: view, scope, view: "disposition" \}\)/);
  assert.match(desk, /data\.can_view_team/);
  assert.match(desk, />Owner</);
  assert.match(desk, />Due</);
  assert.match(desk, />Reason</);
  assert.match(desk, />Checklist</);
  assert.match(desk, /item\.primary_action\.href/);
  assert.match(desk, /item\.secondary_action/);
  assert.match(desk, /item\.needs_setup \? "Needs setup"/);
  assert.match(desk, /executed transaction is safely recorded and visible here/);
  assert.match(desk, /item when practical; it is advisory guidance, not a required first step/);
  assert.match(desk, /data\.buyer_network\.missing_proof/);
  assert.match(desk, /data\.coverage_warnings/);
  assert.match(desk, /caseWorkbench\?\.best_action_href \?\? item\.primary_action\.href/);
  assert.match(desk, /Suggested action \(optional\)/);
  assert.match(desk, /<details className=\{styles\.cardChecklist\}>/);
  assert.match(desk, /All checklist issues/);
  assert.match(desk, /Also available now/);
  assert.match(desk, /className=\{styles\.directActions\}/);
  for (const label of ["Packet", "Find buyers", "Dial buyers", "Offers"]) {
    assert.match(desk, new RegExp(`label: "${label}"`));
  }
  assert.match(desk, /dealWorkbenchHref\(item\.disposition_case_id, "execution"\)/);
  assert.match(desk, /\/os\/dispositions\/\$\{encodeURIComponent\(caseId\)\}/);
  assert.match(desk, /Work this deal/);
});

test("stale, unavailable, and truncated data remain explicit without disabling canonical work", () => {
  assert.match(api, /"configured_unverified"/);
  assert.match(api, /Date\.now\(\) - generatedAt\.getTime\(\) > 5 \* 60 \* 1000/);
  assert.match(desk, /isStale: boolean/);
  assert.match(desk, /This desk snapshot is more than five minutes old/);
  assert.match(desk, /data\.source_health\.external_provider_status/);
  assert.match(desk, /Stonegate records/);
  assert.match(desk, /External discovery/);
  assert.match(desk, /sectionState\.has_more/);
  assert.match(desk, /sectionState\.offset > 0 \|\| sectionState\.has_more/);
  assert.match(desk, /sectionState\.offset \+ sectionState\.returned/);
  assert.match(desk, /setStalenessNow\(Date\.now\(\)\)/);
  assert.match(desk, />Previous</);
  assert.match(desk, />Next /);
  assert.match(desk, /role="alert"/);
  assert.match(desk, /Retry\s*<\/button>/);
  assert.match(desk, /if \(due < now\) return "Overdue"/);
  assert.doesNotMatch(desk, /className=\{styles\.healthBanner\} role="alert"/);
  assert.doesNotMatch(desk, /<main className=\{styles\.workstream\}>/);
});

test("desk actions preserve deal subsection context and can open buyer creation safely", () => {
  assert.match(dealsWorkspace, /type DispositionTab = "package" \| "buyers" \| "execution" \| "outreach" \| "offers" \| "provider" \| "reconciliation"/);
  assert.match(dealsWorkspace, /Disposition workspace/);
  assert.match(dealsWorkspace, /\/os\/dispositions\/\$\{selected\.disposition_case_id\}/);
  assert.match(desk, /\/os\/buyers\?create=1&returnTo=/);
  assert.match(buyersPage, /firstValue\(rawParams\?\.create\) === "1"/);
  assert.match(buyersPage, /requestedReturnTo\?\.startsWith\("\/os\/"\)/);
  assert.match(buyersWorkspace, /useState\(Boolean\(initialCreate && canEdit\)\)/);
  assert.match(buyersWorkspace, /router\.push\(returnTo \?\?/);
});

test("buyer follow-ups can be scheduled from the existing disposition record", () => {
  assert.match(dispositionWorkspace, /name="scheduled_at" type="datetime-local"/);
  assert.match(dispositionWorkspace, /engagementType === "follow_up"/);
  assert.match(dispositionWorkspace, /scheduled_at: scheduledAt/);
  assert.match(dispositionWorkspace, /status: scheduledAt \? "scheduled" : "logged"/);
  assert.match(dispositionWorkspace, /item\.scheduled_at \? "Scheduled " \+/);
  assert.match(dispositionWorkspace, /Log inquiry, showing, or follow-up/);
});

test("the Find buyers workbench hosts one governed, explainable buyer pool", () => {
  assert.match(dispositionWorkspace, /tab === "buyers"\) return "Find buyers"/);
  assert.match(dispositionWorkspace, /<DispositionBuyerPool/);
  assert.match(buyerPool, /useState<DispositionBuyerPoolSource>/);
  assert.match(buyerPool, /useState<DispositionBuyerPoolStage>/);
  assert.match(buyerPool, /\/buyer-pool\?\$\{query\.toString\(\)\}/);
  assert.match(buyerPool, /"\/api\/v1\/buyers\/discovery-runs"/);
  assert.match(buyerPool, /\/buyer-pool\/runs/);
  assert.match(buyerPool, /\/buyer-pool\/candidates\/\$\{entry\.candidate_id\}/);
  assert.match(buyerPool, /\/buyer-pool\/candidates\/\$\{entry\.candidate_id\}\/conversion/);
  assert.match(buyerPool, /expected_version: entry\.lock_version/);
  assert.match(buyerPool, /Shortlisting never sends outreach/);
  assert.match(buyerPool, /Passing applies only to this deal/);
  assert.match(buyerPool, /Approve into network/);
  assert.match(buyerPool, /"Review reason"/);
  assert.match(
    buyerPool,
    /activeEditor\.action === "pass" \|\| activeEditor\.action === "shortlist" \|\| activeEditor\.action === "clear" \? !reason\.trim\(\) : reason\.trim\(\)\.length < 3/,
  );
  assert.match(buyerPool, /canEditDeals/);
  assert.match(buyerPool, /canEditBuyers/);
  assert.match(api, /export type DispositionBuyerPoolPage/);
  assert.match(api, /supporting_evidence: Record<string, unknown>\[\]/);
  assert.match(api, /conflicting_evidence: Record<string, unknown>\[\]/);
});

test("the disposition role default and responsive controls use the canonical desk", () => {
  assert.match(navigation, /return "\/os\/deals\?view=disposition"/);
  assert.match(navigation, /label: "Dispositions"/);
  assert.match(navigation, /allPermissions: \["deals:view", "buyers:view"\]/);
  assert.match(navigation, /activePaths: \["\/os\/dispositions"\]/);
  assert.equal((iaContract.match(/defaultRoute: "\/os\/deals\?view=disposition"/g) ?? []).length, 2);
  assert.match(iaContract, /targetCanonical: "\/os\/deals\?view=disposition"/);
  assert.match(deskStyles, /\.coverageList a \{ width: 44px; height: 44px/);
  assert.match(deskStyles, /min-height: 44px/);
  assert.match(deskStyles, /@media \(max-width: 700px\)/);
  assert.match(deskStyles, /@media \(max-width: 520px\)/);
});
