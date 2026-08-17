import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, extname, resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

import ts from "typescript";

const webRoot = process.cwd();

function createStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    removeItem(key) {
      values.delete(key);
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
  };
}

function createRuntime({
  pathname = "/",
  search = "",
  pixelId = "2118209559079623",
  parameterBuilder,
} = {}) {
  const appendedScripts = [];
  const elementsById = new Map();
  const parameterBuilderCalls = [];
  let cookie = "";
  let randomId = 0;
  const location = {
    origin: "https://www.stonegatehb.com",
    pathname,
    search,
    get href() {
      return `${this.origin}${this.pathname}${this.search}`;
    },
  };
  const document = {
    referrer: "https://www.facebook.com/",
    createElement(tagName) {
      const listeners = new Map();
      return {
        async: false,
        dataset: {},
        id: "",
        src: "",
        tagName,
        addEventListener(name, handler) {
          const handlers = listeners.get(name) ?? [];
          handlers.push(handler);
          listeners.set(name, handlers);
        },
        dispatch(name) {
          for (const handler of listeners.get(name) ?? []) handler();
        },
      };
    },
    getElementById(id) {
      return elementsById.get(id) ?? null;
    },
    querySelector() {
      return null;
    },
    head: {
      appendChild(element) {
        appendedScripts.push(element);
        if (element.id) elementsById.set(element.id, element);
        return element;
      },
    },
  };
  Object.defineProperty(document, "cookie", {
    get() {
      return cookie;
    },
    set(value) {
      cookie = value;
    },
  });

  const window = {
    clearTimeout,
    crypto: {
      randomUUID() {
        randomId += 1;
        return `00000000-0000-4000-8000-${String(randomId).padStart(12, "0")}`;
      },
    },
    innerWidth: 390,
    localStorage: createStorage(),
    location,
    sessionStorage: createStorage(),
    setTimeout,
  };
  const context = vm.createContext({
    AbortController,
    URL,
    URLSearchParams,
    clearTimeout,
    console,
    document,
    fetch: async () => {
      throw new Error("Unexpected fetch.");
    },
    process: { env: { NEXT_PUBLIC_META_PIXEL_ID: pixelId } },
    setTimeout,
    window,
  });
  const runtime = {
    appendedScripts,
    context,
    document,
    location,
    metaParameterBuilder: {
      async processAndCollectAllParams(...args) {
        parameterBuilderCalls.push(args);
        return parameterBuilder?.processAndCollectAllParams
          ? parameterBuilder.processAndCollectAllParams(...args)
          : {};
      },
    },
    parameterBuilderCalls,
    setCookie(value) {
      cookie = value;
    },
    setFetch(fetchImplementation) {
      context.fetch = fetchImplementation;
    },
    window,
  };
  return runtime;
}

function resolveTypeScriptModule(fromPath, specifier) {
  const candidate = resolve(dirname(fromPath), specifier);
  if (extname(candidate)) return candidate;
  return `${candidate}.ts`;
}

function loadTypeScriptModule(relativePath, runtime, cache = new Map()) {
  const absolutePath = resolve(webRoot, relativePath);
  if (cache.has(absolutePath)) return cache.get(absolutePath).exports;

  const loadedModule = { exports: {} };
  cache.set(absolutePath, loadedModule);
  const source = readFileSync(absolutePath, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: absolutePath,
  }).outputText;
  const localRequire = (specifier) => {
    if (specifier === "meta-capi-param-builder-clientjs") {
      return runtime.metaParameterBuilder;
    }
    if (!specifier.startsWith(".")) throw new Error(`Unexpected import: ${specifier}`);
    const importedPath = resolveTypeScriptModule(absolutePath, specifier);
    return loadTypeScriptModule(importedPath, runtime, cache);
  };
  const wrapper = vm.runInContext(
    `(function (exports, require, module, __filename, __dirname) { ${output}\n })`,
    runtime.context,
    { filename: absolutePath },
  );
  wrapper(
    loadedModule.exports,
    localRequire,
    loadedModule,
    absolutePath,
    dirname(absolutePath),
  );
  return loadedModule.exports;
}

function loadTracking(runtime) {
  return loadTypeScriptModule("src/app/lib/conversion-events.ts", runtime);
}

function nextTurn() {
  return new Promise((resolveTurn) => setImmediate(resolveTurn));
}

