import { existsSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";

import { chromium } from "playwright-core";

const baseUrl = process.env.PUBLIC_AUDIT_BASE_URL ?? "http://127.0.0.1:3000";
const screenshotDirectory = process.env.PUBLIC_AUDIT_SCREENSHOT_DIR;
const require = createRequire(import.meta.url);
const axePath = require.resolve("axe-core/axe.min.js");
const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const executablePath = process.env.CHROME_EXECUTABLE_PATH ??
  (existsSync(macChrome) ? macChrome : undefined);
const findings = [];
const contactConsentWording =
  "By submitting this form, you authorize Stonegate Home Buyers to contact you by phone call or email about your property inquiry and possible selling options. This permission does not include text messages.";
const smsConsentWording =
  "By checking this optional box, I agree to receive recurring automated text messages from Stonegate Home Buyers about my property inquiry, appointments, and possible selling options at the number provided. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase. See our Terms & Conditions and Privacy Policy.";
const addressSavingDisclosure =
  "Property details may be saved when you continue, even if you do not finish the form. We may use them to identify the property, maintain inquiry records, research the property owner, and measure form performance.";
const directOfferDisclosure =
  "Stonegate Home Buyers is a real estate investment company, not a brokerage or appraisal service. A direct cash offer may be below potential retail market value in exchange for an as-is sale and fewer listing steps. Any purchase remains subject to written contract terms, title review, and property verification.";

if (screenshotDirectory) mkdirSync(screenshotDirectory, { recursive: true });

function record(viewport, type, detail) {
  findings.push({ viewport, type, detail });
}

async function installApiStubs(page, state) {
  await page.route("**/api/v1/public/experiments", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        experiments: [
          {
            experiment_key: "audit_homepage_cta",
            surface_key: "homepage_offer_cta",
            variants: [
              {
                key: "control",
                label: "Current CTA",
                weight_basis_points: 5000,
                cta_label: "Start My Offer",
              },
              {
                key: "treatment",
                label: "Test CTA",
                weight_basis_points: 5000,
                cta_label: "Get My Cash Offer",
              },
            ],
          },
        ],
      }),
    });
  });
  await page.route("**/api/v1/public/conversion-events", async (route) => {
    state.events.push(route.request().postDataJSON());
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: crypto.randomUUID(), event_type: "test" }) });
  });
  await page.route("**/api/v1/public/address-suggestions?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        available: true,
        suggestions: [
          {
            provider_id: "audit-property-123",
            label: "123 Main St, Atlanta, GA 30303",
            street_address: "123 Main St",
            city: "Atlanta",
            state: "GA",
            postal_code: "30303",
          },
        ],
      }),
    });
  });
  await page.route("**/api/v1/public/seller-leads/enrichment", async (route) => {
    state.enrichments.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        lead_id: "11111111-2222-4333-8444-555555555555",
        enriched_at: new Date().toISOString(),
        message: "Thanks. The additional property details were added to your request.",
      }),
    });
  });
  await page.route("**/api/v1/public/seller-leads/address-capture", async (route) => {
    state.addressCaptures.push(route.request().postDataJSON());
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        lead_id: "11111111-2222-4333-8444-555555555555",
        contact_id: "22222222-2222-4333-8444-555555555555",
        property_id: "33333333-2222-4333-8444-555555555555",
        completion_status: "address_only",
        created: state.addressCaptures.length === 1,
      }),
    });
  });
  await page.route("**/api/v1/public/seller-leads", async (route) => {
    state.submissions.push(route.request().postDataJSON());
    if (state.failNextSubmission) {
      state.failNextSubmission = false;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Stonegate could not save the request yet. Please try again." }),
      });
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        lead_id: "11111111-2222-4333-8444-555555555555",
        contact_id: "22222222-2222-4333-8444-555555555555",
        property_id: "33333333-2222-4333-8444-555555555555",
        duplicate_status: "created",
        matched_existing_lead: false,
        consent_wording_version: "seller-contact-web-v3",
        enrichment_token: "test-enrichment-token-that-is-long-enough-for-the-api",
        enrichment_expires_at: new Date(Date.now() + 86_400_000).toISOString(),
        message: "Thanks. Your property inquiry was received.",
        meta_pixel_event_name: "Contact",
      }),
    });
  });
}

async function checkPage(page, viewport, step) {
  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    duplicateIds: [...document.querySelectorAll("[id]")]
      .map((element) => element.id)
      .filter((id, index, ids) => ids.indexOf(id) !== index),
  }));
  if (layout.scrollWidth > layout.clientWidth) record(viewport, "horizontal-overflow", { step, ...layout });
  if (layout.duplicateIds.length) record(viewport, "duplicate-ids", { step, ids: [...new Set(layout.duplicateIds)] });

  await page.addScriptTag({ path: axePath });
  const violations = await page.evaluate(async () => {
    const result = await window.axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] },
    });
    return result.violations
      .filter((violation) => ["serious", "critical"].includes(violation.impact))
      .map((violation) => ({ id: violation.id, targets: violation.nodes.map((node) => node.target) }));
  });
  if (violations.length) record(viewport, "wcag", { step, violations });
}

async function waitForOfferScrollController(page) {
  await page.waitForFunction(
    () => window.history.scrollRestoration === "manual",
    undefined,
    { timeout: 8_000 },
  );
  await page.evaluate(
    () =>
      new Promise((resolve) => {
        window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
      }),
  );
}

