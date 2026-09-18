import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const control = readFileSync(
  resolve(process.cwd(), "src/app/os/leads/new-lead-control.tsx"),
  "utf8",
);

test("manual lead intake supports contact-first progressive creation", () => {
  assert.match(control, /Only a name and either a phone number or email are required/);
  assert.match(control, /if \(!phone && !email\)/);
  assert.match(control, /<option value="">Not sure yet<\/option>/);
  assert.match(control, /asset_class: assetClass \|\| null/);
  assert.match(control, /defaultValue="manual" name="source"/);
  assert.doesNotMatch(control, /name="street_address" required/);
  assert.doesNotMatch(control, /name="city" required/);
  assert.doesNotMatch(control, /name="postal_code" required/);
});
