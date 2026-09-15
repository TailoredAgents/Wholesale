import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const workspaceSource = readFileSync(
  resolve(webRoot, "src/app/os/operations/operations-workspace.tsx"),
  "utf8",
);
const workspaceStyles = readFileSync(
  resolve(webRoot, "src/app/os/operations/operations.module.css"),
  "utf8",
);

test("team members have a visible, explicit removal control", () => {
  assert.match(workspaceSource, /className=\{styles\.removeMemberButton\}/);
  assert.match(workspaceSource, /<span>Remove<\/span>/);
  assert.match(
    workspaceSource,
    /This only changes team routing\.[\s\S]*owners keep company-wide access/,
  );
});

test("people settings explain owner visibility outside team membership", () => {
  assert.match(
    workspaceSource,
    /Owners keep company-wide visibility even when they are not a team member\./,
  );
});

test("the people editor gives teams equal width and keeps controls visible", () => {
  assert.match(workspaceSource, /styles\.twoColumn\} \$\{styles\.peopleGrid/);
  assert.match(
    workspaceStyles,
    /\.peopleGrid\s*\{\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/,
  );
  assert.match(
    workspaceStyles,
    /\.teamRow\s*\{[\s\S]*?display: grid;[\s\S]*?grid-template-columns: 1fr;/,
  );
});