async function checkMobileActionBar(page, viewport, expectedOfferHref, step) {
  const bar = page.getByRole("navigation", { name: "Quick seller actions" });
  const shouldBeVisible = viewport.width <= 720;
  if (!shouldBeVisible) {
    if (await bar.isVisible()) {
      record(viewport.name, "mobile-action-bar", `${step}: bar is visible on desktop.`);
    }
    return;
  }

  if (!(await bar.isVisible())) {
    record(viewport.name, "mobile-action-bar", `${step}: bar is not visible on mobile.`);
    return;
  }
  const call = bar.getByRole("link", { name: "Call" });
  const offer = bar.getByRole("link", { name: "See My Options" });
  const measurements = await bar.evaluate((element) => {
    const barRect = element.getBoundingClientRect();
    const targets = [...element.querySelectorAll("a")].map((target) => {
      const rect = target.getBoundingClientRect();
      return { height: rect.height, width: rect.width };
    });
    return {
      bar: {
        bottom: barRect.bottom,
        left: barRect.left,
        right: barRect.right,
      },
      targets,
      viewportHeight: window.innerHeight,
      viewportWidth: window.innerWidth,
    };
  });
  if (
    Math.abs(measurements.bar.bottom - measurements.viewportHeight) > 1 ||
    measurements.bar.left < -1 ||
    measurements.bar.right > measurements.viewportWidth + 1
  ) {
    record(viewport.name, "mobile-action-bar", { step, measurements });
  }
  if (measurements.targets.some((target) => target.height < 44 || target.width < 44)) {
    record(viewport.name, "tap-target", { step, targets: measurements.targets });
  }
  if ((await call.getAttribute("href")) !== "tel:+16785417725") {
    record(viewport.name, "mobile-action-bar", `${step}: call destination is incorrect.`);
  }
  if ((await offer.getAttribute("href")) !== expectedOfferHref) {
    record(viewport.name, "mobile-action-bar", {
      step,
      expectedOfferHref,
      actual: await offer.getAttribute("href"),
    });
  }
}

async function checkFocusedControlClearance(page, viewport, locator, step) {
  if (viewport.width > 720) return;
  await locator.evaluate((element) => element.scrollIntoView({ block: "center" }));
  const bar = page.getByRole("navigation", { name: "Quick seller actions" });
  if (!(await bar.count())) return;
  const [controlBox, barBox] = await Promise.all([locator.boundingBox(), bar.boundingBox()]);
  if (
    controlBox &&
    barBox &&
    controlBox.y + controlBox.height > barBox.y &&
    controlBox.y < barBox.y + barBox.height
  ) {
    record(viewport.name, "fixed-control-overlap", { step, controlBox, barBox });
  }
}

async function auditDiscovery(page, viewport) {
  if (await page.title() !== "Stonegate Home Buyers | Sell Your Georgia House As-Is") {
    record(viewport, "metadata", { field: "title", value: await page.title() });
  }
  const canonical = await page
    .locator('link[rel="canonical"]')
    .getAttribute("href", { timeout: 1_000 })
    .catch(() => null);
  if (canonical !== "https://www.stonegatehb.com") {
    record(viewport, "metadata", { field: "canonical", value: canonical });
  }

  const structuredData = await page.locator('script[type="application/ld+json"]').first().textContent();
  try {
    const graph = JSON.parse(structuredData ?? "{}")["@graph"] ?? [];
    const organization = graph.find((item) => item["@type"] === "Organization");
    const types = graph.map((item) => item["@type"]);
    if (
      organization?.url !== "https://www.stonegatehb.com" ||
      organization?.telephone !== "+1-678-541-7725" ||
      organization?.email !== "offers@stonegatehb.com" ||
      !organization?.logo?.url
    ) {
      record(viewport, "structured-data", organization ?? "Organization record missing.");
    }
    if (types.includes("Review") || types.includes("AggregateRating")) {
      record(
        viewport,
        "structured-data",
        "Self-serving Review or AggregateRating schema must not be published.",
      );
    }
  } catch {
    record(viewport, "structured-data", "Homepage JSON-LD could not be parsed.");
  }

  const robotsResponse = await page.context().request.get(`${baseUrl}/robots.txt`);
  const robots = await robotsResponse.text();
  for (const route of ["/os", "/sign-in", "/sign-up"]) {
    if (!robots.includes(`Disallow: ${route}`)) {
      record(viewport, "robots", `Missing private route: ${route}`);
    }
  }

  const sitemapResponse = await page.context().request.get(`${baseUrl}/sitemap.xml`);
  const sitemap = await sitemapResponse.text();
  if (!sitemap.includes("https://www.stonegatehb.com/get-a-cash-offer")) {
    record(viewport, "sitemap", "Cash-offer page is missing.");
  }
  if (!sitemap.includes("https://www.stonegatehb.com/contact")) {
    record(viewport, "sitemap", "Contact and service-area page is missing.");
  }
  if (!sitemap.includes("https://www.stonegatehb.com/service-areas/metro-atlanta")) {
    record(viewport, "sitemap", "Metro Atlanta service-area page is missing.");
  }
  for (const route of ["/os", "/sign-in", "/sign-up"]) {
    if (sitemap.includes(route)) {
      record(viewport, "sitemap", `Private route was published: ${route}`);
    }
  }
  if (sitemap.includes("<lastmod>")) {
    record(viewport, "sitemap", "Sitemap contains unverified modification dates.");
  }

  for (const route of ["/sign-in", "/sign-up"]) {
    const response = await page.context().request.get(`${baseUrl}${route}`);
    if (!response.headers()["x-robots-tag"]?.includes("noindex")) {
      record(viewport, "private-indexing", {
        route,
        xRobotsTag: response.headers()["x-robots-tag"] ?? null,
      });
    }
    const html = await response.text();
    if (!html.includes('name="robots"') || !html.includes("noindex")) {
      record(viewport, "private-indexing", `${route} is missing noindex metadata.`);
    }
  }
}

