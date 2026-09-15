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

test("executed House and Land transactions expose the signed amendment workflow", () => {
  assert.match(workspace, /Record a signed amendment/);
  assert.match(workspace, /executed-amendments/);
  assert.match(workspace, /expected_purchase_price_cents/);
  assert.match(workspace, /revised_purchase_price_cents/);
  assert.match(workspace, /Keep the current investor asking price/);
  assert.match(workspace, /Set a new investor asking price/);
  assert.match(workspace, /every required party signed this exact PDF/);
  assert.match(workspace, /approved investor packet and active packet link will be retired/);
  assert.match(workspace, /Open signed PDF/);
  assert.doesNotMatch(workspace, /assetClass === "house" \? <form className=\{`\$\{styles\.form\} \$\{styles\.amendmentForm\}`\}/);
  assert.match(styles, /\.amendmentForm/);
  assert.match(styles, /\.amendmentSummary/);
});
