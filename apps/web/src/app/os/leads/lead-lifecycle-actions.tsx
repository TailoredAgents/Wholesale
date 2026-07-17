"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "./lifecycle.module.css";

type Status = "idle" | "working" | "error";

export function LeadLifecycleActions({
  leadId,
  archived,
  compact = false,
}: {
  leadId: string;
  archived: boolean;
  compact?: boolean;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const [archiveConfirmationOpen, setArchiveConfirmationOpen] = useState(false);
  const [deleteConfirmationOpen, setDeleteConfirmationOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function headers(): Promise<Record<string, string>> {
    const token = await getToken().catch(() => null);
    return token
      ? { Authorization: `Bearer ${token}` }
      : { "X-Dev-User-Email": devUserEmail };
  }

  async function runAction(action: "archive" | "restore" | "delete") {
    setStatus("working");
    try {
      const path =
        action === "archive"
          ? `/api/v1/leads/${leadId}`
          : action === "restore"
            ? `/api/v1/leads/${leadId}/restore`
            : `/api/v1/leads/${leadId}/permanent?confirmation=DELETE`;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method: action === "restore" ? "POST" : "DELETE",
        headers: await headers(),
      });
      if (!response.ok) {
        throw new Error("Lead lifecycle action failed.");
      }

      setArchiveConfirmationOpen(false);
      setDeleteConfirmationOpen(false);
      setConfirmation("");
      if (action === "archive") {
        router.push("/os/leads");
      } else if (action === "delete") {
        router.push("/os/leads/archived");
      }
      router.refresh();
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className={compact ? styles.compact : styles.actions}>
      {archived ? (
        <>
          <button
            className={styles.restoreButton}
            disabled={status === "working"}
            onClick={() => runAction("restore")}
            type="button"
          >
            Restore
          </button>
          <button
            className={styles.deleteButton}
            disabled={status === "working"}
            onClick={() => setDeleteConfirmationOpen(true)}
            type="button"
          >
            Permanently delete
          </button>
        </>
      ) : (
        <button
          className={styles.archiveButton}
          disabled={status === "working"}
          onClick={() => setArchiveConfirmationOpen(true)}
          type="button"
        >
          Archive lead
        </button>
      )}

      {status === "error" ? <p className={styles.error}>Action failed. Please try again.</p> : null}

      {archiveConfirmationOpen ? (
        <div className={styles.backdrop} role="presentation">
          <section aria-labelledby="archive-title" aria-modal="true" className={styles.dialog} role="dialog">
            <h2 id="archive-title">Archive this lead?</h2>
            <p>It will leave active lists and work queues. You can restore it later.</p>
            <div className={styles.dialogActions}>
              <button onClick={() => setArchiveConfirmationOpen(false)} type="button">
                Cancel
              </button>
              <button
                className={styles.archiveButton}
                disabled={status === "working"}
                onClick={() => runAction("archive")}
                type="button"
              >
                {status === "working" ? "Archiving..." : "Archive lead"}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {deleteConfirmationOpen ? (
        <div className={styles.backdrop} role="presentation">
          <section aria-labelledby="delete-title" aria-modal="true" className={styles.dialog} role="dialog">
            <h2 id="delete-title">Permanently delete this lead?</h2>
            <p>This removes the seller record and its operational history. This cannot be undone.</p>
            <label>
              <span>Type DELETE to confirm</span>
              <input
                autoComplete="off"
                onChange={(event) => setConfirmation(event.target.value)}
                value={confirmation}
              />
            </label>
            <div className={styles.dialogActions}>
              <button onClick={() => setDeleteConfirmationOpen(false)} type="button">
                Cancel
              </button>
              <button
                className={styles.deleteButton}
                disabled={confirmation !== "DELETE" || status === "working"}
                onClick={() => runAction("delete")}
                type="button"
              >
                {status === "working" ? "Deleting..." : "Permanently delete"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
