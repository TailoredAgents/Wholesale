import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const api = readFileSync(resolve(appRoot, "lib/api.ts"), "utf8");
const deals = readFileSync(resolve(appRoot, "os/deals/deals-workspace.tsx"), "utf8");
const dealsPage = readFileSync(resolve(appRoot, "os/deals/page.tsx"), "utf8");
const disposition = readFileSync(resolve(appRoot, "os/dispositions/disposition-workspace.tsx"), "utf8");
const room = readFileSync(resolve(appRoot, "os/dispositions/disposition-offer-room.tsx"), "utf8");
const roomStyles = readFileSync(resolve(appRoot, "os/dispositions/disposition-offer-room.module.css"), "utf8");
const transaction = readFileSync(resolve(appRoot, "os/transactions/transaction-workspace.tsx"), "utf8");

test("DS7 replaces the basic offer list with one canonical Offer Room", () => {
  assert.match(disposition, /<DispositionOfferRoom/);
  assert.match(disposition, /item === "offers" \? "Offer Room"/);
  assert.doesNotMatch(disposition, /<h4>Buyer offers<\/h4>/);
  assert.match(deals, /"offers"/);
  assert.match(api, /export type DispositionOfferRoomWorkspace/);
  assert.match(room, /\/offer-room/);
  assert.match(disposition, /item !== "offers" \|\| data\.can_view_private_economics/);
  assert.match(disposition, /tab === "offers" && data\.can_view_private_economics/);
  assert.match(disposition, /initialTab === "offers" && !initialData\.can_view_private_economics/);
});

