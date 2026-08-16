"use client";

import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef } from "react";

import { recordConversionEvent, recordMetaViewContent } from "./lib/conversion-events";

type PublicConversionTrackerProps = {
  eventType?: string;
  metadata?: Record<string, unknown>;
};

export function PublicConversionTracker({
  eventType = "page_view",
  metadata,
}: PublicConversionTrackerProps) {
  const pathname = usePathname();
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const metadataIdentity = useMemo(() => {
    try {
      return JSON.stringify(metadata ?? null);
    } catch {
      return "[unserializable-metadata]";
    }
  }, [metadata]);
  const lastRecordedIdentity = useRef<string | null>(null);

  useEffect(() => {
    const identity = `${pathname}\n${eventType}\n${metadataIdentity}`;
    if (lastRecordedIdentity.current === identity) return;
    lastRecordedIdentity.current = identity;
    if (eventType === "page_view") {
      void recordMetaViewContent(apiBaseUrl, metadata);
    } else {
      void recordConversionEvent(apiBaseUrl, eventType, metadata);
    }
  }, [apiBaseUrl, eventType, metadata, metadataIdentity, pathname]);

  return null;
}
