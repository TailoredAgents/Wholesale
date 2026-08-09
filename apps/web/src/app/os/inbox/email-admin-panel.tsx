"use client";

import { useAuth } from "@clerk/nextjs";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Inbox,
  Mail,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  UserRoundCog,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import styles from "./email-admin-panel.module.css";

export type EmailSenderGrant = {
  id: string;
  user_id: string;
  user_name: string;
  access_level: string;
  can_send: boolean;
  receives_notifications: boolean;
};

export type EmailSenderAlias = {
  id: string;
  provider: string;
  email_address: string;
  display_name: string;
  alias_type: string;
  purpose_key: string;
  status: string;
  owner_user_id: string | null;
  owner_user_name: string | null;
  assigned_team_id: string | null;
  assigned_team_name: string | null;
  inbound_enabled: boolean;
  outbound_enabled: boolean;
  is_default: boolean;
  signature_text: string | null;
  routing_metadata: Record<string, unknown>;
  can_send: boolean;
  can_manage: boolean;
  grants: EmailSenderGrant[];
};

type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  role_keys: string[];
};

type AdminTeam = {
  id: string;
  name: string;
  team_type: string;
};

type RoutingException = {
  id: string;
  processing_status: string;
  provider_message_id: string;
  sender: string;
  recipients: string[];
  subject: string | null;
  received_at: string;
  reason: string;
  candidate_conversation_ids: string[];
};

type EmailDeadLetter = {
  id: string;
  event_type: string;
  provider_message_id: string;
  sender: string;
  recipients: string[];
  subject: string | null;
  received_at: string;
  processed_at: string | null;
  attempt_count: number;
  error_message: string | null;
  processing_status: string;
};

type ConversationOption = {
  id: string;
  seller_name: string;
  property_address: string;
};

type AliasDraft = {
  email_address: string;
  display_name: string;
  alias_type: "named" | "department" | "contractor";
  purpose_key: string;
  status: "active" | "reserved" | "disabled";
  owner_user_id: string;
  assigned_team_id: string;
  inbound_enabled: boolean;
  outbound_enabled: boolean;
  is_default: boolean;
  signature_text: string;
};

const emptyDraft: AliasDraft = {
  email_address: "",
  display_name: "",
  alias_type: "department",
  purpose_key: "",
  status: "active",
  owner_user_id: "",
  assigned_team_id: "",
  inbound_enabled: true,
  outbound_enabled: true,
  is_default: false,
  signature_text: "",
};

function draftForAlias(alias: EmailSenderAlias): AliasDraft {
  return {
    email_address: alias.email_address,
    display_name: alias.display_name,
    alias_type: alias.alias_type as AliasDraft["alias_type"],
    purpose_key: alias.purpose_key,
    status: alias.status as AliasDraft["status"],
    owner_user_id: alias.owner_user_id ?? "",
    assigned_team_id: alias.assigned_team_id ?? "",
    inbound_enabled: alias.inbound_enabled,
    outbound_enabled: alias.outbound_enabled,
    is_default: alias.is_default,
    signature_text: alias.signature_text ?? "",
  };
}

