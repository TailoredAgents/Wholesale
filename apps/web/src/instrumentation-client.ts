import {
  initializeClientMonitoring,
  loadSentryClient,
} from "./app/lib/sentry-client-loader";

initializeClientMonitoring();

export function onRouterTransitionStart(url: string, navigationType: string) {
  void loadSentryClient().then((Sentry) => {
    Sentry?.captureRouterTransitionStart(url, navigationType);
  });
}

