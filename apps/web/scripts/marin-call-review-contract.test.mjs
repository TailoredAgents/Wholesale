import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const root = resolve(import.meta.dirname, "../src/app/os/inbox");
const workspace = readFileSync(
  resolve(root, "marin-calls/marin-calls-workspace.tsx"),
  "utf8",
);
const inbox = readFileSync(resolve(root, "inbox-workspace.tsx"), "utf8");
const styles = readFileSync(resolve(root, "marin-calls/marin-calls.module.css"), "utf8");

test("Inbox links directly to the Marin call review workspace", () => {
  assert.match(inbox, /href="\/os\/inbox\/marin-calls"/);
  assert.match(inbox, />\s*Marin calls\s*</);
});

test("Marin workspace separates the lightweight list from transcript detail", () => {
  assert.match(workspace, /\/api\/v1\/voice\/marin-calls\?days=30&limit=200/);
  assert.match(workspace, /\/api\/v1\/voice\/marin-calls\/\$\{callbackId\}/);
  assert.match(workspace, /Caller and Marin transcript/);
  assert.match(workspace, /Realtime transcripts are review aids/);
  assert.match(workspace, /Suspected prompt-generated text is removed/);
  assert.match(workspace, /callPathExplanation/);
});

test("Marin workspace exposes operational counts and human review controls", () => {
  for (const label of [
    "Today",
    "Last 7 days",
    "Unique callers",
    "Seller callbacks saved",
    "Human handoffs",
    "Needs review",
  ]) {
    assert.match(workspace, new RegExp(label));
  }
  assert.match(workspace, /seller_callbacks_captured_30_days/);
  assert.match(workspace, /fully_qualified_sellers_30_days/);
  assert.match(workspace, /conversations_started_30_days/);
  assert.match(workspace, /ended_during_greeting_30_days/);
  assert.match(workspace, /caller_audio_issues_30_days/);
  assert.match(workspace, /What should Marin improve\?/);
  assert.match(workspace, /Save issue/);
  assert.match(workspace, /Mark reviewed/);
  assert.match(workspace, /Resolve/);
});

test("Marin activity metrics filter the call list", () => {
  for (const filter of [
    "today",
    "last_7_days",
    "unique_callers",
    "seller_callbacks",
    "human_handoffs",
    "needs_review",
  ]) {
    assert.match(workspace, new RegExp(`activateSummaryFilter\\(\"${filter}\"\\)`));
  }
  assert.match(workspace, /aria-pressed=\{filter === "today"\}/);
  assert.match(workspace, /item\.capture_status !== "none"/);
  assert.match(workspace, /item\.outcome === "transferred"/);
  assert.match(workspace, /const seen = new Set<string>\(\)/);
  assert.match(styles, /\.statFilter\[data-active="true"\]/);
});

test("Marin workspace stays dense and independently scrollable", () => {
  assert.match(styles, /height: calc\(100dvh - 124px\)/);
  assert.match(styles, /grid-template-columns: minmax\(300px, 340px\) minmax\(0, 1fr\)/);
  assert.match(styles, /\.callList[\s\S]*overflow-y: auto/);
  assert.match(styles, /\.transcriptColumn,[\s\S]*overflow-y: auto/);
});
