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
const leadDetail = readFileSync(resolve(appRoot, "leads/[leadId]/lead-detail-view.tsx"), "utf8");
const executedContractImport = readFileSync(
  resolve(appRoot, "leads/[leadId]/executed-contract-import-form.tsx"),
  "utf8",
);
const offerStageAction = readFileSync(
  resolve(appRoot, "leads/[leadId]/offer-stage-action.tsx"),
  "utf8",
);
const dealsPage = readFileSync(resolve(appRoot, "os/deals/page.tsx"), "utf8");
const dealsWorkspace = readFileSync(resolve(appRoot, "os/deals/deals-workspace.tsx"), "utf8");
const pipelineWorkspace = readFileSync(resolve(appRoot, "os/pipeline/pipeline-workspace.tsx"), "utf8");

test("lead board stage movement is permission-gated and accessible", () => {
  assert.match(page, /canEditLead=\{canEditLead\}/);
  assert.match(page, /canRecordOutsideOffer=\{canRecordOutsideOffer\}/);
  assert.match(page, /canImportExecutedContract=\{canImportExecutedContract\}/);
  assert.match(workspace, /canEditLead: boolean/);
  assert.match(workspace, /canImportExecutedContract: boolean/);
  assert.match(workspace, /canRecordOutsideOffer: boolean/);
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
  for (const workflowControlledStage of [
    "offer_pending_approval",
    "offer_ready",
    "offer_presented",
    "negotiating",
    "under_contract",
  ]) {
    assert.doesNotMatch(
      stageForm,
      new RegExp(`\\["${workflowControlledStage}",\\s*"`),
    );
  }
  assert.match(stageForm, /Use Valuation &amp; Offer to advance the offer/);
  assert.match(stageForm, /Use Contract & Deal to manage the signed contract/);
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
  assert.match(workspace, /const canMoveLead =\s*\(canEditLead \|\| canImportExecutedContract \|\| canRecordOutsideOffer\)/);
  assert.match(workspace, /disabled=\{Boolean\(workspaceStageMoveBlockReason\(selectedLead, pipelineStage\)\)\}/);
  assert.match(workspace, /title=\{workspaceStageMoveBlockReason\(selectedLead, pipelineStage\) \?\? undefined\}/);
  assert.match(workspace, /blockedReason=\{dropBlockedReason\}/);
  assert.match(workspace, /disabled=\{!canEditLead && !canImportExecutedContract && !canRecordOutsideOffer\}/);
  assert.match(workspace, /return "Moving to this stage requires Lead editing access\."/);
  assert.doesNotMatch(workspace, /disabled=\{dropDisabled\}/);
  assert.match(workspace, /blockedReason \? styles\.blockedDropTarget : styles\.dropTarget/);
  assert.match(workspace, /Move blocked\. \$\{blockedReason\}/);
});

