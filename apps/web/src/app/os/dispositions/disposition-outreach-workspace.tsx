"use client";

import {
  AlertTriangle,
  Check,
  CheckCircle2,
  CirclePause,
  CirclePlay,
  ExternalLink,
  FileLock2,
  LoaderCircle,
  Mail,
  MessageSquare,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldCheck,
  Square,
  UsersRound,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import type {
  DispositionOutreachChannel,
  DispositionOutreachDelivery,
  DispositionOutreachWorkspace,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./disposition-outreach-workspace.module.css";

type Request = <T>(path: string, options?: RequestInit) => Promise<T>;
type Selection = Record<string, DispositionOutreachChannel[]>;

const defaultSubject = "Investor opportunity: {property_address}";
const defaultEmail = `Hi {buyer_name},

Stonegate has an investor opportunity at {property_address}. Review the attached approved package and reply if you would like to discuss it.

Package reference: {package_reference}`;
const defaultSms = "Hi {buyer_name}, Stonegate has an investor opportunity at {property_address}. Reply if you would like the approved package. Ref {package_reference}. Reply STOP to opt out.";

const activeStatuses = new Set(["queued", "sending", "paused", "provider_degraded"]);

function dateTime(value: string | null) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function channelLabel(channel: DispositionOutreachChannel) {
  return channel === "email" ? "Email" : "SMS";
}

function shortHash(value: string | null) {
  return value ? `${value.slice(0, 12)}...${value.slice(-8)}` : "Not generated";
}

function statusTone(status: string) {
  if (["completed", "delivered", "replied", "sent"].includes(status)) return "success";
  if (["cancelled", "invalidated", "ineligible", "failed_terminal", "suppressed", "opted_out"].includes(status)) return "danger";
  if (["provider_degraded", "completed_with_failures", "failed_retryable", "delivery_unknown", "paused"].includes(status)) return "warning";
  return "neutral";
}

function deliveryCount(selection: Selection) {
  return Object.values(selection).reduce((total, channels) => total + channels.length, 0);
}

function deliveryLink(delivery: DispositionOutreachDelivery) {
  return delivery.conversation_id
    ? `/os/inbox?conversation=${encodeURIComponent(delivery.conversation_id)}`
    : `/os/buyers?buyer=${encodeURIComponent(delivery.buyer_id)}`;
}

function DeliveryCard({ delivery }: { delivery: DispositionOutreachDelivery }) {
  return (
    <article className={styles.deliveryCard}>
      <header>
        <div>
          <strong>{delivery.buyer_name}</strong>
          <span>{delivery.company_name ?? delivery.destination}</span>
        </div>
        <span className={styles.status} data-tone={statusTone(delivery.status)}>{labelize(delivery.status)}</span>
      </header>
      <dl>
        <div><dt>Channel</dt><dd>{channelLabel(delivery.channel)}</dd></div>
        <div><dt>Destination</dt><dd>{delivery.destination}</dd></div>
        <div><dt>Attempts</dt><dd>{delivery.attempt_count}</dd></div>
        <div><dt>Provider</dt><dd>{delivery.provider ?? "Not submitted"}</dd></div>
      </dl>
      {delivery.exclusion_reason ? <p className={styles.deliveryError}>{delivery.exclusion_reason}</p> : null}
      <Link href={deliveryLink(delivery)}>
        {delivery.conversation_id ? "Open Buyer Inbox" : "Open buyer record"}
        <ExternalLink aria-hidden="true" size={13} />
      </Link>
    </article>
  );
}

export function DispositionOutreachWorkspace({
  canApprove,
  canManage,
  canSendBulk,
  caseId,
  onMessage,
  request,
}: {
  canApprove: boolean;
  canManage: boolean;
  canSendBulk: boolean;
  caseId: string;
  onMessage: (message: string | null) => void;
  request: Request;
}) {
  const [workspace, setWorkspace] = useState<DispositionOutreachWorkspace | null>(null);
  const [selection, setSelection] = useState<Selection>({});
  const [emailSenderId, setEmailSenderId] = useState("");
  const [smsSenderId, setSmsSenderId] = useState("");
  const [emailSubject, setEmailSubject] = useState(defaultSubject);
  const [emailBody, setEmailBody] = useState(defaultEmail);
  const [smsBody, setSmsBody] = useState(defaultSms);
  const [approvalReason, setApprovalReason] = useState("");
  const [attested, setAttested] = useState(false);
  const [controlReason, setControlReason] = useState("");
  const [releaseConfirmed, setReleaseConfirmed] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const initializedRef = useRef(false);

  const latest = workspace?.latest_revision ?? null;
  const cap = workspace?.hard_recipient_cap ?? 25;
  const selectedDeliveryCount = deliveryCount(selection);
  const selectedRecipientCount = Object.values(selection).filter((channels) => channels.length).length;
  const usesEmail = Object.values(selection).some((channels) => channels.includes("email"));
  const usesSms = Object.values(selection).some((channels) => channels.includes("sms"));
  const emailSenders = useMemo(() => workspace?.available_senders.filter((item) => item.channel === "email") ?? [], [workspace]);
  const smsSenders = useMemo(() => workspace?.available_senders.filter((item) => item.channel === "sms") ?? [], [workspace]);

  async function load() {
    setError(null);
    try {
      const next = await request<DispositionOutreachWorkspace>(`/api/v1/dispositions/cases/${caseId}/outreach`);
      setWorkspace(next);
      if (!initializedRef.current) {
        initializedRef.current = true;
        setEmailSenderId(next.available_senders.find((item) => item.channel === "email" && item.is_default)?.id ?? next.available_senders.find((item) => item.channel === "email")?.id ?? "");
        setSmsSenderId(next.available_senders.find((item) => item.channel === "sms" && item.is_default)?.id ?? next.available_senders.find((item) => item.channel === "sms")?.id ?? "");
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Outreach workspace could not be loaded.");
    }
  }

  useEffect(() => {
    let active = true;
    void request<DispositionOutreachWorkspace>(`/api/v1/dispositions/cases/${caseId}/outreach`)
      .then((next) => {
        if (!active) return;
        setWorkspace(next);
        if (!initializedRef.current) {
          initializedRef.current = true;
          setEmailSenderId(next.available_senders.find((item) => item.channel === "email" && item.is_default)?.id ?? next.available_senders.find((item) => item.channel === "email")?.id ?? "");
          setSmsSenderId(next.available_senders.find((item) => item.channel === "sms" && item.is_default)?.id ?? next.available_senders.find((item) => item.channel === "sms")?.id ?? "");
        }
      })
      .catch((loadError) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "Outreach workspace could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, [caseId, request]);

  async function mutate(
    key: string,
    operation: () => Promise<unknown>,
    success: string,
  ) {
    setBusyAction(key);
    setError(null);
    onMessage(null);
    try {
      await operation();
      await load();
      onMessage(success);
      return true;
    } catch (mutationError) {
      const detail = mutationError instanceof Error ? mutationError.message : "Outreach action failed.";
      setError(detail);
      onMessage(detail);
      return false;
    } finally {
      setBusyAction(null);
    }
  }

  function toggleChannel(recipientId: string, channel: DispositionOutreachChannel) {
    setSelection((current) => {
      const channels = current[recipientId] ?? [];
      if (channels.includes(channel)) {
        const nextChannels = channels.filter((item) => item !== channel);
        const next = { ...current };
        if (nextChannels.length) next[recipientId] = nextChannels;
        else delete next[recipientId];
        return next;
      }
      if (deliveryCount(current) >= cap) {
        setError(`Supervised outreach is limited to ${cap} recipient-channel deliveries per revision.`);
        return current;
      }
      return { ...current, [recipientId]: [...channels, channel] };
    });
  }

  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace?.campaign_id || !canManage) return;
    const recipients = Object.entries(selection)
      .filter(([, channels]) => channels.length)
      .map(([campaignRecipientId, channels]) => ({ campaign_recipient_id: campaignRecipientId, channels }));
    const created = await mutate(
      "draft",
      () => request(`/api/v1/dispositions/cases/${caseId}/outreach/drafts`, {
        method: "POST",
        body: JSON.stringify({
          campaign_id: workspace.campaign_id,
          recipients,
          email_sender_alias_id: usesEmail ? emailSenderId : null,
          sms_voice_line_id: usesSms ? smsSenderId : null,
          email_subject: usesEmail ? emailSubject.trim() : null,
          email_body: usesEmail ? emailBody.trim() : null,
          sms_body: usesSms ? smsBody.trim() : null,
        }),
      }),
      "Immutable outreach draft created. Review the exact recipients, senders, and messages before approval.",
    );
    if (created) {
      setApprovalReason("");
      setAttested(false);
    }
  }

  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!latest?.approval_hash || !workspace?.campaign_id || !canApprove) return;
    const approved = await mutate(
      "approve",
      () => request(`/api/v1/dispositions/campaigns/${workspace.campaign_id}/outreach/${latest.id}/approve`, {
        method: "POST",
        body: JSON.stringify({
          expected_lock_version: latest.lock_version,
          expected_approval_hash: latest.approval_hash,
          attestation: attested,
          reason: approvalReason.trim(),
        }),
      }),
      `Outreach revision ${latest.revision_number} approved exactly as previewed. No messages have been sent.`,
    );
    if (approved) {
      setAttested(false);
      setReleaseConfirmed(false);
      setControlReason("");
    }
  }

  async function control(action: "release" | "pause" | "resume" | "cancel-unsent" | "retry-failed", success: string) {
    if (!latest || !workspace?.campaign_id) return;
    const completed = await mutate(
      action,
      () => request(`/api/v1/dispositions/campaigns/${workspace.campaign_id}/outreach/${latest.id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ expected_lock_version: latest.lock_version, reason: controlReason.trim() }),
      }),
      success,
    );
    if (completed) {
      setControlReason("");
      setReleaseConfirmed(false);
    }
  }

  if (!workspace) {
    return (
      <div className={error ? styles.loadError : styles.loading} role={error ? "alert" : "status"}>
        {error ? <AlertTriangle aria-hidden="true" size={20} /> : <LoaderCircle aria-hidden="true" className={styles.spin} size={18} />}
        <div><strong>{error ? "Buyer outreach unavailable" : "Loading governed buyer outreach"}</strong>{error ? <p>{error}</p> : null}</div>
        {error ? <button onClick={() => void load()} type="button">Retry</button> : null}
      </div>
    );
  }

  const canDraft = canManage
    && workspace.readiness_status === "ready"
    && Boolean(workspace.campaign_id)
    && selectedDeliveryCount > 0
    && selectedDeliveryCount <= cap
    && (!usesEmail || Boolean(emailSenderId && emailSubject.trim() && emailBody.trim()))
    && (!usesSms || Boolean(smsSenderId && smsBody.trim()))
    && !(latest && activeStatuses.has(latest.status));
  const canApproveLatest = canApprove && Boolean(latest?.approval_hash) && ["draft", "review_required"].includes(latest?.status ?? "") && approvalReason.trim().length >= 3 && attested;
  const controlReady = controlReason.trim().length >= 3;

  return (
    <div className={styles.workspace}>
      {error ? <p className={styles.error} role="alert">{error}</p> : null}

      <header className={styles.hero}>
        <div>
          <span><ShieldCheck aria-hidden="true" size={16} />Supervised buyer outreach</span>
          <h4>Review once. Send the exact approved revision.</h4>
          <p>Stonegate freezes the package, recipients, destinations, senders, and rendered copy before live release.</p>
        </div>
        <div className={styles.heroStatus} data-status={workspace.readiness_status}>
          <strong>{labelize(workspace.readiness_status)}</strong>
          <span>{workspace.prepared_recipients.length} prepared buyers</span>
          <small>Hard cap {workspace.hard_recipient_cap} deliveries</small>
        </div>
      </header>

      <section aria-labelledby="outreach-readiness" className={styles.panel}>
        <div className={styles.panelHeading}>
          <div><span>Preflight</span><h5 id="outreach-readiness">Release readiness</h5></div>
          <strong>{workspace.blockers.length ? `${workspace.blockers.length} blocked` : "Ready to draft"}</strong>
        </div>
        <div className={styles.readinessGrid}>
          <p data-ready={Boolean(workspace.package_version_id)}>{workspace.package_version_id ? <CheckCircle2 aria-hidden="true" size={15} /> : <XCircle aria-hidden="true" size={15} />}Current approved package</p>
          <p data-ready={Boolean(workspace.campaign_id)}>{workspace.campaign_id ? <CheckCircle2 aria-hidden="true" size={15} /> : <XCircle aria-hidden="true" size={15} />}Prepared recipient pool</p>
          <p data-ready={workspace.available_senders.length > 0}>{workspace.available_senders.length ? <CheckCircle2 aria-hidden="true" size={15} /> : <XCircle aria-hidden="true" size={15} />}Company sender controls</p>
        </div>
        {workspace.blockers.length ? <div className={styles.blockers}>{workspace.blockers.map((item) => <p key={item}><AlertTriangle aria-hidden="true" size={14} />{item}</p>)}</div> : null}
      </section>

      <form className={styles.draftPanel} onSubmit={createDraft}>
        <div className={styles.panelHeading}>
          <div><span>Step 1 - Select</span><h5>Recipients and channels</h5></div>
          <strong>{selectedDeliveryCount}/{cap} deliveries - {selectedRecipientCount} buyers</strong>
        </div>
        <div className={styles.recipientList}>
          {workspace.prepared_recipients.map((recipient) => (
            <article key={recipient.id}>
              <div className={styles.recipientIdentity}><UsersRound aria-hidden="true" size={17} /><span><strong>{recipient.buyer_name}</strong><small>{recipient.company_name ?? "Independent buyer"}</small></span></div>
              <div className={styles.channelChoices}>
                {recipient.available_channels.map((channel) => (
                  <label key={channel}>
                    <input checked={(selection[recipient.id] ?? []).includes(channel)} disabled={!canManage || (selectedDeliveryCount >= cap && !(selection[recipient.id] ?? []).includes(channel))} onChange={() => toggleChannel(recipient.id, channel)} type="checkbox" />
                    {channel === "email" ? <Mail aria-hidden="true" size={14} /> : <MessageSquare aria-hidden="true" size={14} />}
                    <span>{channelLabel(channel)}<small>{channel === "email" ? recipient.captured_email : recipient.captured_phone}</small></span>
                  </label>
                ))}
              </div>
            </article>
          ))}
          {!workspace.prepared_recipients.length ? <p className={styles.empty}>Prepare a qualified recipient pool from the Package tab before drafting outreach.</p> : null}
        </div>

        <div className={styles.copyGrid}>
          <section data-enabled={usesEmail}>
            <header><Mail aria-hidden="true" size={17} /><div><span>Email</span><h5>Sender and exact copy</h5></div></header>
            <label><span>Company sender</span><select disabled={!usesEmail || !canManage} onChange={(event) => setEmailSenderId(event.target.value)} value={emailSenderId}><option value="">Select sender</option>{emailSenders.map((sender) => <option key={sender.id} value={sender.id}>{sender.label} - {sender.address}</option>)}</select></label>
            <label><span>Subject</span><input disabled={!usesEmail || !canManage} maxLength={255} onChange={(event) => setEmailSubject(event.target.value)} value={emailSubject} /></label>
            <label><span>Message template</span><textarea disabled={!usesEmail || !canManage} maxLength={4000} onChange={(event) => setEmailBody(event.target.value)} rows={8} value={emailBody} /></label>
          </section>
          <section data-enabled={usesSms}>
            <header><MessageSquare aria-hidden="true" size={17} /><div><span>SMS</span><h5>Line and exact copy</h5></div></header>
            <label><span>Buyer-relations line</span><select disabled={!usesSms || !canManage} onChange={(event) => setSmsSenderId(event.target.value)} value={smsSenderId}><option value="">Select line</option>{smsSenders.map((sender) => <option key={sender.id} value={sender.id}>{sender.label} - {sender.address}</option>)}</select></label>
            <label><span>Message template</span><textarea disabled={!usesSms || !canManage} maxLength={1000} onChange={(event) => setSmsBody(event.target.value)} rows={10} value={smsBody} /></label>
          </section>
        </div>
        <p className={styles.templateHelp}>Allowed placeholders: {`{buyer_name}`}, {`{company_name}`}, {`{property_address}`}, and {`{package_reference}`}. Private seller economics are never available here.</p>
        <button className={styles.primaryButton} disabled={!canDraft || busyAction !== null} type="submit">{busyAction === "draft" ? <LoaderCircle aria-hidden="true" className={styles.spin} size={15} /> : <FileLock2 aria-hidden="true" size={15} />}Create immutable draft</button>
      </form>

      {latest ? (
        <>
          <section aria-labelledby="exact-preview" className={styles.panel}>
            <div className={styles.panelHeading}>
              <div><span>Step 2 - Exact preview</span><h5 id="exact-preview">Revision {latest.revision_number}</h5></div>
              <span className={styles.status} data-tone={statusTone(latest.status)}>{labelize(latest.status)}</span>
            </div>
            <dl className={styles.integrityFacts}>
              <div><dt>Approval hash</dt><dd title={latest.approval_hash ?? undefined}>{shortHash(latest.approval_hash)}</dd></div>
              <div><dt>Recipient manifest</dt><dd title={latest.recipient_manifest_hash}>{shortHash(latest.recipient_manifest_hash)}</dd></div>
              <div><dt>Approved PDF</dt><dd title={latest.artifact_sha256}>{shortHash(latest.artifact_sha256)}</dd></div>
              <div><dt>Mode</dt><dd>{labelize(latest.mode)}</dd></div>
            </dl>
            <div className={styles.messagePreviews}>
              {latest.deliveries.map((delivery) => (
                <article key={delivery.id}>
                  <header><div><strong>{delivery.buyer_name}</strong><span>{channelLabel(delivery.channel)} - {delivery.destination}</span></div><span className={styles.status} data-tone={delivery.eligibility_status === "eligible" ? "success" : "danger"}>{labelize(delivery.eligibility_status)}</span></header>
                  {delivery.subject ? <p><strong>Subject:</strong> {delivery.subject}</p> : null}
                  <pre>{delivery.body}</pre>
                  <small>Body fingerprint {shortHash(delivery.body_hash)}{delivery.exclusion_reason ? ` - ${delivery.exclusion_reason}` : ""}</small>
                </article>
              ))}
            </div>
          </section>

          {["draft", "review_required"].includes(latest.status) ? (
            <form className={styles.approvalPanel} onSubmit={approve}>
              <div className={styles.panelHeading}><div><span>Step 3 - Human approval</span><h5>Approve this exact revision</h5></div><ShieldCheck aria-hidden="true" size={18} /></div>
              <label className={styles.attestation}><input checked={attested} disabled={!canApprove} onChange={(event) => setAttested(event.target.checked)} type="checkbox" /><span>I reviewed every recipient, destination, sender, rendered message, and the approved package fingerprint shown above.</span></label>
              <label><span>Approval reason</span><textarea disabled={!canApprove} maxLength={2000} onChange={(event) => setApprovalReason(event.target.value)} placeholder="Why this exact outreach revision is approved" rows={3} value={approvalReason} /></label>
              <button className={styles.primaryButton} disabled={!canApproveLatest || busyAction !== null} type="submit">{busyAction === "approve" ? <LoaderCircle aria-hidden="true" className={styles.spin} size={15} /> : <Check aria-hidden="true" size={15} />}Approve exact revision</button>
              {!canApprove ? <p className={styles.permissionNote}>A disposition manager must approve live buyer outreach.</p> : null}
            </form>
          ) : null}

          {["approved", "queued", "sending", "paused", "provider_degraded", "completed_with_failures"].includes(latest.status) ? (
            <section className={styles.controlPanel}>
              <div className={styles.panelHeading}><div><span>Release controls</span><h5>Supervised delivery</h5></div><Send aria-hidden="true" size={18} /></div>
              <label><span>Control reason</span><textarea disabled={!canManage && !(canApprove && canSendBulk)} maxLength={2000} onChange={(event) => setControlReason(event.target.value)} placeholder="Required audit note for the next control" rows={2} value={controlReason} /></label>
              {latest.status === "approved" || latest.status === "provider_degraded" ? <label className={styles.attestation}><input checked={releaseConfirmed} disabled={!canApprove || !canSendBulk} onChange={(event) => setReleaseConfirmed(event.target.checked)} type="checkbox" /><span>I understand release can send the exact approved messages to eligible recipients.</span></label> : null}
              <div className={styles.controlActions}>
                {latest.status === "approved" ? <button className={styles.releaseButton} disabled={!canApprove || !canSendBulk || !controlReady || !releaseConfirmed || busyAction !== null} onClick={() => void control("release", "Approved outreach released to the supervised delivery queue.")} type="button"><Send aria-hidden="true" size={15} />Release approved outreach</button> : null}
                {["queued", "sending", "provider_degraded"].includes(latest.status) ? <button disabled={!canManage || !controlReady || busyAction !== null} onClick={() => void control("pause", "Unsent outreach paused.")} type="button"><CirclePause aria-hidden="true" size={15} />Pause unsent</button> : null}
                {["paused", "provider_degraded"].includes(latest.status) ? <button disabled={!canApprove || !canSendBulk || !controlReady || !releaseConfirmed || busyAction !== null} onClick={() => void control("resume", "Approved outreach resumed after a fresh preflight.")} type="button"><CirclePlay aria-hidden="true" size={15} />Resume approved outreach</button> : null}
                {!["cancelled", "completed", "invalidated"].includes(latest.status) ? <button disabled={!canManage || !controlReady || busyAction !== null} onClick={() => void control("cancel-unsent", "Remaining unsent outreach cancelled.")} type="button"><Square aria-hidden="true" size={14} />Cancel unsent</button> : null}
                {["completed_with_failures", "provider_degraded", "paused"].includes(latest.status) ? <button disabled={!canApprove || !canSendBulk || !controlReady || busyAction !== null} onClick={() => void control("retry-failed", "Safely retryable deliveries returned to the supervised queue.")} type="button"><RotateCcw aria-hidden="true" size={14} />Retry safe failures</button> : null}
                <button disabled={busyAction !== null} onClick={() => void load()} type="button"><RefreshCw aria-hidden="true" size={14} />Refresh status</button>
              </div>
              {canApprove && !canSendBulk ? <p className={styles.permissionNote}>Live release, resume, and retry also require the bulk-communications permission.</p> : null}
            </section>
          ) : null}

          <section aria-labelledby="delivery-monitor" className={styles.panel}>
            <div className={styles.panelHeading}>
              <div><span>Delivery monitor</span><h5 id="delivery-monitor">Recipient-level evidence</h5></div>
              <strong>{latest.deliveries.length} deliveries</strong>
            </div>
            <div className={styles.deliveryCounts}>{Object.entries(latest.delivery_counts).map(([status, count]) => <span data-tone={statusTone(status)} key={status}><strong>{count}</strong>{labelize(status)}</span>)}</div>
            <div className={styles.deliveryList}>{latest.deliveries.map((delivery) => <DeliveryCard delivery={delivery} key={delivery.id} />)}</div>
          </section>

          <section aria-labelledby="revision-history" className={styles.panel}>
            <div className={styles.panelHeading}><div><span>Immutable audit trail</span><h5 id="revision-history">Revision history</h5></div><strong>{workspace.revisions.length}</strong></div>
            <div className={styles.revisionList}>{workspace.revisions.map((revision) => <article key={revision.id}><div><strong>Revision {revision.revision_number}</strong><span className={styles.status} data-tone={statusTone(revision.status)}>{labelize(revision.status)}</span></div><span>Created {dateTime(revision.created_at)}</span><small>Approval {shortHash(revision.approval_hash)} - {revision.deliveries.length} deliveries</small></article>)}</div>
          </section>
        </>
      ) : null}
    </div>
  );
}
