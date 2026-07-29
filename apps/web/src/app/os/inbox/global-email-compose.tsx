"use client";

import {
  Check,
  CircleAlert,
  Mail,
  Paperclip,
  Send,
  UserRound,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import type { EmailSenderAlias } from "./email-admin-panel";
import styles from "./global-email-compose.module.css";

type EmailTemplate = {
  id: string;
  name: string;
  subject_template: string;
  body_template: string;
};

type RecipientOption = {
  contact_id: string;
  display_name: string;
  email_address: string;
  contact_type: string;
};

type ComposeResult = {
  conversation_id: string;
  message: {
    communication_id: string;
    status: string;
  };
};

function displayError(payload: unknown, fallback: string) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
}

function parseRecipients(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[;,]/)
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
    ),
  );
}

function activeRecipientQuery(value: string) {
  return value.split(/[;,]/).at(-1)?.trim() ?? "";
}

function addRecipient(value: string, recipient: RecipientOption) {
  const parts = value.split(/[;,]/);
  parts.pop();
  return [...parts.map((item) => item.trim()).filter(Boolean), recipient.email_address].join(
    ", ",
  );
}

async function fileToBase64(file: File) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return window.btoa(binary);
}

export function GlobalEmailCompose({
  aliases,
  apiBaseUrl,
  configurationBlockers,
  getHeaders,
  onClose,
  onSent,
  providerConfigured,
  templates,
}: {
  aliases: EmailSenderAlias[];
  apiBaseUrl: string;
  configurationBlockers: string[];
  getHeaders: () => Promise<Record<string, string>>;
  onClose: () => void;
  onSent: (conversationId: string) => Promise<void>;
  providerConfigured: boolean;
  templates: EmailTemplate[];
}) {
  const senders = useMemo(
    () =>
      aliases.filter(
        (alias) =>
          alias.can_send &&
          alias.status === "active" &&
          alias.inbound_enabled &&
          alias.outbound_enabled,
      ),
    [aliases],
  );
  const defaultSender =
    senders.find((alias) => alias.is_default)?.id ?? senders[0]?.id ?? "";
  const idempotencyKeyRef = useRef<string | null>(null);
  const [senderId, setSenderId] = useState(defaultSender);
  const [to, setTo] = useState("");
  const [contactName, setContactName] = useState("");
  const [cc, setCc] = useState("");
  const [bcc, setBcc] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [attachments, setAttachments] = useState<File[]>([]);
  const [suggestions, setSuggestions] = useState<RecipientOption[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState("");
  const selectedSender = senders.find((alias) => alias.id === senderId) ?? null;
  const primaryRecipients = parseRecipients(to);

  useEffect(() => {
    const query = activeRecipientQuery(to);
    if (query.length < 2) {
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/email/recipients?q=${encodeURIComponent(query)}`,
          {
            headers: await getHeaders(),
            cache: "no-store",
            signal: controller.signal,
          },
        );
        if (!response.ok) return;
        const payload = (await response.json()) as { items: RecipientOption[] };
        setSuggestions(payload.items);
        setShowSuggestions(payload.items.length > 0);
      } catch (searchError) {
        if (!(searchError instanceof DOMException && searchError.name === "AbortError")) {
          setSuggestions([]);
        }
      }
    }, 220);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [apiBaseUrl, getHeaders, to]);

  function resetIdempotency() {
    idempotencyKeyRef.current = window.crypto.randomUUID();
    if (status === "sent") setStatus("idle");
  }

  function applyTemplate(templateId: string) {
    const template = templates.find((item) => item.id === templateId);
    if (!template) return;
    setSubject(template.subject_template);
    setBody(template.body_template);
    resetIdempotency();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!senderId || primaryRecipients.length === 0 || !subject.trim() || !body.trim()) return;
    setStatus("sending");
    setError("");
    idempotencyKeyRef.current ??= window.crypto.randomUUID();
    try {
      const encodedAttachments = await Promise.all(
        attachments.map(async (file) => ({
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          content_base64: await fileToBase64(file),
        })),
      );
      const response = await fetch(`${apiBaseUrl}/api/v1/email/compose`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
          email_sender_alias_id: senderId,
          to: primaryRecipients,
          contact_name: contactName.trim() || null,
          cc: parseRecipients(cc),
          bcc: parseRecipients(bcc),
          subject: subject.trim(),
          body: body.trim(),
          idempotency_key: idempotencyKeyRef.current,
          attachments: encodedAttachments,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(displayError(payload, "The email could not be sent."));
      }
      const result = (await response.json()) as ComposeResult;
      setStatus("sent");
      try {
        await onSent(result.conversation_id);
      } catch {
        setError("Email sent, but the Inbox could not refresh. Close this window and refresh.");
      }
    } catch (submitError) {
      setStatus("idle");
      setError(
        submitError instanceof Error ? submitError.message : "The email could not be sent.",
      );
    }
  }

  return (
    <div className={styles.backdrop} role="presentation" onMouseDown={onClose}>
      <section
        aria-labelledby="global-email-title"
        aria-modal="true"
        className={styles.dialog}
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header>
          <div>
            <span className={styles.headerIcon}>
              <Mail size={18} aria-hidden="true" />
            </span>
            <div>
              <h2 id="global-email-title">New email</h2>
              <p>Start company correspondence without creating a property lead.</p>
            </div>
          </div>
          <button aria-label="Close compose email" onClick={onClose} type="button">
            <X size={19} aria-hidden="true" />
          </button>
        </header>

        <form onSubmit={submit}>
          <div className={styles.addressFields}>
            <label>
              <span>From</span>
              <select
                onChange={(event) => {
                  setSenderId(event.target.value);
                  resetIdempotency();
                }}
                required
                value={senderId}
              >
                <option value="">Select sender</option>
                {senders.map((alias) => (
                  <option key={alias.id} value={alias.id}>
                    {alias.display_name} · {alias.email_address}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.recipientField}>
              <span>To</span>
              <div>
                <input
                  autoFocus
                  onChange={(event) => {
                    setTo(event.target.value);
                    if (activeRecipientQuery(event.target.value).length < 2) {
                      setSuggestions([]);
                    }
                    setShowSuggestions(true);
                    resetIdempotency();
                  }}
                  onFocus={() => setShowSuggestions(suggestions.length > 0)}
                  placeholder="name@example.com"
                  required
                  type="text"
                  value={to}
                />
                {showSuggestions ? (
                  <div className={styles.suggestions}>
                    {suggestions.map((recipient) => (
                      <button
                        key={`${recipient.contact_id}-${recipient.email_address}`}
                        onClick={() => {
                          setTo(addRecipient(to, recipient));
                          if (!contactName) setContactName(recipient.display_name);
                          setShowSuggestions(false);
                          resetIdempotency();
                        }}
                        type="button"
                      >
                        <UserRound size={15} aria-hidden="true" />
                        <span>
                          <strong>{recipient.display_name}</strong>
                          <small>{recipient.email_address}</small>
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </label>
            <label>
              <span>Contact name</span>
              <input
                maxLength={255}
                onChange={(event) => {
                  setContactName(event.target.value);
                  resetIdempotency();
                }}
                placeholder="Optional"
                value={contactName}
              />
            </label>
            <label>
              <span>CC</span>
              <input
                onChange={(event) => {
                  setCc(event.target.value);
                  resetIdempotency();
                }}
                placeholder="Optional, separate with commas"
                value={cc}
              />
            </label>
            <label>
              <span>BCC</span>
              <input
                onChange={(event) => {
                  setBcc(event.target.value);
                  resetIdempotency();
                }}
                placeholder="Optional, separate with commas"
                value={bcc}
              />
            </label>
          </div>

          <div className={styles.messageFields}>
            <div className={styles.subjectRow}>
              <input
                maxLength={255}
                onChange={(event) => {
                  setSubject(event.target.value);
                  resetIdempotency();
                }}
                placeholder="Subject"
                required
                value={subject}
              />
              <select
                aria-label="Use email template"
                defaultValue=""
                onChange={(event) => {
                  applyTemplate(event.target.value);
                  event.target.value = "";
                }}
              >
                <option value="">Use template</option>
                {templates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))}
              </select>
            </div>
            <textarea
              maxLength={4000}
              onChange={(event) => {
                setBody(event.target.value);
                resetIdempotency();
              }}
              placeholder="Write your email..."
              required
              rows={12}
              value={body}
            />
            {selectedSender?.signature_text ? (
              <div className={styles.signaturePreview}>
                <span>Signature</span>
                <p>{selectedSender.signature_text}</p>
              </div>
            ) : null}
          </div>

          <footer>
            <label className={styles.attachButton}>
              <Paperclip size={15} aria-hidden="true" />
              Attach
              <input
                multiple
                onChange={(event) => {
                  setAttachments(Array.from(event.target.files ?? []).slice(0, 5));
                  resetIdempotency();
                }}
                type="file"
              />
            </label>
            <div className={styles.attachmentList}>
              {attachments.map((file) => (
                <span key={`${file.name}-${file.size}`}>{file.name}</span>
              ))}
            </div>
            <button
              className={styles.sendButton}
              disabled={
                status === "sending" ||
                !providerConfigured ||
                !senderId ||
                primaryRecipients.length === 0 ||
                !subject.trim() ||
                !body.trim()
              }
              type="submit"
            >
              {status === "sent" ? (
                <Check size={16} aria-hidden="true" />
              ) : (
                <Send size={16} aria-hidden="true" />
              )}
              {status === "sending" ? "Sending" : status === "sent" ? "Sent" : "Send email"}
            </button>
          </footer>
          {!providerConfigured ? (
            <p className={styles.configurationNote}>
              <CircleAlert size={14} aria-hidden="true" />
              {configurationBlockers.join(" ") || "Email delivery is not configured."}
            </p>
          ) : null}
          {error ? (
            <p className={styles.error} role="alert">
              <CircleAlert size={14} aria-hidden="true" />
              {error}
            </p>
          ) : null}
        </form>
      </section>
    </div>
  );
}
