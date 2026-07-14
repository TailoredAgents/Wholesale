"use client";

import { useEffect, useMemo } from "react";

import { recordConversionEvent } from "./lib/conversion-events";

type PublicConversionTrackerProps = {
  eventType?: string;
  metadata?: Record<string, unknown>;
};

export function PublicConversionTracker({
  eventType = "page_view",
  metadata,
}: PublicConversionTrackerProps) {
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );

  useEffect(() => {
    void recordConversionEvent(apiBaseUrl, eventType, metadata);
  }, [apiBaseUrl, eventType, metadata]);

  return null;
}
