type SentryClient = typeof import("@sentry/nextjs");

const sentryDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
const offerLandingPath = "/get-a-cash-offer";

let sentryClientPromise: Promise<SentryClient | null> | null = null;
let deferredListenersAttached = false;

function isOfferLandingPage() {
  return (
    window.location.pathname === offerLandingPath ||
    window.location.pathname.startsWith(`${offerLandingPath}/`)
  );
}

function initializeSentry(Sentry: SentryClient) {
  const isDeferredOfferSession = isOfferLandingPage();

  Sentry.init({
    dsn: sentryDsn,
    enabled: Boolean(sentryDsn),
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? process.env.NODE_ENV,
    // WebVitalsReporter owns performance telemetry for the conversion page. Starting
    // a pageload trace after the visitor interacts would create misleading timings.
    tracesSampleRate: isDeferredOfferSession
      ? 0
      : Number(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.05"),
    sendDefaultPii: false,
  });

  removeDeferredListeners();
  return Sentry;
}

export function loadSentryClient(): Promise<SentryClient | null> {
  if (!sentryDsn) return Promise.resolve(null);

  if (!sentryClientPromise) {
    sentryClientPromise = import("@sentry/nextjs")
      .then(initializeSentry)
      .catch(() => {
        sentryClientPromise = null;
        return null;
      });
  }

  return sentryClientPromise;
}

function loadAfterInteraction() {
  void loadSentryClient();
}

function captureEarlyError(event: ErrorEvent) {
  const error = event.error ?? (event.message ? new Error(event.message) : null);
  if (!error) return;

  void loadSentryClient().then((Sentry) => {
    Sentry?.captureException(error);
  });
}

function captureEarlyRejection(event: PromiseRejectionEvent) {
  void loadSentryClient().then((Sentry) => {
    Sentry?.captureException(event.reason);
  });
}

function removeDeferredListeners() {
  if (!deferredListenersAttached) return;

  for (const eventName of ["pointerdown", "keydown", "input"] as const) {
    window.removeEventListener(eventName, loadAfterInteraction, true);
  }
  window.removeEventListener("error", captureEarlyError, true);
  window.removeEventListener("unhandledrejection", captureEarlyRejection, true);
  deferredListenersAttached = false;
}

function attachDeferredListeners() {
  if (deferredListenersAttached || !sentryDsn) return;

  for (const eventName of ["pointerdown", "keydown", "input"] as const) {
    window.addEventListener(eventName, loadAfterInteraction, {
      capture: true,
      passive: true,
    });
  }
  window.addEventListener("error", captureEarlyError, true);
  window.addEventListener("unhandledrejection", captureEarlyRejection, true);
  deferredListenersAttached = true;
}

export function initializeClientMonitoring() {
  attachDeferredListeners();

  if (isOfferLandingPage()) {
    return;
  }

  void loadSentryClient();
}

export function captureSentryException(error: unknown) {
  return loadSentryClient().then((Sentry) => {
    Sentry?.captureException(error);
  });
}
