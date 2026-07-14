"use client";

type ConversionAttribution = {
  landing_page: string;
  referrer: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_term: string | null;
  utm_content: string | null;
  gclid: string | null;
  fbclid: string | null;
};

const sessionStorageKey = "oakwell_conversion_session_id";

export function getConversionAttribution(): ConversionAttribution {
  const params = new URLSearchParams(window.location.search);
  return {
    landing_page: window.location.pathname,
    referrer: document.referrer || null,
    utm_source: params.get("utm_source"),
    utm_medium: params.get("utm_medium"),
    utm_campaign: params.get("utm_campaign"),
    utm_term: params.get("utm_term"),
    utm_content: params.get("utm_content"),
    gclid: params.get("gclid"),
    fbclid: params.get("fbclid"),
  };
}

export function getConversionSessionId(): string {
  const existing = window.localStorage.getItem(sessionStorageKey);
  if (existing) {
    return existing;
  }

  const id =
    typeof window.crypto.randomUUID === "function"
      ? window.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  window.localStorage.setItem(sessionStorageKey, id);
  return id;
}

export async function recordConversionEvent(
  apiBaseUrl: string,
  eventType: string,
  metadata?: Record<string, unknown>,
) {
  try {
    await fetch(`${apiBaseUrl}/api/v1/public/conversion-events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: eventType,
        session_id: getConversionSessionId(),
        metadata: metadata ?? null,
        attribution: getConversionAttribution(),
      }),
      keepalive: true,
    });
  } catch {
    // Conversion tracking must never block seller intake.
  }
}
