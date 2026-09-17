import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import { runAuthenticatedSmoke } from "./authenticated-smoke.mjs";

const smokePermissions = [
  "leads:view",
  "communications:view_conversations",
  "dispositions:view",
];

const workspaceMarkers = new Map([
  ["/os", "Daily work summary"],
  ["/os/leads", "Search, filter, assign, and move every active seller opportunity"],
  ["/os/inbox?view=team", "Company communications"],
  ["/os/deals?view=disposition&scope=team", "Market deals. Build investor relationships."],
]);

async function listen(handler) {
  const server = http.createServer(handler);
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Test server did not bind.");
  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    close: () => new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve())),
  };
}

async function jsonBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

test("mints short-lived Clerk tokens, checks protected routes, and revokes the session", async () => {
  let tokenCount = 0;
  let revoked = false;
  const clerk = await listen(async (request, response) => {
    assert.equal(request.headers.authorization, "Bearer sk_test_smoke");
    if (request.url === "/sessions" && request.method === "POST") {
      assert.deepEqual(await jsonBody(request), { user_id: "user_smoke" });
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({ id: "sess_smoke" }));
      return;
    }
    if (request.url === "/sessions/sess_smoke/tokens" && request.method === "POST") {
      tokenCount += 1;
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({ jwt: `token-${tokenCount}` }));
      return;
    }
    if (request.url === "/sessions/sess_smoke/revoke" && request.method === "POST") {
      revoked = true;
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({ id: "sess_smoke", status: "revoked" }));
      return;
    }
    response.writeHead(404).end();
  });
  const application = await listen((request, response) => {
    if (request.url?.startsWith("/api/v1/")) {
      assert.match(request.headers.authorization ?? "", /^Bearer token-\d+$/);
      response.setHeader("Content-Type", "application/json");
      if (request.url === "/api/v1/me") {
        response.end(JSON.stringify({
          user_id: "user-id",
          organization_id: "organization-id",
          email: "smoke@stonegate.test",
          permissions: smokePermissions,
        }));
        return;
      }
      if (request.url === "/api/v1/leads?limit=1&offset=0") {
        response.end(JSON.stringify({ items: [{
          id: "lead-id",
          seller_name: "Seller",
          stage_key: "new",
          property_address: "100 Main St",
        }] }));
        return;
      }
      if (request.url === "/api/v1/inbox/conversations") {
        response.end(JSON.stringify({ items: [{
          id: "conversation-id",
          conversation_type: "lead",
          queue_key: "default",
          response_state: "none",
          unread_count: 0,
        }] }));
        return;
      }
      if (request.url === "/api/v1/dispositions/desk?scope=team") {
        const section = { total: 0, returned: 0, has_more: false, offset: 0 };
        response.end(JSON.stringify({
          requested_scope: "team",
          effective_scope: "team",
          can_view_team: true,
          metrics: {
            today: 0,
            active_deals: 0,
            replies: 0,
            offers: 0,
            deadlines: 0,
          },
          sections: {
            today: section,
            active_deals: section,
            buyer_follow_ups: section,
            replies: section,
            offers: section,
            deadlines: section,
            coverage_warnings: section,
            deal_records: section,
          },
          source_health: { generated_at: "2026-09-17T12:00:00Z" },
          today: [],
          active_deals: [],
          buyer_follow_ups: [],
          replies: [],
          offers: [],
          deadlines: [],
          coverage_warnings: [],
          deal_records: [],
        }));
        return;
      }
      response.writeHead(404).end();
      return;
    }
    assert.match(request.headers.cookie ?? "", /^__session=token-\d+$/);
    response.setHeader("Content-Type", "text/html; charset=utf-8");
    response.end(
      `<!doctype html><title>Stonegate Operating System</title>${workspaceMarkers.get(request.url ?? "") ?? ""}`,
    );
  });

  try {
    const checked = await runAuthenticatedSmoke({
      clerkApiBaseUrl: clerk.baseUrl,
      env: {
        API_BASE_URL: application.baseUrl,
        WEB_BASE_URL: application.baseUrl,
        CLERK_SECRET_KEY: "sk_test_smoke",
        SMOKE_CLERK_USER_ID: "user_smoke",
      },
    });
    assert.deepEqual(checked, [
      "/api/v1/me",
      "/api/v1/leads?limit=1&offset=0",
      "/api/v1/inbox/conversations",
      "/api/v1/dispositions/desk?scope=team",
      "/os",
      "/os/leads",
      "/os/inbox?view=team",
      "/os/deals?view=disposition&scope=team",
    ]);
    assert.equal(tokenCount, checked.length);
    assert.equal(revoked, true);
  } finally {
    await Promise.all([application.close(), clerk.close()]);
  }
});

