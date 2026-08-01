"use client";

import { useAuth } from "@clerk/nextjs";
import { PhoneCall } from "lucide-react";
import { useMemo, useState } from "react";

import styles from "./page.module.css";

type CallStatus = "idle" | "starting" | "started" | "error";

function errorDetail(payload: unknown) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return "Stonegate could not start the call.";
}

export function LeadCallButton({ leadId }: { leadId: string }) {
  const { getToken } = useAuth();
  const [status, setStatus] = useState<CallStatus>("idle");
  const [message, setMessage] = useState("");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function startCall() {
    if (status === "starting") return;
    setStatus("starting");
    setMessage("");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}/api/v1/voice/leads/${leadId}/forwarded-calls`, {
        method: "POST",
        headers,
        body: JSON.stringify({ idempotency_key: window.crypto.randomUUID() }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(errorDetail(payload));
      setStatus("started");
      setMessage("Answer your cellphone and press 1 to connect.");
      window.setTimeout(() => {
        setStatus("idle");
        setMessage("");
      }, 8000);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Stonegate could not start the call.");
    }
  }

  return (
    <div className={styles.callAction}>
      <button disabled={status === "starting"} onClick={() => void startCall()} type="button">
        <PhoneCall aria-hidden="true" size={15} />
        {status === "starting" ? "Calling your cellphone" : "Call seller"}
      </button>
      {message ? (
        <span aria-live="polite" className={status === "error" ? styles.callError : styles.callStatus}>
          {message}
        </span>
      ) : null}
    </div>
  );
}
