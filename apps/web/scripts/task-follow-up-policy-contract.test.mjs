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
const osUtils = readFileSync(resolve(appRoot, "os/os-utils.ts"), "utf8");

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
  assert.match(leadsWorkspace, /<span>Seller<\/span><span>Received<\/span><span>Stage<\/span>/);
  assert.match(leadsWorkspace, /<StatusBadge tone=\{stageTone\(lead\.stage_key\)\}>\{stageLabel\(lead\)\}<\/StatusBadge>/);
  assert.match(leadsWorkspace, /isManualReminderDue\(lead\)[\s\S]*Reminder due/);
  assert.match(leadsWorkspace, /qualificationSummary\(lead\)/);
  assert.match(leadsWorkspace, /No scheduled task/);
  assert.doesNotMatch(leadsWorkspace, /<StatusBadge[^>]*>\{operatingStatus\}<\/StatusBadge>/);
  assert.doesNotMatch(leadsWorkspace, /<span>Status<\/span>/);
});
