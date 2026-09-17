import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const DEFAULT_WEB_PATHS = [
  "/os",
  "/os/leads",
  "/os/inbox?view=team",
  "/os/deals?view=disposition&scope=team",
];
const DEFAULT_WEB_ROUTE_MARKERS = new Map([
  ["/os", "Daily work summary"],
  ["/os/leads", "Search, filter, assign, and move every active seller opportunity"],
  ["/os/inbox?view=team", "Company communications"],
  [
    "/os/deals?view=disposition&scope=team",
    "Market deals. Build investor relationships.",
  ],
]);
const LEADS_PATH = "/api/v1/leads?limit=1&offset=0";
const CONVERSATIONS_PATH = "/api/v1/inbox/conversations";
const DISPOSITION_DESK_PATH = "/api/v1/dispositions/desk?scope=team";
const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_CLERK_API_BASE_URL = "https://api.clerk.com/v1";

function normalizedBaseUrl(value, name) {
  if (!value) throw new Error(`${name} is required.`);
  const url = new URL(value);
  const localHostnames = new Set(["localhost", "127.0.0.1", "::1"]);
  if (url.protocol !== "https:" && !localHostnames.has(url.hostname)) {
    throw new Error(`${name} must use HTTPS outside localhost.`);
  }
  return url.toString().replace(/\/$/, "");
}

function responseDetail(body) {
  const compact = body.replace(/\s+/g, " ").trim();
  return compact ? ` Response: ${compact.slice(0, 500)}` : "";
}

async function fetchWithTimeout(fetchImpl, url, options, timeoutMs) {
  return fetchImpl(url, {
    ...options,
    signal: AbortSignal.timeout(timeoutMs),
  });
}

async function expectSuccessfulResponse(response, label) {
  const body = await response.text();
  if (response.status < 200 || response.status >= 300) {
    const location = response.headers.get("location");
    throw new Error(
      `${label} returned HTTP ${response.status}${location ? ` and redirected to ${location}` : ""}.` +
        responseDetail(body),
    );
  }
  return body;
}

