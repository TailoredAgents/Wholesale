"use client";

import { useAuth } from "@clerk/nextjs";
import { AlertTriangle, Check, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  ProspectingQualificationChecklist,
  ProspectingQualificationChecklistItem,
  ProspectingQualificationState,
} from "../../lib/api";
import type { ActiveProspectingDialerLease } from "./prospecting-dialer";
import {
  applyQualificationSaveFailure,
  applyQualificationSaveSuccess,
  beginQualificationSave,
  buildQualificationMutation,
  createQualificationEditors,
  editQualificationEditor,
  hasBlockingQualificationSave,
  isConfirmedQualificationAnswer,
  qualificationValidationMessage,
  reconcileQualificationEditors,
  replaceQualificationChecklistItem,
  type QualificationEditor,
} from "./prospecting-qualification-state";
import styles from "./prospecting.module.css";

const TEXT_SAVE_DELAY_MS = 600;

function newMutationId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error("This browser cannot safely identify an answer save.");
  }
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

function visualState(item: ProspectingQualificationChecklistItem) {
  if (item.state === "answered") {
    return isConfirmedQualificationAnswer(item) ? "answered" : "not_covered";
  }
  return item.state;
}

function stateClass(state: ProspectingQualificationState) {
  if (state === "answered") return styles.qualificationAnswered;
  if (state === "needs_follow_up") return styles.qualificationFollowUp;
  if (state === "conflict") return styles.qualificationConflict;
  return styles.qualificationNotCovered;
}

function stateLabel(state: ProspectingQualificationState) {
  if (state === "answered") return "Answered";
  if (state === "needs_follow_up") return "Needs follow-up";
  if (state === "conflict") return "Conflict";
  return "Not covered";
}

