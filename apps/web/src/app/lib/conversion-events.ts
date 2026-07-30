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
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/public/experiments`, {
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Experiment endpoint unavailable.");
    const payload = (await response.json()) as { experiments?: PublicExperiment[] };
    const experiment = payload.experiments?.[0];
    if (!experiment) return null;
    return assignExperiment(experiment);
  } catch {
    return latestStoredExperiment();
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

function latestStoredExperiment(): ConversionExperimentContext | null {
  const assignments = Object.values(readStoredAssignments()).sort(
    (left, right) => Date.parse(right.assigned_at) - Date.parse(left.assigned_at),
  );
  return assignments[0] ?? null;
}

export async function recordConversionEvent(
  apiBaseUrl: string,
  eventType: string,
  metadata?: Record<string, unknown>,
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
      }),
      keepalive: true,
    });
  } catch {
    // Conversion tracking must never block seller intake.
  }
}
