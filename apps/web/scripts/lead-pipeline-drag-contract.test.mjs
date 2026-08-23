import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const page = readFileSync(resolve(appRoot, "os/leads/page.tsx"), "utf8");
const workspace = readFileSync(resolve(appRoot, "os/leads/leads-workspace.tsx"), "utf8");
const styles = readFileSync(resolve(appRoot, "os/leads/leads-workspace.module.css"), "utf8");
const utilities = readFileSync(resolve(appRoot, "os/os-utils.ts"), "utf8");
const stageForm = readFileSync(resolve(appRoot, "leads/[leadId]/stage-update-form.tsx"), "utf8");

test("lead board stage movement is permission-gated and accessible", () => {
  assert.match(page, /canEditLead=\{canCreateLead\}/);
  assert.match(workspace, /canEditLead: boolean/);
  assert.match(workspace, /disabled: !canMoveLead \|\| isPending/);
  assert.match(workspace, /<article[\s\S]*styles\.boardCard/);
  assert.match(workspace, /className=\{styles\.dragHandle\}/);
  assert.match(workspace, /aria-label=\{`Move \$\{lead\.seller_name\} to another pipeline stage`\}/);
  assert.match(workspace, /onClick=\{\(event\) => \{[\s\S]*onSelect\(\)/);
  assert.match(workspace, /<label className=\{styles\.moveControl\}>/);
  assert.match(workspace, /Available on keyboard and mobile/);
  assert.match(workspace, /announcements: dragAnnouncements/);
  assert.match(workspace, /aria-live=\{stageNotice\.tone === "error" \? "assertive" : "polite"\}/);
});

test("mouse and delayed touch dragging expose every board destination", () => {
  assert.match(workspace, /useSensor\(MouseSensor, \{ activationConstraint: \{ distance: 6 \} \}\)/);
  assert.match(workspace, /useSensor\(TouchSensor, \{ activationConstraint: \{ delay: 250, tolerance: 8 \} \}\)/);
  assert.match(workspace, /<DndContext/);
  assert.match(workspace, /<DragOverlay>/);
  assert.match(workspace, /collisionDetection=\{pointerWithin\}/);
  assert.match(workspace, /pipelineStages\.map\(\(pipelineStage\) => \{/);
  assert.match(workspace, /if \(nextDisplay === "board"\) \{[\s\S]*setStage\("all"\)/);
  assert.match(workspace, /initialDisplay !== "board" \|\| initialStage === "all"/);
  assert.match(workspace, /currentUrl\.searchParams\.delete\("stage"\)/);
  assert.match(workspace, /disabled=\{display === "board"\}/);
  assert.doesNotMatch(workspace, /visibleStages\.map/);
});

test("stage changes are optimistic, conflict-aware, and reversible", () => {
  assert.match(workspace, /pendingLeadIdsRef\.current\.has\(leadId\)/);
  assert.match(workspace, /currentPipelineStage\?\.key === targetStage\.key/);
  assert.match(workspace, /expected_stage_key: previousStageKey/);
  assert.match(workspace, /Moved on Leads board from/);
  assert.match(workspace, /stage_key: targetStage\.dropStageKey/);
  assert.match(workspace, /stage_key: previousStageKey/);
  assert.match(workspace, /apiErrorMessage\(responseBody\?\.detail/);
  assert.match(workspace, /finally \{[\s\S]*router\.refresh\(\)/);
  assert.match(workspace, /pendingLeadIds\.has\(lead\.id\)/);
  assert.match(stageForm, /\["appointment_scheduling", "Appointment scheduling"\]/);
  assert.match(stageForm, /expected_stage_key: currentStage/);
});

test("canonical destination stages and controlled-workflow restrictions stay explicit", () => {
  for (const [key, dropStageKey] of [
    ["new", "new"],
    ["contacting", "attempting_contact"],
    ["contacted", "contacted"],
    ["qualifying", "qualification_in_progress"],
    ["qualified", "qualified"],
    ["appointment", "appointment_scheduling"],
    ["underwriting", "underwriting"],
    ["offer", "offer_pending_approval"],
    ["nurture", "long_term_follow_up"],
    ["under_contract", "under_contract"],
  ]) {
    const stagePattern = new RegExp(
      `key: "${key}"[\\s\\S]{0,150}dropStageKey: "${dropStageKey}"`,
    );
    assert.match(utilities, stagePattern);
  }
  assert.match(utilities, /pipelineStageMoveBlockReason\(lead, stage\) === null/);
  assert.match(utilities, /stage\.key === "offer"/);
  assert.match(utilities, /Offer stages move through the Valuation & Offer workflow/);
  assert.match(utilities, /stage\.key === "under_contract"/);
  assert.match(utilities, /Under-contract status requires the signed-contract workflow/);
  assert.match(utilities, /getPipelineStage\(lead\.stage_key\)\?\.key === "under_contract"/);
  assert.match(workspace, /const canMoveLead = canEditLead && getPipelineStage\(lead\.stage_key\)\?\.key !== "under_contract"/);
  assert.match(workspace, /disabled=\{!leadCanEnterPipelineStage\(selectedLead, pipelineStage\)\}/);
  assert.match(workspace, /title=\{pipelineStageMoveBlockReason\(selectedLead, pipelineStage\) \?\? undefined\}/);
  assert.match(workspace, /blockedReason=\{dropBlockedReason\}/);
  assert.match(workspace, /disabled=\{!canEditLead\}/);
  assert.doesNotMatch(workspace, /disabled=\{dropDisabled\}/);
  assert.match(workspace, /blockedReason \? styles\.blockedDropTarget : styles\.dropTarget/);
  assert.match(workspace, /Move blocked\. \$\{blockedReason\}/);
});

test("board styling distinguishes handles, pending cards, overlays, and drop targets", () => {
  for (const className of [
    "boardCard",
    "cardSelect",
    "dragHandle",
    "draggingCard",
    "dragOverlay",
    "dropTarget",
    "blockedDropTarget",
    "disabledDropTarget",
    "savingBadge",
    "moveControl",
    "stageSuccess",
    "stageError",
  ]) {
    assert.match(styles, new RegExp(`\\.${className}\\b`));
  }
  assert.match(styles, /\.dragHandle[\s\S]*touch-action: none/);
});
