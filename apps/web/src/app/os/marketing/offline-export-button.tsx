"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "../page.module.css";

type Status = "idle" | "saving" | "saved" | "error";

export function OfflineExportButton() {
  const router = useRouter();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<Status>("idle");
  const [created, setCreated] = useState<number | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function getHeaders() {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      headers["X-Dev-User-Email"] = devUserEmail;
    }
    return headers;
  }

  async function handleClick() {
    setStatus("saving");
    setCreated(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/marketing/offline-conversions/generate`,
        {
          method: "POST",
          headers: await getHeaders(),
        },
      );
      if (!response.ok) {
        throw new Error("Unable to generate exports.");
      }
      const payload = (await response.json()) as { created: number };
      setCreated(payload.created);
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className={styles.actionPanel}>
      <button disabled={status === "saving"} onClick={handleClick} type="button">
        Generate offline exports
      </button>
      {status === "saved" ? <p className={styles.saved}>{created ?? 0} created</p> : null}
      {status === "error" ? <p className={styles.error}>error</p> : null}
      {status === "saving" ? <p className={styles.saving}>saving</p> : null}
    </div>
  );
}
