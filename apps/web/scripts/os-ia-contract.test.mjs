import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

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
      literals.push({
        path: relative(webRoot, path).replaceAll("\\", "/"),
        value: match[2],
      });
    }
  }
  return literals;
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
  assert.match(prospectingPage, /view === "my-calls"\s*\? getProspectingWorkbench\(\)/);
  assert.match(prospectingPage, /canManage && view === "campaigns"/);
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
