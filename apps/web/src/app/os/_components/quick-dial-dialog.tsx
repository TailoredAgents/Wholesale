"use client";

import { useAuth } from "@clerk/nextjs";
import { Building2, Delete, Headphones, MessageSquare, Phone, PhoneCall, PhoneIncoming, Send, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, type RefObject, useEffect, useMemo, useRef, useState } from "react";

import { useWebPhone } from "./web-phone-provider";
import styles from "./quick-dial-dialog.module.css";

type QuickDialPurpose =
  | "title_company"
  | "attorney"
  | "contractor"
  | "lender"
  | "investor"
  | "vendor"
  | "other";

type QuickDialResponse = {
  conversation_id: string;
  contact_id: string;
  conversation_type: string;
  contact_name: string;
  reused_contact: boolean;
  reused_conversation: boolean;
  intent: {
    id: string;
    conversation_id: string;
    recipient: string;
    from_number: string;
    status: string;
    expires_at: string;
    recording_enabled: boolean;
  };
};

type QuickTextResponse = {
  conversation_id: string;
  contact_name: string;
  message: { recipient: string; status: string };
};

const purposeOptions: Array<{ value: QuickDialPurpose; label: string }> = [
  { value: "title_company", label: "Title company" },
  { value: "attorney", label: "Attorney" },
  { value: "contractor", label: "Contractor" },
  { value: "lender", label: "Lender" },
  { value: "investor", label: "Investor" },
  { value: "vendor", label: "Other vendor" },
  { value: "other", label: "Other business call" },
];

const dialPadKeys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];

type QuickDialCloseOptions = {
  focusActiveCall?: boolean;
};

function responseDetail(payload: unknown) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) {
    return "Stonegate could not prepare this call.";
  }
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg?: unknown }).msg ?? "")
          : "",
      )
      .filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  return "Stonegate could not prepare this call.";
}

export function QuickDialLauncher({
  buttonRef,
  expanded,
  onOpen,
}: {
  buttonRef: RefObject<HTMLButtonElement | null>;
  expanded: boolean;
  onOpen: (trigger: HTMLButtonElement) => void;
}) {
  const webPhone = useWebPhone();
  const phoneOccupied = Boolean(webPhone.activeCall) || webPhone.status.callActive;

  if (phoneOccupied) return null;

  return (
    <button
      aria-controls="stonegate-quick-dial"
      aria-expanded={expanded}
      aria-haspopup="dialog"
      aria-hidden={expanded}
      aria-label="Open Stonegate phone"
      className={`${styles.launcher} ${webPhone.incomingEnabled ? styles.launcherReady : ""} ${expanded ? styles.launcherHidden : ""}`}
      disabled={expanded}
      onClick={(event) => onOpen(event.currentTarget)}
      ref={buttonRef}
      title={webPhone.incomingEnabled ? "Stonegate phone · Incoming calls on" : "Open Stonegate phone"}
      type="button"
    >
      {webPhone.incomingEnabled ? (
        <PhoneIncoming aria-hidden="true" size={22} />
      ) : (
        <Phone aria-hidden="true" size={22} />
      )}
      <span>Phone</span>
    </button>
  );
}

