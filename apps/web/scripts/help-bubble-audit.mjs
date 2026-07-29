import { existsSync } from "node:fs";

import { chromium } from "playwright-core";

const baseUrl = process.env.HELP_AUDIT_BASE_URL ?? "http://localhost:3000";
const screenshotDirectory = process.env.HELP_AUDIT_SCREENSHOT_DIR;
const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const executablePath = process.env.CHROME_EXECUTABLE_PATH ??
  (existsSync(macChrome) ? macChrome : undefined);
const viewports = [
  { name: "mobile", width: 390, height: 844 },
  { name: "desktop", width: 1440, height: 900 },
];
const results = [];
const browser = await chromium.launch({ headless: true, executablePath });

try {
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport });
    await page.goto(`${baseUrl}/os`, { timeout: 30_000, waitUntil: "networkidle" });
    await page.evaluate(() => {
      const clerkDevelopmentOverlay = document.querySelector("#clerk-components");
      if (clerkDevelopmentOverlay instanceof HTMLElement) {
        clerkDevelopmentOverlay.style.display = "none";
      }
    });
    const bubble = page.getByRole("button", { name: "Open Stonegate Help" });
    await bubble.waitFor({ state: "visible" });
    const bubbleBox = await bubble.boundingBox();
    await bubble.click({ force: true });
    const panel = page.getByRole("dialog", { name: "Stonegate Help" });
    await panel.waitFor({ state: "visible" });
    const panelBox = await panel.boundingBox();
    const pageMetrics = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    const fitsViewport = Boolean(
      bubbleBox &&
      panelBox &&
      panelBox.x >= 0 &&
      panelBox.y >= 0 &&
      panelBox.x + panelBox.width <= viewport.width &&
      panelBox.y + panelBox.height <= viewport.height &&
      pageMetrics.scrollWidth === pageMetrics.clientWidth
    );
    if (screenshotDirectory) {
      await page.screenshot({
        path: `${screenshotDirectory}/stonegate-help-${viewport.name}.png`,
        fullPage: true,
      });
    }
    results.push({ viewport, bubbleBox, panelBox, pageMetrics, fitsViewport });
    await page.close();
  }
} finally {
  await browser.close();
}

console.log(JSON.stringify(results, null, 2));
if (results.some((result) => !result.fitsViewport)) process.exitCode = 1;
