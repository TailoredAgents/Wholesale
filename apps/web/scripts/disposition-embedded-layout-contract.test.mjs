import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const dispositionRoot = resolve(process.cwd(), "src/app/os/dispositions");

function source(file) {
  return readFileSync(resolve(dispositionRoot, file), "utf8");
}

test("every embedded disposition tab responds to the Deal panel width", () => {
  const workspace = source("disposition-workspace.tsx");
  const shared = source("dispositions.module.css");
  const tabStyles = new Map([
    ["Packet", source("disposition-package-readiness.module.css")],
    ["Find buyers", shared],
    ["Outreach desk", source("disposition-execution-workspace.module.css")],
    ["Bulk outreach", source("disposition-outreach-workspace.module.css")],
    ["Offers & closing", source("disposition-offer-room.module.css")],
    ["External distribution", source("disposition-provider-workspace.module.css")],
    ["Finance reconciliation", shared],
  ]);

  assert.match(shared, /container: disposition-detail \/ inline-size/);
  assert.match(shared, /\.body\.embeddedBody\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s);
  assert.match(shared, /@container disposition-detail \(max-width: 1100px\)/);
  assert.match(shared, /@container disposition-detail \(max-width: 760px\)/);

  for (const [label, styles] of tabStyles) {
    assert.match(workspace, new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.match(styles, /@container disposition-detail \(max-width:/, `${label} needs an embedded-width layout`);
  }
});