export function QuickDialDialog({
  canCall,
  canText,
  onClose,
  onSubmittingChange,
}: {
  canCall: boolean;
  canText: boolean;
  onClose: (options?: QuickDialCloseOptions) => void;
  onSubmittingChange: (submitting: boolean) => void;
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const webPhone = useWebPhone();
  const dialogRef = useRef<HTMLElement>(null);
  const idempotencyKeyRef = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const phoneInputRef = useRef<HTMLInputElement>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const submittingRef = useRef(false);
  const [phoneNumber, setPhoneNumber] = useState("");
  const [contactName, setContactName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [purpose, setPurpose] = useState<QuickDialPurpose>("other");
  const [callReason, setCallReason] = useState("");
  const [mode, setMode] = useState<"call" | "text">(canCall ? "call" : "text");
  const [messageBody, setMessageBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

  useEffect(() => {
    submittingRef.current = submitting;
  }, [submitting]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
      onSubmittingChange(false);
    };
  }, [onSubmittingChange]);

  useEffect(() => {
    idempotencyKeyRef.current = null;
  }, [callReason, companyName, contactName, messageBody, mode, phoneNumber, purpose]);

  useEffect(() => {
    const dialogElement = dialogRef.current;
    if (!dialogElement) return;
    const currentDialog: HTMLElement = dialogElement;
    const focusFrame = window.requestAnimationFrame(() => phoneInputRef.current?.focus());

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || submittingRef.current) return;
      event.preventDefault();
      event.stopPropagation();
      onClose();
    }

    currentDialog.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      currentDialog.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  useEffect(() => {
    const closeForIncomingCall = () => onClose({ focusActiveCall: true });
    window.addEventListener("stonegate:incoming-phone-call", closeForIncomingCall);
    return () => window.removeEventListener("stonegate:incoming-phone-call", closeForIncomingCall);
  }, [onClose]);

  function appendDialPadKey(key: string) {
    setPhoneNumber((current) => `${current}${key}`.slice(0, 80));
    window.requestAnimationFrame(() => phoneInputRef.current?.focus());
  }

  async function toggleIncomingCalls() {
    if (webPhone.busy || webPhone.status.callActive) return;
    setError(null);
    try {
      if (webPhone.incomingEnabled) await webPhone.disableIncomingCalls();
      else await webPhone.enableIncomingCalls();
    } catch (toggleError) {
      setError(
        toggleError instanceof Error
          ? toggleError.message
          : "Stonegate could not update incoming browser calls.",
      );
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      submitting ||
      requestControllerRef.current ||
      webPhone.busy ||
      webPhone.status.callActive
    ) {
      return;
    }
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setSubmitting(true);
    onSubmittingChange(true);
    setError(null);
    try {
      if (mode === "text") {
        const idempotencyKey = idempotencyKeyRef.current ?? window.crypto.randomUUID();
        idempotencyKeyRef.current = idempotencyKey;
        const token = await getToken().catch(() => null);
        const headers: Record<string, string> = {
          Accept: "application/json",
          "Content-Type": "application/json",
        };
        if (token) headers.Authorization = `Bearer ${token}`;
        else headers["X-Dev-User-Email"] = devUserEmail;
        const response = await fetch(`${apiBaseUrl}/api/v1/inbox/quick-text`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            phone_number: phoneNumber,
            contact_name: contactName.trim() || null,
            company_name: companyName.trim() || null,
            body: messageBody.trim(),
            idempotency_key: idempotencyKey,
          }),
          signal: controller.signal,
        });
        const payload = (await response.json().catch(() => null)) as QuickTextResponse | null;
        if (!response.ok || !payload) throw new Error(responseDetail(payload));
        idempotencyKeyRef.current = null;
        requestControllerRef.current = null;
        onClose();
        router.push(
          `/os/inbox?conversation=${encodeURIComponent(payload.conversation_id)}&channel=sms`,
        );
        return;
      }
      await webPhone.prepareAndStartCall(async () => {
        const idempotencyKey = idempotencyKeyRef.current ?? window.crypto.randomUUID();
        idempotencyKeyRef.current = idempotencyKey;
        const token = await getToken().catch(() => null);
        if (controller.signal.aborted || !mountedRef.current) {
          throw new DOMException("Quick Dial was closed.", "AbortError");
        }
        const headers: Record<string, string> = {
          Accept: "application/json",
          "Content-Type": "application/json",
        };
        if (token) headers.Authorization = `Bearer ${token}`;
        else headers["X-Dev-User-Email"] = devUserEmail;
        const response = await fetch(`${apiBaseUrl}/api/v1/voice/quick-dial`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            phone_number: phoneNumber,
            contact_name: contactName.trim() || null,
            company_name: companyName.trim() || null,
            purpose,
            call_reason: callReason.trim() || null,
            idempotency_key: idempotencyKey,
          }),
          signal: controller.signal,
        });
        const payload = (await response.json().catch(() => null)) as QuickDialResponse | null;
        if (controller.signal.aborted || !mountedRef.current) {
          throw new DOMException("Quick Dial was closed.", "AbortError");
        }
        if (!response.ok || !payload) throw new Error(responseDetail(payload));

        // A returned call authorization may be consumed by Twilio even when the SDK later
        // reports a connection error. Rotate now so a deliberate retry creates a fresh intent.
        idempotencyKeyRef.current = null;
        requestControllerRef.current = null;
        return {
          callIntentId: payload.intent.id,
          contextHref: `/os/inbox?conversation=${encodeURIComponent(payload.conversation_id)}&channel=call`,
          contextLabel: companyName.trim() || "Quick Dial",
          displayName: payload.contact_name,
          fromNumber: payload.intent.from_number,
          phoneNumber: payload.intent.recipient,
        };
      });
      if (mountedRef.current) onClose({ focusActiveCall: true });
    } catch (submitError) {
      if (controller.signal.aborted || !mountedRef.current) return;
      setError(
        submitError instanceof Error ? submitError.message : "Stonegate could not start the call.",
      );
    } finally {
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
      if (mountedRef.current) {
        setSubmitting(false);
        onSubmittingChange(false);
      }
    }
  }

  return (
    <div className={styles.dockLayer} role="presentation">
      <section
        aria-labelledby="quick-dial-title"
        aria-modal="false"
        className={styles.dialog}
        id="stonegate-quick-dial"
        ref={dialogRef}
        role="dialog"
      >
        <header>
          <div className={styles.headingIcon} aria-hidden="true">
            <Headphones size={20} />
          </div>
          <div>
            <span>Stonegate Web Phone</span>
            <h2 id="quick-dial-title">Call or text</h2>
            <p>Type or paste any external number and contact them from Stonegate.</p>
          </div>
          <button
            aria-label="Close Quick Dial"
            className={styles.closeButton}
            disabled={submitting}
            onClick={() => onClose()}
            type="button"
          >
            <X aria-hidden="true" size={18} />
          </button>
        </header>

        <form onSubmit={submit}>
          {canCall && canText ? (
            <div aria-label="Communication type" className={styles.modeSwitch} role="tablist">
              <button
                aria-selected={mode === "call"}
                onClick={() => setMode("call")}
                role="tab"
                type="button"
              >
                <PhoneCall aria-hidden="true" size={16} /> Call
              </button>
              <button
                aria-selected={mode === "text"}
                onClick={() => setMode("text")}
                role="tab"
                type="button"
              >
                <MessageSquare aria-hidden="true" size={16} /> Text
              </button>
            </div>
          ) : null}
          <fieldset className={styles.dialingFields} disabled={submitting}>
            <label className={styles.wideField}>
              <span>Phone number</span>
              <input
                autoComplete="tel"
                inputMode="tel"
                maxLength={80}
                onChange={(event) => setPhoneNumber(event.target.value)}
                placeholder="(678) 555-0123"
                ref={phoneInputRef}
                required
                type="tel"
                value={phoneNumber}
              />
            </label>
            <div aria-label="Dial pad" className={styles.dialPad} role="group">
              {dialPadKeys.map((key) => (
                <button
                  aria-label={`Enter ${key}`}
                  key={key}
                  onClick={() => appendDialPadKey(key)}
                  type="button"
                >
                  {key}
                </button>
              ))}
            </div>
            <button
              aria-label="Delete last phone digit"
              className={styles.backspaceButton}
              disabled={!phoneNumber}
              onClick={() => setPhoneNumber((current) => current.slice(0, -1))}
              type="button"
            >
              <Delete aria-hidden="true" size={18} />
              Delete
            </button>

            <details className={styles.callDetails}>
              <summary>Add contact details <span>Optional</span></summary>
              <div className={styles.detailFields}>
                <label>
                  <span>Contact name</span>
                  <input
                    autoComplete="name"
                    maxLength={255}
                    onChange={(event) => setContactName(event.target.value)}
                    placeholder="Jordan Smith"
                    value={contactName}
                  />
                </label>
                <label>
                  <span>Company</span>
                  <input
                    autoComplete="organization"
                    maxLength={255}
                    onChange={(event) => setCompanyName(event.target.value)}
                    placeholder="Peachtree Title"
                    value={companyName}
                  />
                </label>
                {mode === "call" ? (
                  <>
                    <label>
                      <span>Call type</span>
                      <select
                        onChange={(event) => setPurpose(event.target.value as QuickDialPurpose)}
                        value={purpose}
                      >
                        {purposeOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Reason</span>
                      <input
                        maxLength={500}
                        onChange={(event) => setCallReason(event.target.value)}
                        placeholder="Discuss closing availability"
                        value={callReason}
                      />
                    </label>
                  </>
                ) : null}
              </div>
            </details>
            {mode === "text" ? (
              <label className={styles.wideField}>
                <span>Message</span>
                <textarea
                  maxLength={1600}
                  onChange={(event) => setMessageBody(event.target.value)}
                  placeholder="Write your message…"
                  required
                  rows={5}
                  value={messageBody}
                />
              </label>
            ) : null}
          </fieldset>

          <div className={styles.callNotice}>
            <Building2 aria-hidden="true" size={18} />
            <p>
              {mode === "call"
                ? `${webPhone.incomingEnabled
                    ? "This browser will ring with your configured Stonegate cellphone. First answer wins."
                    : "Turn on incoming calls to answer Stonegate callbacks here while this OS tab stays open."} A matching contact is reused; otherwise a company conversation is created.`
                : "The text is sent one-to-one from Stonegate and saved in Conversations. A matching contact is reused automatically."}
            </p>
            {mode === "call" ? (
              <button
                aria-pressed={webPhone.incomingEnabled}
                className={styles.incomingToggle}
                disabled={submitting || webPhone.busy || webPhone.status.callActive}
                onClick={() => void toggleIncomingCalls()}
                type="button"
              >
                <PhoneIncoming aria-hidden="true" size={16} />
                {webPhone.incomingEnabled ? "Incoming on" : "Enable incoming"}
              </button>
            ) : null}
          </div>
          {error ? <p aria-live="assertive" className={styles.error}>{error}</p> : null}
          {webPhone.activeCall && webPhone.status.callActive ? (
            <p aria-live="polite" className={styles.error}>
              End the current call with {webPhone.activeCall.displayName} before starting another one.
            </p>
          ) : null}
          <footer>
            <button
              className={styles.cancelButton}
              disabled={submitting}
              onClick={() => onClose()}
              type="button"
            >
              Cancel
            </button>
            <button
              className={styles.callButton}
              disabled={
                submitting ||
                (mode === "call" && (webPhone.busy || webPhone.status.callActive))
              }
              type="submit"
            >
              {mode === "call" ? (
                <PhoneCall aria-hidden="true" size={17} />
              ) : (
                <Send aria-hidden="true" size={17} />
              )}
              {mode === "call"
                ? submitting || webPhone.busy ? "Starting browser call…" : "Call in browser"
                : submitting ? "Sending…" : "Send text"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
