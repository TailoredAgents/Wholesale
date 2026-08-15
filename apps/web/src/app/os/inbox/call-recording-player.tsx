"use client";

import {
  Download,
  FastForward,
  LoaderCircle,
  Pause,
  Play,
  Rewind,
  Volume2,
  VolumeX,
} from "lucide-react";
import {
  forwardRef,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import {
  CALL_PLAYBACK_RATES,
  clampPlaybackTime,
  formatPlaybackTime,
  parseCallPlaybackSession,
  playbackAriaValue,
  skipPlaybackTime,
} from "./call-playback";
import styles from "./inbox.module.css";

const ACTIVE_CALL_PLAYER_EVENT = "stonegate:active-call-player";
const CALL_PLAYBACK_SESSION_PREFIX = "stonegate:call-playback:";

export type CallRecordingPlayerHandle = {
  seekTo: (seconds: number, options?: { play?: boolean }) => Promise<void>;
};

type CallRecordingPlayerProps = {
  apiBaseUrl: string;
  getHeaders: () => Promise<Record<string, string>>;
  onError: (message: string) => void;
  recordingId: string;
};

export const CallRecordingPlayer = forwardRef<
  CallRecordingPlayerHandle,
  CallRecordingPlayerProps
>(function CallRecordingPlayer({ apiBaseUrl, getHeaders, onError, recordingId }, ref) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const objectUrlRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const metadataAbortControllerRef = useRef<AbortController | null>(null);
  const loadPromiseRef = useRef<Promise<HTMLAudioElement | null> | null>(null);
  const positionRestoredRef = useRef(false);
  const lastPersistedSecondRef = useRef(-1);
  const lastAudibleVolumeRef = useRef(1);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [playerError, setPlayerError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const [manualPlayRequired, setManualPlayRequired] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const sessionKey = `${CALL_PLAYBACK_SESSION_PREFIX}${recordingId}`;

  const persistPlayback = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !Number.isFinite(audio.currentTime)) return;
    try {
      const position = clampPlaybackTime(audio.currentTime, audio.duration);
      if (
        Number.isFinite(audio.duration) &&
        audio.duration > 0 &&
        position >= Math.max(0, audio.duration - 2)
      ) {
        window.sessionStorage.removeItem(sessionKey);
        return;
      }
      window.sessionStorage.setItem(
        sessionKey,
        JSON.stringify({
          position,
          rate: audio.playbackRate,
        }),
      );
    } catch {
      // Playback remains fully functional when browser storage is unavailable.
    }
  }, [sessionKey]);

  const clearMedia = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    metadataAbortControllerRef.current?.abort();
    metadataAbortControllerRef.current = null;
    const objectUrlToRevoke = objectUrlRef.current;
    objectUrlRef.current = null;
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    if (objectUrlToRevoke) URL.revokeObjectURL(objectUrlToRevoke);
    setObjectUrl(null);
    setIsPlaying(false);
    setIsBuffering(false);
    setCurrentTime(0);
    setDuration(0);
  }, []);

  useEffect(
    () => () => {
      persistPlayback();
      abortControllerRef.current?.abort();
      metadataAbortControllerRef.current?.abort();
      const objectUrlToRevoke = objectUrlRef.current;
      objectUrlRef.current = null;
      if (audioRef.current) audioRef.current.pause();
      if (objectUrlToRevoke) URL.revokeObjectURL(objectUrlToRevoke);
    },
    [persistPlayback],
  );

  useEffect(() => {
    const pauseWhenAnotherPlayerStarts = (event: Event) => {
      const activeRecordingId = (event as CustomEvent<{ recordingId?: string }>).detail
        ?.recordingId;
      if (
        activeRecordingId &&
        activeRecordingId !== recordingId &&
        (objectUrlRef.current || abortControllerRef.current || metadataAbortControllerRef.current)
      ) {
        if (objectUrlRef.current) persistPlayback();
        clearMedia();
        positionRestoredRef.current = false;
        setPlayerError(null);
        setManualPlayRequired(false);
        setLoadState("idle");
      }
    };
    window.addEventListener(ACTIVE_CALL_PLAYER_EVENT, pauseWhenAnotherPlayerStarts);
    return () => window.removeEventListener(ACTIVE_CALL_PLAYER_EVENT, pauseWhenAnotherPlayerStarts);
  }, [clearMedia, persistPlayback, recordingId]);

  const showPlayerError = useCallback(
    (message: string) => {
      setPlayerError(message);
      setLoadState("error");
      clearMedia();
      onError(message);
    },
    [clearMedia, onError],
  );

  const loadRecording = useCallback(async () => {
    if (objectUrlRef.current && audioRef.current) return audioRef.current;
    if (loadPromiseRef.current) return loadPromiseRef.current;
    const request = (async () => {
      setLoadState("loading");
      setPlayerError(null);
      setManualPlayRequired(false);
      const controller = new AbortController();
      abortControllerRef.current = controller;
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/voice/recordings/${recordingId}/media`,
          {
            headers: await getHeaders(),
            cache: "no-store",
            signal: controller.signal,
          },
        );
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(recordingErrorMessage(payload));
        }
        const blob = await response.blob();
        if (blob.size === 0) throw new Error("The recording file is empty.");
        if (controller.signal.aborted) return null;
        const audio = audioRef.current;
        if (!audio) return null;
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;
        audio.src = url;
        audio.load();
        setObjectUrl(url);
        setLoadState("ready");
        return audio;
      } catch (error) {
        if (isAbortError(error)) return null;
        showPlayerError(
          error instanceof Error ? error.message : "Recording could not be loaded.",
        );
        return null;
      } finally {
        if (abortControllerRef.current === controller) abortControllerRef.current = null;
      }
    })();
    loadPromiseRef.current = request;
    try {
      return await request;
    } finally {
      if (loadPromiseRef.current === request) loadPromiseRef.current = null;
    }
  }, [apiBaseUrl, getHeaders, recordingId, showPlayerError]);

  const waitForAudioMetadata = useCallback(async (audio: HTMLAudioElement) => {
    metadataAbortControllerRef.current?.abort();
    const controller = new AbortController();
    metadataAbortControllerRef.current = controller;
    try {
      await waitForMetadata(audio, controller.signal);
    } finally {
      if (metadataAbortControllerRef.current === controller) {
        metadataAbortControllerRef.current = null;
      }
    }
  }, []);

  const playFrom = useCallback(
    async (requestedTime?: number) => {
      const audio = await loadRecording();
      if (!audio) return;
      try {
        await waitForAudioMetadata(audio);
      } catch (error) {
        if (isAbortError(error)) return;
        showPlayerError("The recording loaded, but its playback information is unavailable.");
        return;
      }
      const safeDuration = Number.isFinite(audio.duration) ? audio.duration : 0;
      setDuration(safeDuration);
      let rate = playbackRate;
      if (!positionRestoredRef.current) {
        let saved: ReturnType<typeof parseCallPlaybackSession> = null;
        try {
          saved = parseCallPlaybackSession(window.sessionStorage.getItem(sessionKey), safeDuration);
        } catch {
          saved = null;
        }
        if (saved) {
          rate = saved.rate;
          setPlaybackRate(saved.rate);
          if (requestedTime === undefined) audio.currentTime = saved.position;
        }
        positionRestoredRef.current = true;
      }
      audio.playbackRate = rate;
      if (requestedTime !== undefined) {
        audio.currentTime = clampPlaybackTime(requestedTime, safeDuration);
      } else if (audio.ended) {
        audio.currentTime = 0;
      }
      setCurrentTime(audio.currentTime);
      window.dispatchEvent(
        new CustomEvent(ACTIVE_CALL_PLAYER_EVENT, { detail: { recordingId } }),
      );
      setManualPlayRequired(false);
      try {
        await audio.play();
      } catch {
        setManualPlayRequired(true);
      }
    },
    [
      loadRecording,
      playbackRate,
      recordingId,
      sessionKey,
      showPlayerError,
      waitForAudioMetadata,
    ],
  );

  const seekTo = useCallback(
    async (seconds: number, options: { play?: boolean } = { play: true }) => {
      if (options.play === false) {
        const audio = await loadRecording();
        if (!audio) return;
        try {
          await waitForAudioMetadata(audio);
        } catch (error) {
          if (isAbortError(error)) return;
          showPlayerError(
            "The recording loaded, but its playback information is unavailable.",
          );
          return;
        }
        audio.currentTime = clampPlaybackTime(seconds, audio.duration);
        setCurrentTime(audio.currentTime);
        persistPlayback();
        return;
      }
      await playFrom(seconds);
    },
    [loadRecording, persistPlayback, playFrom, showPlayerError, waitForAudioMetadata],
  );

  useImperativeHandle(ref, () => ({ seekTo }), [seekTo]);

  const togglePlayback = async () => {
    const audio = audioRef.current;
    if (!objectUrlRef.current || !audio || audio.paused) {
      await playFrom();
      return;
    }
    audio.pause();
  };

  const skip = (delta: number) => {
    const audio = audioRef.current;
    if (
      !audio ||
      !objectUrlRef.current ||
      !Number.isFinite(audio.duration) ||
      audio.duration <= 0
    ) {
      return;
    }
    audio.currentTime = skipPlaybackTime(audio.currentTime, delta, audio.duration);
    setCurrentTime(audio.currentTime);
    persistPlayback();
  };

  const changePlaybackRate = (rate: number) => {
    setPlaybackRate(rate);
    if (audioRef.current) audioRef.current.playbackRate = rate;
    persistPlayback();
  };

  const changeVolume = (nextVolume: number) => {
    const safeVolume = Math.min(1, Math.max(0, nextVolume));
    if (safeVolume > 0) lastAudibleVolumeRef.current = safeVolume;
    setVolume(safeVolume);
    setMuted(safeVolume === 0);
    if (audioRef.current) {
      audioRef.current.volume = safeVolume;
      audioRef.current.muted = safeVolume === 0;
    }
  };

  const toggleMute = () => {
    const nextMuted = !muted && volume > 0;
    const nextVolume = nextMuted
      ? volume
      : volume > 0
        ? volume
        : lastAudibleVolumeRef.current;
    if (!nextMuted && volume === 0) setVolume(nextVolume);
    setMuted(nextMuted);
    if (audioRef.current) {
      audioRef.current.volume = nextVolume;
      audioRef.current.muted = nextMuted;
    }
  };

  const downloadRecording = async () => {
    const audio = await loadRecording();
    if (!audio || !objectUrlRef.current) return;
    const anchor = document.createElement("a");
    anchor.href = objectUrlRef.current;
    anchor.download = `stonegate-call-${recordingId}.mp3`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  };

  const retryRecording = () => {
    abortControllerRef.current?.abort();
    clearMedia();
    positionRestoredRef.current = false;
    setPlayerError(null);
    setLoadState("idle");
    void playFrom();
  };

  const handlePlayerKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    const key = event.key.toLowerCase();
    if ([" ", "k"].includes(key)) {
      event.preventDefault();
      void togglePlayback();
    } else if (key === "j") {
      event.preventDefault();
      skip(-10);
    } else if (key === "l") {
      event.preventDefault();
      skip(10);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      skip(-5);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      skip(5);
    } else if (event.key === "Home") {
      event.preventDefault();
      void seekTo(0, { play: false });
    } else if (event.key === "End") {
      event.preventDefault();
      void seekTo(duration, { play: false });
    }
  };

  const mediaReady = duration > 0;
  let inlineStatus = playerError;
  if (!inlineStatus && loadState === "loading") inlineStatus = "Loading recording…";
  if (!inlineStatus && objectUrl && !mediaReady) inlineStatus = "Preparing playback…";
  if (!inlineStatus && isBuffering) inlineStatus = "Buffering…";
  if (!inlineStatus && manualPlayRequired) {
    inlineStatus = "Recording ready. Press play to continue.";
  }

  return (
    <div
      aria-busy={loadState === "loading" || isBuffering}
      aria-label="Call recording player"
      className={styles.recordingPlayer}
      data-state={loadState}
      onKeyDown={handlePlayerKeyboard}
      role="group"
      tabIndex={0}
    >
      <audio
        aria-hidden="true"
        className={styles.recordingAudioEngine}
        onCanPlay={() => setIsBuffering(false)}
        onDurationChange={(event) => {
          const nextDuration = Number.isFinite(event.currentTarget.duration)
            ? event.currentTarget.duration
            : 0;
          setDuration(nextDuration);
        }}
        onEnded={() => {
          setIsPlaying(false);
          setCurrentTime(duration);
          try {
            window.sessionStorage.removeItem(sessionKey);
          } catch {
            // Ending playback does not depend on browser storage.
          }
        }}
        onError={() => {
          if (objectUrlRef.current) {
            showPlayerError("The recording loaded, but this browser could not play it.");
          }
        }}
        onPause={() => {
          setIsPlaying(false);
          if (objectUrlRef.current) persistPlayback();
        }}
        onPlay={() => {
          setIsPlaying(true);
          setManualPlayRequired(false);
        }}
        onPlaying={() => setIsBuffering(false)}
        onTimeUpdate={(event) => {
          const nextTime = event.currentTarget.currentTime;
          setCurrentTime(nextTime);
          const wholeSecond = Math.floor(nextTime);
          if (wholeSecond - lastPersistedSecondRef.current >= 5) {
            lastPersistedSecondRef.current = wholeSecond;
            persistPlayback();
          }
        }}
        onWaiting={() => setIsBuffering(true)}
        preload="metadata"
        ref={audioRef}
      />

      {!objectUrl ? (
        <div className={styles.recordingLoadActions}>
          <button
            className={styles.recordingPrimaryButton}
            disabled={loadState === "loading"}
            onClick={() => void playFrom()}
            type="button"
          >
            {loadState === "loading" ? (
              <LoaderCircle className={styles.attachmentSpinner} size={14} aria-hidden="true" />
            ) : (
              <Play size={14} aria-hidden="true" />
            )}
            {loadState === "loading" ? "Loading audio" : "Play recording"}
          </button>
          <button
            disabled={loadState === "loading"}
            onClick={() => void downloadRecording()}
            type="button"
          >
            <Download size={13} aria-hidden="true" />
            Download
          </button>
          {loadState === "error" ? (
            <button onClick={retryRecording} type="button">
              Retry
            </button>
          ) : null}
        </div>
      ) : (
        <div className={styles.recordingControlsGrid}>
          <div className={styles.recordingTransportControls}>
            <button
              aria-label={isPlaying ? "Pause call recording" : "Play call recording"}
              className={styles.recordingPrimaryButton}
              onClick={() => void togglePlayback()}
              title={isPlaying ? "Pause" : "Play"}
              type="button"
            >
              {isPlaying ? (
                <Pause size={15} aria-hidden="true" />
              ) : (
                <Play size={15} aria-hidden="true" />
              )}
            </button>
            <button
              aria-label="Go back 10 seconds"
              disabled={!mediaReady}
              onClick={() => skip(-10)}
              type="button"
            >
              <Rewind size={14} aria-hidden="true" />
              <span>10</span>
            </button>
            <button
              aria-label="Go forward 10 seconds"
              disabled={!mediaReady}
              onClick={() => skip(10)}
              type="button"
            >
              <FastForward size={14} aria-hidden="true" />
              <span>10</span>
            </button>
          </div>

          <div className={styles.recordingTimelineControl}>
            <input
              aria-label="Recording position"
              aria-valuetext={playbackAriaValue(currentTime, duration)}
              disabled={!mediaReady}
              max={Math.max(duration, 0)}
              min="0"
              onBlur={persistPlayback}
              onChange={(event) => {
                const audio = audioRef.current;
                if (!audio) return;
                audio.currentTime = clampPlaybackTime(Number(event.target.value), duration);
                setCurrentTime(audio.currentTime);
              }}
              onKeyUp={persistPlayback}
              onPointerUp={persistPlayback}
              step="0.1"
              type="range"
              value={clampPlaybackTime(currentTime, duration)}
            />
            <span aria-label="Recording time">
              {formatPlaybackTime(currentTime)} / {formatPlaybackTime(duration)}
            </span>
          </div>

          <div className={styles.recordingUtilityControls}>
            <label>
              <span className={styles.visuallyHidden}>Playback speed</span>
              <select
                aria-label="Playback speed"
                onChange={(event) => changePlaybackRate(Number(event.target.value))}
                value={playbackRate}
              >
                {CALL_PLAYBACK_RATES.map((rate) => (
                  <option key={rate} value={rate}>
                    {rate}×
                  </option>
                ))}
              </select>
            </label>
            <button
              aria-label={muted ? "Unmute recording" : "Mute recording"}
              onClick={toggleMute}
              type="button"
            >
              {muted || volume === 0 ? (
                <VolumeX size={14} aria-hidden="true" />
              ) : (
                <Volume2 size={14} aria-hidden="true" />
              )}
            </button>
            <input
              aria-label="Recording volume"
              className={styles.recordingVolumeRange}
              max="1"
              min="0"
              onChange={(event) => changeVolume(Number(event.target.value))}
              step="0.05"
              type="range"
              value={muted ? 0 : volume}
            />
            <button
              onClick={() => void downloadRecording()}
              title="Download call audio"
              type="button"
            >
              <Download size={13} aria-hidden="true" />
              <span className={styles.visuallyHidden}>Download call audio</span>
            </button>
          </div>
        </div>
      )}

      {inlineStatus ? (
        <small
          aria-live="polite"
          className={styles.recordingStatus}
          role={playerError ? "alert" : "status"}
        >
          {inlineStatus}
        </small>
      ) : null}
      <small className={styles.recordingKeyboardHint}>
        Keyboard: Space/K play · J/L ±10s · arrows ±5s
      </small>
    </div>
  );
});

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

function waitForMetadata(audio: HTMLAudioElement, signal?: AbortSignal) {
  if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) return Promise.resolve();
  if (signal?.aborted) {
    return Promise.reject(
      new DOMException("Recording metadata wait was cancelled.", "AbortError"),
    );
  }
  return new Promise<void>((resolve, reject) => {
    const finish = () => {
      window.clearTimeout(timeout);
      audio.removeEventListener("loadedmetadata", handleLoaded);
      audio.removeEventListener("error", handleError);
      signal?.removeEventListener("abort", handleAbort);
    };
    const handleLoaded = () => {
      finish();
      resolve();
    };
    const handleError = () => {
      finish();
      reject(new Error("Recording metadata could not be loaded."));
    };
    const handleAbort = () => {
      finish();
      reject(new DOMException("Recording metadata wait was cancelled.", "AbortError"));
    };
    const timeout = window.setTimeout(() => {
      finish();
      reject(new Error("Recording metadata timed out."));
    }, 10_000);
    audio.addEventListener("loadedmetadata", handleLoaded, { once: true });
    audio.addEventListener("error", handleError, { once: true });
    signal?.addEventListener("abort", handleAbort, { once: true });
    if (signal?.aborted) {
      handleAbort();
      return;
    }
    if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) handleLoaded();
  });
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}
