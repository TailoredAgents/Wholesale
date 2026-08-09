"use client";

import { useAuth } from "@clerk/nextjs";
import { useId, useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import type { LeadCloseOutResponse, LeadReopenResponse } from "../../lib/api";
import { Button, Dialog, FormField, TextArea, TextInput } from "../_components/design-system";
import styles from "./lifecycle.module.css";

type Status = "idle" | "working" | "error";
type CloseOutDisposition = "dead" | "disqualified";

const closedStages = new Set(["dead", "disqualified"]);

function localDateTimeValue(value: Date) {
  const localValue = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return localValue.toISOString().slice(0, 16);
}

async function responseError(response: Response, fallback: string) {
  const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function useLeadLifecycleApi() {
  const { getToken } = useAuth();
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  return async function request(path: string, init: RequestInit) {
    const token = await getToken().catch(() => null);
    const headers = new Headers(init.headers);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    } else {
      headers.set("X-Dev-User-Email", devUserEmail);
    }
    return fetch(`${apiBaseUrl}${path}`, { ...init, headers });
  };
}

export function LeadReopenControl({
  canEditLead,
  compact = false,
  leadId,
}: {
  canEditLead: boolean;
  compact?: boolean;
  leadId: string;
}) {
  const router = useRouter();
  const request = useLeadLifecycleApi();
  const formId = useId();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [nextActionTitle, setNextActionTitle] = useState("Follow up with reopened lead");
  const [nextActionDueAt, setNextActionDueAt] = useState("");
  const [minimumNextAction, setMinimumNextAction] = useState("");

  function openDialog() {
    const now = new Date();
    const minimum = new Date(now.getTime() + 5 * 60_000);
    const suggested = new Date(now.getTime() + 24 * 60 * 60_000);
    suggested.setMinutes(Math.ceil(suggested.getMinutes() / 5) * 5, 0, 0);
    setMinimumNextAction(localDateTimeValue(minimum));
    setNextActionDueAt(localDateTimeValue(suggested));
    setReason("");
    setNextActionTitle("Follow up with reopened lead");
    setError("");
    setStatus("idle");
    setOpen(true);
  }

  function closeDialog() {
    if (status === "working") return;
    setOpen(false);
    setError("");
  }

  async function reopenLead(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedReason = reason.trim();
    const normalizedTitle = nextActionTitle.trim();
    const dueAt = new Date(nextActionDueAt);
    if (normalizedReason.length < 10) {
      setStatus("error");
      setError("Explain why the lead is being reopened in at least 10 characters.");
      return;
    }
    if (normalizedTitle.length < 3) {
      setStatus("error");
      setError("Enter a clear title for the next action.");
      return;
    }
    if (Number.isNaN(dueAt.getTime()) || dueAt.getTime() <= Date.now()) {
      setStatus("error");
      setError("Schedule the next action for a future date and time.");
      return;
    }

    setStatus("working");
    setError("");
    try {
      const response = await request(`/api/v1/leads/${leadId}/reopen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: normalizedReason,
          next_action_due_at: dueAt.toISOString(),
          next_action_title: normalizedTitle,
        }),
      });
      if (!response.ok) {
        throw new Error(await responseError(response, "The lead could not be reopened."));
      }
      await response.json() as LeadReopenResponse;
      setOpen(false);
      router.push(`/os/leads/${leadId}?returnTo=${encodeURIComponent("/os/leads")}`);
      router.refresh();
    } catch (caught) {
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "The lead could not be reopened.");
    }
  }

  if (!canEditLead) {
    return (
      <span
        className={styles.readOnly}
        title="Your role can view this lead but cannot reopen it."
      >
        Read only
      </span>
    );
  }

  return (
    <div className={compact ? styles.compact : styles.actions}>
      <button
        className={styles.restoreButton}
        disabled={status === "working"}
        onClick={openDialog}
        type="button"
      >
        Reopen lead
      </button>

      <Dialog
        description="Reopening restores the lead to the active pipeline and creates a required follow-up task."
        footer={
          <>
            <Button disabled={status === "working"} onClick={closeDialog} type="button" variant="quiet">
              Cancel
            </Button>
            <Button form={formId} loading={status === "working"} type="submit">
              Reopen lead
            </Button>
          </>
        }
        onClose={closeDialog}
        open={open}
        title="Reopen this lead?"
      >
        <form className={styles.lifecycleForm} id={formId} onSubmit={reopenLead}>
          <FormField
            hint="This explanation is saved in the lead's activity and audit history."
            htmlFor={`${formId}-reason`}
            label="Reason for reopening"
          >
            <TextArea
              aria-describedby={`${formId}-reason-hint`}
              autoFocus
              id={`${formId}-reason`}
              maxLength={500}
              minLength={10}
              onChange={(event) => setReason(event.target.value)}
              required
              rows={3}
              value={reason}
            />
          </FormField>
          <FormField htmlFor={`${formId}-title`} label="Next action">
            <TextInput
              id={`${formId}-title`}
              maxLength={255}
              minLength={3}
              onChange={(event) => setNextActionTitle(event.target.value)}
              required
              value={nextActionTitle}
            />
          </FormField>
          <FormField
            hint="The lead will immediately return to active work, so it cannot be left without a follow-up."
            htmlFor={`${formId}-due-at`}
            label="Next action due"
          >
            <TextInput
              aria-describedby={`${formId}-due-at-hint`}
              id={`${formId}-due-at`}
              min={minimumNextAction}
              onChange={(event) => setNextActionDueAt(event.target.value)}
              required
              type="datetime-local"
              value={nextActionDueAt}
            />
          </FormField>
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
        </form>
      </Dialog>
    </div>
  );
}

export function LeadLifecycleActions({
  leadId,
  archived,
  canArchiveRecords,
  canEditLead,
  stageKey,
  compact = false,
}: {
  leadId: string;
  archived: boolean;
  canArchiveRecords: boolean;
  canEditLead: boolean;
  stageKey?: string;
  compact?: boolean;
}) {
  const router = useRouter();
  const request = useLeadLifecycleApi();
  const closeOutFormId = useId();
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [closeOutOpen, setCloseOutOpen] = useState(false);
  const [archiveConfirmationOpen, setArchiveConfirmationOpen] = useState(false);
  const [deleteConfirmationOpen, setDeleteConfirmationOpen] = useState(false);
  const [disposition, setDisposition] = useState<CloseOutDisposition>("dead");
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const isClosedLead = archived && Boolean(stageKey && closedStages.has(stageKey));

  function closeDialog(setOpen: (value: boolean) => void) {
    if (status === "working") return;
    setOpen(false);
    setStatus("idle");
    setError("");
  }

  async function closeOutLead(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedReason = reason.trim();
    if (normalizedReason.length < 10) {
      setStatus("error");
      setError("Explain why this lead is being closed in at least 10 characters.");
      return;
    }

    setStatus("working");
    setError("");
    try {
      const response = await request(`/api/v1/leads/${leadId}/close-out`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ disposition, reason: normalizedReason }),
      });
      if (!response.ok) {
        throw new Error(await responseError(response, "The lead could not be closed out."));
      }
      await response.json() as LeadCloseOutResponse;
      setCloseOutOpen(false);
      router.push("/os/leads/closed");
      router.refresh();
    } catch (caught) {
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "The lead could not be closed out.");
    }
  }

  async function runAdministrativeAction(action: "archive" | "restore" | "delete") {
    setStatus("working");
    setError("");
    try {
      const path =
        action === "archive"
          ? `/api/v1/leads/${leadId}`
          : action === "restore"
            ? `/api/v1/leads/${leadId}/restore`
            : `/api/v1/leads/${leadId}/permanent?confirmation=DELETE`;
      const response = await request(path, {
        method: action === "restore" ? "POST" : "DELETE",
      });
      if (!response.ok) {
        throw new Error(await responseError(response, "The lead lifecycle action failed."));
      }

      setArchiveConfirmationOpen(false);
      setDeleteConfirmationOpen(false);
      setConfirmation("");
      if (action === "archive" || action === "delete") {
        router.push(action === "archive" ? "/os/leads" : "/os/leads/archived");
      } else {
        router.push(`/os/leads/${leadId}`);
      }
      router.refresh();
      setStatus("idle");
    } catch (caught) {
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "The lead lifecycle action failed.");
    }
  }

  if (isClosedLead) {
    return <LeadReopenControl canEditLead={canEditLead} compact={compact} leadId={leadId} />;
  }

  const hasAvailableAction = archived ? canArchiveRecords : canEditLead || canArchiveRecords;

  if (!hasAvailableAction) {
    return (
      <span
        className={styles.readOnly}
        title="Your role can view this lead but cannot change its lifecycle."
      >
        Read only
      </span>
    );
  }

  return (
    <div className={compact ? styles.compact : styles.actions}>
      {archived && canArchiveRecords ? (
        <>
          <button
            className={styles.restoreButton}
            disabled={status === "working"}
            onClick={() => runAdministrativeAction("restore")}
            type="button"
          >
            Restore
          </button>
          <button
            className={styles.deleteButton}
            disabled={status === "working"}
            onClick={() => {
              setError("");
              setStatus("idle");
              setConfirmation("");
              setDeleteConfirmationOpen(true);
            }}
            type="button"
          >
            Permanently delete
          </button>
        </>
      ) : !archived ? (
        <>
          {canEditLead ? (
            <button
              className={styles.closeOutButton}
              disabled={status === "working"}
              onClick={() => {
                setError("");
                setStatus("idle");
                setDisposition("dead");
                setReason("");
                setCloseOutOpen(true);
              }}
              type="button"
            >
              Close out lead
            </button>
          ) : null}
          {canArchiveRecords ? (
            <button
              className={styles.archiveButton}
              disabled={status === "working"}
              onClick={() => {
                setError("");
                setStatus("idle");
                setArchiveConfirmationOpen(true);
              }}
              type="button"
            >
              Administrative archive
            </button>
          ) : null}
        </>
      ) : null}

      {!closeOutOpen && !archiveConfirmationOpen && !deleteConfirmationOpen && error ? (
        <p className={styles.error} role="alert">{error}</p>
      ) : null}

      <Dialog
        description="Closing a lead stops routine seller work while preserving the complete record as read-only history."
        footer={
          <>
            <Button disabled={status === "working"} onClick={() => closeDialog(setCloseOutOpen)} type="button" variant="quiet">
              Cancel
            </Button>
            <Button form={closeOutFormId} loading={status === "working"} type="submit" variant="danger">
              Close out lead
            </Button>
          </>
        }
        onClose={() => closeDialog(setCloseOutOpen)}
        open={closeOutOpen}
        title="Close out this lead?"
      >
        <form className={styles.lifecycleForm} id={closeOutFormId} onSubmit={closeOutLead}>
          <fieldset className={styles.dispositionChoices}>
            <legend>Choose a disposition</legend>
            <label className={disposition === "dead" ? styles.dispositionSelected : undefined}>
              <input
                autoFocus
                checked={disposition === "dead"}
                name={`${closeOutFormId}-disposition`}
                onChange={() => setDisposition("dead")}
                type="radio"
                value="dead"
              />
              <span>
                <strong>Dead</strong>
                <small>A legitimate seller opportunity that is no longer moving forward.</small>
              </span>
            </label>
            <label className={disposition === "disqualified" ? styles.dispositionSelected : undefined}>
              <input
                checked={disposition === "disqualified"}
                name={`${closeOutFormId}-disposition`}
                onChange={() => setDisposition("disqualified")}
                type="radio"
                value="disqualified"
              />
              <span>
                <strong>Disqualified</strong>
                <small>Spam, invalid information, no authority, wrong market, or unusable lead.</small>
              </span>
            </label>
          </fieldset>
          <FormField
            hint="Be specific. The reason is saved in recent activity and the audit history."
            htmlFor={`${closeOutFormId}-reason`}
            label="Close-out reason"
          >
            <TextArea
              aria-describedby={`${closeOutFormId}-reason-hint`}
              id={`${closeOutFormId}-reason`}
              maxLength={500}
              minLength={10}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Example: Seller already sold the property to another buyer."
              required
              rows={4}
              value={reason}
            />
          </FormField>
          <div className={styles.closeOutImpact}>
            <strong>This will automatically:</strong>
            <ul>
              <li>Cancel open follow-ups, reminders, calling-list work, and appointments.</li>
              <li>Cancel every pending approval tied to this lead.</li>
              <li>Retire pending or approved offer plans and unused offer concessions.</li>
              <li>Close the Lead Queue case and Inbox conversation.</li>
              <li>Move the record to Closed Leads with its full read-only history.</li>
            </ul>
            <p>
              Cancel or resolve active deal, contract, and disposition work first. A funded deal
              remains a completed success and cannot be closed as dead or disqualified.
            </p>
          </div>
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
        </form>
      </Dialog>

      <Dialog
        description="Use Administrative archive only for confirmed duplicate or test records; never for a real seller opportunity."
        footer={
          <>
            <Button disabled={status === "working"} onClick={() => closeDialog(setArchiveConfirmationOpen)} type="button" variant="quiet">
              Cancel
            </Button>
            <Button disabled={status === "working"} onClick={() => runAdministrativeAction("archive")} type="button">
              {status === "working" ? "Archiving..." : "Archive record"}
            </Button>
          </>
        }
        onClose={() => closeDialog(setArchiveConfirmationOpen)}
        open={archiveConfirmationOpen}
        title="Administratively archive this record?"
      >
        <p className={styles.dialogCopy}>The duplicate or test record remains available under Archived with read-only history, restoration, and confirmed test-data deletion controls.</p>
        {error ? <p className={styles.error} role="alert">{error}</p> : null}
      </Dialog>

      <Dialog
        description="This removes the seller record and its operational history. This cannot be undone."
        footer={
          <>
            <Button disabled={status === "working"} onClick={() => closeDialog(setDeleteConfirmationOpen)} type="button" variant="quiet">
              Cancel
            </Button>
            <Button disabled={confirmation !== "DELETE"} loading={status === "working"} onClick={() => runAdministrativeAction("delete")} type="button" variant="danger">
              Permanently delete
            </Button>
          </>
        }
        onClose={() => closeDialog(setDeleteConfirmationOpen)}
        open={deleteConfirmationOpen}
        title="Permanently delete this lead?"
      >
        <FormField htmlFor={`delete-confirmation-${leadId}`} label="Type DELETE to confirm">
          <TextInput
            autoComplete="off"
            id={`delete-confirmation-${leadId}`}
            onChange={(event) => setConfirmation(event.target.value)}
            value={confirmation}
          />
        </FormField>
        {error ? <p className={styles.error} role="alert">{error}</p> : null}
      </Dialog>
    </div>
  );
}
