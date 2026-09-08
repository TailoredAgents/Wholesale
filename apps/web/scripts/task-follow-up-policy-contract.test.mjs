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
