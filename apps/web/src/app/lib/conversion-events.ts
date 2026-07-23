"use client";

export type ConversionAttribution = {
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

const conversionSessionKey = "stonegate_conversion_session_id_v2";
const attributionStorageKey = "stonegate_conversion_attribution_v1";
let fallbackSessionId: string | null = null;

function sanitizeReferrer(value: string) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return `${url.origin}${url.pathname}`.slice(0, 500);
  } catch {
    return null;
  }
}

function captureCurrentAttribution(): ConversionAttribution {
  const params = new URLSearchParams(window.location.search);
  return {
    landing_page: window.location.pathname.slice(0, 255),
    referrer: sanitizeReferrer(document.referrer),
    utm_source: params.get("utm_source"),
    utm_medium: params.get("utm_medium"),
    utm_campaign: params.get("utm_campaign"),
    utm_term: params.get("utm_term"),
    utm_content: params.get("utm_content"),
    gclid: params.get("gclid"),
    fbclid: params.get("fbclid"),
  };
}

export function getConversionAttribution(): ConversionAttribution {
  try {
    const stored = window.sessionStorage.getItem(attributionStorageKey);
    if (stored) return JSON.parse(stored) as ConversionAttribution;
    const attribution = captureCurrentAttribution();
    window.sessionStorage.setItem(attributionStorageKey, JSON.stringify(attribution));
    return attribution;
  } catch {
    return captureCurrentAttribution();
  }
}

export function getConversionSessionId(): string {
  if (fallbackSessionId) return fallbackSessionId;
  try {
    const existing = window.sessionStorage.getItem(conversionSessionKey);
    if (existing) return existing;
  } catch {
    // Storage can be unavailable in privacy-restricted browsing contexts.
  }

  const id =
    typeof window.crypto.randomUUID === "function"
      ? window.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  fallbackSessionId = id;
  try {
    window.sessionStorage.setItem(conversionSessionKey, id);
  } catch {
    // The in-memory identifier still links events emitted during this page lifecycle.
  }
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
