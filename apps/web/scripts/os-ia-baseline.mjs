import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

import { currentRouteInventory, evidenceContract } from "./os-ia-contract.mjs";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDirectory, "../../..");
const baseUrl = process.env.IA_BASELINE_BASE_URL ?? "http://127.0.0.1:3000";
const outputDirectory = resolve(
  repositoryRoot,
  process.env.IA_BASELINE_OUTPUT ?? evidenceContract.visualArtifactDirectory,
);
const requestedRoutes = process.env.IA_BASELINE_ROUTES
  ?.split(",")
  .map((route) => route.trim())
  .filter(Boolean);
const routes = currentRouteInventory
  .map((route) => route.baselinePath)
  .filter(Boolean)
  .filter((route) => !requestedRoutes || requestedRoutes.includes(route));
const viewports = [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 1024, height: 1366 },
  { name: "desktop", width: 1440, height: 900 },
];
const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const executablePath = process.env.CHROME_EXECUTABLE_PATH ??
  (existsSync(macChrome) ? macChrome : undefined);

mkdirSync(outputDirectory, { recursive: true });

function slug(route) {
  return route
    .replace(/^\//, "")
    .replace(/[?&=]/g, "-")
    .replaceAll("/", "-");
}

async function capture(page, viewport, route) {
  const startedAt = Date.now();
  const browserErrors = [];
  const recordBrowserError = (value) => {
    const message = String(value).slice(0, 2_000);
    if (!browserErrors.includes(message)) browserErrors.push(message);
  };
  page.on("pageerror", (error) => recordBrowserError(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") recordBrowserError(message.text());
  });
  let response;
  try {
    response = await page.goto(`${baseUrl}${route}`, {
      timeout: 30_000,
      waitUntil: "domcontentloaded",
    });
    await page.locator("h1").first().waitFor({ timeout: 15_000 });
    await page.waitForTimeout(500);
    const developmentOverlaysRemoved = await page.evaluate(() => {
      let removed = 0;
      document.querySelectorAll("nextjs-portal").forEach((element) => {
        element.remove();
        removed += 1;
      });
      document.querySelectorAll("body *").forEach((element) => {
        if (
          window.getComputedStyle(element).position === "fixed" &&
          element.textContent?.includes("Configure your application")
        ) {
          element.remove();
          removed += 1;
        }
      });
      return removed;
    });
    const screenshot = `${viewport.name}-${slug(route)}.png`;
    await page.screenshot({
      fullPage: false,
      path: resolve(outputDirectory, screenshot),
    });
    const evidence = await page.evaluate(() => ({
      bodyTextLength: document.body.innerText.trim().length,
      clientHeight: document.documentElement.clientHeight,
      clientWidth: document.documentElement.clientWidth,
      errorBoundary:
        document.documentElement.id === "__next_error__" ||
        document.body.innerText.includes("This page could not be loaded."),
      h1: document.querySelector("h1")?.textContent?.trim() ?? null,
      navigationLabels: Array.from(
        document.querySelectorAll("aside nav a"),
        (link) => link.textContent?.trim() ?? "",
      ).filter(Boolean),
      scrollHeight: document.documentElement.scrollHeight,
      scrollWidth: document.documentElement.scrollWidth,
      title: document.title,
    }));
    const finalUrl = page.url();
    const ignoredBrowserErrors = browserErrors.filter((error) =>
      error.includes("status of 401 (Unauthorized)"),
    );
    const fatalBrowserErrors = browserErrors.filter(
      (error) => !ignoredBrowserErrors.includes(error),
    );
    const failure =
      !response ||
      response.status() >= 400 ||
      finalUrl.includes("/sign-in") ||
      fatalBrowserErrors.length > 0 ||
      evidence.errorBoundary ||
      !evidence.h1 ||
      evidence.bodyTextLength < 100;
    return {
      ...evidence,
      browserErrors,
      fatalBrowserErrors,
      ignoredBrowserErrors,
      developmentOverlaysRemoved,
      durationMs: Date.now() - startedAt,
      failure,
      finalUrl,
      route,
      screenshot,
      status: response?.status() ?? null,
      viewport: viewport.name,
    };
  } catch (error) {
    return {
      durationMs: Date.now() - startedAt,
      error: error instanceof Error ? error.message : String(error),
      failure: true,
      finalUrl: page.url(),
      route,
      status: response?.status() ?? null,
      viewport: viewport.name,
    };
  }
}

const browser = await chromium.launch({
  channel: executablePath ? undefined : "chrome",
  executablePath,
  headless: true,
});
const captures = [];

try {
  for (const viewport of viewports) {
    const context = await browser.newContext({
      reducedMotion: "reduce",
      viewport: { width: viewport.width, height: viewport.height },
    });
    for (const route of routes) {
      const page = await context.newPage();
      captures.push(await capture(page, viewport, route));
      await page.close();
    }
    await context.close();
  }
} finally {
  await browser.close();
}

const manifest = {
  baseUrl,
  capturedAt: new Date().toISOString(),
  captures,
  contract: "apps/web/scripts/os-ia-contract.mjs",
  failures: captures.filter((capture) => capture.failure).length,
  outputDirectory,
  routeCount: routes.length,
  viewportCount: viewports.length,
};
writeFileSync(
  resolve(outputDirectory, "manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
);

console.log(
  `Captured ${captures.length} IA baselines across ${viewports.length} viewports in ${outputDirectory}.`,
);
if (manifest.failures) {
  console.error(`${manifest.failures} baseline captures failed. See manifest.json.`);
  process.exitCode = 1;
}
