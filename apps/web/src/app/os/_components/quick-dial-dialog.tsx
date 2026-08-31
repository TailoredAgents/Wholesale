"use client";

import { useAuth } from "@clerk/nextjs";
import { Building2, Headphones, PhoneCall, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

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

const purposeOptions: Array<{ value: QuickDialPurpose; label: string }> = [
  { value: "title_company", label: "Title company" },
  { value: "attorney", label: "Attorney" },
  { value: "contractor", label: "Contractor" },
  { value: "lender", label: "Lender" },
  { value: "investor", label: "Investor" },
  { value: "vendor", label: "Other vendor" },
  { value: "other", label: "Other business call" },
];

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

export function QuickDialDialog({ onClose }: { onClose: () => void }) {
  const { getToken } = useAuth();
  const webPhone = useWebPhone();
  const dialogRef = useRef<HTMLElement>(null);
  const idempotencyKeyRef = useRef<string | null>(null);
  const [phoneNumber, setPhoneNumber] = useState("");
  const [contactName, setContactName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [purpose, setPurpose] = useState<QuickDialPurpose>("other");
  const [callReason, setCallReason] = useState("");
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
    const dialogElement = dialogRef.current;
    if (!dialogElement) return;
    const currentDialog: HTMLElement = dialogElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const backdrop = dialogElement.parentElement;
    const workspace = backdrop?.parentElement;
    const shell = workspace?.parentElement;
    const backgroundElements = [
      ...Array.from(workspace?.children ?? []).filter((element) => element !== backdrop),
      ...Array.from(shell?.children ?? []).filter((element) => element !== workspace),
    ].filter((element): element is HTMLElement => element instanceof HTMLElement);
    const backgroundState = backgroundElements.map((element) => ({
      element,
      ariaHidden: element.getAttribute("aria-hidden"),
      inert: element.inert,
    }));
    backgroundElements.forEach((element) => {
      element.inert = true;
      element.setAttribute("aria-hidden", "true");
    });
    const selector =
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (submitting) return;
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(currentDialog.querySelectorAll<HTMLElement>(selector));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    currentDialog.addEventListener("keydown", handleKeyDown);
    return () => {
      currentDialog.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      backgroundState.forEach(({ element, ariaHidden, inert }) => {
        element.inert = inert;
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      });
    };
  }, [onClose, submitting]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || webPhone.busy || webPhone.status.callActive) return;
    setSubmitting(true);
    setError(null);
    try {
      const idempotencyKey = idempotencyKeyRef.current ?? window.crypto.randomUUID();
      idempotencyKeyRef.current = idempotencyKey;
      const token = await getToken().catch(() => null);
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
      });
      const payload = (await response.json().catch(() => null)) as QuickDialResponse | null;
      if (!response.ok || !payload) throw new Error(responseDetail(payload));

      // A returned call authorization may be consumed by Twilio even when the SDK later
      // reports a connection error. Rotate now so a deliberate retry creates a fresh intent.
      idempotencyKeyRef.current = null;
      await webPhone.startCall({
        callIntentId: payload.intent.id,
        contextHref: `/os/inbox?conversation=${encodeURIComponent(payload.conversation_id)}&channel=call`,
        contextLabel: companyName.trim() || "Quick Dial",
        displayName: payload.contact_name,
        fromNumber: payload.intent.from_number,
        phoneNumber: payload.intent.recipient,
      });
      onClose();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Stonegate could not start the call.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.backdrop} role="presentation">
      <section
        aria-labelledby="quick-dial-title"
        aria-modal="true"
        className={styles.dialog}
        ref={dialogRef}
        role="dialog"
      >
        <header>
          <div className={styles.headingIcon} aria-hidden="true">
            <Headphones size={20} />
          </div>
          <div>
            <span>Stonegate Web Phone</span>
            <h2 id="quick-dial-title">Quick Dial</h2>
            <p>Call a company or professional without creating a seller lead.</p>
          </div>
           <button aria-label="Close Quick Dial" className={styles.closeButton} disabled={submitting} onClick={onClose} type="button">
            <X aria-hidden="true" size={18} />
          </button>
        </header>

        <form onSubmit={submit}>
          <label className={styles.wideField}>
            <span>Phone number</span>
            <input
              autoComplete="tel"
              autoFocus
              inputMode="tel"
              maxLength={80}
              onChange={(event) => setPhoneNumber(event.target.value)}
              placeholder="(678) 555-0123"
              required
              type="tel"
              value={phoneNumber}
            />
          </label>
          <label>
            <span>Contact name <small>Optional</small></span>
            <input
              autoComplete="name"
              maxLength={255}
              onChange={(event) => setContactName(event.target.value)}
              placeholder="Jordan Smith"
              value={contactName}
            />
          </label>
          <label>
            <span>Company <small>Optional</small></span>
            <input
              autoComplete="organization"
              maxLength={255}
              onChange={(event) => setCompanyName(event.target.value)}
              placeholder="Peachtree Title"
              value={companyName}
            />
          </label>
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
            <span>Reason <small>Optional</small></span>
            <input
              maxLength={500}
              onChange={(event) => setCallReason(event.target.value)}
              placeholder="Discuss closing availability"
              value={callReason}
            />
          </label>

          <div className={styles.callNotice}>
            <Building2 aria-hidden="true" size={18} />
            <p>
              Stonegate will reuse an existing matching contact when possible. Otherwise, this
              creates a company contact and saves the call in Inbox.
            </p>
          </div>
          {error ? <p aria-live="assertive" className={styles.error}>{error}</p> : null}
          {webPhone.activeCall && webPhone.status.callActive ? (
            <p aria-live="polite" className={styles.error}>
              End the current call with {webPhone.activeCall.displayName} before starting another one.
            </p>
          ) : null}
          <footer>
            <button className={styles.cancelButton} disabled={submitting} onClick={onClose} type="button">
              Cancel
            </button>
            <button
              className={styles.callButton}
              disabled={submitting || webPhone.busy || webPhone.status.callActive}
              type="submit"
            >
              <PhoneCall aria-hidden="true" size={17} />
              {submitting || webPhone.busy ? "Starting browser call…" : "Call in browser"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
