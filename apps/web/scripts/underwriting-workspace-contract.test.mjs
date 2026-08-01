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
const versionComparison = readFileSync(
  resolve(webRoot, "src/app/leads/[leadId]/underwriting-version-comparison.tsx"),
  "utf8",
);
const qualityScorecards = readFileSync(
  resolve(webRoot, "src/app/os/settings/data-quality/underwriting-quality.tsx"),
  "utf8",
);
const marketAdjustment = readFileSync(
  resolve(webRoot, "src/app/leads/[leadId]/adjustment-shadow-panel.tsx"),
  "utf8",
);
const calibrationOutcome = readFileSync(
  resolve(webRoot, "src/app/leads/[leadId]/calibration-outcome-form.tsx"),
  "utf8",
);
const reportService = readFileSync(
  resolve(repositoryRoot, "apps/api/app/services/underwriting_reports.py"),
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

test("U3.9 compares immutable comp, repair, and adjustment evidence", () => {
  assert.match(versionComparison, /comp_snapshot/);
  assert.match(versionComparison, /repair_snapshot/);
  assert.match(versionComparison, /adjustment_snapshot/);
  assert.match(versionComparison, /Comparable set/);
  assert.match(versionComparison, /Repair scope/);
  assert.match(versionComparison, /Adjustment research/);
});

test("U3.9 keeps investor and owner-facing report boundaries explicit", () => {
  assert.match(reportService, /def adjustment_research_story/);
  assert.match(reportService, /LIVE VALUATION EVIDENCE/);
  assert.match(reportService, /def client_explainability_story/);
  assert.match(reportService, /internal acquisition calculations are intentionally excluded/i);
});

test("U3.9 exposes segmented calibration and operating-quality scorecards", () => {
  assert.match(qualityScorecards, /Underwriting evidence quality/);
  assert.match(qualityScorecards, /Evidence segment scorecards/);
  assert.match(qualityScorecards, /AI scope corrections/);
  assert.match(qualityScorecards, /Catalog repair error/);
  const phase = roadmap.slice(
    roadmap.indexOf("#### U3.9:"),
    roadmap.indexOf("#### U3.10:"),
  );
  assert.match(phase, /Status:\*\* Implemented/);
  assert.match(phase, /property type, adaptive search level/);
});

test("Stonegate Valuation is the single live user-facing method", () => {
  assert.match(marketValue, /Stonegate Valuation/);
  assert.match(marketValue, /market_adjustment/);
  assert.match(marketAdjustment, /Stonegate valuation adjustments/);
  assert.doesNotMatch(marketAdjustment, /V2\.2 still controls/);
  assert.doesNotMatch(marketValue, /Underwriting V2\.2/);
  assert.match(calibrationOutcome, /validation_scenarios/);
  const phase = roadmap.slice(roadmap.indexOf("#### U3.10:"));
  assert.match(phase, /Status:\*\* Superseded by owner decision/);
  assert.match(phase, /V3 is the single live method/);
  assert.match(phase, /V2\.2 remains\s+available only as a technical rollback/);
});