test("the public tracking policy excludes every internal and authentication route", () => {
  const runtime = createRuntime();
  const policy = loadTypeScriptModule("src/app/lib/public-tracking-policy.ts", runtime);

  for (const pathname of ["/", "/about", "/get-a-cash-offer", "/service-areas/atlanta"]) {
    assert.equal(policy.isPublicTrackingPath(pathname), true, pathname);
  }
  for (const pathname of [
    "/os",
    "/os/inbox",
    "/leads/lead-id",
    "/sign-in",
    "/sign-up/account",
    "/__clerk/callback",
    "/auth/callback",
    "/sso-callback",
  ]) {
    assert.equal(policy.isPublicTrackingPath(pathname), false, pathname);
  }
  assert.equal(policy.isPublicTrackingPath("/oshkosh"), true);
});

test("a direct internal route never initializes or requests the Meta Pixel", async () => {
  for (const pathname of ["/os", "/os/leads", "/leads/lead-id", "/sign-in", "/__clerk/callback"]) {
    const runtime = createRuntime({ pathname });
    const tracking = loadTracking(runtime);

    assert.equal(await tracking.initializeMetaPixel(), false, pathname);
    assert.equal(runtime.appendedScripts.length, 0, pathname);
    assert.equal(runtime.window.fbq, undefined, pathname);
  }
});

test("the pre-hydration bootstrap gates internal paths and deduplicates hydrated PageView", async () => {
  const publicRuntime = createRuntime({ pathname: "/" });
  const bootstrap = loadTypeScriptModule(
    "src/app/lib/meta-pixel-bootstrap.ts",
    publicRuntime,
  );
  const script = bootstrap.buildMetaPixelBootstrap("2118209559079623");
  assert.ok(script);
  vm.runInContext(script, publicRuntime.context);
  vm.runInContext(script, publicRuntime.context);
  assert.equal(publicRuntime.appendedScripts.length, 1);
  assert.equal(
    publicRuntime.window.fbq.queue.filter((entry) => entry[0] === "init").length,
    1,
  );
  assert.equal(
    publicRuntime.window.fbq.queue.filter(
      (entry) => entry[0] === "track" && entry[1] === "PageView",
    ).length,
    1,
  );
  const tracking = loadTracking(publicRuntime);
  assert.equal(tracking.trackMetaPageNavigation("/"), false);
  publicRuntime.appendedScripts[0].dispatch("load");
  assert.equal(await tracking.initializeMetaPixel(), true);

  const internalRuntime = createRuntime({ pathname: "/os/inbox" });
  const internalBootstrap = loadTypeScriptModule(
    "src/app/lib/meta-pixel-bootstrap.ts",
    internalRuntime,
  );
  vm.runInContext(
    internalBootstrap.buildMetaPixelBootstrap("2118209559079623"),
    internalRuntime.context,
  );
  assert.equal(internalRuntime.appendedScripts.length, 0);
  assert.equal(internalRuntime.window.fbq, undefined);
});

test("the inline bootstrap escapes values that could terminate a script element", () => {
  const runtime = createRuntime();
  const bootstrap = loadTypeScriptModule("src/app/lib/meta-pixel-bootstrap.ts", runtime);
  const unsafePixelId = '</script><script id="injected">';
  const script = bootstrap.buildMetaPixelBootstrap(unsafePixelId);
  assert.doesNotMatch(script, /<\/script>/i);
  vm.runInContext(script, runtime.context);
  assert.equal(runtime.window.fbq.queue[0][1], unsafePixelId);
});

test("Meta Pixel initialization is idempotent and PageView fires once per public navigation", async () => {
  const runtime = createRuntime({ pathname: "/" });
  const tracking = loadTracking(runtime);

  const readiness = tracking.initializeMetaPixel();
  const repeatedReadiness = tracking.initializeMetaPixel();
  assert.equal(readiness, repeatedReadiness);
  assert.equal(runtime.appendedScripts.length, 1);
  runtime.appendedScripts[0].dispatch("load");
  assert.equal(await readiness, true);

  assert.equal(tracking.trackMetaPageNavigation("/"), true);
  assert.equal(tracking.trackMetaPageNavigation("/"), false);
  runtime.location.pathname = "/about";
  assert.equal(tracking.trackMetaPageNavigation("/about"), true);
  runtime.location.pathname = "/os";
  assert.equal(tracking.trackMetaPageNavigation("/os"), false);
  runtime.location.pathname = "/";
  assert.equal(tracking.trackMetaPageNavigation("/"), true);

  const queued = runtime.window.fbq.queue;
  assert.equal(queued.filter((entry) => entry[0] === "init").length, 1);
  assert.equal(
    queued.filter((entry) => entry[0] === "track" && entry[1] === "PageView").length,
    3,
  );
});

