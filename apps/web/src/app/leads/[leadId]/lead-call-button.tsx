"use client";

import { useAuth } from "@clerk/nextjs";
import { Headphones, PhoneCall } from "lucide-react";
import { useMemo, useState } from "react";

import { useWebPhone } from "../../os/_components/web-phone-provider";
import styles from "./page.module.css";

type CallStatus = "idle" | "starting_browser" | "starting_cellphone" | "started" | "error";

type VoiceCallIntent = {
  id: string;
  conversation_id: string;
  recipient: string;
  from_number: string;
  status: string;
  expires_at: string;
  recording_enabled: boolean;
};

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

export function LeadCallButton({
  leadId,
  phoneNumber,
  sellerName,
}: {
  leadId: string;
  phoneNumber: string;
  sellerName: string;
}) {
  const { getToken } = useAuth();
  const webPhone = useWebPhone();
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

  async function requestIntent(path: string) {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    const response = await fetch(`${apiBaseUrl}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify({ idempotency_key: window.crypto.randomUUID() }),
    });
    const payload = (await response.json().catch(() => null)) as VoiceCallIntent | null;
    if (!response.ok || !payload) throw new Error(errorDetail(payload));
    return payload;
  }

  async function startBrowserCall() {
    if (status.startsWith("starting") || webPhone.busy || webPhone.status.callActive) return;
    setStatus("starting_browser");
    setMessage("");
    try {
      const intent = await requestIntent(`/api/v1/voice/leads/${leadId}/call-intents`);
      await webPhone.startCall({
        callIntentId: intent.id,
        contextHref: `/os/leads/${encodeURIComponent(leadId)}`,
        contextLabel: "Seller lead",
        displayName: sellerName,
        fromNumber: intent.from_number,
        phoneNumber: intent.recipient || phoneNumber,
      });
      setStatus("started");
      setMessage("Browser call started. Use the phone bar to mute or hang up.");
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Stonegate could not start the call.");
    }
  }

  async function startCellphoneCall() {
    if (status.startsWith("starting") || webPhone.busy || webPhone.status.callActive) return;
    setStatus("starting_cellphone");
    setMessage("");
    try {
      await requestIntent(`/api/v1/voice/leads/${leadId}/forwarded-calls`);
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

  const starting = status.startsWith("starting");
  return (
    <div className={styles.callAction}>
      <button
        disabled={starting || webPhone.busy || webPhone.status.callActive}
        onClick={() => void startBrowserCall()}
        type="button"
      >
        <Headphones aria-hidden="true" size={15} />
        {status === "starting_browser" ? "Starting browser call" : "Call seller"}
      </button>
      <button
        aria-label="Call seller through my cellphone"
        className={styles.cellphoneCallButton}
        disabled={starting || webPhone.busy || webPhone.status.callActive}
        onClick={() => void startCellphoneCall()}
        title="Call through my cellphone"
        type="button"
      >
        <PhoneCall aria-hidden="true" size={15} />
      </button>
      {message ? (
        <span aria-live="polite" className={status === "error" ? styles.callError : styles.callStatus}>
          {message}
        </span>
      ) : null}
    </div>
  );
}
