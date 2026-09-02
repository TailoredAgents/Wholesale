"use client";

import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Clipboard,
  Ban,
  Download,
  FileClock,
  FileText,
  History,
  LoaderCircle,
  LockKeyhole,
  Link2,
  RefreshCw,
  ShieldAlert,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  DispositionPackageEvidence,
  DispositionPackageEvidenceClassification,
  DispositionPackageReadinessCheck,
  DispositionPackageVersion,
  DispositionPackageWorkspace,
  DispositionPackageShareLink,
  DispositionPackageShareLinkIssued,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./disposition-package-readiness.module.css";

type Request = <T>(path: string, options?: RequestInit) => Promise<T>;

const classificationLabels: Record<DispositionPackageEvidenceClassification, string> = {
  verified_fact: "Verified facts",
  seller_statement: "Seller statements",
  provider_signal: "Provider signals",
  stonegate_analysis: "Stonegate analysis",
  unknown: "Unknown or unresolved",
};

const classificationDescriptions: Record<DispositionPackageEvidenceClassification, string> = {
  verified_fact: "Saved evidence that can be stated as a fact.",
  seller_statement: "Information attributed to the seller, not independently verified.",
  provider_signal: "Third-party research retained as a signal, not a guaranteed fact.",
  stonegate_analysis: "Stonegate calculations and conclusions based on saved evidence.",
  unknown: "Missing or conflicting information that must not be presented as fact.",
};

const classifications = Object.keys(classificationLabels) as DispositionPackageEvidenceClassification[];
const acceptableArtifactScanStatuses = new Set(["clean", "not_configured"]);
const maximumExternalPacketBytes = 15 * 1024 * 1024;

function fileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function validateExternalPacket(file: File) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return "Choose a file whose name ends in .pdf.";
  }
  const normalizedType = file.type.split(";", 1)[0].trim().toLowerCase();
  if (normalizedType && normalizedType !== "application/pdf") {
    return "Choose a PDF file. This file is labeled as a different document type.";
  }
  if (file.size === 0) return "The selected PDF is empty.";
  if (file.size > maximumExternalPacketBytes) {
    return `This PDF is ${fileSize(file.size)}. Investor packet PDFs cannot exceed 15 MB.`;
  }
  try {
    const header = new TextDecoder("ascii").decode(await file.slice(0, 5).arrayBuffer());
    if (header !== "%PDF-") return "The selected file does not contain a valid PDF header.";
  } catch {
    return "Stonegate could not read this PDF. Choose the file again or export a fresh copy.";
  }
  return null;
}

function money(cents: number | null | undefined) {
  return cents == null
    ? "Not set"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(cents / 100);
}

function dollars(cents: unknown) {
  return typeof cents === "number" ? String(cents / 100) : "";
}

function optionalCents(value: FormDataEntryValue | null) {
  const normalized = String(value ?? "").replace(/[$,]/g, "").trim();
  if (!normalized) return undefined;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : undefined;
}

function dateTime(value: string | null | undefined) {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "Not recorded"
    : parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function shareLinkIsPreliminary(link: DispositionPackageShareLink) {
  return link.is_preliminary === true || link.is_current_now === false;
}

function displayValue(value: unknown): string {
  if (value == null || value === "") return "Not recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return new Intl.NumberFormat("en-US").format(value);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(displayValue).join(", ");
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const preferred = record.display_value ?? record.label ?? record.value ?? record.name;
    if (preferred != null && preferred !== value) return displayValue(preferred);
    return Object.entries(record)
      .map(([key, item]) => `${labelize(key)}: ${displayValue(item)}`)
      .join(" - ");
  }
  return String(value);
}