test("Meta Parameter Builder is lazy, receives the current URL, and is not given an IP callback", async () => {
  const runtime = createRuntime({
    pathname: "/get-a-cash-offer",
    search: "?fbclid=PAID_CLICK&utm_source=facebook",
    parameterBuilder: {
      async processAndCollectAllParams() {
        return {};
      },
    },
  });
  const tracking = loadTracking(runtime);

  assert.equal(runtime.parameterBuilderCalls.length, 0, "the collector must not be statically loaded");
  assert.equal(await tracking.prepareMetaBrowserParameters(), true);
  assert.equal(runtime.parameterBuilderCalls.length, 1);
  assert.deepEqual(Array.from(runtime.parameterBuilderCalls[0]), [
    "https://www.stonegatehb.com/get-a-cash-offer?fbclid=PAID_CLICK&utm_source=facebook",
  ]);
});

test("Meta Parameter Builder recovers an in-app click ID and keeps its SDK appendix opaque", async () => {
  const capturedAtMs = Date.now() - 100;
  const fbc = `fb.1.${capturedAtMs}.IN_APP_CLICK.Bg`;
  const fbp = `fb.1.${capturedAtMs}.browser-id`;
  let runtime;
  runtime = createRuntime({
    pathname: "/get-a-cash-offer",
    search: "?gclid=COINCIDENTAL_GOOGLE_CLICK",
    parameterBuilder: {
      async processAndCollectAllParams() {
        runtime.setCookie(`_fbc=${fbc}; _fbp=${fbp}`);
        return { _fbc: fbc, _fbp: fbp };
      },
    },
  });
  const tracking = loadTracking(runtime);
  const initial = tracking.createMetaBrowserEvent("in-app-event");

  const enriched = await tracking.waitForMetaBrowserCookies(initial, 100);

  assert.equal(enriched.fbc, fbc, "the full official cookie must be sent to Meta");
  assert.equal(enriched.fbp, fbp);
  assert.equal(tracking.getConversionAttribution().fbclid, "IN_APP_CLICK");
  assert.equal(tracking.getConversionAttribution().gclid, "COINCIDENTAL_GOOGLE_CLICK");
  assert.equal(
    tracking.getConversionAttribution().fbclid_captured_at,
    new Date(capturedAtMs).toISOString(),
  );
  assert.equal(runtime.parameterBuilderCalls[0].length, 1, "no external IP collector was supplied");
});

test("tracking never creates fbc when Meta supplies no click identifier", async () => {
  const runtime = createRuntime({ pathname: "/get-a-cash-offer" });
  const tracking = loadTracking(runtime);

  assert.equal(await tracking.prepareMetaBrowserParameters(), true);
  assert.equal(tracking.createMetaBrowserEvent("direct-event").fbc, null);
});

test("Meta cookie enrichment stops at its bounded deadline when the in-app bridge stalls", async () => {
  const runtime = createRuntime({
    pathname: "/get-a-cash-offer",
    parameterBuilder: {
      processAndCollectAllParams() {
        return new Promise(() => {});
      },
    },
  });
  const tracking = loadTracking(runtime);
  const startedAt = Date.now();
  const waiting = tracking.waitForMetaBrowserCookies(
    tracking.createMetaBrowserEvent("bounded-event"),
    20,
  );
  runtime.appendedScripts[0].dispatch("load");

  const event = await waiting;
  assert.equal(event.fbc, null);
  assert.ok(Date.now() - startedAt < 250, "a stalled bridge must not block conversion delivery");
});

test("fbc uses the active click's original millisecond timestamp instead of a stale cookie", () => {
  const runtime = createRuntime({ pathname: "/get-a-cash-offer", search: "?fbclid=NEW_CLICK" });
  runtime.setCookie("_fbc=fb.1.1111111111111.OLD_CLICK");
  const tracking = loadTracking(runtime);

  const attribution = tracking.getConversionAttribution();
  const event = tracking.createMetaBrowserEvent("stable-event-id");
  const capturedAtMs = Date.parse(attribution.fbclid_captured_at);
  assert.equal(event.fbc, `fb.1.${capturedAtMs}.NEW_CLICK`);
  assert.match(event.fbc, /^fb\.1\.\d{13}\.NEW_CLICK$/);

  runtime.location.pathname = "/os/inbox";
  runtime.location.search = "";
  assert.deepEqual(tracking.getConversionAttribution(), attribution);
  runtime.location.pathname = "/about";
  assert.deepEqual(tracking.getConversionAttribution(), attribution);
});

