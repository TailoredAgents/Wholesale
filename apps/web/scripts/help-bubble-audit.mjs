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
    const helpRequests = [];
    await page.route("**/api/v1/help**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      if (request.method() === "GET" && pathname.endsWith("/api/v1/help")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            title: "Stonegate Help",
            description: "Approved guidance",
            suggested_questions: ["How do I perform a comp?"],
            available_documents: ["USER_MANUAL.md", "UNDERWRITING_COMP_METHOD.md"],
            role_keys: ["owner"],
          }),
        });
        return;
      }
      if (request.method() === "POST" && pathname.endsWith("/api/v1/help/ask")) {
        const payload = request.postDataJSON();
        helpRequests.push(payload);
        const firstAnswer = [
          "Open the lead’s **Underwriting** tab.",
          "",
          "1. Confirm the property address.",
          "2. Open **Comp setup**.",
          "3. Select **Run complete analysis**. [1]",
          "",
          "Choose an estimate method:",
          "",
          "- **System**",
          "- **Total**",
          "- **Itemized**",
        ].join("\n");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            answer:
              helpRequests.length === 1
                ? firstAnswer
                : "If the address does not match, stop and correct the property record before continuing. [2]",
            citations: [
              {
                document: "USER_MANUAL.md",
                title: "Stonegate User Manual",
                heading_path: "Underwriting > Run A Complete Analysis",
                excerpt: "Verify the subject property before relying on the analysis.",
              },
              {
                document: "UNDERWRITING_COMP_METHOD.md",
                title: "Stonegate Underwriting Comp Method",
                heading_path: "Subject Match",
                excerpt: "A mismatched subject must be corrected before comp selection.",
              },
            ],
            used_ai: true,
            role_keys: ["owner"],
          }),
        });
        return;
      }
      await route.continue();
    });
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
    const composer = panel.getByLabel("Question");
    await composer.fill("How do I perform a comp?");
    await panel.getByRole("button", { name: "Ask Stonegate Help" }).click();
    await panel.getByText("Underwriting", { exact: true }).waitFor();
    const formattedAnswer = Boolean(
      (await panel.locator("ol li").count()) === 3 &&
      (await panel.locator("ul li").count()) === 3 &&
      (await panel.locator("strong").filter({ hasText: "Comp setup" }).count()) === 1 &&
      !(await panel.innerText()).includes("**")
    );
    await panel.getByRole("button", { name: "Open approved source 1" }).click();
    await panel.getByRole("button", { name: "Back to conversation" }).click();
    await composer.fill("What if the address does not match?");
    await panel.getByRole("button", { name: "Ask Stonegate Help" }).click();
    await panel
      .getByText("stop and correct the property record before continuing", { exact: false })
      .waitFor();
    const followUpRequest = helpRequests.at(-1);
    const conversationalContext = Boolean(
      helpRequests.length === 2 &&
      followUpRequest?.history?.length === 1 &&
      followUpRequest.history[0]?.question === "How do I perform a comp?" &&
      followUpRequest.history[0]?.answer?.includes("Run complete analysis")
    );
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
    results.push({
      viewport,
      bubbleBox,
      panelBox,
      pageMetrics,
      fitsViewport,
      formattedAnswer,
      conversationalContext,
    });
    await page.close();
  }
} finally {
  await browser.close();
}

console.log(JSON.stringify(results, null, 2));
if (
  results.some(
    (result) =>
      !result.fitsViewport || !result.formattedAnswer || !result.conversationalContext,
  )
) {
  process.exitCode = 1;
}
