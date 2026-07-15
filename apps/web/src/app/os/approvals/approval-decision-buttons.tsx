"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "../page.module.css";

type Status = "idle" | "saving" | "saved" | "error";

export function ApprovalDecisionButtons({ approvalId }: { approvalId: string }) {
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

  async function decide(decision: "approved" | "rejected") {
    setStatus("saving");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/approvals/${approvalId}/decision`, {
        method: "PATCH",
        headers: await getHeaders(),
        body: JSON.stringify({
          status: decision,
          decision_notes: `Decision recorded from approval queue: ${decision}.`,
        }),
      });
      if (!response.ok) {
        throw new Error("Unable to decide approval.");
      }
      setStatus("saved");
      router.refresh();
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className={styles.inlineActions}>
      <button disabled={status === "saving"} onClick={() => void decide("approved")} type="button">
        Approve
      </button>
      <button disabled={status === "saving"} onClick={() => void decide("rejected")} type="button">
        Reject
      </button>
      {status === "error" ? <span className={styles.error}>error</span> : null}
    </div>
  );
}
