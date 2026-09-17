import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const inboxStyles = readFileSync(
  resolve(scriptDirectory, "../src/app/os/inbox/inbox.module.css"),
  "utf8",
);

function firstRule(selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return inboxStyles.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`))?.[1] ?? "";
}

test("conversation threads preserve a useful message-reading area", () => {
  const threadPane = firstRule(".threadPane");
  assert.match(threadPane, /grid-template-rows:\s*auto auto minmax\(160px, 1fr\) auto/);
  assert.match(threadPane, /overflow:\s*hidden/);
});

test("the composer yields space to the timeline and scrolls its advanced controls", () => {
  const composer = firstRule(".composer");
  assert.match(composer, /max-height:\s*min\(300px, 38dvh\)/);
  assert.match(composer, /overflow-y:\s*auto/);
  assert.match(composer, /overscroll-behavior-y:\s*contain/);
  assert.match(inboxStyles, /max-height:\s*min\(34dvh, 280px\)/);
});