async function auditPublicProof(page, viewport) {
  const proof = page.locator('[data-public-proof="true"]');
  if ((await proof.count()) === 0) {
    if (await page.getByText("Verified Stonegate proof", { exact: true }).count()) {
      record(viewport, "public-proof", "An empty proof heading is visible.");
    }
    return;
  }

  const text = (await proof.innerText()).toLowerCase();
  if (!text.includes("individual records")) {
    record(viewport, "public-proof", "The individual-outcome context is missing.");
  }
  for (const marker of ["lorem ipsum", "sample testimonial", "placeholder"]) {
    if (text.includes(marker)) {
      record(viewport, "public-proof", `Disallowed marker is visible: ${marker}`);
    }
  }
  if ((await proof.locator("article, figure").count()) === 0) {
    record(viewport, "public-proof", "The proof section has no published records.");
  }
}

async function auditTeamIdentity(page, viewport, route) {
  const teamSection = page.locator('[data-public-team="true"]');
  const teamCount = await teamSection.count();
  const pageText = (await page.locator("main").innerText()).toLowerCase();

  for (const marker of ["coming soon", "lorem ipsum", "placeholder", "sample bio"]) {
    if (pageText.includes(marker)) {
      record(viewport, "public-team", { route, detail: `Disallowed marker is visible: ${marker}` });
    }
  }

  if (teamCount === 0) return;

  const images = teamSection.locator("img");
  if ((await images.count()) === 0) {
    record(viewport, "public-team", { route, detail: "Published team content has no photograph." });
    return;
  }

  for (let index = 0; index < (await images.count()); index += 1) {
    const image = images.nth(index);
    const imageState = await image.evaluate((element) => ({
      alt: element.getAttribute("alt")?.trim() ?? "",
      complete: element.complete,
      naturalWidth: element.naturalWidth,
      naturalHeight: element.naturalHeight,
    }));
    if (
      imageState.alt.length < 8 ||
      !imageState.complete ||
      imageState.naturalWidth < 250 ||
      imageState.naturalHeight < 250
    ) {
      record(viewport, "public-team-image", { route, index, imageState });
    }
  }
}

async function auditAboutPage(page, viewport) {
  const route = "/about";
  await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle" });
  await checkPage(page, viewport.name, "about-page");
  await checkMobileActionBar(page, viewport, "/get-a-cash-offer", "about-page");
  await auditTeamIdentity(page, viewport.name, route);

  if (
    !(await page
      .locator("footer")
      .getByText(directOfferDisclosure, { exact: true })
      .isVisible())
  ) {
    record(viewport.name, "public-footer", "Standard pages lost the direct-offer disclosure.");
  }

  if ((await page.title()) !== "About Stonegate Home Buyers | Georgia") {
    record(viewport.name, "metadata", { route, title: await page.title() });
  }
  const canonical = await page
    .locator('link[rel="canonical"]')
    .getAttribute("href", { timeout: 1_000 })
    .catch(() => null);
  if (canonical !== "https://www.stonegatehb.com/about") {
    record(viewport.name, "metadata", { route, canonical });
  }
  if (!(await page.getByText("A simpler sale should still be an informed sale.").isVisible())) {
    record(viewport.name, "about-content", "The company-story section is missing.");
  }
  for (const heading of ["Seller conversation", "Property decision", "Written follow-through"]) {
    if (!(await page.getByText(heading, { exact: true }).isVisible())) {
      record(viewport.name, "about-content", `The accountability step is missing: ${heading}`);
    }
  }
  if (screenshotDirectory) {
    await page.screenshot({
      fullPage: true,
      path: `${screenshotDirectory}/about-${viewport.name}.png`,
    });
  }
}

async function auditContactPage(page, viewport) {
  await page.goto(`${baseUrl}/contact`, { waitUntil: "networkidle" });
  await checkPage(page, viewport.name, "contact-page");
  await checkMobileActionBar(page, viewport, "/get-a-cash-offer", "contact-page");

  if (
    (await page.title()) !==
    "Contact Stonegate Home Buyers | Metro Atlanta Service Area"
  ) {
    record(viewport.name, "metadata", { route: "/contact", title: await page.title() });
  }
  const canonical = await page
    .locator('link[rel="canonical"]')
    .getAttribute("href", { timeout: 1_000 })
    .catch(() => null);
  if (canonical !== "https://www.stonegatehb.com/contact") {
    record(viewport.name, "metadata", { route: "/contact", canonical });
  }

  const structuredData = await page.locator('script[type="application/ld+json"]').first().textContent();
  try {
    const contactPage = JSON.parse(structuredData ?? "{}");
    if (
      contactPage["@type"] !== "ContactPage" ||
      contactPage.mainEntity?.telephone !== "+1-678-541-7725" ||
      contactPage.mainEntity?.email !== "offers@stonegatehb.com" ||
      !contactPage.mainEntity?.areaServed?.some?.((area) => area.name === "Georgia") ||
      !contactPage.mainEntity?.areaServed?.some?.((area) => area.name === "Metro Atlanta, Georgia")
    ) {
      record(viewport.name, "structured-data", {
        route: "/contact",
        value: contactPage,
      });
    }
  } catch {
    record(viewport.name, "structured-data", "Contact JSON-LD could not be parsed.");
  }

  const phoneLink = page
    .locator("main")
    .getByRole("link", { name: /\(678\) 541-7725/ })
    .first();
  const emailLink = page
    .locator("main")
    .getByRole("link", { name: /Email Stonegate/ })
    .first();
  if ((await phoneLink.getAttribute("href")) !== "tel:+16785417725") {
    record(viewport.name, "contact-destination", "Contact phone destination is incorrect.");
  }
  if (!(await emailLink.getAttribute("href"))?.startsWith("mailto:offers@stonegatehb.com")) {
    record(viewport.name, "contact-destination", "Contact email destination is incorrect.");
  }
  if (!(await page.getByText("Online property requests are accepted 24 hours a day.").isVisible())) {
    record(viewport.name, "contact-fact", "Request availability is missing.");
  }
  if (!(await page.getByText("Metro Atlanta and surrounding Georgia communities").isVisible())) {
    record(viewport.name, "contact-fact", "Service-area summary is missing.");
  }
  if (screenshotDirectory) {
    await page.screenshot({
      fullPage: true,
      path: `${screenshotDirectory}/contact-${viewport.name}.png`,
    });
  }
}