test("an authorized catch-up workflow records already-executed contracts without a fake stage move", () => {
  assert.match(leadDetail, /permissions\.includes\("contracts:record_executed"\)/);
  assert.match(leadDetail, /permissions\.includes\("contracts:modify"\)/);
  assert.match(leadDetail, /Record an already-signed contract/);
  assert.match(leadDetail, /<ExecutedContractImportForm/);
  assert.match(executedContractImport, /import-executed-contract/);
  assert.match(executedContractImport, /requestData\.set\("file", file, file\.name\)/);
  assert.match(executedContractImport, /requestData\.set\("confirm_fully_executed", "true"\)/);
  assert.match(executedContractImport, /body: requestData/);
  assert.match(executedContractImport, /onRecorded\?\.\(imported\)/);
  assert.doesNotMatch(executedContractImport, /import-executed-contract\?\$\{/);
  assert.doesNotMatch(executedContractImport, /"Content-Type": "application\/pdf"/);
  assert.match(executedContractImport, /attestation_reason/);
  assert.match(executedContractImport, /Record contract and open Dispositions/);
  assert.match(executedContractImport, /\/os\/dispositions\?case=/);
  assert.match(executedContractImport, /\/os\/transactions\?transaction=.*&tab=timeline/);
  assert.match(executedContractImport, /Check People &amp; Access/);
  assert.match(executedContractImport, /Check Finance Policy/);
  assert.match(executedContractImport, /disposition_handoff_status: "ready" \| "needs_setup"/);
  assert.match(executedContractImport, /disposition_handoff_blockers/);
  assert.match(executedContractImport, /visible to Dispositions as Needs setup/);
  assert.match(executedContractImport, /remaining closing terms are optional/);
  assert.match(executedContractImport, /creates follow-up work/);
  assert.match(executedContractImport, /name="closing_date" type="date"/);
  assert.match(executedContractImport, /Array\.isArray\(payload\.detail\)/);
  assert.match(executedContractImport, /type="number"/);
  assert.match(stageForm, /canImportExecutedContract: boolean/);
  assert.match(stageForm, /canEditLead: boolean/);
  assert.match(stageForm, /canImportExecutedContract && !hasExecutedTransaction/);
  assert.doesNotMatch(stageForm, /assetClass === "house"/);
  assert.match(stageForm, /value="under_contract">Under Contract - record signed agreement/);
  assert.match(stageForm, /requestedStage === "under_contract"/);
  assert.match(stageForm, /<ExecutedContractImportForm/);
  assert.match(stageForm, /onCancel={cancelExecutedContractImport}/);
  assert.match(stageForm, /selectRef\.current\?\.focus\(\)/);
  assert.match(executedContractImport, /Cancel and keep current stage/);
});

test("board and Move to stage open the governed signed-contract form for Under Contract", () => {
  assert.match(page, /permissions\.includes\("contracts:record_executed"\)/);
  assert.match(page, /permissions\.includes\("contracts:modify"\)/);
  assert.match(page, /canImportExecutedContract=\{canImportExecutedContract\}/);
  assert.match(workspace, /ExecutedContractImportForm,[\s\S]*ExecutedContractImportResponse/);
  assert.match(workspace, /canImportExecutedContract: boolean/);
  assert.doesNotMatch(workspace, /targetStage\.key === "under_contract"[\s\S]{0,300}lead\.asset_class !== "house"/);
  assert.match(workspace, /requires executed-contract recording access/);
  assert.match(workspace, /if \(!lead \|\| pendingLeadIdsRef\.current\.has\(leadId\)\) return/);
  assert.match(workspace, /canEditLead \|\| canImportExecutedContract \|\| canRecordOutsideOffer/);
  assert.match(workspace, /if \(targetStage\.key === "under_contract"\) \{[\s\S]*setContractImportLeadId\(leadId\)[\s\S]*return;/);
  assert.match(workspace, /<ExecutedContractImportDialog/);
  assert.match(workspace, /<ExecutedContractImportForm[\s\S]*leadId=\{lead\.id\}[\s\S]*onRecorded=\{onRecorded\}/);
  assert.match(workspace, /<dialog[\s\S]*aria-labelledby="executed-contract-import-title"/);
  assert.match(workspace, /onClose=\{onClose\}/);
  assert.match(workspace, /Cancel recording the signed contract/);
  assert.match(workspace, /Under Contract opens the signed-contract form/);
  assert.match(workspace, /lead\.id === result\.lead_id \? \{ \.\.\.lead, stage_key: result\.lead_stage \}/);

  const governedBranch = workspace.indexOf('if (targetStage.key === "under_contract")');
  const directStagePatch = workspace.indexOf('/stage`, {', governedBranch);
  assert.ok(governedBranch >= 0 && directStagePatch > governedBranch);
  assert.match(
    workspace.slice(governedBranch, directStagePatch),
    /setContractImportLeadId\(leadId\)[\s\S]*return;/,
  );
});

test("Offer opens an action choice and outside evidence reaches governed offer stages", () => {
  assert.match(page, /const canRecordOutsideOffer = Boolean\(profile\?\.permissions\.includes\("leads:edit"\)\)/);
  assert.match(page, /canRecordOutsideOffer=\{canRecordOutsideOffer\}/);
  assert.match(stageForm, /value="offer_action">Offer - choose workflow/);
  assert.match(stageForm, /requestedStage === "offer_action"/);
  assert.match(stageForm, /<OfferStageAction/);
  assert.match(workspace, /targetStage\.key === "offer"/);
  assert.match(workspace, /setOfferActionLeadId\(leadId\)/);
  assert.match(workspace, /<OfferStageActionDialog/);
  assert.match(workspace, /Opening the offer choices/);
  assert.match(offerStageAction, /\/outside-offers/);
  assert.match(offerStageAction, /expected_stage_key: expectedStageKey/);
  assert.match(offerStageAction, /Review Land valuation/);
  assert.match(offerStageAction, /Use Record an outside offer for an offer already presented/);
  assert.match(offerStageAction, /Stonegate Valuation & Offer/);
  assert.match(offerStageAction, /Record an outside offer/);
  assert.match(offerStageAction, /result\.stage_key === "negotiating"/);
  assert.match(offerStageAction, /Verbally accepted/);
  assert.match(offerStageAction, /remains Offer Presented until a fully signed purchase agreement/);
  assert.match(offerStageAction, /assetClass === "land"[\s\S]*\? `\/os\/leads\/\$\{leadId\}\?tab=valuation`/);
  assert.doesNotMatch(offerStageAction, /House leads are supported in this release/);
  assert.doesNotMatch(offerStageAction, /assetClass === "house" \? \(/);

  const offerBranch = workspace.indexOf('if (targetStage.key === "offer")');
  const directStagePatch = workspace.indexOf('/stage`, {', offerBranch);
  assert.ok(offerBranch >= 0 && directStagePatch > offerBranch);
  assert.match(
    workspace.slice(offerBranch, directStagePatch),
    /setOfferActionLeadId\(leadId\)[\s\S]*return;/,
  );
});

test("Land lead detail exposes factual contract catch-up without residential creation controls", () => {
  assert.doesNotMatch(leadDetail, /meta="Intentionally blocked"/);
  assert.match(leadDetail, /lead\.transactions\.map\(\(transaction\) => \(/);
  assert.match(leadDetail, /Open transaction coordination/);
  assert.match(leadDetail, /lead\.asset_class === "house" \? \([\s\S]*<TransactionForm leadId=\{lead\.id\}/);
  assert.match(leadDetail, /Stonegate-generated Land agreements and e-signing remain unavailable/);
  assert.match(leadDetail, /canImportExecutedContract && !lead\.transactions\.some[\s\S]*Record an already-signed contract/);
  assert.match(leadDetail, /Open contract evidence and closing files/);
  assert.doesNotMatch(leadDetail, /Legacy residential \$\{labelize\(transaction\.contract_type\)\}/);
  assert.doesNotMatch(leadDetail, /lead\.asset_class === "land" \? "Incompatible with Land"/);
});

test("Transaction Coordinators receive the same executed-contract catch-up action in Deals", () => {
  assert.match(dealsPage, /permissions\.includes\("contracts:record_executed"\)/);
  assert.match(dealsPage, /canRecordExecutedContract=/);
  assert.match(dealsWorkspace, /canRecordExecutedContract: boolean/);
  assert.match(dealsWorkspace, /Record an already-signed contract/);
  assert.match(dealsWorkspace, /<ExecutedContractImportForm leadId=\{selected\.lead_id\}/);
  assert.match(dealsWorkspace, /without[\s\S]*general Leads access/);
});

test("negotiation next actions link to the real valuation ledger", () => {
  for (const source of [workspace, pipelineWorkspace]) {
    assert.match(source, /tab=valuation#negotiation-governance/);
    assert.doesNotMatch(source, /tab=contract#negotiation/);
  }
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
    "contractImportDialog",
    "contractImportHeader",
    "contractImportBody",
    "offerActionDialog",
    "offerActionHeader",
    "offerActionBody",
  ]) {
    assert.match(styles, new RegExp(`\\.${className}\\b`));
  }
  assert.match(styles, /\.dragHandle[\s\S]*touch-action: none/);
});
