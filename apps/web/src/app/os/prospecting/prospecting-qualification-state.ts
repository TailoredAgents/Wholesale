import type {
  ProspectingQualificationChecklist,
  ProspectingQualificationChecklistItem,
  ProspectingQualificationState,
} from "../../lib/api";

export type QualificationSaveStatus =
  | "idle"
  | "dirty"
  | "saving"
  | "saved"
  | "error"
  | "conflict";

export type QualificationEditor = {
  item: ProspectingQualificationChecklistItem;
  draftState: ProspectingQualificationState;
  draftValue: string;
  saveStatus: QualificationSaveStatus;
  errorMessage: string | null;
  editVersion: number;
  pendingEditVersion: number | null;
  mutationId: string;
};

export type QualificationMutation = {
  state: ProspectingQualificationState;
  answer_value: string | null;
  expected_revision: number;
  mutation_id: string;
  browser_session_id: string | null;
  lease_token: string | null;
};

export function normalizeQualificationAnswer(value: string | null | undefined) {
  const normalized = String(value ?? "").trim();
  return normalized || null;
}

export function isConfirmedQualificationAnswer(
  item: ProspectingQualificationChecklistItem,
) {
  const answer = normalizeQualificationAnswer(item.answer_value);
  if (item.state !== "answered" || !answer) return false;
  if (item.answer_type !== "choice") return true;
  return item.choices.includes(answer);
}

export function qualificationValidationMessage(editor: QualificationEditor) {
  const answer = normalizeQualificationAnswer(editor.draftValue);
  if (editor.draftState === "not_covered") return null;
  if (!answer) {
    return editor.draftState === "answered"
      ? "Enter an answer before marking this question answered."
      : "Add a short explanation for this answer state.";
  }
  if (editor.draftState !== "answered") return null;
  if (
    editor.item.answer_type === "choice" &&
    !editor.item.choices.includes(answer)
  ) {
    return "Choose one of the approved script answers.";
  }
  return null;
}

export function createQualificationEditors(
  checklist: ProspectingQualificationChecklist,
) {
  return Object.fromEntries(
    checklist.items.map((item) => [
      item.question_key,
      {
        item,
        draftState: item.state,
        draftValue: item.answer_value ?? "",
        saveStatus: "idle" as const,
        errorMessage: null,
        editVersion: 0,
        pendingEditVersion: null,
        mutationId: "",
      },
    ]),
  ) satisfies Record<string, QualificationEditor>;
}

export function editQualificationEditor(
  editor: QualificationEditor,
  update: {
    state?: ProspectingQualificationState;
    answerValue?: string;
    mutationId: string;
  },
): QualificationEditor {
  return {
    ...editor,
    draftState: update.state ?? editor.draftState,
    draftValue: update.answerValue ?? editor.draftValue,
    saveStatus: editor.saveStatus === "saving" ? "saving" : "dirty",
    errorMessage: null,
    editVersion: editor.editVersion + 1,
    mutationId: update.mutationId,
  };
}

export function beginQualificationSave(editor: QualificationEditor) {
  return {
    ...editor,
    saveStatus: "saving" as const,
    errorMessage: null,
    pendingEditVersion: editor.editVersion,
  };
}

export function applyQualificationSaveSuccess(
  editor: QualificationEditor,
  item: ProspectingQualificationChecklistItem,
) {
  if (item.question_key !== editor.item.question_key) return editor;
  const editedWhileSaving = editor.pendingEditVersion !== editor.editVersion;
  return {
    ...editor,
    item,
    draftState: editedWhileSaving ? editor.draftState : item.state,
    draftValue: editedWhileSaving ? editor.draftValue : item.answer_value ?? "",
    saveStatus: editedWhileSaving ? ("dirty" as const) : ("saved" as const),
    errorMessage: null,
    pendingEditVersion: null,
  };
}