async function auditServiceAreaPage(page, viewport) {
  const route = "/service-areas/metro-atlanta";
  await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle" });
  await checkPage(page, viewport.name, "service-area-page");
  await checkMobileActionBar(page, viewport, "/get-a-cash-offer", "service-area-page");

  if ((await page.title()) !== "Metro Atlanta Home Buyers | Sell Your House As-Is") {
    record(viewport.name, "metadata", { route, title: await page.title() });
  }
  const canonical = await page
    .locator('link[rel="canonical"]')
    .getAttribute("href", { timeout: 1_000 })
    .catch(() => null);
  if (canonical !== "https://www.stonegatehb.com/service-areas/metro-atlanta") {
    record(viewport.name, "metadata", { route, canonical });
  }

  const structuredData = await page.locator('script[type="application/ld+json"]').first().textContent();
  try {
    const graph = JSON.parse(structuredData ?? "{}")["@graph"] ?? [];
    const types = graph.map((item) => item["@type"]);
    for (const expectedType of ["WebPage", "Service", "BreadcrumbList"]) {
      if (!types.includes(expectedType)) {
        record(viewport.name, "structured-data", {
          route,
          missingType: expectedType,
          types,
        });
      }
    }
    const service = graph.find((item) => item["@type"] === "Service");
    if (
      service?.provider?.["@id"] !== "https://www.stonegatehb.com/#organization" ||
      service?.areaServed?.name !== "Metro Atlanta, Georgia"
    ) {
      record(viewport.name, "structured-data", { route, service });
    }
    if (types.includes("LocalBusiness")) {
      record(viewport.name, "structured-data", {
        route,
        detail: "LocalBusiness must remain absent until a qualifying address is confirmed.",
      });
    }
  } catch {
    record(viewport.name, "structured-data", "Service-area JSON-LD could not be parsed.");
  }

  for (const href of [
    "/sell-inherited-house",
    "/sell-house-needs-repairs",
    "/sell-house-fast",
    "/how-it-works",
  ]) {
    if (!(await page.locator(`a[href="${href}"]:visible`).first().isVisible())) {
      record(viewport.name, "internal-link", { route, href });
    }
  }
  if (!(await page.getByText("The address decides whether Stonegate can help.").isVisible())) {
    record(viewport.name, "service-area-content", "Address-based coverage explanation is missing.");
  }
  if (screenshotDirectory) {
    await page.screenshot({
      fullPage: true,
      path: `${screenshotDirectory}/service-area-${viewport.name}.png`,
    });
  }
}