export function ProspectingQualificationChecklist({
  attemptId,
  canAutosave,
  checklist,
  lease,
  onBlockingChange,
  onChecklistChange,
}: {
  attemptId: string;
  canAutosave: boolean;
  checklist: ProspectingQualificationChecklist;
  lease: ActiveProspectingDialerLease | null;
  onBlockingChange: (blocked: boolean) => void;
  onChecklistChange: (
    attemptId: string,
    checklist: ProspectingQualificationChecklist,
  ) => void;
}) {
  const { getToken } = useAuth();
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );
  const [editors, setEditors] = useState<Record<string, QualificationEditor>>(
    () => createQualificationEditors(checklist),
  );
  const editorsRef = useRef(editors);
  const checklistRef = useRef(checklist);
  const leaseRef = useRef(lease);
  const canAutosaveRef = useRef(canAutosave);
  const activeAttemptRef = useRef(attemptId);
  const initializedAttemptRef = useRef(attemptId);
  const mountedRef = useRef(true);
  const timersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const replaceEditors = useCallback(
    (
      update: (
        current: Record<string, QualificationEditor>,
      ) => Record<string, QualificationEditor>,
    ) => {
      const next = update(editorsRef.current);
      editorsRef.current = next;
      setEditors(next);
    },
    [],
  );

  leaseRef.current = lease;
  canAutosaveRef.current = canAutosave;

  useEffect(() => {
    mountedRef.current = true;
    const timers = timersRef.current;
    return () => {
      mountedRef.current = false;
      for (const timer of timers.values()) clearTimeout(timer);
      timers.clear();
      onBlockingChange(false);
    };
  }, [onBlockingChange]);

  useEffect(() => {
    activeAttemptRef.current = attemptId;
    checklistRef.current = checklist;
    if (initializedAttemptRef.current !== attemptId) {
      initializedAttemptRef.current = attemptId;
      const nextEditors = createQualificationEditors(checklist);
      editorsRef.current = nextEditors;
      setEditors(nextEditors);
      return;
    }
    replaceEditors((current) =>
      Object.fromEntries(
        checklist.items.map((item) => {
          const editor = current[item.question_key];
          if (!editor) {
            return [
              item.question_key,
              createQualificationEditors({ ...checklist, items: [item] })[
                item.question_key
              ],
            ];
          }
          const preserveDraft = ["dirty", "saving", "error", "conflict"].includes(
            editor.saveStatus,
          );
          return [
            item.question_key,
            {
              ...editor,
              item,
              draftState: preserveDraft ? editor.draftState : item.state,
              draftValue: preserveDraft
                ? editor.draftValue
                : item.answer_value ?? "",
            },
          ];
        }),
      ),
    );
  }, [attemptId, checklist, replaceEditors]);

  useEffect(() => {
    onBlockingChange(hasBlockingQualificationSave(editors));
  }, [editors, onBlockingChange]);

  const requestHeaders = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    return headers;
  }, [devUserEmail, getToken]);

  const saveQuestion = useCallback(
    async (questionKey: string) => {
      const selectedAttemptId = activeAttemptRef.current;
      if (selectedAttemptId !== attemptId || !mountedRef.current) return;
      const editor = editorsRef.current[questionKey];
      if (!editor || editor.saveStatus === "saving") return;
      if (editor.saveStatus === "idle" || editor.saveStatus === "saved") return;
      if (!canAutosaveRef.current) {
        replaceEditors((current) => ({
          ...current,
          [questionKey]: applyQualificationSaveFailure(
            current[questionKey],
            "This tab is read-only because it does not own the active calling session.",
          ),
        }));
        return;
      }
      const validationMessage = qualificationValidationMessage(editor);
      if (validationMessage) {
        replaceEditors((current) => ({
          ...current,
          [questionKey]: applyQualificationSaveFailure(
            current[questionKey],
            validationMessage,
          ),
        }));
        return;
      }
      const editorWithMutation = editor.mutationId
        ? editor
        : editQualificationEditor(editor, { mutationId: newMutationId() });
      const savingEditor = beginQualificationSave(editorWithMutation);
      replaceEditors((current) => ({ ...current, [questionKey]: savingEditor }));
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/prospecting/attempts/${attemptId}/qualification/${encodeURIComponent(questionKey)}`,
          {
            method: "PUT",
            headers: await requestHeaders(),
            body: JSON.stringify(
              buildQualificationMutation(savingEditor, leaseRef.current),
            ),
          },
        );
        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as
            | { detail?: string }
            | null;
          const error = new Error(
            payload?.detail ?? "The answer could not be saved.",
          ) as Error & { status?: number };
          error.status = response.status;
          throw error;
        }
        const savedItem =
          (await response.json()) as ProspectingQualificationChecklistItem;
        if (
          !mountedRef.current ||
          activeAttemptRef.current !== selectedAttemptId ||
          activeAttemptRef.current !== attemptId
        ) {
          return;
        }
        const nextChecklist = replaceQualificationChecklistItem(
          checklistRef.current,
          savedItem,
        );
        checklistRef.current = nextChecklist;
        let shouldSaveLatestEdit = false;
        replaceEditors((current) => {
          const nextEditor = applyQualificationSaveSuccess(
            current[questionKey],
            savedItem,
          );
          shouldSaveLatestEdit = nextEditor.saveStatus === "dirty";
          return { ...current, [questionKey]: nextEditor };
        });
        onChecklistChange(attemptId, nextChecklist);
        if (shouldSaveLatestEdit) {
          window.setTimeout(() => void saveQuestion(questionKey), 0);
        }
      } catch (error) {
        if (
          !mountedRef.current ||
          activeAttemptRef.current !== selectedAttemptId ||
          activeAttemptRef.current !== attemptId
        ) {
          return;
        }
        const status = (error as Error & { status?: number }).status;
        replaceEditors((current) => ({
          ...current,
          [questionKey]: applyQualificationSaveFailure(
            current[questionKey],
            error instanceof Error ? error.message : "The answer could not be saved.",
            status === 409,
          ),
        }));
      }
    },
    [
      apiBaseUrl,
      attemptId,
      onChecklistChange,
      replaceEditors,
      requestHeaders,
    ],
  );

  const scheduleTextSave = useCallback(
    (questionKey: string) => {
      const existing = timersRef.current.get(questionKey);
      if (existing) clearTimeout(existing);
      const timer = setTimeout(() => {
        timersRef.current.delete(questionKey);
        void saveQuestion(questionKey);
      }, TEXT_SAVE_DELAY_MS);
      timersRef.current.set(questionKey, timer);
    },
    [saveQuestion],
  );

  const editQuestion = useCallback(
    (
      questionKey: string,
      update: { state?: ProspectingQualificationState; answerValue?: string },
      save: "debounce" | "now",
    ) => {
      if (!canAutosave) return;
      const existing = timersRef.current.get(questionKey);
      if (existing) {
        clearTimeout(existing);
        timersRef.current.delete(questionKey);
      }
      replaceEditors((current) => ({
        ...current,
        [questionKey]: editQualificationEditor(current[questionKey], {
          ...update,
          mutationId: newMutationId(),
        }),
      }));
      if (save === "debounce") scheduleTextSave(questionKey);
      else window.setTimeout(() => void saveQuestion(questionKey), 0);
    },
    [canAutosave, replaceEditors, saveQuestion, scheduleTextSave],
  );

  const reconcileSavedChecklist = useCallback(async (
    questionKey: string,
    mode: "retry" | "discard",
  ) => {
    const selectedAttemptId = activeAttemptRef.current;
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/attempts/${attemptId}/qualification`,
        { headers: await requestHeaders() },
      );
      if (!response.ok) throw new Error("The latest saved answers could not be loaded.");
      const nextChecklist =
        (await response.json()) as ProspectingQualificationChecklist;
      if (
        !mountedRef.current ||
        activeAttemptRef.current !== selectedAttemptId ||
        activeAttemptRef.current !== attemptId
      ) {
        return;
      }
      checklistRef.current = nextChecklist;
      let focusNeedsSave = false;
      replaceEditors((current) => {
        const reconciled = reconcileQualificationEditors(
          current,
          nextChecklist,
          questionKey,
          mode,
        );
        focusNeedsSave = reconciled.focusNeedsSave;
        return reconciled.editors;
      });
      onChecklistChange(attemptId, nextChecklist);
      if (mode === "retry" && focusNeedsSave) {
        window.setTimeout(() => void saveQuestion(questionKey), 0);
      }
    } catch (error) {
      replaceEditors((current) => ({
        ...current,
        [questionKey]: applyQualificationSaveFailure(
          current[questionKey],
          error instanceof Error
            ? error.message
            : "The latest saved answer could not be loaded.",
          current[questionKey].saveStatus === "conflict",
        ),
      }));
    }
  }, [
    apiBaseUrl,
    attemptId,
    onChecklistChange,
    replaceEditors,
    requestHeaders,
    saveQuestion,
  ]);

  const currentChecklist = checklistRef.current;
  const progressLabel = `${currentChecklist.answered_count} of ${currentChecklist.total_count} questions answered`;
  const missingRequiredLabels = currentChecklist.missing_required_keys.map(
    (key) =>
      currentChecklist.items.find((item) => item.question_key === key)?.label ?? key,
  );

  return (
    <section
      aria-labelledby={`qualification-title-${attemptId}`}
      className={styles.qualificationChecklist}
    >
      <header>
        <div>
          <span>Live qualification</span>
          <h3 id={`qualification-title-${attemptId}`}>Cover each seller question</h3>
        </div>
        <strong aria-label={progressLabel}>
          {currentChecklist.answered_count}/{currentChecklist.total_count}
        </strong>
      </header>
      <progress
        aria-label={progressLabel}
        max={Math.max(currentChecklist.total_count, 1)}
        value={currentChecklist.answered_count}
      />
      <p className={styles.qualificationRequiredProgress}>
        <strong>
          Required {currentChecklist.required_answered_count}/
          {currentChecklist.required_count}
        </strong>
        {missingRequiredLabels.length
          ? `Missing for handoff: ${missingRequiredLabels.join(", ")}`
          : "All required questions are covered for a warm handoff."}
      </p>
      {!canAutosave ? (
        <p className={styles.qualificationReadOnly} role="status">
          Only the assigned caller in the tab that owns the active session can edit
          this checklist.
        </p>
      ) : null}
      <div className={styles.qualificationItems}>
        {currentChecklist.items.map((item, index) => {
          const editor = editors[item.question_key];
          if (!editor) return null;
          const confirmedState = visualState(editor.item);
          const usesExplanationInput = ["needs_follow_up", "conflict"].includes(
            editor.draftState,
          );
          const statusId = `qualification-status-${attemptId}-${item.question_key}`;
          const inputId = `qualification-answer-${attemptId}-${item.question_key}`;
          return (
            <fieldset
              className={`${styles.qualificationItem} ${stateClass(confirmedState)}`}
              disabled={!canAutosave}
              key={item.question_key}
            >
              <legend>
                <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <strong>{item.label}</strong>
                {item.is_required ? <em>Required</em> : null}
              </legend>
              <p>{item.prompt}</p>
              <label htmlFor={inputId}>
                {usesExplanationInput ? "Follow-up or conflict context" : "Seller response"}
              </label>
              {item.answer_type === "choice" && !usesExplanationInput ? (
                <select
                  aria-describedby={statusId}
                  id={inputId}
                  onChange={(event) =>
                    editQuestion(
                      item.question_key,
                      {
                        answerValue: event.target.value,
                        state: event.target.value ? "answered" : "not_covered",
                      },
                      "now",
                    )
                  }
                  value={editor.draftValue}
                >
                  <option value="">Select an approved answer</option>
                  {item.choices.map((choice) => (
                    <option key={choice} value={choice}>{choice}</option>
                  ))}
                </select>
              ) : (
                <textarea
                  aria-describedby={statusId}
                  id={inputId}
                  onBlur={() => {
                    const timer = timersRef.current.get(item.question_key);
                    if (timer) clearTimeout(timer);
                    timersRef.current.delete(item.question_key);
                    void saveQuestion(item.question_key);
                  }}
                  onChange={(event) =>
                    editQuestion(
                      item.question_key,
                      {
                        answerValue: event.target.value,
                        state: usesExplanationInput
                          ? editor.draftState
                          : event.target.value.trim()
                            ? "answered"
                            : "not_covered",
                      },
                      "debounce",
                    )
                  }
                  maxLength={2000}
                  placeholder={
                    usesExplanationInput
                      ? "Explain what needs follow-up or which answers conflict"
                      : "Enter only what the seller tells you"
                  }
                  rows={2}
                  value={editor.draftValue}
                />
              )}
              <div
                aria-label={`${item.label} answer state`}
                className={styles.qualificationStateControls}
                role="group"
              >
                <button
                  aria-pressed={editor.draftState === "answered"}
                  onClick={() =>
                    editQuestion(
                      item.question_key,
                      {
                        state: "answered",
                        answerValue:
                          item.answer_type === "choice" &&
                          !item.choices.includes(editor.draftValue)
                            ? ""
                            : editor.draftValue,
                      },
                      "now",
                    )
                  }
                  type="button"
                >
                  Answered
                </button>
                <button
                  aria-pressed={editor.draftState === "needs_follow_up"}
                  onClick={() =>
                    editQuestion(
                      item.question_key,
                      {
                        state: "needs_follow_up",
                        answerValue:
                          item.answer_type === "choice" ? "" : editor.draftValue,
                      },
                      "now",
                    )
                  }
                  type="button"
                >
                  Follow up
                </button>
                <button
                  aria-pressed={editor.draftState === "conflict"}
                  onClick={() =>
                    editQuestion(
                      item.question_key,
                      {
                        state: "conflict",
                        answerValue:
                          item.answer_type === "choice" ? "" : editor.draftValue,
                      },
                      "now",
                    )
                  }
                  type="button"
                >
                  Conflicting answer
                </button>
                <button
                  aria-pressed={editor.draftState === "not_covered"}
                  onClick={() =>
                    editQuestion(
                      item.question_key,
                      { state: "not_covered", answerValue: "" },
                      "now",
                    )
                  }
                  type="button"
                >
                  Clear
                </button>
              </div>
              <div className={styles.qualificationSaveState} id={statusId}>
                <span className={styles.qualificationStateBadge}>
                  {confirmedState === "answered" ? <Check aria-hidden="true" size={13} /> : null}
                  {confirmedState === "needs_follow_up" || confirmedState === "conflict" ? (
                    <AlertTriangle aria-hidden="true" size={13} />
                  ) : null}
                  {stateLabel(confirmedState)}
                </span>
                {editor.saveStatus === "saving" ? <small role="status">Saving...</small> : null}
                {editor.saveStatus === "dirty" ? <small role="status">Waiting to save...</small> : null}
                {editor.saveStatus === "saved" ? <small role="status">Saved</small> : null}
                {editor.saveStatus === "error" ? (
                  <small role="alert">{editor.errorMessage}</small>
                ) : null}
                {editor.saveStatus === "conflict" ? (
                  <small role="alert">{editor.errorMessage}</small>
                ) : null}
                {editor.saveStatus === "error" ? (
                  <button onClick={() => void reconcileSavedChecklist(item.question_key, "retry")} type="button">
                    <RefreshCw aria-hidden="true" size={13} /> Reconcile and retry
                  </button>
                ) : null}
                {editor.saveStatus === "conflict" ? (
                  <button onClick={() => void reconcileSavedChecklist(item.question_key, "discard")} type="button">
                    <RefreshCw aria-hidden="true" size={13} /> Load saved answer
                  </button>
                ) : null}
              </div>
            </fieldset>
          );
        })}
      </div>
    </section>
  );
}
