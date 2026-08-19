import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const stateSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-call-evidence-state.ts"),
  "utf8",
);
const viewerSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-call-evidence.tsx"),
  "utf8",
);
const workspaceSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-workspace.tsx"),
  "utf8",
);
const playerSource = readFileSync(
  resolve(webRoot, "src/app/os/inbox/call-recording-player.tsx"),
  "utf8",
);
const cssSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting.module.css"),
  "utf8",
);

let stateModulePromise;
function importStateModule() {
  if (!stateModulePromise) {
    const javascript = ts.transpileModule(stateSource, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText;
    stateModulePromise = import(
      `data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`
    );
  }
  return stateModulePromise;
}

test("every evidence lifecycle state has a clear operator-facing presentation", async () => {
  const { evidenceStatusPresentation } = await importStateModule();
  const statuses = [
    "unavailable",
    "recording_ready",
    "processing",
    "ready",
    "failed",
    "exhausted",
  ];
  for (const status of statuses) {
    const presentation = evidenceStatusPresentation(status);
    assert.ok(presentation.label.length > 3, status);
    assert.ok(presentation.detail.length > 10, status);
    assert.ok(["neutral", "progress", "ready", "warning", "error"].includes(presentation.tone));
  }
  assert.match(evidenceStatusPresentation("processing").label, /processing/i);
  assert.match(evidenceStatusPresentation("exhausted").label, /retry/i);
});

test("quick facts retain actionable house and land intelligence without empty rows", async () => {
  const { buildEvidenceFacts } = await importStateModule();
  const facts = buildEvidenceFacts({
    summary: "Seller wants to move.",
    motivation: "Moving closer to family",
    timeline: "Within 30 days",
    property_condition: null,
    occupancy_status: "Vacant",
    asking_price: "$200,000",
    mortgage_balance: null,
    mortgage_or_title: null,
    repairs: ["Roof"],
    objections: [],
    commitments: ["Send photos"],
    next_action: "Call tomorrow",
    follow_up_at: null,
    appointment_details: null,
    confidence: 88,
    evidence: [],
    acreage: "5 acres",
  });
  assert.deepEqual(
    facts.map((fact) => fact.label),
    ["Motivation", "Timeline", "Occupancy", "Asking price", "Next action", "Acreage", "Repairs", "Commitments"],
  );
  assert.ok(facts.every((fact) => fact.value.trim().length > 0));
});

test("AI qualification suggestions visibly distinguish corroboration and conflict", async () => {
  const { suggestionPresentation, formatSuggestionValue, formatEvidenceTimestamp } =
    await importStateModule();
  const suggestion = {
    question_key: "timeline",
    state: "conflict",
    current_value: "Six months",
    suggested_value: "Thirty days",
    evidence: [],
  };
  assert.deepEqual(suggestionPresentation(suggestion), {
    label: "Conflict to review",
    tone: "error",
  });
  assert.equal(formatSuggestionValue(["one", "two"]), "one; two");
  assert.equal(formatEvidenceTimestamp(125.8), "2:05");
});

test("completed attempt history lazy-loads evidence only after expansion", () => {
  assert.match(workspaceSource, /dynamic\([\s\S]*prospecting-call-evidence/);
  assert.match(workspaceSource, /ssr: false/);
  assert.match(workspaceSource, /expanded \? \([\s\S]*<ProspectingCallEvidence/);
  assert.match(workspaceSource, /INITIAL_EVIDENCE_PRESENTATION/);
  assert.doesNotMatch(workspaceSource, /attempts\/\$\{attempt\.id\}\/evidence/);
  assert.match(viewerSource, /prospecting\/attempts\/\$\{attemptId\}\/evidence/);
});

test("the evidence viewer reuses production playback and quick-read behavior", () => {
  assert.match(viewerSource, /CallRecordingPlayer/);
  assert.match(viewerSource, /buildCallQuickRead/);
  assert.match(viewerSource, /playerRef\.current\?\.seekTo\(seconds, \{ play: true \}\)/);
  assert.match(viewerSource, /Full transcript/);
  assert.match(viewerSource, /speaker_segments/);
  assert.match(viewerSource, /Download transcript/);
  assert.match(playerSource, /canDownload\?: boolean/);
  assert.match(playerSource, /canDownload = true/);
});

test("server capabilities gate every privileged call-evidence control", () => {
  assert.match(viewerSource, /evidence\.capabilities\.can_play \? \(/);
  assert.match(viewerSource, /canDownload=\{evidence\.capabilities\.can_download_audio\}/);
  assert.match(viewerSource, /evidence\.capabilities\.can_delete \? \(/);
  assert.match(viewerSource, /evidence\.capabilities\.can_retry \? \(/);
  assert.match(viewerSource, /evidence\.capabilities\.can_download_transcript \? \(/);
});

test("audio deletion does not incorrectly hide a retained transcript download", () => {
  assert.match(viewerSource, /canDownload=\{evidence\.capabilities\.can_download_audio\}/);
  assert.match(
    viewerSource,
    /evidence\.capabilities\.can_download_transcript \? \([\s\S]*Download transcript/,
  );
  assert.match(viewerSource, /!evidence\.capabilities\.can_download_transcript/);
});

test("notes remain automatic and failed work has explicit recovery without approval UI", () => {
  assert.match(viewerSource, /AI notes are saved automatically\. No approval is required\./);
  assert.match(viewerSource, /Retry call intelligence/);
  assert.match(viewerSource, /will retry automatically/);
  assert.match(viewerSource, /voice\/transcripts\/\$\{transcript\.id\}\/retry/);
  assert.doesNotMatch(viewerSource, /Approve notes|Reject draft|\/review/);
});

test("mobile evidence controls meet touch targets and disclosures remain compact", () => {
  assert.match(cssSource, /@media \(max-width: 760px\)[\s\S]*\.callEvidence button[\s\S]*min-height: 44px/);
  assert.match(cssSource, /\.callEvidenceTranscriptText[\s\S]*max-height: 360px/);
  assert.match(cssSource, /prefers-reduced-motion: reduce/);
});