async function auditJourney(browser, viewport) {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport });
  const page = await context.newPage();
  const state = {
    addressCaptures: [],
    events: [],
    submissions: [],
    enrichments: [],
    failNextSubmission: true,
  };
  const browserErrors = [];
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      message.text() !== "Failed to load resource: the server responded with a status of 503 (Service Unavailable)"
    ) {
      browserErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await installApiStubs(page, state);

  await page.goto(`${baseUrl}/get-a-cash-offer?utm_source=facebook&fbclid=FRESH_AUDIT`, {
    waitUntil: "networkidle",
  });
  await waitForOfferScrollController(page);
  const freshEntryScrollY = await page.evaluate(() => window.scrollY);
  if (freshEntryScrollY > 1) {
    record(viewport.name, "offer-entry", { stage: "fresh", scrollY: freshEntryScrollY });
  }
  if (screenshotDirectory) {
    await page.screenshot({
      fullPage: true,
      path: `${screenshotDirectory}/offer-fresh-${viewport.name}.png`,
    });
  }
  await page.evaluate(() => window.sessionStorage.clear());

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await checkPage(page, viewport.name, "homepage");
  await auditPublicProof(page, viewport.name);
  await auditTeamIdentity(page, viewport.name, "/");
  await checkMobileActionBar(
    page,
    viewport,
    "/get-a-cash-offer",
    "homepage",
  );
  if (viewport.name === "desktop") {
    await auditDiscovery(page, viewport.name);
  }
  await page.getByLabel("Property address").first().fill("123 Main St");
  await page.getByRole("button", { name: /Start My Offer|Get My Cash Offer/ }).first().click();
  await page.waitForURL(/\/get-a-cash-offer\?address=123\+Main\+St/);
  if (await page.getByRole("navigation", { name: "Primary navigation" }).count()) {
    record(viewport.name, "offer-shell", "The focused offer page still exposes primary navigation.");
  }
  const landingHome = page.getByRole("link", { name: "Stonegate Home Buyers home" });
  if ((await landingHome.count()) !== 1 || (await landingHome.getAttribute("href")) !== "/") {
    record(viewport.name, "offer-shell", "The focused offer page is missing its linked company logo.");
  }
  const landingPhone = page.locator('header a[href="tel:+16785417725"]');
  if ((await landingPhone.count()) !== 1) {
    record(viewport.name, "offer-shell", "The focused offer page is missing its tap-to-call header action.");
  }
  for (const [name, href] of [
    ["Privacy Policy", "/privacy-policy"],
    ["Terms & Conditions", "/terms"],
  ]) {
    const legalLink = page.getByRole("navigation", { name: "Legal information" }).getByRole("link", { name });
    if ((await legalLink.count()) !== 1 || (await legalLink.getAttribute("href")) !== href) {
      record(viewport.name, "offer-shell", `The focused offer page is missing ${name}.`);
    }
  }
  if (await page.getByText(addressSavingDisclosure, { exact: true }).count()) {
    record(viewport.name, "offer-clutter", "The Step 1 address-saving disclaimer is still visible.");
  }
  if (
    await page
      .locator("footer")
      .getByText(directOfferDisclosure, { exact: true })
      .count()
  ) {
    record(viewport.name, "offer-clutter", "The conversion footer disclaimer is still visible.");
  }
  if (
    await page.getByRole("navigation", { name: "Quick seller actions" }).count()
  ) {
    record(viewport.name, "offer-clutter", "The focused offer page still has a fixed action bar.");
  }

  if (viewport.width <= 720) {
    const offerEntryUrl = new URL(page.url());
    offerEntryUrl.searchParams.set("utm_source", "facebook");
    offerEntryUrl.searchParams.set("fbclid", "AUDIT_CLICK");
    const expectedOfferSearch = offerEntryUrl.search;
    offerEntryUrl.hash = "cash-offer-form";
    await page.goto(offerEntryUrl.toString(), { waitUntil: "domcontentloaded" });
    await waitForOfferScrollController(page);
    const legacyEntryState = await page.evaluate(() => ({
      hash: window.location.hash,
      scrollY: window.scrollY,
    }));
    if (legacyEntryState.hash || legacyEntryState.scrollY > 1) {
      record(viewport.name, "offer-entry", { stage: "legacy-hash", ...legacyEntryState });
    }
    if (new URL(page.url()).search !== expectedOfferSearch) {
      record(viewport.name, "offer-entry", "Legacy hash cleanup discarded attribution parameters.");
    }

    const addressBox = await page.locator("#property_address").boundingBox();
    if (!addressBox || addressBox.y < 0 || addressBox.y + addressBox.height > viewport.height) {
      record(viewport.name, "first-screen-action", {
        detail: "The address field is not fully visible on the first mobile screen.",
        addressBox,
        viewport,
      });
    }

    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForOfferScrollController(page);
    const reloadScrollY = await page.evaluate(() => window.scrollY);
    if (reloadScrollY > 1) {
      record(viewport.name, "offer-entry", { stage: "reload", scrollY: reloadScrollY });
    }
    if (new URL(page.url()).search !== expectedOfferSearch) {
      record(viewport.name, "offer-entry", "Reloading discarded attribution parameters.");
    }

    await page.evaluate(() => {
      window.scrollTo(0, document.documentElement.scrollHeight);
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    });
    await waitForOfferScrollController(page);
    const restoredPageScrollY = await page.evaluate(() => window.scrollY);
    if (restoredPageScrollY > 1) {
      record(viewport.name, "offer-entry", {
        stage: "restored-page",
        scrollY: restoredPageScrollY,
      });
    }
  }
  await page
    .waitForFunction(
      () => document.querySelector("#property_address")?.value === "123 Main St",
      undefined,
      { timeout: 8_000 },
    )
    .catch(() => undefined);
  if ((await page.locator("#property_address").inputValue()) !== "123 Main St") {
    record(viewport.name, "address-prefill", "Homepage address was not preserved.");
  }
  if (screenshotDirectory) {
    await page.screenshot({
      fullPage: true,
      path: `${screenshotDirectory}/offer-property-${viewport.name}.png`,
    });
  }
  await page.locator("#property_address").focus();
  const addressOption = page.getByRole("option", { name: "123 Main St, Atlanta, GA 30303" });
  await addressOption.waitFor();
  await page.locator("#property_address").press("Enter");
  if ((await page.locator("#property_address").inputValue()) !== "123 Main St, Atlanta, GA 30303") {
    record(viewport.name, "address-autocomplete", "The selected address was not shown in the field.");
  }
  await page.getByRole("button", { name: "Edit address" }).click();
  const propertyFieldSemantics = await page.evaluate(() =>
    Object.fromEntries(
      ["property_address", "property_city", "property_state", "property_postal_code"].map(
        (id) => {
          const control = document.getElementById(id);
          return [
            id,
            {
              autocomplete: control?.getAttribute("autocomplete") ?? null,
              required: control?.hasAttribute("required") ?? false,
            },
          ];
        },
      ),
    ),
  );
  const expectedPropertyAutocomplete = {
    property_address: "section-property address-line1",
    property_city: "section-property address-level2",
    property_state: "section-property address-level1",
    property_postal_code: "section-property postal-code",
  };
  for (const [field, autocomplete] of Object.entries(expectedPropertyAutocomplete)) {
    if (
      !propertyFieldSemantics[field]?.required ||
      propertyFieldSemantics[field]?.autocomplete !== autocomplete
    ) {
      record(viewport.name, "form-autofill", {
        field,
        expected: { autocomplete, required: true },
        actual: propertyFieldSemantics[field],
      });
    }
  }
  if (
    (await page.getByText("Required step", { exact: true }).count()) ||
    (await page.locator("#cash-offer-form em").filter({ hasText: "Required" }).count())
  ) {
    record(viewport.name, "requirement-presentation", "Required fields use warning-like badges.");
  }

  await page.locator("#property_city").fill("");
  await page.locator("#property_postal_code").fill("");
  await page.getByRole("button", { name: /Continue/ }).click();
  if (state.addressCaptures.length !== 0) {
    record(viewport.name, "address-capture", "Invalid Step 1 created an address-only lead.");
  }
  if (!(await page.locator("#property_city-error").isVisible())) {
    record(viewport.name, "validation", "Property step did not expose field errors.");
  }
  await page.locator("#property_city").fill("Atlanta");
  await page.locator("#property_state").fill("GA");
  await page.locator("#property_postal_code").fill("30303");
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.waitForTimeout(900);
  if (state.addressCaptures.length !== 1) {
    record(viewport.name, "address-capture", {
      detail: "Valid Step 1 did not create exactly one initial address capture.",
      count: state.addressCaptures.length,
    });
  }
  const initialAddressCapture = state.addressCaptures[0];
  if (
    !initialAddressCapture?.intake_attempt_id ||
    initialAddressCapture.property_address !== "123 Main St" ||
    initialAddressCapture.property_city !== "Atlanta" ||
    initialAddressCapture.property_state !== "GA" ||
    initialAddressCapture.property_postal_code !== "30303"
  ) {
    record(viewport.name, "address-capture-payload", initialAddressCapture ?? null);
  }
  for (const forbidden of [
    "name",
    "phone",
    "email",
    "consent_to_contact",
    "sms_consent",
    "desired_timeline",
  ]) {
    if (forbidden in (initialAddressCapture ?? {})) {
      record(viewport.name, "address-capture-payload", `Step 1 included ${forbidden}.`);
    }
  }
  if (
    initialAddressCapture?.meta_browser_event?.event_id !==
    `stonegate-lead-${initialAddressCapture?.intake_attempt_id}`
  ) {
    record(
      viewport.name,
      "meta-lead-identity",
      "Step 1 did not use the deterministic address Lead event ID.",
    );
  }
  await checkPage(page, viewport.name, "contact");
  await page.getByRole("button", { name: "Back" }).click();
  if ((await page.locator("#property_city").inputValue()) !== "Atlanta") {
    record(viewport.name, "back-navigation", "Property answer was not preserved.");
  }
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.waitForTimeout(20);
  if (
    state.addressCaptures.some(
      (capture) => capture.intake_attempt_id !== initialAddressCapture?.intake_attempt_id,
    )
  ) {
    record(viewport.name, "address-capture-identity", "Back/continue changed the attempt ID.");
  }
  const contactFieldSemantics = await page.evaluate(() =>
    Object.fromEntries(
      ["name", "phone", "email", "sms_consent"].map((id) => {
        const control = document.getElementById(id);
        return [
          id,
          {
            autocomplete: control?.getAttribute("autocomplete") ?? null,
            required: control?.hasAttribute("required") ?? false,
            type: control?.getAttribute("type") ?? null,
          },
        ];
      }),
    ),
  );
  const expectedContactSemantics = {
    name: { autocomplete: "section-contact name", required: true, type: null },
    phone: { autocomplete: "section-contact tel", required: true, type: "tel" },
    email: { autocomplete: "section-contact email", required: false, type: "email" },
    sms_consent: { autocomplete: null, required: false, type: "checkbox" },
  };
  for (const [field, expected] of Object.entries(expectedContactSemantics)) {
    const actual = contactFieldSemantics[field];
    if (
      !actual ||
      actual.autocomplete !== expected.autocomplete ||
      actual.required !== expected.required ||
      actual.type !== expected.type
    ) {
      record(viewport.name, "form-autofill", { field, expected, actual });
    }
  }
  const contactDisclosure = page.getByText(contactConsentWording, { exact: true });
  if ((await contactDisclosure.count()) !== 1 || !(await contactDisclosure.isVisible())) {
    record(viewport.name, "contact-consent-copy", {
      expected: contactConsentWording,
      matches: await contactDisclosure.count(),
    });
  }
  const visibleSmsConsent = (await page.locator('label:has(#sms_consent) small').innerText())
    .replace(/\s+/g, " ")
    .trim();
  if (visibleSmsConsent !== smsConsentWording) {
    record(viewport.name, "sms-consent-copy", {
      expected: smsConsentWording,
      actual: visibleSmsConsent,
    });
  }
  if (await page.locator("#sms_consent").isChecked()) {
    record(viewport.name, "sms-consent-default", "Optional SMS consent was checked by default.");
  }
  for (const selector of ["#consent_to_contact", 'input[name="preferred_contact_method"]']) {
    if (await page.locator(selector).count()) {
      record(viewport.name, "removed-consent-control", {
        selector,
        message: "The website should use phone follow-up by default and a separate optional SMS checkbox.",
      });
    }
  }
  if (
    (await page.locator("#phone").getAttribute("required")) === null ||
    (await page.locator("#email").getAttribute("required")) !== null
  ) {
    record(
      viewport.name,
      "contact-requirement",
      "Phone must remain required while email remains optional.",
    );
  }
  if (screenshotDirectory) {
    await page.screenshot({ fullPage: true, path: `${screenshotDirectory}/offer-contact-${viewport.name}.png` });
  }

  await page.getByRole("button", { name: "Request My Options Review" }).click();
  if (!(await page.locator("#name-error").isVisible())) {
    record(viewport.name, "validation", "Contact step did not expose field errors.");
  }
  if (
    !(await page.locator("#phone-error").isVisible()) ||
    (await page.locator("#phone-error").textContent()) !== "Phone number is required."
  ) {
    record(viewport.name, "validation", "Missing phone did not expose the required error.");
  }
  await page.locator("#name").fill("Jane Seller");
  await page.locator("#phone").fill("404-555-0100");
  await checkFocusedControlClearance(
    page,
    viewport,
    page.getByRole("button", { name: "Request My Options Review" }),
    "offer-submit",
  );
  await page.waitForTimeout(20);
  await page.getByRole("button", { name: "Request My Options Review" }).click();
  const recoverableError = page.getByText("Stonegate could not save the request yet. Please try again.");
  await recoverableError.waitFor();
  if ((await page.locator("#name").inputValue()) !== "Jane Seller") {
    record(viewport.name, "submission-recovery", "A failed submission did not preserve the seller's answers.");
  }
  if (state.submissions.at(-1)?.sms_consent !== false) {
    record(viewport.name, "sms-consent-payload", "An unchecked SMS box did not submit false.");
  }
  const failedMetaEventId = state.submissions.at(-1)?.meta_browser_event?.event_id;
  if (
    failedMetaEventId !==
    `stonegate-contact-${state.submissions.at(-1)?.intake_attempt_id}`
  ) {
    record(
      viewport.name,
      "meta-contact-identity",
      "The failed submission did not use its deterministic Contact event ID.",
    );
  }

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("#name").waitFor({ timeout: 8_000 });
  if (
    (await page.locator("#name").inputValue()) !== "Jane Seller" ||
    (await page.locator("#phone").inputValue()) !== "404-555-0100"
  ) {
    record(
      viewport.name,
      "submission-recovery",
      "A reload after failed submission did not restore the seller's draft.",
    );
  }
  await page.locator("#sms_consent").check();
  await page.waitForTimeout(20);
  const storedDraft = await page.evaluate(() => JSON.parse(sessionStorage.getItem("stonegate_cash_offer_draft_v1") ?? "{}"));
  if ("sms_consent" in (storedDraft.values ?? {}) || "consent_to_contact" in (storedDraft.values ?? {})) {
    record(viewport.name, "consent-persistence", "Consent evidence was persisted in the browser draft.");
  }
  await page.getByRole("button", { name: "Request My Options Review" }).click();
  const confirmationHeading = page.getByText("Thanks. Stonegate has your property request.");
  try {
    await confirmationHeading.waitFor({ timeout: 8_000 });
  } catch {
    record(viewport.name, "submission", {
      submissions: state.submissions.length,
      addressCaptures: state.addressCaptures.length,
      visibleError: await page.locator('[role="status"]').last().textContent().catch(() => null),
      visibleFieldErrors: await page.locator('[id$="-error"]').allTextContents(),
    });
    if (screenshotDirectory) {
      await page.screenshot({ fullPage: true, path: `${screenshotDirectory}/offer-submit-error-${viewport.name}.png` });
    }
    await context.close();
    return;
  }
  const confirmationEmail = page.getByRole("link", { name: "Email Stonegate" });
  if (
    !(await confirmationEmail.getAttribute("href"))?.startsWith(
      "mailto:offers@stonegatehb.com",
    )
  ) {
    record(viewport.name, "contact-destination", "Confirmation email destination is incorrect.");
  }

  if (state.submissions.length !== 2) record(viewport.name, "submission-count", state.submissions.length);
  const failedMetaEvent = state.submissions.at(-2)?.meta_browser_event;
  const retriedMetaEvent = state.submissions.at(-1)?.meta_browser_event;
  if (
    !failedMetaEvent?.event_id ||
    failedMetaEvent.event_id !== retriedMetaEvent?.event_id
  ) {
    record(
      viewport.name,
      "meta-contact-retry",
      "A retried seller submission did not preserve its original Meta event ID.",
    );
  }
  const payload = state.submissions.at(-1);
  if (
    payload?.meta_browser_event?.event_id !==
      `stonegate-contact-${payload?.intake_attempt_id}` ||
    payload?.meta_browser_event?.event_id === initialAddressCapture?.meta_browser_event?.event_id
  ) {
    record(
      viewport.name,
      "meta-contact-identity",
      "Step 2 did not use a distinct deterministic Contact event ID.",
    );
  }
  if (
    !payload?.intake_attempt_id ||
    payload.intake_attempt_id !== initialAddressCapture?.intake_attempt_id ||
    state.addressCaptures.some(
      (capture) => capture.intake_attempt_id !== payload.intake_attempt_id,
    )
  ) {
    record(viewport.name, "address-capture-identity", {
      finalAttemptId: payload?.intake_attempt_id ?? null,
      captureAttemptIds: state.addressCaptures.map((capture) => capture.intake_attempt_id),
    });
  }
  const draftAfterSuccess = await page.evaluate(() =>
    sessionStorage.getItem("stonegate_cash_offer_draft_v1"),
  );
  if (draftAfterSuccess !== null) {
    record(viewport.name, "address-capture-identity", "Successful intake retained its draft ID.");
  }
  for (const [key, expected] of Object.entries({
    property_state: "GA",
    property_type: null,
    property_condition: null,
    occupancy_status: null,
    reason_for_selling: null,
    desired_timeline: null,
    asking_price: null,
    mortgage_balance: null,
    preferred_contact_method: "phone",
    consent_to_contact: true,
    consent_wording_version: "seller-contact-web-v3",
    sms_consent: true,
    sms_consent_wording_version: "seller-sms-web-v3",
  })) {
    if (payload?.[key] !== expected) record(viewport.name, "payload", { key, expected, actual: payload?.[key] });
  }
  if (!payload?.conversion_session_id) record(viewport.name, "session-link", "Missing conversion_session_id.");
  if (
    payload?.experiment_key !== "audit_homepage_cta" ||
    !["control", "treatment"].includes(payload?.experiment_variant)
  ) {
    record(viewport.name, "experiment-link", {
      experimentKey: payload?.experiment_key,
      variant: payload?.experiment_variant,
    });
  }
  const expectedDevice =
    viewport.width <= 720 ? "mobile" : viewport.width <= 1024 ? "tablet" : "desktop";
  if (payload?.device_category !== expectedDevice) {
    record(viewport.name, "device-category", {
      expected: expectedDevice,
      actual: payload?.device_category,
    });
  }

  await page.getByRole("button", { name: "Add property details" }).click();
  const enrichmentTimeline = page.locator("#desired_timeline");
  if (
    (await enrichmentTimeline.count()) !== 1 ||
    (await enrichmentTimeline.getAttribute("required")) !== null
  ) {
    record(
      viewport.name,
      "optional-enrichment",
      "The seller timeline was not presented as one optional post-submit field.",
    );
  }
  await enrichmentTimeline.selectOption("within_30_days");
  await page.locator("#property_type").selectOption("single_family");
  await page.locator("#property_condition").selectOption("major_repairs");
  await page.locator("#occupancy_status").selectOption("vacant");
  await page.locator("#reason_for_selling").selectOption("repairs_or_condition");
  await page.locator("#asking_price").fill("200,000");
  await page.locator("#mortgage_balance").fill("90,000");
  await page.locator("#comments").fill("Older roof and kitchen updates are likely.");
  await checkPage(page, viewport.name, "optional-enrichment");
  if (screenshotDirectory) {
    await page.screenshot({
      fullPage: true,
      path: `${screenshotDirectory}/offer-enrichment-${viewport.name}.png`,
    });
  }
  await page.getByRole("button", { name: "Save property details" }).click();
  await page.getByText("The additional property details were added", { exact: false }).waitFor();
  if (state.enrichments.length !== 1) {
    record(viewport.name, "enrichment-count", state.enrichments.length);
  }
  const enrichment = state.enrichments.at(-1);
  for (const [key, expected] of Object.entries({
    property_type: "single_family",
    property_condition: "major_repairs",
    occupancy_status: "vacant",
    reason_for_selling: "repairs_or_condition",
    desired_timeline: "within_30_days",
    asking_price: "200,000",
    mortgage_balance: "90,000",
  })) {
    if (enrichment?.[key] !== expected) {
      record(viewport.name, "enrichment-payload", { key, expected, actual: enrichment?.[key] });
    }
  }
  if (!enrichment?.enrichment_token || !enrichment?.conversion_session_id) {
    record(viewport.name, "enrichment-link", "Enrichment was not securely linked to the request.");
  }

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByText("Thanks. Stonegate has your property request.").waitFor({ timeout: 8_000 });
  await page.getByRole("button", { name: /Submit another property/ }).waitFor({ timeout: 8_000 });
  if (state.submissions.length !== 2) record(viewport.name, "durable-confirmation", state.submissions.length);
  await checkPage(page, viewport.name, "confirmation");
  if (screenshotDirectory) {
    await page.screenshot({ fullPage: true, path: `${screenshotDirectory}/offer-confirmation-${viewport.name}.png` });
  }
  await page.getByRole("button", { name: /Submit another property/ }).click();
  if (!(await page.getByText("What’s the property address?").isVisible())) {
    record(viewport.name, "reset", "New property reset did not return to step one.");
  }

  for (const error of browserErrors) record(viewport.name, "browser-error", error);
  if (!state.events.some((event) => event.event_type === "form_step_complete")) {
    record(viewport.name, "measurement", "Step completion event was not emitted.");
  }
  if (!state.events.some((event) => event.event_type === "form_start")) {
    record(viewport.name, "measurement", "Form-start measurement was not emitted.");
  }
  if (
    !state.events.some(
      (event) =>
        event.event_type === "offer_start" &&
        event.metadata?.entry_point === "homepage_hero",
    )
  ) {
    record(viewport.name, "measurement", "The upstream offer-start measurement was not emitted.");
  }
  if (!state.events.some((event) => event.event_type === "form_validation_error")) {
    record(viewport.name, "measurement", "Validation event was not emitted.");
  }
  const attributedEvents = state.events.filter(
    (event) => event.experiment_key === "audit_homepage_cta",
  );
  if (!attributedEvents.length) {
    record(viewport.name, "measurement", "Experiment assignment was not emitted.");
  } else if (
    new Set(attributedEvents.map((event) => event.experiment_variant)).size !== 1
  ) {
    record(viewport.name, "measurement", "Experiment assignment changed within one journey.");
  }
  await auditServiceAreaPage(page, viewport);
  await auditContactPage(page, viewport);
  await auditAboutPage(page, viewport);
  await page.goto(`${baseUrl}/terms`, { waitUntil: "load" });
  await checkMobileActionBar(page, viewport, "/get-a-cash-offer", "terms");
  await checkFocusedControlClearance(
    page,
    viewport,
    page.locator("footer").getByText(/All rights reserved/),
    "terms-footer",
  );
  await context.close();
}

const browser = await chromium.launch({
  channel: executablePath ? undefined : "chrome",
  executablePath,
  headless: true,
});

try {
  await auditJourney(browser, { name: "desktop", width: 1440, height: 1000 });
  await auditJourney(browser, { name: "tablet", width: 820, height: 1180 });
  await auditJourney(browser, { name: "mobile", width: 390, height: 844 });
} finally {
  await browser.close();
}

if (findings.length) {
  console.error(JSON.stringify({ findings }, null, 2));
  process.exitCode = 1;
} else {
  console.log(
    "Public audit passed: discovery, accessibility, team identity, and desktop/tablet/mobile offer journeys.",
  );
}
