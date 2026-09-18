import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import ts from "typescript";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

async function companyTimeModule() {
  const typescript = await source("src/app/lib/company-time.ts");
  const javascript = ts.transpileModule(typescript, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`);
}

test("company time is deterministic across server and browser time zones", async () => {
  const time = await companyTimeModule();

  assert.equal(time.COMPANY_TIME_ZONE, "America/New_York");
  assert.equal(time.companyDateKey("2026-09-18T02:30:00Z"), "2026-09-17");
  assert.equal(time.companyDateTimeInputValue("2026-07-10T16:30:00Z"), "2026-07-10T12:30");
  assert.equal(time.companyDateTimeInputToIso("2026-07-10T12:30"), "2026-07-10T16:30:00.000Z");
  assert.equal(time.companyDateTimeInputToIso("2026-01-10T12:30"), "2026-01-10T17:30:00.000Z");
  assert.throws(
    () => time.companyDateTimeInputToIso("2026-03-08T02:30"),
    /daylight saving time/,
  );
});

test("lead lists distinguish provider receipt time from CRM ingestion time", async () => {
  const api = await source("src/app/lib/api.ts");
  const leads = await source("src/app/os/leads/leads-workspace.tsx");
  const utils = await source("src/app/os/os-utils.ts");

  assert.match(api, /received_at: string;/);
  assert.match(leads, /dateTime=\{lead\.received_at\}/);
  assert.match(leads, /Added to Stonegate/);
  assert.match(utils, /Date\.parse\(first\.received_at\)/);
});

test("transaction and meeting datetime inputs round-trip explicitly as Eastern time", async () => {
  const transaction = await source("src/app/os/transactions/transaction-workspace.tsx");
  const meeting = await source("src/app/os/field-operations/field-meeting-workspace.tsx");

  assert.match(transaction, /companyDateTimeInputToIso/);
  assert.match(transaction, /companyDateTimeInputValue\(detail\.closing_date\)/);
  assert.doesNotMatch(transaction, /detail\.closing_date\?\.slice\(0, 16\)/);
  assert.match(meeting, /companyDateTimeInputValue\(existing\?\.next_follow_up_at\)/);
  assert.doesNotMatch(meeting, /next_follow_up_at\?\.slice\(0, 16\)/);
});
