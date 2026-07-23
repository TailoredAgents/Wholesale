"use client";

import { usePathname } from "next/navigation";
import { useReportWebVitals } from "next/web-vitals";
import { useCallback, useMemo } from "react";

import { recordConversionEvent } from "./lib/conversion-events";

const publicMetricNames = new Set(["LCP", "INP", "CLS"]);

export function WebVitalsReporter() {
  const pathname = usePathname();
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const reportMetric = useCallback(
    (metric: { name: string; value: number; rating?: string; navigationType?: string }) => {
      if (
        pathname.startsWith("/os") ||
        pathname.startsWith("/sign-in") ||
        pathname.startsWith("/sign-up") ||
        !publicMetricNames.has(metric.name)
      ) {
        return;
      }
      void recordConversionEvent(apiBaseUrl, "web_vital", {
        metric: metric.name,
        value: Number(metric.value.toFixed(metric.name === "CLS" ? 4 : 1)),
        rating: metric.rating ?? "unknown",
        navigation_type: metric.navigationType ?? "unknown",
        route: pathname,
      });
    },
    [apiBaseUrl, pathname],
  );

  useReportWebVitals(reportMetric);
  return null;
}
