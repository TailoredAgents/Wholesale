import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const apiSource = readFileSync(resolve(webRoot, "src/app/lib/api.ts"), "utf8");
const campaignWorkspaceSource = readFileSync(
  resolve(webRoot, "src/app/os/campaigns/campaign-management-workspace.tsx"),
  "utf8",
);
const operationsWorkspaceSource = readFileSync(
  resolve(webRoot, "src/app/os/operations/operations-workspace.tsx"),
  "utf8",
);

test("campaign response contracts preserve House or Land classification", () => {
  assert.match(
    apiSource,
    /campaigns: Array<\{[\s\S]*?channel: string;\s+asset_class: "house" \| "land";/,
  );
});

for (const [name, source, extractor] of [
  ["campaign workspace", campaignWorkspaceSource, "value"],
  ["operations workspace", operationsWorkspaceSource, "formValue"],
]) {
  test(`${name} requires an explicit workflow and submits it`, () => {
    assert.match(
      source,
      /<select defaultValue="" name="asset_class" required>/,
    );
    assert.match(source, /<option disabled value="">Select House or Land<\/option>/);
    assert.match(source, /<option value="house">House<\/option>/);
    assert.match(source, /<option value="land">Land<\/option>/);
    assert.match(
      source,
      new RegExp(`asset_class: ${extractor}\\((?:formData|data), "asset_class"\\)`),
    );
  });
}

test("campaign managers can verify classification after creation", () => {
  assert.match(campaignWorkspaceSource, /labelize\(selectedCampaign\.asset_class\)/);
  assert.match(operationsWorkspaceSource, /labelize\(campaign\.asset_class\)/);
});
