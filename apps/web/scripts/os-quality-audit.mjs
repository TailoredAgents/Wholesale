import { existsSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";

import { chromium } from "playwright-core";

const baseUrl = process.env.OS_AUDIT_BASE_URL ?? "http://127.0.0.1:3000";
const require = createRequire(import.meta.url);
const axePath = require.resolve("axe-core/axe.min.js");
const leadId = process.env.OS_AUDIT_LEAD_ID;
const screenshotDirectory = process.env.OS_AUDIT_SCREENSHOT_DIR;
const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const executablePath = process.env.CHROME_EXECUTABLE_PATH ??
  (existsSync(macChrome) ? macChrome : undefined);

const routes = [
  "/os",
  "/os/inbox",
  "/os/tasks",
  "/os/calendar",
  "/os/operations",
  "/os/campaigns",
  "/os/prospecting",
  "/os/lead-manager",
  "/os/leads",
  "/os/pipeline",
  "/os/field-operations",
  "/os/underwriting",
  "/os/approvals",
  "/os/transactions",
  "/os/dispositions",
  "/os/buyers",
  "/os/finance?period=30",
  "/os/marketing?period=30",
  "/os/operating-model",
  "/os/ai",
  "/os/leads/archived",
];

if (leadId) routes.push(`/os/leads/${leadId}`);

const screenshotRoutes = new Set([
  "/os",
  "/os/inbox",
  "/os/leads",
  "/os/underwriting",
  "/os/dispositions",
  ...(leadId ? [`/os/leads/${leadId}`] : []),
]);
if (screenshotDirectory) mkdirSync(screenshotDirectory, { recursive: true });

const widths = [390, 768, 1280, 1440];
const findings = [];

function record(width, route, type, detail) {
  findings.push({ width, route, type, detail });
}

async function auditRoute(page, width, route) {
  const browserErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  let response;
  try {
    response = await page.goto(`${baseUrl}${route}`, {
      timeout: 20_000,
      waitUntil: "networkidle",
    });
  } catch (error) {
    record(width, route, "navigation", error instanceof Error ? error.message : String(error));
    return;
  }

  if (response?.status() !== 200) record(width, route, "status", response?.status() ?? 0);
  for (const error of browserErrors) record(width, route, "browser-error", error);

  if ([390, 1440].includes(width)) {
    await page.addScriptTag({ path: axePath });
    const violations = await page.evaluate(async () => {
      const result = await window.axe.run(document, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] },
      });
      return result.violations
        .filter((violation) => ["serious", "critical"].includes(violation.impact))
        .map((violation) => ({
          id: violation.id,
          impact: violation.impact,
          targets: violation.nodes.slice(0, 5).map((node) => node.target.join(" ")),
        }));
    });
    if (violations.length) record(width, route, "wcag", violations);
  }

  const result = await page.evaluate(() => {
    const visible = (element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    };
    const hasName = (element) => {
      if (
        element.getAttribute("aria-label") ||
        element.getAttribute("aria-labelledby") ||
        element.getAttribute("title")
      ) return true;
      if (["A", "BUTTON", "SUMMARY"].includes(element.tagName)) {
        return Boolean(element.textContent?.trim() || element.querySelector("img[alt]"));
      }
      if (element.closest("label")) return true;
      return Boolean(
        element.id && document.querySelector(`label[for="${CSS.escape(element.id)}"]`),
      );
    };
    const controls = Array.from(
      document.querySelectorAll(
        'button, a[href], input:not([type="hidden"]), select, textarea, summary',
      ),
    ).filter(visible);
    const ids = Array.from(document.querySelectorAll("[id]"), (element) => element.id);
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
    const longMotion = Array.from(document.querySelectorAll("*"))
      .filter(visible)
      .filter((element) => {
        const style = window.getComputedStyle(element);
        const durations = `${style.transitionDuration},${style.animationDuration}`
          .split(",")
          .map((value) => value.trim())
          .map((value) => value.endsWith("ms") ? Number.parseFloat(value) / 1000 : Number.parseFloat(value));
        return durations.some((duration) => Number.isFinite(duration) && duration > 0.02);
      })
      .slice(0, 5)
      .map((element) => element.tagName.toLowerCase());

    return {
      clientWidth: document.documentElement.clientWidth,
      duplicateIds,
      headings: Array.from(document.querySelectorAll("h1"), (heading) => heading.textContent?.trim()),
      imagesMissingAlt: Array.from(document.querySelectorAll("img:not([alt])")).filter(visible).length,
      longMotion,
      mainCount: document.querySelectorAll("main").length,
      scrollWidth: document.documentElement.scrollWidth,
      unnamedControls: controls
        .filter((control) => !hasName(control))
        .slice(0, 10)
        .map((control) => control.outerHTML.slice(0, 160)),
    };
  });

  if (result.scrollWidth > result.clientWidth) {
    record(width, route, "horizontal-overflow", result.scrollWidth - result.clientWidth);
  }
  if (result.headings.length !== 1) record(width, route, "h1-count", result.headings);
  if (result.mainCount !== 1) record(width, route, "main-count", result.mainCount);
  if (result.unnamedControls.length) record(width, route, "unnamed-controls", result.unnamedControls);
  if (result.duplicateIds.length) record(width, route, "duplicate-ids", result.duplicateIds);
  if (result.imagesMissingAlt) record(width, route, "missing-image-alt", result.imagesMissingAlt);
  if (result.longMotion.length) record(width, route, "reduced-motion", result.longMotion);
  if (screenshotDirectory && screenshotRoutes.has(route)) {
    const slug = route.replace(/^\//, "").replaceAll("/", "-");
    await page.screenshot({
      fullPage: true,
      path: `${screenshotDirectory}/${slug}-${width}.png`,
    });
  }
}

