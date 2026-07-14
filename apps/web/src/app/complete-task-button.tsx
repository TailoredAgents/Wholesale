"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "./page.module.css";

type Status = "idle" | "saving" | "error";

export function CompleteTaskButton({ taskId }: { taskId: string }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function completeTask() {
    setStatus("saving");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      } else {
        headers["X-Dev-User-Email"] = devUserEmail;
      }
      const response = await fetch(`${apiBaseUrl}/api/v1/tasks/${taskId}/complete`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ reason: "Completed from dashboard speed-to-lead queue." }),
      });

      if (!response.ok) {
        throw new Error("Unable to complete task.");
      }

      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <button className={styles.smallButton} disabled={status === "saving"} onClick={completeTask}>
      {status === "saving" ? "Saving" : status === "error" ? "Retry" : "Done"}
    </button>
  );
}
