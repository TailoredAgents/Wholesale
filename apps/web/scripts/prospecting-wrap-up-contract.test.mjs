import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const stateSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-wrap-up-state.ts"),
  "utf8",
);
const workspaceSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-workspace.tsx"),
  "utf8",
);
const dialerSource = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-dialer.tsx"),
  "utf8",
);
const apiSource = readFileSync(resolve(webRoot, "src/app/lib/api.ts"), "utf8");
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

function validation(overrides = {}) {
  return {
    outcome: "no_answer",
    callbackAt: "",
    handoffUserId: "",
    appointmentStartAt: "",
    appointmentLocationType: "",
    appointmentLocation: "",
    propertyAddress: "123 Main St, Atlanta, GA",
    qualificationSaveBlocked: false,
    missingWarmHandoffCount: 0,
    nativeDialer: true,
    nativeWrapUpReady: true,
    technicalFailure: false,
    now: new Date("2026-08-19T12:00:00.000Z"),
    ...overrides,
  };
}

function entry(overrides = {}) {
  return {
    legal_name: "Test Seller",
    status: "queued",
    next_attempt_at: "2026-08-20T12:00:00.000Z",
    ...overrides,
  };
}

test("callbacks and appointments require complete future commitments", async () => {
  const { validateProspectingWrapUp } = await importStateModule();
  assert.match(
    validateProspectingWrapUp(validation({ outcome: "callback_requested" })),
    /future callback date and time/,
  );
  assert.match(
    validateProspectingWrapUp(
      validation({
        outcome: "follow_up",
        callbackAt: "2026-08-19T07:00:00.000Z",
      }),
    ),
    /future callback date and time/,
  );
  assert.equal(
    validateProspectingWrapUp(
      validation({
        outcome: "callback_requested",
        callbackAt: "2026-08-20T12:00:00.000Z",
      }),
    ),
    null,
  );
  assert.match(
    validateProspectingWrapUp(
      validation({ outcome: "appointment_set", missingWarmHandoffCount: 1 }),
    ),
    /required warm-handoff question/,
  );
  assert.match(
    validateProspectingWrapUp(
      validation({
        outcome: "appointment_set",
        handoffUserId: "owner-one",
        appointmentStartAt: "2026-08-20T12:00:00.000Z",
        appointmentLocationType: "seller_property",
        propertyAddress: null,
      }),
    ),
    /where the appointment will happen/,
  );
});

test("only seller-property appointments may use the saved property as location", async () => {
  const { validateProspectingWrapUp } = await importStateModule();
  const appointment = {
    outcome: "appointment_set",
    handoffUserId: "owner-one",
    appointmentStartAt: "2026-08-20T12:00:00.000Z",
    appointmentLocation: "",
  };

  assert.equal(
    validateProspectingWrapUp(
      validation({
        ...appointment,
        appointmentLocationType: "seller_property",
      }),
    ),
    null,
  );
  for (const appointmentLocationType of ["phone", "video", "office"]) {
    assert.match(
      validateProspectingWrapUp(
        validation({ ...appointment, appointmentLocationType }),
      ),
      /where the appointment will happen/,
    );
  }
  assert.equal(
    validateProspectingWrapUp(
      validation({
        ...appointment,
        appointmentLocationType: "video",
        appointmentLocation: "https://meet.example.com/seller",
      }),
    ),
    null,
  );
  assert.match(
    workspaceSource,
    /appointmentLocationType !== "seller_property"[\s\S]*!entry\.property_address/,
  );
});

test("provider failure and active calls cannot be mislabeled as seller outcomes", async () => {
  const { PROSPECTING_OUTCOME_OPTIONS, validateProspectingWrapUp } =
    await importStateModule();
  assert.equal(
    PROSPECTING_OUTCOME_OPTIONS.some((option) => option.key === "technical_failure"),
    false,
  );
  assert.match(
    validateProspectingWrapUp(validation({ technicalFailure: true })),
    /technical call failure, not a seller outcome/,
  );
  assert.match(
    validateProspectingWrapUp(validation({ nativeWrapUpReady: false })),
    /reaches wrap-up/,
  );
  assert.match(workspaceSource, /technicalFailure \? \(/);
  assert.match(workspaceSource, /Record technical failure and return to queue/);
  assert.match(dialerSource, /\["failed", "cancelled"\]/);
});

test("receipts report only server-returned cadence and exact DNC target", async () => {
  const { createProspectingWrapUpReceipt } = await importStateModule();
  const retry = createProspectingWrapUpReceipt(
    entry(),
    "no_answer",
    "attempt-one",
  );
  assert.equal(retry.title, "Retry scheduled");
  assert.equal(retry.nextAttemptAt, "2026-08-20T12:00:00.000Z");

  const dnc = createProspectingWrapUpReceipt(
    entry({ status: "completed", next_attempt_at: null }),
    "do_not_call",
    "attempt-two",
    "+16785550100",
  );
  assert.match(dnc.detail, /exactly \+16785550100/);
  assert.match(workspaceSource, /if \(result\.data\) \{[\s\S]*createProspectingWrapUpReceipt/);
  assert.doesNotMatch(workspaceSource, /setLastWrapUp\([\s\S]{0,120}requestWrapUp/);
});

test("normal and technical wrap-up retries are stable and single-flight", () => {
  assert.match(apiSource, /ProspectingAttemptCompletionPayload[\s\S]*idempotency_key: string/);
  assert.match(apiSource, /ProspectingTechnicalFailurePayload[\s\S]*idempotency_key: string/);
  assert.match(workspaceSource, /pendingWrapUpRef/);
  assert.match(workspaceSource, /technicalFailureSubmissionRef/);
  assert.match(workspaceSource, /wrapUpInFlightRef\.current/);
  assert.match(workspaceSource, /idempotency_key: crypto\.randomUUID\(\)/);
  assert.match(workspaceSource, /pending\.payload/);
  assert.match(workspaceSource, /Retry safe wrap-up/);
  assert.doesNotMatch(workspaceSource, /localStorage/);
});

test("retry queues remain distinct from seller-requested callbacks", () => {
  assert.match(apiSource, /retries_due\?: number/);
  assert.match(apiSource, /retries_scheduled\?: number/);
  assert.match(workspaceSource, /item\.queue_kind === "retry_due"/);
  assert.match(workspaceSource, /"callback_scheduled", "retry_scheduled"/);
  assert.match(workspaceSource, /Retries due/);
});

test("manager monitoring stays read-only and mobile wrap-up remains touch safe", () => {
  assert.match(workspaceSource, /Read-only manager view/);
  assert.match(workspaceSource, /canMutateAttempt \? \(/);
  assert.match(cssSource, /@media \(max-width: 760px\)[\s\S]*\.outcomeChoices section/);
  assert.match(cssSource, /\.technicalOutcomeBoundary button,[\s\S]*min-height: 44px/);
});