function sourceLabel(evidence: DispositionPackageEvidence) {
  for (const key of ["source_label", "source", "provider", "record_type"]) {
    const value = evidence.provenance[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "Saved Stonegate evidence";
}

function versionName(version: DispositionPackageVersion | null) {
  return version ? `v${version.version_number}` : "No version";
}

function externalArtifactScanIssue(version: DispositionPackageVersion | null) {
  if (!version || version.artifact_source !== "external_upload") return null;
  const scanStatus = version.artifact_metadata?.malware_scan_status?.trim().toLowerCase();
  if (scanStatus && acceptableArtifactScanStatuses.has(scanStatus)) return null;
  if (!scanStatus) {
    return "The uploaded investor packet has no recorded PDF scan result. Upload a newly scanned PDF before approval.";
  }
  return `The uploaded investor packet scan is ${labelize(scanStatus)}. Upload a clean replacement PDF before approval.`;
}

function safePublicEntries(preview: Record<string, unknown>) {
  const presentedSeparately = new Set([
    "headline",
    "description",
    "highlights",
    "unknowns",
    "disclaimer",
    "selected_assets",
    "photos",
  ]);
  return Object.entries(preview).filter(
    ([key, value]) => !presentedSeparately.has(key) && value != null && value !== "",
  );
}

function privateEconomicsEntries(economics: Record<string, unknown>) {
  return Object.entries(economics).filter(([, value]) => value != null && value !== "");
}

function privateValue(key: string, value: unknown) {
  return key.endsWith("_cents") && typeof value === "number" ? money(value) : displayValue(value);
}

function fallbackRemediation(
  check: DispositionPackageReadinessCheck,
  dealId: string,
  leadId: string,
) {
  const subject = `${check.key} ${check.label}`.toLowerCase();
  if (subject.includes("valuation") || subject.includes("arv") || subject.includes("comp")) {
    return { label: "Review valuation", href: `/os/leads/${leadId}?tab=valuation` };
  }
  if (subject.includes("photo") || subject.includes("repair") || subject.includes("condition")) {
    return { label: "Review appointment evidence", href: `/os/leads/${leadId}?tab=appointments` };
  }
  if (subject.includes("contract") || subject.includes("agreement") || subject.includes("term")) {
    return { label: "Review contract", href: `/os/deals?deal=${dealId}&tab=contract` };
  }
  if (subject.includes("document") || subject.includes("title") || subject.includes("file")) {
    return { label: "Review documents", href: `/os/deals?deal=${dealId}&tab=documents` };
  }
  if (subject.includes("property") || subject.includes("address") || subject.includes("parcel")) {
    return { label: "Review property", href: `/os/leads/${leadId}?tab=property` };
  }
  return null;
}

function CheckIcon({ status }: { status: DispositionPackageReadinessCheck["status"] }) {
  if (status === "ready") return <CheckCircle2 aria-hidden="true" size={17} />;
  if (status === "warning") return <AlertTriangle aria-hidden="true" size={17} />;
  return <XCircle aria-hidden="true" size={17} />;
}

export function DispositionPackageReadiness({
  assetClass,
  canEditDeals,
  caseId,
  dealId,
  leadId,
  download,
  onCaseChanged,
  onMessage,
  request,
}: {
  assetClass: "house" | "land";
  canEditDeals: boolean;
  caseId: string;
  dealId: string;
  leadId: string;
  download: (path: string, fileName: string) => Promise<void>;
  onCaseChanged: () => Promise<void>;
  onMessage: (message: string | null) => void;
  request: Request;
}) {
  const requestRef = useRef(request);
  const loadSequenceRef = useRef(0);
  const approvalDialogRef = useRef<HTMLDialogElement>(null);
  const approvalReasonRef = useRef<HTMLTextAreaElement>(null);
  const checklistRef = useRef<HTMLElement>(null);
  const statusRef = useRef<HTMLParagraphElement>(null);
  const [data, setData] = useState<DispositionPackageWorkspace | null>(null);
  const [loadedCaseId, setLoadedCaseId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [approvalReason, setApprovalReason] = useState("");
  const [attested, setAttested] = useState(false);
  const [copied, setCopied] = useState<"email" | "sms" | null>(null);
  const [shareLinks, setShareLinks] = useState<DispositionPackageShareLink[]>([]);
  const [issuedLink, setIssuedLink] = useState<DispositionPackageShareLinkIssued | null>(null);
  const [copiedLink, setCopiedLink] = useState<"link" | "sms" | null>(null);
  const [selectedExternalPacket, setSelectedExternalPacket] = useState<{ name: string; size: number } | null>(null);

  useEffect(() => {
    requestRef.current = request;
  }, [request]);

  const load = useCallback(async () => {
    const sequence = ++loadSequenceRef.current;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const [result, links] = await Promise.all([
        requestRef.current<DispositionPackageWorkspace>(
          `/api/v1/dispositions/cases/${caseId}/package`,
          { cache: "no-store" },
        ),
        requestRef.current<DispositionPackageShareLink[]>(
          `/api/v1/dispositions/cases/${caseId}/package/share-links`,
          { cache: "no-store" },
        ),
      ]);
      if (sequence !== loadSequenceRef.current) return;
      setData(result);
      setShareLinks(links);
      setLoadedCaseId(caseId);
    } catch (loadError) {
      if (sequence !== loadSequenceRef.current) return;
      setError(loadError instanceof Error ? loadError.message : "Unable to load package readiness.");
    } finally {
      if (sequence === loadSequenceRef.current) setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    const sequence = ++loadSequenceRef.current;
    void Promise.all([
      requestRef.current<DispositionPackageWorkspace>(
        `/api/v1/dispositions/cases/${caseId}/package`,
        { cache: "no-store" },
      ),
      requestRef.current<DispositionPackageShareLink[]>(
        `/api/v1/dispositions/cases/${caseId}/package/share-links`,
        { cache: "no-store" },
      ),
    ])
      .then(([result, links]) => {
        if (sequence !== loadSequenceRef.current) return;
        setData(result);
        setShareLinks(links);
        setLoadedCaseId(caseId);
      })
      .catch((loadError: unknown) => {
        if (sequence !== loadSequenceRef.current) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load package readiness.");
      })
      .finally(() => {
        if (sequence === loadSequenceRef.current) setLoading(false);
      });
    return () => {
      loadSequenceRef.current += 1;
    };
  }, [caseId]);

  const evidenceGroups = useMemo(() => {
    const groups = new Map<DispositionPackageEvidenceClassification, DispositionPackageEvidence[]>();
    for (const classification of classifications) groups.set(classification, []);
    for (const item of data?.evidence_manifest ?? []) groups.get(item.classification)?.push(item);
    return groups;
  }, [data?.evidence_manifest]);

  const latestVersion = data?.latest_version ?? null;
  const approvedVersion = data?.approved_version ?? null;
  const readiness = data?.current_readiness ?? null;
  const totalChecks = readiness?.checks.length ?? 0;
  const latestArtifactScanIssue = externalArtifactScanIssue(latestVersion);
  const approvedArtifactScanIssue = externalArtifactScanIssue(approvedVersion);
  const currentApprovedVersion = Boolean(
    data?.approved_package_is_current &&
      approvedVersion &&
      approvedVersion.is_current &&
      !approvedArtifactScanIssue,
  );
  const shoppingVersion = currentApprovedVersion ? approvedVersion : latestVersion;
  const shoppingArtifactIssue = externalArtifactScanIssue(shoppingVersion);
  const shoppingArtifactAvailable = Boolean(
    shoppingVersion &&
      !shoppingArtifactIssue &&
      (shoppingVersion.pdf_file_name || shoppingVersion.pdf_sha256),
  );
  const shoppingIsPreliminary = !currentApprovedVersion;

  async function mutate(
    actionKey: string,
    work: () => Promise<unknown>,
    successMessage: string,
    reloadCase = true,
    broadcastError = true,
  ) {
    setBusyAction(actionKey);
    setError(null);
    setSuccess(null);
    onMessage(null);
    try {
      await work();
      await load();
      if (reloadCase) await onCaseChanged();
      setSuccess(successMessage);
      onMessage(successMessage);
      return true;
    } catch (mutationError) {
      const detail = mutationError instanceof Error ? mutationError.message : "Unable to update the package.";
      setError(detail);
      if (broadcastError) onMessage(detail);
      requestAnimationFrame(() => statusRef.current?.focus());
      return false;
    } finally {
      setBusyAction(null);
    }
  }

  async function rebuild(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data || !canEditDeals) return;
    const values = new FormData(event.currentTarget);
    const payload = {
      expected_latest_version: data.latest_version?.version_number ?? 0,
      asking_price_cents: optionalCents(values.get("asking_price")),
      minimum_acceptable_cents: optionalCents(values.get("minimum_acceptable")),
      desired_assignment_fee_cents: optionalCents(values.get("desired_assignment_fee")),
    };
    await mutate(
      "rebuild",
      () =>
        requestRef.current(`/api/v1/dispositions/cases/${caseId}/package/versions`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      `Investor package ${data.latest_version ? "rebuilt" : "created"} from current saved evidence.`,
    );
  }

  async function uploadExternalPackage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data || !canEditDeals) return;
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("external_package_pdf") as HTMLInputElement | null;
    const file = fileInput?.files?.[0];
    if (!file) {
      setError("Choose the completed investor-packet PDF.");
      return;
    }
    const validationError = await validateExternalPacket(file);
    if (validationError) {
      setError(validationError);
      requestAnimationFrame(() => statusRef.current?.focus());
      return;
    }
    const values = new FormData(form);
    const query = new URLSearchParams({
      expected_latest_version: String(data.latest_version?.version_number ?? 0),
      file_name: file.name,
      content_type: "application/pdf",
    });
    const sourceNote = String(values.get("source_note") ?? "").trim();
    if (sourceNote) query.set("source_note", sourceNote);
    const uploaded = await mutate(
      "external-upload",
      () =>
        requestRef.current<DispositionPackageVersion>(
          `/api/v1/dispositions/cases/${caseId}/package/versions/external?${query.toString()}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/pdf" },
            body: file,
          },
        ),
      "External investor packet uploaded as an exact draft. Review or approve it when useful; shopping and outreach may continue with its Preliminary label.",
      true,
      false,
    );
    if (uploaded) {
      form.reset();
      setSelectedExternalPacket(null);
    }
  }

  function openApproval() {
    if (!latestVersion || latestArtifactScanIssue) {
      checklistRef.current?.focus();
      return;
    }
    setApprovalReason("");
    setAttested(false);
    approvalDialogRef.current?.showModal();
    requestAnimationFrame(() => approvalReasonRef.current?.focus());
  }

  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!latestVersion || !attested || approvalReason.trim().length < 3) return;
    const approved = await mutate(
      "approve",
      () =>
        requestRef.current(
          `/api/v1/dispositions/cases/${caseId}/package/versions/${latestVersion.id}/approval`,
          {
            method: "POST",
            body: JSON.stringify({
              expected_version: latestVersion.lock_version,
              attestation: true,
              reason: approvalReason.trim(),
            }),
          },
        ),
      `Investor package v${latestVersion.version_number} approved.`,
    );
    if (approved) approvalDialogRef.current?.close();
  }

  async function copySummary(channel: "email" | "sms", value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(channel);
      window.setTimeout(() => setCopied(null), 1800);
    } catch {
      setError("Unable to copy the summary. Select the text and copy it manually.");
    }
  }

  async function createShareLink() {
    if (!canEditDeals || !shoppingArtifactAvailable) return;
    setBusyAction("share-link");
    setError(null);
    setSuccess(null);
    try {
      const issued = await requestRef.current<DispositionPackageShareLinkIssued>(
        `/api/v1/dispositions/cases/${caseId}/package/share-links`,
        { method: "POST", body: JSON.stringify({ expires_in_hours: 72 }) },
      );
      setIssuedLink(issued);
      setShareLinks((current) => [issued, ...current.filter((item) => item.id !== issued.id)]);
      try {
        await navigator.clipboard.writeText(issued.share_url);
        setCopiedLink("link");
        window.setTimeout(() => setCopiedLink(null), 1800);
      } catch {
        // The visible read-only URL remains available for manual copy.
      }
      const message = `${shareLinkIsPreliminary(issued) ? "Preliminary" : "Approved"} investor package link created and copied. It expires in 72 hours.`;
      setSuccess(message);
      onMessage(message);
    } catch (shareError) {
      const detail = shareError instanceof Error ? shareError.message : "Unable to create a package link.";
      setError(detail);
      onMessage(detail);
    } finally {
      setBusyAction(null);
    }
  }

  async function copyShareLink(channel: "link" | "sms") {
    if (!issuedLink || !data) return;
    const value = channel === "sms"
      ? `${data.sms_summary}\n\n${issuedLink.share_url}`
      : issuedLink.share_url;
    try {
      await navigator.clipboard.writeText(value);
      setCopiedLink(channel);
      window.setTimeout(() => setCopiedLink(null), 1800);
    } catch {
      setError("Unable to copy the secure link. Select the visible URL and copy it manually.");
    }
  }

  async function revokeShareLink(link: DispositionPackageShareLink) {
    if (!canEditDeals || link.status !== "active") return;
    setBusyAction(`revoke-${link.id}`);
    setError(null);
    try {
      const revoked = await requestRef.current<DispositionPackageShareLink>(
        `/api/v1/dispositions/cases/${caseId}/package/share-links/${link.id}/revoke`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_version: link.lock_version,
            reason: "Revoked from the disposition package workspace.",
          }),
        },
      );
      setShareLinks((current) => current.map((item) => item.id === revoked.id ? revoked : item));
      if (issuedLink?.id === revoked.id) setIssuedLink(null);
      const message = "Investor package link revoked.";
      setSuccess(message);
      onMessage(message);
    } catch (revokeError) {
      const detail = revokeError instanceof Error ? revokeError.message : "Unable to revoke the package link.";
      setError(detail);
      onMessage(detail);
    } finally {
      setBusyAction(null);
    }
  }

  if (!data || loadedCaseId !== caseId) {
    if (!loading && error) {
      return (
        <div className={styles.loadError} role="alert">
          <ShieldAlert aria-hidden="true" size={20} />
          <div><strong>Package readiness is unavailable.</strong><p>{error}</p></div>
          <button onClick={() => void load()} type="button">Retry</button>
        </div>
      );
    }
    return (
      <div aria-busy="true" aria-live="polite" className={styles.loading} role="status">
        <LoaderCircle aria-hidden="true" className={styles.spin} size={18} />
        Loading investor package readiness
      </div>
    );
  }

  if (!readiness) {
    return (
      <div className={styles.loadError} role="alert">
        <ShieldAlert aria-hidden="true" size={20} />
        <div><strong>Package readiness is unavailable.</strong><p>{error ?? "The package could not be loaded."}</p></div>
        <button onClick={() => void load()} type="button">Retry</button>
      </div>
    );
  }

  const preview = data.public_preview;
  const previewHeadline = typeof preview.headline === "string"
    ? preview.headline
    : typeof preview.property_address === "string"
      ? preview.property_address
      : "Investor package preview";
  const previewDescription = typeof preview.description === "string" ? preview.description : "";
  const highlights = Array.isArray(preview.highlights) ? preview.highlights.filter((item): item is string => typeof item === "string") : [];
  const previewUnknowns = Array.isArray(preview.unknowns) ? preview.unknowns.filter((item): item is string => typeof item === "string") : [];
  const disclaimer = typeof preview.disclaimer === "string" ? preview.disclaimer : "";
  const publicEntries = safePublicEntries(preview);
  const privateEntries = data.private_economics ? privateEconomicsEntries(data.private_economics) : [];

  return (
    <div className={styles.workspace} id="package-versions" tabIndex={-1}>
      {error ? <p className={styles.error} ref={statusRef} role="alert" tabIndex={-1}>{error}</p> : null}
      {success ? <p aria-live="polite" className={styles.success} role="status">{success}</p> : null}

      <header className={styles.hero}>
        <div>
          <span><FileText aria-hidden="true" size={16} />Deal launch package</span>
          <h4>{previewHeadline}</h4>
          <p>Build and improve the buyer-facing packet while you shop the deal. Readiness stays visible; approval controls package status, not access to safe preparation work.</p>
        </div>
        <div className={styles.heroStatus} data-status={latestArtifactScanIssue ? "blocked" : readiness.status}>
          <strong>{latestArtifactScanIssue ? "Artifact unavailable" : readiness.status === "ready" ? "Ready for review" : "Needs attention"}</strong>
          <span>{readiness.ready_count} of {totalChecks} checks ready</span>
          <small>{versionName(latestVersion)} - {data.approved_package_is_current ? "approved" : "preliminary shopping allowed"}</small>
        </div>
      </header>

      <section aria-labelledby="package-path-heading" className={styles.packagePathChooser}>
        <header>
          <span>Choose your packet path</span>
          <h5 id="package-path-heading">How do you want to create the investor packet?</h5>
          <p>
            {assetClass === "land"
              ? "Upload the completed Land investor packet as a governed draft. Stonegate preserves that exact file while CRM readiness, buyer matching, and private economics remain structured records."
              : "Both paths create a governed draft that must be reviewed and approved. Uploading an existing PDF preserves that exact file; it does not replace Stonegate's CRM readiness, buyer matching, private economics, or outreach-summary controls."}
          </p>
        </header>
        <div>
          {assetClass === "house" ? <a href="#build-with-stonegate">
            <RefreshCw aria-hidden="true" size={18} />
            <span><strong>Build with Stonegate</strong><small>Generate a packet from the current saved evidence and approved economics.</small></span>
          </a> : null}
          <a href="#use-existing-pdf">
            <Upload aria-hidden="true" size={18} />
            <span><strong>Use existing PDF</strong><small>Upload your finished investor packet unchanged as the exact draft artifact.</small></span>
          </a>
        </div>
      </section>

      {!data.approved_package_is_current && approvedVersion ? (
        <div className={styles.staleApproval} role="status">
          <AlertTriangle aria-hidden="true" size={17} />
          <div><strong>Approved v{approvedVersion.version_number} is no longer current.</strong><p>Saved deal evidence changed. Buyer shopping and preparation can continue from the latest available facts, clearly marked Preliminary; rebuild and approve before treating the package as final.</p></div>
        </div>
      ) : null}

      <section aria-labelledby="package-readiness-heading" className={styles.panel} ref={checklistRef} tabIndex={-1}>
        <div className={styles.panelHeading}>
          <div><span>Launch readiness</span><h5 id="package-readiness-heading">Evidence and preparation checks</h5></div>
          <strong>{readiness.blocked_count + (latestArtifactScanIssue ? 1 : 0)} approval issues - {readiness.warning_count} warnings</strong>
        </div>
        <div className={styles.checkList}>
          {readiness.checks.map((check) => {
            const remediation = check.remediation ?? fallbackRemediation(check, dealId, leadId);
            return (
              <article data-status={check.status} id={check.key} key={check.key} tabIndex={-1}>
                <CheckIcon status={check.status} />
                <div>
                  <strong>{check.label}</strong>
                  <p>{check.detail}</p>
                  <small>{check.source_label ?? "Saved Stonegate record"}{check.captured_at ? ` - ${dateTime(check.captured_at)}` : ""}</small>
                </div>
                {remediation ? <Link href={remediation.href}>{remediation.label}</Link> : null}
              </article>
            );
          })}
          {!readiness.checks.length ? <p className={styles.empty}>No readiness checks were returned.</p> : null}
        </div>
        {(latestArtifactScanIssue || readiness.blockers.length || readiness.warnings.length || readiness.unknowns.length) ? (
          <div className={styles.readinessNotes}>
            {latestArtifactScanIssue ? <p data-status="blocked"><ShieldAlert aria-hidden="true" size={14} />{latestArtifactScanIssue}</p> : null}
            {readiness.blockers.map((item) => <p data-status="blocked" key={`blocker-${item}`}><XCircle aria-hidden="true" size={14} />{item}</p>)}
            {readiness.warnings.map((item) => <p data-status="warning" key={`warning-${item}`}><AlertTriangle aria-hidden="true" size={14} />{item}</p>)}
            {readiness.unknowns.map((item) => <p data-status="unknown" key={`unknown-${item}`}><ShieldAlert aria-hidden="true" size={14} />{item}</p>)}
          </div>
        ) : null}
      </section>

      <div className={styles.previewGrid}>
        <section aria-labelledby="investor-preview-heading" className={styles.panel}>
          <div className={styles.panelHeading}>
            <div><span>Recipient-safe</span><h5 id="investor-preview-heading">Investor-visible preview</h5></div>
            <strong>Safe projection</strong>
          </div>
          {previewDescription ? <p className={styles.previewDescription}>{previewDescription}</p> : null}
          <dl className={styles.previewFacts}>
            {publicEntries.map(([key, value]) => <div key={key}><dt>{labelize(key)}</dt><dd>{key.endsWith("_cents") && typeof value === "number" ? money(value) : displayValue(value)}</dd></div>)}
          </dl>
          {highlights.length ? <div className={styles.previewList}><strong>Highlights</strong>{highlights.map((item) => <p key={item}><CheckCircle2 aria-hidden="true" size={14} />{item}</p>)}</div> : null}
          {[...previewUnknowns, ...readiness.unknowns].length ? <div className={styles.previewList} data-tone="unknown"><strong>Unknowns disclosed</strong>{[...new Set([...previewUnknowns, ...readiness.unknowns])].map((item) => <p key={item}><ShieldAlert aria-hidden="true" size={14} />{item}</p>)}</div> : null}
          {disclaimer ? <p className={styles.disclaimer}>{disclaimer}</p> : null}
        </section>

        {data.can_view_internal_economics && data.private_economics ? (
          <section aria-labelledby="internal-economics-heading" className={`${styles.panel} ${styles.privatePanel}`}>
            <div className={styles.panelHeading}>
              <div><span><LockKeyhole aria-hidden="true" size={13} />Internal only</span><h5 id="internal-economics-heading">Economics never shared</h5></div>
              <strong>Private</strong>
            </div>
            <p className={styles.privateWarning}>These values are excluded from every investor preview, PDF, email, and SMS.</p>
            <dl className={styles.previewFacts}>
              {privateEntries.map(([key, value]) => <div key={key}><dt>{labelize(key)}</dt><dd>{privateValue(key, value)}</dd></div>)}
            </dl>
          </section>
        ) : null}
      </div>

      <details className={`${styles.panel} ${styles.foldPanel}`}>
        <summary className={styles.panelHeading}>
          <div><span>Claim controls</span><h5 id="package-evidence-heading">Classified evidence</h5></div>
          <strong>{data.evidence_manifest.length} saved items</strong>
        </summary>
        <div className={styles.evidenceGroups}>
          {classifications.map((classification) => {
            const evidence = evidenceGroups.get(classification) ?? [];
            if (!evidence.length) return null;
            return (
              <section aria-labelledby={`evidence-${classification}`} key={classification}>
                <header><h6 id={`evidence-${classification}`}>{classificationLabels[classification]}</h6><p>{classificationDescriptions[classification]}</p></header>
                {evidence.map((item) => <article key={item.key}><div><strong>{item.label}</strong><span data-freshness={item.freshness}>{labelize(item.freshness)}</span></div><p>{displayValue(item.value)}</p><small>{sourceLabel(item)}{item.captured_at ? ` - Captured ${dateTime(item.captured_at)}` : ""}{item.expires_at ? ` - Expires ${dateTime(item.expires_at)}` : ""}</small></article>)}
              </section>
            );
          })}
        </div>
      </details>

      <details className={`${styles.panel} ${styles.foldPanel}`}>
        <summary className={styles.panelHeading}>
          <div><span>{currentApprovedVersion ? "Current approved facts" : "Preliminary - checklist incomplete"}</span><h5 id="package-summaries-heading">Deterministic buyer summaries</h5></div>
          <strong>{currentApprovedVersion ? "Approved" : "Preliminary"}</strong>
        </summary>
        <div className={styles.summaryGrid}>
          <label><span>Email summary</span><textarea readOnly rows={9} value={data.email_summary} /><button onClick={() => void copySummary("email", data.email_summary)} type="button"><Clipboard aria-hidden="true" size={14} />{copied === "email" ? "Copied" : "Copy email"}</button></label>
          <label><span>SMS summary</span><textarea readOnly rows={9} value={data.sms_summary} /><button onClick={() => void copySummary("sms", data.sms_summary)} type="button"><Clipboard aria-hidden="true" size={14} />{copied === "sms" ? "Copied" : "Copy SMS"}</button></label>
        </div>
        {shoppingIsPreliminary ? <p className={styles.permissionNote}>These summaries are Preliminary. Unknown or changed facts remain visible for review while buyer work continues.</p> : null}
      </details>

      <details className={`${styles.panel} ${styles.foldPanel}`}>
        <summary className={styles.panelHeading}>
          <div><span>Recipient-safe delivery</span><h5 id="package-share-heading">Secure investor packet link</h5></div>
          <strong>Revocable - 72-hour expiry</strong>
        </summary>
        <div className={styles.shareLinkWorkspace}>
          <div className={styles.shareLinkActions}>
            <p>Create a link to the latest available buyer-safe PDF. An incomplete or unapproved version remains visibly Preliminary; seller notes, private economics, and access instructions stay excluded.</p>
            <button disabled={!canEditDeals || !shoppingArtifactAvailable || busyAction !== null} onClick={() => void createShareLink()} type="button">
              <Link2 aria-hidden="true" size={15} />{busyAction === "share-link" ? "Creating link..." : "Create & copy secure link"}
            </button>
          </div>
          {!shoppingArtifactAvailable ? <p className={styles.permissionNote}>{shoppingArtifactIssue ?? "Build or upload a concrete PDF artifact before creating a buyer link."}</p> : shoppingIsPreliminary ? <p className={styles.permissionNote}>This issued link permanently records Preliminary provenance. Create a new link after package approval for Approved provenance.</p> : null}
          {issuedLink ? (
            <div className={styles.issuedLink}>
              <label><span>New secure link</span><input readOnly value={issuedLink.share_url} /></label>
              <div>
                <button onClick={() => void copyShareLink("link")} type="button"><Clipboard aria-hidden="true" size={14} />{copiedLink === "link" ? "Copied" : "Copy link"}</button>
                <button onClick={() => void copyShareLink("sms")} type="button"><Clipboard aria-hidden="true" size={14} />{copiedLink === "sms" ? "Copied" : "Copy SMS + link"}</button>
              </div>
              <small>{shareLinkIsPreliminary(issuedLink) ? "Preliminary package - " : "Approved package - "}This raw link is shown only now. Stonegate stores a one-way token digest, not the reusable link secret.</small>
            </div>
          ) : null}
          <div className={styles.shareLinkHistory}>
            {shareLinks.map((link) => (
              <article key={link.id}>
                <div>
                  <strong>Package v{link.package_version_number} - {shareLinkIsPreliminary(link) ? "Preliminary" : "Approved"} - {labelize(link.status)}</strong>
                  <span>Ends {dateTime(link.expires_at)} - {link.access_count} open{link.access_count === 1 ? "" : "s"} - token ...{link.token_hint}{link.is_current_now === false ? " - package or source facts changed since issue" : ""}</span>
                  {link.last_accessed_at ? <small>Last opened {dateTime(link.last_accessed_at)}</small> : <small>Not opened yet</small>}
                </div>
                {link.status === "active" ? (
                  <button disabled={!canEditDeals || busyAction !== null} onClick={() => void revokeShareLink(link)} type="button"><Ban aria-hidden="true" size={14} />Revoke</button>
                ) : null}
              </article>
            ))}
            {!shareLinks.length ? <p className={styles.empty}>No investor package links have been created.</p> : null}
          </div>
        </div>
      </details>

      <div className={styles.actionGrid}>
        {assetClass === "house" ? <form className={styles.buildPanel} id="build-with-stonegate" onSubmit={rebuild}>
          <div className={styles.panelHeading}>
            <div><span>Stonegate-built draft</span><h5>Build with Stonegate</h5></div>
            <RefreshCw aria-hidden="true" size={18} />
          </div>
          <p className={styles.packagePathNote}>{latestVersion ? "Rebuild a new immutable version from the latest CRM evidence." : "Create the first immutable version from the current CRM evidence."}</p>
          {data.can_view_internal_economics && data.private_economics ? (
            <div className={styles.economicsFields}>
              <label><span>Investor asking price</span><input defaultValue={dollars(data.private_economics.buyer_asking_price_cents)} inputMode="decimal" name="asking_price" /></label>
              <label><span>Internal minimum target</span><input defaultValue={dollars(data.private_economics.minimum_acceptable_cents)} inputMode="decimal" name="minimum_acceptable" /><small>Internal selection guidance; never included in the buyer package.</small></label>
              <label><span>Desired assignment fee</span><input defaultValue={dollars(data.private_economics.desired_assignment_fee_cents)} inputMode="decimal" name="desired_assignment_fee" /></label>
            </div>
          ) : <p className={styles.permissionNote}>You can rebuild the public package, but internal economics are hidden for your role.</p>}
          <button disabled={!canEditDeals || busyAction !== null} type="submit">{busyAction === "rebuild" ? <LoaderCircle aria-hidden="true" className={styles.spin} size={15} /> : <RefreshCw aria-hidden="true" size={15} />}{latestVersion ? "Rebuild draft" : "Build draft"}</button>
        </form> : null}

        <section className={styles.releasePanel}>
          <div className={styles.panelHeading}>
            <div><span>Human approval</span><h5>Approve and prepare</h5></div>
            <Check aria-hidden="true" size={18} />
          </div>
          <button disabled={!canEditDeals || !data.can_approve || !latestVersion || Boolean(latestArtifactScanIssue) || latestVersion.status === "approved" || busyAction !== null} onClick={openApproval} type="button"><Check aria-hidden="true" size={15} />Approve {versionName(latestVersion)}</button>
          <button disabled={!approvedVersion || busyAction !== null} onClick={() => approvedVersion && void download(`/api/v1/dispositions/cases/${caseId}/package/versions/${approvedVersion.id}/package.pdf`, approvedVersion.pdf_file_name ?? `stonegate-investor-package-v${approvedVersion.version_number}.pdf`)} type="button"><Download aria-hidden="true" size={15} />Download approved {versionName(approvedVersion)} PDF</button>
          {assetClass === "house"
            ? <p id="release-version-requirement">Find and rank investors in <strong>Find buyers</strong>. Prepare exact bulk recipients in <strong>Bulk outreach</strong>. Both remain available while checklist work continues, and neither action sends a buyer message by itself.</p>
            : <p>Upload and approve the exact Land packet when useful. Find buyers, the one-to-one dialer, and supervised bulk outreach remain available independently of package approval.</p>}
        </section>
      </div>

      <form className={styles.externalUploadPanel} id="use-existing-pdf" onSubmit={uploadExternalPackage}>
        <div className={styles.panelHeading}>
          <div><span>Externally prepared packet</span><h5>Use existing PDF</h5></div>
          <Upload aria-hidden="true" size={18} />
        </div>
        <p>
          Upload the exact buyer-facing packet you already made. Stonegate preserves that PDF,
          records its fingerprint, and uses it as the official packet only after human approval.
          CRM facts still supply readiness, matching, private economics, and outreach summaries.
        </p>
        <div className={styles.externalUploadFields}>
          <label>
            <span>Investor packet PDF</span>
            <input accept="application/pdf,.pdf" name="external_package_pdf" onChange={(event) => {
              const file = event.target.files?.[0];
              setSelectedExternalPacket(file ? { name: file.name, size: file.size } : null);
              setError(null);
            }} required type="file" />
            {selectedExternalPacket ? <small>{selectedExternalPacket.name} - {fileSize(selectedExternalPacket.size)}</small> : <small>PDF only - maximum 15 MB</small>}
          </label>
          <label>
            <span>Source note</span>
            <input maxLength={500} name="source_note" placeholder="Optional: who prepared it and when" />
          </label>
        </div>
        <button aria-busy={busyAction === "external-upload"} disabled={!canEditDeals || busyAction !== null} type="submit">
          {busyAction === "external-upload" ? <LoaderCircle aria-hidden="true" className={styles.spin} size={15} /> : <Upload aria-hidden="true" size={15} />}
          {busyAction === "external-upload" ? "Uploading exact PDF..." : "Upload external packet draft"}
        </button>
        {busyAction === "external-upload" && selectedExternalPacket ? <div aria-live="polite" className={styles.uploadProgress} role="status"><span /><small>Uploading {selectedExternalPacket.name}. Keep this page open until it finishes.</small></div> : null}
      </form>

      <details className={`${styles.panel} ${styles.foldPanel}`}>
        <summary className={styles.panelHeading}>
          <div><span>Reproducible record</span><h5 id="package-history-heading">Version history</h5></div>
          <History aria-hidden="true" size={18} />
        </summary>
        <div className={styles.versionList}>
          {data.versions.map((version) => {
            const scanIssue = externalArtifactScanIssue(version);
            const scanStatus = version.artifact_metadata?.malware_scan_status ?? "missing";
            const canDownloadVersionPdf =
              version.status === "approved" || canEditDeals || data.can_approve;
            return (
              <article key={version.id}>
                <div className={styles.versionIdentity}>
                  <FileClock aria-hidden="true" size={17} />
                  <span>
                    <strong>Package v{version.version_number}</strong>
                    <small>{version.artifact_source === "external_upload" ? "Uploaded external PDF" : "Stonegate-generated PDF"} - Created {dateTime(version.created_at)}</small>
                    {version.artifact_source === "external_upload" ? <small data-status={scanIssue ? "blocked" : "ready"}>PDF scan: {labelize(scanStatus)}</small> : null}
                    {version.artifact_metadata?.source_note ? <small>{version.artifact_metadata.source_note}</small> : null}
                  </span>
                </div>
                <div className={styles.versionMeta}>
                  <span data-status={version.status}>{labelize(version.status)}</span>
                  {version.is_current ? <b>Current evidence</b> : null}
                  <small>Fingerprint {version.source_fingerprint.slice(0, 12)}</small>
                </div>
                <div className={styles.versionDecision}>
                  {version.approved_at ? (
                    <>
                      <strong>Approved {dateTime(version.approved_at)}</strong>
                      <small>Approver {version.approved_by_user_id?.slice(0, 8)} - {version.approval_reason}</small>
                      {scanIssue ? <small>{scanIssue}</small> : null}
                    </>
                  ) : (
                    <>
                      <strong>Not approved</strong>
                      <small>{scanIssue ?? version.readiness.blockers[0] ?? version.readiness.warnings[0] ?? "Awaiting human review"}</small>
                    </>
                  )}
                </div>
                {(version.pdf_file_name || version.pdf_sha256) && canDownloadVersionPdf ? (
                  <button aria-label={`Download investor package version ${version.version_number}`} disabled={busyAction !== null} onClick={() => void download(`/api/v1/dispositions/cases/${caseId}/package/versions/${version.id}/package.pdf`, version.pdf_file_name ?? `stonegate-investor-package-v${version.version_number}.pdf`)} type="button"><Download aria-hidden="true" size={15} />PDF</button>
                ) : version.pdf_file_name || version.pdf_sha256 ? (
                  <small className={styles.restrictedDraftPdf}>Draft PDF restricted</small>
                ) : null}
              </article>
            );
          })}
          {!data.versions.length ? <p className={styles.empty}>No package versions have been created.</p> : null}
        </div>
      </details>

      <dialog aria-labelledby="approve-package-title" className={styles.approvalDialog} onCancel={() => approvalDialogRef.current?.close()} ref={approvalDialogRef}>
        <form method="dialog"><button aria-label="Cancel package approval" onClick={() => approvalDialogRef.current?.close()} type="button"><X aria-hidden="true" size={18} /></button></form>
        <form onSubmit={approve}>
          <div><span>Exact version approval</span><h4 id="approve-package-title">Approve investor package {versionName(latestVersion)}</h4><p>{latestVersion?.artifact_source === "external_upload" ? "This approves the exact externally prepared PDF that was uploaded; Stonegate will not regenerate or replace its bytes." : "This freezes the public preview, evidence manifest, email/SMS summaries, and generated PDF for this version."}</p></div>
          <label><span>Approval reason</span><textarea aria-describedby="approval-reason-help" minLength={3} onChange={(event) => setApprovalReason(event.target.value)} ref={approvalReasonRef} required rows={4} value={approvalReason} /><small id="approval-reason-help">Record what you reviewed and why this version is ready for investors.</small></label>
          <label className={styles.attestation}><input checked={attested} onChange={(event) => setAttested(event.target.checked)} required type="checkbox" /><span>{latestVersion?.artifact_source === "external_upload" ? `I reviewed the exact uploaded PDF for ${versionName(latestVersion)} as well as the saved evidence. It contains no private floor, seller notes, or unverified claim presented as fact.` : `I reviewed the investor-visible preview and supporting evidence for ${versionName(latestVersion)}. No private floor, seller notes, or unverified claim is being presented as fact.`}</span></label>
          <div className={styles.dialogActions}><button onClick={() => approvalDialogRef.current?.close()} type="button">Cancel</button><button disabled={!attested || approvalReason.trim().length < 3 || busyAction !== null} type="submit">{busyAction === "approve" ? <LoaderCircle aria-hidden="true" className={styles.spin} size={15} /> : <Check aria-hidden="true" size={15} />}Approve exact version</button></div>
        </form>
      </dialog>
    </div>
  );
}
