import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const tasksWorkspace = readFileSync(
  resolve(appRoot, "os/tasks/tasks-workspace.tsx"),
  "utf8",
);
const tasksPage = readFileSync(resolve(appRoot, "os/tasks/page.tsx"), "utf8");
const inboxWorkspace = readFileSync(
  resolve(appRoot, "os/inbox/inbox-workspace.tsx"),
  "utf8",
);
const leadsWorkspace = readFileSync(
  resolve(appRoot, "os/leads/leads-workspace.tsx"),
  "utf8",
);
const reminderControl = readFileSync(
  resolve(appRoot, "os/leads/lead-reminder-control.tsx"),
  "utf8",
);
const leadStageBadge = readFileSync(
  resolve(appRoot, "os/_components/lead-stage-badge.tsx"),
  "utf8",
);
const leadStageBadgeStyles = readFileSync(
  resolve(appRoot, "os/_components/lead-stage-badge.module.css"),
  "utf8",
);
const osUtils = readFileSync(resolve(appRoot, "os/os-utils.ts"), "utf8");
const homePage = readFileSync(resolve(appRoot, "os/page.tsx"), "utf8");
const apiSource = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");

test("AI operations stay out of human task and due-date views", () => {
  assert.match(tasksWorkspace, /if \(item\.item_type === "ai_work"\)/);
  assert.match(tasksWorkspace, /view === "ai_review"[\s\S]*item\.work_kind === "ai_review"/);
  assert.match(tasksWorkspace, /view === "exceptions"[\s\S]*"operational_exception"/);
  assert.match(tasksWorkspace, /AI Suggestions/);
  assert.match(tasksWorkspace, /item\.item_type !== "ai_work" && item\.due_status !== "completed"/);
  assert.match(tasksPage, /item\.item_type !== "ai_work" && item\.due_status !== "completed"/);
});

test("completing a primary task schedules another action only by explicit choice", () => {
  assert.match(tasksWorkspace, /const \[scheduleSuccessor, setScheduleSuccessor\] = useState\(false\)/);
  assert.match(tasksWorkspace, /name="schedule_successor"/);
  assert.match(tasksWorkspace, /successor: shouldScheduleSuccessor/);
  assert.match(tasksWorkspace, /No replacement task will be created/);
  assert.doesNotMatch(tasksWorkspace, /name="terminal"/);
  assert.doesNotMatch(tasksWorkspace, /must leave this step with one owner/);
});

test("AI call notes do not preselect creation of a follow-up task", () => {
  assert.match(inboxWorkspace, /const \[createTask, setCreateTask\] = useState\(false\)/);
  assert.match(inboxWorkspace, /checked=\{createTask\}/);
  assert.match(inboxWorkspace, /Create follow-up task/);
});

test("seller reminders are explicit, easy to schedule, and easy to finish", () => {
  assert.match(leadsWorkspace, /<LeadReminderControl/);
  assert.match(leadsWorkspace, /canEdit=\{canEditLead\}/);
  assert.match(leadsWorkspace, /lead=\{selectedLead\}/);
  assert.match(reminderControl, /Set reminder/);
  assert.match(reminderControl, />6 months</);
  assert.match(reminderControl, /sms_notification_enabled: smsNotificationEnabled/);
  assert.match(reminderControl, /Text the assigned user when due/);
  assert.match(reminderControl, /SMS notification on/);
  assert.match(reminderControl, /\/api\/v1\/leads\/\$\{lead\.id\}\/tasks/);
  assert.match(reminderControl, /\/api\/v1\/tasks\/\$\{reminder\.task_id\}\/complete/);
  assert.match(reminderControl, />Done/);
  assert.match(osUtils, /label: "Reminders"/);
  assert.match(osUtils, /return "Reminder due"/);
  assert.doesNotMatch(osUtils, /return "Needs follow-up"/);
  assert.doesNotMatch(osUtils, /return "Overdue follow-up"/);
});

test("lead status presents the pipeline stage without turning qualification gaps into urgency", () => {
  assert.match(leadsWorkspace, /<span>Seller<\/span><span>Received<\/span><span>Stage<\/span><span>Owner<\/span><span>Reminder<\/span>/);
  assert.match(leadsWorkspace, /<LeadStageBadge stageKey=\{lead\.stage_key\} \/>/);
  assert.match(leadsWorkspace, /isManualReminderDue\(lead\)[\s\S]*Reminder due/);
  assert.match(leadsWorkspace, /qualificationSummary\(lead\)/);
  assert.match(leadsWorkspace, /lead\.primary_next_action\?\.title \?\? "No reminder set"/);
  assert.doesNotMatch(leadsWorkspace, /Open qualification queue/);
  assert.doesNotMatch(leadsWorkspace, /getLeadOperatingStatus/);
  assert.doesNotMatch(leadsWorkspace, /<StatusBadge[^>]*>\{operatingStatus\}<\/StatusBadge>/);
  assert.doesNotMatch(leadsWorkspace, /<span>Status<\/span>/);
});

test("lead stages use one consistent, distinct color system", () => {
  assert.match(leadStageBadge, /getPipelineStage\(stageKey\)\?\.key/);
  assert.match(leadStageBadge, /\["dead", "disqualified", "closed"\]/);
  for (const stage of [
    "new",
    "contacting",
    "contacted",
    "qualifying",
    "qualified",
    "appointment",
    "underwriting",
    "offer",
    "nurture",
    "under_contract",
    "closed",
  ]) {
    assert.match(leadStageBadgeStyles, new RegExp(`data-stage="${stage}"`));
  }
  assert.doesNotMatch(leadsWorkspace, /function stageTone/);
});

test("Home shows real reply work and manual reminders instead of synthetic urgency", () => {
  assert.match(apiSource, /getInboxAttentionSummary/);
  assert.match(apiSource, /\/api\/v1\/inbox\/attention-summary/);
  assert.match(homePage, /inboxAttention\.needs_reply_count/);
  assert.match(homePage, /reminder\?\.action_type === "follow_up"/);
  assert.match(homePage, /Only reminders set by your team/);
  assert.match(homePage, /Scheduled commitments only/);
  assert.match(homePage, /Open Today/);
  assert.doesNotMatch(homePage, /Unread conversations/);
  assert.doesNotMatch(homePage, /Seller records incomplete/);
  assert.doesNotMatch(homePage, /Tasks without due dates/);
  assert.doesNotMatch(homePage, /for \(const lead of needsQualification\)/);
});

test("Inbox uses explicit reply states and only deliberate reminders become overdue", () => {
  assert.match(inboxWorkspace, /Needs reply/);
  assert.match(inboxWorkspace, /Waiting on them/);
  assert.match(inboxWorkspace, /Remind me/);
  assert.match(inboxWorkspace, /Done/);
  assert.match(inboxWorkspace, /\/response/);
  assert.match(inboxWorkspace, /action === "remind"/);
  assert.match(inboxWorkspace, /Reminder overdue/);
  assert.match(homePage, /scheduled reminders overdue/);
  assert.doesNotMatch(homePage, /beyond response target/);
});
