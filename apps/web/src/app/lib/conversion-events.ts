"use client";

import { isPublicTrackingPath } from "./public-tracking-policy";

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
  fbclid_captured_at: string | null;
};

export type MetaBrowserEvent = {
  event_id: string;
  event_source_url: string;
  fbc: string | null;
  fbp: string | null;
};

type MetaParameterBuilder = {
  processAndCollectAllParams: (
    url?: string | null,
    getIpFn?: (() => string | Promise<string>) | null,
  ) => Promise<Record<string, string>>;
};

type MetaParameterBuilderModule = Partial<MetaParameterBuilder> & {
  default?: Partial<MetaParameterBuilder>;
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
    __stonegateMetaPixelIds?: string[];
    __stonegateMetaLastPageViewPath?: string;
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
const experimentExposureKey = "stonegate_experiment_exposures_v1";
const experimentRequestTimeoutMs = 2_500;
const metaBrowserCookieWaitMs = 750;
const metaBrowserCookiePollMs = 25;
const metaPixelReadyTimeoutMs = 5_000;
const metaPixelScriptId = "stonegate-meta-pixel-script";
let fallbackSessionId: string | null = null;
let fallbackAttribution: ConversionAttribution | null = null;
let experimentRequest: Promise<ConversionExperimentContext | null> | null = null;
let resolvedExperimentContext: ConversionExperimentContext | null = null;
let metaPixelReadyPromise: Promise<boolean> | null = null;
let metaParameterCollectionPromise: Promise<boolean> | null = null;
let metaParameterCollectionUrl: string | null = null;
const fallbackExperimentExposures = new Set<string>();
const inFlightExperimentExposures = new Set<string>();

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
  const fbclid = cleanAttributionValue(params.get("fbclid"), 255);
  return {
    landing_page: window.location.pathname.slice(0, 255),
    referrer: sanitizeReferrer(document.referrer),
    utm_source: cleanAttributionValue(params.get("utm_source"), 120),
    utm_medium: cleanAttributionValue(params.get("utm_medium"), 120),
    utm_campaign: cleanAttributionValue(params.get("utm_campaign"), 255),
    utm_term: cleanAttributionValue(params.get("utm_term"), 255),
    utm_content: cleanAttributionValue(params.get("utm_content"), 255),
    gclid: cleanAttributionValue(params.get("gclid"), 255),
    fbclid,
    fbclid_captured_at: fbclid ? new Date().toISOString() : null,
  };
}

function cleanAttributionValue(value: string | null, maxLength: number) {
  const cleaned = value?.trim();
  return cleaned ? cleaned.slice(0, maxLength) : null;
}

function hasCampaignParameters(attribution: ConversionAttribution) {
  return Boolean(
    attribution.utm_source ||
      attribution.utm_medium ||
      attribution.utm_campaign ||
      attribution.utm_term ||
      attribution.utm_content,
  );
}

function hasExplicitPlatformClick(attribution: ConversionAttribution) {
  return Boolean(attribution.gclid || attribution.fbclid);
}

function recoverMetaClickFromCookie(attribution: ConversionAttribution) {
  if (attribution.fbclid) return attribution;
  const parsedFbc = parseFbc(readCookie("_fbc"));
  if (!parsedFbc) return attribution;
  return {
    ...attribution,
    fbclid: parsedFbc.fbclid,
    fbclid_captured_at: parsedFbc.capturedAt,
  };
}

function parseStoredAttribution(value: string | null): ConversionAttribution | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as Partial<ConversionAttribution>;
    if (typeof parsed.landing_page !== "string") return null;
    const fbclid = cleanAttributionValue(parsed.fbclid ?? null, 255);
    const capturedAt = parsed.fbclid_captured_at;
    let validCapturedAt =
      typeof capturedAt === "string" &&
      Number.isFinite(Date.parse(capturedAt)) &&
      Date.parse(capturedAt) <= Date.now() + 5 * 60 * 1000
        ? capturedAt
        : null;
    if (fbclid && !validCapturedAt) {
      const parsedFbc = parseFbc(readCookie("_fbc"));
      if (parsedFbc?.fbclid === fbclid) validCapturedAt = parsedFbc.capturedAt;
    }
    return {
      landing_page: parsed.landing_page.slice(0, 255),
      referrer: typeof parsed.referrer === "string" ? parsed.referrer.slice(0, 500) : null,
      utm_source: cleanAttributionValue(parsed.utm_source ?? null, 120),
      utm_medium: cleanAttributionValue(parsed.utm_medium ?? null, 120),
      utm_campaign: cleanAttributionValue(parsed.utm_campaign ?? null, 255),
      utm_term: cleanAttributionValue(parsed.utm_term ?? null, 255),
      utm_content: cleanAttributionValue(parsed.utm_content ?? null, 255),
      gclid: cleanAttributionValue(parsed.gclid ?? null, 255),
      fbclid,
      fbclid_captured_at: validCapturedAt,
    };
  } catch {
    return null;
  }
}

