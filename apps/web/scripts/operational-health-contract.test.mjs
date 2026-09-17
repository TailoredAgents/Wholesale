import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const render = readFileSync("../../render.yaml", "utf8");
const webHealthRoute = readFileSync("src/app/health/route.ts", "utf8");

function serviceBlock(name) {
  const marker = `    name: ${name}`;
  assert.ok(render.includes(marker), `${name} must exist in render.yaml`);
  return render.split(marker, 2)[1].split("\n  - type:", 1)[0];
}

test("Render probes application readiness rather than unconditional API liveness", () => {
  assert.match(serviceBlock("oakwell-web"), /healthCheckPath: \/health/);
  assert.match(serviceBlock("oakwell-api"), /healthCheckPath: \/ready/);
});

test("the web health check executes a no-store route handler", () => {
  assert.match(webHealthRoute, /export function GET/);
  assert.match(webHealthRoute, /status: "ok"/);
  assert.match(webHealthRoute, /"Cache-Control": "no-store"/);
});