test("normalized offers compare execution terms and explain risk evidence", () => {
  for (const text of [
    "Offer amount",
    "Earnest money",
    "Due diligence",
    "Closing",
    "Funding",
    "Proof of funds",
    "Reliability",
    "Risk",
  ]) assert.match(room, new RegExp(text));
  assert.match(api, /risk_flags:/);
  assert.match(api, /contingencies:/);
  assert.match(api, /contingencies_confirmed:/);
  assert.match(api, /proof_status:/);
  assert.match(api, /reliability_score_basis_points:/);
  assert.match(room, /supporting_evidence/);
  assert.match(room, /A higher price can still be a weaker executable offer/);
  assert.equal(room.match(/<span>Funding confidence<\/span>/g)?.length, 2);
  assert.match(room, /defaultValue="unknown" name="funding_method"/);
  assert.match(room, /defaultValue="0" name="funding_confidence"/);
  assert.match(room, /Earnest money \(optional\)/);
  assert.match(room, /due_diligence_days: optionalNumber/);
  assert.match(room, /contingencies_confirmed/);
  assert.match(room, /Unknown - buyer terms have not been confirmed/);
  assert.match(room, /const payload: Record<string, unknown>/);
  assert.match(room, /addIfEntered\("amount", "amount_cents"/);
  assert.match(room, /latest_proof_document_id \?\? offer\.proof_document_id/);
  assert.match(room, /Blank revision fields keep their saved values/);
});

test("selection and replacement remain reason-required human actions", () => {
  assert.match(room, /Human-approved primary/);
  assert.match(room, /Primary offer/);
  assert.match(room, /Backup offer/);
  assert.match(room, /selection_reason/);
  assert.match(room, /Activate backup buyer/);
  assert.match(room, /replacement_reason/);
  assert.match(room, /Primary and backup coverage must use offers from different buyers/);
  assert.match(room, /Unselected viable offers stay available/);
  assert.match(room, /eligibility_override_reason/);
  assert.match(room, /approved minimum price cannot be overridden/);
  assert.match(room, /Approve new coverage version/);
  assert.match(room, /Earlier selections remain in history/);
  assert.match(room, /Coverage approval is stale/);
  assert.match(room, /Live coverage blockers/);
  assert.match(room, /Reapprove changed coverage/);
  assert.match(room, /keep the same primary and backup/);
  assert.match(room, /expected_offer_lock_versions/);
  assert.match(room, /expected_selection_lock_version/);
  assert.match(room, /canViewPrivateEconomics/);
  assert.match(room, /canEditDeals/);
  assert.match(room, /canApproveBuyerSelection/);
  assert.match(dealsPage, /dispositions:approve_buyer_selection/);
  assert.doesNotMatch(room, /auto.?select/i);
});

test("closing protection keeps checklist, deadlines, alerts, and outcomes operational", () => {
  for (const label of [
    "Agreement",
    "Signature",
    "Deposit",
    "Access",
    "Title",
    "Closing",
    "Missed deadline",
    "Record outcome",
    "Negotiation history",
  ]) assert.match(room, new RegExp(label));
  assert.match(room, /isCheckpointOverdue\(deadline\)/);
  assert.match(room, /Complete milestone/);
  assert.match(room, /Record deposit/);
  assert.match(room, /Waive deposit/);
  assert.match(room, /minLength=\{10\}/);
  assert.match(room, /evidenceNote\.trim\(\)\.length >= 10/);
  assert.match(room, /canApproveWaiver/);
  assert.match(room, /Manager approval is required to waive a deposit/);
  assert.match(room, /confirmation_note/);
  assert.match(room, /decision: status === "completed" \? "received" : "waived"/);
  assert.match(room, /data-status="waived"|status === "waived"/);
  assert.match(room, /Update in Deal \/ Transaction/);
  assert.match(room, /Acknowledge alert/);
  assert.match(room, /pass|withdrawal|fallout|retrade/);
  assert.doesNotMatch(room, /<option value="completed_close"/);
  assert.match(room, /funded transaction records the completed close automatically/);
  assert.match(room, /currentSelectionOfferIds/);
  assert.match(room, /currentSelectionOfferIds\.has\(offer\.id\)/);
  assert.match(api, /selection_history:/);
  assert.match(api, /negotiation_history:/);
  assert.match(api, /checkpoints:/);
  assert.match(api, /outcomes:/);
  assert.match(room, /status: "completed"/);
  assert.match(room, /cause_category/);
  assert.match(room, /evidence: \{\}/);
});

test("the Offer Room gives Alex one evidence-backed buyer-to-closing path", () => {
  for (const label of [
    "Buyer offer recorded",
    "Proof and terms verified",
    "Primary and backup approved",
    "Buyer deposit secured",
    "Title and access cleared",
    "Funded and closed",
  ]) assert.match(room, new RegExp(label));
  assert.match(room, /Interested buyer to funded closing/);
  assert.match(room, /Nothing is marked complete from a guess/);
  assert.match(room, /outcome\.outcome_type === "completed_close"/);
  assert.match(room, /data\.strategy_agreement\.label/);
  assert.match(room, /data\.strategy_agreement\.ready/);
  assert.match(room, /data\.strategy_agreement\.blockers/);
  assert.match(api, /strategy_agreement:/);
  assert.match(room, /proof_verified_amount_cents >= offerForVerification\.amount_cents/);
  assert.match(room, /new Date\(offerForVerification\.proof_expires_at\)\.getTime\(\) > generatedAt/);
  assert.match(room, /new Date\(offerForVerification\.proposed_closing_at\)\.getTime\(\) > generatedAt/);
  assert.match(room, /canonicalChecklistComplete\("title"\)/);
  assert.match(room, /canonicalChecklistComplete\("access"\)/);
  assert.match(room, /checkpoint\.canonical_source === "transaction_checklist"/);
  assert.match(room, /hasCanonicalChecklistEvidence/);
  assert.match(room, /checkpoint\.canonical_source === "buyer_offer"/);
  assert.match(room, /depositCheckpoint\?\.status === "waived"/);
  assert.match(room, /primaryEarnestMoneyCents != null/);
  assert.match(room, /primaryEarnestMoneyCents === 0/);
  assert.match(room, /resolved: closingComplete \|\| depositDecisionResolved/);
  assert.match(room, /warning: !closingComplete && depositWaived/);
  assert.match(room, /aria-current="step"/);
  assert.match(roomStyles, /\.placementSteps li\[data-state="current"\]/);
  assert.match(roomStyles, /scroll-snap-type: inline proximity/);
});

test("unknown mutation outcomes reuse stable idempotency keys", () => {
  assert.match(room, /pendingIdempotencyKeysRef/);
  assert.match(room, /pendingIdempotencyKey\(idempotencyAction, "offer"\)/);
  assert.match(room, /clearPendingIdempotencyKey\(idempotencyAction\)/);
  assert.match(room, /disabled=\{busyAction !== null/);
});

test("assignment execution uses the frozen selected-buyer identity", () => {
  assert.match(api, /assignee_name: string \| null/);
  assert.match(api, /assignee_email: string \| null/);
  assert.match(transaction, /assignee_name: documentType === "assignment_contract"/);
  assert.match(transaction, /assignee_email: documentType === "assignment_contract"/);
  assert.match(transaction, /signaturePackage\?\.assignee_name/);
  assert.match(transaction, /signaturePackage\?\.assignee_email/);
  assert.match(transaction, /readOnly=\{signatureDocumentType === "assignment_contract"\}/);
  assert.match(transaction, /The assignee is frozen from the approved Offer Room buyer selection/);
  assert.match(transaction, /Void approved package/);
  assert.match(transaction, /withdrawManualPackage\(pkg\.id, pkg\.status\)/);
});

test("the Offer Room has explicit load errors, accessibility, and responsive comparison", () => {
  assert.match(room, /role="alert"/);
  assert.match(room, /aria-live="polite"/);
  assert.match(room, /aria-labelledby="offer-comparison-heading"/);
  assert.match(room, /aria-labelledby="closing-protection-heading"/);
  assert.match(room, /Retry/);
  assert.match(room, /House disposition - Offer Room/);
  assert.match(roomStyles, /overflow-x: auto/);
  assert.match(roomStyles, /min-height: 44px/);
  assert.match(roomStyles, /@media \(max-width: 760px\)/);
  assert.match(roomStyles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("Offer Room source contains no mojibake separators", () => {
  assert.doesNotMatch(room, /[\u00b7\u00c2\u00c3\ufffd]/);
});
