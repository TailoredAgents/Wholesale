import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const leadsPage = readFileSync(resolve(appRoot, "os/leads/page.tsx"), "utf8");
const leadsNav = readFileSync(resolve(appRoot, "os/leads/seller-leads-nav.tsx"), "utf8");
const todayWorkspace = readFileSync(
  resolve(appRoot, "os/leads/seller-today-workspace.tsx"),
  "utf8",
);
const leadManagerRedirect = readFileSync(
  resolve(appRoot, "os/lead-manager/page.tsx"),
  "utf8",
);

test("the primary Leads navigation uses a focused Today workspace", () => {
  assert.match(leadsNav, /view=today/);
  assert.match(leadsNav, /label: "Today"/);
  assert.doesNotMatch(leadsNav, /label: "Lead Queue"/);
  assert.match(leadsPage, /<SellerTodayWorkspace/);
  assert.doesNotMatch(leadsPage, /getLeadManagerOverview/);
  assert.doesNotMatch(leadsPage, /<LeadManagerWorkspace/);
  assert.match(leadManagerRedirect, /redirect\("\/os\/leads\?view=today"\)/);
});

test("Today shows real activity without manufacturing follow-up work", () => {
  assert.match(todayWorkspace, /missed_prospecting_callback/);
  assert.match(todayWorkspace, /MAILBOX_NOTIFICATION_TYPES/);
  assert.match(todayWorkspace, /const reminder = lead\.primary_next_action/);
  assert.match(todayWorkspace, /reminder\?\.action_type === "follow_up"/);
  assert.match(todayWorkspace, /\["scheduled", "rescheduled"\]/);
  assert.match(todayWorkspace, /What actually needs attention today/);
  assert.match(todayWorkspace, /It does not invent follow-up work/);
  assert.match(todayWorkspace, /view=needs_qualification/);
  assert.doesNotMatch(todayWorkspace, /neglected/i);
  assert.doesNotMatch(todayWorkspace, /awaiting_acceptance/);
});