function storeAttribution(attribution: ConversionAttribution) {
  fallbackAttribution = attribution;
  try {
    window.sessionStorage.setItem(attributionStorageKey, JSON.stringify(attribution));
  } catch {
    // The in-memory attribution remains stable for this page lifecycle.
  }
}

export function getConversionAttribution(): ConversionAttribution {
  const current = captureCurrentAttribution();
  let stored = fallbackAttribution;
  try {
    stored = parseStoredAttribution(window.sessionStorage.getItem(attributionStorageKey)) ?? stored;
  } catch {
    // Privacy-restricted browsers can still use the in-memory attribution.
  }

  if (!isPublicTrackingPath(window.location.pathname)) return stored ?? current;
  if (stored && !hasExplicitPlatformClick(current)) {
    const merged = hasCampaignParameters(current)
      ? {
          ...stored,
          utm_source: current.utm_source,
          utm_medium: current.utm_medium,
          utm_campaign: current.utm_campaign,
          utm_term: current.utm_term,
          utm_content: current.utm_content,
        }
      : stored;
    const recovered = recoverMetaClickFromCookie(merged);
    storeAttribution(recovered);
    return recovered;
  }

  if (stored?.fbclid && stored.fbclid === current.fbclid && !current.gclid) {
    current.fbclid_captured_at = stored.fbclid_captured_at ?? current.fbclid_captured_at;
  }
  const nextAttribution = recoverMetaClickFromCookie(current);
  storeAttribution(nextAttribution);
  return nextAttribution;
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
  try {
    const prefix = `${name}=`;
    const value = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(prefix));
    if (!value) return null;
    return decodeURIComponent(value.slice(prefix.length));
  } catch {
    return null;
  }
}

function resolveMetaParameterBuilder(
  imported: MetaParameterBuilderModule,
): MetaParameterBuilder | null {
  const candidate =
    typeof imported.processAndCollectAllParams === "function"
      ? imported
      : imported.default;
  return typeof candidate?.processAndCollectAllParams === "function"
    ? (candidate as MetaParameterBuilder)
    : null;
}

export function prepareMetaBrowserParameters(): Promise<boolean> {
  const pixelId = process.env.NEXT_PUBLIC_META_PIXEL_ID?.trim();
  if (
    typeof window === "undefined" ||
    !pixelId ||
    !isPublicTrackingPath(window.location.pathname)
  ) {
    return Promise.resolve(false);
  }
  const currentUrl = window.location.href;
  if (
    metaParameterCollectionPromise &&
    metaParameterCollectionUrl === currentUrl
  ) {
    return metaParameterCollectionPromise;
  }
  metaParameterCollectionUrl = currentUrl;
  metaParameterCollectionPromise = import("meta-capi-param-builder-clientjs")
    .then(async (imported) => {
      const builder = resolveMetaParameterBuilder(imported);
      if (!builder) return false;
      // The API already receives the trusted request IP. Omitting getIpFn avoids
      // an extra third-party request while still enabling in-app click-ID recovery.
      await builder.processAndCollectAllParams(currentUrl);
      return true;
    })
    .catch(() => false);
  return metaParameterCollectionPromise;
}

