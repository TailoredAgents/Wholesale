import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const workspace = readFileSync(
  resolve(webRoot, "src/app/os/lead-manager/lead-manager-workspace.tsx"),
  "utf8",
);
const component = readFileSync(
  resolve(webRoot, "src/app/os/lead-manager/acquisitions-performance-scorecard.tsx"),
  "utf8",
);
const styles = readFileSync(
  resolve(webRoot, "src/app/os/lead-manager/acquisitions-performance-scorecard.module.css"),
  "utf8",
);
const api = readFileSync(resolve(webRoot, "src/app/lib/api.ts"), "utf8");
const repositoryRoot = resolve(webRoot, "..", "..");
const governanceDoc = readFileSync(
  resolve(repositoryRoot, "docs/ACQUISITIONS_PERFORMANCE_SCORECARD.md"),
  "utf8",
);
const leadManagerManual = readFileSync(
  resolve(repositoryRoot, "docs/LEAD_MANAGER_USER_MANUAL.md"),
  "utf8",
);
const controlReference = readFileSync(
  resolve(repositoryRoot, "docs/UI_CONTROL_REFERENCE.md"),
  "utf8",
);

test("the existing Performance view lazily mounts the acquisitions scorecard", () => {
  assert.match(workspace, /view === "performance"/);
  assert.match(workspace, /<AcquisitionsPerformanceScorecard\s*\/>/);
  assert.doesNotMatch(workspace, /<th>Avg response<\/th>/);
});

test("30 and 90 day reports use one auth-inclusive, bounded, revocable request", () => {
  assert.match(component, /type PeriodDays = 30 \| 90/);
  assert.match(component, /period_days: String\(periodDays\)/);
  assert.match(component, /\/api\/v1\/lead-manager\/performance/);
  assert.match(component, /useAuth/);
  assert.match(component, /getToken/);
  assert.match(component, /X-Dev-User-Email/);
  assert.match(component, /AbortController/);
  assert.match(component, /REQUEST_TIMEOUT_MS = 12_000/);
  assert.match(component, /const timeoutTask = new Promise<never>/);
  assert.match(component, /Promise\.race\(\[requestTask, timeoutTask\]\)/);
  assert.match(component, /cache: "no-store"/);
  assert.match(component, /setData\(null\)/);
  assert.match(component, /prior confirmed snapshot remains visible/i);
  assert.match(component, /before a \$\{periodDays\}-day snapshot could be confirmed/);
  assert.match(component, /priorSnapshotVisible/);

  const timeoutStartsAt = component.indexOf("const timeoutTask");
  const tokenStartsAt = component.indexOf("await getToken()");
  assert.ok(timeoutStartsAt >= 0 && timeoutStartsAt < tokenStartsAt);
});

test("scorecards expose governed weights, coverage, reliability, and shadow status", () => {
  for (const label of [
    "Acquisitions performance",
    "Overall",
    "Evidence coverage",
    "Shadow score",
    "Evidence-backed strengths",
    "Coaching focus",
    "Raw scoring evidence",
    "Methodology and weights",
  ]) {
    assert.match(component, new RegExp(label));
  }
  assert.match(component, /scorecard\.reliability_status/);
  assert.match(component, /dimension\.weight_basis_points/);
  assert.match(component, /dimension\.sample_size/);
  assert.match(component, /dimension\.minimum_sample_size/);
  assert.match(component, /confirmedData\.warnings/);
  assert.match(component, /scorecard\.warnings/);
  assert.match(component, /confirmedData\.policy_version/);
  assert.match(component, /<details className=\{styles\.methodology\} open>/);
});

test("missing and low-sample evidence is disclosed rather than fabricated", () => {
  assert.match(api, /overall_score: number \| null/);
  assert.match(api, /score: number \| null/);
  assert.match(api, /numerator: number \| null/);
  assert.match(api, /denominator: number \| null/);
  assert.match(component, /value === null \? "Unavailable"/);
  assert.match(component, /Missing evidence stays unavailable instead of becoming a zero/);
  assert.match(component, /dimension\.status === "ready" \? dimension\.score : null/);
  assert.match(component, /dimension\.status === "building"/);
  assert.match(component, /return "Building"/);
  assert.match(component, /Numeric score withheld until the minimum sample is reached/);
  assert.match(component, /Building dimensions with low sample sizes withhold their numeric score/);
  assert.doesNotMatch(component, /dimension\.score \?\? 0/);
  assert.doesNotMatch(component, /scorecard\.overall_score \?\? 0/);
});

test("raw evidence preserves fractional values and labels dimension-specific operands", () => {
  assert.match(component, /maximumFractionDigits: 4/);
  assert.match(component, /timing points \/ \$\{denominator\} possible timing points/);
  assert.match(component, /total score points \/ \$\{denominator\} reviewed calls/);
  assert.match(component, /successful credited share \/ \$\{denominator\} matured credited share/);
  assert.doesNotMatch(component, /integerFormatter\.format\(dimension\.numerator\)/);
  assert.doesNotMatch(component, /integerFormatter\.format\(dimension\.denominator\)/);
});

test("the report remains accessible and responsive", () => {
  assert.match(component, /aria-label="Acquisitions performance scorecard"/);
  assert.match(component, /aria-busy=\{requestPending\}/);
  assert.match(component, /aria-label="Performance period"/);
  assert.match(component, /aria-pressed=\{periodDays === days\}/);
  assert.match(component, /attemptedPeriodDays/);
  assert.match(component, /role="progressbar"/);
  assert.match(component, /scope="col"/);
  assert.match(component, /scope="row"/);
  assert.match(component, /role="region"/);
  assert.match(component, /aria-labelledby="acquisitions-raw-evidence-heading"/);
  assert.match(component, /<caption className=\{styles\.srOnly\}>/);
  assert.match(component, /tabIndex=\{0\}/);
  assert.match(component, /aria-live="polite"/);
  assert.match(component, /Snapshot generated/);
  assert.match(component, /performance snapshot refreshed/);
  assert.match(styles, /min-height: 44px/);
  assert.match(styles, /\.srOnly/);
  assert.match(styles, /\.tableWrap:focus-visible/);
  assert.match(styles, /@media \(max-width: 700px\)/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("shadow scores are explicitly coaching-only", () => {
  assert.match(component, /Shadow mode is coaching-only/);
  assert.match(component, /does not change lead assignment, pay, employment decisions, or automation/);
  assert.match(component, /Conversation quality is based only on recorded, reviewable call evidence/);
});

test("manager documentation matches scorecard access, controls, and Building policy", () => {
  assert.match(governanceDoc, /Manage acquisition operations/);
  assert.match(governanceDoc, /numeric\s+score and bar are withheld/);
  assert.match(governanceDoc, /generation timestamp/);
  assert.match(leadManagerManual, /Performance.*, for authorized managers only/);
  assert.match(leadManagerManual, /## Manager Performance Scorecard/);
  assert.match(leadManagerManual, /trailing 30- or 90-day evidence window/);
  assert.doesNotMatch(leadManagerManual, /## Your Performance Scorecard/);
  assert.doesNotMatch(leadManagerManual, /Average acceptance time/);
  assert.match(controlReference, /Manager only; read-only shadow coaching view/);
  assert.match(controlReference, /Raw scoring evidence/);
  assert.match(controlReference, /Building dimensions expose raw inputs but withhold the numeric score and bar/);
});
