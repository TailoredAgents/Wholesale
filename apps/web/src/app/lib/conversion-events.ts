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

export type MetaBrowserEvent = {
  event_id: string;
  event_source_url: string;
  fbc: string | null;
  fbp: string | null;
};

type MetaPixelFunction = ((...args: unknown[]) => void) & {
  callMethod?: (...args: unknown[]) => void;
  queue: unknown[][];
  loaded: boolean;
  version: string;
};

declare global {
  interface Window {
    fbq?: MetaPixelFunction;
    _fbq?: MetaPixelFunction;
  }
}

export type PublicExperimentVariant = {
  key: string;
  label: string;
  weight_basis_points: number;
  cta_label: string;
};

export type PublicExperiment = {
  experiment_key: string;
  surface_key: string;
  variants: PublicExperimentVariant[];
};

export type ConversionExperimentContext = {
  experiment_key: string;
  experiment_variant: string;
  surface_key: string;
  cta_label: string;
};

const conversionSessionKey = "stonegate_conversion_session_id_v2";
const attributionStorageKey = "stonegate_conversion_attribution_v1";
const experimentVisitorKey = "stonegate_experiment_visitor_id_v1";
const experimentAssignmentKey = "stonegate_experiment_assignments_v1";
const experimentRequestTimeoutMs = 2_500;
let fallbackSessionId: string | null = null;
let experimentRequest: Promise<ConversionExperimentContext | null> | null = null;

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

export function getDeviceCategory() {
  if (window.innerWidth <= 720) return "mobile";
  if (window.innerWidth <= 1024) return "tablet";
  return "desktop";
}

function readCookie(name: string) {
  const prefix = `${name}=`;
  const value = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return value ? decodeURIComponent(value.slice(prefix.length)) : null;
}

function newEventId() {
  return typeof window.crypto.randomUUID === "function"
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function createMetaBrowserEvent(): MetaBrowserEvent {
  const attribution = getConversionAttribution();
  const storedFbc = readCookie("_fbc");
  const fbc =
    storedFbc ??
    (attribution.fbclid
      ? `fb.1.${Math.floor(Date.now() / 1000)}.${attribution.fbclid}`
      : null);
  return {
    event_id: newEventId(),
    event_source_url: `${window.location.origin}${window.location.pathname}`.slice(0, 500),
    fbc,
    fbp: readCookie("_fbp"),
  };
}

export function initializeMetaPixel() {
  const pixelId = process.env.NEXT_PUBLIC_META_PIXEL_ID?.trim();
  if (!pixelId || window.fbq) return;
  const fbq = function (...args: unknown[]) {
    if (fbq.callMethod) fbq.callMethod(...args);
    else fbq.queue.push(args);
  } as MetaPixelFunction;
  fbq.queue = [];
  fbq.loaded = true;
  fbq.version = "2.0";
  window.fbq = fbq;
  window._fbq = fbq;
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://connect.facebook.net/en_US/fbevents.js";
  document.head.appendChild(script);
  fbq("init", pixelId);
}

export function trackMetaPixelEvent(
  eventName: "PageView" | "ViewContent" | "Lead",
  eventId?: string,
) {
  initializeMetaPixel();
  if (!window.fbq) return;
  if (eventId) window.fbq("track", eventName, {}, { eventID: eventId });
  else window.fbq("track", eventName);
}

export async function getConversionExperimentContext(
  apiBaseUrl: string,
): Promise<ConversionExperimentContext | null> {
  if (!experimentRequest) {
    experimentRequest = loadExperimentContext(apiBaseUrl);
  }
  return experimentRequest;
}

async function loadExperimentContext(
  apiBaseUrl: string,
): Promise<ConversionExperimentContext | null> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), experimentRequestTimeoutMs);
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/public/experiments`, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error("Experiment endpoint unavailable.");
    const payload = (await response.json()) as { experiments?: PublicExperiment[] };
    const experiment = payload.experiments?.[0];
    if (!experiment) return null;
    return assignExperiment(experiment);
  } catch {
    return null;
  } finally {
    window.clearTimeout(timeout);
  }
}

function assignExperiment(experiment: PublicExperiment): ConversionExperimentContext | null {
  if (!experiment.variants.length) return null;
  const stored = readStoredAssignments();
  const existing = stored[experiment.experiment_key];
  const selected =
    experiment.variants.find((variant) => variant.key === existing?.experiment_variant) ??
    chooseVariant(experiment);
  if (!selected) return null;
  const context = {
    experiment_key: experiment.experiment_key,
    experiment_variant: selected.key,
    surface_key: experiment.surface_key,
    cta_label: selected.cta_label,
  };
  stored[experiment.experiment_key] = {
    ...context,
    assigned_at: new Date().toISOString(),
  };
  try {
    window.localStorage.setItem(experimentAssignmentKey, JSON.stringify(stored));
  } catch {
    // The in-memory context still keeps this page internally consistent.
  }
  return context;
}

function chooseVariant(experiment: PublicExperiment) {
  const bucket = stableHash(
    `${getExperimentVisitorId()}:${experiment.experiment_key}`,
  ) % 10000;
  let boundary = 0;
  for (const variant of experiment.variants) {
    boundary += variant.weight_basis_points;
    if (bucket < boundary) return variant;
  }
  return experiment.variants.at(-1);
}

function getExperimentVisitorId() {
  try {
    const existing = window.localStorage.getItem(experimentVisitorKey);
    if (existing) return existing;
    const created =
      typeof window.crypto.randomUUID === "function"
        ? window.crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(experimentVisitorKey, created);
    return created;
  } catch {
    return getConversionSessionId();
  }
}

function stableHash(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

type StoredAssignment = ConversionExperimentContext & { assigned_at: string };

function readStoredAssignments(): Record<string, StoredAssignment> {
  try {
    const stored = window.localStorage.getItem(experimentAssignmentKey);
    return stored ? (JSON.parse(stored) as Record<string, StoredAssignment>) : {};
  } catch {
    return {};
  }
}

export async function recordConversionEvent(
  apiBaseUrl: string,
  eventType: string,
  metadata?: Record<string, unknown>,
  metaBrowserEvent?: MetaBrowserEvent,
) {
  try {
    const experiment = await getConversionExperimentContext(apiBaseUrl);
    await fetch(`${apiBaseUrl}/api/v1/public/conversion-events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: eventType,
        session_id: getConversionSessionId(),
        experiment_key: experiment?.experiment_key ?? null,
        experiment_variant: experiment?.experiment_variant ?? null,
        device_category: getDeviceCategory(),
        metadata: metadata ?? null,
        attribution: getConversionAttribution(),
        meta_browser_event: metaBrowserEvent ?? null,
      }),
      keepalive: true,
    });
  } catch {
    // Conversion tracking must never block seller intake.
  }
}


export async function recordMetaViewContent(
  apiBaseUrl: string,
  metadata?: Record<string, unknown>,
) {
  const metaBrowserEvent = createMetaBrowserEvent();
  trackMetaPixelEvent("ViewContent", metaBrowserEvent.event_id);
  await recordConversionEvent(apiBaseUrl, "page_view", metadata, metaBrowserEvent);
}