function newEventId() {
  return typeof window.crypto.randomUUID === "function"
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function cookieFbcMatchesAttribution(fbc: string, fbclid: string) {
  return parseFbc(fbc)?.fbclid === fbclid;
}

function parseFbc(fbc: string | null) {
  if (!fbc) return null;
  const parts = fbc.split(".");
  if ((parts.length !== 4 && parts.length !== 5) || parts[0] !== "fb") return null;
  const capturedAtMs = Number(parts[2]);
  // Parameter Builder appends a fifth SDK token. It is not part of fbclid.
  const fbclid = cleanAttributionValue(parts[3], 255);
  if (
    !fbclid ||
    !Number.isSafeInteger(capturedAtMs) ||
    capturedAtMs < 1_000_000_000_000
  ) {
    return null;
  }
  const capturedAt = new Date(capturedAtMs);
  if (
    !Number.isFinite(capturedAt.getTime()) ||
    capturedAt.getTime() > Date.now() + 5 * 60 * 1000
  ) {
    return null;
  }
  return { capturedAt: capturedAt.toISOString(), fbclid };
}

function fallbackFbc(attribution: ConversionAttribution) {
  if (!attribution.fbclid || !attribution.fbclid_captured_at) return null;
  const capturedAtMs = Date.parse(attribution.fbclid_captured_at);
  if (!Number.isFinite(capturedAtMs)) return null;
  return `fb.1.${Math.floor(capturedAtMs)}.${attribution.fbclid}`;
}

function resolveFbc(attribution: ConversionAttribution) {
  const storedFbc = readCookie("_fbc");
  if (
    storedFbc &&
    (!attribution.fbclid || cookieFbcMatchesAttribution(storedFbc, attribution.fbclid))
  ) {
    return storedFbc;
  }
  return fallbackFbc(attribution);
}

export function createMetaBrowserEvent(eventId = newEventId()): MetaBrowserEvent {
  const attribution = getConversionAttribution();
  return {
    event_id: eventId,
    event_source_url: `${window.location.origin}${window.location.pathname}`.slice(0, 500),
    fbc: resolveFbc(attribution),
    fbp: readCookie("_fbp"),
  };
}

function ensureMetaPixelQueue() {
  if (window.fbq) return window.fbq;
  const fbq = function (...args: unknown[]) {
    if (fbq.callMethod) fbq.callMethod(...args);
    else fbq.queue.push(args);
  } as MetaPixelFunction;
  fbq.queue = [];
  fbq.loaded = true;
  fbq.version = "2.0";
  window.fbq = fbq;
  window._fbq = fbq;
  return fbq;
}

function pixelWasInitialized(fbq: MetaPixelFunction, pixelId: string) {
  return (
    window.__stonegateMetaPixelIds?.includes(pixelId) ||
    (Array.isArray(fbq.queue) &&
      fbq.queue.some((args) => args[0] === "init" && args[1] === pixelId))
  );
}

export function initializeMetaPixel(): Promise<boolean> {
  const pixelId = process.env.NEXT_PUBLIC_META_PIXEL_ID?.trim();
  if (!pixelId || !isPublicTrackingPath(window.location.pathname)) {
    return Promise.resolve(false);
  }
  void prepareMetaBrowserParameters();
  if (metaPixelReadyPromise) return metaPixelReadyPromise;

  const fbq = ensureMetaPixelQueue();
  if (!pixelWasInitialized(fbq, pixelId)) {
    fbq("init", pixelId);
    window.__stonegateMetaPixelIds = [...(window.__stonegateMetaPixelIds ?? []), pixelId];
  }

  const existingScript =
    (document.getElementById(metaPixelScriptId) as HTMLScriptElement | null) ??
    document.querySelector<HTMLScriptElement>(
      'script[src="https://connect.facebook.net/en_US/fbevents.js"]',
    );
  const script = existingScript ?? document.createElement("script");
  if (!existingScript) {
    script.id = metaPixelScriptId;
    script.async = true;
    script.src = "https://connect.facebook.net/en_US/fbevents.js";
  }

  metaPixelReadyPromise = new Promise<boolean>((resolve) => {
    let settled = false;
    let readinessTimeout: number | null = null;
    const settle = (ready: boolean) => {
      if (settled) return;
      settled = true;
      if (readinessTimeout !== null) window.clearTimeout(readinessTimeout);
      resolve(ready);
    };
    if (window.fbq?.callMethod || script.dataset.stonegateLoaded === "true") {
      settle(true);
      return;
    }
    script.addEventListener(
      "load",
      () => {
        script.dataset.stonegateLoaded = "true";
        settle(true);
      },
      { once: true },
    );
    script.addEventListener("error", () => settle(false), { once: true });
    readinessTimeout = window.setTimeout(
      () => settle(Boolean(window.fbq?.callMethod)),
      metaPixelReadyTimeoutMs,
    );
  });

  if (!existingScript) document.head.appendChild(script);
  return metaPixelReadyPromise;
}

export function trackMetaPixelEvent(
  eventName: "PageView" | "ViewContent" | "Lead" | "Contact",
  eventId?: string,
) {
  if (!isPublicTrackingPath(window.location.pathname)) return false;
  void initializeMetaPixel();
  if (!window.fbq) return false;
  if (eventId) window.fbq("track", eventName, {}, { eventID: eventId });
  else window.fbq("track", eventName);
  return true;
}

export function trackMetaPageNavigation(pathname: string) {
  if (!isPublicTrackingPath(pathname)) {
    window.__stonegateMetaLastPageViewPath = undefined;
    return false;
  }
  if (window.__stonegateMetaLastPageViewPath === pathname) return false;
  window.__stonegateMetaLastPageViewPath = pathname;
  return trackMetaPixelEvent("PageView");
}

function refreshMetaBrowserEventCookies(event: MetaBrowserEvent): MetaBrowserEvent {
  const attribution = getConversionAttribution();
  return {
    ...event,
    fbc: resolveFbc(attribution),
    fbp: readCookie("_fbp"),
  };
}

function wait(delayMs: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, delayMs));
}