export function applyQualificationSaveFailure(
  editor: QualificationEditor,
  message: string,
  conflict = false,
) {
  return {
    ...editor,
    saveStatus: conflict ? ("conflict" as const) : ("error" as const),
    errorMessage: message,
    pendingEditVersion: null,
  };
}

export function buildQualificationMutation(
  editor: QualificationEditor,
  lease: { browserSessionId: string; leaseToken: string } | null,
): QualificationMutation {
  const validationMessage = qualificationValidationMessage(editor);
  if (validationMessage) throw new Error(validationMessage);
  return {
    state: editor.draftState,
    answer_value:
      editor.draftState === "not_covered"
        ? null
        : normalizeQualificationAnswer(editor.draftValue),
    expected_revision: editor.item.revision,
    mutation_id: editor.mutationId,
    browser_session_id: lease?.browserSessionId ?? null,
    lease_token: lease?.leaseToken ?? null,
  };
}

export function replaceQualificationChecklistItem(
  checklist: ProspectingQualificationChecklist,
  nextItem: ProspectingQualificationChecklistItem,
) {
  const items = checklist.items.map((item) =>
    item.question_key === nextItem.question_key ? nextItem : item,
  );
  const answered = items.filter(isConfirmedQualificationAnswer);
  const required = items.filter((item) => item.is_required);
  const requiredAnswered = required.filter(isConfirmedQualificationAnswer);
  const missingRequiredKeys = required
    .filter((item) => !isConfirmedQualificationAnswer(item))
    .map((item) => item.question_key);
  return {
    ...checklist,
    items,
    answered_count: answered.length,
    total_count: items.length,
    required_answered_count: requiredAnswered.length,
    required_count: required.length,
    missing_required_keys: missingRequiredKeys,
    complete: missingRequiredKeys.length === 0,
  };
}

export function reconcileQualificationEditors(
  current: Record<string, QualificationEditor>,
  checklist: ProspectingQualificationChecklist,
  focusQuestionKey: string,
  mode: "retry" | "discard",
) {
  const fresh = createQualificationEditors(checklist);
  let focusNeedsSave = false;
  const editors = Object.fromEntries(
    checklist.items.map((item) => {
      const existing = current[item.question_key];
      if (!existing) return [item.question_key, fresh[item.question_key]];
      if (item.question_key === focusQuestionKey) {
        if (mode === "discard") return [item.question_key, fresh[item.question_key]];
        const serverMatchesDraft =
          existing.draftState === item.state &&
          normalizeQualificationAnswer(existing.draftValue) ===
            normalizeQualificationAnswer(item.answer_value);
        if (serverMatchesDraft) {
          return [
            item.question_key,
            { ...fresh[item.question_key], saveStatus: "saved" as const },
          ];
        }
        focusNeedsSave = true;
        return [
          item.question_key,
          {
            ...existing,
            item,
            saveStatus: "dirty" as const,
            errorMessage: null,
            pendingEditVersion: null,
          },
        ];
      }
      const preserveDraft = ["dirty", "saving", "error", "conflict"].includes(
        existing.saveStatus,
      );
      return [
        item.question_key,
        preserveDraft ? { ...existing, item } : fresh[item.question_key],
      ];
    }),
  ) as Record<string, QualificationEditor>;
  return { editors, focusNeedsSave };
}

export function hasBlockingQualificationSave(
  editors: Record<string, QualificationEditor>,
) {
  return Object.values(editors).some((editor) =>
    ["dirty", "saving", "error", "conflict"].includes(editor.saveStatus),
  );
}

export function pruneQualificationOverrides<T>(
  current: Record<string, T>,
  retainedAttemptIds: ReadonlySet<string>,
) {
  const entries = Object.entries(current).filter(([attemptId]) =>
    retainedAttemptIds.has(attemptId),
  );
  return entries.length === Object.keys(current).length
    ? current
    : (Object.fromEntries(entries) as Record<string, T>);
}