async function auditKeyboard(browser) {
  const context = await browser.newContext({
    reducedMotion: "reduce",
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  await page.goto(`${baseUrl}/os`, { waitUntil: "networkidle" });
  await page.keyboard.press("Tab");
  const firstFocus = await page.evaluate(() => ({
    href: document.activeElement?.getAttribute("href"),
    outline: window.getComputedStyle(document.activeElement).outlineStyle,
    text: document.activeElement?.textContent?.trim(),
  }));
  if (firstFocus.href !== "#main-content" || firstFocus.text !== "Skip to main content") {
    record(390, "/os", "skip-link", firstFocus);
  }
  if (firstFocus.outline === "none") record(390, "/os", "focus-indicator", firstFocus);
  await page.keyboard.press("Enter");
  const focusTarget = await page.evaluate(() => document.activeElement?.id);
  if (focusTarget !== "main-content") record(390, "/os", "skip-target", focusTarget);

  const menuButton = page.getByRole("button", { name: "Open navigation" });
  await menuButton.click();
  const navigationDialog = page.getByRole("dialog", { name: "Operating System" });
  if (!(await navigationDialog.isVisible())) record(390, "/os", "navigation-dialog", "not visible");
  await page.waitForFunction(() => Boolean(document.activeElement?.closest('[role="dialog"]')));
  const focusInside = await page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]')));
  if (!focusInside) record(390, "/os", "navigation-focus", "focus escaped drawer");
  await page.keyboard.press("Escape");
  const restoredName = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
  if (restoredName !== "Open navigation") record(390, "/os", "focus-restoration", restoredName);

  await page.goto(`${baseUrl}/os/buyers`, { waitUntil: "networkidle" });
  const addBuyer = page.getByRole("button", { name: "Add buyer" });
  if (await addBuyer.isVisible()) {
    await addBuyer.click();
    const buyerDialog = page.getByRole("dialog", { name: "Add qualified buyer" });
    if (!(await buyerDialog.isVisible())) record(390, "/os/buyers", "buyer-drawer", "not visible");
    await page.keyboard.press("Escape");
    if (await buyerDialog.isVisible()) record(390, "/os/buyers", "buyer-drawer", "Escape did not close");
    const restoredBuyerFocus = await page.evaluate(() => document.activeElement?.textContent?.trim());
    if (restoredBuyerFocus !== "Add buyer") {
      record(390, "/os/buyers", "buyer-focus-restoration", restoredBuyerFocus);
    }
  }

  const colors = await page.evaluate(() => {
    const theme = document.querySelector("main")?.closest("div");
    if (!theme) return null;
    const style = window.getComputedStyle(theme);
    const read = (name) => style.getPropertyValue(name).trim();
    return {
      brand: read("--sg-color-brand-strong"),
      danger: read("--sg-color-danger"),
      info: read("--sg-color-info"),
      muted: read("--sg-color-text-muted"),
      surface: read("--sg-color-surface"),
      text: read("--sg-color-text"),
      textSoft: read("--sg-color-text-soft"),
      warning: read("--sg-color-warning"),
    };
  });
  if (!colors) {
    record(390, "/os/buyers", "contrast-tokens", "theme variables unavailable");
  } else {
    const parseColor = (value) => {
      if (value.startsWith("#")) {
        const hex = value.slice(1);
        return [0, 2, 4].map((index) => Number.parseInt(hex.slice(index, index + 2), 16));
      }
      return (value.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
    };
    const luminance = (value) => {
      const channels = parseColor(value).map((channel) => channel / 255)
        .map((channel) => channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
      return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    };
    const contrast = (foreground, background) => {
      const first = luminance(foreground);
      const second = luminance(background);
      return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
    };
    for (const key of ["text", "textSoft", "muted", "brand", "warning", "info", "danger"]) {
      const ratio = contrast(colors[key], colors.surface);
      if (ratio < 4.5) record(390, "/os/buyers", "contrast-token", { key, ratio });
    }
  }
  await context.close();
}

const browser = await chromium.launch({
  channel: executablePath ? undefined : "chrome",
  executablePath,
  headless: true,
});

try {
  for (const width of widths) {
    const context = await browser.newContext({
      reducedMotion: "reduce",
      viewport: { width, height: 900 },
    });
    for (const route of routes) {
      const page = await context.newPage();
      await auditRoute(page, width, route);
      await page.close();
    }
    await context.close();
  }
  await auditKeyboard(browser);
} finally {
  await browser.close();
}

const checked = routes.length * widths.length;
if (findings.length) {
  console.error(JSON.stringify({ checked, findings }, null, 2));
  process.exitCode = 1;
} else {
  console.log(`OS quality audit passed: ${checked} route and viewport combinations.`);
}