test("UTM-only and internal navigation cannot erase a stored platform click", () => {
  const runtime = createRuntime({ pathname: "/get-a-cash-offer", search: "?fbclid=FIRST_CLICK" });
  const tracking = loadTracking(runtime);
  const original = tracking.getConversionAttribution();

  runtime.location.pathname = "/about";
  runtime.location.search = "?utm_source=newsletter&utm_campaign=follow-up";
  const withNewCampaignLabels = tracking.getConversionAttribution();
  assert.equal(withNewCampaignLabels.fbclid, "FIRST_CLICK");
  assert.equal(withNewCampaignLabels.fbclid_captured_at, original.fbclid_captured_at);
  assert.equal(withNewCampaignLabels.utm_source, "newsletter");

  runtime.location.pathname = "/os/inbox";
  runtime.location.search = "?fbclid=INTERNAL_CLICK";
  assert.deepEqual(tracking.getConversionAttribution(), withNewCampaignLabels);
});

test("a real fbc cookie recovers click ID and time without inventing legacy timestamps", () => {
  const runtime = createRuntime({ pathname: "/get-a-cash-offer" });
  runtime.window.sessionStorage.setItem(
    "stonegate_conversion_attribution_v1",
    JSON.stringify({
      landing_page: "/get-a-cash-offer",
      referrer: null,
      utm_source: null,
      utm_medium: null,
      utm_campaign: null,
      utm_term: null,
      utm_content: null,
      gclid: null,
      fbclid: "LEGACY_CLICK",
    }),
  );
  const tracking = loadTracking(runtime);
  assert.equal(tracking.getConversionAttribution().fbclid_captured_at, null);

  const recoveredRuntime = createRuntime({ pathname: "/get-a-cash-offer" });
  recoveredRuntime.setCookie("_fbc=fb.1.1700000000123.RECOVERED_CLICK");
  const recoveredTracking = loadTracking(recoveredRuntime);
  const recovered = recoveredTracking.getConversionAttribution();
  assert.equal(recovered.fbclid, "RECOVERED_CLICK");
  assert.equal(recovered.fbclid_captured_at, "2023-11-14T22:13:20.123Z");

  recoveredRuntime.setCookie("");
  assert.deepEqual(recoveredTracking.getConversionAttribution(), recovered);
});

test("ViewContent fires immediately and its server envelope waits briefly for fbp", async () => {
  const runtime = createRuntime({ pathname: "/get-a-cash-offer" });
  const eventPayloads = [];
  runtime.setFetch(async (url, options = {}) => {
    if (String(url).endsWith("/api/v1/public/experiments")) {
      return { ok: true, json: async () => ({ experiments: [] }) };
    }
    if (String(url).endsWith("/api/v1/public/conversion-events")) {
      eventPayloads.push(JSON.parse(options.body));
      return { ok: true, status: 201 };
    }
    throw new Error(`Unexpected URL: ${url}`);
  });
  const tracking = loadTracking(runtime);

  const recording = tracking.recordMetaViewContent("https://api.stonegatehb.com", {
    page: "cash_offer",
  });
  const queuedViewContent = runtime.window.fbq.queue.find(
    (entry) => entry[0] === "track" && entry[1] === "ViewContent",
  );
  assert.ok(queuedViewContent, "ViewContent should queue before waiting for the cookie.");
  runtime.appendedScripts[0].dispatch("load");
  runtime.window.setTimeout(() => runtime.setCookie("_fbp=fb.1.1234567890123.browser-id"), 40);

  assert.equal(await recording, true);
  assert.equal(eventPayloads.length, 1);
  assert.equal(eventPayloads[0].meta_browser_event.fbp, "fb.1.1234567890123.browser-id");
  assert.equal(
    eventPayloads[0].meta_browser_event.event_id,
    queuedViewContent[3].eventID,
  );
});