test("fails when a protected production data endpoint has the wrong shape", async () => {
  const application = await listen((request, response) => {
    response.setHeader("Content-Type", "application/json");
    if (request.url === "/api/v1/me") {
      response.end(JSON.stringify({
        user_id: "user-id",
        organization_id: "organization-id",
        email: "smoke@stonegate.test",
        permissions: smokePermissions,
      }));
      return;
    }
    if (request.url === "/api/v1/leads?limit=1&offset=0") {
      response.end(JSON.stringify({ items: "not-an-array" }));
      return;
    }
    response.end(JSON.stringify({ items: [] }));
  });

  try {
    await assert.rejects(
      runAuthenticatedSmoke({
        env: {
          API_BASE_URL: application.baseUrl,
          WEB_BASE_URL: application.baseUrl,
          SMOKE_CLERK_SESSION_TOKEN: "direct-test-token",
          SMOKE_WEB_PATHS: "/os",
        },
      }),
      /Protected leads API returned an invalid response shape/,
    );
  } finally {
    await application.close();
  }
});

test("fails when the disposition desk silently downgrades the company scope", async () => {
  const application = await listen((request, response) => {
    response.setHeader("Content-Type", "application/json");
    if (request.url === "/api/v1/me") {
      response.end(JSON.stringify({
        user_id: "user-id",
        organization_id: "organization-id",
        email: "smoke@stonegate.test",
        permissions: smokePermissions,
      }));
      return;
    }
    if (request.url === "/api/v1/dispositions/desk?scope=team") {
      response.end(JSON.stringify({
        requested_scope: "team",
        effective_scope: "mine",
        can_view_team: false,
      }));
      return;
    }
    response.end(JSON.stringify({ items: [] }));
  });

  try {
    await assert.rejects(
      runAuthenticatedSmoke({
        env: {
          API_BASE_URL: application.baseUrl,
          WEB_BASE_URL: application.baseUrl,
          SMOKE_CLERK_SESSION_TOKEN: "direct-test-token",
          SMOKE_WEB_PATHS: "/os",
        },
      }),
      /did not return the company team scope/,
    );
  } finally {
    await application.close();
  }
});

test("fails closed when a protected route redirects to sign-in", async () => {
  const application = await listen((request, response) => {
    if (request.url === "/api/v1/me") {
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({
        user_id: "user-id",
        organization_id: "organization-id",
        email: "smoke@stonegate.test",
        permissions: smokePermissions,
      }));
      return;
    }
    response.writeHead(307, { Location: "/sign-in" }).end();
  });

  try {
    await assert.rejects(
      runAuthenticatedSmoke({
        env: {
          API_BASE_URL: application.baseUrl,
          WEB_BASE_URL: application.baseUrl,
          SMOKE_CLERK_SESSION_TOKEN: "direct-test-token",
          SMOKE_WEB_PATHS: "/os",
        },
      }),
      /redirected to \/sign-in/,
    );
  } finally {
    await application.close();
  }
});

test("fails when a protected route renders only the shared shell", async () => {
  const application = await listen((request, response) => {
    if (request.url?.startsWith("/api/v1/")) {
      response.setHeader("Content-Type", "application/json");
      if (request.url === "/api/v1/me") {
        response.end(JSON.stringify({
          user_id: "user-id",
          organization_id: "organization-id",
          email: "smoke@stonegate.test",
          permissions: smokePermissions,
        }));
        return;
      }
      if (request.url === "/api/v1/dispositions/desk?scope=team") {
        const section = { total: 0, returned: 0, has_more: false, offset: 0 };
        response.end(JSON.stringify({
          requested_scope: "team",
          effective_scope: "team",
          can_view_team: true,
          metrics: { today: 0, active_deals: 0, replies: 0, offers: 0, deadlines: 0 },
          sections: Object.fromEntries(
            ["today", "active_deals", "buyer_follow_ups", "replies", "offers", "deadlines", "coverage_warnings", "deal_records"]
              .map((key) => [key, section]),
          ),
          source_health: { generated_at: "2026-09-17T12:00:00Z" },
          today: [], active_deals: [], buyer_follow_ups: [], replies: [], offers: [],
          deadlines: [], coverage_warnings: [], deal_records: [],
        }));
        return;
      }
      response.end(JSON.stringify({ items: [] }));
      return;
    }
    response.setHeader("Content-Type", "text/html; charset=utf-8");
    response.end("<!doctype html><title>Stonegate Operating System</title>");
  });

  try {
    await assert.rejects(
      runAuthenticatedSmoke({
        env: {
          API_BASE_URL: application.baseUrl,
          WEB_BASE_URL: application.baseUrl,
          SMOKE_CLERK_SESSION_TOKEN: "direct-test-token",
        },
      }),
      /did not render its workspace content/,
    );
  } finally {
    await application.close();
  }
});

test("requires an explicit credential and never falls back to development auth", async () => {
  await assert.rejects(
    runAuthenticatedSmoke({
      env: {
        API_BASE_URL: "http://127.0.0.1:8000",
        WEB_BASE_URL: "http://127.0.0.1:3000",
      },
    }),
    /CLERK_SECRET_KEY and SMOKE_CLERK_USER_ID/,
  );
});
