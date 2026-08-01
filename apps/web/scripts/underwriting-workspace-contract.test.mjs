import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const repositoryRoot = resolve(webRoot, "../..");
const leadDetail = readFileSync(
  resolve(webRoot, "src/app/leads/[leadId]/lead-detail-view.tsx"),
  "utf8",
);
const marketValue = readFileSync(
  resolve(webRoot, "src/app/leads/[leadId]/market-value-preview.tsx"),
  "utf8",
);
const roadmap = readFileSync(
  resolve(repositoryRoot, "docs/UNDERWRITING_COMP_METHOD.md"),
  "utf8",
);

test("valuation workspace preserves the four progressive stages", () => {
  for (const label of ["Quick Comp", "Desk Review", "Walkthrough", "Offer Decision"]) {
    assert.match(leadDetail, new RegExp(`label: "${label}"`));
  }
  assert.match(leadDetail, /valuationStageState/);
  assert.match(leadDetail, /latestVersion = lead\.underwriting_versions\[0\]/);
  assert.match(leadDetail, /lead\.intelligence\.missing_fields\.slice\(0, 3\)/);
});

test("normal recalculation reuses evidence and provider refresh is explicit", () => {
  assert.match(marketValue, /onClick=\{\(\) => createAnalysis\(false\)\}/);
  assert.match(marketValue, /Recalculate valuation/);
  assert.match(marketValue, /onClick=\{\(\) => createAnalysis\(true\)\}/);
  assert.match(marketValue, /Refresh market data/);
});

test("decision summary connects existing downstream workspaces", () => {
  for (const label of ["Current decision", "Reports", "Offer approval", "Contract & signing"]) {
    assert.match(leadDetail, new RegExp(label.replace("&", "&")));
  }
  assert.match(leadDetail, /tab=contract/);
  assert.match(leadDetail, /appointmentHref/);
  assert.match(leadDetail, /seller_contract_ceiling_cents/);
});

test("U3.8 is documented as one implemented workflow", () => {
  const phase = roadmap.slice(
    roadmap.indexOf("#### U3.8:"),
    roadmap.indexOf("#### U3.9:"),
  );
  assert.match(phase, /Status:\*\* Implemented/);
  assert.match(phase, /no parallel valuation record was\s+introduced/i);
  assert.match(phase, /Refresh market\s+data/);
});