test("conversion recording exposes unsuccessful responses without throwing into the UI", async () => {
  const runtime = createRuntime({ pixelId: "" });
  let conversionResponseOk = false;
  runtime.setFetch(async (url) => {
    if (String(url).endsWith("/api/v1/public/experiments")) {
      return { ok: true, json: async () => ({ experiments: [] }) };
    }
    return { ok: conversionResponseOk, status: conversionResponseOk ? 201 : 503 };
  });
  const tracking = loadTracking(runtime);

  assert.equal(await tracking.recordConversionEvent("https://api.stonegatehb.com", "form_start"), false);
  conversionResponseOk = true;
  assert.equal(await tracking.recordConversionEvent("https://api.stonegatehb.com", "form_start"), true);
});

test("conversion delivery never waits for the optional experiment endpoint", async () => {
  const runtime = createRuntime({ pixelId: "" });
  let releaseExperiment;
  let conversionPosted = false;
  runtime.setFetch(async (url) => {
    if (String(url).endsWith("/api/v1/public/experiments")) {
      return new Promise((resolveExperiment) => {
        releaseExperiment = () =>
          resolveExperiment({ ok: true, json: async () => ({ experiments: [] }) });
      });
    }
    conversionPosted = true;
    return { ok: true, status: 201 };
  });
  const tracking = loadTracking(runtime);

  const result = await tracking.recordConversionEvent(
    "https://api.stonegatehb.com",
    "page_view",
  );
  assert.equal(result, true);
  assert.equal(conversionPosted, true);
  releaseExperiment();
  await tracking.getConversionExperimentContext("https://api.stonegatehb.com");
});

test("a resolved experiment emits one successful exposure per session", async () => {
  const runtime = createRuntime({ pixelId: "" });
  const payloads = [];
  runtime.setFetch(async (url, options = {}) => {
    if (String(url).endsWith("/api/v1/public/experiments")) {
      return {
        ok: true,
        json: async () => ({
          experiments: [
            {
              experiment_key: "offer_flow_v1",
              surface_key: "cash_offer",
              variants: [
                {
                  key: "control",
                  label: "Control",
                  weight_basis_points: 10_000,
                  cta_label: "Review My Options",
                },
              ],
            },
          ],
        }),
      };
    }
    payloads.push(JSON.parse(options.body));
    return { ok: true, status: 201 };
  });
  const tracking = loadTracking(runtime);

  await Promise.all([
    tracking.recordConversionEvent("https://api.stonegatehb.com", "page_view"),
    tracking.recordConversionEvent("https://api.stonegatehb.com", "form_start"),
  ]);
  await tracking.getConversionExperimentContext("https://api.stonegatehb.com");
  await nextTurn();
  await tracking.recordConversionEvent("https://api.stonegatehb.com", "form_step_complete");
  await nextTurn();

  const exposures = payloads.filter((payload) => payload.event_type === "experiment_exposure");
  assert.equal(exposures.length, 1);
  assert.equal(exposures[0].experiment_key, "offer_flow_v1");
  assert.equal(exposures[0].experiment_variant, "control");
  assert.equal(exposures[0].metadata.surface_key, "cash_offer");
});

test("a failed experiment exposure can retry without concurrent duplicates", async () => {
  const runtime = createRuntime({ pixelId: "" });
  let exposureAttempts = 0;
  runtime.setFetch(async (url, options = {}) => {
    if (String(url).endsWith("/api/v1/public/experiments")) {
      return {
        ok: true,
        json: async () => ({
          experiments: [
            {
              experiment_key: "retry_exposure_v1",
              surface_key: "cash_offer",
              variants: [
                {
                  key: "control",
                  label: "Control",
                  weight_basis_points: 10_000,
                  cta_label: "Continue",
                },
              ],
            },
          ],
        }),
      };
    }
    const payload = JSON.parse(options.body);
    if (payload.event_type === "experiment_exposure") {
      exposureAttempts += 1;
      return { ok: exposureAttempts > 1, status: exposureAttempts > 1 ? 201 : 503 };
    }
    return { ok: true, status: 201 };
  });
  const tracking = loadTracking(runtime);

  await tracking.recordConversionEvent("https://api.stonegatehb.com", "page_view");
  await tracking.getConversionExperimentContext("https://api.stonegatehb.com");
  await nextTurn();
  assert.equal(exposureAttempts, 1);

  await Promise.all([
    tracking.recordConversionEvent("https://api.stonegatehb.com", "form_start"),
    tracking.recordConversionEvent("https://api.stonegatehb.com", "form_step_complete"),
  ]);
  await nextTurn();
  assert.equal(exposureAttempts, 2);
  await tracking.recordConversionEvent("https://api.stonegatehb.com", "form_submit_attempt");
  await nextTurn();
  assert.equal(exposureAttempts, 2);
});
