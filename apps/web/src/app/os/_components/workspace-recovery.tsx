"use client";

import { RefreshCw, WifiOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import styles from "./workspace-recovery.module.css";

const retryDelays = [1_500, 3_000, 5_000, 8_000, 13_000, 15_000];

export function WorkspaceRecovery({
  autoRetry = true,
  detail,
  title = "Stonegate is reconnecting",
}: {
  autoRetry?: boolean;
  detail?: string | null;
  title?: string;
}) {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const attemptRef = useRef(0);

  useEffect(() => {
    if (!autoRetry) return;
    let cancelled = false;
    let timer: number | undefined;

    function scheduleRetry() {
      const delay = retryDelays[Math.min(attemptRef.current, retryDelays.length - 1)];
      timer = window.setTimeout(() => {
        if (cancelled) return;
        if (document.visibilityState === "visible") {
          attemptRef.current += 1;
          setAttempt(attemptRef.current);
          router.refresh();
        }
        scheduleRetry();
      }, delay);
    }

    scheduleRetry();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [autoRetry, router]);

  return (
    <section aria-live="polite" className={styles.recovery} role="status">
      <WifiOff aria-hidden="true" size={24} />
      <div>
        <h2>{title}</h2>
        <p>
          {autoRetry
            ? "Your account and this page are still intact. Stonegate will restore this exact screen as soon as the API responds."
            : "Stonegate reached the API, but the current session was not authorized to load this workspace."}
        </p>
        {detail ? <small>{detail}</small> : null}
        {autoRetry && attempt ? <small>Automatic recovery attempt {attempt} completed.</small> : null}
      </div>
      <button onClick={() => router.refresh()} type="button">
        <RefreshCw aria-hidden="true" size={14} />
        Retry now
      </button>
    </section>
  );
}