export async function waitForMetaBrowserCookies(
  event: MetaBrowserEvent,
  waitMs = metaBrowserCookieWaitMs,
) {
  if (!process.env.NEXT_PUBLIC_META_PIXEL_ID?.trim()) return refreshMetaBrowserEventCookies(event);
  const deadline = Date.now() + Math.max(0, waitMs);
  const parameterCollection = prepareMetaBrowserParameters();
  void initializeMetaPixel();
  if (waitMs > 0) {
    await Promise.race([parameterCollection, wait(Math.max(1, waitMs))]);
  } else {
    void parameterCollection;
  }
  let refreshed = refreshMetaBrowserEventCookies(event);
  while (!refreshed.fbp && Date.now() < deadline) {
    await wait(Math.min(metaBrowserCookiePollMs, Math.max(1, deadline - Date.now())));
    refreshed = refreshMetaBrowserEventCookies(event);
  }
  return refreshed;
}

export async function getConversionExperimentContext(
  apiBaseUrl: string,
): Promise<ConversionExperimentContext | null> {
  if (!experimentRequest) {
    experimentRequest = loadExperimentContext(apiBaseUrl).then((context) => {
      resolvedExperimentContext = context;
      return context;
    });
  }
  const context = await experimentRequest;
  if (context) queueExperimentExposure(apiBaseUrl, context);
  return context;
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

function experimentExposureIdentity(context: ConversionExperimentContext) {
  return `${getConversionSessionId()}:${context.experiment_key}`;
}

function wasExperimentExposureSent(exposureIdentity: string) {
  if (fallbackExperimentExposures.has(exposureIdentity)) return true;
  try {
    const raw = window.sessionStorage.getItem(experimentExposureKey);
    const stored = raw ? (JSON.parse(raw) as unknown) : [];
    const identities = Array.isArray(stored)
      ? stored.filter((value): value is string => typeof value === "string")
      : [];
    if (identities.includes(exposureIdentity)) {
      fallbackExperimentExposures.add(exposureIdentity);
      return true;
    }
  } catch {
    // The in-memory marker still protects this page lifecycle.
  }
  return false;
}

function markExperimentExposureSent(exposureIdentity: string) {
  fallbackExperimentExposures.add(exposureIdentity);
  try {
    const raw = window.sessionStorage.getItem(experimentExposureKey);
    const stored = raw ? (JSON.parse(raw) as unknown) : [];
    const identities = Array.isArray(stored)
      ? stored.filter((value): value is string => typeof value === "string")
      : [];
    if (!identities.includes(exposureIdentity)) identities.push(exposureIdentity);
    window.sessionStorage.setItem(experimentExposureKey, JSON.stringify(identities));
  } catch {
    // The successful in-memory marker still prevents another send this lifecycle.
  }
}

function queueExperimentExposure(
  apiBaseUrl: string,
  context: ConversionExperimentContext,
) {
  const exposureIdentity = experimentExposureIdentity(context);
  if (
    wasExperimentExposureSent(exposureIdentity) ||
    inFlightExperimentExposures.has(exposureIdentity)
  ) {
    return;
  }
  inFlightExperimentExposures.add(exposureIdentity);
  void postConversionEvent(
    apiBaseUrl,
    "experiment_exposure",
    {
      surface_key: context.surface_key,
      cta_label: context.cta_label,
    },
    undefined,
    context,
  ).then((sent) => {
    inFlightExperimentExposures.delete(exposureIdentity);
    if (sent) markExperimentExposureSent(exposureIdentity);
  });
}

async function postConversionEvent(
  apiBaseUrl: string,
  eventType: string,
  metadata: Record<string, unknown> | undefined,
  metaBrowserEvent: MetaBrowserEvent | undefined,
  experiment: ConversionExperimentContext | null,
) {
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/public/conversion-events`, {
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
    return response.ok;
  } catch {
    // Conversion measurement must never block seller intake or navigation.
    return false;
  }
}

export async function recordConversionEvent(
  apiBaseUrl: string,
  eventType: string,
  metadata?: Record<string, unknown>,
  metaBrowserEvent?: MetaBrowserEvent,
) {
  void getConversionExperimentContext(apiBaseUrl);
  if (resolvedExperimentContext) {
    queueExperimentExposure(apiBaseUrl, resolvedExperimentContext);
  }
  return postConversionEvent(
    apiBaseUrl,
    eventType,
    metadata,
    metaBrowserEvent,
    resolvedExperimentContext,
  );
}


export async function recordMetaViewContent(
  apiBaseUrl: string,
  metadata?: Record<string, unknown>,
) {
  if (!isPublicTrackingPath(window.location.pathname)) return false;
  const metaBrowserEvent = createMetaBrowserEvent();
  trackMetaPixelEvent("ViewContent", metaBrowserEvent.event_id);
  const serverMetaBrowserEvent = await waitForMetaBrowserCookies(metaBrowserEvent);
  return recordConversionEvent(apiBaseUrl, "page_view", metadata, serverMetaBrowserEvent);
}
