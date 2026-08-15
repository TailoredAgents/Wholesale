"use client";

import { Download, LoaderCircle, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import styles from "./inbox.module.css";

export function CallRecordingPlayer({
  apiBaseUrl,
  getHeaders,
  onError,
  recordingId,
}: {
  apiBaseUrl: string;
  getHeaders: () => Promise<Record<string, string>>;
  onError: (message: string) => void;
  recordingId: string;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const objectUrlRef = useRef<string | null>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready">("idle");
  const [autoPlayRequested, setAutoPlayRequested] = useState(false);
  const [manualPlayRequired, setManualPlayRequired] = useState(false);

  useEffect(
    () => () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    },
    [],
  );

  useEffect(() => {
    if (!objectUrl || !autoPlayRequested || !audioRef.current) return;
    let active = true;
    void audioRef.current
      .play()
      .then(() => {
        if (active) setManualPlayRequired(false);
      })
      .catch(() => {
        if (active) setManualPlayRequired(true);
      })
      .finally(() => {
        if (active) setAutoPlayRequested(false);
      });
    return () => {
      active = false;
    };
  }, [autoPlayRequested, objectUrl]);

  async function loadAndPlay() {
    if (objectUrl) {
      setAutoPlayRequested(true);
      return;
    }
    setLoadState("loading");
    setManualPlayRequired(false);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/voice/recordings/${recordingId}/media`,
        {
          headers: await getHeaders(),
          cache: "no-store",
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(recordingErrorMessage(payload));
      }
      const blob = await response.blob();
      if (blob.size === 0) throw new Error("The recording file is empty.");
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      setObjectUrl(url);
      setAutoPlayRequested(true);
      setLoadState("ready");
    } catch (error) {
      setLoadState("idle");
      onError(error instanceof Error ? error.message : "Recording could not be loaded.");
    }
  }

  function downloadRecording() {
    if (!objectUrl) return;
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `stonegate-call-${recordingId}.mp3`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  if (!objectUrl) {
    return (
      <button disabled={loadState === "loading"} onClick={() => void loadAndPlay()} type="button">
        {loadState === "loading" ? (
          <LoaderCircle className={styles.attachmentSpinner} size={13} aria-hidden="true" />
        ) : (
          <Play size={13} aria-hidden="true" />
        )}
        {loadState === "loading" ? "Loading audio" : "Play recording"}
      </button>
    );
  }

  return (
    <div className={styles.recordingPlayer}>
      <audio
        aria-label="Call recording"
        autoPlay
        controls
        onError={() => onError("The recording loaded, but this browser could not play it.")}
        preload="auto"
        ref={audioRef}
        src={objectUrl}
      >
        Call recording
      </audio>
      <button onClick={downloadRecording} title="Download call audio" type="button">
        <Download size={13} aria-hidden="true" />
        <span className={styles.visuallyHidden}>Download call audio</span>
      </button>
      {manualPlayRequired ? <small>Recording loaded. Press play above.</small> : null}
    </div>
  );
}

function recordingErrorMessage(payload: unknown) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return "Recording could not be loaded.";
}
