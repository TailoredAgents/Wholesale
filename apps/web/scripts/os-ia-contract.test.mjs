import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

import ts from "typescript";

import {
  canonicalHelpDocuments,
  controlReferenceSections,
  currentRouteInventory,
  evidenceContract,
  legacyNavigation,
  permissionInventory,
  roleInventory,
  targetDestinations,
  targetGroups,
  targetRoleExperiences,
  vocabulary,
} from "./os-ia-contract.mjs";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const repositoryRoot = resolve(webRoot, "../..");
const osSourceRoot = resolve(webRoot, "src/app/os");
const applicationSourceRoot = resolve(webRoot, "src");

function walk(directory, predicate = () => true) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return walk(path, predicate);
    return predicate(path) ? [path] : [];
  });
}

function sorted(values) {
  return [...values].sort((first, second) => first.localeCompare(second));
}

function unique(values) {
  return new Set(values).size === values.length;
}

function routeFromPage(path) {
  const route = relative(resolve(webRoot, "src/app"), path)
    .replaceAll("\\", "/")
    .replace(/\/page\.tsx$/, "");
  return `/${route}`;
}

function routeInventoryForPath(path) {
  const pathname = path.split(/[?#]/)[0];
  const exact = currentRouteInventory.find((route) => route.routePattern === pathname);
  if (exact) return exact;
  if (pathname.endsWith("/")) {
    const dynamicPrefix = currentRouteInventory.find(
      (route) => route.routePattern.includes("[") && route.routePattern.startsWith(pathname),
    );
    if (dynamicPrefix) return dynamicPrefix;
  }
  return currentRouteInventory.find((route) => {
    if (!route.routePattern.includes("[")) return false;
    const expression = route.routePattern
      .split("/")
      .map((segment) =>
        /^\[[^\]]+\]$/.test(segment)
          ? "[^/]+"
          : segment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
      )
      .join("/");
    return new RegExp(`^${expression}$`).test(pathname);
  });
}

function sourceRouteLiterals() {
  const sourceFiles = walk(applicationSourceRoot, (path) => /\.(ts|tsx)$/.test(path));
  const literals = [];
  const literalPattern = /(["'`])(\/os(?:[^"'`\s${}]*))\1?/g;
  for (const path of sourceFiles) {
    const source = readFileSync(path, "utf8");
    for (const match of source.matchAll(literalPattern)) {
      if (match[2] === "/os(.*)") continue;
      if (match[2].includes(":path*")) continue;
      literals.push({
        path: relative(webRoot, path).replaceAll("\\", "/"),
        value: match[2],
      });
    }
  }
  return literals;
}

function loadTypeScriptModule(path) {
  const commonJsModule = { exports: {} };
  const compiled = ts.transpileModule(readFileSync(path, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  });
  vm.runInNewContext(compiled.outputText, {
    exports: commonJsModule.exports,
    module: commonJsModule,
  });
  return commonJsModule.exports;
}

test("target navigation contains exactly 11 unique destinations in approved groups", () => {
  assert.equal(targetDestinations.length, 11);
  assert.ok(unique(targetDestinations.map((destination) => destination.id)));
  assert.ok(unique(targetDestinations.map((destination) => destination.canonicalRoute)));
  assert.deepEqual(
    targetGroups.map((group) => group.id),
    ["work", "operations", "business", "administration"],
  );
  const groupIds = new Set(targetGroups.map((group) => group.id));
  for (const destination of targetDestinations) {
    assert.ok(groupIds.has(destination.group), `${destination.id} has an unknown group`);
  }
});

test("target role visibility is complete, bounded, and least-privilege for service roles", () => {
  const destinationIds = new Set(targetDestinations.map((destination) => destination.id));
  assert.ok(unique(targetRoleExperiences.map((experience) => experience.role)));
  for (const experience of targetRoleExperiences) {
    assert.ok(experience.destinations.length <= 11, `${experience.role} exceeds the destination cap`);
    assert.ok(unique(experience.destinations), `${experience.role} has duplicate destinations`);
    for (const destination of experience.destinations) {
      assert.ok(destinationIds.has(destination), `${experience.role} references ${destination}`);
    }
  }
  for (const role of ["owner", "founder_operator", "ceo"]) {
    assert.deepEqual(
      targetRoleExperiences.find((experience) => experience.role === role)?.destinations,
      targetDestinations.map((destination) => destination.id),
    );
  }
  assert.deepEqual(
    targetRoleExperiences.find((experience) => experience.role === "prospecting_caller")
      ?.destinations,
    ["prospecting"],
  );
  assert.deepEqual(
    targetRoleExperiences.find((experience) => experience.role === "operations_assistant")
      ?.destinations,
    ["home", "inbox", "tasks", "calendar", "prospecting", "seller-leads", "deals", "buyers"],
  );
  assert.deepEqual(
    targetRoleExperiences.find((experience) => experience.role === "ai_service")?.destinations,
    [],
  );
});

test("every current App Router page is represented in the migration inventory", () => {
  const discoveredRoutes = walk(osSourceRoot, (path) =>
    path.replaceAll("\\", "/").endsWith("/page.tsx"),
  ).map(routeFromPage);
  assert.deepEqual(
    sorted(currentRouteInventory.map((route) => route.routePattern)),
    sorted(discoveredRoutes),
  );
  for (const route of currentRouteInventory) {
    assert.equal(
      relative(webRoot, resolve(webRoot, route.source)).replaceAll("\\", "/"),
      route.source,
    );
    assert.ok(statSync(resolve(webRoot, route.source)).isFile(), `${route.source} is missing`);
    if (route.migration !== "development-only") {
      assert.ok(route.targetWorkspace, `${route.routePattern} lacks a target workspace`);
      assert.ok(route.targetCanonical, `${route.routePattern} lacks a target destination`);
    }
  }
});

test("live primary navigation matches the approved 11-destination target", () => {
  const source = readFileSync(resolve(osSourceRoot, "os-navigation.tsx"), "utf8");
  const primarySource = source.slice(
    source.indexOf("export const osNavGroups"),
    source.indexOf("export function isOwnerProfile"),
  );
  const sourceItems = [...primarySource.matchAll(/href:\s*"([^"]+)"[\s\S]*?label:\s*"([^"]+)"/g)]
    .map((match) => `${match[1]}|${match[2]}`);
  const contractItems = targetDestinations.map(
    (item) => `${item.canonicalRoute}|${item.label}`,
  );
  assert.deepEqual(sorted(contractItems), sorted(sourceItems));
  for (const item of targetDestinations) {
    assert.ok(routeInventoryForPath(item.canonicalRoute), `${item.canonicalRoute} has no route owner`);
  }
});

test("legacy routes preserve record context without competing navigation", () => {
  const navigation = readFileSync(resolve(osSourceRoot, "os-navigation.tsx"), "utf8");
  const shell = readFileSync(resolve(osSourceRoot, "os-shell.tsx"), "utf8");
  const transactions = readFileSync(resolve(osSourceRoot, "transactions/page.tsx"), "utf8");
  const dispositions = readFileSync(resolve(osSourceRoot, "dispositions/page.tsx"), "utf8");
  const setup = readFileSync(
    resolve(osSourceRoot, "dispositions/disposition-setup-workspace.tsx"),
    "utf8",
  );
  const componentNames = walk(resolve(osSourceRoot, "_components")).map((path) =>
    path.split("/").at(-1),
  );

  assert.doesNotMatch(navigation, /compatibilityNavGroups|visibleCompatibilityGroups/);
  assert.doesNotMatch(shell, /toolsOpen|Open additional tools|>Tools</);
  assert.match(transactions, /item\.transaction_id === params\.transaction/);
  assert.match(transactions, /redirect\(`\/os\/deals\?/);
  assert.match(dispositions, /item\.disposition_case_id === params\.case/);
  assert.match(dispositions, /DispositionSetupWorkspace/);
  assert.match(setup, /router\.push\(/);
  assert.ok(componentNames.every((name) => !name?.includes("journey")));
});

test("all static OS links and their declared query keys have a route owner", () => {
  const unresolved = [];
  const unaccountedQueryKeys = [];
  for (const link of sourceRouteLiterals()) {
    const route = routeInventoryForPath(link.value);
    if (!route) {
      unresolved.push(link);
      continue;
    }
    const query = link.value.split("?")[1]?.split("#")[0];
    if (!query) continue;
    const declaredKeys = new Set(route.queryParameters.map((parameter) => parameter.name));
    for (const pair of query.split("&")) {
      const key = pair.split("=")[0];
      if (key && !key.includes("$") && !declaredKeys.has(key)) {
        unaccountedQueryKeys.push({ ...link, key, route: route.routePattern });
      }
    }
  }
  assert.deepEqual(unresolved, []);
  assert.deepEqual(unaccountedQueryKeys, []);
});

test("IA9 canonical records preserve context and load only active specialist data", () => {
  const dealsPage = readFileSync(resolve(osSourceRoot, "deals/page.tsx"), "utf8");
  const dealWorkspace = readFileSync(resolve(osSourceRoot, "deals/deals-workspace.tsx"), "utf8");
  const transactionWorkspace = readFileSync(
    resolve(osSourceRoot, "transactions/transaction-workspace.tsx"),
    "utf8",
  );
  const dispositionWorkspace = readFileSync(
    resolve(osSourceRoot, "dispositions/disposition-workspace.tsx"),
    "utf8",
  );
  const leadRecord = readFileSync(
    resolve(applicationSourceRoot, "app/leads/[leadId]/lead-detail-view.tsx"),
    "utf8",
  );
  const buyerPage = readFileSync(resolve(osSourceRoot, "buyers/page.tsx"), "utf8");
  const buyerWorkspace = readFileSync(
    resolve(osSourceRoot, "buyers/buyers-workspace.tsx"),
    "utf8",
  );
  const prospectingPage = readFileSync(resolve(osSourceRoot, "prospecting/page.tsx"), "utf8");

  assert.match(dealsPage, /transactionTabs\.has\(params\.tab/);
  assert.match(dealsPage, /dispositionTabs\.has\(params\.tab/);
  assert.match(dealWorkspace, /returnTo=/);
  assert.doesNotMatch(transactionWorkspace, /\bembedded\b/);
  assert.doesNotMatch(dispositionWorkspace, /\bembedded\b/);
  assert.match(leadRecord, /activeTab === "contract"\s*\? getBuyers\(\)/);
  assert.match(leadRecord, /internalReturnPath/);
  assert.match(buyerPage, /initialBuyerId=\{params\?\.buyer\}/);
  assert.match(buyerWorkspace, /window\.history\.replaceState\(null, "", `\/os\/buyers\?/);
  assert.match(buyerWorkspace, /styles\.detailOpen/);
  assert.match(leadRecord, /RecordTimeline/);
  assert.match(transactionWorkspace, /RecordTimeline/);
  assert.doesNotMatch(buyerPage, /DealJourney/);
  assert.doesNotMatch(prospectingPage, /AcquisitionJourney/);
  assert.match(
    prospectingPage,
    /view === "my-calls" \|\| \(canManage && view === "dialer-control"\)\s*\? getProspectingWorkbench\(\)/,
  );
  assert.match(prospectingPage, /canManage && view === "campaigns"/);
});

test("seller lead close-out is atomic, auditable, and separate from administrative archive", () => {
  const leadsPage = readFileSync(resolve(osSourceRoot, "leads/page.tsx"), "utf8");
  const lifecycle = readFileSync(
    resolve(osSourceRoot, "leads/lead-lifecycle-actions.tsx"),
    "utf8",
  );
  const closedPage = readFileSync(resolve(osSourceRoot, "leads/closed/page.tsx"), "utf8");
  const archivedPage = readFileSync(resolve(osSourceRoot, "leads/archived/page.tsx"), "utf8");
  const leadManager = readFileSync(
    resolve(osSourceRoot, "lead-manager/lead-manager-workspace.tsx"),
    "utf8",
  );
  const leadDetail = readFileSync(
    resolve(applicationSourceRoot, "app/leads/[leadId]/lead-detail-view.tsx"),
    "utf8",
  );
  const api = readFileSync(resolve(applicationSourceRoot, "app/lib/api.ts"), "utf8");
  const stageForm = readFileSync(
    resolve(applicationSourceRoot, "app/leads/[leadId]/stage-update-form.tsx"),
    "utf8",
  );

  assert.match(leadsPage, /href="\/os\/leads\/closed"/);
  assert.match(lifecycle, /\/api\/v1\/leads\/\$\{leadId\}\/close-out/);
  assert.match(lifecycle, /\/api\/v1\/leads\/\$\{leadId\}\/reopen/);
  assert.match(lifecycle, /minLength=\{10\}/);
  assert.match(lifecycle, /next_action_due_at: dueAt\.toISOString\(\)/);
  assert.match(lifecycle, /Cancel every pending approval tied to this lead/);
  assert.match(
    lifecycle,
    /Retire pending or approved offer plans and unused offer concessions/,
  );
  assert.match(lifecycle, /A funded deal\s+remains a completed success/);
  assert.match(lifecycle, /confirmed duplicate or test records/);
  assert.match(closedPage, /getClosedLeads\(\{ limit: pageSize \+ 1, offset, q \}\)/);
  assert.match(
    closedPage,
    /full read-only seller, property, communication, appointment, valuation, transaction, and buyer-offer history/,
  );
  assert.match(closedPage, /LeadReopenControl/);
  assert.match(closedPage, /close_out_reason/);
  assert.match(closedPage, /closed_out_by_user_email/);
  assert.match(closedPage, /Boolean\(lead\.archived_at\)/);
  assert.match(archivedPage, /getArchivedLeads\(\)/);
  assert.match(archivedPage, /Duplicate and test records/);
  assert.match(archivedPage, /encodeURIComponent\("\/os\/leads\/archived"\)/);
  assert.match(archivedPage, /lead\.close_out_disposition/);
  assert.match(archivedPage, /lead\.closed_out_at/);
  assert.match(lifecycle, /Permanently delete/);
  assert.doesNotMatch(stageForm, /\["dead",\s*"Dead"\]/);
  assert.doesNotMatch(stageForm, /\["disqualified",\s*"Disqualified"\]/);
  assert.match(leadManager, /Disqualify and close/);
  assert.match(leadManager, /qualificationNextAction === "disqualify"/);
  assert.match(leadManager, /name="disqualification_reason"/);
  assert.match(leadManager, /disqualification_reason:\s*nextActionType === "disqualify"/);
  assert.match(leadManager, /minLength=\{10\}/);
  assert.match(leadManager, /name="next_action_due_at" required type="datetime-local"/);
  assert.match(leadManager, /stops its tasks, reminders, appointments, and overdue follow-up warnings/);
  assert.match(leadDetail, /getWorkspaceProfile\(\)/);
  assert.match(leadDetail, /permissions\.includes\("leads:edit"\)/);
  assert.match(leadDetail, /permissions\.includes\("records:delete_or_archive"\)/);
  assert.match(leadDetail, /function ArchivedLeadRecord/);
  assert.match(leadDetail, /<ArchivedLeadRecord lead=\{lead\} \/>/);
  assert.match(leadDetail, /Calls, messages, and internal notes/);
  assert.match(leadDetail, /Recent activity history/);
  assert.match(leadDetail, /ReadOnlyAppointmentsPanel/);
  assert.match(leadDetail, /ReadOnlyValuationPanel/);
  assert.match(leadDetail, /ReadOnlyTransactionsPanel/);
  assert.match(leadDetail, /ReadOnlyBuyerOffersPanel/);
  assert.match(lifecycle, /canEditLead \? \(/);
  assert.match(lifecycle, /canArchiveRecords \? \(/);
  assert.match(lifecycle, />\s*Read only\s*<\/span>/);
  assert.match(closedPage, /getWorkspaceProfile\(\)/);
  assert.match(closedPage, /limit: pageSize \+ 1, offset, q/);
  assert.match(closedPage, /name="q"/);
  assert.match(closedPage, /pageHref\(page - 1, q\)/);
  assert.match(closedPage, /pageHref\(page \+ 1, q\)/);
  assert.match(archivedPage, /permissions\.includes\("records:delete_or_archive"\)/);
  assert.match(api, /closed: "true",\s*limit: String\(limit\),\s*offset: String\(offset\)/);
  assert.match(api, /cancelled_pending_approvals: number/);
  const closedRoute = currentRouteInventory.find(
    (route) => route.routePattern === "/os/leads/closed",
  );
  assert.ok(closedRoute?.queryParameters.some((parameter) => parameter.name === "q"));
  assert.ok(closedRoute?.queryParameters.some((parameter) => parameter.name === "page"));
});

test("address-only website leads stay visible without polluting operational queues", () => {
  const utilities = readFileSync(resolve(osSourceRoot, "os-utils.ts"), "utf8");
  const workspace = readFileSync(
    resolve(osSourceRoot, "leads/leads-workspace.tsx"),
    "utf8",
  );
  const leadDetail = readFileSync(
    resolve(applicationSourceRoot, "app/leads/[leadId]/lead-detail-view.tsx"),
    "utf8",
  );

  assert.match(utilities, /key: "address_only"/);
  assert.match(utilities, /label: "Address Only"/);
  assert.match(utilities, /website_intake_status === "address_only"/);
  assert.match(utilities, /return "Skip trace needed"/);
  assert.match(utilities, /\["all", "address_only"\]\.includes\(viewKey\) \? "newest" : "priority"/);
  assert.match(utilities, /if \(isAddressOnlyLead\(lead\)\) \{\s*return false;/);
  assert.match(workspace, /Review address-only lead/);
  assert.match(workspace, /const contactReadyLeads = (?:leads|workingLeads)\.filter\(\(lead\) => !isAddressOnlyLead\(lead\)\)/);
  assert.match(workspace, /const newLeadCount = contactReadyLeads\.filter/);
  assert.match(workspace, /const unassignedCount = contactReadyLeads\.filter/);
  assert.match(workspace, /Paid prospects/);
  assert.match(workspace, /Includes address-only captures/);
  assert.match(leadDetail, /Contact information was not completed/);
  assert.match(leadDetail, /DNC status manually before outreach/);
  assert.match(leadDetail, /Automated follow-up has not started/);
});

test("RBAC permission and role inventories remain synchronized with the API", () => {
  const source = readFileSync(resolve(repositoryRoot, "apps/api/app/domain/rbac.py"), "utf8");
  const permissionClass = source.slice(
    source.indexOf("class PermissionKeys:"),
    source.indexOf("\n\n@dataclass", source.indexOf("class PermissionKeys:")),
  );
  const sourcePermissions = [...permissionClass.matchAll(
    /^\s+[A-Z0-9_]+\s*=\s*"([^"]+)"/gm,
  )].map((match) => match[1]);
  const sourceRoles = [...source.matchAll(/RoleDefinition\(\s*"([^"]+)"/g)].map(
    (match) => match[1],
  );
  assert.deepEqual(sorted(permissionInventory), sorted(sourcePermissions));
  assert.deepEqual(sorted(roleInventory), sorted(sourceRoles));
  for (const destination of targetDestinations) {
    for (const permission of destination.anyPermissions) {
      assert.ok(permissionInventory.includes(permission), `${permission} is not a valid permission`);
    }
  }
});

test("the detailed Help control reference has an explicit future owner for every section", () => {
  const source = readFileSync(resolve(repositoryRoot, "docs/UI_CONTROL_REFERENCE.md"), "utf8");
  const headings = [...source.matchAll(/^## (.+)$/gm)].map((match) => match[1].trim());
  assert.deepEqual(
    sorted(controlReferenceSections.map((section) => section.heading)),
    sorted(headings),
  );
  const validOwners = new Set([
    ...targetDestinations.map((destination) => destination.id),
    "global",
    "public",
    "internal",
  ]);
  for (const section of controlReferenceSections) {
    assert.ok(validOwners.has(section.owner), `${section.heading} has unknown owner ${section.owner}`);
  }
  const routeHelpSections = new Set(
    currentRouteInventory.flatMap((route) => route.helpSections),
  );
  for (const heading of routeHelpSections) {
    assert.ok(headings.includes(heading), `${heading} is absent from the control reference`);
  }
});

test("canonical Help sources and baseline evidence commands are present", () => {
  for (const document of canonicalHelpDocuments) {
    assert.ok(statSync(resolve(repositoryRoot, document)).isFile(), `${document} is missing`);
  }
  assert.equal(evidenceContract.requiredViewports.length, 3);
  assert.match(evidenceContract.architectureCheck, /audit:ia/);
  assert.match(evidenceContract.visualBaseline, /baseline:ia/);
});

test("role defaults and current manuals use canonical workspace language", () => {
  const navigation = readFileSync(resolve(osSourceRoot, "os-navigation.tsx"), "utf8");
  for (const experience of targetRoleExperiences.filter((item) => item.defaultRoute)) {
    if (["owner", "founder_operator", "ceo", "administrator"].includes(experience.role)) continue;
    assert.ok(
      navigation.includes(`return "${experience.defaultRoute}"`),
      `${experience.role} default is not implemented in os-navigation.tsx`,
    );
  }
  for (const document of canonicalHelpDocuments) {
    const source = readFileSync(resolve(repositoryRoot, document), "utf8");
    assert.doesNotMatch(source, /Tools\s*>\s*(Lead Desk|Seller Pipeline|Field Operations)/i);
    assert.doesNotMatch(source, /Use \*\*Tools\*\*/i);
  }
});

test("old and new employee vocabulary is explicit and non-duplicative", () => {
  assert.ok(unique(vocabulary.map((term) => term.current)));
  const currentLabels = new Set(legacyNavigation.map((item) => item.label));
  for (const term of vocabulary) {
    assert.ok(currentLabels.has(term.current), `${term.current} is not a current navigation term`);
    assert.notEqual(term.current, term.target);
  }
});

test("Calendar owns one quick appointment workflow with contextual entry points", () => {
  const calendarWorkspace = readFileSync(
    resolve(osSourceRoot, "field-operations/field-operations-workspace.tsx"),
    "utf8",
  );
  const fieldCalendar = readFileSync(
    resolve(osSourceRoot, "field-operations/field-calendar.tsx"),
    "utf8",
  );
  const leadRecord = readFileSync(
    resolve(applicationSourceRoot, "app/leads/[leadId]/lead-detail-view.tsx"),
    "utf8",
  );
  const inbox = readFileSync(resolve(osSourceRoot, "inbox/inbox-workspace.tsx"), "utf8");

  assert.match(calendarWorkspace, /Schedule an appointment/);
  assert.match(calendarWorkspace, /Meeting format/);
  assert.match(calendarWorkspace, /Assigned team member/);
  assert.match(calendarWorkspace, /Schedule anyway/);
  assert.match(calendarWorkspace, /error\.status !== 409/);
  assert.match(fieldCalendar, /onSchedule/);
  assert.match(fieldCalendar, /appointmentVisuals/);
  assert.match(fieldCalendar, /appointmentBlockStyle/);
  assert.match(fieldCalendar, /Appointment color legend/);
  assert.match(leadRecord, /view=appointment&schedule=1&lead=/);
  assert.match(inbox, /view=appointment&schedule=1&lead=/);
});

test("Operations Assistant cannot enter Settings through underwriting permission", () => {
  const source = readFileSync(resolve(osSourceRoot, "settings/settings-sections.ts"), "utf8");
  const dataQuality = source.slice(
    source.indexOf('key: "data-quality"'),
    source.indexOf('key: "finance-policy"'),
  );
  assert.match(dataQuality, /allowedRoles:\s*\["administrator", "acquisition_manager", "acquisition_rep"\]/);
  assert.doesNotMatch(dataQuality, /operations_assistant/);
  assert.match(source, /section\.allowedRoles\.some\(\(role\) => profile\.role_keys\.includes\(role\)\)/);
});

test("Inbox quietly refreshes pending live Twilio SMS delivery states", () => {
  const delivery = loadTypeScriptModule(
    resolve(osSourceRoot, "inbox/sms-delivery.ts"),
  );
  const now = Date.parse("2026-08-13T21:00:00Z");
  const makeItem = (id, status, overrides = {}) => ({
    id,
    direction: "outbound",
    channel: "sms",
    status,
    provider: "twilio",
    occurred_at: "2026-08-13T20:59:00Z",
    ...overrides,
  });

  assert.equal(delivery.SMS_DELIVERY_REFRESH_INTERVAL_MS, 2_000);
  assert.equal(delivery.SMS_DELIVERY_REFRESH_MAX_ATTEMPTS, 15);
  assert.equal(delivery.SMS_DELIVERY_AUTO_REFRESH_RECENCY_MS, 5 * 60_000);
  assert.equal(
    delivery.pendingOutboundTwilioSmsKey(
      [
        makeItem("queued-message", "queued"),
        makeItem("sent-message", "sent"),
        makeItem("delivered-message", "delivered"),
        makeItem("inbound-message", "queued", { direction: "inbound" }),
        makeItem("simulated-message", "queued", { provider: "simulated" }),
        makeItem("old-message", "queued", { occurred_at: "2026-08-13T20:00:00Z" }),
      ],
      now,
    ),
    "queued-message|sent-message",
  );
  assert.equal(
    delivery.pendingOutboundTwilioSmsKey(
      [
        makeItem("delivered-message", "delivered"),
        makeItem("failed-message", "failed"),
        makeItem("undelivered-message", "undelivered"),
      ],
      now,
    ),
    "",
  );

  const inbox = readFileSync(resolve(osSourceRoot, "inbox/inbox-workspace.tsx"), "utf8");
  assert.match(inbox, /if \(!openConversationId \|\| !pendingSmsDeliveryKey\) return/);
  assert.match(inbox, /attemptCount >= SMS_DELIVERY_REFRESH_MAX_ATTEMPTS/);
  assert.match(inbox, /current\?\.id === conversationId \? refreshed : current/);
  assert.match(inbox, /window\.clearTimeout\(timer\)/);
});

test("Lead contact permission control manages calls and SMS without a typed note", () => {
  const control = readFileSync(
    resolve(osSourceRoot, "_components/sms-permission-control.tsx"),
    "utf8",
  );
  const inbox = readFileSync(resolve(osSourceRoot, "inbox/inbox-workspace.tsx"), "utf8");
  const leadDetail = readFileSync(
    resolve(applicationSourceRoot, "app/leads/[leadId]/lead-detail-view.tsx"),
    "utf8",
  );

  assert.match(control, /\/contact-permission/);
  assert.match(control, /Phone calls/);
  assert.match(control, /Text messages \(SMS\)/);
  assert.match(control, /Call permission:/);
  assert.match(control, /SMS permission:/);
  assert.doesNotMatch(control, /name="evidence_note"/);
  assert.match(inbox, /fallbackPhoneConsentStatus=\{detail\.voice_eligibility\.consent_status\}/);
  assert.match(inbox, /fallbackConsentStatus=\{detail\.sms_eligibility\.consent_status\}/);
  assert.match(leadDetail, /canManagePhone=\{canManagePhonePermission\}/);
  assert.match(leadDetail, /canManageSms=\{canManageSmsPermission\}/);
});

test("Inbox call intelligence includes a safely derived completed-note quick read", () => {
  const quickRead = loadTypeScriptModule(
    resolve(osSourceRoot, "inbox/call-quick-read.ts"),
  );
  const items = quickRead.buildCallQuickRead({
    summary:
      "Seller is considering relocating closer to family. Additional details are intentionally excluded from the compact presentation.",
    motivation: "Health and safety concerns make maintaining the property difficult.",
    timeline: "No firm sale deadline was established.",
    asking_price: "$100,000",
    mortgage_balance: "$62,000",
    next_action: "Verify title, value, repairs, and current occupancy before discussing an offer.",
  });

  assert.equal(
    items.map((item) => item.label).join("|"),
    "Bottom line|Why now|Timing|Numbers|Next step",
  );
  assert.equal(items[0].value, "Seller is considering relocating closer to family.");
  assert.equal(items[3].value, "Asking $100,000 / Payoff $62,000");

  const backendSummary = quickRead.buildCallQuickRead(
    {
      summary: "Long-form summary that should not be used.",
      motivation: null,
      timeline: null,
      asking_price: null,
      mortgage_balance: null,
      next_action: null,
    },
    "Motivated seller; verify the foundation repair before pricing.",
  );
  assert.equal(
    backendSummary[0].value,
    "Motivated seller; verify the foundation repair before pricing.",
  );
  assert.equal(backendSummary.length, 1);

  const contaminatedTimeline = quickRead.buildCallQuickRead({
    summary: "Seller is considering relocating closer to family.",
    motivation: "Health and safety concerns.",
    timeline: "Seller will not make the長 drive without an offer.",
    asking_price: "$100,000",
    mortgage_balance: "$62,000",
    next_action: "Verify title and value.",
  });
  assert.equal(contaminatedTimeline.some((item) => item.label === "Timing"), false);

  const inbox = readFileSync(resolve(osSourceRoot, "inbox/inbox-workspace.tsx"), "utf8");
  assert.match(inbox, /\["approved", "completed"\]\.includes\(transcript\.status\)/);
  assert.match(inbox, /<strong>Quick read<\/strong>/);
});

test("Inbox call recordings use a private authenticated player with complete controls", () => {
  const inbox = readFileSync(resolve(osSourceRoot, "inbox/inbox-workspace.tsx"), "utf8");
  const player = readFileSync(resolve(osSourceRoot, "inbox/call-recording-player.tsx"), "utf8");
  const inboxStyles = readFileSync(resolve(osSourceRoot, "inbox/inbox.module.css"), "utf8");

  assert.match(player, /\/api\/v1\/voice\/recordings\/\$\{recordingId\}\/media/);
  assert.match(player, /headers: await getHeaders\(\)/);
  assert.match(player, /cache: "no-store"/);
  assert.match(player, /signal: controller\.signal/);
  assert.match(player, /response\.blob\(\)/);
  assert.match(player, /blob\.size === 0/);
  assert.match(player, /URL\.createObjectURL/);
  assert.match(player, /URL\.revokeObjectURL/);
  assert.match(player, /abortControllerRef\.current\?\.abort\(\)/);
  assert.doesNotMatch(player, /api\.twilio\.com|RecordingUrl|provider_recording_id/);

  assert.match(player, /audio\.play\(\)/);
  assert.match(player, /audio\.pause\(\)/);
  assert.match(player, /Pause call recording/);
  assert.match(player, /Play call recording/);
  assert.match(player, /aria-label="Go back 10 seconds"/);
  assert.match(player, /aria-label="Go forward 10 seconds"/);
  assert.match(player, /aria-label="Recording position"/);
  assert.match(player, /aria-valuetext=\{playbackAriaValue\(currentTime, duration\)\}/);
  assert.match(player, /formatPlaybackTime\(currentTime\)[\s\S]*formatPlaybackTime\(duration\)/);
  assert.match(player, /aria-label="Playback speed"/);
  assert.match(player, /CALL_PLAYBACK_RATES\.map/);
  assert.match(player, /Unmute recording/);
  assert.match(player, /Mute recording/);
  assert.match(player, /aria-label="Recording volume"/);
  assert.match(player, /Download call audio/);

  assert.match(player, /stonegate:call-playback:/);
  assert.match(player, /window\.sessionStorage\.getItem\(sessionKey\)/);
  assert.match(player, /window\.sessionStorage\.setItem/);
  assert.match(player, /window\.sessionStorage\.removeItem\(sessionKey\)/);
  assert.match(player, /stonegate:active-call-player/);
  assert.match(player, /window\.addEventListener\(ACTIVE_CALL_PLAYER_EVENT/);
  assert.match(player, /new CustomEvent\(ACTIVE_CALL_PLAYER_EVENT/);
  assert.match(player, /activeRecordingId !== recordingId[\s\S]*persistPlayback\(\)[\s\S]*clearMedia\(\)/);
  assert.match(player, /metadataAbortControllerRef\.current\?\.abort\(\)/);
  assert.match(player, /waitForMetadata\(audio, controller\.signal\)/);
  assert.match(player, /signal\?\.addEventListener\("abort", handleAbort/);
  assert.match(player, /if \(isAbortError\(error\)\) return/);
  assert.match(player, /role="group"/);
  assert.match(inboxStyles, /container: recording-player \/ inline-size/);
  assert.match(inboxStyles, /@container recording-player \(max-width: 500px\)/);
  assert.match(inboxStyles, /\.transcriptSegmentHeader > button[\s\S]*min-height: 44px/);

  assert.match(player, /useImperativeHandle\(ref, \(\) => \(\{ seekTo \}\)/);
  assert.match(inbox, /Play recording from \$\{formatDuration/);
  assert.match(inbox, /onSeekToSeconds\(Math\.max\(0, segment\.start \?\? 0\)\)/);
  assert.match(inbox, /recordingPlayerRefs\.current\[item\.recording_id as string\]\?\.seekTo/);
  assert.match(inbox, /\{ play: true \}/);
  assert.match(inbox, /className=\{styles\.fullTranscriptPanel\}/);
  assert.match(inbox, /Download transcript \(\.txt\)/);
  assert.match(inbox, /\/api\/v1\/voice\/transcripts\/\$\{transcript\.id\}\/download/);
  assert.match(inbox, /headers: await getHeaders\(\)/);
  assert.match(inbox, /cache: "no-store"/);
});

test("Call playback helpers clamp unsafe media values and restore safe session progress", () => {
  const playback = loadTypeScriptModule(resolve(osSourceRoot, "inbox/call-playback.ts"));

  assert.deepEqual(Array.from(playback.CALL_PLAYBACK_RATES), [0.75, 1, 1.25, 1.5, 2]);
  assert.equal(playback.clampPlaybackTime(-4, 60), 0);
  assert.equal(playback.clampPlaybackTime(90, 60), 60);
  assert.equal(playback.clampPlaybackTime(Number.NaN, 60), 0);
  assert.equal(playback.clampPlaybackTime(Number.POSITIVE_INFINITY, 60), 0);
  assert.equal(playback.clampPlaybackTime(25, Number.NaN), 25);
  assert.equal(playback.skipPlaybackTime(4, -10, 60), 0);
  assert.equal(playback.skipPlaybackTime(55, 10, 60), 60);
  assert.equal(playback.skipPlaybackTime(Number.NaN, 10, 60), 0);

  assert.equal(playback.formatPlaybackTime(Number.NaN), "0:00");
  assert.equal(playback.formatPlaybackTime(59.9), "0:59");
  assert.equal(playback.formatPlaybackTime(60), "1:00");
  assert.equal(playback.formatPlaybackTime(3599), "59:59");
  assert.equal(playback.formatPlaybackTime(3600), "1:00:00");
  assert.equal(playback.formatPlaybackTime(3661), "1:01:01");
  assert.equal(
    playback.playbackAriaValue(61, 120),
    "1 minute 1 second of 2 minutes",
  );

  assert.equal(playback.parseCallPlaybackSession(null, 100), null);
  assert.equal(playback.parseCallPlaybackSession("not-json", 100), null);
  assert.equal(
    playback.parseCallPlaybackSession('{"position":"25","rate":1}', 100),
    null,
  );
  assert.equal(
    playback.parseCallPlaybackSession('{"position":25,"rate":3}', 100),
    null,
  );
  assert.equal(
    playback.parseCallPlaybackSession('{"position":1e999,"rate":1}', 100),
    null,
  );

  const restored = playback.parseCallPlaybackSession('{"position":25,"rate":1.25}', 100);
  assert.equal(restored.position, 25);
  assert.equal(restored.rate, 1.25);
  const negative = playback.parseCallPlaybackSession('{"position":-5,"rate":1}', 100);
  assert.equal(negative.position, 0);
  const completed = playback.parseCallPlaybackSession('{"position":99,"rate":1.5}', 100);
  assert.equal(completed.position, 0);
  assert.equal(completed.rate, 1.5);
  const metadataPending = playback.parseCallPlaybackSession(
    '{"position":25,"rate":0.75}',
    Number.NaN,
  );
  assert.equal(metadataPending.position, 25);
  assert.equal(metadataPending.rate, 0.75);
});

test("Inbox renders private inbound MMS photos inline", () => {
  const inbox = readFileSync(resolve(osSourceRoot, "inbox/inbox-workspace.tsx"), "utf8");
  const attachment = readFileSync(resolve(osSourceRoot, "inbox/message-attachment.tsx"), "utf8");

  assert.match(inbox, /item\.channel === "sms" && item\.attachments\.length > 0/);
  assert.match(inbox, /\? "MMS"/);
  assert.match(inbox, /item\.body\.trim\(\)/);
  assert.match(inbox, /<MessageAttachment/);
  assert.match(attachment, /headers: await getHeaders\(\)/);
  assert.match(attachment, /cache: "no-store"/);
  assert.match(attachment, /URL\.revokeObjectURL/);
  assert.match(attachment, /<Image[\s\S]*unoptimized/);
  assert.match(attachment, /target="_blank"/);
  assert.match(attachment, /Image attachment sent by/);
  assert.doesNotMatch(attachment, /Property photo sent by/);
});

test("Property lead editing stays collapsed until the operator asks to open it", () => {
  const leadRecord = readFileSync(
    resolve(applicationSourceRoot, "app/leads/[leadId]/lead-detail-view.tsx"),
    "utf8",
  );

  assert.match(leadRecord, /<details[\s\S]*styles\.editLeadDisclosure/);
  assert.match(leadRecord, /open=\{editLeadOpen\}/);
  assert.match(leadRecord, /const editLeadOpen = requestedEditor === "lead"/);
  assert.match(leadRecord, /tab=property&edit=lead#edit-lead/);
  assert.match(leadRecord, /Open editor/);
  assert.match(leadRecord, /Close editor/);
});

test("All Leads is chronological by default while operational lead views stay priority-first", () => {
  const utilities = loadTypeScriptModule(resolve(osSourceRoot, "os-utils.ts"));
  const makeLead = (id, createdAt, overrides = {}) => ({
    id,
    created_at: createdAt,
    lead_temperature: null,
    source: "referral",
    stage_key: "new",
    motivation: null,
    desired_timeline: null,
    property_condition: null,
    occupancy_status: null,
    asking_price: null,
    mortgage_balance: null,
    appointment_status: null,
    ...overrides,
  });
  const hotOlderLead = makeLead("hot-older", "2026-08-07T12:00:00Z", {
    lead_temperature: "hot",
  });
  const fastTimelineLead = makeLead("fast-timeline", "2026-08-08T12:00:00Z", {
    desired_timeline: "ASAP",
  });
  const newestLead = makeLead("newest", "2026-08-09T12:00:00Z");
  const leads = [hotOlderLead, newestLead, fastTimelineLead];

  assert.equal(
    utilities.getFilteredLeads(leads, [], "all").map((lead) => lead.id).join(","),
    "newest,fast-timeline,hot-older",
  );
  assert.equal(
    utilities.getFilteredLeads(leads, [], "all", "oldest").map((lead) => lead.id).join(","),
    "hot-older,fast-timeline,newest",
  );
  assert.equal(
    utilities.getFilteredLeads(leads, [], "urgent").map((lead) => lead.id).join(","),
    "hot-older,fast-timeline",
  );
  assert.equal(utilities.normalizeLeadSortKey("invalid", "all"), "newest");
  assert.equal(utilities.normalizeLeadSortKey("invalid", "urgent"), "priority");
});

test("Leads exposes received timestamps and URL-backed sort controls", () => {
  const page = readFileSync(resolve(osSourceRoot, "leads/page.tsx"), "utf8");
  const workspace = readFileSync(
    resolve(osSourceRoot, "leads/leads-workspace.tsx"),
    "utf8",
  );
  const leadsRoute = currentRouteInventory.find((route) => route.routePattern === "/os/leads");

  assert.match(page, /initialSort=\{normalizeLeadSortKey\(first\(params\.sort\)/);
  assert.match(workspace, /leadSortOptions\.map/);
  assert.match(workspace, /params\.set\("sort", next\.sort\)/);
  assert.match(workspace, /<span>Received<\/span>/);
  assert.match(workspace, /className=\{styles\.received\} dateTime=\{lead\.created_at\}/);
  assert.ok(leadsRoute?.queryParameters.some((parameter) => parameter.name === "sort"));
});

test("Tall dialogs keep actions visible while their body scrolls", () => {
  const designSystemStyles = readFileSync(
    resolve(osSourceRoot, "_components/design-system.module.css"),
    "utf8",
  );
  const closedDialogRule = designSystemStyles.match(/\.overlay\s*\{([^}]*)\}/s)?.[1] ?? "";

  assert.doesNotMatch(closedDialogRule, /display\s*:/);
  assert.match(
    designSystemStyles,
    /\.overlay\[open\]\s*\{[^}]*display:\s*grid;[^}]*grid-template-rows:\s*auto minmax\(0, 1fr\) auto;/s,
  );
  assert.match(
    designSystemStyles,
    /\.overlayBody\s*\{[^}]*min-height:\s*0;[^}]*overflow-y:\s*auto;/s,
  );
});

test("Voice line settings make 24/7 staff ringing the visible default", () => {
  const voiceSettings = readFileSync(
    resolve(osSourceRoot, "settings/communications/voice-line-settings.tsx"),
    "utf8",
  );

  assert.equal(
    [...voiceSettings.matchAll(/coverage_start_hour: 0,/g)].length,
    2,
  );
  assert.equal(
    [...voiceSettings.matchAll(/coverage_end_hour: 24,/g)].length,
    2,
  );
  assert.doesNotMatch(voiceSettings, /name="coverage_start_hour"/);
  assert.doesNotMatch(voiceSettings, /name="coverage_end_hour"/);
  assert.equal([...voiceSettings.matchAll(/<strong>24\/7 staff ringing<\/strong>/g)].length, 2);
  assert.equal([...voiceSettings.matchAll(/name="coverage_timezone"/g)].length, 2);
  assert.match(voiceSettings, /24\/7 staff ringing is always on/);
});

test("Marketing exposes safe Meta delivery health without rendering credentials", () => {
  const page = readFileSync(resolve(osSourceRoot, "marketing/page.tsx"), "utf8");
  const api = readFileSync(resolve(applicationSourceRoot, "app/lib/api.ts"), "utf8");

  assert.match(page, /Meta delivery health/);
  assert.match(page, /Meta match-key coverage/);
  assert.match(page, /Dataset alignment/);
  assert.match(page, /API \$\{testMode\(apiMetaTestMode\)\} · Worker/);
  assert.match(page, /provider_accepted_count/);
  assert.match(page, /provider_warnings/);
  assert.match(api, /meta_pixel_id_fingerprint/);
  assert.match(api, /oldest_meta_pending_at/);
  assert.match(api, /normalizeMarketingOverview/);
  assert.doesNotMatch(page, /META_CONVERSIONS_ACCESS_TOKEN/);
  assert.doesNotMatch(page, /META_TEST_EVENT_CODE/);
});
