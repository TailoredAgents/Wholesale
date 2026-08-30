import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workspacePath = new URL(
  "../src/app/os/dispositions/disposition-execution-workspace.tsx",
  import.meta.url,
);
const parentPath = new URL(
  "../src/app/os/dispositions/disposition-workspace.tsx",
  import.meta.url,
);

test("the disposition workspace mounts a permission-aware one-to-one call queue", async () => {
  const [workspace, parent] = await Promise.all([
    readFile(workspacePath, "utf8"),
    readFile(parentPath, "utf8"),
  ]);

  assert.match(parent, /DispositionExecutionWorkspace/);
  assert.match(parent, /Call queue/);
  assert.match(workspace, /execution\/sms/);
  assert.match(workspace, /!candidate\.sms\.allowed/);
  assert.match(workspace, /execution\/calls/);
  assert.match(workspace, /!candidate\.voice\.allowed/);
  assert.match(workspace, /Open approved investor packet/);
  assert.match(workspace, /Text approved packet/);
  assert.match(workspace, /package\/share-links/);
  assert.match(workspace, /expires_in_hours: 72/);
  assert.doesNotMatch(workspace, /share-links\/\$\{issued\.id\}\/revoke/);
  assert.match(workspace, /check the buyer conversation before retrying/);
  assert.match(workspace, /idempotency_key: outcomeIdempotencyKey/);
  assert.match(workspace, /setOutcomeIdempotencyKey\(idempotency\("dispo-outcome"\)\)/);
  assert.match(workspace, /idempotency_key: `dispo-showing-/);
  assert.match(workspace, /outcome === "callback"/);
  assert.match(workspace, /No-answer gets a 4-hour retry task/);
});

test("showing controls persist state without exposing access secrets", async () => {
  const workspace = await readFile(workspacePath, "utf8");

  assert.match(workspace, /access_status/);
  assert.match(workspace, /Shared privately/);
  assert.match(workspace, /24-hour follow-up/);
  assert.match(workspace, /const finished = \["completed", "cancelled", "no_show"\]/);
  assert.doesNotMatch(workspace, /name="(?:lockbox|alarm|access)_code"/i);
});
