import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const stateSource = readFileSync(
  resolve(
    webRoot,
    "src/app/os/prospecting/prospecting-qualification-state.ts",
  ),
  "utf8",
);
const checklistSource = readFileSync(
  resolve(
    webRoot,
    "src/app/os/prospecting/prospecting-qualification-checklist.tsx",
  ),
  "utf8",
);
const workspaceSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-workspace.tsx"),
  "utf8",
);
const dialerSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-dialer.tsx"),
  "utf8",
);
const cssSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting.module.css"),
  "utf8",
);

let stateModulePromise;
function importStateModule() {
  if (!stateModulePromise) {
    const javascript = ts.transpileModule(stateSource, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText;
    stateModulePromise = import(
      `data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`
    );
  }
  return stateModulePromise;
}

function item(overrides = {}) {
  return {
    question_key: "motivation",
    label: "Motivation",
    prompt: "Why are you considering selling?",
    answer_type: "text",
    choices: [],
    is_required: true,
    state: "not_covered",
    answer_value: null,
    source: "va",
    revision: 0,
    captured_at: null,
    updated_at: null,
    ...overrides,
  };
}

function checklist(items) {
  return {
    attempt_id: "attempt-one",
    script_version_id: "script-one",
    items,
    answered_count: 0,
    total_count: items.length,
    required_answered_count: 0,
    required_count: items.filter((entry) => entry.is_required).length,
    missing_required_keys: items
      .filter((entry) => entry.is_required)
      .map((entry) => entry.question_key),
    complete: false,
  };
}

test("blank and unpinned choice answers never become confirmed green answers", async () => {
  const {
    createQualificationEditors,
    editQualificationEditor,
    isConfirmedQualificationAnswer,
    qualificationValidationMessage,
  } = await importStateModule();

  assert.equal(
    isConfirmedQualificationAnswer(
      item({ state: "answered", answer_value: "   " }),
    ),
    false,
  );
  const choice = item({
    question_key: "occupancy",
    answer_type: "choice",
    choices: ["Vacant", "Owner occupied"],
    state: "answered",
    answer_value: "vacant",
  });
  assert.equal(isConfirmedQualificationAnswer(choice), false);
  assert.equal(
    isConfirmedQualificationAnswer({ ...choice, answer_value: "Vacant" }),
    true,
  );

  const editor = createQualificationEditors(checklist([item()])).motivation;
  const blankAnswered = editQualificationEditor(editor, {
    state: "answered",
    answerValue: " ",
    mutationId: "mutation-one",
  });
  assert.match(qualificationValidationMessage(blankAnswered), /Enter an answer/);
  const unexplainedConflict = editQualificationEditor(editor, {
    state: "conflict",
    answerValue: "",
    mutationId: "mutation-two",
  });
  assert.match(qualificationValidationMessage(unexplainedConflict), /short explanation/);
  assert.match(
    checklistSource,
    /const usesExplanationInput = \["needs_follow_up", "conflict"\]\.includes/,
  );
  assert.match(
    checklistSource,
    /item\.answer_type === "choice" && !usesExplanationInput/,
  );
  assert.match(checklistSource, /Follow-up or conflict context/);
  assert.match(checklistSource, /maxLength=\{2000\}/);
  assert.equal(
    checklistSource.match(
      /item\.answer_type === "choice" \? "" : editor\.draftValue/g,
    )?.length,
    2,
  );
});

test("a newer local edit survives an older in-flight response", async () => {
  const {
    applyQualificationSaveSuccess,
    beginQualificationSave,
    buildQualificationMutation,
    createQualificationEditors,
    editQualificationEditor,
  } = await importStateModule();
  const initial = createQualificationEditors(checklist([item()])).motivation;
  const firstEdit = editQualificationEditor(initial, {
    state: "answered",
    answerValue: "First answer",
    mutationId: "mutation-one",
  });
  const saving = beginQualificationSave(firstEdit);
  const secondEdit = editQualificationEditor(saving, {
    state: "answered",
    answerValue: "Latest answer",
    mutationId: "mutation-two",
  });
  const afterOldResponse = applyQualificationSaveSuccess(
    secondEdit,
    item({
      state: "answered",
      answer_value: "First answer",
      revision: 1,
    }),
  );
  assert.equal(afterOldResponse.saveStatus, "dirty");
  assert.equal(afterOldResponse.draftValue, "Latest answer");
  const nextMutation = buildQualificationMutation(afterOldResponse, {
    browserSessionId: "browser-one",
    leaseToken: "lease-one",
  });
  assert.equal(nextMutation.expected_revision, 1);
  assert.equal(nextMutation.mutation_id, "mutation-two");
  assert.equal(nextMutation.browser_session_id, "browser-one");
  assert.equal(nextMutation.lease_token, "lease-one");
});

test("saved checklist progress only counts valid server-confirmed answers", async () => {
  const { replaceQualificationChecklistItem } = await importStateModule();
  const initial = checklist([
    item(),
    item({
      question_key: "occupancy",
      label: "Occupancy",
      answer_type: "choice",
      choices: ["Vacant", "Owner occupied"],
    }),
    item({ question_key: "asking_price", label: "Price", is_required: false }),
  ]);
  const withMotivation = replaceQualificationChecklistItem(
    initial,
    item({ state: "answered", answer_value: "Moving closer to family", revision: 1 }),
  );
  assert.equal(withMotivation.answered_count, 1);
  assert.deepEqual(withMotivation.missing_required_keys, ["occupancy"]);
  assert.equal(withMotivation.complete, false);

  const complete = replaceQualificationChecklistItem(
    withMotivation,
    item({
      question_key: "occupancy",
      label: "Occupancy",
      answer_type: "choice",
      choices: ["Vacant", "Owner occupied"],
      state: "answered",
      answer_value: "Vacant",
      revision: 1,
    }),
  );
  assert.equal(complete.required_answered_count, 2);
  assert.deepEqual(complete.missing_required_keys, []);
  assert.equal(complete.complete, true);
});

test("only unresolved saves block every disposition; saved conflicts remain warm-handoff data", async () => {
  const {
    createQualificationEditors,
    hasBlockingQualificationSave,
  } = await importStateModule();
  const clearEditors = createQualificationEditors(checklist([item()]));
  assert.equal(hasBlockingQualificationSave(clearEditors), false);
  const conflictedEditors = createQualificationEditors(
    checklist([item({ state: "conflict", answer_value: "Seller changed answer" })]),
  );
  assert.equal(hasBlockingQualificationSave(conflictedEditors), false);
  const savingEditors = {
    ...clearEditors,
    motivation: { ...clearEditors.motivation, saveStatus: "saving" },
  };
  assert.equal(hasBlockingQualificationSave(savingEditors), true);
});

test("reconciling one ambiguous save preserves unrelated local drafts", async () => {
  const {
    createQualificationEditors,
    editQualificationEditor,
    reconcileQualificationEditors,
  } = await importStateModule();
  const initialChecklist = checklist([
    item(),
    item({ question_key: "timeline", label: "Timeline" }),
  ]);
  const initial = createQualificationEditors(initialChecklist);
  const current = {
    motivation: editQualificationEditor(initial.motivation, {
      state: "answered",
      answerValue: "Move closer to family",
      mutationId: "mutation-one",
    }),
    timeline: editQualificationEditor(initial.timeline, {
      state: "answered",
      answerValue: "Within 30 days",
      mutationId: "mutation-two",
    }),
  };
  current.motivation.saveStatus = "error";
  const serverChecklist = {
    ...initialChecklist,
    items: [
      item({ state: "answered", answer_value: "Move closer to family", revision: 1 }),
      item({ question_key: "timeline", label: "Timeline" }),
    ],
  };
  const reconciled = reconcileQualificationEditors(
    current,
    serverChecklist,
    "motivation",
    "retry",
  );
  assert.equal(reconciled.editors.motivation.saveStatus, "saved");
  assert.equal(reconciled.editors.timeline.draftValue, "Within 30 days");
  assert.equal(reconciled.editors.timeline.saveStatus, "dirty");
});

test("qualification overrides are pruned without dropping the retained active attempt", async () => {
  const { pruneQualificationOverrides } = await importStateModule();
  const current = {
    "stale-attempt": { answered_count: 1 },
    "active-attempt": { answered_count: 3 },
    "optimistic-attempt": { answered_count: 2 },
  };
  const pruned = pruneQualificationOverrides(
    current,
    new Set(["active-attempt", "optimistic-attempt"]),
  );
  assert.deepEqual(Object.keys(pruned).sort(), [
    "active-attempt",
    "optimistic-attempt",
  ]);
  assert.equal(
    pruneQualificationOverrides(pruned, new Set(Object.keys(pruned))),
    pruned,
  );
  assert.match(workspaceSource, /optimisticEntryRef\.current\?\.active_attempt/);
});

test("live checklist autosave is lease-aware, stale-safe, and never persisted locally", () => {
  assert.match(checklistSource, /const TEXT_SAVE_DELAY_MS = 600/);
  assert.match(checklistSource, /crypto\.randomUUID/);
  assert.match(checklistSource, /method: "PUT"/);
  assert.match(checklistSource, /buildQualificationMutation\(savingEditor, leaseRef\.current\)/);
  assert.match(checklistSource, /activeAttemptRef\.current !== selectedAttemptId/);
  assert.match(checklistSource, /response\.status/);
  assert.match(checklistSource, /Load saved answer/);
  assert.match(checklistSource, /Reconcile and retry/);
  assert.doesNotMatch(checklistSource, /localStorage|sessionStorage/);
  assert.doesNotMatch(checklistSource, /qualification_answers/);
});

test("workspace uses each entry's pinned script and authoritative checklist", () => {
  assert.match(workspaceSource, /const activeScript = entry\.script/);
  assert.match(workspaceSource, /qualification_answers: \{\}/);
  assert.match(workspaceSource, /<LiveQualificationChecklist/);
  assert.match(workspaceSource, /source_name/);
  assert.match(workspaceSource, /entry\.warnings\.map/);
  assert.doesNotMatch(workspaceSource, /activeScript=\{data\.active_script\}/);
  assert.doesNotMatch(workspaceSource, /const priorAnswers/);
  assert.doesNotMatch(workspaceSource, /defaultValue=\{priorAnswers/);
  assert.match(workspaceSource, /Complete before warm handoff/);
  assert.match(workspaceSource, /canMutateAttempt/);
  assert.match(workspaceSource, /Manager monitoring is read-only/);
  assert.match(workspaceSource, /optimisticEntryRef/);
  assert.doesNotMatch(workspaceSource, /localMutationIsNewer/);
});

test("ownership gates writes while manager monitoring remains navigable", () => {
  assert.match(dialerSource, /onOwnershipChange\(leadership\)/);
  assert.match(
    workspaceSource,
    /entry\?\.assigned_user_id === data\.current_user_id[\s\S]*dialerLeadership === "leader"[\s\S]*!nativeDialerAvailable \|\| dialerLease/,
  );
  assert.match(workspaceSource, /dialerLeadership === "unsupported"/);
  assert.match(workspaceSource, /lockSelectionToCurrentAttempt/);
  assert.match(workspaceSource, /Qualification \{item\.active_attempt\.qualification_checklist\.answered_count\}/);
});

test("mobile puts the call checklist first and uses touch-sized controls", () => {
  assert.match(cssSource, /@media \(max-width: 760px\)[\s\S]*\.scriptPanel \{[\s\S]*order: 1/);
  assert.match(cssSource, /\.outcomePanel \{[\s\S]*order: 2/);
  assert.match(cssSource, /\.prospectPanel \{[\s\S]*order: 3/);
  assert.match(
    cssSource,
    /\.qualificationStateControls button,[\s\S]*\.qualificationItem textarea \{[\s\S]*min-height: 44px/,
  );
});
