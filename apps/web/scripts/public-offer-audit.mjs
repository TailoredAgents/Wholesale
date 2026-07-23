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

if (screenshotDirectory) mkdirSync(screenshotDirectory, { recursive: true });

function record(viewport, type, detail) {
  findings.push({ viewport, type, detail });
}

async function installApiStubs(page, state) {
  await page.route("**/api/v1/public/conversion-events", async (route) => {
    state.events.push(route.request().postDataJSON());
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: crypto.randomUUID(), event_type: "test" }) });
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
        consent_wording_version: "seller-contact-web-v2",
        message: "Thanks. Your information was received.",
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

async function auditJourney(browser, viewport) {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport });
  const page = await context.newPage();
  const state = { events: [], submissions: [], failNextSubmission: true };
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

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.getByLabel("Property address").first().fill("123 Main St");
  await page.getByRole("button", { name: "Start My Offer" }).first().click();
  await page.waitForURL(/\/get-a-cash-offer\?address=123\+Main\+St/);
  if ((await page.locator("#property_address").inputValue()) !== "123 Main St") {
    record(viewport.name, "address-prefill", "Homepage address was not preserved.");
  }

  await page.getByRole("button", { name: /Continue/ }).click();
  if (!(await page.locator("#property_city-error").isVisible())) {
    record(viewport.name, "validation", "Property step did not expose field errors.");
  }
  await page.locator("#property_city").fill("Atlanta");
  await page.locator("#property_postal_code").fill("30303");
  await page.locator("#property_type").selectOption("single_family");
  await page.getByRole("button", { name: /Continue/ }).click();
  await checkPage(page, viewport.name, "situation");
  if (screenshotDirectory) {
    await page.screenshot({ fullPage: true, path: `${screenshotDirectory}/offer-situation-${viewport.name}.png` });
  }

  await page.locator('input[name="property_condition"][value="major_repairs"]').check();
  await page.locator('input[name="occupancy_status"][value="vacant"]').check();
  await page.locator("#reason_for_selling").selectOption("repairs_or_condition");
  await page.locator("#desired_timeline").selectOption("within_30_days");
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.locator("#asking_price").fill("200,000");
  await page.locator("#mortgage_balance").fill("90,000");
  await page.locator("#comments").fill("Older roof and kitchen updates are likely.");
  await page.getByRole("button", { name: "Back" }).click();
  if (!(await page.locator('input[name="property_condition"][value="major_repairs"]').isChecked())) {
    record(viewport.name, "back-navigation", "Situation answer was not preserved.");
  }
  await page.getByRole("button", { name: /Continue/ }).click();
  if ((await page.locator("#asking_price").inputValue()) !== "200,000") {
    record(viewport.name, "answer-preservation", "Optional details were not preserved.");
  }
  await page.getByRole("button", { name: /Continue/ }).click();
  await checkPage(page, viewport.name, "contact");
  if (screenshotDirectory) {
    await page.screenshot({ fullPage: true, path: `${screenshotDirectory}/offer-contact-${viewport.name}.png` });
  }

  await page.getByRole("button", { name: "Request My Cash Offer" }).click();
  if (!(await page.locator("#name-error").isVisible())) {
    record(viewport.name, "validation", "Contact step did not expose field errors.");
  }
  await page.locator("#name").fill("Jane Seller");
  await page.locator("#phone").fill("404-555-0100");
  await page.locator('label:has(input[name="preferred_contact_method"][value="sms"])').click();
  await page.locator("#consent_to_contact").check();
  await page.getByRole("button", { name: "Request My Cash Offer" }).click();
  if (!(await page.locator("#sms_consent-error").isVisible())) {
    record(viewport.name, "sms-consent", "Text preference did not require separate SMS consent.");
  }
  await page.locator("#sms_consent").check();
  await page.waitForTimeout(20);
  const storedDraft = await page.evaluate(() => JSON.parse(sessionStorage.getItem("stonegate_cash_offer_draft_v1") ?? "{}"));
  if (storedDraft.values?.sms_consent || storedDraft.values?.consent_to_contact) {
    record(viewport.name, "consent-persistence", "Consent checkboxes were persisted in the draft.");
  }
  await page.getByRole("button", { name: "Request My Cash Offer" }).click();
  const recoverableError = page.getByText("Stonegate could not save the request yet. Please try again.");
  await recoverableError.waitFor();
  if ((await page.locator("#name").inputValue()) !== "Jane Seller") {
    record(viewport.name, "submission-recovery", "A failed submission did not preserve the seller's answers.");
  }
  await page.getByRole("button", { name: "Request My Cash Offer" }).click();
  const confirmationHeading = page.getByText("Thanks. Stonegate has the property request.");
  try {
    await confirmationHeading.waitFor({ timeout: 8_000 });
  } catch {
    record(viewport.name, "submission", {
      submissions: state.submissions.length,
      visibleError: await page.locator('[role="status"]').last().textContent().catch(() => null),
      visibleFieldErrors: await page.locator('[id$="-error"]').allTextContents(),
    });
    if (screenshotDirectory) {
      await page.screenshot({ fullPage: true, path: `${screenshotDirectory}/offer-submit-error-${viewport.name}.png` });
    }
    await context.close();
    return;
  }

  if (state.submissions.length !== 2) record(viewport.name, "submission-count", state.submissions.length);
  const payload = state.submissions.at(-1);
  for (const [key, expected] of Object.entries({
    property_type: "single_family",
    property_condition: "major_repairs",
    occupancy_status: "vacant",
    reason_for_selling: "repairs_or_condition",
    desired_timeline: "within_30_days",
    asking_price: "200,000",
    mortgage_balance: "90,000",
    preferred_contact_method: "sms",
    consent_to_contact: true,
    sms_consent: true,
  })) {
    if (payload?.[key] !== expected) record(viewport.name, "payload", { key, expected, actual: payload?.[key] });
  }
  if (!payload?.conversion_session_id) record(viewport.name, "session-link", "Missing conversion_session_id.");

  await page.reload({ waitUntil: "networkidle" });
  await page.getByText("Thanks. Stonegate has the property request.").waitFor({ timeout: 8_000 });
  if (state.submissions.length !== 2) record(viewport.name, "durable-confirmation", state.submissions.length);
  await checkPage(page, viewport.name, "confirmation");
  if (screenshotDirectory) {
    await page.screenshot({ fullPage: true, path: `${screenshotDirectory}/offer-confirmation-${viewport.name}.png` });
  }
  await page.getByRole("button", { name: /Submit another property/ }).click();
  if (!(await page.getByText("Where is the property?").isVisible())) {
    record(viewport.name, "reset", "New property reset did not return to step one.");
  }

  for (const error of browserErrors) record(viewport.name, "browser-error", error);
  if (!state.events.some((event) => event.event_type === "form_step_complete")) {
    record(viewport.name, "measurement", "Step completion event was not emitted.");
  }
  if (!state.events.some((event) => event.event_type === "form_validation_error")) {
    record(viewport.name, "measurement", "Validation event was not emitted.");
  }
  await context.close();
}

const browser = await chromium.launch({
  channel: executablePath ? undefined : "chrome",
  executablePath,
  headless: true,
});

try {
  await auditJourney(browser, { name: "desktop", width: 1440, height: 1000 });
  await auditJourney(browser, { name: "mobile", width: 390, height: 844 });
} finally {
  await browser.close();
}

if (findings.length) {
  console.error(JSON.stringify({ findings }, null, 2));
  process.exitCode = 1;
} else {
  console.log("Public offer audit passed: desktop and mobile progressive journeys.");
}