function labelize(value: string) {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function errorMessage(payload: unknown, fallback: string) {
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

export function EmailAdminPanel({
  aliases,
  conversations,
  open,
  providerConfigured,
  configurationBlockers,
  onAliasesChanged,
  onClose,
  variant = "dialog",
}: {
  aliases: EmailSenderAlias[];
  conversations: ConversationOption[];
  open: boolean;
  providerConfigured: boolean;
  configurationBlockers: string[];
  onAliasesChanged: () => Promise<void>;
  onClose?: () => void;
  variant?: "dialog" | "inline";
}) {
  const { getToken } = useAuth();
  const [tab, setTab] = useState<"senders" | "routing" | "dead_letters">("senders");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [teams, setTeams] = useState<AdminTeam[]>([]);
  const [exceptions, setExceptions] = useState<RoutingException[]>([]);
  const [deadLetters, setDeadLetters] = useState<EmailDeadLetter[]>([]);
  const initialAlias = aliases.find((alias) => alias.is_default) ?? aliases[0] ?? null;
  const [selectedAliasId, setSelectedAliasId] = useState<string | null>(
    initialAlias?.id ?? null,
  );
  const [creating, setCreating] = useState(!initialAlias);
  const [draft, setDraft] = useState<AliasDraft>(
    initialAlias ? draftForAlias(initialAlias) : emptyDraft,
  );
  const [grantUserId, setGrantUserId] = useState("");
  const [grantAccessLevel, setGrantAccessLevel] = useState<"sender" | "watcher">("sender");
  const [routingSelections, setRoutingSelections] = useState<Record<string, string>>({});
  const [requeueReasons, setRequeueReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
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
  const selectedAlias = aliases.find((alias) => alias.id === selectedAliasId) ?? null;

  const request = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        ...init,
        headers: { ...headers, ...init?.headers },
        cache: "no-store",
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(errorMessage(payload, `Request failed with status ${response.status}.`));
      }
      return (await response.json()) as T;
    },
    [apiBaseUrl, devUserEmail, getToken],
  );

  const loadAdministration = useCallback(async () => {
    const [options, routing, deadLetterResponse] = await Promise.all([
      request<{ users: AdminUser[]; teams: AdminTeam[] }>("/api/v1/email/admin/options"),
      request<{ items: RoutingException[] }>("/api/v1/email/routing-exceptions"),
      request<{ items: EmailDeadLetter[] }>("/api/v1/email/dead-letters"),
    ]);
    setUsers(options.users);
    setTeams(options.teams);
    setExceptions(routing.items);
    setDeadLetters(deadLetterResponse.items);
  }, [request]);

  useEffect(() => {
    if (!open) return;
    const handle = window.setTimeout(() => {
      void loadAdministration().catch((loadError: unknown) => {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Email administration could not load.",
        );
      });
    }, 0);
    return () => window.clearTimeout(handle);
  }, [loadAdministration, open]);

  function selectAlias(alias: EmailSenderAlias) {
    setCreating(false);
    setSelectedAliasId(alias.id);
    setDraft(draftForAlias(alias));
    setMessage("");
    setError("");
  }

  function beginCreate() {
    setCreating(true);
    setSelectedAliasId(null);
    setDraft(emptyDraft);
    setMessage("");
    setError("");
  }

  async function saveAlias(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    const payload = {
      ...(creating ? { email_address: draft.email_address.trim() } : {}),
      display_name: draft.display_name.trim(),
      ...(creating ? { alias_type: draft.alias_type } : {}),
      purpose_key: draft.purpose_key.trim(),
      status: draft.status,
      owner_user_id: draft.owner_user_id || null,
      assigned_team_id: draft.assigned_team_id || null,
      ...(creating ? { provider: "resend" } : {}),
      inbound_enabled: draft.inbound_enabled,
      outbound_enabled: draft.outbound_enabled,
      is_default: draft.is_default,
      signature_text: draft.signature_text.trim() || null,
    };
    try {
      const alias = await request<EmailSenderAlias>(
        creating ? "/api/v1/email/aliases" : `/api/v1/email/aliases/${selectedAliasId}`,
        {
          method: creating ? "POST" : "PATCH",
          body: JSON.stringify(payload),
        },
      );
      await onAliasesChanged();
      setCreating(false);
      setSelectedAliasId(alias.id);
      setDraft(draftForAlias(alias));
      setMessage("Sender saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "The sender could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function saveGrant() {
    if (!selectedAlias || !grantUserId) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await request(`/api/v1/email/aliases/${selectedAlias.id}/grants`, {
        method: "PUT",
        body: JSON.stringify({
          user_id: grantUserId,
          access_level: grantAccessLevel,
          can_send: grantAccessLevel === "sender",
          receives_notifications: true,
        }),
      });
      setGrantUserId("");
      await onAliasesChanged();
      setMessage("Access updated.");
    } catch (grantError) {
      setError(grantError instanceof Error ? grantError.message : "Access could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  async function revokeGrant(userId: string) {
    if (!selectedAlias) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await request(`/api/v1/email/aliases/${selectedAlias.id}/grants/${userId}`, {
        method: "DELETE",
      });
      await onAliasesChanged();
      setMessage("Access removed.");
    } catch (grantError) {
      setError(grantError instanceof Error ? grantError.message : "Access could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  async function resolveException(eventId: string) {
    const conversationId = routingSelections[eventId];
    if (!conversationId) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await request(`/api/v1/email/routing-exceptions/${eventId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ conversation_id: conversationId }),
      });
      await loadAdministration();
      setMessage("Email assigned. The worker will place it in the conversation.");
    } catch (routingError) {
      setError(
        routingError instanceof Error ? routingError.message : "The email could not be assigned.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function requeueDeadLetter(eventId: string) {
    const reason = requeueReasons[eventId]?.trim() ?? "";
    if (reason.length < 10) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await request(`/api/v1/email/dead-letters/${eventId}/requeue`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setRequeueReasons((current) => ({ ...current, [eventId]: "" }));
      await loadAdministration();
      setMessage("Email event requeued. The worker will try it again.");
    } catch (requeueError) {
      setError(
        requeueError instanceof Error
          ? requeueError.message
          : "The email event could not be requeued.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  const panel = (
      <section
        aria-labelledby="email-admin-title"
        aria-modal={variant === "dialog" ? "true" : undefined}
        className={`${styles.panel} ${variant === "inline" ? styles.inlinePanel : ""}`}
        onMouseDown={(event) => event.stopPropagation()}
        role={variant === "dialog" ? "dialog" : "region"}
      >
        <header className={styles.header}>
          <div>
            <span>Shared Inbox</span>
            <h2 id="email-admin-title">Email administration</h2>
          </div>
          {variant === "dialog" ? <button onClick={onClose} title="Close email administration" type="button">
            <X aria-hidden="true" size={18} />
          </button> : null}
        </header>

        <div className={styles.providerStatus} data-ready={providerConfigured}>
          {providerConfigured ? <Check aria-hidden="true" size={16} /> : <AlertTriangle size={16} />}
          <div>
            <strong>{providerConfigured ? "Resend configuration ready" : "Resend is disabled"}</strong>
            <span>
              {providerConfigured
                ? "Sender and routing controls are ready for provider acceptance."
                : configurationBlockers.join(" ") || "Production credentials are not configured."}
            </span>
          </div>
        </div>

        <nav aria-label="Email administration sections" className={styles.tabs}>
          <button
            aria-selected={tab === "senders"}
            onClick={() => setTab("senders")}
            role="tab"
            type="button"
          >
            <Mail aria-hidden="true" size={16} />
            Senders
          </button>
          <button
            aria-selected={tab === "routing"}
            onClick={() => setTab("routing")}
            role="tab"
            type="button"
          >
            <Inbox aria-hidden="true" size={16} />
            Routing
            {exceptions.length ? <span>{exceptions.length}</span> : null}
          </button>
          <button
            aria-selected={tab === "dead_letters"}
            onClick={() => setTab("dead_letters")}
            role="tab"
            type="button"
          >
            <AlertTriangle aria-hidden="true" size={16} />
            Failed events
            {deadLetters.length ? <span>{deadLetters.length}</span> : null}
          </button>
        </nav>

        {error ? <p className={styles.error}>{error}</p> : null}
        {message ? <p className={styles.success}>{message}</p> : null}

        {tab === "senders" ? (
          <div className={styles.senderWorkspace}>
            <aside className={styles.senderList}>
              <button className={styles.addSender} onClick={beginCreate} type="button">
                <Plus aria-hidden="true" size={15} />
                Add sender
              </button>
              {aliases.map((alias) => (
                <button
                  aria-current={!creating && selectedAliasId === alias.id}
                  key={alias.id}
                  onClick={() => selectAlias(alias)}
                  type="button"
                >
                  <span>{alias.display_name}</span>
                  <small>{alias.email_address}</small>
                  <em data-status={alias.status}>{labelize(alias.status)}</em>
                </button>
              ))}
            </aside>

            <div className={styles.editor}>
              <form onSubmit={saveAlias}>
                <div className={styles.editorHeading}>
                  <div>
                    <span>{creating ? "New company address" : labelize(draft.alias_type)}</span>
                    <h3>{creating ? "Add sender" : draft.email_address}</h3>
                  </div>
                  <button disabled={busy} type="submit">
                    <Save aria-hidden="true" size={15} />
                    {busy ? "Saving" : "Save"}
                  </button>
                </div>

                <div className={styles.formGrid}>
                  {creating ? (
                    <label>
                      <span>Email address</span>
                      <input
                        onChange={(event) =>
                          setDraft((current) => ({
                            ...current,
                            email_address: event.target.value.toLowerCase(),
                          }))
                        }
                        placeholder="offers@stonegatehb.com"
                        required
                        type="email"
                        value={draft.email_address}
                      />
                    </label>
                  ) : null}
                  <label>
                    <span>Display name</span>
                    <input
                      maxLength={255}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          display_name: event.target.value,
                        }))
                      }
                      required
                      value={draft.display_name}
                    />
                  </label>
                  {creating ? (
                    <label>
                      <span>Address type</span>
                      <select
                        onChange={(event) =>
                          setDraft((current) => ({
                            ...current,
                            alias_type: event.target.value as AliasDraft["alias_type"],
                          }))
                        }
                        value={draft.alias_type}
                      >
                        <option value="department">Department</option>
                        <option value="named">Named employee</option>
                        <option value="contractor">Contractor</option>
                      </select>
                    </label>
                  ) : null}
                  <label>
                    <span>Purpose</span>
                    <input
                      maxLength={80}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          purpose_key: event.target.value
                            .toLowerCase()
                            .replace(/[^a-z0-9]+/g, "_")
                            .replace(/^_|_$/g, ""),
                        }))
                      }
                      placeholder="seller_intake"
                      required
                      value={draft.purpose_key}
                    />
                  </label>
                  <label>
                    <span>Status</span>
                    <select
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          status: event.target.value as AliasDraft["status"],
                        }))
                      }
                      value={draft.status}
                    >
                      <option value="active">Active</option>
                      <option value="reserved">Reserved</option>
                      <option value="disabled">Disabled</option>
                    </select>
                  </label>
                  <label>
                    <span>Owner</span>
                    <select
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          owner_user_id: event.target.value,
                        }))
                      }
                      value={draft.owner_user_id}
                    >
                      <option value="">No individual owner</option>
                      {users.map((user) => (
                        <option key={user.id} value={user.id}>
                          {user.display_name} · {user.role_keys.map(labelize).join(", ")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Routing team</span>
                    <select
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          assigned_team_id: event.target.value,
                        }))
                      }
                      value={draft.assigned_team_id}
                    >
                      <option value="">No team</option>
                      {teams.map((team) => (
                        <option key={team.id} value={team.id}>
                          {team.name} · {labelize(team.team_type)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className={styles.toggleRow}>
                  <label>
                    <input
                      checked={draft.inbound_enabled}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          inbound_enabled: event.target.checked,
                        }))
                      }
                      type="checkbox"
                    />
                    Receive
                  </label>
                  <label>
                    <input
                      checked={draft.outbound_enabled}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          outbound_enabled: event.target.checked,
                        }))
                      }
                      type="checkbox"
                    />
                    Send
                  </label>
                  <label>
                    <input
                      checked={draft.is_default}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          is_default: event.target.checked,
                        }))
                      }
                      type="checkbox"
                    />
                    Default sender
                  </label>
                </div>

                <label className={styles.signature}>
                  <span>Signature</span>
                  <textarea
                    maxLength={4000}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        signature_text: event.target.value,
                      }))
                    }
                    placeholder="Name, role, company, and contact details"
                    rows={4}
                    value={draft.signature_text}
                  />
                </label>
              </form>

              {!creating && selectedAlias ? (
                <section className={styles.access}>
                  <div className={styles.sectionHeading}>
                    <div>
                      <span>Direct access</span>
                      <strong>Sender and watcher grants</strong>
                    </div>
                    <UserRoundCog aria-hidden="true" size={19} />
                  </div>
                  <div className={styles.grantControls}>
                    <select
                      aria-label="Team member"
                      onChange={(event) => setGrantUserId(event.target.value)}
                      value={grantUserId}
                    >
                      <option value="">Select team member</option>
                      {users
                        .filter(
                          (user) =>
                            !selectedAlias.grants.some((grant) => grant.user_id === user.id),
                        )
                        .map((user) => (
                          <option key={user.id} value={user.id}>
                            {user.display_name}
                          </option>
                        ))}
                    </select>
                    <select
                      aria-label="Access level"
                      onChange={(event) =>
                        setGrantAccessLevel(event.target.value as "sender" | "watcher")
                      }
                      value={grantAccessLevel}
                    >
                      <option value="sender">Can send</option>
                      <option value="watcher">Notifications only</option>
                    </select>
                    <button disabled={!grantUserId || busy} onClick={saveGrant} type="button">
                      <Plus aria-hidden="true" size={14} />
                      Add
                    </button>
                  </div>
                  <div className={styles.grantList}>
                    {selectedAlias.grants.map((grant) => (
                      <div key={grant.id}>
                        <span>
                          <strong>{grant.user_name}</strong>
                          <small>{labelize(grant.access_level)}</small>
                        </span>
                        <button
                          onClick={() => void revokeGrant(grant.user_id)}
                          title={`Remove ${grant.user_name}`}
                          type="button"
                        >
                          <Trash2 aria-hidden="true" size={14} />
                        </button>
                      </div>
                    ))}
                    {!selectedAlias.grants.length ? (
                      <p>No direct grants. Owner and team routing still apply.</p>
                    ) : null}
                  </div>
                </section>
              ) : null}
            </div>
          </div>
        ) : tab === "routing" ? (
          <div className={styles.routing}>
            <div className={styles.routingHeading}>
              <div>
                <span>Manual review</span>
                <h3>Unresolved inbound email</h3>
              </div>
              <strong>{exceptions.length}</strong>
            </div>
            {exceptions.map((item) => (
              <article key={item.id}>
                <header>
                  <div>
                    <strong>{item.subject || "No subject"}</strong>
                    <span>
                      {item.sender || "Unknown sender"} · {formatDateTime(item.received_at)}
                    </span>
                  </div>
                  <em>{labelize(item.processing_status)}</em>
                </header>
                <p>{item.reason}</p>
                <div>
                  <select
                    aria-label={`Conversation for ${item.subject || "inbound email"}`}
                    onChange={(event) =>
                      setRoutingSelections((current) => ({
                        ...current,
                        [item.id]: event.target.value,
                      }))
                    }
                    value={routingSelections[item.id] ?? ""}
                  >
                    <option value="">Select seller conversation</option>
                    {conversations.map((conversation) => (
                      <option key={conversation.id} value={conversation.id}>
                        {conversation.seller_name} · {conversation.property_address}
                      </option>
                    ))}
                  </select>
                  <button
                    disabled={!routingSelections[item.id] || busy}
                    onClick={() => void resolveException(item.id)}
                    type="button"
                  >
                    Assign
                    <ArrowRight aria-hidden="true" size={14} />
                  </button>
                </div>
              </article>
            ))}
            {!exceptions.length ? (
              <div className={styles.routingEmpty}>
                <Check aria-hidden="true" size={22} />
                <strong>No routing exceptions</strong>
                <span>Inbound email is matching Stonegate conversations normally.</span>
              </div>
            ) : null}
          </div>
        ) : (
          <div className={styles.routing}>
            <div className={styles.routingHeading}>
              <div>
                <span>Operator recovery</span>
                <h3>Failed Resend events</h3>
              </div>
              <strong>{deadLetters.length}</strong>
            </div>
            {deadLetters.map((item) => {
              const reason = requeueReasons[item.id] ?? "";
              return (
                <article key={item.id}>
                  <header>
                    <div>
                      <strong>{item.subject || labelize(item.event_type)}</strong>
                      <span>
                        {item.sender || item.provider_message_id || "Unknown message"} ·{" "}
                        {formatDateTime(item.processed_at || item.received_at)}
                      </span>
                    </div>
                    <em>{item.attempt_count} attempts</em>
                  </header>
                  <p>{item.error_message || "Processing stopped after repeated failures."}</p>
                  <div>
                    <input
                      aria-label={`Requeue reason for ${item.subject || item.event_type}`}
                      maxLength={500}
                      onChange={(event) =>
                        setRequeueReasons((current) => ({
                          ...current,
                          [item.id]: event.target.value,
                        }))
                      }
                      placeholder="Why is it safe to retry this event?"
                      value={reason}
                    />
                    <button
                      disabled={reason.trim().length < 10 || busy}
                      onClick={() => void requeueDeadLetter(item.id)}
                      type="button"
                    >
                      <RotateCcw aria-hidden="true" size={14} />
                      Requeue
                    </button>
                  </div>
                </article>
              );
            })}
            {!deadLetters.length ? (
              <div className={styles.routingEmpty}>
                <Check aria-hidden="true" size={22} />
                <strong>No failed email events</strong>
                <span>Resend events are processing within their retry budget.</span>
              </div>
            ) : null}
          </div>
        )}
      </section>
  );

  if (variant === "inline") return panel;

  return (
    <div className={styles.backdrop} onMouseDown={onClose} role="presentation">
      {panel}
    </div>
  );
}
