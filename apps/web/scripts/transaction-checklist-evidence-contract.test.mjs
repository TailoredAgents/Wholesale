import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = resolve(process.cwd(), "src/app");
const workspace = readFileSync(
  resolve(appRoot, "os/transactions/transaction-workspace.tsx"),
  "utf8",
);
const styles = readFileSync(
  resolve(appRoot, "os/transactions/transactions.module.css"),
  "utf8",
);

test("canonical closing checklist completion collects and submits evidence", () => {
  for (const key of ["open_title", "seller_documents", "due_diligence", "closing_confirmed"]) {
    assert.match(workspace, new RegExp(`"${key}"`));
  }
  assert.match(workspace, /Supporting evidence note/);
  assert.match(workspace, /Supporting evidence for \$\{item\.title\}/);
  assert.match(workspace, /evidenceNotes\.length < 10/);
  assert.match(workspace, /evidence_notes: evidenceNotes \|\| null/);
  assert.match(workspace, /Required to mark this item complete/);
  assert.match(styles, /\.checkEvidence textarea/);
});
