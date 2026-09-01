"use client";

import {
  AlertTriangle,
  Check,
  CircleOff,
  Download,
  ExternalLink,
  FileArchive,
  FileCheck2,
  Link2,
  LoaderCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  UsersRound,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  DispositionProviderEvidence,
  DispositionProviderListingRevision,
  DispositionProviderManualStatus,
  DispositionProviderWorkspace,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./disposition-provider-workspace.module.css";

type Request = <T>(path: string, options?: RequestInit) => Promise<T>;
type DownloadFile = (path: string, fileName: string) => Promise<void>;

const providerStatuses: DispositionProviderManualStatus[] = [
  "draft",
  "active",
  "paused",
  "under_contract",
  "sold",
  "archived",
  "unknown",
];

function dateTime(value: string | null) {
  if (!value) return "Not recorded";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function money(value: number | null) {
  if (value == null) return "Not recorded";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value / 100);
}

function dollarsToCents(value: FormDataEntryValue | null) {
  const normalized = String(value ?? "").replace(/[$,]/g, "").trim();
  return normalized ? Math.round(Number(normalized) * 100) : null;
}

function localDateTimeValue() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

function approvalRevision(data: DispositionProviderWorkspace) {
  return data.revisions.find((item) => item.status === "approved" && item.is_current)
    ?? null;
}

function latestRevisionNumber(data: DispositionProviderWorkspace) {
  return data.revisions.reduce((latest, item) => Math.max(latest, item.revision_number), 0);
}

function revisionIsPreliminary(revision: DispositionProviderListingRevision) {
  return revision.package_is_preliminary === true
    || (revision.package_status ?? "approved") !== "approved"
    || revision.package_was_current_at_prepare === false
    || revision.package_is_current_now === false;
}

function currentAtPrepareLabel(revision: DispositionProviderListingRevision) {
  if (revision.package_was_current_at_prepare === true) return "Current at preparation";
  if (revision.package_was_current_at_prepare === false) return "Facts had changed before preparation";
  return "Preparation currentness not recorded";
}

function currentNowLabel(revision: DispositionProviderListingRevision) {
  if (revision.package_is_current_now === true) return "Package and source facts are current now";
  if (revision.package_is_current_now === false) return "Package or source facts changed since preparation";
  return "Current package state not reported";
}

function eventSummary(event: DispositionProviderEvidence) {
  const buyer = event.buyer_name || event.buyer_email || event.buyer_phone;
  if (event.event_type === "offer") {
    return `${buyer ?? "Unidentified buyer"} - ${money(event.offer_amount_cents)}`;
  }
  return buyer ?? event.message ?? "Provider activity recorded without buyer identity";
}

export function DispositionProviderWorkspace({
  canApprove,
  canEditDeals,
  canManage,
  caseId,
  download,
  onMessage,
  onWorkspaceChanged,
  request,
}: {
  canApprove: boolean;
  canEditDeals: boolean;
  canManage: boolean;
  caseId: string;
  download: DownloadFile;
  onMessage: (message: string | null) => void;
  onWorkspaceChanged: () => Promise<unknown> | unknown;
  request: Request;
}) {
  const requestRef = useRef(request);
  const [data, setData] = useState<DispositionProviderWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [approvalRevisionId, setApprovalRevisionId] = useState<string | null>(null);
  const [manualEventType, setManualEventType] = useState<"inquiry" | "offer" | "engagement">("inquiry");

  useEffect(() => {
    requestRef.current = request;
  }, [request]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const workspace = await requestRef.current<DispositionProviderWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/provider`,
      );
      setData(workspace);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Unable to load the provider workspace.");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    let active = true;
    requestRef.current<DispositionProviderWorkspace>(
      `/api/v1/dispositions/cases/${caseId}/provider`,
    )
      .then((workspace) => {
        if (!active) return;
        setData(workspace);
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setLoadError(error instanceof Error ? error.message : "Unable to load the provider workspace.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [caseId]);

  async function mutate(
    key: string,
    work: () => Promise<unknown>,
    success: string,
    allowed: boolean,
  ) {
    if (!allowed) {
      setNotice("Your role can review this handoff but cannot perform that action.");
      return false;
    }
    setBusyAction(key);
    setNotice(null);
    onMessage(null);
    try {
      await work();
      await load();
      try {
        await onWorkspaceChanged();
      } catch {
        // The provider mutation succeeded; aggregate readiness can be retried separately.
      }
      setNotice(success);
      onMessage(success);
      return true;
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Unable to update the provider handoff.";
      setNotice(detail);
      onMessage(detail);
      return false;
    } finally {
      setBusyAction(null);
    }
  }

  const approvedRevision = useMemo(() => data ? approvalRevision(data) : null, [data]);
  const shoppingPackage = data?.available_package ?? data?.approved_package ?? null;
  const shoppingPackageStatus = data?.available_package?.status ?? (data?.approved_package ? "approved" : null);
  const shoppingIsPreliminary = Boolean(
    shoppingPackage
      && (shoppingPackageStatus !== "approved" || shoppingPackage.is_current === false),
  );
  const canPrepare = Boolean(data?.eligible && shoppingPackage && data.permissions.can_prepare && canEditDeals && canManage);
  const canApproveRevision = Boolean(data?.eligible && data.permissions.can_approve && canApprove);
  const canRecordManual = Boolean(data?.eligible && data.permissions.can_record_manual && canEditDeals && canManage);
  const canDisconnect = Boolean(data?.permissions.can_disconnect && canEditDeals && canManage);
  const canExport = Boolean(data?.permissions.can_export);
  const isDisconnected = data?.listing?.status === "disconnected";
  const hasExternalLink = Boolean(data?.listing?.external_property_id && data.listing.external_url);
  const isManuallyPublished = Boolean(
    data?.listing?.status === "manual_published"
      && data.listing.external_property_id
      && data.listing.external_url,
  );

  async function prepareRevision() {
    if (!data) return;
    await mutate(
      "prepare",
      () => requestRef.current(
        `/api/v1/dispositions/cases/${caseId}/provider/listing-revisions`,
        {
          method: "POST",
          body: JSON.stringify({ expected_latest_revision: latestRevisionNumber(data) }),
        },
      ),
      `A new manual handoff revision was prepared from the ${shoppingIsPreliminary ? "Preliminary" : "approved"} Stonegate package.`,
      canPrepare,
    );
  }

  async function approveRevision(event: FormEvent<HTMLFormElement>, revision: DispositionProviderListingRevision) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const saved = await mutate(
      `approve-${revision.id}`,
      () => requestRef.current(
        `/api/v1/dispositions/cases/${caseId}/provider/listing-revisions/${revision.id}/approve`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_lock_version: revision.lock_version,
            attestation: values.get("attestation") === "on",
            reason: String(values.get("reason") ?? "").trim(),
          }),
        },
      ),
      `Revision ${revision.revision_number} approved for manual publication. No provider action was taken.`,
      canApproveRevision,
    );
    if (saved) {
      setApprovalRevisionId(null);
      form.reset();
    }
  }

  async function recordManualLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data?.listing || !approvedRevision) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    await mutate(
      "manual-link",
      () => requestRef.current(
        `/api/v1/dispositions/cases/${caseId}/provider/manual-link`,
        {
          method: "POST",
          body: JSON.stringify({
            revision_id: approvedRevision.id,
            expected_listing_version: data.listing?.lock_version,
            external_property_id: String(values.get("external_property_id") ?? "").trim(),
            external_url: String(values.get("external_url") ?? "").trim(),
            provider_status: values.get("provider_status"),
            note: String(values.get("note") ?? "").trim() || null,
          }),
        },
      ),
      "The manually published InvestorLift property was linked to this Stonegate record.",
      canRecordManual,
    );
  }

  async function recordManualEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const eventType = String(values.get("event_type") ?? "inquiry");
    const saved = await mutate(
      "manual-event",
      () => requestRef.current(
        `/api/v1/dispositions/cases/${caseId}/provider/manual-events`,
        {
          method: "POST",
          body: JSON.stringify({
            event_type: eventType,
            external_event_id: String(values.get("external_event_id") ?? "").trim() || null,
            occurred_at: new Date(String(values.get("occurred_at"))).toISOString(),
            buyer_name: String(values.get("buyer_name") ?? "").trim() || null,
            buyer_email: String(values.get("buyer_email") ?? "").trim() || null,
            buyer_phone: String(values.get("buyer_phone") ?? "").trim() || null,
            offer_amount_cents: eventType === "offer"
              ? dollarsToCents(values.get("offer_amount"))
              : null,
            message: String(values.get("message") ?? "").trim() || null,
            metadata: { capture_method: "stonegate_manual_investorlift_review" },
          }),
        },
      ),
      "InvestorLift activity was staged as evidence. It will not select a buyer or send a response.",
      canRecordManual,
    );
    if (saved) {
      form.reset();
      setManualEventType("inquiry");
    }
  }

  async function reviewEvent(event: FormEvent<HTMLFormElement>, evidence: DispositionProviderEvidence) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const reviewStatus = String(values.get("review_status") ?? "reviewed");
    await mutate(
      `review-event-${evidence.id}`,
      () => requestRef.current(
        `/api/v1/dispositions/cases/${caseId}/provider/manual-events/${evidence.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_lock_version: evidence.lock_version,
            review_status: reviewStatus,
            review_note: String(values.get("review_note") ?? "").trim() || null,
          }),
        },
      ),
      reviewStatus === "dismissed"
        ? "Provider evidence dismissed and preserved in history."
        : "Provider evidence marked reviewed. Buyer selection remains a separate human decision.",
      canRecordManual,
    );
  }

  async function recordManualRefresh(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await mutate(
      "manual-refresh",
      () => requestRef.current(
        `/api/v1/dispositions/cases/${caseId}/provider/manual-refresh`,
        {
          method: "POST",
          body: JSON.stringify({
            provider_status: values.get("provider_status"),
            external_property_id: String(values.get("external_property_id") ?? "").trim() || null,
            external_url: String(values.get("external_url") ?? "").trim() || null,
            note: String(values.get("note") ?? "").trim() || null,
          }),
        },
      ),
      "The latest manually observed InvestorLift status was recorded. No provider API was called.",
      canRecordManual,
    );
  }

  async function disconnect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await mutate(
      "disconnect",
      () => requestRef.current(
        `/api/v1/dispositions/cases/${caseId}/provider/disconnect`,
        {
          method: "POST",
          body: JSON.stringify({
            attestation: values.get("attestation") === "on",
            reason: String(values.get("reason") ?? "").trim(),
          }),
        },
      ),
      "InvestorLift handoff disconnected. Stonegate history and owned buyer operations remain intact.",
      canDisconnect,
    );
  }

  if (loading && !data) {
    return <div aria-busy="true" aria-live="polite" className={styles.loading} role="status"><LoaderCircle aria-hidden="true" className={styles.spin} size={18} />Loading provider handoff</div>;
  }

  if (loadError || !data) {
    return <div className={styles.loadError} role="alert"><AlertTriangle aria-hidden="true" size={25} /><strong>Provider workspace unavailable</strong><p>{loadError ?? "The provider workspace did not return a record."}</p><button onClick={() => void load()} type="button"><RefreshCw aria-hidden="true" size={14} />Retry</button></div>;
  }

  const stagedCount = data.staged_events.filter((item) => item.review_status === "staged").length;
  const prepareComplete = data.revisions.length > 0;
  const approveComplete = Boolean(approvedRevision);
  const publishComplete = isManuallyPublished;

  return (
    <section aria-label="InvestorLift manual handoff" className={styles.workspace} id="provider-handoff" tabIndex={-1}>
      {notice ? <p aria-live="polite" className={/unable|cannot|blocked|required|failed|error/i.test(notice) ? styles.error : styles.success} role="status">{notice}</p> : null}

      <header className={styles.hero}>
        <div>
          <span className={styles.eyebrow}><UploadCloud aria-hidden="true" size={15} />House disposition provider</span>
          <h4>{data.provider_label} handoff</h4>
          <p>Prepare an exact public handoff from the latest usable package while checklist work continues, publish it manually, then preserve provider activity here.</p>
        </div>
        <div className={styles.heroStatus}>
          <strong>Manual-only</strong>
          <span>No live sync</span>
          <small>{data.account ? labelize(data.account.status) : "Account record creates on first preparation"}</small>
        </div>
      </header>

      <aside className={styles.boundary} role="note">
        <ShieldCheck aria-hidden="true" size={20} />
        <div>
          <strong>The direct InvestorLift API contract is unverified.</strong>
          <p>Stonegate does not claim a live connection and does not request provider credentials in this workspace.</p>
          <ul>
            <li>Every handoff preserves whether its source package was approved or Preliminary.</li>
            <li>Private Stonegate economics are never included in the provider bundle.</li>
            <li>Inquiries, engagement, and offers stay staged until a person reviews them.</li>
          </ul>
        </div>
      </aside>

      {!data.eligible ? (
        <div className={styles.empty} role="status">
          <CircleOff aria-hidden="true" size={26} />
          <h5>InvestorLift handoff is not available for this case</h5>
          <p>{data.eligibility_blockers.join(" ") || "This workflow is limited to House disposition cases."}</p>
        </div>
      ) : (
        <>
          <section className={styles.workflow}>
            <header><span>Manual publication workflow</span><h5>One governed path from Stonegate to InvestorLift</h5><p>Each step records exact evidence without depending on provider uptime.</p></header>
            <div className={styles.steps}>
              <article data-complete={prepareComplete}><span>{prepareComplete ? <Check size={13} /> : "1"}</span><strong>Prepare</strong><p>Freeze a public revision from the latest usable package.</p></article>
              <article data-complete={approveComplete}><span>{approveComplete ? <Check size={13} /> : "2"}</span><strong>Approve exact handoff</strong><p>A permitted reviewer approves the exact public payload.</p></article>
              <article data-complete={approveComplete}><span>{approveComplete ? <Check size={13} /> : "3"}</span><strong>Download</strong><p>Download the approved bundle; private economics stay in Stonegate.</p></article>
              <article data-complete={publishComplete}><span>{publishComplete ? <Check size={13} /> : "4"}</span><strong>Publish manually</strong><p>Post the approved bundle in InvestorLift and record its ID and URL.</p></article>
              <article data-complete={stagedCount === 0 && data.staged_events.length > 0}><span>5</span><strong>Record and review</strong><p>Stage inquiries and offers, then review each item before action.</p></article>
            </div>
          </section>

          <div className={styles.layout}>
            <div className={styles.column}>
              <section className={styles.panel}>
                <header className={styles.panelHeading}><div><span>Release control</span><h5>Public package revisions</h5><p>Preparing a new revision never publishes or sends anything.</p></div><strong>{shoppingPackage ? `Stonegate package v${shoppingPackage.version_number} - ${shoppingIsPreliminary ? "Preliminary" : "Approved"}` : "Artifact required"}</strong></header>
                <div className={styles.panelActions}>
                  <button className={styles.button} disabled={Boolean(busyAction) || !canPrepare} onClick={() => void prepareRevision()} type="button">{busyAction === "prepare" ? <LoaderCircle className={styles.spin} size={14} /> : <Plus size={14} />}Prepare latest package</button>
                  <button className={styles.secondaryButton} disabled={Boolean(busyAction)} onClick={() => void load()} type="button"><RefreshCw size={14} />Reload Stonegate state</button>
                  <button className={styles.secondaryButton} disabled={Boolean(busyAction) || !canExport} onClick={() => void download(`/api/v1/dispositions/cases/${caseId}/provider/export?format=json`, "stonegate-investorlift-handoff.json")} type="button"><Download size={14} />Export history</button>
                </div>
                {!shoppingPackage ? <p className={styles.permissionNote}>Build or upload a concrete buyer-safe package artifact before preparing a provider revision.</p> : shoppingIsPreliminary ? <p className={styles.permissionNote}>This handoff will remain visibly Preliminary. Package checklist gaps do not disable preparation.</p> : null}
                {!canPrepare ? <p className={styles.permissionNote}>Preparing revisions requires deal-edit and disposition-management access.</p> : null}
                <div className={styles.revisionList}>
                  {data.revisions.map((revision) => (
                    <article className={styles.revisionCard} key={revision.id}>
                      <div className={styles.revisionIdentity}><span>Revision {revision.revision_number}</span><strong>{revision.is_current ? "Current handoff" : "Historical handoff"}</strong><small>Created {dateTime(revision.created_at)}</small></div>
                      <div className={styles.revisionEvidence}>
                        <span className={styles.revisionStatus} data-status={revision.status}>{labelize(revision.status)}</span>
                        <small>Frozen source {labelize(revision.package_status ?? "approved")}</small>
                        <small>Current handoff label: {revisionIsPreliminary(revision) ? "Preliminary" : "Approved"}</small>
                        <small>{currentAtPrepareLabel(revision)}</small>
                        <small>{currentNowLabel(revision)}</small>
                        <small>Payload {revision.public_payload_sha256.slice(0, 12)}</small>
                        <small>Package {revision.package_source_fingerprint.slice(0, 12)}</small>
                      </div>
                      <div className={styles.revisionDecision}>{revision.approved_at ? <><strong>Approved {dateTime(revision.approved_at)}</strong><small>{revision.approval_reason}</small></> : <><strong>Human approval required</strong><small>Review the exact public JSON below before approval.</small></>}</div>
                      <div className={styles.panelActions}>
                        {revision.status === "draft" ? <button className={styles.inlineButton} disabled={Boolean(busyAction) || !canApproveRevision} onClick={() => setApprovalRevisionId((current) => current === revision.id ? null : revision.id)} type="button"><FileCheck2 size={13} />Review</button> : null}
                        {revision.status === "approved" ? <button className={styles.inlineButton} disabled={Boolean(busyAction) || !canExport} onClick={() => void download(`/api/v1/dispositions/cases/${caseId}/provider/listing-revisions/${revision.id}/bundle`, `stonegate-investorlift-revision-${revision.revision_number}.json`)} type="button"><FileArchive size={13} />Download</button> : null}
                      </div>
                      <details><summary>View exact public payload</summary><pre>{JSON.stringify(revision.public_payload, null, 2)}</pre></details>
                      {approvalRevisionId === revision.id ? <form className={styles.form} onSubmit={(event) => void approveRevision(event, revision)}><label><span>Approval reason</span><textarea name="reason" placeholder="Why this exact public package is ready for manual publication" required /></label><label className={styles.attestation}><input name="attestation" required type="checkbox" /><span>I reviewed this exact public payload and approve it for manual publication in InvestorLift.</span></label><div className={styles.formFooter}><button className={styles.secondaryButton} onClick={() => setApprovalRevisionId(null)} type="button">Cancel</button><button disabled={Boolean(busyAction) || !canApproveRevision} type="submit">Approve exact handoff</button></div></form> : null}
                    </article>
                  ))}
                  {!data.revisions.length ? <div className={styles.empty}><FileArchive size={24} /><h5>No provider revision prepared</h5><p>Prepare the latest usable Stonegate package to begin. Nothing will be published.</p></div> : null}
                </div>
              </section>

              <section className={styles.panel}>
                <header className={styles.panelHeading}><div><span>Human review queue</span><h5>Staged InvestorLift activity</h5><p>These records are evidence only. They cannot select a buyer or accept an offer.</p></div><strong>{stagedCount} awaiting review</strong></header>
                {isManuallyPublished ? <form className={styles.form} onSubmit={(event) => void recordManualEvent(event)}>
                  <div className={styles.formGrid}>
                    <label><span>Activity</span><select name="event_type" onChange={(event) => setManualEventType(event.target.value as "inquiry" | "offer" | "engagement")} value={manualEventType}><option value="inquiry">Inquiry</option><option value="engagement">Engagement</option><option value="offer">Offer</option></select></label>
                    <label><span>Occurred at</span><input defaultValue={localDateTimeValue()} name="occurred_at" required type="datetime-local" /></label>
                    <label><span>Buyer name</span><input name="buyer_name" /></label>
                    <label><span>Buyer email</span><input name="buyer_email" type="email" /></label>
                    <label><span>Buyer phone</span><input name="buyer_phone" type="tel" /></label>
                    <label><span>Offer amount{manualEventType === "offer" ? " - required" : ""}</span><input min="1" name="offer_amount" placeholder="Required only for an offer" required={manualEventType === "offer"} step="0.01" type="number" /></label>
                    <label data-wide="true"><span>InvestorLift event ID</span><input name="external_event_id" /><small>Optional provider reference used for replay protection.</small></label>
                    <label data-wide="true"><span>Message or notes</span><textarea name="message" /></label>
                  </div>
                  <div className={styles.formFooter}><button disabled={Boolean(busyAction) || !canRecordManual} type="submit">Stage provider evidence</button></div>
                </form> : <p className={styles.permissionNote}>Record the manually published InvestorLift property before adding inquiries, engagement, or offers.</p>}
                <div className={styles.eventList}>
                  {data.staged_events.map((evidence) => <article className={styles.eventCard} key={evidence.id}><div><small>{labelize(evidence.event_type)} - {dateTime(evidence.occurred_at)}</small><strong>{eventSummary(evidence)}</strong>{evidence.message ? <p>{evidence.message}</p> : null}<span>Evidence {evidence.evidence_sha256.slice(0, 12)}{evidence.external_event_id ? ` - Provider event ${evidence.external_event_id}` : ""}</span></div><span className={styles.eventStatus} data-status={evidence.review_status}>{labelize(evidence.review_status)}</span>{evidence.review_status === "staged" ? <form className={styles.eventActions} onSubmit={(event) => void reviewEvent(event, evidence)}><select aria-label={`Review decision for ${eventSummary(evidence)}`} defaultValue="reviewed" name="review_status"><option value="reviewed">Mark reviewed</option><option value="dismissed">Dismiss</option></select><input aria-label={`Review note for ${eventSummary(evidence)}`} name="review_note" placeholder="Optional review note" /><button className={styles.inlineButton} disabled={Boolean(busyAction) || !canRecordManual} type="submit">Save review</button></form> : evidence.review_note ? <p>{evidence.review_note}</p> : null}</article>)}
                  {!data.staged_events.length ? <div className={styles.empty}><UsersRound size={24} /><h5>No provider activity recorded</h5><p>After manual publication, record InvestorLift inquiries and offers here for human review.</p></div> : null}
                </div>
              </section>
            </div>

            <div className={styles.column}>
              <section className={styles.panel}>
                <header className={styles.panelHeading}><div><span>Manual publication record</span><h5>InvestorLift property link</h5><p>Publish the approved bundle in InvestorLift first, then copy its property ID and URL here.</p></div><strong>{isManuallyPublished ? "Recorded" : hasExternalLink ? "Update required" : "Not recorded"}</strong></header>
                {approvedRevision && revisionIsPreliminary(approvedRevision) ? <p className={styles.permissionNote}>Current handoff label: Preliminary. Its frozen source was preliminary or the package or source facts changed. Prepare a new current revision to produce an Approved handoff; this warning does not erase the existing approval or publication history.</p> : null}
                {hasExternalLink && !isManuallyPublished && !isDisconnected ? <p className={styles.permissionNote}>The ID and URL below belong to an earlier manual publication. Publish the newly approved revision, then confirm or replace those values to record the updated InvestorLift publication.</p> : null}
                {data.listing && approvedRevision && !isDisconnected ? <form className={styles.form} onSubmit={(event) => void recordManualLink(event)}>
                  <label><span>InvestorLift property ID</span><input defaultValue={data.listing.external_property_id ?? ""} name="external_property_id" required /></label>
                  <label><span>InvestorLift property URL</span><input defaultValue={data.listing.external_url ?? ""} name="external_url" required type="url" /></label>
                  <label><span>Provider status</span><select defaultValue={data.listing.provider_status ?? "active"} name="provider_status">{providerStatuses.map((status) => <option key={status} value={status}>{labelize(status)}</option>)}</select></label>
                  <label><span>Publication note</span><textarea name="note" placeholder="Optional source or publication note" /></label>
                  <button disabled={Boolean(busyAction) || !canRecordManual} type="submit"><Link2 size={14} />Record manual publication</button>
                </form> : <p className={styles.permissionNote}>{isDisconnected ? "This handoff is disconnected; its history remains available." : "Approve a provider revision before recording the manual publication."}</p>}
                {hasExternalLink && data.listing ? <dl className={styles.linkFacts}><div><dt>External property ID</dt><dd>{data.listing.external_property_id}</dd></div><div><dt>Provider status</dt><dd>{labelize(data.listing.provider_status ?? "unknown")}</dd></div><div><dt>{isManuallyPublished ? "Manual publication" : "Previous manual publication"}</dt><dd>{dateTime(data.listing.manual_published_at)}</dd></div><div><dt>Last manual check</dt><dd>{dateTime(data.listing.last_refreshed_at)}</dd></div><div><dt>InvestorLift record</dt><dd><a href={data.listing.external_url ?? "#"} rel="noreferrer" target="_blank">Open record <ExternalLink size={11} /></a></dd></div></dl> : null}
              </section>

              {isManuallyPublished && data.listing && !isDisconnected ? <section className={styles.panel}>
                <header className={styles.panelHeading}><div><span>Manual status check</span><h5>Record what staff observed</h5><p>This saves a manual observation. It does not query InvestorLift.</p></div><RefreshCw size={17} /></header>
                <form className={styles.form} onSubmit={(event) => void recordManualRefresh(event)}>
                  <label><span>Provider status</span><select defaultValue={data.listing.provider_status ?? "unknown"} name="provider_status">{providerStatuses.map((status) => <option key={status} value={status}>{labelize(status)}</option>)}</select></label>
                  <label><span>InvestorLift property ID</span><input defaultValue={data.listing.external_property_id ?? ""} name="external_property_id" /></label>
                  <label><span>InvestorLift property URL</span><input defaultValue={data.listing.external_url ?? ""} name="external_url" type="url" /></label>
                  <label><span>Observation note</span><textarea name="note" required /></label>
                  <button disabled={Boolean(busyAction) || !canRecordManual} type="submit">Record manual status check</button>
                </form>
              </section> : null}

              <section className={styles.panel}>
                <header className={styles.panelHeading}><div><span>Resilience and ownership</span><h5>Export or disconnect</h5><p>Stonegate remains the source of truth even if InvestorLift is unavailable or cancelled.</p></div><ShieldCheck size={17} /></header>
                <div className={styles.panelActions}><button className={styles.secondaryButton} disabled={Boolean(busyAction) || !canExport} onClick={() => void download(`/api/v1/dispositions/cases/${caseId}/provider/export?format=json`, "stonegate-investorlift-history.json")} type="button"><Download size={14} />JSON</button><button className={styles.secondaryButton} disabled={Boolean(busyAction) || !canExport} onClick={() => void download(`/api/v1/dispositions/cases/${caseId}/provider/export?format=csv`, "stonegate-investorlift-events.csv")} type="button"><Download size={14} />CSV</button></div>
                {!isDisconnected && data.listing ? <form className={styles.form} onSubmit={(event) => void disconnect(event)}><label><span>Disconnect reason</span><textarea name="reason" required /></label><label className={styles.attestation}><input name="attestation" required type="checkbox" /><span>I understand Stonegate will preserve the full history and future provider activity must be recorded manually if needed.</span></label><button className={styles.dangerButton} disabled={Boolean(busyAction) || !canDisconnect} type="submit"><CircleOff size={14} />Disconnect manual handoff</button></form> : null}
                {isDisconnected ? <p className={styles.permissionNote}>Disconnected {dateTime(data.listing?.disconnected_at ?? null)}. {data.listing?.disconnect_reason}</p> : null}
              </section>

              <section className={styles.panel}>
                <header className={styles.panelHeading}><div><span>Audit trail</span><h5>Recent manual operations</h5><p>Every preparation, approval, publication record, review, and status check remains observable.</p></div><strong>{data.recent_runs.length} shown</strong></header>
                <div className={styles.eventList}>{data.recent_runs.map((run) => <article className={styles.eventCard} key={run.id}><div><small>{labelize(run.operation)} - {dateTime(run.completed_at)}</small><strong>{labelize(run.status)}</strong>{run.error_message ? <p>{run.error_message}</p> : null}<span>Request {run.request_sha256.slice(0, 12)} - Manual mode</span></div><span className={styles.eventStatus} data-status={run.status}>{labelize(run.status)}</span></article>)}{!data.recent_runs.length ? <p className={styles.permissionNote}>No manual provider operations have been recorded yet.</p> : null}</div>
              </section>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