function recordValue(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} returned an invalid response shape.`);
  }
  return value;
}

function stringValue(value, label) {
  if (typeof value !== "string" || !value) {
    throw new Error(`${label} returned an invalid response shape.`);
  }
}

function arrayValue(value, label) {
  if (!Array.isArray(value)) {
    throw new Error(`${label} returned an invalid response shape.`);
  }
  return value;
}

async function checkProtectedJson({
  apiBaseUrl,
  credential,
  fetchImpl,
  label,
  origin,
  path,
  timeoutMs,
  validate,
}) {
  const token = await credential.getToken();
  const response = await fetchWithTimeout(
    fetchImpl,
    `${apiBaseUrl}${path}`,
    {
      redirect: "manual",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        Origin: origin,
        "User-Agent": "stonegate-authenticated-smoke/1.0",
      },
    },
    timeoutMs,
  );
  const body = await expectSuccessfulResponse(response, label);
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    throw new Error(`${label} did not return JSON.`);
  }
  let payload;
  try {
    payload = JSON.parse(body);
  } catch {
    throw new Error(`${label} returned invalid JSON.`);
  }
  validate(payload);
}

function validateWorkspaceIdentity(payload) {
  const me = recordValue(payload, "Protected API /api/v1/me");
  if (
    typeof me.user_id !== "string" ||
    typeof me.organization_id !== "string" ||
    typeof me.email !== "string" ||
    !Array.isArray(me.permissions)
  ) {
    throw new Error("Protected API /api/v1/me returned an incomplete workspace identity.");
  }
  const requiredPermissionGroups = [
    ["leads:view", "leads:view_assigned"],
    ["communications:view_conversations", "communications:view_assigned_conversations"],
    ["dispositions:view", "buyers:view"],
  ];
  for (const alternatives of requiredPermissionGroups) {
    if (!alternatives.some((permission) => me.permissions.includes(permission))) {
      throw new Error(
        `Production smoke user is missing one of: ${alternatives.join(", ")}.`,
      );
    }
  }
}

function validateLeads(payload) {
  const response = recordValue(payload, "Protected leads API");
  const items = arrayValue(response.items, "Protected leads API");
  if (items.length === 0) return;
  const item = recordValue(items[0], "Protected leads API item");
  stringValue(item.id, "Protected leads API item");
  stringValue(item.seller_name, "Protected leads API item");
  stringValue(item.stage_key, "Protected leads API item");
  stringValue(item.property_address, "Protected leads API item");
}

function validateConversations(payload) {
  const response = recordValue(payload, "Protected conversations API");
  const items = arrayValue(response.items, "Protected conversations API");
  if (items.length === 0) return;
  const item = recordValue(items[0], "Protected conversations API item");
  stringValue(item.id, "Protected conversations API item");
  stringValue(item.conversation_type, "Protected conversations API item");
  stringValue(item.queue_key, "Protected conversations API item");
  stringValue(item.response_state, "Protected conversations API item");
  if (typeof item.unread_count !== "number") {
    throw new Error("Protected conversations API item returned an invalid response shape.");
  }
}

function validateDispositionDesk(payload) {
  const desk = recordValue(payload, "Protected disposition desk API");
  if (
    desk.requested_scope !== "team" ||
    desk.effective_scope !== "team" ||
    desk.can_view_team !== true
  ) {
    throw new Error("Protected disposition desk API did not return the company team scope.");
  }
  const metrics = recordValue(desk.metrics, "Protected disposition desk API metrics");
  const sections = recordValue(desk.sections, "Protected disposition desk API sections");
  for (const key of ["today", "active_deals", "replies", "offers", "deadlines"]) {
    if (metrics[key] !== null && typeof metrics[key] !== "number") {
      throw new Error(`Protected disposition desk API metric ${key} is invalid.`);
    }
  }
  const sourceHealth = recordValue(
    desk.source_health,
    "Protected disposition desk API source health",
  );
  stringValue(sourceHealth.generated_at, "Protected disposition desk API source health");
  for (const key of [
    "today",
    "active_deals",
    "buyer_follow_ups",
    "replies",
    "offers",
    "deadlines",
    "coverage_warnings",
    "deal_records",
  ]) {
    arrayValue(desk[key], `Protected disposition desk API ${key}`);
    const section = recordValue(sections[key], `Protected disposition desk API section ${key}`);
    if (
      typeof section.total !== "number" ||
      typeof section.returned !== "number" ||
      typeof section.has_more !== "boolean" ||
      typeof section.offset !== "number"
    ) {
      throw new Error(`Protected disposition desk API section ${key} is invalid.`);
    }
  }
}

async function clerkRequest({
  clerkApiBaseUrl,
  fetchImpl,
  path,
  secretKey,
  timeoutMs,
  body,
}) {
  const response = await fetchWithTimeout(
    fetchImpl,
    `${clerkApiBaseUrl}${path}`,
    {
      method: "POST",
      redirect: "manual",
      headers: {
        Authorization: `Bearer ${secretKey}`,
        "Content-Type": "application/json",
        "User-Agent": "stonegate-authenticated-smoke/1.0",
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    },
    timeoutMs,
  );
  const responseBody = await expectSuccessfulResponse(response, `Clerk ${path}`);
  try {
    return JSON.parse(responseBody);
  } catch {
    throw new Error(`Clerk ${path} returned invalid JSON.`);
  }
}

export async function createClerkCredential({
  secretKey,
  userId,
  fetchImpl = fetch,
  clerkApiBaseUrl = DEFAULT_CLERK_API_BASE_URL,
  timeoutMs = DEFAULT_TIMEOUT_MS,
}) {
  if (!secretKey || !userId) {
    throw new Error(
      "CLERK_SECRET_KEY and SMOKE_CLERK_USER_ID are both required when no direct session token is supplied.",
    );
  }
  const normalizedClerkBase = normalizedBaseUrl(clerkApiBaseUrl, "Clerk API base URL");
  const session = await clerkRequest({
    clerkApiBaseUrl: normalizedClerkBase,
    fetchImpl,
    path: "/sessions",
    secretKey,
    timeoutMs,
    body: { user_id: userId },
  });
  if (!session || typeof session.id !== "string" || !session.id) {
    throw new Error("Clerk session creation returned no session ID.");
  }

  let revoked = false;
  return {
    async getToken() {
      const tokenPayload = await clerkRequest({
        clerkApiBaseUrl: normalizedClerkBase,
        fetchImpl,
        path: `/sessions/${encodeURIComponent(session.id)}/tokens`,
        secretKey,
        timeoutMs,
      });
      if (!tokenPayload || typeof tokenPayload.jwt !== "string" || !tokenPayload.jwt) {
        throw new Error("Clerk session token creation returned no JWT.");
      }
      return tokenPayload.jwt;
    },
    async revoke() {
      if (revoked) return;
      revoked = true;
      await clerkRequest({
        clerkApiBaseUrl: normalizedClerkBase,
        fetchImpl,
        path: `/sessions/${encodeURIComponent(session.id)}/revoke`,
        secretKey,
        timeoutMs,
      });
    },
  };
}

function directTokenCredential(token) {
  return {
    async getToken() {
      return token;
    },
    async revoke() {},
  };
}

function parseWebPaths(value) {
  if (!value) return DEFAULT_WEB_PATHS;
  const paths = value
    .split(",")
    .map((path) => path.trim())
    .filter(Boolean);
  if (paths.length === 0 || paths.some((path) => !path.startsWith("/"))) {
    throw new Error("SMOKE_WEB_PATHS must be a comma-separated list of absolute paths.");
  }
  return paths;
}

export async function runAuthenticatedSmoke({
  env = process.env,
  fetchImpl = fetch,
  clerkApiBaseUrl = DEFAULT_CLERK_API_BASE_URL,
} = {}) {
  const apiBaseUrl = normalizedBaseUrl(env.API_BASE_URL, "API_BASE_URL");
  const webBaseUrl = normalizedBaseUrl(env.WEB_BASE_URL, "WEB_BASE_URL");
  const timeoutMs = Number(env.SMOKE_REQUEST_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS);
  if (!Number.isFinite(timeoutMs) || timeoutMs < 1_000 || timeoutMs > 120_000) {
    throw new Error("SMOKE_REQUEST_TIMEOUT_MS must be between 1000 and 120000 milliseconds.");
  }
  const webPaths = parseWebPaths(env.SMOKE_WEB_PATHS);
  const directToken = env.SMOKE_CLERK_SESSION_TOKEN?.trim();
  const credential = directToken
    ? directTokenCredential(directToken)
    : await createClerkCredential({
        secretKey: env.CLERK_SECRET_KEY,
        userId: env.SMOKE_CLERK_USER_ID,
        fetchImpl,
        clerkApiBaseUrl,
        timeoutMs,
      });
  const checked = [];

  try {
    const apiChecks = [
      {
        path: "/api/v1/me",
        label: "Protected API /api/v1/me",
        validate: validateWorkspaceIdentity,
      },
      { path: LEADS_PATH, label: "Protected leads API", validate: validateLeads },
      {
        path: CONVERSATIONS_PATH,
        label: "Protected conversations API",
        validate: validateConversations,
      },
      {
        path: DISPOSITION_DESK_PATH,
        label: "Protected disposition desk API",
        validate: validateDispositionDesk,
      },
    ];
    for (const check of apiChecks) {
      await checkProtectedJson({
        apiBaseUrl,
        credential,
        fetchImpl,
        label: check.label,
        origin: webBaseUrl,
        path: check.path,
        timeoutMs,
        validate: check.validate,
      });
      checked.push(check.path);
    }

    for (const path of webPaths) {
      const webToken = await credential.getToken();
      const response = await fetchWithTimeout(
        fetchImpl,
        `${webBaseUrl}${path}`,
        {
          redirect: "manual",
          headers: {
            Cookie: `__session=${webToken}`,
            "User-Agent": "stonegate-authenticated-smoke/1.0",
          },
        },
        timeoutMs,
      );
      const html = await expectSuccessfulResponse(response, `Protected web route ${path}`);
      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.toLowerCase().includes("text/html")) {
        throw new Error(`Protected web route ${path} did not return HTML.`);
      }
      if (!html.includes("Stonegate Operating System")) {
        throw new Error(`Protected web route ${path} did not render the OS shell.`);
      }
      const routeMarker = DEFAULT_WEB_ROUTE_MARKERS.get(path);
      if (routeMarker && !html.includes(routeMarker)) {
        throw new Error(`Protected web route ${path} did not render its workspace content.`);
      }
      if (html.includes("Stonegate authentication is temporarily unavailable")) {
        throw new Error(`Protected web route ${path} rendered the authentication outage page.`);
      }
      checked.push(path);
    }
  } finally {
    await credential.revoke();
  }

  return checked;
}

async function main() {
  const checked = await runAuthenticatedSmoke();
  console.log(`Authenticated smoke passed: ${checked.join(", ")}`);
}

const invokedPath = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : "";
if (invokedPath === import.meta.url) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
