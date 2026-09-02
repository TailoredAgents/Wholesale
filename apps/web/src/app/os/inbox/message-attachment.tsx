"use client";

import { Download, ImageIcon, LoaderCircle, Paperclip, RefreshCw } from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";

import styles from "./inbox.module.css";

export type MessageAttachmentData = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  content_url: string | null;
  malware_scan_status: string | null;
};

const previewableImageTypes = new Set([
  "image/gif",
  "image/jpeg",
  "image/png",
  "image/webp",
]);

export function MessageAttachment({
  apiBaseUrl,
  attachment,
  formatSize,
  getHeaders,
  senderLabel,
}: {
  apiBaseUrl: string;
  attachment: MessageAttachmentData;
  formatSize: (sizeBytes: number) => string;
  getHeaders: () => Promise<Record<string, string>>;
  senderLabel: string;
}) {
  const previewable = previewableImageTypes.has(attachment.content_type.toLowerCase());
  const scanVerified = attachment.malware_scan_status === "clean";
  const scanLabel = scanVerified
    ? formatSize(attachment.size_bytes)
    : attachment.malware_scan_status === "scan_error"
      ? "Scan unavailable"
      : "Not malware-scanned";
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">(
    previewable ? "loading" : "idle",
  );
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (!previewable || !attachment.content_url) return;
    const controller = new AbortController();
    let active = true;
    let createdUrl: string | null = null;

    async function loadPreview() {
      try {
        const blob = await fetchAttachmentBlob(
          apiBaseUrl,
          attachment.content_url as string,
          getHeaders,
          controller.signal,
        );
        createdUrl = URL.createObjectURL(blob);
        if (!active) {
          URL.revokeObjectURL(createdUrl);
          return;
        }
        setObjectUrl(createdUrl);
        setLoadState("ready");
      } catch (error) {
        if (active && !(error instanceof DOMException && error.name === "AbortError")) {
          setLoadState("error");
        }
      }
    }

    void loadPreview();
    return () => {
      active = false;
      controller.abort();
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [apiBaseUrl, attachment.content_url, getHeaders, previewable, retryKey]);

  async function downloadAttachment() {
    if (
      !scanVerified &&
      !window.confirm(
        "Stonegate has not malware-scanned this attachment. Only open it if you recognize the sender and expected the file.",
      )
    ) {
      return;
    }
    setLoadState((current) => (previewable ? current : "loading"));
    try {
      const downloadUrl = objectUrl ?? (await loadDownloadUrl());
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = attachment.filename;
      anchor.click();
      if (!objectUrl) window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
      if (!previewable) setLoadState("idle");
    } catch {
      setLoadState("error");
    }
  }

  async function loadDownloadUrl() {
    if (!attachment.content_url) throw new Error("Attachment content is unavailable.");
    const blob = await fetchAttachmentBlob(
      apiBaseUrl,
      attachment.content_url,
      getHeaders,
    );
    return URL.createObjectURL(blob);
  }

  if (!previewable) {
    return (
      <button
        className={styles.messageFileAttachment}
        disabled={loadState === "loading"}
        onClick={() => void downloadAttachment()}
        title={`Download ${attachment.filename}`}
        type="button"
      >
        {loadState === "loading" ? (
          <LoaderCircle className={styles.attachmentSpinner} size={13} aria-hidden="true" />
        ) : (
          <Paperclip size={13} aria-hidden="true" />
        )}
        <span>{attachment.filename}</span>
        <small>{loadState === "error" ? "Retry" : scanLabel}</small>
      </button>
    );
  }

  if (!attachment.content_url || loadState === "error") {
    return (
      <button
        className={styles.messageMediaFallback}
        onClick={() => {
          setLoadState("loading");
          setRetryKey((current) => current + 1);
        }}
        type="button"
      >
        <RefreshCw size={18} aria-hidden="true" />
        <span>Image could not load</span>
        <small>Try again</small>
      </button>
    );
  }

  if (!objectUrl || loadState === "loading") {
    return (
      <div className={styles.messageMediaLoading} role="status">
        <LoaderCircle className={styles.attachmentSpinner} size={20} aria-hidden="true" />
        <span>Loading image</span>
      </div>
    );
  }

  return (
    <figure className={styles.messageMediaAttachment}>
      <a
        className={styles.messageMediaPreview}
        href={objectUrl}
        onClick={(event) => {
          if (
            !scanVerified &&
            !window.confirm(
              "Stonegate has not malware-scanned this attachment. Only open it if you recognize the sender and expected the file.",
            )
          ) {
            event.preventDefault();
          }
        }}
        rel="noreferrer"
        target="_blank"
        title={`Open ${attachment.filename} full size`}
      >
        <Image
          alt={`Image attachment sent by ${senderLabel}`}
          fill
          sizes="(max-width: 720px) 75vw, 320px"
          src={objectUrl}
          unoptimized
        />
        <span className={styles.visuallyHidden}>Open image full size</span>
      </a>
      <figcaption>
        <span>
          <ImageIcon size={13} aria-hidden="true" />
          {attachment.filename}
          {!scanVerified ? <small>Not scanned</small> : null}
        </span>
        <button
          onClick={() => void downloadAttachment()}
          title={`Download ${attachment.filename}`}
          type="button"
        >
          <Download size={13} aria-hidden="true" />
          <span className={styles.visuallyHidden}>Download image</span>
        </button>
      </figcaption>
    </figure>
  );
}

async function fetchAttachmentBlob(
  apiBaseUrl: string,
  contentUrl: string,
  getHeaders: () => Promise<Record<string, string>>,
  signal?: AbortSignal,
) {
  const response = await fetch(`${apiBaseUrl}${contentUrl}`, {
    headers: await getHeaders(),
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(`Attachment request failed with status ${response.status}.`);
  }
  return response.blob();
}
